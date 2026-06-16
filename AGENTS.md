# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python weather ETL pipeline using the Open-Meteo API, local files, PostgreSQL, and optional Airflow orchestration.

- `src/`: pipeline code. `main.py` is the CLI entry point; extraction, transformation, loading, quality checks, and backfill logic are split into focused modules.
- `tests/`: pytest tests for CLI behavior, transformations, and data quality.
- `data/`: local inputs and generated weather data. `data/cities.csv` controls the configured locations.
- `sql/`: PostgreSQL schema, staging, star schema, and mart scripts.
- `dags/`: Airflow DAG definitions for daily ETL and archive backfill.
- `scripts/`: operational helpers for scheduled runs, reports, data quality checks, and city CSV generation.
- `images/`, `reports/`, and `logs/`: generated visual, report, and runtime artifacts.

## Build, Test, and Development Commands

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the pipeline without database loading:

```powershell
python src/main.py
```

Run extraction, transformation, and PostgreSQL loading:

```powershell
docker compose up -d
python src/main.py --init-db
python src/main.py --load
```

Useful variants:

```powershell
python src/main.py --skip-extract --load
python src/main.py --date 2026-06-10
python src/main.py --all-raw
python src/backfill_weather.py --start-date 2026-05-10 --end-date 2026-06-08
```

Start Airflow locally:

```powershell
docker compose -f docker-compose.airflow.yml up airflow-init
docker compose -f docker-compose.airflow.yml up -d
```

## Coding Style & Naming Conventions

Use Python 3 with four-space indentation and small modules aligned to pipeline stages. Prefer `snake_case` for files, functions, variables, CLI flags, and test names. Keep configuration in `.env` and `src/config.py`; do not hard-code credentials, paths, or API endpoints in transformation logic.

## Testing Guidelines

Tests use `pytest`; configuration lives in `pytest.ini`, with `src` on `pythonpath` and `tests/` as the test root. Run:

```powershell
pytest
```

Name files `test_<behavior>.py` and functions `test_<expected_outcome>()`. Add focused tests for transformation rules, data quality checks, CLI flags, and failure paths when modifying pipeline behavior.

## Commit & Pull Request Guidelines

The Git history uses short conventional-style messages such as `feat(orchestration): add Airflow DAGs`, `fix(scheduler): stabilize postgres readiness check`, and `test(pipeline): add data quality checks and CI`. Follow this pattern: `type(scope): imperative summary`.

Pull requests should include a brief purpose, changed pipeline stages, commands run, and any generated artifacts affected. Mention environment or scheduler changes, and include screenshots only for Power BI/report/UI-facing updates.

## Security & Configuration Tips

Keep `.env` local and update `.env.example` when adding required variables. Do not commit raw secrets, local virtual environments, cache folders, database volumes, or large generated data unless explicitly intended.
