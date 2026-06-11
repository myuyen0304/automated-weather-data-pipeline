from __future__ import annotations

import argparse

from extract_weather import extract_all_cities
from transform_weather import transform_raw_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the weather data pipeline.")
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Transform existing raw JSON without calling the Open-Meteo API.",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only extract raw JSON and skip transformation.",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Create PostgreSQL schema (staging, dims, fact, marts) then exit.",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Also load cleaned data into PostgreSQL (requires a running DB).",
    )
    args = parser.parse_args()

    # --init-db chạy độc lập: chỉ tạo schema rồi thoát.
    if args.init_db:
        # Import muộn để extract/transform vẫn chạy được khi chưa cài DB driver.
        from load_postgres import init_database

        init_database()
        return

    if not args.skip_extract:
        extract_all_cities()

    if not args.extract_only:
        transform_raw_files()

    if args.load:
        from load_postgres import load_to_postgres

        load_to_postgres()


if __name__ == "__main__":
    main()
