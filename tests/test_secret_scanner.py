from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "check_secrets.py"


def test_secret_scanner_accepts_normal_text_and_rejects_private_key(tmp_path: Path) -> None:
    safe = tmp_path / "safe.txt"
    safe.write_text("SEM_API_TOKEN=replace-with-random-value\n", encoding="utf-8")
    accepted = subprocess.run(
        [sys.executable, str(SCANNER), "--path", str(safe)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0

    unsafe = tmp_path / "unsafe.txt"
    unsafe.write_text("-----BEGIN " + "PRIVATE KEY-----\n", encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, str(SCANNER), "--path", str(unsafe)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 1
    assert "private-key" in rejected.stdout
    assert "BEGIN PRIVATE KEY" not in rejected.stdout
