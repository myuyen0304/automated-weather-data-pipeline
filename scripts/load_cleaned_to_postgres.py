from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from load_postgres import load_to_postgres  # noqa: E402


def main() -> None:
    load_to_postgres()


if __name__ == "__main__":
    main()
