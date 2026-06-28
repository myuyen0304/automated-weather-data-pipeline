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

# dbt nằm trong VENV CÔ LẬP của image (xem Dockerfile.airflow) -> gọi thẳng binary,
# KHÔNG qua run_project_command (hàm đó hardcode sys.executable = python của Airflow,
# không có dbt). Project dbt = weather_dbt/ dưới project root đã mount vào container.
DBT_BIN = os.getenv("DBT_BIN", "/home/airflow/dbt-venv/bin/dbt")
DBT_PROJECT_DIR = PROJECT_ROOT / "weather_dbt"


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


def run_dbt_command(args: list[str]) -> None:
    """Chạy dbt từ venv cô lập của image (KHÔNG dùng python của Airflow).

    dbt đọc env DB_* (đã set host.docker.internal trong docker-compose.airflow.yml)
    qua env_var() trong profiles.yml. Ép target/ + logs/ ra /tmp vì project mount
    từ host -> uid airflow (50000) có thể không ghi được dưới weather_dbt/.
    """
    env = os.environ.copy()
    env["DBT_TARGET_PATH"] = "/tmp/dbt_target"
    env["DBT_LOG_PATH"] = "/tmp/dbt_logs"

    command = [
        DBT_BIN,
        *args,
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROJECT_DIR),
    ]
    print(f"Running dbt: {' '.join(command)}")
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
        # --skip-extract: agri chỉ nạp mapping city->region/crop, KHÔNG cần fetch forecast.
        # Thiếu nó thì main.py extract lại forecast hôm nay cho cả 34 city qua API và ghi đè
        # weather_observations.csv — side effect thừa, không đụng tới fact.
        run_project_command(["src/main.py", "--skip-extract", "--load-agriculture"])

    @task
    def dbt_build() -> None:
        # Dựng tầng mart bằng dbt (thay sql/05 + sql/08 trong init cũ). `dbt build`
        # chạy models + tests trong MỘT lượt, đúng thứ tự phụ thuộc tự suy từ ref().
        # ĐẶT CUỐI: mart_irrigation_need cần dim_agri_region đã nạp (load_agriculture/07)
        # mới ra dòng; fact cũng phải có data (load_postgres_marts) trước đó.
        run_dbt_command(["build"])

    schema = init_schema()
    target_date = resolve_archive_target_date()
    backfilled = backfill_archive_day(target_date)
    transformed = transform_archive_day(target_date)
    validated = validate_cleaned_data()
    loaded = load_postgres_marts()
    loaded_agri = load_agriculture()
    dbt_built = dbt_build()

    schema >> target_date >> backfilled >> transformed >> validated >> loaded >> loaded_agri >> dbt_built


weather_daily_pipeline()
