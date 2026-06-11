# UPGRADE.md

File này ghi lại câu hỏi nâng cấp gần nhất và giải pháp đề xuất cho project `automated-weather-data-pipeline`.

## Câu hỏi

Làm sao để lưu dữ liệu nhiều ngày để làm dashboard Power BI đẹp hơn?

## Trả lời ngắn

Pipeline hiện tại đã có nền tảng để lưu dữ liệu nhiều ngày trong PostgreSQL:

- Mỗi lần chạy `src/main.py --load`, pipeline extract dữ liệu mới từ Open-Meteo, transform thành CSV sạch, rồi load vào database.
- Bảng `stg_weather_observations` chỉ là buffer cho batch hiện tại, nên nó bị `TRUNCATE` trước mỗi lần load.
- Bảng `fact_weather_observation` là nơi giữ lịch sử nhiều ngày.
- Fact table có unique key theo `(location_id, observation_time)`, nên chạy lại cùng một mốc thời gian sẽ không tạo dòng trùng.
- Mart daily/weekly sẽ đọc từ fact table để phục vụ dashboard.

Vì vậy, để dashboard có trend đẹp, cách đúng là chạy pipeline đều đặn hằng ngày và để fact table tích lũy dữ liệu.

## Cách làm ngay, chưa cần sửa code

### 1. Khởi tạo database một lần

Chạy PostgreSQL bằng Docker:

```bash
docker compose up -d
```

Tạo schema:

```bash
uv --cache-dir .uv-cache run python src/main.py --init-db
```

### 2. Chạy pipeline full load mỗi ngày

Chạy thủ công:

```bash
uv --cache-dir .uv-cache run python src/main.py --load
```

Lệnh này sẽ chạy đủ:

```text
Open-Meteo API -> raw JSON -> cleaned CSV -> staging -> star schema -> marts
```

### 3. Dùng Windows Task Scheduler để chạy tự động

Repo đã có `run_pipeline.bat`. Có thể tạo task chạy mỗi ngày lúc 07:00:

```bash
schtasks /Create /SC DAILY /ST 07:00 /TN WeatherPipeline /TR "\"D:\automated-weather-data-pipeline\run_pipeline.bat\""
```

Sau đó kiểm tra log:

```text
logs/pipeline.log
```

Nếu log kết thúc bằng:

```text
Ket thuc pipeline (exit=0)
```

thì pipeline chạy thành công.

## Cách kiểm tra dữ liệu đang tích lũy

Sau vài ngày chạy, kiểm tra số dòng theo ngày trong fact table:

```sql
SELECT
    d.full_date,
    COUNT(*) AS observation_count
FROM fact_weather_observation f
JOIN dim_date d ON d.date_id = f.date_id
GROUP BY d.full_date
ORDER BY d.full_date;
```

Với 34 tỉnh/thành, nếu chạy 1 lần mỗi ngày thì kỳ vọng khoảng:

```text
34 observations / day
```

Ví dụ:

```text
7 ngày  -> khoảng 238 dòng fact
30 ngày -> khoảng 1020 dòng fact
```

Số dòng thực tế có thể khác nếu:

- Có ngày pipeline không chạy.
- API lỗi ở một vài city.
- Chạy nhiều lần trong ngày và `observation_time` khác nhau.

## Dashboard sẽ đẹp hơn khi có bao nhiêu ngày data?

Mốc thực tế:

| Thời lượng dữ liệu | Dashboard làm được gì |
|---|---|
| 1 ngày | Overview, city comparison, map, current snapshot |
| 7 ngày | Trend cơ bản theo ngày, weekly rain, biến động nhiệt độ/độ ẩm |
| 30 ngày | Dashboard nhìn thuyết phục hơn, so sánh tuần, pattern mưa/nắng rõ hơn |
| 90 ngày trở lên | Có thể phân tích mùa vụ nhẹ, anomaly, top city theo giai đoạn |

Với portfolio project, mục tiêu hợp lý là tích lũy tối thiểu 7-30 ngày.

## Lưu ý quan trọng về raw data hiện tại

Code hiện tại lưu raw JSON theo dạng:

```text
data/raw/open-meteo/date=YYYY-MM-DD/<city>.json
```

Điều này ổn nếu pipeline chỉ chạy 1 lần mỗi ngày.

Nhưng nếu chạy nhiều lần trong cùng một ngày, file raw của cùng city sẽ bị ghi đè, vì tên file chỉ có city và date.

Ví dụ:

```text
data/raw/open-meteo/date=2026-06-11/ho_chi_minh_city.json
```

Nếu chạy lúc 07:00 rồi chạy lại lúc 12:00, raw JSON 12:00 có thể ghi đè raw JSON 07:00.

PostgreSQL fact table vẫn có thể giữ nhiều observation nếu `observation_time` khác nhau, nhưng raw landing zone thì chưa giữ được nhiều bản trong cùng ngày.

## Nâng cấp nên làm nếu muốn lưu nhiều lần trong ngày

Nếu muốn dashboard intraday, ví dụ theo giờ, nên đổi raw path thành dạng có timestamp hoặc hour partition.

Gợi ý:

```text
data/raw/open-meteo/date=YYYY-MM-DD/run_at=HHmmss/<city>.json
```

hoặc:

```text
data/raw/open-meteo/date=YYYY-MM-DD/hour=HH/<city>.json
```

Khi đó cần sửa:

- `src/extract_weather.py`
  - `save_raw_weather_response()`
  - thêm `run_timestamp` hoặc `run_hour` vào folder output
- `src/transform_weather.py`
  - đảm bảo transform có thể đọc raw files nằm sâu hơn 1 cấp
- Docs
  - cập nhật README, `GIAI_THICH_CODE.md`, `PIPELINE_STATUS_EXPLAINED.md`

## Nâng cấp nếu muốn backfill dữ liệu quá khứ

Pipeline hiện tại dùng Open-Meteo Forecast API cho current weather.

Điểm giới hạn:

- Nếu hôm nay mới bắt đầu chạy, pipeline không tự lấy lại dữ liệu current weather của các ngày đã bỏ lỡ.
- Muốn có dữ liệu lịch sử, cần thêm một extractor riêng dùng Open-Meteo historical/archive endpoint.

Backlog nâng cấp:

- Tạo `src/backfill_weather.py`.
- Nhận tham số:

```bash
uv --cache-dir .uv-cache run python src/backfill_weather.py --start-date 2026-06-01 --end-date 2026-06-10
```

- Lưu raw theo ngày:

```text
data/raw/open-meteo/date=YYYY-MM-DD/<city>.json
```

- Transform và load lại bằng:

```bash
uv --cache-dir .uv-cache run python src/main.py --skip-extract --all-raw --load
```

Trước khi implement backfill, cần kiểm tra lại Open-Meteo historical API docs vì endpoint và field có thể khác Forecast API.

## Khuyến nghị cho project hiện tại

Ưu tiên theo thứ tự:

1. Chạy `run_pipeline.bat` hằng ngày bằng Windows Task Scheduler.
2. Tích lũy ít nhất 7 ngày data trong PostgreSQL.
3. Làm Power BI dashboard từ `mart_daily_weather_summary` và `mart_weekly_weather_summary`.
4. Sau khi dashboard chạy ổn, mới nâng cấp intraday raw storage nếu muốn phân tích theo giờ.
5. Nếu cần demo nhanh mà không chờ 7-30 ngày, implement historical backfill bằng Open-Meteo archive endpoint.

## Câu giải thích để phỏng vấn

Có thể nói:

```text
Pipeline của em lưu lịch sử ở fact table trong PostgreSQL, không lưu lịch sử ở staging.
Mỗi lần pipeline chạy, staging được truncate để chỉ chứa batch mới nhất, sau đó dữ liệu được merge vào star schema.
Fact table có unique constraint theo location và observation_time nên tránh duplicate khi chạy lại.
Để dashboard có trend, em dùng scheduler chạy pipeline hằng ngày và Power BI đọc từ mart daily/weekly.
Nếu cần dữ liệu quá khứ trước ngày bắt đầu chạy pipeline, em sẽ thêm backfill job dùng Open-Meteo historical/archive API.
```

