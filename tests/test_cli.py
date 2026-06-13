from __future__ import annotations

import subprocess
import sys


def test_extract_only_cannot_be_combined_with_load() -> None:
    result = subprocess.run(
        [sys.executable, "src/main.py", "--extract-only", "--load"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--extract-only cannot be combined with --load" in result.stderr
