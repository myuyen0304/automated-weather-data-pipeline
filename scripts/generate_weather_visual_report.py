from __future__ import annotations

import html
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform_weather import list_raw_weather_files, normalize_weather_record


OUTPUT_PATH = PROJECT_ROOT / "reports" / "weather_snapshot.html"
LATEST_OUTPUT_PATH = PROJECT_ROOT / "reports" / "weather_snapshot_latest.html"


def _fmt_number(value: object, digits: int = 1) -> str:
    if pd.isna(value):
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _escape(value: object) -> str:
    return html.escape(str(value))


def _bar_chart(
    rows: Iterable[dict[str, object]],
    label_key: str,
    value_key: str,
    color: str,
    value_suffix: str = "",
    value_display_key: str | None = None,
) -> str:
    rows = list(rows)
    max_value = max((float(row[value_key]) for row in rows), default=0.0)
    if max_value <= 0:
        max_value = 1.0

    items = []
    for row in rows:
        label = _escape(row[label_key])
        value = float(row[value_key])
        width = max(2.0, value / max_value * 100)
        items.append(
            f"""
            <div class="bar-row">
              <div class="bar-label" title="{label}">{label}</div>
              <div class="bar-track">
                <div class="bar-fill" style="width:{width:.2f}%; background:{color};"></div>
              </div>
              <div class="bar-value">{_escape(row[value_display_key]) if value_display_key else _fmt_number(value)}{value_suffix}</div>
            </div>
            """
        )
    return "\n".join(items)


def _table(df: pd.DataFrame, columns: list[str], limit: int = 20) -> str:
    header = "".join(f"<th>{_escape(column)}</th>" for column in columns)
    body_rows = []
    for _, row in df.head(limit).iterrows():
        cells = "".join(f"<td>{_escape(row[column])}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"""
    <table>
      <thead><tr>{header}</tr></thead>
      <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def load_raw_history() -> pd.DataFrame:
    raw_files = list_raw_weather_files(include_history=True)
    records = [normalize_weather_record(raw_path) for raw_path in raw_files]
    df = pd.DataFrame(records)
    df["observation_time"] = pd.to_datetime(df["observation_time"])
    df["date"] = df["observation_time"].dt.date.astype(str)
    return df.sort_values(["observation_time", "city"])


def build_report(df: pd.DataFrame) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    latest_time = df["observation_time"].max()
    latest_date = latest_time.date().isoformat()
    latest_df = df[df["date"] == latest_date].copy()

    coverage = (
        df.groupby("date")
        .agg(records=("city", "count"), cities=("city", "nunique"))
        .reset_index()
        .sort_values("date")
    )

    latest_temp = (
        latest_df[["city", "temperature", "humidity", "rain", "weather_condition"]]
        .sort_values("temperature", ascending=False)
        .reset_index(drop=True)
    )

    temp_rows = latest_temp.head(12).rename(columns={"city": "label", "temperature": "value"})
    rain_rows = (
        latest_df.groupby("city", as_index=False)["rain"]
        .sum()
        .sort_values("rain", ascending=False)
        .head(12)
        .rename(columns={"city": "label", "rain": "value"})
    )
    humidity_rows = (
        latest_df[["city", "humidity"]]
        .sort_values("humidity", ascending=False)
        .head(12)
        .rename(columns={"city": "label", "humidity": "value"})
    )
    coverage_display = coverage.rename(columns={"date": "label", "records": "value"}).copy()
    coverage_display["display"] = coverage_display.apply(
        lambda row: f"{int(row['value'])} records / {int(row['cities'])} cities",
        axis=1,
    )
    coverage_rows = coverage_display.to_dict("records")

    city_count = df["city"].nunique()
    date_count = df["date"].nunique()
    row_count = len(df)
    expected_per_full_day = city_count
    full_days = int((coverage["records"] >= expected_per_full_day).sum())

    latest_table = latest_temp.copy()
    latest_table["temperature"] = latest_table["temperature"].map(lambda value: f"{value:.1f}")
    latest_table["humidity"] = latest_table["humidity"].map(lambda value: f"{value:.0f}")
    latest_table["rain"] = latest_table["rain"].map(lambda value: f"{value:.1f}")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weather Data Snapshot</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #1d2433;
      --muted: #667085;
      --line: #d9dee7;
      --blue: #2474b8;
      --green: #2f855a;
      --amber: #b7791f;
      --red: #c2410c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, Segoe UI, Arial, sans-serif;
      letter-spacing: 0;
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 24px auto 40px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: end;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      line-height: 1.15;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 17px;
      line-height: 1.25;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .stamp {{
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }}
    .metric {{
      padding: 14px;
      min-height: 86px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .metric-value {{
      margin-top: 8px;
      font-size: 24px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }}
    section {{
      padding: 16px;
      min-width: 0;
    }}
    .wide {{
      grid-column: 1 / -1;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 150px 1fr 62px;
      gap: 10px;
      align-items: center;
      min-height: 28px;
      margin-bottom: 8px;
    }}
    .bar-label {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
    }}
    .bar-track {{
      height: 12px;
      border-radius: 999px;
      background: #edf1f6;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 999px;
    }}
    .bar-value {{
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      text-align: right;
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 9px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: #f9fafb;
    }}
    @media (max-width: 900px) {{
      header {{
        display: block;
      }}
      .stamp {{
        margin-top: 8px;
      }}
      .metrics {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 560px) {{
      main {{
        width: min(100% - 20px, 1180px);
      }}
      .metrics {{
        grid-template-columns: 1fr;
      }}
      .bar-row {{
        grid-template-columns: 105px 1fr 52px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Weather Data Snapshot</h1>
        <p>Local raw history preview before running a larger backfill.</p>
      </div>
      <div class="stamp">
        Generated at: {_escape(generated_at)}<br>
        Latest observation: {_escape(latest_time.strftime("%Y-%m-%d %H:%M"))}
      </div>
    </header>

    <div class="metrics">
      <div class="metric"><div class="metric-label">Raw records</div><div class="metric-value">{row_count:,}</div></div>
      <div class="metric"><div class="metric-label">Cities</div><div class="metric-value">{city_count}</div></div>
      <div class="metric"><div class="metric-label">Date partitions</div><div class="metric-value">{date_count}</div></div>
      <div class="metric"><div class="metric-label">Full city-days</div><div class="metric-value">{full_days}</div></div>
      <div class="metric"><div class="metric-label">Latest rows</div><div class="metric-value">{len(latest_df)}</div></div>
    </div>

    <div class="grid">
      <section>
        <h2>Coverage By Date</h2>
        {_bar_chart(coverage_rows, "label", "value", "var(--blue)", value_display_key="display")}
      </section>
      <section>
        <h2>Hottest Cities On Latest Date</h2>
        {_bar_chart(temp_rows.to_dict("records"), "label", "value", "var(--red)", " C")}
      </section>
      <section>
        <h2>Highest Humidity On Latest Date</h2>
        {_bar_chart(humidity_rows.to_dict("records"), "label", "value", "var(--green)", "%")}
      </section>
      <section>
        <h2>Rain On Latest Date</h2>
        {_bar_chart(rain_rows.to_dict("records"), "label", "value", "var(--amber)", " mm")}
      </section>
      <section class="wide">
        <h2>Latest City Snapshot</h2>
        {_table(latest_table, ["city", "temperature", "humidity", "rain", "weather_condition"], limit=40)}
      </section>
    </div>
  </main>
</body>
</html>
"""


def main() -> None:
    df = load_raw_history()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    html_report = build_report(df)
    OUTPUT_PATH.write_text(html_report, encoding="utf-8")
    LATEST_OUTPUT_PATH.write_text(html_report, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Wrote {LATEST_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
