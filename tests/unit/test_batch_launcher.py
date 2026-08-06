from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
SINGLE_BATCH = PROJECT / "\u5355\u671f\u6293\u53d6.bat"


def test_single_batch_uses_cmd_compatible_line_endings() -> None:
    data = SINGLE_BATCH.read_bytes()

    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_single_batch_invalid_input_stays_in_cmd_and_returns_error() -> None:
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", f"call {SINGLE_BATCH.name}"],
        cwd=PROJECT,
        input=b"abc\r\nx\r\n",
        capture_output=True,
        timeout=20,
        check=False,
    )
    output = (completed.stdout + completed.stderr).lower()

    assert b"not recognized" not in output
    assert completed.returncode != 0
