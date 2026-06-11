# Checklist lỗi cần sửa sau

File này là bản gộp từ:

- `CHECKLIST_LOI_CAN_SUA.md` ở root repo.
- `docs/CHECKLIST_LOI_CAN_SUA.md`.

Quy ước sau khi gộp: mọi file Markdown tài liệu của project phải nằm trong `docs/`.

## Trạng thái hiện tại

Các lỗi/rủi ro đã được rà soát và đã fix trong codebase hiện tại. File này giữ lại:

- Lý do ban đầu vì sao lỗi/rủi ro được ghi nhận.
- Acceptance criteria từ checklist cũ.
- Trạng thái xử lý mới nhất sau khi fix.
- Các lệnh verification đã chạy.

## Trạng thái kiểm tra gần nhất

- [x] `uv --cache-dir .uv-cache run python src/main.py --help` chạy được.
- [x] `src.config` load được 34 city từ `data/cities.csv`.
- [x] `uv --cache-dir .uv-cache run python src/main.py --skip-extract` transform được cleaned CSV 34 dòng.
- [x] `uv --cache-dir .uv-cache run python src/main.py --skip-extract --date 2026-06-11` transform đúng partition ngày.
- [x] `uv --cache-dir .uv-cache run python src/main.py --skip-extract --all-raw` reprocess được toàn bộ raw history.
- [x] `uv --cache-dir .uv-cache run python src/main.py --skip-extract --load` load được 34 dòng vào PostgreSQL staging.
- [x] `cmd /c run_pipeline.bat` chạy full pipeline và kết thúc `exit=0`.
- [x] PostgreSQL container `weather_postgres` healthy tại thời điểm kiểm tra.
- [x] PostgreSQL counts sau kiểm tra:
  - `stg_weather_observations`: 34
  - `dim_location`: 34
  - `dim_date`: 1
  - `fact_weather_observation`: 109
  - `mart_daily_weather_summary`: 34
  - `mart_weekly_weather_summary`: 34

## Lỗi/rủi ro đã fix

### 1. Chặn combo CLI sai: `--extract-only --load`

- [x] Đã sửa `src/main.py` để không cho phép chạy đồng thời `--extract-only` và `--load`.
- File liên quan: `src/main.py`
- Vấn đề ban đầu: `--extract-only` bỏ qua transform, nhưng `--load` vẫn có thể load file cleaned CSV cũ.
- Acceptance criteria:
  - [x] Chạy `uv --cache-dir .uv-cache run python src/main.py --extract-only --load` fail sớm với message rõ ràng.
  - [x] Chạy `uv --cache-dir .uv-cache run python src/main.py --extract-only` vẫn chỉ extract.
  - [x] Chạy `uv --cache-dir .uv-cache run python src/main.py --load` vẫn chạy extract -> transform -> load.
- Verification:
  - `uv --cache-dir .uv-cache run python src/main.py --extract-only --load` fail sớm với parser error.
  - `uv --cache-dir .uv-cache run python src/main.py --help` hiển thị option hợp lệ.

### 2. Validate schema CSV trước khi load PostgreSQL

- [x] Đã sửa `src/load_postgres.py` để kiểm tra đủ cột bắt buộc trước khi load.
- File liên quan: `src/load_postgres.py`
- Vấn đề ban đầu: code chỉ lấy các cột tồn tại; nếu CSV thiếu cột quan trọng như `city`, `observation_time`, `temperature`, lỗi có thể xảy ra muộn hoặc load dữ liệu sai.
- Acceptance criteria:
  - [x] Nếu CSV thiếu cột trong `STAGING_COLUMNS`, pipeline raise lỗi rõ danh sách cột thiếu.
  - [x] Nếu CSV đủ schema, load vẫn thành công.
- Verification:
  - File CSV thiếu cột bị chặn với lỗi `Cleaned CSV is missing required staging columns`.
  - CSV đủ schema vẫn load thành công vào staging.

### 3. Chỉ transform batch raw cần thiết

- [x] Đã sửa `src/transform_weather.py` và `src/main.py` để không mặc định transform toàn bộ raw history mỗi lần.
- File liên quan: `src/transform_weather.py`, `src/main.py`
- Vấn đề ban đầu: `raw_dir.rglob("*.json")` đọc mọi raw JSON trong `data/raw/open-meteo`, dễ làm cleaned CSV phình to và fail nếu raw cũ không còn khớp city config.
- Cách hoạt động hiện tại:
  - Full run mới: transform đúng raw files vừa extract.
  - `--skip-extract`: transform folder ngày mới nhất.
  - `--date YYYY-MM-DD`: transform một partition ngày cụ thể.
  - `--all-raw`: reprocess toàn bộ raw history khi cần.
- Acceptance criteria:
  - [x] Một lần run daily chỉ transform batch mong muốn.
  - [x] Vẫn có cách reprocess toàn bộ lịch sử khi cần.
- Verification:
  - `uv --cache-dir .uv-cache run python src/main.py --skip-extract` chạy được.
  - `uv --cache-dir .uv-cache run python src/main.py --skip-extract --date 2026-06-11` chạy được.
  - `uv --cache-dir .uv-cache run python src/main.py --skip-extract --all-raw` chạy được.

### 4. Làm `scripts/build_cities_csv.py` fail nếu thiếu tỉnh/thành

- [x] Đã sửa script build city để không ghi file partial như thể thành công.
- File liên quan: `scripts/build_cities_csv.py`
- Vấn đề ban đầu: nếu geocoding chỉ lấy được một phần danh sách, script vẫn ghi `data/cities.csv` và exit success.
- Trạng thái hiện tại:
  - Nếu `missing` không rỗng, script exit non-zero trước khi ghi file.
  - Nếu số dòng không đủ `PROVINCES`, script exit non-zero trước khi ghi file.
- Acceptance criteria:
  - [x] Nếu `missing` không rỗng, script exit non-zero.
  - [x] Output báo danh sách tỉnh/thành thiếu.
  - [x] `data/cities.csv` chỉ được coi là hợp lệ khi đủ 34 dòng.

### 5. Không ignore toàn bộ `docs/`

- [x] Đã sửa `.gitignore` để không ignore toàn bộ thư mục `docs/`.
- File liên quan: `.gitignore`
- Vấn đề ban đầu: các file học/giải thích trong `docs/` bị ignore, dễ mất tài liệu portfolio.
- Trạng thái hiện tại:
  - `docs/` có thể được Git track.
  - Các file local/runtime như `.env`, `.venv/`, `.uv-cache/`, `data/raw/`, `data/cleaned/`, `logs/` vẫn nên bị ignore.
- Acceptance criteria:
  - [x] `docs/GIAI_THICH_CODE.md`, `docs/HANDS_ON_PIPELINE.md`, `docs/PIPELINE_STATUS_EXPLAINED.md` có thể được Git track.
  - [x] Chỉ ignore các file local/private nếu thật sự cần.

### 6. Làm `run_pipeline.bat` chạy ổn với môi trường `uv`

- [x] Đã sửa `run_pipeline.bat` để dùng môi trường rõ ràng hơn.
- File liên quan: `run_pipeline.bat`
- Vấn đề ban đầu: batch file chạy `python src\main.py --load`; Task Scheduler có thể dùng nhầm Python nếu virtualenv không activate đúng.
- Cách hoạt động hiện tại:
  - Ưu tiên `.venv\Scripts\python.exe`.
  - Nếu không có, dùng `venv\Scripts\python.exe`.
  - Nếu không có virtualenv, fallback sang `uv --cache-dir .uv-cache run python`.
  - Ghi exit code vào `logs/pipeline.log` và trả đúng exit code cho Task Scheduler.
- Acceptance criteria:
  - [x] Chạy trực tiếp `run_pipeline.bat` từ project root thành công.
  - [x] Log ghi rõ start/end và exit code.
  - [x] Nếu DB chưa sẵn sàng, log báo lỗi qua output pipeline.
- Verification:
  - `cmd /c run_pipeline.bat` chạy sạch console và log kết thúc với `exit=0`.

## Việc còn nên làm sau

- [ ] Chạy full live pipeline `uv --cache-dir .uv-cache run python src/main.py --load` khi muốn lấy dữ liệu mới từ Open-Meteo.
- [ ] Commit các file docs nếu muốn dùng repo làm portfolio.
- [ ] Cân nhắc thêm test tự động cho CLI guard, schema validation và transform partition.
- [ ] Khi cần dashboard đẹp hơn, tích lũy 7-30 ngày dữ liệu bằng `run_pipeline.bat` hoặc Windows Task Scheduler.

