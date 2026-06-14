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
    dag_id="weather_archive_backfill",
    description="Manual Open-Meteo Archive backfill, then reload all raw history.",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    params={
        "start_date": "2026-06-10",
        "end_date": "2026-06-10",
        "sleep": "0.2",
    },
    default_args={
        "owner": "weather-pipeline",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["weather", "backfill", "open-meteo", "portfolio"],
)
def weather_archive_backfill():
    @task
    def backfill_raw_archive(start_date: str, end_date: str, sleep: str) -> None:
        run_project_command(
            [
                "src/backfill_weather.py",
                "--start-date",
                start_date,
                "--end-date",
                end_date,
                "--sleep",
                sleep,
            ]
        )

    @task
    def reload_all_raw_history() -> None:
        run_project_command(["src/main.py", "--skip-extract", "--all-raw", "--load"])

    backfilled = backfill_raw_archive(
        "{{ params.start_date }}",
        "{{ params.end_date }}",
        "{{ params.sleep }}",
    )
    reloaded = reload_all_raw_history()

    backfilled >> reloaded


weather_archive_backfill()
