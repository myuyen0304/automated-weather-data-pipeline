# Automated Weather Data Pipeline

## 1. Project Overview

**Automated Weather Data Pipeline** is a beginner-friendly Data Engineering project that automatically collects daily weather observations from the **Open-Meteo Forecast API**, stores raw JSON responses, transforms and cleans the data using Python, loads the result into PostgreSQL, applies SQL-based data modelling with fact and dimension tables, and builds analytical marts for Power BI dashboards.

This project uses Open-Meteo as the only weather data source. The selected endpoint is:

```text
https://api.open-meteo.com/v1/forecast
```

Open-Meteo is a good fit for this portfolio project because it returns weather data as JSON, supports current weather variables through latitude and longitude, and does not require an API key for the basic forecast/current-weather workflow used here.

The pipeline is automated with Windows Task Scheduler (via `run_pipeline.bat`) — or Linux Cron as an alternative — so weather data can be collected and updated every day without manual execution.

---

## 2. Project Objectives

The main objectives of this project are:

- Automatically collect daily weather data from Open-Meteo.
- Query weather data by city coordinates.
- Store the original Open-Meteo API response as raw JSON files.
- Clean, normalize, and transform weather data using Python.
- Load processed data into PostgreSQL.
- Design a simple analytical data model using fact and dimension tables.
- Create SQL marts for daily and weekly weather analysis.
- Visualize weather trends using Power BI.
- Automate the pipeline using Windows Task Scheduler (or Linux Cron).

---

## 3. Pipeline Architecture

```text
Open-Meteo Forecast API
    |
Python Ingestion
    |
Raw JSON Storage
    |
Data Cleaning & Transformation
    |
PostgreSQL Staging Table
    |
SQL Data Modelling
    |
Fact & Dimension Tables
    |
SQL Mart Tables
    |
Power BI Dashboard
    |
Windows Task Scheduler (run_pipeline.bat)
```

---

## 4. Tech Stack

| Layer | Technology |
|---|---|
| Data Source | Open-Meteo Forecast API |
| API Endpoint | `https://api.open-meteo.com/v1/forecast` |
| Programming Language | Python |
| API Ingestion | requests |
| Data Processing | pandas |
| Raw Storage | Local JSON files |
| Database | PostgreSQL |
| Data Modelling | SQL |
| Analytics Layer | SQL views / mart tables |
| Local Database | Docker Compose (postgres:16) |
| Dashboard | Power BI |
| Automation | Windows Task Scheduler (`run_pipeline.bat`); Linux Cron as an alternative |
| Environment Management | python-dotenv, virtual environment (`.venv` / `venv` / `uv`) |

---

## 5. Data Source

The project collects weather data from the Open-Meteo Forecast API.

Open-Meteo requires geographical coordinates, so the pipeline keeps a configured list of cities with latitude and longitude.

The pipeline collects weather for **34 Vietnamese provinces/cities**, configured in `data/cities.csv` and loaded at runtime by `load_cities()` in `src/config.py`. To add or remove a location, edit that CSV — no code change is needed.

First rows of `data/cities.csv`:

| City | Country | Latitude | Longitude |
|---|---|---:|---:|
| Hanoi | Vietnam | 21.0245 | 105.8412 |
| Hai Phong | Vietnam | 20.8449 | 106.6881 |
| Hue | Vietnam | 16.4619 | 107.5955 |
| Da Nang | Vietnam | 16.0678 | 108.2208 |
| Ho Chi Minh City | Vietnam | 10.8230 | 106.6296 |
| Can Tho | Vietnam | 10.0371 | 105.7883 |
| … | … | … | … |

Example request for Ho Chi Minh City:

```text
https://api.open-meteo.com/v1/forecast?latitude=10.823&longitude=106.6296&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m,is_day&timezone=Asia/Ho_Chi_Minh&forecast_days=1
```

The pipeline focuses on the `current` weather block. Useful Open-Meteo variables include:

| Open-Meteo field | Meaning |
|---|---|
| `current.time` | Observation timestamp |
| `current.temperature_2m` | Temperature at 2 meters |
| `current.relative_humidity_2m` | Relative humidity at 2 meters |
| `current.apparent_temperature` | Apparent temperature |
| `current.precipitation` | Total precipitation |
| `current.rain` | Rain amount |
| `current.weather_code` | Open-Meteo weather condition code |
| `current.cloud_cover` | Cloud cover percentage |
| `current.pressure_msl` | Mean sea level pressure |
| `current.surface_pressure` | Surface pressure |
| `current.wind_speed_10m` | Wind speed at 10 meters |
| `current.wind_direction_10m` | Wind direction at 10 meters |
| `current.wind_gusts_10m` | Wind gusts at 10 meters |
| `current.is_day` | Day or night flag |

---

## 6. Project Folder Structure

```text
automated-weather-data-pipeline/
|
├── data/
│   ├── cities.csv                       # 34 provinces/cities (CSV-driven config)
│   ├── raw/
│   │   └── open-meteo/
│   │       └── date=YYYY-MM-DD/<city>.json
│   └── cleaned/
│       └── weather_observations.csv     # transformed output
|
├── sql/
│   ├── 01_create_staging_table.sql
│   ├── 02_create_dimensions.sql
│   ├── 03_create_fact_table.sql
│   ├── 04_load_star_schema.sql          # runs every batch (staging -> star schema)
│   └── 05_create_marts.sql
|
├── src/
│   ├── config.py
│   ├── extract_weather.py
│   ├── transform_weather.py
│   ├── load_postgres.py
│   └── main.py
|
├── scripts/
│   └── build_cities_csv.py
|
├── docs/                                # extra guides (Vietnamese)
├── images/                             # architecture diagram
|
├── docker-compose.yml                  # local PostgreSQL (postgres:16)
├── run_pipeline.bat                    # Windows Task Scheduler entry point
├── .env.example
├── requirements.txt
└── README.md
```

> A Power BI file (`dashboard/weather_dashboard.pbix`) is optional and not committed to the repo.

---

## 7. Pipeline Steps

### 7.1 Extract

The extraction step calls Open-Meteo using Python and saves the raw JSON response into the local raw data folder.

Raw files are stored by date and city.

Example raw storage structure:

```text
data/
└── raw/
    └── open-meteo/
        └── date=2026-06-10/
            ├── ho_chi_minh_city.json
            ├── hanoi.json
            └── da_nang.json
```

The purpose of storing raw JSON files is to preserve the original API response. This allows the pipeline to reprocess historical data if the transformation logic changes later.

### 7.2 Transform

The transformation step reads raw Open-Meteo JSON files and converts them into structured tabular data.

Main transformation tasks:

- Extract required fields from the `current` block.
- Add city and country from the local city configuration.
- Standardize column names for analytics.
- Convert `current.time` into a proper timestamp.
- Convert `weather_code` into a readable `weather_condition`.
- Handle missing rain and precipitation values.
- Normalize numeric fields.
- Add an `inserted_at` timestamp.
- Prepare the dataset for loading into PostgreSQL.

Output columns may include:

| Column | Description |
|---|---|
| city | City name |
| country | Country name |
| latitude | Location latitude |
| longitude | Location longitude |
| observation_time | Time of weather observation |
| temperature | Temperature value |
| humidity | Humidity percentage |
| apparent_temperature | Apparent temperature |
| pressure_msl | Mean sea level pressure |
| surface_pressure | Surface pressure |
| wind_speed | Wind speed |
| wind_direction | Wind direction |
| wind_gusts | Wind gusts |
| precipitation | Total precipitation |
| rain | Rain amount |
| cloud_cover | Cloud coverage percentage |
| weather_code | Open-Meteo weather code |
| weather_condition | Readable weather condition mapped from `weather_code` |
| is_day | Day or night flag |
| inserted_at | Time when the pipeline inserted the data |

### 7.3 Load

The load step inserts cleaned weather data into a PostgreSQL staging table.

The staging table keeps cleaned but not yet modelled data. It acts as the intermediate layer between raw files and the analytical data model.

Example staging table:

```sql
CREATE TABLE stg_weather_observations (
    city VARCHAR(100),
    country VARCHAR(100),
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6),
    observation_time TIMESTAMP,
    temperature NUMERIC(5,2),
    humidity NUMERIC(5,2),
    apparent_temperature NUMERIC(5,2),
    pressure_msl NUMERIC(7,2),
    surface_pressure NUMERIC(7,2),
    wind_speed NUMERIC(6,2),
    wind_direction NUMERIC(6,2),
    wind_gusts NUMERIC(6,2),
    precipitation NUMERIC(6,2),
    rain NUMERIC(6,2),
    cloud_cover INT,
    weather_code INT,
    weather_condition VARCHAR(100),
    is_day BOOLEAN,
    inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. Data Modelling

This project applies a simple star schema for analytical querying.

The model contains:

- `dim_location`
- `dim_date`
- `fact_weather_observation`

```text
dim_location
      |
      |
fact_weather_observation ---- dim_date
```

### 8.1 Dimension Table: dim_location

The `dim_location` table stores information about each city or location.

```sql
CREATE TABLE dim_location (
    location_id SERIAL PRIMARY KEY,
    city VARCHAR(100),
    country VARCHAR(100),
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6)
);
```

### 8.2 Dimension Table: dim_date

The `dim_date` table stores date attributes for time-based analysis.

```sql
CREATE TABLE dim_date (
    date_id INT PRIMARY KEY,
    full_date DATE,
    day INT,
    month INT,
    quarter INT,
    year INT,
    day_of_week VARCHAR(20),
    is_weekend BOOLEAN
);
```

### 8.3 Fact Table: fact_weather_observation

The `fact_weather_observation` table stores measurable weather values.

```sql
CREATE TABLE fact_weather_observation (
    observation_id BIGSERIAL PRIMARY KEY,
    location_id INT REFERENCES dim_location(location_id),
    date_id INT REFERENCES dim_date(date_id),
    observation_time TIMESTAMP,
    temperature NUMERIC(5,2),
    humidity NUMERIC(5,2),
    apparent_temperature NUMERIC(5,2),
    pressure_msl NUMERIC(7,2),
    surface_pressure NUMERIC(7,2),
    wind_speed NUMERIC(6,2),
    wind_direction NUMERIC(6,2),
    wind_gusts NUMERIC(6,2),
    precipitation NUMERIC(6,2),
    rain NUMERIC(6,2),
    cloud_cover INT,
    weather_code INT,
    weather_condition VARCHAR(100),
    is_day BOOLEAN,
    inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. Analytics Mart

The analytics mart is created for reporting and dashboarding.

Example mart:

```sql
CREATE VIEW mart_daily_weather_summary AS
SELECT
    l.city,
    d.full_date,
    AVG(f.temperature) AS avg_temperature,
    MAX(f.temperature) AS max_temperature,
    MIN(f.temperature) AS min_temperature,
    AVG(f.humidity) AS avg_humidity,
    AVG(f.apparent_temperature) AS avg_apparent_temperature,
    AVG(f.pressure_msl) AS avg_pressure_msl,
    AVG(f.surface_pressure) AS avg_surface_pressure,
    AVG(f.wind_speed) AS avg_wind_speed,
    MAX(f.wind_gusts) AS max_wind_gusts,
    SUM(f.precipitation) AS total_precipitation,
    SUM(f.rain) AS total_rain,
    AVG(f.cloud_cover) AS avg_cloud_cover
FROM fact_weather_observation f
JOIN dim_location l
    ON f.location_id = l.location_id
JOIN dim_date d
    ON f.date_id = d.date_id
GROUP BY
    l.city,
    d.full_date;
```

This mart can be used to answer questions such as:

- What is the average daily temperature by city?
- Which city had the highest temperature?
- How much rain was recorded this week?
- How does humidity change over time?
- Which city has the highest average wind speed?
- How does pressure change by city and date?

---

## 10. Dashboard

Power BI is used to visualize the weather data.

Recommended dashboard charts:

| Chart | Purpose |
|---|---|
| Average Temperature by City | Compare temperature across cities |
| Temperature Trend by Date | Analyze temperature changes over time |
| Total Rain by Week | Track weekly rainfall |
| Humidity by City | Compare humidity levels |
| Wind Speed Trend | Monitor wind speed changes |
| Pressure Trend | Monitor pressure changes |
| Weather Condition Distribution | Analyze weather condition frequency |
| Cloud Cover by City | Compare cloud coverage |

Dashboard data source:

```text
PostgreSQL -> mart_daily_weather_summary -> Power BI
```

---

## 11. Automation

The pipeline is automated on Windows with **Task Scheduler** running `run_pipeline.bat`,
which calls `python src\main.py --load` and writes output to `logs\pipeline.log`. The wrapper
auto-detects the interpreter in this order: `.venv` → `venv` → `uv run`.

Create a daily 07:00 task from the project root:

```bat
schtasks /Create /SC DAILY /ST 07:00 /TN WeatherPipeline /TR "\"%CD%\run_pipeline.bat\""
```

On Linux you can use Cron instead:

```bash
0 7 * * * /usr/bin/python3 /home/user/automated-weather-data-pipeline/src/main.py --load
```

### main.py CLI flags

`src/main.py` orchestrates the pipeline through `argparse`. By default it extracts and transforms;
loading into PostgreSQL only happens with `--load`.

| Flag | Effect |
|---|---|
| (none) | Extract from Open-Meteo, then transform the current batch to cleaned CSV |
| `--load` | Also load cleaned data into PostgreSQL and rebuild the star schema |
| `--init-db` | Create the schema (staging, dims, fact, marts), then exit |
| `--skip-extract` | Transform existing raw JSON without calling the API |
| `--extract-only` | Only fetch raw JSON, skip transform (cannot combine with `--load`) |
| `--date YYYY-MM-DD` | Transform raw JSON from one date partition |
| `--all-raw` | Reprocess the entire raw history instead of the latest batch |

---

## 12. Environment Variables

Open-Meteo does not require an API key for this workflow, so the `.env` file should focus on the API base URL, timezone, and PostgreSQL credentials.

Example `.env.example`:

```text
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1/forecast
WEATHER_TIMEZONE=Asia/Ho_Chi_Minh

DB_HOST=localhost
DB_PORT=5432
DB_NAME=weather_db
DB_USER=postgres
DB_PASSWORD=postgres
```

The `.env` file should not be committed to GitHub.

---

## 13. Requirements

Example `requirements.txt`:

```text
requests
pandas
psycopg2-binary
SQLAlchemy
python-dotenv
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 14. How to Run

### Step 1: Clone the repository

```bash
git clone https://github.com/your-username/automated-weather-data-pipeline.git
cd automated-weather-data-pipeline
```

### Step 2: Create virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

For Windows:

```bash
venv\Scripts\activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure environment variables

Create a `.env` file based on `.env.example`.

```bash
cp .env.example .env
```

Then update the PostgreSQL credentials if needed.

### Step 5: Configure cities

Cities are defined in `data/cities.csv` (CSV-driven — no code change needed). Each row is
`city,country,latitude,longitude`:

```text
city,country,latitude,longitude
Hanoi,Vietnam,21.0245,105.8412
Hai Phong,Vietnam,20.8449,106.6881
Ho Chi Minh City,Vietnam,10.823,106.6296
...
```

Add or remove rows to change which locations the pipeline collects.

### Step 6: Start PostgreSQL

The repo ships a `docker-compose.yml` with PostgreSQL 16. Start it with:

```bash
docker compose up -d
```

The `POSTGRES_*` values match `.env` (`DB_NAME` / `DB_USER` / `DB_PASSWORD`).

### Step 7: Create database tables

Create the schema once (staging, dimensions, fact, marts):

```bash
python src/main.py --init-db
```

This runs `sql/01`, `02`, `03`, and `05`. Note: `sql/04_load_star_schema.sql` is **not** run here —
it loads data from staging into the star schema and runs on every `--load` batch instead.

### Step 8: Run the pipeline manually

Full run (extract → transform → load into PostgreSQL):

```bash
python src/main.py --load
```

Useful variants:

```bash
python src/main.py                       # extract + transform only (no DB)
python src/main.py --skip-extract --load # re-transform existing raw, then load
python src/main.py --date 2026-06-10     # transform one date partition
python src/main.py --all-raw             # reprocess the full raw history
```

### Step 9: Schedule daily runs

On Windows, register `run_pipeline.bat` with Task Scheduler:

```bat
schtasks /Create /SC DAILY /ST 07:00 /TN WeatherPipeline /TR "\"%CD%\run_pipeline.bat\""
```

On Linux, use Cron instead:

```bash
0 7 * * * /usr/bin/python3 /home/user/automated-weather-data-pipeline/src/main.py --load
```

---

## 15. Expected Output

After the pipeline runs successfully, the system should produce:

- Raw Open-Meteo JSON files stored by date and city.
- Cleaned weather data loaded into PostgreSQL.
- Fact and dimension tables for analytical querying.
- SQL mart table or view for dashboard reporting.
- Power BI dashboard showing weather trends and metrics.
- Automated daily execution through Windows Task Scheduler (or Linux Cron).

---

## 16. Future Improvements

Possible improvements for future versions:

- Replace Cron job with Apache Airflow.
- Store raw JSON and cleaned data in Amazon S3 or MinIO.
- Save cleaned data as Parquet files.
- Use dbt for data modelling and testing.
- Add data quality checks.
- Add Open-Meteo historical weather backfill.
- Deploy PostgreSQL on AWS RDS.
- Build a Docker-based development environment.
- Add CI/CD using GitHub Actions.
- Add forecasting models for temperature or rainfall prediction.
- Track machine learning experiments with MLflow.

---

## 17. Skills Demonstrated

This project demonstrates the following Data Engineering skills:

- Open-Meteo API ingestion
- JSON processing
- ETL pipeline development
- Raw data storage
- Python data transformation
- PostgreSQL database loading
- SQL data modelling
- Star schema design
- Fact and dimension table design
- SQL analytics
- Dashboard design
- Pipeline automation
- Environment variable management
- Portfolio project documentation
