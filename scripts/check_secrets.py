from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 5 * 1024 * 1024
ALLOW_MARKER = "pragma: allowlist secret"


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]


RULES = (
    Rule("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    Rule("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    Rule("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    Rule("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    Rule("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    Rule("smart-email-token", re.compile(r"\bsem_[A-Za-z0-9_-]{32,}\b")),
    Rule("microsoft-refresh-token", re.compile(r"\bM\.[A-Za-z0-9!*_-]{80,}\b")),
    Rule("bearer-token", re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{24,}\b", re.IGNORECASE)),
)


def repository_candidates() -> list[Path]:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git is required for the repository secret scan")
    result = subprocess.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def scan_file(path: Path) -> list[tuple[int, str]]:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        return []
    payload = path.read_bytes()
    if b"\0" in payload:
        return []
    text = payload.decode("utf-8", errors="replace")
    findings: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for rule in RULES:
            if rule.pattern.search(line):
                findings.append((line_number, rule.name))
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan publishable text files for credential patterns")
    parser.add_argument("--path", action="append", type=Path, default=[])
    arguments = parser.parse_args()
    paths = [item.resolve() for item in arguments.path] or repository_candidates()
    findings: list[tuple[Path, int, str]] = []
    for path in paths:
        for line_number, rule_name in scan_file(path):
            findings.append((path, line_number, rule_name))
    if findings:
        for path, line_number, rule_name in findings:
            try:
                display = path.relative_to(ROOT)
            except ValueError:
                display = path
            print(f"potential secret: {display}:{line_number} [{rule_name}]")
        raise SystemExit(1)
    print(f"secret scan passed: {len(paths)} files")


if __name__ == "__main__":
    main()
