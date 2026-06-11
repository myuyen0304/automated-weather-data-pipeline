# Hands-on Weather Pipeline

Mục tiêu của file này là học pipeline bằng từng checkpoint nhỏ, có output thật để kiểm tra, thay vì chỉ đọc README.

## Checkpoint 1: Extract raw JSON từ Open-Meteo

### Mục tiêu

Chứng minh pipeline có thể gọi Open-Meteo Forecast API cho từng thành phố và lưu response gốc vào Raw Zone.

### File liên quan

- `src/config.py`: cấu hình API, timezone, danh sách thành phố và field cần lấy.
- `src/extract_weather.py`: gọi API và ghi raw JSON.
- `src/main.py`: entrypoint chạy checkpoint hiện tại.
- `data/raw/open-meteo/date=YYYY-MM-DD/*.json`: output raw sau khi chạy.

### Lệnh chạy

```bash
uv venv
uv --cache-dir .uv-cache pip install -r requirements.txt
uv --cache-dir .uv-cache run python src/main.py
```

### Cách kiểm tra đã chạy đúng

Sau khi chạy thành công, thư mục raw sẽ có 3 file:

```text
data/raw/open-meteo/date=YYYY-MM-DD/
├── ho_chi_minh_city.json
├── hanoi.json
└── da_nang.json
```

Mỗi file cần có các phần chính từ Open-Meteo:

- `latitude`
- `longitude`
- `timezone`
- `current_units`
- `current`

Trong `current`, kiểm tra các field như:

- `time`
- `temperature_2m`
- `relative_humidity_2m`
- `weather_code`
- `wind_speed_10m`

### Vì sao checkpoint này quan trọng?

Trong data pipeline, Raw Zone là bằng chứng đầu tiên rằng mình lấy được dữ liệu thật từ source. Nếu bước này sai, transform, database, mart và dashboard phía sau đều không đáng tin.

### Phỏng vấn trả lời sao?

Em bắt đầu pipeline bằng Raw Zone để lưu response gốc từ Open-Meteo. Việc này giúp em kiểm tra lại dữ liệu nguồn và có thể reprocess nếu logic transform thay đổi. Ở checkpoint đầu tiên, em chưa vội load database mà ưu tiên chứng minh ingestion chạy được và tạo ra raw JSON theo ngày, theo thành phố.

## Checkpoint 2: Transform raw JSON thành bảng sạch

### Mục tiêu

Đọc raw JSON đã lưu, lấy block `current`, thêm city/country từ config, chuẩn hóa tên cột và xuất ra một bảng sạch để kiểm tra trước khi load PostgreSQL.

### File liên quan

- `src/transform_weather.py`: normalize raw JSON thành record dạng bảng.
- `data/cleaned/weather_observations.csv`: output cleaned sau transform.

### Lệnh chạy

Nếu muốn chạy cả extract và transform:

```bash
uv --cache-dir .uv-cache run python src/main.py
```

Nếu đã có raw JSON và chỉ muốn transform lại:

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract
```

Nếu chỉ muốn kiểm tra extract:

```bash
uv --cache-dir .uv-cache run python src/main.py --extract-only
```

### Cách kiểm tra đã chạy đúng

File `data/cleaned/weather_observations.csv` cần có 3 dòng tương ứng 3 thành phố:

- Ho Chi Minh City
- Hanoi
- Da Nang

Các cột quan trọng:

- `observation_time`
- `temperature`
- `humidity`
- `weather_code`
- `weather_condition`
- `source_file`

### Phỏng vấn trả lời sao?

Sau khi lưu raw JSON, em tách riêng bước transform để chuyển dữ liệu nested từ Open-Meteo thành bảng phẳng. Em map tên field kỹ thuật như `temperature_2m` sang tên analytics dễ đọc hơn như `temperature`, đồng thời thêm `city`, `country` và `source_file` để truy vết dữ liệu.

## Checkpoint 3: Bật PostgreSQL bằng Docker và load vào staging

### Mục tiêu

Tạo database thật bằng Docker, tạo bảng `stg_weather_observations`, rồi load dữ liệu từ `data/cleaned/weather_observations.csv` vào staging.

### File liên quan

- `docker-compose.yml`: định nghĩa container PostgreSQL 16.
- `.env`: thông tin kết nối (tạo từ `.env.example`).
- `sql/01_create_staging_table.sql`: DDL bảng staging.
- `src/load_postgres.py`: nạp CSV vào staging và chạy SQL mô hình hóa.

### Lệnh chạy

```bat
REM 1) Bật PostgreSQL (cần Docker Desktop đang chạy)
docker compose up -d
docker ps

REM 2) Tạo file .env từ mẫu (chỉ làm 1 lần)
copy .env.example .env

REM 3) Cài thêm thư viện DB nếu chưa có
pip install -r requirements.txt

REM 4) Tạo schema (staging + dim + fact + mart). Chỉ chạy 1 lần.
python src\main.py --init-db
```

### Cách kiểm tra đã chạy đúng

```bat
docker exec -it weather_postgres psql -U postgres -d weather_db -c "\dt"
```

Phải thấy các bảng: `stg_weather_observations`, `dim_location`, `dim_date`, `fact_weather_observation`.

### Vì sao checkpoint này quan trọng?

Staging là lớp đệm giữa file phẳng và mô hình phân tích. Tách staging giúp mình kiểm tra dữ liệu đã sạch trước khi đẩy vào fact/dimension, và dễ load lại khi cần.

### Phỏng vấn trả lời sao?

Em dùng Docker để dựng PostgreSQL nhanh và tái lập được môi trường. Dữ liệu cleaned được load vào bảng staging trước, rồi mới mô hình hóa, nên nếu logic transform đổi thì chỉ cần load lại staging mà không ảnh hưởng schema phân tích.

## Checkpoint 4: Mô hình hóa star schema (dim + fact)

### Mục tiêu

Từ staging, nạp `dim_location`, `dim_date` và `fact_weather_observation` theo mô hình star schema.

### File liên quan

- `sql/02_create_dimensions.sql`, `sql/03_create_fact_table.sql`: DDL dim/fact.
- `sql/04_load_star_schema.sql`: nạp dim + fact từ staging (chạy mỗi lần pipeline).
- `src/load_postgres.py`: hàm `populate_star_schema()` / `load_to_postgres()`.

### Lệnh chạy

```bat
REM Chạy đầy đủ: extract -> transform -> load (staging + star schema)
python src\main.py --load
```

### Cách kiểm tra đã chạy đúng

```bat
docker exec -it weather_postgres psql -U postgres -d weather_db -c "SELECT COUNT(*) FROM fact_weather_observation;"
```

Số dòng phải > 0. Chạy lại lệnh `--load` lần nữa, số dòng **không tăng trùng** (nhờ ràng buộc `UNIQUE(location_id, observation_time)` và `ON CONFLICT DO NOTHING`).

### Phỏng vấn trả lời sao?

Em thiết kế star schema với 1 bảng fact và 2 dimension (location, date). Script load được viết idempotent bằng `ON CONFLICT DO NOTHING` để cron chạy hằng ngày không sinh dữ liệu trùng — đây là yêu cầu quan trọng của pipeline tự động.

## Checkpoint 5: Tạo mart và truy vấn phân tích

### Mục tiêu

Tạo view tổng hợp để dashboard và phân tích đọc trực tiếp.

### File liên quan

- `sql/05_create_marts.sql`: `mart_daily_weather_summary`, `mart_weekly_weather_summary`.

### Cách kiểm tra đã chạy đúng

```bat
docker exec -it weather_postgres psql -U postgres -d weather_db -c "SELECT * FROM mart_daily_weather_summary;"
```

Kết quả trả về nhiệt độ trung bình/max/min, tổng mưa, độ ẩm trung bình... theo từng thành phố và ngày.

### Phỏng vấn trả lời sao?

Em tách lớp mart bằng view để tính sẵn chỉ số tổng hợp (avg/max/min, tổng mưa). Nhờ đó Power BI chỉ cần đọc mart, vừa đơn giản vừa tách biệt logic nghiệp vụ khỏi tầng trình bày.

## Checkpoint 6: Power BI và tự động hóa bằng Task Scheduler

### Kết nối Power BI

Power BI Desktop → **Get Data** → **PostgreSQL database**:

- Server: `localhost:5432`
- Database: `weather_db`
- Chọn view `mart_daily_weather_summary` (và `mart_weekly_weather_summary`).

Gợi ý biểu đồ: Average Temperature by City, Temperature Trend by Date, Total Rain by Week, Humidity by City, Weather Condition Distribution.

### Tự động hóa hằng ngày (Windows Task Scheduler)

README gốc dùng Linux Cron (`0 7 * * *`). Trên Windows mình dùng `run_pipeline.bat` + Task Scheduler.

Tạo task chạy 7:00 sáng mỗi ngày (chạy trong thư mục project):

```bat
schtasks /Create /SC DAILY /ST 07:00 /TN WeatherPipeline /TR "\"%CD%\run_pipeline.bat\""
```

Kiểm tra / chạy thử / xóa task:

```bat
schtasks /Query  /TN WeatherPipeline
schtasks /Run    /TN WeatherPipeline
schtasks /Delete /TN WeatherPipeline /F
```

Log mỗi lần chạy nằm ở `logs\pipeline.log`.

### Phỏng vấn trả lời sao?

Pipeline được lên lịch tự động: trên Linux dùng Cron, còn trên Windows em dùng Task Scheduler gọi một file `.bat` để kích hoạt venv và chạy `main.py --load`. Toàn bộ extract → transform → load → cập nhật mart diễn ra hằng ngày mà không cần thao tác tay.
