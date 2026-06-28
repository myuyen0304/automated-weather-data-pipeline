# weather_dbt

Tầng **mart** của pipeline, quản bằng dbt. Chỉ thay `sql/05` + `sql/08`; phần
extract/transform/load (fact + dim) GIỮ NGUYÊN ở Python/SQL EL và được dbt đọc qua
`source()`. Bối cảnh & lý do: xem `docs/DBT_CONCEPT_NOTE.md`.

## Cấu trúc

```
weather_dbt/
├── dbt_project.yml                 # profile='weather_dbt', mart mặc định materialized=view
├── profiles.yml                    # kết nối Postgres (env_var, default khớp docker-compose)
├── requirements-dbt.txt            # dbt-postgres (tách khỏi requirements.txt lõi)
└── models/
    ├── sources.yml                 # fact + dim = source (EL nạp, dbt chỉ đọc)
    └── marts/
        ├── mart_daily_weather_summary.sql    # port sql/05
        ├── mart_weekly_weather_summary.sql   # port sql/05
        ├── mart_irrigation_need.sql          # port sql/08, dùng ref(mart_daily)
        └── schema.yml                          # test declarative (not_null, relationships)
```

## Chạy (từ thư mục weather_dbt/)

```powershell
# 1. Cài dbt
pip install -r requirements-dbt.txt

# 2. Postgres weather phải đang chạy (docker compose up -d ở repo root) và đã có
#    fact/dim (python src/main.py --init-db --load ... ) vì dbt chỉ đọc chúng.

# 3. profiles.yml nằm trong project -> luôn truyền --profiles-dir .
dbt debug --profiles-dir .          # phải "Connection test: OK"
dbt run   --profiles-dir .          # dựng 3 mart (dbt tự suy thứ tự qua ref())
dbt test  --profiles-dir .          # chạy test khai báo
dbt docs generate --profiles-dir .  # sinh lineage docs (tùy chọn)
```

## Lưu ý

- dbt đọc **biến môi trường OS**, không tự đọc `.env`. Default trong `profiles.yml`
  khớp `docker-compose.yml` nên local chạy ngay; credential khác thì export trước.
- Mart là **view** (giống bản SQL gốc). Đổi sang `table`/`incremental` bằng cách sửa
  `+materialized` trong `dbt_project.yml` — không cần đụng SQL.
- `mart_irrigation_need` phụ thuộc `mart_daily_weather_summary` qua `ref()`, nên
  `dbt run` tự chạy daily trước. Đây là thứ thay đoạn hardcode `05,08` trong
  `load_postgres.py`.
