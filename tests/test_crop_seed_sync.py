"""Guard: KNOWN_CROPS (data_quality.py) phải khớp ĐÚNG seed dim_crop (sql/06).

DQ chạy thuần pandas TRƯỚC khi nạp DB nên không query được dim_crop -> KNOWN_CROPS
phải hardcode tay. Nếu thêm/bớt cây ở sql/06 mà quên cập nhật set này thì:
  - cây MỚI trong dim_crop nhưng thiếu ở KNOWN_CROPS -> mapping trỏ tới nó bị DQ gate
    chặn oan (validate_agri_region_mapping báo "unknown crop");
  - cây bị BỚT ở sql/06 nhưng còn trong KNOWN_CROPS -> mapping qua được DQ rồi JOIN
    rỗng ở mart_irrigation_need (lỗi im lặng).
Test này parse trực tiếp INSERT INTO dim_crop trong sql/06 và assert set-equality,
biến drift im lặng thành lỗi CI đỏ.
"""

from __future__ import annotations

import re
from pathlib import Path

from data_quality import KNOWN_CROPS

SQL_FILE = (
    Path(__file__).resolve().parents[1]
    / "sql"
    / "06_create_agriculture_schema.sql"
)


def _seeded_crops_from_sql() -> set[str]:
    """Trích tên crop từ INSERT INTO dim_crop ... VALUES trong sql/06.

    Chỉ quét đúng câu lệnh INSERT INTO dim_crop (bao tới câu INSERT kế tiếp, vd
    dim_agri_region) để không nhặt nhầm crop ở câu lệnh khác. KHÔNG cắt theo dấu ;
    vì chuỗi nguồn có chứa ; (vd '...(chọn 0.95, cà phê có ground cover); cây lâu
    năm...'). Mỗi tuple bắt đầu bằng ('<crop>', <kc-số> nên match ( '<crop>' , <số>
    — chuỗi nguồn dạng (chọn 0.95...) không có dấu nháy ngay sau ( nên không nhặt nhầm;
    các dòng dim_agri_region là ('Hanoi', 'Red River Delta', 'rice'...) cũng không khớp
    vì sau tên đầu là chuỗi, không phải số.
    """
    sql = SQL_FILE.read_text(encoding="utf-8")

    start = sql.find("INSERT INTO dim_crop")
    assert start != -1, "không tìm thấy INSERT INTO dim_crop trong sql/06"
    next_insert = sql.find("INSERT INTO", start + len("INSERT INTO dim_crop"))
    end = next_insert if next_insert != -1 else len(sql)
    block = sql[start:end]

    crops = set(re.findall(r"\(\s*'([a-z_]+)'\s*,\s*[0-9]", block))
    assert crops, "không parse được crop nào từ INSERT INTO dim_crop"
    return crops


def test_known_crops_matches_dim_crop_seed() -> None:
    seeded = _seeded_crops_from_sql()

    missing_in_known = seeded - KNOWN_CROPS
    extra_in_known = KNOWN_CROPS - seeded

    assert not missing_in_known, (
        "Cây có trong dim_crop (sql/06) nhưng THIẾU ở KNOWN_CROPS "
        f"(data_quality.py): {sorted(missing_in_known)}"
    )
    assert not extra_in_known, (
        "Cây có trong KNOWN_CROPS (data_quality.py) nhưng KHÔNG được seed ở "
        f"dim_crop (sql/06): {sorted(extra_in_known)}"
    )
