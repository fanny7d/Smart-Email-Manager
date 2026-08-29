from __future__ import annotations

import tomllib
from pathlib import Path

from smart_email_manager import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_package_version_license_and_community_files_are_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__
    assert project["license"] == "MIT"
    for filename in (
        "CHANGELOG.md",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "SECURITY.md",
        "SUPPORT.md",
    ):
        assert (ROOT / filename).is_file()
