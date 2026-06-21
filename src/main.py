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
    parser.add_argument(
        "--load-agriculture",
        action="store_true",
        help=(
            "Also load agriculture mapping/rules and refresh the rule-based "
            "weather advisory mart. If --load is set, weather loads first."
        ),
    )
    parser.add_argument(
        "--date",
        help="Transform raw JSON from one partition, formatted as YYYY-MM-DD.",
    )
    parser.add_argument(
        "--all-raw",
        action="store_true",
        help="Reprocess all raw JSON history instead of the current batch/latest date.",
    )
    args = parser.parse_args()

    if args.extract_only and args.load:
        parser.error("--extract-only cannot be combined with --load because load needs transformed data.")

    if args.extract_only and args.load_agriculture:
        parser.error("--extract-only cannot be combined with --load-agriculture.")

    # --init-db chạy độc lập: chỉ tạo schema rồi thoát.
    if args.init_db:
        # Import muộn để extract/transform vẫn chạy được khi chưa cài DB driver.
        from load_postgres import init_database

        init_database()
        return

    extracted_paths = []
    if not args.skip_extract:
        extracted_paths = extract_all_cities()

    if not args.extract_only:
        local_extracted_paths = [path for path in extracted_paths if path.exists()]
        if local_extracted_paths and not args.date and not args.all_raw:
            transform_raw_files(raw_files=local_extracted_paths)
        else:
            transform_raw_files(run_date=args.date, include_history=args.all_raw)

    if args.load:
        from load_postgres import load_to_postgres

        load_to_postgres()

    if args.load_agriculture:
        from load_agriculture import load_agriculture_to_postgres

        load_agriculture_to_postgres()


if __name__ == "__main__":
    main()
