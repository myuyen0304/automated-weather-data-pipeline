from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pandera.pandas as pa

from config import CITIES


REQUIRED_DASHBOARD_COLUMNS = [
    "city",
    "country",
    "latitude",
    "longitude",
    "observation_time",
    "temperature",
    "humidity",
    "apparent_temperature",
    "pressure_msl",
    "surface_pressure",
    "wind_speed",
    "wind_direction",
    "wind_gusts",
    "precipitation",
    "rain",
    "cloud_cover",
    "weather_code",
    "weather_condition",
    "is_day",
    "inserted_at",
]

# Cột số cần range-check -> phải pre-coerce bằng pd.to_numeric TRƯỚC khi đưa vào
# Pandera. Không dùng Column(coerce=True): nếu một cột có giá trị không parse
# được, coerce=True của Pandera cast cả cột 1 lần (series.astype), thất bại
# toàn cột và khiến Check chạy trên dữ liệu chưa coerce -> lỗi TypeError mù mờ
# thay vì đếm đúng số dòng lỗi. Tự coerce bằng to_numeric(errors="coerce") giữ
# đúng ngữ nghĩa cũ: giá trị không parse được -> NaN -> bắt bởi not_nullable.
NUMERIC_RANGE_COLUMNS = [
    "humidity",
    "temperature",
    "precipitation",
    "rain",
    "wind_speed",
    "wind_gusts",
    "cloud_cover",
]

# 4 biến nông học (FAO-56), tuỳ chọn: chỉ thêm vào schema nếu cột có mặt, và
# nullable=True để NaN được dung thứ (Check bỏ qua NaN mặc định) -> giữ đúng
# hành vi "range chỉ kiểm trên giá trị non-null" của bản pandas cũ.
OPTIONAL_AGRO_COLUMNS = [
    "et0_fao",
    "soil_moisture",
    "soil_temperature",
    "shortwave_radiation",
]

# Grain mapping = (city, crop): một tỉnh có thể nhiều cây. area_share/crop_source
# là cột tuỳ chọn (validate nếu có), không bắt buộc.
REQUIRED_AGRI_MAPPING_COLUMNS = [
    "city",
    "agri_region",
    "crop",
]

# Cột chuỗi có thể "blank" (rỗng/NaN) -> được strip trước khi validate, giữ NaN
# nguyên vẹn (không ép thành chuỗi "nan") để not_nullable của Pandera vẫn bắt
# đúng giá trị null thật.
AGRI_STRIPPABLE_COLUMNS = ["city", "agri_region", "crop", "crop_role", "crop_source"]

OPTIONAL_AGRI_COLUMNS = ["area_share", "crop_source", "crop_role", "is_flagship"]

# Cây trồng hợp lệ = đúng các crop được seed trong dim_crop (sql/06). Mapping trỏ
# tới crop ngoài tập này sẽ bị JOIN rỗng ở mart -> chặn sớm tại DQ gate.
# Cây hợp lệ = cây đã seed trong dim_crop (sql/06). DQ chạy thuần pandas TRƯỚC khi
# nạp DB nên KHÔNG query được dim_crop -> phải hardcode, và set này PHẢI khớp đúng
# seed dim_crop ở sql/06_create_agriculture_schema.sql. Cây không có Kc trích nguồn
# (cao su/tiêu/điều...) cố ý KHÔNG đưa vào -> mapping tham chiếu sẽ bị chặn tại đây,
# ép phải có nguồn trước khi thêm (chống "số magic không nguồn").
KNOWN_CROPS = {
    "coffee", "vegetable", "rice",
    "maize", "soybean", "groundnut", "sugarcane",
    "cassava", "sweet_potato", "banana", "citrus", "tea", "rubber",
}

# crop_role: xếp hạng định tính cây trong tỉnh. Mỗi tỉnh phải có ĐÚNG 1 'primary'
# (cây có diện tích gieo trồng lớn nhất) -> partial unique index chặn >=2, DQ gate ở đây chặn cả 0 và sai giá trị.
VALID_CROP_ROLES = {"primary", "secondary"}

# is_flagship: chuỗi boolean-like đọc từ CSV. "nan"/"none"/"" coi là falsy (cột
# tuỳ chọn, để trống nghĩa là không đánh dấu) -> khớp hành vi cũ.
IS_FLAGSHIP_TRUTHY = {"true", "1", "yes"}
IS_FLAGSHIP_FALSY = {"false", "0", "no", "nan", "none", ""}

# Dung sai khi kiểm tổng area_share của một city (chỉ khi MỌI dòng city đó có share).
AREA_SHARE_SUM_TOLERANCE = 0.01

EXPECTED_CITIES = {str(city["city"]) for city in CITIES}
EXPECTED_CITY_COUNT = len(EXPECTED_CITIES)

TEMPERATURE_MIN_C = -20
TEMPERATURE_MAX_C = 60

# Hourly grain: mỗi (city, ngày) phải đủ 24 giờ thì mart daily (và delivery risk
# suy ra từ nó) mới đúng — thiếu đúng giờ mưa -> total_rain thấp giả -> báo "Low"
# sai. Để strict=24 cho batch daily T-5 (thường đủ); hạ ngưỡng tại đây nếu Archive
# hay skip giờ null hợp lệ gây false-fail.
EXPECTED_HOURS_PER_DAY = 24


@dataclass(frozen=True)
class DataQualityResult:
    row_count: int
    observation_dates: int
    expected_city_count: int


def _format_values(values: set[object], limit: int = 8) -> str:
    ordered = sorted(str(value) for value in values)
    suffix = "" if len(ordered) <= limit else f", ... (+{len(ordered) - limit} more)"
    return ", ".join(ordered[:limit]) + suffix


def _blank_string_mask(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype(str).str.strip().eq("")


def _not_blank_check(error: str) -> pa.Check:
    return pa.Check(lambda s: ~_blank_string_mask(s), error=error, element_wise=False)


# --- Pandera <-> error-message translation -----------------------------------
#
# Mỗi "group" mô tả 1 dòng thông báo lỗi cuối cùng: label hiển thị, cột nguồn,
# tập tên check cần gộp lại (vd not_nullable + range check của cùng 1 cột ->
# 1 dòng duy nhất, giữ đúng ngữ nghĩa "isna() | ngoài range" của bản pandas cũ),
# và style ("count" = đếm số dòng vi phạm, "values" = liệt kê giá trị vi phạm
# qua _format_values, dùng cho các check dạng isin()).
_ErrorGroup = tuple[str, str, frozenset[str], str]


def _pandera_errors_to_messages(
    err: pa.errors.SchemaErrors,
    *,
    unique_label: str,
    groups: list[_ErrorGroup],
) -> list[str]:
    cases = err.failure_cases
    messages: list[str] = []

    uniqueness_idx = set(cases.loc[cases["check"] == "multiple_fields_uniqueness", "index"].dropna())
    if uniqueness_idx:
        messages.append(f"{unique_label}: {len(uniqueness_idx)}")

    for label, column, check_names, style in groups:
        subset = cases[(cases["column"] == column) & cases["check"].isin(check_names)]
        if subset.empty:
            continue
        if style == "values":
            values = {str(v) for v in subset["failure_case"].dropna() if str(v).strip()}
            if values:
                messages.append(f"{label}: {_format_values(values)}")
        else:
            row_count = len(set(subset["index"].dropna()))
            if row_count:
                messages.append(f"{label}: {row_count} row(s)")

    return messages


def _weather_schema(present_optional: list[str]) -> pa.DataFrameSchema:
    schema_columns: dict[str, pa.Column] = {
        column: pa.Column(nullable=False)
        for column in REQUIRED_DASHBOARD_COLUMNS
        if column not in NUMERIC_RANGE_COLUMNS
    }

    schema_columns["humidity"] = pa.Column(
        float, pa.Check.in_range(0, 100, error="humidity_range"), nullable=False
    )
    schema_columns["temperature"] = pa.Column(
        float,
        pa.Check.in_range(TEMPERATURE_MIN_C, TEMPERATURE_MAX_C, error="temperature_range"),
        nullable=False,
    )
    for column in ("precipitation", "rain", "wind_speed", "wind_gusts"):
        schema_columns[column] = pa.Column(
            float, pa.Check.ge(0, error=f"{column}_nonneg"), nullable=False
        )
    # cloud_cover có 2 check độc lập (không âm + trong 0-100), giống bản cũ.
    schema_columns["cloud_cover"] = pa.Column(
        float,
        [
            pa.Check.ge(0, error="cloud_cover_nonneg"),
            pa.Check.in_range(0, 100, error="cloud_cover_range"),
        ],
        nullable=False,
    )

    optional_checks = {
        "et0_fao": pa.Check.ge(0, error="et0_fao_nonneg"),
        "soil_moisture": pa.Check.in_range(0, 1, error="soil_moisture_range"),
        "soil_temperature": pa.Check.in_range(
            TEMPERATURE_MIN_C, TEMPERATURE_MAX_C, error="soil_temperature_range"
        ),
        "shortwave_radiation": pa.Check.ge(0, error="shortwave_radiation_nonneg"),
    }
    for column in present_optional:
        schema_columns[column] = pa.Column(float, optional_checks[column], nullable=True)

    return pa.DataFrameSchema(schema_columns, unique=["city", "observation_time"], strict=False)


def _weather_error_groups(present_optional: list[str]) -> list[_ErrorGroup]:
    groups: list[_ErrorGroup] = []
    for column in REQUIRED_DASHBOARD_COLUMNS:
        if column in NUMERIC_RANGE_COLUMNS:
            continue
        label = "invalid observation_time values" if column == "observation_time" else f"null values in {column}"
        groups.append((label, column, frozenset({"not_nullable"}), "count"))

    groups.append(("humidity outside 0-100", "humidity", frozenset({"not_nullable", "humidity_range"}), "count"))
    groups.append((
        f"temperature outside {TEMPERATURE_MIN_C}..{TEMPERATURE_MAX_C}C",
        "temperature",
        frozenset({"not_nullable", "temperature_range"}),
        "count",
    ))
    for column in ("precipitation", "rain", "wind_speed", "wind_gusts"):
        groups.append((
            f"{column} has negative or non-numeric values",
            column,
            frozenset({"not_nullable", f"{column}_nonneg"}),
            "count",
        ))
    groups.append((
        "cloud_cover has negative or non-numeric values",
        "cloud_cover",
        frozenset({"not_nullable", "cloud_cover_nonneg"}),
        "count",
    ))
    groups.append((
        "cloud_cover outside 0-100",
        "cloud_cover",
        frozenset({"not_nullable", "cloud_cover_range"}),
        "count",
    ))

    optional_labels = {
        "et0_fao": ("et0_fao negative", "et0_fao_nonneg"),
        "soil_moisture": ("soil_moisture outside 0-1 m3/m3", "soil_moisture_range"),
        "soil_temperature": (
            f"soil_temperature outside {TEMPERATURE_MIN_C}..{TEMPERATURE_MAX_C}C",
            "soil_temperature_range",
        ),
        "shortwave_radiation": ("shortwave_radiation negative", "shortwave_radiation_nonneg"),
    }
    for column in present_optional:
        label, check_name = optional_labels[column]
        groups.append((label, column, frozenset({check_name}), "count"))

    return groups


def validate_weather_observations(df: pd.DataFrame) -> DataQualityResult:
    """Validate cleaned weather observations before loading them to PostgreSQL."""
    errors: list[str] = []

    missing_columns = [column for column in REQUIRED_DASHBOARD_COLUMNS if column not in df.columns]
    if missing_columns:
        errors.append(f"missing required columns: {', '.join(missing_columns)}")
        raise ValueError("Data quality check failed: " + "; ".join(errors))

    if df.empty:
        errors.append("batch has no rows")

    working = df.copy()
    working["observation_time"] = pd.to_datetime(working["observation_time"], errors="coerce")
    for column in NUMERIC_RANGE_COLUMNS:
        working[column] = pd.to_numeric(working[column], errors="coerce")

    present_optional = [column for column in OPTIONAL_AGRO_COLUMNS if column in working.columns]
    for column in present_optional:
        working[column] = pd.to_numeric(working[column], errors="coerce")

    schema = _weather_schema(present_optional)
    try:
        schema.validate(working, lazy=True)
    except pa.errors.SchemaErrors as exc:
        errors.extend(
            _pandera_errors_to_messages(
                exc,
                unique_label="duplicate city/observation_time rows",
                groups=_weather_error_groups(present_optional),
            )
        )

    observed_cities = set(working["city"].dropna().astype(str))
    missing_cities = EXPECTED_CITIES - observed_cities
    unknown_cities = observed_cities - EXPECTED_CITIES
    if missing_cities:
        errors.append(f"missing configured cities: {_format_values(missing_cities)}")
    if unknown_cities:
        errors.append(f"unknown cities: {_format_values(unknown_cities)}")

    if not working["observation_time"].isna().all():
        working["observation_date"] = working["observation_time"].dt.date
        coverage = working.groupby("observation_date")["city"].nunique()
        incomplete_dates = coverage[coverage != EXPECTED_CITY_COUNT]
        if not incomplete_dates.empty:
            formatted = ", ".join(
                f"{date}={count}/{EXPECTED_CITY_COUNT}"
                for date, count in incomplete_dates.items()
            )
            errors.append(f"incomplete city coverage by date: {formatted}")

        hours_per_group = working.groupby(["city", "observation_date"])[
            "observation_time"
        ].apply(lambda times: times.dt.hour.nunique())
        incomplete_hours = hours_per_group[hours_per_group < EXPECTED_HOURS_PER_DAY]
        if not incomplete_hours.empty:
            items = [
                f"{city}@{date}={count}/{EXPECTED_HOURS_PER_DAY}h"
                for (city, date), count in incomplete_hours.items()
            ]
            suffix = "" if len(items) <= 8 else f", ... (+{len(items) - 8} more)"
            errors.append(
                "incomplete hourly coverage (expected "
                f"{EXPECTED_HOURS_PER_DAY} hours/city/day): "
                + ", ".join(items[:8])
                + suffix
            )

    if errors:
        raise ValueError("Data quality check failed: " + "; ".join(errors))

    observation_dates = int(working["observation_time"].dt.date.nunique())
    return DataQualityResult(
        row_count=len(working),
        observation_dates=observation_dates,
        expected_city_count=EXPECTED_CITY_COUNT,
    )


def _require_columns(df: pd.DataFrame, required_columns: list[str], label: str) -> None:
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            f"{label} data quality check failed: "
            f"missing required columns: {', '.join(missing_columns)}"
        )


def _valid_role_check() -> pa.Check:
    # Giá trị blank được coi là "hợp lệ" ở check này (đã có blank_crop_role
    # riêng bắt) -> tránh báo trùng 1 dòng blank ở cả 2 message, khớp bản cũ
    # (`~blank_role & ~roles.isin(...)`).
    def _check(series: pd.Series) -> pd.Series:
        return _blank_string_mask(series) | series.isin(VALID_CROP_ROLES)

    return pa.Check(_check, error="invalid_crop_role", element_wise=False)


def _is_flagship_check() -> pa.Check:
    def _check(series: pd.Series) -> pd.Series:
        normalized = series.astype(str).str.strip().str.lower()
        return normalized.isin(IS_FLAGSHIP_TRUTHY | IS_FLAGSHIP_FALSY)

    return pa.Check(_check, error="invalid_is_flagship", element_wise=False)


def _agri_schema(present_optional: list[str]) -> pa.DataFrameSchema:
    schema_columns: dict[str, pa.Column] = {
        "city": pa.Column(nullable=False, checks=_not_blank_check("blank_city")),
        "agri_region": pa.Column(nullable=False, checks=_not_blank_check("blank_agri_region")),
        "crop": pa.Column(
            nullable=False,
            checks=[_not_blank_check("blank_crop"), pa.Check.isin(KNOWN_CROPS, error="unknown_crop")],
        ),
    }

    if "area_share" in present_optional:
        schema_columns["area_share"] = pa.Column(
            float,
            pa.Check.in_range(0, 1, include_min=False, include_max=True, error="area_share_range"),
            nullable=True,
        )
    if "crop_source" in present_optional:
        schema_columns["crop_source"] = pa.Column(
            nullable=False, checks=_not_blank_check("blank_crop_source")
        )
    if "crop_role" in present_optional:
        schema_columns["crop_role"] = pa.Column(
            nullable=False,
            checks=[_not_blank_check("blank_crop_role"), _valid_role_check()],
        )
    if "is_flagship" in present_optional:
        schema_columns["is_flagship"] = pa.Column(nullable=True, checks=_is_flagship_check())

    return pa.DataFrameSchema(schema_columns, unique=["city", "crop"], strict=False)


def _agri_error_groups(present_optional: list[str]) -> list[_ErrorGroup]:
    groups: list[_ErrorGroup] = [
        ("blank values in city", "city", frozenset({"blank_city", "not_nullable"}), "count"),
        (
            "blank values in agri_region",
            "agri_region",
            frozenset({"blank_agri_region", "not_nullable"}),
            "count",
        ),
        ("blank values in crop", "crop", frozenset({"blank_crop", "not_nullable"}), "count"),
        ("unknown crops (not in dim_crop)", "crop", frozenset({"unknown_crop"}), "values"),
    ]

    if "area_share" in present_optional:
        groups.append(("area_share out of range (0,1]", "area_share", frozenset({"area_share_range"}), "count"))
    if "crop_source" in present_optional:
        groups.append((
            "blank crop_source (su hien dien cay phai co can cu)",
            "crop_source",
            frozenset({"blank_crop_source", "not_nullable"}),
            "count",
        ))
    if "crop_role" in present_optional:
        groups.append(("blank crop_role", "crop_role", frozenset({"blank_crop_role", "not_nullable"}), "count"))
        groups.append((
            "invalid crop_role (phai la primary/secondary)",
            "crop_role",
            frozenset({"invalid_crop_role"}),
            "values",
        ))
    if "is_flagship" in present_optional:
        groups.append((
            "invalid is_flagship (phai boolean true/false)",
            "is_flagship",
            frozenset({"invalid_is_flagship"}),
            "values",
        ))

    return groups


def validate_agri_region_mapping(df: pd.DataFrame) -> int:
    """Validate city -> agriculture region/crop mapping before loading it."""
    _require_columns(df, REQUIRED_AGRI_MAPPING_COLUMNS, "Agriculture mapping")
    errors: list[str] = []

    if df.empty:
        errors.append("mapping batch has no rows")

    working = df.copy()
    for column in AGRI_STRIPPABLE_COLUMNS:
        if column in working.columns:
            working[column] = working[column].where(
                working[column].isna(), working[column].astype(str).str.strip()
            )

    present_optional = [column for column in OPTIONAL_AGRI_COLUMNS if column in working.columns]
    if "area_share" in present_optional:
        working["area_share"] = pd.to_numeric(working["area_share"], errors="coerce")

    # Grain (city, crop): cho phép nhiều cây/tỉnh, nhưng KHÔNG trùng đúng cặp.
    schema = _agri_schema(present_optional)
    try:
        schema.validate(working, lazy=True)
    except pa.errors.SchemaErrors as exc:
        errors.extend(
            _pandera_errors_to_messages(
                exc,
                unique_label="duplicate (city, crop) mapping rows",
                groups=_agri_error_groups(present_optional),
            )
        )

    observed_cities = set(working["city"].dropna().astype(str).str.strip())
    missing_cities = EXPECTED_CITIES - observed_cities
    unknown_cities = observed_cities - EXPECTED_CITIES
    if missing_cities:
        errors.append(f"missing configured cities: {_format_values(missing_cities)}")
    if unknown_cities:
        errors.append(f"unknown cities: {_format_values(unknown_cities)}")

    # area_share là tuỳ chọn + NULLABLE (chưa có nguồn tỷ trọng theo 34 tỉnh mới).
    # Range (0,1] đã kiểm bằng Pandera ở trên; tổng theo city chỉ kiểm khi MỌI
    # dòng city đó có share (cấu hình đầy đủ) -> phải ~ 1. KHÔNG tự chia đều.
    if "area_share" in present_optional:
        share_df = pd.DataFrame({
            "city": working["city"].astype(str).str.strip(),
            "share": working["area_share"],
            "present": working["area_share"].notna(),
        })
        for city, group in share_df.groupby("city"):
            if group["present"].all():
                total = float(group["share"].sum())
                if abs(total - 1.0) > AREA_SHARE_SUM_TOLERANCE:
                    errors.append(
                        f"area_share for {city} sums to {total:.3f}, expected ~1.0"
                    )

    # crop_role (nếu có cột): Pandera đã bắt blank/giá trị lạ ở trên; ở đây chỉ
    # còn invariant cross-row "mỗi tỉnh đúng 1 primary" (partial unique index
    # DB chỉ chặn >=2, phải chặn thêm 0 primary ở DQ gate).
    if "crop_role" in present_optional:
        role_df = pd.DataFrame({
            "city": working["city"].astype(str).str.strip(),
            "is_primary": working["crop_role"].astype(str).str.strip().eq("primary"),
        })
        primary_counts = role_df.groupby("city")["is_primary"].sum()
        wrong_primary = primary_counts[primary_counts != 1]
        if not wrong_primary.empty:
            formatted = ", ".join(
                f"{city}={int(count)}" for city, count in wrong_primary.items()
            )
            errors.append(
                f"each city needs exactly 1 primary crop, got: {formatted}"
            )

    # is_flagship (nếu có cột): Pandera đã bắt giá trị không phải boolean-like;
    # ở đây chỉ còn invariant cross-row "mỗi tỉnh TỐI ĐA 1 flagship".
    if "is_flagship" in present_optional:
        normalized = working["is_flagship"].astype(str).str.strip().str.lower()
        flag_df = pd.DataFrame({
            "city": working["city"].astype(str).str.strip(),
            "is_flag": normalized.isin(IS_FLAGSHIP_TRUTHY),
        })
        flag_counts = flag_df.groupby("city")["is_flag"].sum()
        too_many_flags = flag_counts[flag_counts > 1]
        if not too_many_flags.empty:
            formatted = ", ".join(
                f"{city}={int(count)}" for city, count in too_many_flags.items()
            )
            errors.append(
                f"each city allows at most 1 flagship crop, got: {formatted}"
            )

    if errors:
        raise ValueError("Agriculture mapping data quality check failed: " + "; ".join(errors))

    return len(working)
