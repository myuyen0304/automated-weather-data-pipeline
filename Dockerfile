# Image runtime cho pipeline thời tiết — chạy extract/transform/load + dbt HOÀN TOÀN
# trong Docker, KHÔNG cần Python/venv trên máy host.
#
#   docker compose build pipeline
#   docker compose run --rm pipeline python src/main.py --init-db
#   docker compose run --rm pipeline python src/main.py --load
#   docker compose run --rm pipeline dbt build --project-dir weather_dbt
#   docker compose run --rm tests            # pytest trong container
#
# Khác Dockerfile.airflow: image này KHÔNG có Airflow nên dbt cài THẲNG vào cùng
# môi trường (không cần venv cô lập) — trên python:3.11-slim không có gì để dbt
# đụng pin jinja2/click/pydantic.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    # dbt đọc profiles.yml + dbt_project.yml trong weather_dbt/; ép target/log ra
    # /tmp để không ghi vào layer image ở runtime.
    DBT_PROFILES_DIR=/app/weather_dbt \
    DBT_TARGET_PATH=/tmp/dbt_target \
    DBT_LOG_PATH=/tmp/dbt_logs

# Cài dep trước (tận dụng layer cache). requirements.txt = lõi EL; dbt-postgres =
# tầng mart. Tất cả có wheel sẵn nên không cần trình biên dịch.
COPY requirements.txt weather_dbt/requirements-dbt.txt ./
RUN pip install -r requirements.txt -r requirements-dbt.txt

# Bake code + config bất biến vào image (không mount local lúc chạy). RAW/CLEANED
# đều ghi thẳng MinIO nên KHÔNG cần data/raw, data/cleaned trong image.
COPY src/ ./src/
COPY sql/ ./sql/
COPY tests/ ./tests/
COPY weather_dbt/ ./weather_dbt/
COPY pytest.ini ./pytest.ini
COPY data/cities.csv ./data/cities.csv
COPY data/agriculture/ ./data/agriculture/

# Mặc định in help; ghi đè bằng lệnh sau tên service khi `docker compose run`.
CMD ["python", "src/main.py", "--help"]
