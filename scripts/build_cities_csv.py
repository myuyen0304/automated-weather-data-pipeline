"""build_cities_csv.py — tiện ích CHẠY MỘT LẦN để sinh data/cities.csv.

Gọi Open-Meteo Geocoding API lấy tọa độ cho 34 tỉnh/thành Việt Nam, rồi ghi ra
data/cities.csv đúng định dạng mà src/config.py mong đợi
(các cột: city, country, latitude, longitude).

VÌ SAO TRA THEO TỈNH LỴ, KHÔNG THEO TÊN TỈNH:
    Geocoding chỉ trả về nơi có dân TRÙNG ĐÚNG CHỮ với từ khóa. Nhiều tỉnh cótỉnh lỵ tên khác hẳn (Nghệ An -> Vinh, Gia Lai -> Pleiku, Khánh Hòa -> Nha Trang...). Tra thẳng "Gia Lai" sẽ không ra, hoặc tệ hơn là dính một xã nhỏ trùng tên ở tỉnh khác -> tọa độ sai. Nên ta tra theo THÀNH PHỐ TỈNH LỴ (điểm đại diện cho tỉnh) nhưng vẫn ghi TÊN TỈNH vào cột `city`.

ĐÂY KHÔNG phải một phần của pipeline hằng ngày. Tọa độ tỉnh gần như không đổi, nên chỉ chạy lại khi muốn đổi danh sách tỉnh. Sau khi sinh xong, hãy commit data/cities.csv vào git.

Cách chạy (từ thư mục gốc project):
    python scripts/build_cities_csv.py

LƯU Ý: script ghi đè data/cities.csv. Nếu đã chỉnh tay file đó, hãy sao lưu trước.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "cities.csv"

REQUEST_DELAY_SECONDS = 1.0   # lịch sự với API miễn phí (nghỉ giữa các tỉnh)
REQUEST_TIMEOUT = 60          # mạng có lúc chậm -> để rộng tay
MAX_RETRIES = 3              # thử lại khi timeout/lỗi mạng

# (Tên tỉnh để ghi vào cột `city`,  Từ khóa geocode = thành phố tỉnh lỵ).
# Tên tỉnh KHÔNG DẤU vì cột `city` sẽ được slugify thành tên file raw
# (xem src/extract_weather.py: slugify_city) và phải là khóa duy nhất.
# 34 đơn vị sau sáp nhập 2025 = 6 thành phố trực thuộc TW + 28 tỉnh.
PROVINCES: list[tuple[str, str]] = [
    # 6 thành phố trực thuộc trung ương: tra bằng chính tên nó
    ("Hanoi", "Hanoi"),
    ("Hai Phong", "Hai Phong"),
    ("Hue", "Hue"),
    ("Da Nang", "Da Nang"),
    ("Ho Chi Minh City", "Ho Chi Minh City"),
    ("Can Tho", "Can Tho"),
    # 28 tỉnh: tra bằng thành phố tỉnh lỵ
    ("Tuyen Quang", "Tuyen Quang"),
    ("Lao Cai", "Lao Cai"),
    ("Thai Nguyen", "Thai Nguyen"),
    ("Phu Tho", "Viet Tri"),
    ("Bac Ninh", "Bac Ninh"),
    ("Hung Yen", "Hung Yen"),
    ("Ninh Binh", "Ninh Binh"),
    ("Quang Ninh", "Ha Long"),
    ("Cao Bang", "Cao Bang"),
    ("Lang Son", "Lang Son"),
    ("Lai Chau", "Lai Chau"),
    ("Dien Bien", "Dien Bien Phu"),
    ("Son La", "Son La"),
    ("Thanh Hoa", "Thanh Hoa"),
    ("Nghe An", "Vinh"),
    ("Ha Tinh", "Ha Tinh"),
    ("Quang Tri", "Dong Ha"),
    ("Quang Ngai", "Quang Ngai"),
    ("Gia Lai", "Pleiku"),
    ("Khanh Hoa", "Nha Trang"),
    ("Lam Dong", "Da Lat"),
    ("Dak Lak", "Buon Ma Thuot"),
    ("Dong Nai", "Bien Hoa"),
    ("Tay Ninh", "Tay Ninh"),
    ("Vinh Long", "Vinh Long"),
    ("Dong Thap", "Cao Lanh"),
    ("An Giang", "Long Xuyen"),
    ("Ca Mau", "Ca Mau"),
]

# Tọa độ điền tay cho vài tỉnh geocoding không trị được:
#   - Hai Phong: API trả rỗng (không index tốt) dù là thành phố lớn.
#   - Quang Tri: tra 'Dong Ha' bị khớp nhầm một "Dong Ha" ở Khánh Hòa.
# Khi tỉnh có trong bảng này, ta DÙNG LUÔN tọa độ ở đây, bỏ qua gọi API.
MANUAL_OVERRIDES: dict[str, tuple[float, float]] = {
    "Hai Phong": (20.8449, 106.6881),   # trung tâm TP Hải Phòng
    "Quang Tri": (16.8163, 107.1003),   # TP Đông Hà, tỉnh lỵ Quảng Trị
}

# Hộp bao Việt Nam để chặn tọa độ rõ ràng sai (nằm ngoài lãnh thổ).
VN_LAT_RANGE = (8.0, 23.5)
VN_LON_RANGE = (102.0, 110.0)


def geocode(query: str) -> dict | None:
    """Tra tọa độ cho một từ khóa (thành phố tỉnh lỵ). Có retry khi lỗi mạng.

    Lọc chỉ lấy kết quả ở Việt Nam, ưu tiên nơi đông dân nhất (tránh nhầm xã/
    huyện trùng tên), và kiểm tra tọa độ nằm trong hộp bao Việt Nam.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                GEOCODING_URL,
                params={"name": query, "count": 10, "language": "en",
                        "format": "json"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                wait = 2 * attempt  # backoff tăng dần: 2s, 4s
                print(f"        (thu lai {attempt}/{MAX_RETRIES} sau {wait}s: {query})")
                time.sleep(wait)
            else:
                raise last_error
    else:  # pragma: no cover - vòng lặp luôn break hoặc raise
        return None

    vn_results = [
        r for r in results
        if r.get("country_code") == "VN"
        and VN_LAT_RANGE[0] <= r.get("latitude", 0) <= VN_LAT_RANGE[1]
        and VN_LON_RANGE[0] <= r.get("longitude", 0) <= VN_LON_RANGE[1]
    ]
    if not vn_results:
        return None

    best = max(vn_results, key=lambda r: r.get("population") or 0)
    return {
        "latitude": best["latitude"],
        "longitude": best["longitude"],
        "resolved_name": best.get("name", query),
    }


def main() -> None:
    # Console Windows mặc định là cp1252, không in được tên có dấu (vd "Huế")
    # mà Geocoding API trả về. Ép stdout sang UTF-8 để khỏi crash khi print.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    rows: list[dict[str, object]] = []
    missing: list[str] = []

    for label, query in PROVINCES:
        # Ưu tiên tọa độ điền tay nếu có (bỏ qua API cho các ca cứng đầu).
        if label in MANUAL_OVERRIDES:
            lat, lon = MANUAL_OVERRIDES[label]
            rows.append(
                {"city": label, "country": "Vietnam",
                 "latitude": lat, "longitude": lon}
            )
            print(f"[FIX  ] {label:18s} -> {lat:.4f}, {lon:.4f}  (dien tay)")
            continue

        try:
            hit = geocode(query)
        except requests.RequestException as exc:
            print(f"[LOI ] {label} (tra '{query}'): {exc}", file=sys.stderr)
            missing.append(label)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        if hit is None:
            print(f"[?    ] Khong tim thay o VN: {label} (tra '{query}')")
            missing.append(label)
        else:
            rows.append(
                {
                    "city": label,  # luôn ghi TÊN TỈNH, không phải tên tỉnh lỵ
                    "country": "Vietnam",
                    "latitude": round(float(hit["latitude"]), 4),
                    "longitude": round(float(hit["longitude"]), 4),
                }
            )
            note = "" if query == label else f"  (qua tinh ly '{query}')"
            print(
                f"[OK   ] {label:18s} -> "
                f"{hit['latitude']:.4f}, {hit['longitude']:.4f} "
                f"({hit['resolved_name']}){note}"
            )

        time.sleep(REQUEST_DELAY_SECONDS)

    if not rows:
        print("Khong lay duoc tinh nao — khong ghi file.", file=sys.stderr)
        sys.exit(1)

    if missing:
        print(
            f"Khong ghi file vi con thieu {len(missing)} tinh/thanh: "
            f"{', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(rows) != len(PROVINCES):
        print(
            f"Khong ghi file vi chi co {len(rows)}/{len(PROVINCES)} dong.",
            file=sys.stderr,
        )
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=["city", "country", "latitude", "longitude"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDa ghi {len(rows)}/{len(PROVINCES)} tinh vao {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
