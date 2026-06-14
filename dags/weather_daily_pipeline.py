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
    description="Daily Open-Meteo weather ETL into PostgreSQL marts.",
    schedule="30 8 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "weather-pipeline",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["weather", "open-meteo", "postgres", "portfolio"],
)
def weather_daily_pipeline():
    @task
    def init_schema() -> None:
        run_project_command(["src/main.py", "--init-db"])

    @task
    def extract_current_weather() -> None:
        run_project_command(["src/main.py", "--extract-only"])

    @task
    def transform_latest_raw() -> None:
        run_project_command(["src/main.py", "--skip-extract"])

    @task
    def validate_cleaned_data() -> None:
        run_project_command(["scripts/check_cleaned_data_quality.py"])

    @task
    def load_postgres_marts() -> None:
        run_project_command(["scripts/load_cleaned_to_postgres.py"])

    schema = init_schema()
    extracted = extract_current_weather()
    transformed = transform_latest_raw()
    validated = validate_cleaned_data()
    loaded = load_postgres_marts()

    schema >> extracted >> transformed >> validated >> loaded


weather_daily_pipeline()
