# Pipeline đã làm đến đâu?

File này ghi trạng thái hiện tại của project `automated-weather-data-pipeline` sau khi đã rà code và fix các lỗi chính trong checklist.

## 1. Mục tiêu pipeline

Pipeline này thu thập dữ liệu thời tiết từ Open-Meteo, lưu raw JSON, transform thành bảng sạch, load vào PostgreSQL, tạo star schema và mart để phục vụ phân tích/Power BI.

Luồng hiện tại:

```text
Open-Meteo API
-> Raw JSON theo ngày
-> Cleaned CSV
-> PostgreSQL staging
-> dim_location / dim_date / fact_weather_observation
-> mart_daily_weather_summary / mart_weekly_weather_summary
```

## 2. Cấu hình hiện tại

File chính:

- `src/config.py`
- `data/cities.csv`

Đang cấu hình:

- API source: `https://api.open-meteo.com/v1/forecast`
- Timezone: `Asia/Ho_Chi_Minh`
- Raw path: `data/raw/open-meteo`
- Cleaned path: `data/cleaned`
- Database: PostgreSQL `weather_db`
- City list: 34 tỉnh/thành từ `data/cities.csv`

Open-Meteo không cần API key cho use case hiện tại.

## 3. Checkpoint 1: Extract raw JSON

File chính:

- `src/extract_weather.py`
- `src/main.py`

Pipeline gọi Open-Meteo Forecast API theo `latitude` và `longitude` của từng city trong `data/cities.csv`.

Các field lấy từ block `current`:

- `temperature_2m`
- `relative_humidity_2m`
- `apparent_temperature`
- `precipitation`
- `rain`
- `weather_code`
- `cloud_cover`
- `pressure_msl`
- `surface_pressure`
- `wind_speed_10m`
- `wind_direction_10m`
- `wind_gusts_10m`
- `is_day`

Output raw hiện nằm theo partition ngày:

```text
data/raw/open-meteo/date=2026-06-11/
```

Sau lần chạy gần nhất, partition này có 34 raw JSON files, tương ứng 34 tỉnh/thành.

Ý nghĩa:

- Raw Zone giữ response gốc từ API.
- Có thể reprocess lại nếu logic transform thay đổi.
- Tên file được slugify từ city, ví dụ `ho_chi_minh_city.json`, `an_giang.json`.

Trạng thái: đã chạy được.

## 4. Checkpoint 2: Transform raw JSON thành bảng sạch

File chính:

- `src/transform_weather.py`

Bước này đọc raw JSON, lấy block `current`, flatten thành bảng và ghi ra:

```text
data/cleaned/weather_observations.csv
```

Những việc transform đang làm:

- Map raw filename về đúng city trong `data/cities.csv`.
- Thêm `city`, `country`, `latitude`, `longitude`.
- Đổi field Open-Meteo sang tên dễ phân tích hơn.
- Chuyển `temperature_2m` thành `temperature`.
- Chuyển `relative_humidity_2m` thành `humidity`.
- Chuyển `wind_speed_10m` thành `wind_speed`.
- Map `weather_code` thành `weather_condition`.
- Thêm `inserted_at`.
- Giữ `source_file` để truy vết dòng dữ liệu.

Fix mới nhất:

- Trước đây transform mặc định đọc toàn bộ raw history bằng `rglob("*.json")`.
- Hiện tại transform mặc định chỉ lấy batch hợp lý:
  - Full run mới: transform đúng raw files vừa extract.
  - `--skip-extract`: transform folder ngày mới nhất.
  - `--date YYYY-MM-DD`: transform một partition ngày cụ thể.
  - `--all-raw`: reprocess toàn bộ raw history khi thật sự cần.

Verification gần nhất:

```text
uv --cache-dir .uv-cache run python src/main.py --skip-extract
Saved cleaned weather table: ...weather_observations.csv (34 rows from 34 raw files)
```

Trạng thái: đã chạy được.

## 5. Checkpoint 3: PostgreSQL staging và star schema

File chính:

- `docker-compose.yml`
- `src/load_postgres.py`
- `sql/01_create_staging_table.sql`
- `sql/02_create_dimensions.sql`
- `sql/03_create_fact_table.sql`
- `sql/04_load_star_schema.sql`
- `sql/05_create_marts.sql`

PostgreSQL chạy bằng Docker Compose:

```text
container: weather_postgres
image: postgres:16
database: weather_db
status checked: Up / healthy
```

Các bảng/view:

- `stg_weather_observations`
- `dim_location`
- `dim_date`
- `fact_weather_observation`
- `mart_daily_weather_summary`
- `mart_weekly_weather_summary`

Luồng load:

```text
data/cleaned/weather_observations.csv
-> stg_weather_observations
-> dim_location
-> dim_date
-> fact_weather_observation
-> marts
```

Fix mới nhất:

- `src/load_postgres.py` đã validate đủ schema CSV trước khi load.
- Nếu cleaned CSV thiếu cột bắt buộc, pipeline fail sớm với message rõ:

```text
Cleaned CSV is missing required staging columns: ...
```

Verification DB gần nhất:

```text
stg_weather_observations: 34
dim_location: 34
dim_date: 1
fact_weather_observation: 109
mart_daily_weather_summary: 34
mart_weekly_weather_summary: 34
```

Lưu ý: `fact_weather_observation` có 109 dòng vì đã chạy live pipeline nhiều lần trong ngày; fact giữ lịch sử theo `location_id + observation_time`.

Trạng thái: đã chạy được từ cleaned CSV vào PostgreSQL và mart.

## 6. Entry point hiện tại

File chính:

- `src/main.py`

Các mode đang có:

```bash
uv --cache-dir .uv-cache run python src/main.py
```

Chạy extract và transform.

```bash
uv --cache-dir .uv-cache run python src/main.py --load
```

Chạy extract -> transform -> load PostgreSQL.

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract
```

Bỏ qua API, transform raw JSON từ folder ngày mới nhất.

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract --date 2026-06-11
```

Transform một partition ngày cụ thể.

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract --all-raw
```

Reprocess toàn bộ raw history.

```bash
uv --cache-dir .uv-cache run python src/main.py --extract-only
```

Chỉ gọi API và lưu raw JSON.

```bash
uv --cache-dir .uv-cache run python src/main.py --init-db
```

Tạo schema PostgreSQL: staging, dimensions, fact, marts.

Fix mới nhất:

- Đã chặn combo sai `--extract-only --load`.
- Lệnh này hiện fail sớm:

```bash
uv --cache-dir .uv-cache run python src/main.py --extract-only --load
```

Message:

```text
--extract-only cannot be combined with --load because load needs transformed data.
```

## 7. Automation hiện có

File chính:

- `run_pipeline.bat`

File này dùng cho Windows Task Scheduler. Nó chạy full pipeline và ghi log vào:

```text
logs/pipeline.log
```

Fix mới nhất:

- Không còn phụ thuộc mơ hồ vào `python` trong PATH.
- Ưu tiên `.venv\Scripts\python.exe`.
- Nếu không có, dùng `venv\Scripts\python.exe`.
- Nếu không có virtualenv, fallback sang:

```text
uv --cache-dir .uv-cache run python src\main.py --load
```

- Ghi exit code vào log.
- Trả đúng exit code cho Task Scheduler.
- Đã sửa comment batch gây lỗi redirection và tạo file rác `load`.

Verification:

```text
cmd /c run_pipeline.bat
```

Kết quả:

```text
logs/pipeline.log ... Ket thuc pipeline (exit=0)
```

Trạng thái: batch wrapper đã chạy được, nhưng chưa xác nhận task đã được đăng ký thật trong Windows Task Scheduler.

## 8. Script build city list

File chính:

- `scripts/build_cities_csv.py`

Mục đích:

- Gọi Open-Meteo Geocoding API để sinh `data/cities.csv`.
- Đây là tiện ích chạy một lần, không phải pipeline hằng ngày.

Fix mới nhất:

- Nếu còn thiếu tỉnh/thành trong quá trình geocoding, script không ghi file partial nữa.
- Nếu số dòng output không bằng số dòng trong `PROVINCES`, script exit non-zero.
- Điều này tránh việc commit nhầm `data/cities.csv` thiếu city.

Trạng thái: logic fail-safe đã thêm, chưa cần chạy lại nếu `data/cities.csv` hiện tại đang ổn.

## 9. Checklist bug đã xử lý

File checklist:

- `CHECKLIST_LOI_CAN_SUA.md`

Các mục đã tick:

- [x] Chặn combo CLI sai `--extract-only --load`.
- [x] Validate schema CSV trước khi load PostgreSQL.
- [x] Chỉ transform batch raw cần thiết.
- [x] Làm `scripts/build_cities_csv.py` fail nếu thiếu tỉnh/thành.
- [x] Không ignore toàn bộ `docs/`.
- [x] Làm `run_pipeline.bat` chạy ổn với môi trường `uv`.

## 10. Những phần chưa hoàn thiện

Power BI:

- Chưa có dashboard `.pbix` được verify trong repo.
- Hiện tại đã có mart/view để Power BI kết nối sau.

Data quality:

- Đã có schema validation trước khi load staging.
- Chưa có test kiểm tra null, duplicate, range nhiệt độ, range humidity.

Backfill:

- Pipeline hiện lấy current weather theo thời điểm chạy.
- Chưa có historical weather backfill nhiều ngày.

Production scheduling:

- `run_pipeline.bat` đã chạy được và trả exit code đúng.
- Chưa xác nhận task đã được đăng ký thật trong Windows Task Scheduler.

Packaging:

- Repo đang dùng `requirements.txt` với `uv pip install`.
- Chưa có `pyproject.toml`/`uv.lock` để quản lý dependency chuẩn hơn.

Automated tests:

- Chưa có test tự động cho CLI guard, schema validation và transform partition.

## 11. Tóm tắt ngắn gọn để tự giải thích

Hiện tại project đã chạy được core ETL:

```text
Extract: Open-Meteo API -> raw JSON
Transform: raw JSON -> cleaned CSV
Load: cleaned CSV -> PostgreSQL staging
Model: staging -> dim/fact
Mart: fact/dim -> daily and weekly summary views
Automation wrapper: run_pipeline.bat -> full pipeline -> logs/pipeline.log
```

Cái đã có bằng chứng chạy thật:

- Lấy được data từ Open-Meteo cho 34 tỉnh/thành.
- Ghi được 34 raw JSON files theo ngày.
- Transform được cleaned CSV 34 dòng, 21 cột.
- PostgreSQL container đang healthy.
- Load được 34 dòng vào staging.
- `dim_location` có 34 dòng.
- Mart daily/weekly có 34 dòng.
- `run_pipeline.bat` chạy full pipeline và kết thúc `exit=0`.

Cái tiếp theo nên làm:

1. Thêm data quality checks.
2. Thêm test tự động cho CLI/schema/transform partition.
3. Tạo Power BI dashboard từ `mart_daily_weather_summary`.
4. Chuyển dependency sang `pyproject.toml` và `uv.lock`.
5. Đăng ký Windows Task Scheduler và kiểm tra log sau lần chạy tự động đầu tiên.

## 12. Phỏng vấn trả lời sao?

Em xây pipeline theo từng layer. Đầu tiên em gọi Open-Meteo API theo tọa độ trong `data/cities.csv` và lưu response gốc vào Raw Zone theo ngày. Việc giữ raw JSON giúp em kiểm tra lại dữ liệu nguồn và reprocess khi logic transform thay đổi.

Sau đó em transform JSON nested thành bảng phẳng, chuẩn hóa tên cột và map `weather_code` thành điều kiện thời tiết dễ đọc. Transform hiện hỗ trợ chạy theo batch mới nhất, theo ngày cụ thể, hoặc reprocess toàn bộ lịch sử khi cần.

Sau khi có cleaned CSV, em validate schema rồi load vào PostgreSQL staging. Từ staging, em tạo star schema gồm `dim_location`, `dim_date` và `fact_weather_observation`. Cuối cùng em tạo mart daily/weekly summary để Power BI có thể đọc trực tiếp. Hiện tại pipeline đã chạy end-to-end tới PostgreSQL mart và có batch wrapper cho Windows Task Scheduler.
