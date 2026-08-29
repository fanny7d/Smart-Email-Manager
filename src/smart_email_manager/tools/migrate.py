from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config


def main() -> None:
    try:
        migration_resources: Any = files("smart_email_manager_migrations")
    except ModuleNotFoundError:
        editable_path = Path(__file__).resolve().parents[3] / "migrations"
        if not editable_path.is_dir():
            raise RuntimeError("packaged Alembic migrations are unavailable") from None
        migration_resources = editable_path
    with as_file(migration_resources) as migration_path:
        config = Config()
        config.set_main_option("script_location", str(migration_path))
        command.upgrade(config, "head")


if __name__ == "__main__":
    main()
