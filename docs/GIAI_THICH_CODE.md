# Giải thích chi tiết code & lý do thiết kế

Tài liệu này giải thích **code hiện tại đang làm gì** và **vì sao thiết kế như vậy** trong project `automated-weather-data-pipeline`.

Trạng thái mới nhất của codebase:

- Data source: Open-Meteo Forecast API.
- Danh sách địa điểm: 34 tỉnh/thành Việt Nam từ `data/cities.csv`.
- Raw Zone: `data/raw/open-meteo/date=YYYY-MM-DD/*.json`.
- Cleaned output: `data/cleaned/weather_observations.csv`.
- Database: PostgreSQL chạy bằng Docker Compose.
- Data model: `dim_location`, `dim_date`, `fact_weather_observation`.
- Mart: `mart_daily_weather_summary`, `mart_weekly_weather_summary`.
- Automation wrapper: `run_pipeline.bat` cho Windows Task Scheduler.

Kiến trúc tổng thể:

```text
Open-Meteo API
    |
    | requests + retry
    v
Raw Zone
data/raw/open-meteo/date=YYYY-MM-DD/<city_slug>.json
    |
    | pandas transform
    v
Cleaned CSV
data/cleaned/weather_observations.csv
    |
    | schema validation + pandas.to_sql
    v
PostgreSQL staging
stg_weather_observations
    |
    | SQL load script
    v
Star schema
dim_location + dim_date + fact_weather_observation
    |
    | SQL views
    v
Analytics marts
mart_daily_weather_summary + mart_weekly_weather_summary
```

---

## 0. Nguyên tắc thiết kế chính

### Tách tầng rõ ràng

Project chia code theo đúng flow data engineering:

- `extract_weather.py`: lấy dữ liệu từ API và lưu raw.
- `transform_weather.py`: đọc raw, làm sạch, flatten thành bảng.
- `load_postgres.py`: load cleaned CSV vào PostgreSQL và chạy SQL model.
- `main.py`: điều phối các bước.

Lợi ích: khi lỗi xảy ra, mình biết lỗi nằm ở tầng nào. Ví dụ API lỗi thì sửa extract, schema CSV lỗi thì sửa transform/load, SQL lỗi thì sửa `sql/`.

### Mỗi tầng để lại output kiểm tra được

Pipeline không chỉ chạy trong RAM:

- Sau extract có raw JSON.
- Sau transform có cleaned CSV.
- Sau load có bảng staging/fact/mart trong PostgreSQL.

Nhờ vậy mình có thể kiểm tra từng checkpoint mà không cần chạy lại toàn bộ pipeline.

### Idempotent ở tầng database

Pipeline có thể chạy nhiều lần trong ngày. Để tránh nhân đôi dữ liệu:

- `stg_weather_observations` bị `TRUNCATE` trước mỗi batch load.
- `dim_location` dùng `ON CONFLICT (city) DO NOTHING`.
- `dim_date` dùng `ON CONFLICT (date_id) DO NOTHING`.
- `fact_weather_observation` có unique key `(location_id, observation_time)` và dùng `ON CONFLICT DO NOTHING`.

Nói ngắn gọn: staging là buffer batch hiện tại, fact mới là nơi giữ lịch sử.

### Config tách khỏi code

Thông tin thay đổi theo môi trường nằm ở:

- `.env`
- `.env.example`
- `data/cities.csv`
- `src/config.py`

Code không hard-code danh sách city trong Python nữa. Thêm/xóa địa điểm thì sửa `data/cities.csv`.

---

## 1. Cấu hình tập trung - `src/config.py`

File này là source of truth cho đường dẫn, API config, DB config và danh sách city.

### Các đường dẫn chính

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CITIES_FILE = PROJECT_ROOT / "data" / "cities.csv"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "open-meteo"
CLEANED_DATA_DIR = PROJECT_ROOT / "data" / "cleaned"
SQL_DIR = PROJECT_ROOT / "sql"
```

Vì sao dùng `Path(__file__).resolve().parents[1]`?

- `__file__` là đường dẫn tới `src/config.py`.
- `parents[1]` đi lên thư mục gốc project.
- Nhờ vậy chạy script từ đâu cũng vẫn tìm đúng `data/`, `sql/`, `.env`.

### Load `.env`

```python
load_dotenv(PROJECT_ROOT / ".env")
```

`.env` chứa thông tin local như DB host/user/password. File này bị ignore, không commit.

Open-Meteo workflow hiện tại không cần API key.

### DB connection

```python
def get_db_url() -> str:
    return (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
```

Hàm này tạo connection string cho SQLAlchemy.

Vì sao gói thành hàm?

- Nếu đổi host hoặc database, chỉ sửa config.
- `load_postgres.py` không cần biết chi tiết từng biến env.

### Danh sách weather fields

```python
CURRENT_WEATHER_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "is_day",
]
```

Đây là các field xin từ Open-Meteo block `current`.

### Load city từ `data/cities.csv`

```python
def load_cities(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, skipinitialspace=True)
        ...
        "latitude": float(clean_row["latitude"]),
        "longitude": float(clean_row["longitude"]),
```

Vì sao cần ép `latitude`/`longitude` sang `float`?

- CSV đọc mọi thứ thành string.
- API cần tọa độ số.
- Nếu không ép kiểu, lỗi có thể xuất hiện muộn ở bước request.

Hiện tại `data/cities.csv` có 34 tỉnh/thành.

---

## 2. Extract - `src/extract_weather.py`

File này làm nhiệm vụ gọi Open-Meteo API và lưu raw JSON.

### Slug city

```python
def slugify_city(city: str) -> str:
    slug = city.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")
```

Ví dụ:

```text
Ho Chi Minh City -> ho_chi_minh_city
An Giang -> an_giang
Ca Mau -> ca_mau
```

Slug được dùng làm tên file raw. Transform cũng dùng cùng slug để map file về đúng city config.

### Build API params

```python
def build_open_meteo_params(city_config):
    return {
        "latitude": city_config["latitude"],
        "longitude": city_config["longitude"],
        "current": ",".join(CURRENT_WEATHER_FIELDS),
        "timezone": WEATHER_TIMEZONE,
        "forecast_days": 1,
    }
```

Open-Meteo không query bằng tên city mà query bằng tọa độ.

### Request có retry và tắt proxy env

```python
session = requests.Session()
session.trust_env = False
```

Vì sao có `trust_env = False`?

- Trên máy hiện tại từng gặp lỗi request Python bị ảnh hưởng bởi proxy/env.
- PowerShell gọi API được, nhưng Python `requests` timeout/502.
- Tắt đọc proxy từ env giúp request đi trực tiếp ổn định hơn.

Retry logic:

- Tối đa 3 lần.
- Timeout 45 giây.
- HTTP 5xx hoặc lỗi mạng thì retry.
- HTTP 4xx thì fail ngay vì thường là request sai.

```python
except HTTPError as exc:
    status_code = exc.response.status_code if exc.response is not None else None
    if status_code is not None and status_code < 500:
        raise
```

### Lưu raw JSON

```python
output_dir = RAW_DATA_DIR / f"date={run_date}"
output_path = output_dir / f"{slugify_city(city_config['city'])}.json"
```

Raw path hiện tại:

```text
data/raw/open-meteo/date=YYYY-MM-DD/<city_slug>.json
```

Vì sao lưu raw trước?

- Raw là dữ liệu gốc, chưa chỉnh sửa.
- Nếu transform sai, có thể reprocess từ raw.
- Không cần gọi lại API cho dữ liệu đã lưu.
- Đây là pattern Raw Zone trong data lake.

---

## 3. Transform - `src/transform_weather.py`

File này đọc raw JSON và tạo bảng cleaned.

Output:

```text
data/cleaned/weather_observations.csv
```

### Weather code map

```python
WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    ...
    95: "Thunderstorm",
}
```

Open-Meteo trả `weather_code` dạng số. Dashboard/người đọc cần text dễ hiểu, nên map sang `weather_condition`.

Nếu gặp code chưa có trong map:

```python
"weather_condition": WEATHER_CODE_MAP.get(weather_code, "Unknown")
```

### Map raw file về city

```python
CITY_BY_FILE_STEM = {slugify_city(city["city"]): city for city in CITIES}
city_config = CITY_BY_FILE_STEM.get(raw_path.stem)
```

`raw_path.stem` là tên file không có `.json`, ví dụ `an_giang`.

Nếu raw file không map được city config:

```python
raise ValueError(f"Cannot map raw file to configured city: {raw_path}")
```

Đây là fail-fast tốt. Nó giúp phát hiện trường hợp raw cũ không còn khớp `data/cities.csv`.

### Flatten JSON

Open-Meteo response có block nested:

```json
{
  "latitude": 10.823,
  "longitude": 106.6296,
  "current": {
    "time": "...",
    "temperature_2m": 25.1,
    "relative_humidity_2m": 97
  }
}
```

Transform chuyển thành một row phẳng:

```python
{
    "city": ...,
    "country": ...,
    "latitude": ...,
    "longitude": ...,
    "observation_time": current.get("time"),
    "temperature": current.get("temperature_2m"),
    "humidity": current.get("relative_humidity_2m"),
    ...
}
```

### Metadata lineage

Transform thêm:

- `inserted_at`: thời điểm transform.
- `source_file`: raw file sinh ra row đó.

Hai cột này giúp debug và truy vết dữ liệu.

### Transform batch mới nhất, theo ngày hoặc toàn bộ history

Bug cũ: transform dùng `raw_dir.rglob("*.json")`, tức là mỗi lần chạy sẽ đọc toàn bộ raw history.

Code mới có:

```python
def list_raw_weather_files(raw_dir, run_date=None, include_history=False):
```

Hành vi hiện tại:

- Full run mới: transform đúng raw files vừa extract.
- `--skip-extract`: transform folder ngày mới nhất.
- `--date YYYY-MM-DD`: transform một partition ngày cụ thể.
- `--all-raw`: reprocess toàn bộ raw history.

Vì sao thiết kế vậy?

- Daily run không nên tự động reprocess toàn bộ lịch sử.
- Khi cần backfill/reprocess thì vẫn có `--all-raw`.
- Khi debug một ngày cụ thể thì dùng `--date`.

---

## 4. Database infrastructure - `docker-compose.yml`

Project dùng PostgreSQL 16 trong Docker:

```yaml
services:
  postgres:
    image: postgres:16
    container_name: weather_postgres
    environment:
      POSTGRES_DB: weather_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
```

### Vì sao dùng Docker?

- Không cần cài PostgreSQL trực tiếp vào Windows.
- Dễ reset, dễ chạy lại trên máy khác.
- Config DB rõ ràng trong repo.

### Volume

```yaml
volumes:
  - weather_pgdata:/var/lib/postgresql/data
```

Volume giữ dữ liệu PostgreSQL sau khi container restart.

### Healthcheck

```yaml
pg_isready -U postgres -d weather_db
```

Healthcheck giúp biết container đã thật sự sẵn sàng nhận connection.

---

## 5. Load - `src/load_postgres.py`

File này load cleaned CSV vào PostgreSQL và chạy SQL model.

### Staging columns

```python
STAGING_COLUMNS = [
    "city",
    "country",
    "latitude",
    ...
    "inserted_at",
]
```

Danh sách này phải khớp với `stg_weather_observations`.

### Validate schema trước khi load

Bug cũ: code chỉ lấy các cột có tồn tại:

```python
df = df[[c for c in STAGING_COLUMNS if c in df.columns]]
```

Nếu CSV thiếu cột quan trọng, pipeline có thể load sai hoặc lỗi muộn.

Code mới:

```python
missing_columns = [column for column in STAGING_COLUMNS if column not in df.columns]
if missing_columns:
    raise ValueError(...)
```

Nếu CSV thiếu cột, pipeline fail sớm với message rõ.

Ngoài ra còn check:

```python
if df.empty:
    raise ValueError(...)
```

### TRUNCATE staging

```python
conn.execute(text(f"TRUNCATE TABLE {STAGING_TABLE}"))
df.to_sql(STAGING_TABLE, engine, if_exists="append", index=False)
```

Vì sao `TRUNCATE` staging?

- Staging là buffer cho batch hiện tại.
- Nếu không truncate, staging sẽ tích lũy data cũ và trùng.
- Lịch sử thật nằm ở fact table.

### Init DB vs Load data

```python
init_database()
```

Chạy các script tạo schema:

- `01_create_staging_table.sql`
- `02_create_dimensions.sql`
- `03_create_fact_table.sql`
- `05_create_marts.sql`

```python
load_to_postgres()
```

Chạy:

- Load CSV vào staging.
- Chạy `04_load_star_schema.sql`.

Lưu ý: `04_load_star_schema.sql` không chạy trong init vì nó là script nạp data, không phải script tạo schema.

---

## 6. SQL model - `sql/`

### `01_create_staging_table.sql`

Tạo bảng:

```text
stg_weather_observations
```

Vai trò: nhận dữ liệu cleaned CSV trước khi load vào star schema.

### `02_create_dimensions.sql`

Tạo:

```text
dim_location
dim_date
```

`dim_location` có:

```sql
CONSTRAINT uq_dim_location_city UNIQUE (city)
```

Ràng buộc này giúp `ON CONFLICT (city) DO NOTHING` hoạt động.

### `03_create_fact_table.sql`

Tạo:

```text
fact_weather_observation
```

Grain của fact:

```text
1 row = 1 weather observation for 1 location at 1 observation_time
```

Unique key:

```sql
CONSTRAINT uq_fact_location_time UNIQUE (location_id, observation_time)
```

Đây là key chống trùng khi pipeline chạy lại.

### `04_load_star_schema.sql`

Script này chạy mỗi lần pipeline load.

Nó làm 3 bước:

1. Insert new locations vào `dim_location`.
2. Insert new dates vào `dim_date`.
3. Insert observations vào `fact_weather_observation`.

Các insert đều dùng `ON CONFLICT DO NOTHING` để idempotent.

### `05_create_marts.sql`

Tạo 2 SQL views:

```text
mart_daily_weather_summary
mart_weekly_weather_summary
```

Vì sao dùng view?

- Data hiện còn nhỏ.
- View luôn phản ánh dữ liệu mới nhất trong fact/dim.
- Chưa cần materialized view.

---

## 7. Điều phối - `src/main.py`

`main.py` là entrypoint cho pipeline.

### Các lệnh hiện tại

Chạy extract + transform:

```bash
uv --cache-dir .uv-cache run python src/main.py
```

Chạy full pipeline extract -> transform -> load DB:

```bash
uv --cache-dir .uv-cache run python src/main.py --load
```

Chỉ transform raw ngày mới nhất:

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract
```

Transform một ngày cụ thể:

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract --date 2026-06-11
```

Reprocess toàn bộ raw history:

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract --all-raw
```

Chỉ extract:

```bash
uv --cache-dir .uv-cache run python src/main.py --extract-only
```

Tạo schema DB:

```bash
uv --cache-dir .uv-cache run python src/main.py --init-db
```

### Chặn combo sai

Bug cũ: có thể chạy:

```bash
python src/main.py --extract-only --load
```

Lệnh đó nguy hiểm vì extract-only bỏ qua transform, nhưng load vẫn có thể load CSV cũ.

Code mới:

```python
if args.extract_only and args.load:
    parser.error("--extract-only cannot be combined with --load because load needs transformed data.")
```

---

## 8. Automation - `run_pipeline.bat`

File này dùng cho Windows Task Scheduler.

### Hành vi hiện tại

```bat
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" src\main.py --load
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" src\main.py --load
) else (
    uv --cache-dir .uv-cache run python src\main.py --load
)
```

Vì sao làm vậy?

- Ưu tiên Python trong `.venv`.
- Nếu không có `.venv`, dùng `venv`.
- Nếu không có virtualenv, fallback sang `uv`.
- Không phụ thuộc mơ hồ vào `python` trong PATH của Task Scheduler.

### Logging và exit code

Batch ghi log vào:

```text
logs/pipeline.log
```

Và trả đúng exit code:

```bat
set "PIPELINE_EXIT=%ERRORLEVEL%"
exit /b %PIPELINE_EXIT%
```

Điều này quan trọng vì Task Scheduler cần exit code để biết job thành công hay thất bại.

Verification gần nhất:

```text
cmd /c run_pipeline.bat
logs/pipeline.log ... Ket thuc pipeline (exit=0)
```

---

## 9. Build city list - `scripts/build_cities_csv.py`

File này là tiện ích chạy một lần để sinh `data/cities.csv` từ Open-Meteo Geocoding API.

Nó không phải pipeline hằng ngày.

### Vì sao có script này?

Open-Meteo weather API cần tọa độ, không cần tên city. Vì vậy mình cần một file city list:

```text
city,country,latitude,longitude
```

### Manual overrides

Một số địa điểm geocoding dễ sai hoặc không ra kết quả, nên có:

```python
MANUAL_OVERRIDES = {
    "Hai Phong": (...),
    "Quang Tri": (...),
}
```

### Fail nếu thiếu city

Bug cũ: script có thể ghi file partial nếu geocoding thiếu một số tỉnh/thành.

Code mới:

```python
if missing:
    sys.exit(1)

if len(rows) != len(PROVINCES):
    sys.exit(1)
```

Nhờ vậy không commit nhầm `data/cities.csv` thiếu dòng.

---

## 10. Repo hygiene - `.gitignore`

Hiện tại ignore:

- `.env`
- `.venv/`
- `.uv-cache/`
- `data/raw/`
- `data/cleaned/`
- `logs/`
- `*.pbix`

Không còn ignore toàn bộ `docs/` nữa.

Vì sao?

- `docs/` là tài liệu portfolio và học tập, nên cần commit được.
- Raw/cleaned/log là artifact local, có thể tái tạo, không nên làm nặng repo.
- `.env` chứa secret, không commit.

---

## 11. Trạng thái verification mới nhất

Đã kiểm tra:

```text
cities: 34
stg_weather_observations: 34
dim_location: 34
dim_date: 1
fact_weather_observation: 109
mart_daily_weather_summary: 34
mart_weekly_weather_summary: 34
```

Các lệnh đã chạy được:

```bash
uv --cache-dir .uv-cache run python src/main.py --help
uv --cache-dir .uv-cache run python src/main.py --skip-extract
uv --cache-dir .uv-cache run python src/main.py --skip-extract --date 2026-06-11
uv --cache-dir .uv-cache run python src/main.py --skip-extract --all-raw
uv --cache-dir .uv-cache run python src/main.py --skip-extract --load
cmd /c run_pipeline.bat
```

Lưu ý: `fact_weather_observation` có 109 dòng vì pipeline đã chạy nhiều lần trong ngày; fact giữ lịch sử theo `location_id + observation_time`.

---

## 12. Tóm tắt theo tầng pipeline

| Tầng | Trạng thái | File chính |
|---|---|---|
| Data source | Done | Open-Meteo Forecast API |
| City config | Done | `data/cities.csv`, `src/config.py` |
| Extract | Done | `src/extract_weather.py` |
| Raw Zone | Done | `data/raw/open-meteo/date=YYYY-MM-DD/` |
| Transform | Done | `src/transform_weather.py` |
| Cleaned CSV | Done | `data/cleaned/weather_observations.csv` |
| PostgreSQL staging | Done | `src/load_postgres.py`, `sql/01` |
| Star schema | Done | `sql/02`, `sql/03`, `sql/04` |
| Mart views | Done | `sql/05` |
| Dashboard | Planned | Power BI chưa verify `.pbix` |
| Automation wrapper | Done | `run_pipeline.bat` |
| Scheduled job thật | Pending | Chưa xác nhận Task Scheduler đã đăng ký |
| Tests/data quality | Pending | Chưa có automated tests |

---

## 13. Glossary cần nắm

| Thuật ngữ | Nghĩa | Trong project này |
|---|---|---|
| Raw Zone | Nơi lưu dữ liệu gốc chưa xử lý | `data/raw/open-meteo/date=.../*.json` |
| Cleaned data | Dữ liệu đã flatten/chuẩn hóa | `weather_observations.csv` |
| Staging | Bảng đệm để load batch hiện tại | `stg_weather_observations` |
| Fact table | Bảng chứa số đo/sự kiện | `fact_weather_observation` |
| Dimension table | Bảng chứa ngữ cảnh phân tích | `dim_location`, `dim_date` |
| Star schema | Fact ở giữa, dimension xung quanh | Weather fact nối location/date |
| Mart | Bảng/view tổng hợp cho BI | daily/weekly summary views |
| Idempotent | Chạy lại không tạo trùng dữ liệu | `UNIQUE` + `ON CONFLICT DO NOTHING` |
| Partition | Chia data theo thư mục/ngày | `date=YYYY-MM-DD` |
| Lineage | Truy vết dữ liệu từ đâu ra | `source_file`, `inserted_at` |
| Orchestration | Điều phối các bước chạy | `main.py`, `run_pipeline.bat` |

---

## 14. Câu hỏi phỏng vấn mẫu

### Q1. Pipeline này chạy end-to-end như thế nào?

Em lấy dữ liệu thời tiết hiện tại từ Open-Meteo API cho 34 tỉnh/thành trong `data/cities.csv`. Dữ liệu raw được lưu theo ngày ở `data/raw/open-meteo/date=YYYY-MM-DD`. Sau đó em transform JSON nested thành CSV phẳng, validate schema rồi load vào PostgreSQL staging. Từ staging, SQL script nạp vào star schema gồm `dim_location`, `dim_date`, `fact_weather_observation`, rồi tạo mart daily/weekly để Power BI đọc.

### Q2. Vì sao phải lưu raw JSON?

Raw JSON là dữ liệu gốc. Nếu transform sai hoặc cần thêm field mới, em có thể reprocess từ raw mà không cần gọi API lại. Đây là cách tách ingestion khỏi processing và giúp debug từng tầng.

### Q3. Idempotent trong project này nằm ở đâu?

Staging được truncate mỗi batch nên không tích lũy trùng. Fact có unique key `(location_id, observation_time)` và SQL load dùng `ON CONFLICT DO NOTHING`, nên chạy lại cùng observation sẽ không tạo duplicate.

### Q4. Vì sao không để một bảng phẳng mà dùng star schema?

Star schema tách số đo khỏi ngữ cảnh. Fact chứa metrics như temperature, humidity, rain; dimensions chứa location/date. Cách này dễ query, dễ tổng hợp và phù hợp với Power BI.

### Q5. Grain của fact table là gì?

Một dòng trong `fact_weather_observation` là một observation của một location tại một `observation_time`.

### Q6. Vì sao cần staging?

Staging là nơi hạ cánh của cleaned CSV trước khi mô hình hóa. Nó giúp kiểm tra dữ liệu batch hiện tại và tách logic load file khỏi logic build star schema.

### Q7. Vì sao transform không mặc định đọc toàn bộ raw history nữa?

Daily run chỉ nên xử lý batch mới nhất hoặc batch vừa extract để tránh phình CSV và tránh lỗi do raw cũ lệch config. Khi thật sự cần reprocess lịch sử thì dùng `--all-raw`.

### Q8. Vì sao `--extract-only --load` bị chặn?

`--extract-only` nghĩa là chỉ lưu raw, không transform. Nếu vẫn cho `--load`, pipeline có thể load CSV cũ, gây hiểu nhầm là dữ liệu mới đã vào DB. Vì vậy code fail sớm combo này.

### Q9. Vì sao mart là view?

Data hiện nhỏ, view đủ nhanh và luôn đọc dữ liệu mới nhất từ fact/dim. Nếu data lớn hoặc dashboard chậm, có thể chuyển sang materialized view.

### Q10. Automation hiện tại đã tới đâu?

Đã có `run_pipeline.bat` chạy full pipeline và ghi log exit code. File này phù hợp để Windows Task Scheduler gọi. Tuy nhiên chưa xác nhận task scheduler đã được đăng ký chạy tự động thật mỗi ngày.

### Q11. Nếu API lỗi thì sao?

Extractor có retry 3 lần, timeout 45 giây, retry cho network error và HTTP 5xx. HTTP 4xx fail ngay vì thường là request sai. Ngoài ra raw lưu theo city nên dễ biết city nào bị lỗi.

### Q12. Nếu nâng cấp tiếp thì làm gì?

Em sẽ thêm automated tests cho CLI/schema/transform partition, thêm data quality checks như range temperature/humidity, tạo Power BI dashboard thật và đăng ký Task Scheduler để chạy hằng ngày.
