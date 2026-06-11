# Automated Weather Data Pipeline

## Mô tả dự án

**Automated Weather Data Pipeline** là một dự án Data Engineering cơ bản nhưng có đầy đủ các thành phần quan trọng của một pipeline dữ liệu thực tế. Hệ thống được xây dựng để tự động thu thập dữ liệu thời tiết hằng ngày từ **Open-Meteo Forecast API**, lưu trữ dữ liệu gốc, xử lý và chuẩn hóa dữ liệu, nạp vào PostgreSQL, sau đó xây dựng các bảng phân tích để phục vụ dashboard báo cáo.

Project chọn **Open-Meteo API** làm nguồn dữ liệu chính vì API này có thể sử dụng công khai cho forecast/current weather, không cần API key cho use case cơ bản, trả về JSON rõ ràng và hỗ trợ nhiều biến thời tiết như nhiệt độ, độ ẩm, áp suất, mưa, mây che phủ và gió.

Pipeline sử dụng Python để gọi endpoint `https://api.open-meteo.com/v1/forecast` theo tọa độ của từng thành phố. Dữ liệu gốc từ API được lưu vào Raw Zone theo ngày và thành phố để có thể kiểm tra lại hoặc tái xử lý khi cần. Sau đó, dữ liệu được làm sạch, chuẩn hóa định dạng thời gian, đổi tên các trường Open-Meteo về schema phân tích dễ đọc hơn, xử lý giá trị thiếu và chuyển đổi thành dạng bảng trước khi nạp vào PostgreSQL.

Trong PostgreSQL, dữ liệu được tổ chức theo hướng phân tích với mô hình gồm bảng fact và dimension. Các bảng chính gồm `fact_weather_observation`, `dim_location` và `dim_date`. Từ các bảng này, project tạo thêm mart/view để tính toán các chỉ số như nhiệt độ trung bình theo ngày, lượng mưa theo tuần, độ ẩm trung bình theo thành phố, áp suất trung bình và xu hướng tốc độ gió.

Dữ liệu sau khi được xử lý và tổng hợp sẽ được trực quan hóa bằng Power BI. Dashboard giúp người dùng theo dõi xu hướng thời tiết, so sánh dữ liệu giữa các thành phố và phân tích các chỉ số thời tiết quan trọng theo thời gian.

Để hệ thống có thể chạy tự động, pipeline được thiết lập bằng Linux Cron job. Cron job sẽ chạy script chính mỗi ngày để tự động lấy dữ liệu mới, xử lý dữ liệu và cập nhật vào database mà không cần thao tác thủ công.

---

## Mục tiêu dự án

Dự án được xây dựng nhằm thực hành các kỹ năng cốt lõi trong Data Engineering:

- Thu thập dữ liệu từ Open-Meteo Forecast API.
- Gọi API dựa trên tọa độ `latitude` và `longitude` của từng thành phố.
- Xử lý dữ liệu JSON bằng Python.
- Lưu trữ dữ liệu raw để phục vụ kiểm tra và tái xử lý.
- Làm sạch và chuẩn hóa dữ liệu thời tiết.
- Nạp dữ liệu vào PostgreSQL.
- Thiết kế mô hình dữ liệu phục vụ phân tích.
- Viết SQL để tạo bảng fact, dimension và mart.
- Xây dựng dashboard bằng Power BI.
- Tự động hóa pipeline bằng Cron job.

---

## Kiến trúc pipeline

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
Cron Job Automation
```

---

## Tech stack

| Thành phần | Công nghệ |
|---|---|
| Data Source | Open-Meteo Forecast API |
| API Endpoint | `https://api.open-meteo.com/v1/forecast` |
| Programming Language | Python |
| API Ingestion | requests |
| Data Processing | pandas |
| Raw Storage | Local JSON files |
| Database | PostgreSQL |
| Data Modelling | SQL |
| Analytics Mart | SQL View / Table |
| Dashboard | Power BI |
| Automation | Linux Cron job |
| Environment Management | python-dotenv, virtual environment |

---

## Dữ liệu thu thập

Open-Meteo Forecast API yêu cầu tọa độ địa lý. Project cấu hình sẵn danh sách thành phố và tọa độ, ví dụ:

| City | Country | Latitude | Longitude |
|---|---|---:|---:|
| Ho Chi Minh City | Vietnam | 10.8231 | 106.6297 |
| Hanoi | Vietnam | 21.0285 | 105.8542 |
| Da Nang | Vietnam | 16.0544 | 108.2022 |

Ví dụ request cho Ho Chi Minh City:

```text
https://api.open-meteo.com/v1/forecast?latitude=10.8231&longitude=106.6297&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m,is_day&timezone=Asia/Ho_Chi_Minh&forecast_days=1
```

### Trường raw từ Open-Meteo

| Trường Open-Meteo | Mô tả |
|---|---|
| `latitude` | Vĩ độ của địa điểm |
| `longitude` | Kinh độ của địa điểm |
| `timezone` | Múi giờ được dùng trong response |
| `current.time` | Thời điểm ghi nhận |
| `current.temperature_2m` | Nhiệt độ tại độ cao 2m |
| `current.relative_humidity_2m` | Độ ẩm tương đối tại độ cao 2m |
| `current.apparent_temperature` | Nhiệt độ cảm nhận |
| `current.precipitation` | Lượng giáng thủy |
| `current.rain` | Lượng mưa |
| `current.weather_code` | Mã trạng thái thời tiết |
| `current.cloud_cover` | Tỷ lệ mây che phủ |
| `current.pressure_msl` | Áp suất mực nước biển |
| `current.surface_pressure` | Áp suất bề mặt |
| `current.wind_speed_10m` | Tốc độ gió tại độ cao 10m |
| `current.wind_direction_10m` | Hướng gió |
| `current.wind_gusts_10m` | Gió giật |
| `current.is_day` | Có phải ban ngày hay không |

### Schema sau khi transform

| Trường dữ liệu | Mô tả |
|---|---|
| city | Tên thành phố từ file cấu hình |
| country | Quốc gia |
| latitude | Vĩ độ |
| longitude | Kinh độ |
| observation_time | Thời điểm ghi nhận thời tiết |
| temperature | Nhiệt độ |
| humidity | Độ ẩm |
| apparent_temperature | Nhiệt độ cảm nhận |
| pressure_msl | Áp suất mực nước biển |
| surface_pressure | Áp suất bề mặt |
| wind_speed | Tốc độ gió |
| wind_direction | Hướng gió |
| wind_gusts | Gió giật |
| precipitation | Lượng giáng thủy |
| rain | Lượng mưa |
| cloud_cover | Mức độ mây che phủ |
| weather_code | Mã điều kiện thời tiết của Open-Meteo |
| weather_condition | Mô tả điều kiện thời tiết được map từ `weather_code` |
| is_day | Có phải ban ngày hay không |
| inserted_at | Thời điểm dữ liệu được nạp vào hệ thống |

---

## Data modelling

Dự án sử dụng mô hình dữ liệu dạng Star Schema đơn giản để phục vụ phân tích.

```text
dim_location
      |
      |
fact_weather_observation ---- dim_date
```

### fact_weather_observation

Bảng fact lưu các chỉ số đo lường thời tiết.

Ví dụ:

- temperature
- humidity
- apparent_temperature
- pressure_msl
- surface_pressure
- wind_speed
- wind_direction
- wind_gusts
- precipitation
- rain
- cloud_cover
- weather_code
- weather_condition

### dim_location

Bảng dimension lưu thông tin địa điểm.

Ví dụ:

- city
- country
- latitude
- longitude

### dim_date

Bảng dimension lưu thông tin ngày tháng để phân tích theo thời gian.

Ví dụ:

- full_date
- day
- month
- quarter
- year
- day_of_week
- is_weekend

---

## Analytics mart

Sau khi có fact và dimension, project tạo bảng mart để phục vụ dashboard.

Ví dụ mart:

- `mart_daily_weather_summary`
- `mart_weekly_weather_summary`

Chỉ số có thể tính:

- Nhiệt độ trung bình theo ngày.
- Nhiệt độ cao nhất và thấp nhất.
- Nhiệt độ cảm nhận trung bình.
- Tổng lượng mưa theo ngày hoặc theo tuần.
- Độ ẩm trung bình theo thành phố.
- Áp suất trung bình.
- Tốc độ gió trung bình.
- Mức độ mây che phủ trung bình.
- Tần suất xuất hiện của từng `weather_condition`.

---

## Dashboard

Dashboard Power BI có thể gồm các biểu đồ:

| Biểu đồ | Mục đích |
|---|---|
| Average Temperature by City | So sánh nhiệt độ trung bình giữa các thành phố |
| Temperature Trend by Date | Theo dõi xu hướng nhiệt độ theo thời gian |
| Total Rain by Week | Phân tích lượng mưa theo tuần |
| Humidity by City | So sánh độ ẩm giữa các thành phố |
| Wind Speed Trend | Theo dõi biến động tốc độ gió |
| Pressure Trend | Theo dõi xu hướng áp suất |
| Weather Condition Distribution | Phân tích tần suất các trạng thái thời tiết |

---

## Automation

Pipeline được tự động hóa bằng Linux Cron job.

Ví dụ chạy pipeline mỗi ngày lúc 7 giờ sáng:

```bash
0 7 * * * /usr/bin/python3 /home/user/automated-weather-data-pipeline/src/main.py
```

File `main.py` sẽ điều phối toàn bộ pipeline:

```python
from extract_weather import extract_all_cities
from transform_weather import transform_raw_files
from load_postgres import load_to_postgres

def main():
    extract_all_cities()
    transform_raw_files()
    load_to_postgres()

if __name__ == "__main__":
    main()
```

---

## Cấu hình môi trường

Vì Open-Meteo Forecast API không cần API key cho use case này, file `.env` chỉ cần các thông tin cấu hình API base URL, timezone và PostgreSQL.

Ví dụ:

```text
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1/forecast
WEATHER_TIMEZONE=Asia/Ho_Chi_Minh

DB_HOST=localhost
DB_PORT=5432
DB_NAME=weather_db
DB_USER=postgres
DB_PASSWORD=postgres
```

---

## Kết quả đầu ra

Sau khi hoàn thành, project tạo ra các kết quả sau:

- Dữ liệu thời tiết raw dạng JSON từ Open-Meteo.
- Dữ liệu raw được lưu theo ngày và thành phố trong `data/raw/open-meteo/`.
- Dữ liệu thời tiết đã được làm sạch.
- Bảng staging trong PostgreSQL.
- Mô hình dữ liệu gồm fact và dimension.
- Bảng mart phục vụ phân tích.
- Dashboard Power BI.
- Pipeline chạy tự động hằng ngày bằng Cron job.

---

## Giá trị của dự án

Dự án này giúp thể hiện các kỹ năng Data Engineering nền tảng:

- API data ingestion với Open-Meteo.
- Xử lý JSON response có cấu trúc nested.
- ETL pipeline development.
- Raw data storage.
- Data cleaning.
- PostgreSQL database design.
- SQL data modelling.
- Star schema design.
- SQL analytics.
- Dashboard reporting.
- Workflow automation.

Đây là project phù hợp cho beginner muốn xây dựng portfolio Data Engineering vì phạm vi vừa đủ, không quá phức tạp nhưng vẫn thể hiện được tư duy pipeline end-to-end.
