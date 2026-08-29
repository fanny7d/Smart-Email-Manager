from __future__ import annotations

import json
from pathlib import Path

from smart_email_manager.api.app import app


def main() -> None:
    target = Path("contracts/openapi.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
