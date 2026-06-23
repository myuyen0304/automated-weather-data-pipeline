from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pendulum

try:
    from airflow.sdk import dag, task
except ImportError:  # Airflow 2 fallback for local linting or older images.
    from airflow.decorators import dag, task


PROJECT_ROOT = Path(os.getenv("WEATHER_PROJECT_ROOT", "/opt/airflow/project"))
# Độ trễ ERA5: đọc qua env vì KHÔNG import config được lúc Airflow parse DAG (src chỉ
# vào PYTHONPATH ở subprocess). Phải khớp config.ERA5_DELAY_DAYS — override chung qua
# docker-compose.airflow.yml (ERA5_DELAY_DAYS), default 5 nếu env trống.
ARCHIVE_DELAY_DAYS = int(os.getenv("ERA5_DELAY_DAYS", "5"))


def run_project_command(args: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    command = [sys.executable, *args]
    print(f"Running from {PROJECT_ROOT}: {' '.join(command)}")
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    result.check_returncode()


@dag(
    dag_id="weather_daily_pipeline",
    description="Daily Open-Meteo Archive catch-up into PostgreSQL marts.",
    schedule="30 8 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "weather-pipeline",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["weather", "archive", "open-meteo", "postgres", "portfolio"],
)
def weather_daily_pipeline():
    @task
    def init_schema() -> None:
        run_project_command(["src/main.py", "--init-db"])

    @task
    def resolve_archive_target_date() -> str:
        return (
            pendulum.now("Asia/Ho_Chi_Minh")
            .subtract(days=ARCHIVE_DELAY_DAYS)
            .to_date_string()
        )

    @task
    def backfill_archive_day(target_date: str) -> None:
        run_project_command(
            [
                "src/backfill_weather.py",
                "--start-date",
                target_date,
                "--end-date",
                target_date,
                "--sleep",
                "0.2",
            ]
        )

    @task
    def transform_archive_day(target_date: str) -> None:
        run_project_command(["src/main.py", "--skip-extract", "--date", target_date])

    @task
    def validate_cleaned_data() -> None:
        run_project_command(["scripts/check_cleaned_data_quality.py"])

    @task
    def load_postgres_marts() -> None:
        run_project_command(["scripts/load_cleaned_to_postgres.py"])

    @task
    def load_agriculture() -> None:
        # Refresh dim_agri_region từ mapping CSV (idempotent TRUNCATE+INSERT).
        # Đặt sau load weather để chuỗi đọc tự nhiên; mart_irrigation_need là VIEW
        # nên thứ tự dim/fact không đổi kết quả.
        run_project_command(["src/main.py", "--load-agriculture"])

    schema = init_schema()
    target_date = resolve_archive_target_date()
    backfilled = backfill_archive_day(target_date)
    transformed = transform_archive_day(target_date)
    validated = validate_cleaned_data()
    loaded = load_postgres_marts()
    loaded_agri = load_agriculture()

    schema >> target_date >> backfilled >> transformed >> validated >> loaded >> loaded_agri


weather_daily_pipeline()
