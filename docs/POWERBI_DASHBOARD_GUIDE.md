# Power BI Dashboard Guide

File này ghi lại ý tưởng phân tích dashboard và các bước tạo dashboard Power BI cho project `automated-weather-data-pipeline`.

## 1. Mục tiêu dashboard

Dashboard hiện tại nên đi theo hướng:

```text
Daily Weather Monitoring Dashboard for 34 Vietnam provinces/cities
```

Lý do:

- Pipeline hiện lấy dữ liệu current weather từ Open-Meteo.
- Dữ liệu đang có 34 tỉnh/thành từ `data/cities.csv`.
- PostgreSQL đã có staging, star schema và mart daily/weekly.
- Dữ liệu trend dài hạn chưa nhiều, nên chưa nên tập trung forecasting.

Khi scheduler chạy được 7-30 ngày, dashboard có thể mở rộng thành:

```text
Weather Trend Analytics Dashboard
```

## 2. Data source nên dùng trong Power BI

Nên bắt đầu từ các SQL views:

```text
mart_daily_weather_summary
mart_weekly_weather_summary
```

Nếu cần phân tích chi tiết hơn, connect thêm các bảng:

```text
fact_weather_observation
dim_location
dim_date
```

Vai trò từng bảng/view:

| Object | Vai trò |
|---|---|
| `mart_daily_weather_summary` | Tổng hợp thời tiết theo ngày và tỉnh/thành |
| `mart_weekly_weather_summary` | Tổng hợp thời tiết theo tuần và tỉnh/thành |
| `fact_weather_observation` | Dữ liệu observation chi tiết |
| `dim_location` | City, country, latitude, longitude |
| `dim_date` | Date attributes: day, month, quarter, year, weekend |

## 3. Dashboard pages nên có

### Page 1: Overview

Mục tiêu: nhìn nhanh tình hình thời tiết toàn bộ 34 tỉnh/thành.

KPI cards:

- Average Temperature
- Max Temperature
- Min Temperature
- Average Humidity
- Total Rain
- Average Wind Speed
- Number of Locations

Charts:

- Bar chart: average temperature by city
- Bar chart: average humidity by city
- Map visual: city location with temperature or weather condition
- Table: city, temperature, humidity, rain, weather condition

Insight trả lời được:

- Tỉnh/thành nào đang nóng nhất?
- Tỉnh/thành nào có độ ẩm cao?
- Khu vực nào đang có mưa?
- Bức tranh thời tiết hiện tại trên toàn bộ địa điểm như thế nào?

### Page 2: City Comparison

Mục tiêu: so sánh thời tiết giữa các tỉnh/thành.

Charts:

- Top 10 hottest cities
- Top 10 most humid cities
- Top 10 rainiest cities
- Average wind speed by city
- Average cloud cover by city

Suggested visuals:

- Clustered bar chart
- Sorted table
- Conditional formatting table

Insight trả lời được:

- Thành phố nào nóng nhất hôm nay?
- Thành phố nào ẩm nhất?
- Thành phố nào có lượng mưa cao nhất?
- Nơi nào có gió mạnh hơn các nơi khác?

### Page 3: Trend

Mục tiêu: phân tích biến động theo thời gian.

Charts:

- Line chart: average temperature trend by date
- Line chart: average humidity trend by date
- Column chart: total rain by week
- Line chart: average wind speed trend

Lưu ý:

- Page này chỉ thật sự có ý nghĩa khi pipeline chạy nhiều ngày.
- Nếu mới có 1 ngày dữ liệu, trend chart sẽ chưa đẹp.

Insight trả lời được:

- Nhiệt độ tăng/giảm qua các ngày như thế nào?
- Độ ẩm thay đổi ra sao?
- Tuần nào có mưa nhiều hơn?
- Gió có xu hướng mạnh lên hay yếu đi?

### Page 4: Weather Condition

Mục tiêu: phân tích phân bố trạng thái thời tiết.

Charts:

- Donut chart: count by weather condition
- Bar chart: weather condition by city
- Matrix: city x weather condition
- Filter/slicer: date, city, condition

Insight trả lời được:

- Bao nhiêu tỉnh/thành đang Clear sky?
- Bao nhiêu tỉnh/thành đang Overcast?
- Khu vực nào đang có rain showers?

## 4. Layout gợi ý cho trang Overview

```text
┌──────────────────────────────────────────────────────────────┐
│ KPI Cards: Avg Temp | Max Temp | Avg Humidity | Total Rain   │
├──────────────────────────────┬───────────────────────────────┤
│ Vietnam Map                  │ Avg Temperature by City        │
│ latitude / longitude         │ bar chart                      │
├──────────────────────────────┼───────────────────────────────┤
│ Top Humid / Rainy Cities     │ Weather Condition Distribution │
│ table or bar chart           │ donut chart                    │
└──────────────────────────────┴───────────────────────────────┘
```

## 5. Các measure nên tạo trong Power BI

Nếu dùng mart daily/weekly, nhiều chỉ số đã có sẵn. Nhưng vẫn nên tạo DAX measures để card/visual dễ dùng.

Ví dụ:

```DAX
Avg Temperature = AVERAGE(mart_daily_weather_summary[avg_temperature])
```

```DAX
Max Temperature = MAX(mart_daily_weather_summary[max_temperature])
```

```DAX
Min Temperature = MIN(mart_daily_weather_summary[min_temperature])
```

```DAX
Avg Humidity = AVERAGE(mart_daily_weather_summary[avg_humidity])
```

```DAX
Total Rain = SUM(mart_daily_weather_summary[total_rain])
```

```DAX
Avg Wind Speed = AVERAGE(mart_daily_weather_summary[avg_wind_speed])
```

```DAX
Location Count = DISTINCTCOUNT(mart_daily_weather_summary[city])
```

Nếu dùng fact table:

```DAX
Observation Count = COUNTROWS(fact_weather_observation)
```

## 6. Các bước tạo dashboard trong Power BI

### Bước 1: Đảm bảo PostgreSQL đang chạy

Trong project root:

```bash
docker compose ps
```

Nếu chưa chạy:

```bash
docker compose up -d
```

Kiểm tra pipeline load được data:

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract --load
```

### Bước 2: Mở Power BI Desktop

Mở Power BI Desktop trên Windows.

Chọn:

```text
Get Data -> Database -> PostgreSQL database
```

### Bước 3: Nhập thông tin kết nối PostgreSQL

Thông tin local hiện tại:

```text
Server: localhost
Database: weather_db
```

Nếu Power BI hỏi port, dùng:

```text
localhost:5432
```

Credential:

```text
Username: postgres
Password: postgres
```

Thông tin này khớp với:

- `docker-compose.yml`
- `.env.example`
- `src/config.py`

### Bước 4: Chọn bảng/view cần load

Nên chọn trước:

```text
mart_daily_weather_summary
mart_weekly_weather_summary
```

Nếu muốn map hoặc phân tích chi tiết, chọn thêm:

```text
dim_location
dim_date
fact_weather_observation
```

Khuyến nghị:

- Load `mart_daily_weather_summary` trước để làm dashboard nhanh.
- Sau đó thêm `dim_location` nếu cần latitude/longitude cho map.

### Bước 5: Kiểm tra model relationship

Nếu chỉ dùng mart views, có thể chưa cần relationship phức tạp.

Nếu dùng fact/dim:

Tạo relationship:

```text
fact_weather_observation[location_id] -> dim_location[location_id]
fact_weather_observation[date_id] -> dim_date[date_id]
```

Cardinality:

```text
Many-to-one (*:1)
```

Cross filter:

```text
Single
```

### Bước 6: Tạo measures

Vào tab:

```text
Modeling -> New measure
```

Tạo các measure trong mục 5:

- Avg Temperature
- Max Temperature
- Min Temperature
- Avg Humidity
- Total Rain
- Avg Wind Speed
- Location Count

### Bước 7: Tạo Overview page

Thêm các KPI cards:

- Avg Temperature
- Max Temperature
- Avg Humidity
- Total Rain
- Location Count

Thêm bar chart:

```text
Axis: city
Values: avg_temperature
Sort: descending
```

Thêm bar chart humidity:

```text
Axis: city
Values: avg_humidity
Sort: descending
```

Thêm table:

```text
city
full_date
avg_temperature
avg_humidity
total_rain
avg_wind_speed
```

### Bước 8: Tạo map visual

Nếu dùng `dim_location`:

Map fields:

```text
Latitude: dim_location[latitude]
Longitude: dim_location[longitude]
Legend: dim_location[city]
Size or color: avg_temperature
```

Nếu Power BI không tự join mart với dim_location, dùng fact/dim model hoặc merge city trong Power Query.

### Bước 9: Tạo City Comparison page

Visuals nên có:

- Top 10 hottest cities
- Top 10 highest humidity cities
- Top 10 rainiest cities
- Average wind speed by city

Cách làm Top 10:

- Dùng bar chart.
- Filter visual-level: Top N = 10.
- By value: Avg Temperature hoặc Total Rain.

### Bước 10: Tạo Trend page

Visuals:

Line chart temperature:

```text
X-axis: full_date
Y-axis: avg_temperature
Legend: city
```

Line chart humidity:

```text
X-axis: full_date
Y-axis: avg_humidity
Legend: city
```

Weekly rain:

```text
X-axis: iso_week
Y-axis: total_rain
Legend: city
```

Lưu ý:

- Nếu data mới có 1 ngày, trend sẽ gần như chưa có ý nghĩa.
- Sau 7-30 ngày scheduler chạy, page này sẽ hữu ích hơn.

### Bước 11: Tạo slicers

Nên thêm slicers:

- Date
- City
- Weather condition nếu dùng fact table

Với mart daily:

```text
full_date
city
```

Với fact:

```text
observation_time
weather_condition
city
```

### Bước 12: Refresh data

Sau khi pipeline chạy mới:

```bash
uv --cache-dir .uv-cache run python src/main.py --load
```

Trong Power BI:

```text
Home -> Refresh
```

Nếu đã publish lên Power BI Service, cần cấu hình gateway để refresh từ PostgreSQL local. Với project portfolio local, refresh trong Power BI Desktop là đủ.

## 7. Insight mẫu để trình bày

Khi demo dashboard, có thể nói:

```text
Dashboard này cho phép theo dõi thời tiết hiện tại của 34 tỉnh/thành Việt Nam.
Em chia dashboard thành overview, city comparison, trend và weather condition.
Dữ liệu được lấy từ Open-Meteo, transform thành cleaned CSV, load vào PostgreSQL,
rồi Power BI đọc từ mart views để giảm logic xử lý ở tầng dashboard.
```

Ví dụ câu hỏi dashboard trả lời được:

- Tỉnh/thành nào đang nóng nhất?
- Tỉnh/thành nào có độ ẩm cao nhất?
- Khu vực nào đang có mưa?
- Nhiệt độ trung bình thay đổi thế nào qua các ngày?
- Tuần nào có tổng lượng mưa cao hơn?

## 8. Việc nên làm trước khi dashboard đẹp

- Chạy pipeline nhiều ngày để có trend thật.
- Đăng ký `run_pipeline.bat` với Windows Task Scheduler.
- Thêm data quality checks trước khi load fact.
- Cân nhắc tạo thêm view cho latest observation nếu dashboard cần current snapshot:

```text
mart_latest_weather_by_city
```

View này sẽ giúp dashboard current weather dễ làm hơn vì mỗi city chỉ lấy observation mới nhất.
