from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / ".venv" / "bin"
DATABASE = "smart_email_manager_cli_e2e_test"
API_URL = "http://127.0.0.1:18002"
TEST_MASTER_KEY = "dGVzdC1tYXN0ZXIta2V5LW1hdGVyaWFsLTMyLWJ5dGU="


def command(
    arguments: list[str],
    *,
    environment: dict[str, str],
    parse_json: bool = False,
) -> Any:
    process = subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        rendered = " ".join(arguments)
        detail = (process.stderr or process.stdout).strip()[-1_000:]
        raise RuntimeError(f"command failed ({process.returncode}): {rendered}\n{detail}")
    return json.loads(process.stdout) if parse_json else process.stdout.strip()


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_for_api(environment: dict[str, str]) -> None:
    for _attempt in range(50):
        result = subprocess.run(
            ["curl", "-fsS", f"{API_URL}/api/v1/system/health"],
            env=environment,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.2)
    raise RuntimeError("isolated CLI acceptance API did not become healthy")


def wait_for_job(
    sem: Any,
    job_id: str,
    expected: str,
    *,
    attempts: int = 50,
) -> None:
    observed = ""
    for _attempt in range(attempts):
        observed = sem("jobs", "show", job_id, "--output", "json")["status"]
        if observed == expected:
            return
        time.sleep(0.2)
    raise RuntimeError(f"job {job_id} remained {observed}; expected {expected}")


def main() -> None:
    if not DATABASE.endswith("_test"):
        raise RuntimeError("CLI acceptance database must end in _test")
    base_environment = os.environ.copy()
    base_environment.update(
        {
            "SEM_ENVIRONMENT": "test",
            "SEM_DATABASE_URL": f"postgresql+psycopg:///{DATABASE}",
            "SEM_API_HOST": "127.0.0.1",
            "SEM_API_PORT": "18002",
            "SEM_API_TOKEN": "",
            "SEM_MASTER_KEY": TEST_MASTER_KEY,
            "SEM_MASTER_KEY_VERSION": "2",
        }
    )
    api_process: subprocess.Popen[str] | None = None
    worker_process: subprocess.Popen[str] | None = None
    subprocess.run(["dropdb", "--if-exists", DATABASE], capture_output=True, check=False)
    subprocess.run(["createdb", DATABASE], check=True)
    try:
        command([str(BIN / "sem-migrate")], environment=base_environment)
        with tempfile.TemporaryDirectory(prefix="sem-cli-e2e-") as temporary_directory:
            temporary = Path(temporary_directory)
            config_path = temporary / "config.toml"
            api_log = (temporary / "api.log").open("w", encoding="utf-8")
            try:
                api_process = subprocess.Popen(
                    [str(BIN / "sem-api")],
                    cwd=ROOT,
                    env=base_environment,
                    stdout=api_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_for_api(base_environment)

                def sem(
                    *arguments: str,
                    extra_environment: dict[str, str] | None = None,
                ) -> Any:
                    environment = base_environment.copy()
                    if extra_environment:
                        environment.update(extra_environment)
                    parse_json = "--output" in arguments and "json" in arguments
                    return command(
                        [str(BIN / "sem"), "--config", str(config_path), *arguments],
                        environment=environment,
                        parse_json=parse_json,
                    )

                sem("config", "init", "--api-url", API_URL, "--timeout", "10")
                assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
                bootstrap = sem("auth", "token-create", "cli-e2e", "--scope", "*", "--output", "json")
                bootstrap_id = bootstrap["token"]["id"]
                sem(
                    "config",
                    "token-set",
                    extra_environment={"SEM_TOKEN_INPUT": bootstrap["secret"]},
                )
                token_path = temporary / "token"
                assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
                assert sem("config", "validate", "--output", "json")["status"] == "ok"
                assert len(sem("auth", "token-list", "--output", "json")["items"]) == 1

                group = sem("groups", "create", "cli-e2e-group", "--output", "json")
                group_id = group["id"]
                updated_group = sem(
                    "groups",
                    "update",
                    group_id,
                    "--name",
                    "cli-e2e-group-updated",
                    "--sort-order",
                    "7",
                    "--output",
                    "json",
                )
                assert updated_group["sort_order"] == 7
                tag = sem("tags", "create", "cli-e2e-tag", "--output", "json")
                tag_id = tag["id"]
                account = sem(
                    "accounts",
                    "create",
                    "cli-e2e@outlook.com",
                    "--remark",
                    "isolated",
                    "--output",
                    "json",
                )
                account_id = account["id"]
                secret_status = sem(
                    "accounts",
                    "secrets-set",
                    account_id,
                    "--output",
                    "json",
                    extra_environment={
                        "SEM_OUTLOOK_PASSWORD": "test-password",
                        "SEM_OUTLOOK_REFRESH_TOKEN": "test-refresh",
                    },
                )
                assert secret_status["has_password"] and secret_status["has_refresh_token"]
                assert sem("accounts", "secrets-status", account_id, "--output", "json")["has_refresh_token"]
                assert (
                    len(
                        sem(
                            "accounts",
                            "aliases",
                            account_id,
                            "--alias",
                            "cli-e2e-alias@outlook.com",
                            "--output",
                            "json",
                        )["items"]
                    )
                    == 1
                )
                assert (
                    len(
                        sem(
                            "accounts",
                            "tags",
                            account_id,
                            "--tag-id",
                            tag_id,
                            "--action",
                            "add",
                            "--output",
                            "json",
                        )["items"]
                    )
                    == 1
                )
                row_version = sem("accounts", "show", account_id, "--output", "json")["row_version"]
                moved = sem(
                    "accounts",
                    "update",
                    account_id,
                    "--row-version",
                    str(row_version),
                    "--move-group",
                    "--group-id",
                    group_id,
                    "--output",
                    "json",
                )
                assert moved["group_id"] == group_id
                bulk_result = sem(
                    "accounts",
                    "bulk",
                    "--account-id",
                    account_id,
                    "--no-forwarding-enabled",
                    "--output",
                    "json",
                )
                assert bulk_result["updated_count"] in {0, 1}
                preview = sem(
                    "accounts",
                    "bulk-preview",
                    "--account-id",
                    account_id,
                    "--set-lifecycle",
                    "inactive",
                    "--output",
                    "json",
                )
                assert (
                    sem(
                        "accounts",
                        "bulk-execute",
                        "--preview-token",
                        preview["preview_token"],
                        "--output",
                        "json",
                    )["updated_count"]
                    == 1
                )
                assert (
                    sem(
                        "accounts",
                        "bulk",
                        "--account-id",
                        account_id,
                        "--lifecycle-status",
                        "active",
                        "--output",
                        "json",
                    )["updated_count"]
                    == 1
                )

                view = sem(
                    "fleet",
                    "view-create",
                    "cli-e2e-view",
                    "--filters-json",
                    '{"lifecycle_statuses":["active"]}',
                    "--output",
                    "json",
                )
                view_id = view["id"]
                assert (
                    sem(
                        "fleet",
                        "view-update",
                        view_id,
                        "--name",
                        "cli-e2e-view-updated",
                        "--sort-order",
                        "2",
                        "--output",
                        "json",
                    )["sort_order"]
                    == 2
                )
                assert len(sem("fleet", "views", "--output", "json")["saved"]) == 1

                proxy = sem(
                    "proxies",
                    "create",
                    "cli-e2e-proxy",
                    "--output",
                    "json",
                    extra_environment={"SEM_PROXY_URL": "socks5://127.0.0.1:7890"},
                )
                proxy_id = proxy["id"]
                assert (
                    sem(
                        "proxies",
                        "update",
                        proxy_id,
                        "cli-e2e-proxy-updated",
                        "--output",
                        "json",
                        extra_environment={"SEM_PROXY_URL": "socks5://127.0.0.1:7890"},
                    )["name"]
                    == "cli-e2e-proxy-updated"
                )
                sem("proxies", "assign-account", account_id, "--profile-id", proxy_id)
                assert sem("proxies", "resolve", account_id, "--output", "json")["source"] == "account"
                assert sem("proxies", "probe", proxy_id, "--output", "json")["status"] == "healthy"

                policy = sem(
                    "retention",
                    "policy",
                    account_id,
                    "--folder",
                    "inbox",
                    "--folder",
                    "junkemail",
                    "--max-messages",
                    "50",
                    "--output",
                    "json",
                )
                assert policy["max_messages"] == 50
                assert len(sem("retention", "policy-show", account_id, "--output", "json")["folders"]) == 2
                assert len(sem("retention", "policies", "--output", "json")["items"]) == 1
                assert not sem("retention", "mail", account_id, "--output", "json")["items"]
                assert sem("retention", "stats", "--output", "json")["message_count"] == 0
                sem("retention", "clear", "--account-id", account_id, "--yes")

                share = sem(
                    "shares",
                    "create",
                    account_id,
                    "--duration-minutes",
                    "30",
                    "--output",
                    "json",
                )
                share_id = share["id"]
                share_environment = {"SEM_SHARE_TOKEN": share["token"]}
                assert (
                    sem(
                        "shares",
                        "public-status",
                        "--output",
                        "json",
                        extra_environment=share_environment,
                    )["status"]
                    == "active"
                )
                assert not sem(
                    "shares",
                    "public-mail",
                    "--source",
                    "retained",
                    "--output",
                    "json",
                    extra_environment=share_environment,
                )["items"]
                assert sem("shares", "revoke", share_id, "--output", "json")["status"] == "revoked"
                sem("shares", "delete", share_id)

                forwarding = sem(
                    "forwarding",
                    "destination-create",
                    "cli-e2e-smtp",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "1",
                    "--recipient",
                    "target@example.com",
                    "--output",
                    "json",
                    extra_environment={"SEM_FORWARDING_SECRET": "test-smtp-secret"},
                )
                forwarding_id = forwarding["id"]
                assert (
                    sem(
                        "forwarding",
                        "destination-update",
                        forwarding_id,
                        "cli-e2e-smtp-updated",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "1",
                        "--recipient",
                        "target@example.com",
                        "--output",
                        "json",
                    )["name"]
                    == "cli-e2e-smtp-updated"
                )
                assert not sem("forwarding", "destination-test", forwarding_id, "--output", "json")["success"]
                assert sem(
                    "forwarding",
                    "account-set",
                    account_id,
                    "--destination-id",
                    forwarding_id,
                    "--output",
                    "json",
                )["enabled"]
                assert (
                    len(sem("forwarding", "account-show", account_id, "--output", "json")["destination_ids"])
                    == 1
                )
                assert sem("forwarding", "cursor-reset", account_id, "--output", "json")["cursor_at"] is None
                assert not sem("forwarding", "logs", "--account-id", account_id, "--output", "json")["items"]

                schedule = sem(
                    "schedules",
                    "create",
                    "cli-e2e-schedule",
                    "--cron",
                    "*/10 * * * *",
                    "--task-type",
                    "token_refresh",
                    "--account-id",
                    account_id,
                    "--output",
                    "json",
                )
                schedule_id = schedule["id"]
                assert (
                    sem(
                        "schedules",
                        "update",
                        schedule_id,
                        "cli-e2e-schedule-updated",
                        "--cron",
                        "*/15 * * * *",
                        "--task-type",
                        "retention_sync",
                        "--account-id",
                        account_id,
                        "--output",
                        "json",
                    )["task_type"]
                    == "retention_sync"
                )
                assert len(sem("schedules", "list", "--output", "json")["items"]) == 1
                sem("schedules", "delete", schedule_id)

                project = sem(
                    "projects",
                    "create",
                    "cli-e2e-project",
                    "--account-id",
                    account_id,
                    "--output",
                    "json",
                )
                project_id = project["id"]
                assert len(sem("projects", "accounts", project_id, "--output", "json")["items"]) == 1
                assert sem("projects", "events", project_id, "--output", "json")["items"]
                claim = sem("projects", "claim", project_id, "cli-e2e-owner", "--output", "json")
                claim_environment = {"SEM_CLAIM_TOKEN": claim["claim_token"]}
                assert (
                    sem(
                        "projects",
                        "heartbeat",
                        claim["project_account_id"],
                        "--lease-seconds",
                        "120",
                        "--output",
                        "json",
                        extra_environment=claim_environment,
                    )["status"]
                    == "leased"
                )
                assert (
                    sem(
                        "projects",
                        "release",
                        claim["project_account_id"],
                        "--output",
                        "json",
                        extra_environment=claim_environment,
                    )["status"]
                    == "to_claim"
                )
                claim = sem("projects", "claim", project_id, "cli-e2e-owner", "--output", "json")
                claim_environment = {"SEM_CLAIM_TOKEN": claim["claim_token"]}
                assert (
                    sem(
                        "projects",
                        "complete",
                        claim["project_account_id"],
                        "--output",
                        "json",
                        extra_environment=claim_environment,
                    )["status"]
                    == "done"
                )
                assert (
                    sem(
                        "projects",
                        "account-action",
                        project_id,
                        "--action",
                        "remove",
                        "--project-account-id",
                        claim["project_account_id"],
                        "--output",
                        "json",
                    )["updated_count"]
                    == 1
                )
                assert (
                    sem(
                        "projects",
                        "account-action",
                        project_id,
                        "--action",
                        "restore",
                        "--project-account-id",
                        claim["project_account_id"],
                        "--output",
                        "json",
                    )["updated_count"]
                    == 1
                )
                assert (
                    sem("projects", "status", project_id, "--status", "paused", "--output", "json")["status"]
                    == "paused"
                )
                assert (
                    sem("projects", "status", project_id, "--status", "active", "--output", "json")["status"]
                    == "active"
                )

                job = sem(
                    "health",
                    "check",
                    "--account-id",
                    account_id,
                    "--mode",
                    "metadata",
                    "--output",
                    "json",
                )
                job_id = job["id"]
                assert sem("jobs", "pause", job_id, "--output", "json")["status"] == "pausing"
                worker_log = (temporary / "worker.log").open("w", encoding="utf-8")
                worker_process = subprocess.Popen(
                    [str(BIN / "sem-worker")],
                    cwd=ROOT,
                    env=base_environment,
                    stdout=worker_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_for_job(sem, job_id, "paused")
                stop_process(worker_process)
                worker_process = None
                worker_log.close()
                assert sem("jobs", "resume", job_id, "--output", "json")["status"] == "queued"
                assert sem("jobs", "cancel", job_id, "--output", "json")["status"] == "cancelling"
                worker_log = (temporary / "worker-2.log").open("w", encoding="utf-8")
                worker_process = subprocess.Popen(
                    [str(BIN / "sem-worker")],
                    cwd=ROOT,
                    env=base_environment,
                    stdout=worker_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_for_job(sem, job_id, "cancelled")
                sem("jobs", "watch", job_id)
                assert sem("jobs", "list", "--output", "json")["items"]
                stop_process(worker_process)
                worker_process = None
                worker_log.close()

                refresh_job = sem("refresh", "start", "--account-id", account_id, "--output", "json")["id"]
                sem("jobs", "cancel", refresh_job, "--output", "json")
                assert sem("refresh", "summary", "--output", "json")["total_refreshable"] == 1
                assert not sem("refresh", "logs", "--account-id", account_id, "--output", "json")["items"]
                retention_job = sem("retention", "sync", "--account-id", account_id, "--output", "json")["id"]
                sem("jobs", "cancel", retention_job, "--output", "json")
                forwarding_job = sem("forwarding", "run", "--account-id", account_id, "--output", "json")[
                    "id"
                ]
                sem("jobs", "cancel", forwarding_job, "--output", "json")
                assert (
                    sem(
                        "codes",
                        "query",
                        "--account-id",
                        account_id,
                        "--account-limit",
                        "1",
                        "--recent-minutes",
                        "10",
                        "--output",
                        "json",
                    )["checked_accounts"]
                    == 1
                )

                imported = sem(
                    "imports",
                    "plan",
                    str(ROOT / "examples" / "outlook-import.example.txt"),
                    "--idempotency-key",
                    "cli-e2e-import",
                    "--output",
                    "json",
                )
                import_id = imported["id"]
                assert sem("imports", "show", import_id, "--output", "json")["status"] == "validated"
                assert len(sem("imports", "list", "--output", "json")["items"]) == 1
                committed_import = sem(
                    "imports",
                    "commit",
                    import_id,
                    "--no-connectivity-check",
                    "--output",
                    "json",
                )
                assert committed_import["batch"]["created_count"] == 1
                assert sem("imports", "rollback", import_id, "--output", "json")["status"] == "rolled_back"
                assert (
                    sem(
                        "security",
                        "rotate-key",
                        "--old-key-version",
                        "1",
                        "--output",
                        "json",
                        extra_environment={"SEM_OLD_MASTER_KEY": TEST_MASTER_KEY},
                    )["new_key_version"]
                    == 2
                )
                assert sem("audit", "list", "--output", "json")["items"]

                sem("fleet", "view-delete", view_id)
                sem("forwarding", "destination-delete", forwarding_id, "--yes")
                sem("proxies", "delete", proxy_id, "--yes")
                row_version = sem("accounts", "show", account_id, "--output", "json")["row_version"]
                sem(
                    "accounts",
                    "archive",
                    account_id,
                    "--row-version",
                    str(row_version),
                    "--output",
                    "json",
                )
                sem("accounts", "purge", account_id, "cli-e2e@outlook.com", "--yes")
                sem("tags", "delete", tag_id)
                sem("groups", "delete", group_id)
                assert sem("auth", "token-revoke", bootstrap_id, "--output", "json")["revoked_at"]
            finally:
                stop_process(worker_process)
                stop_process(api_process)
                api_log.close()
    finally:
        subprocess.run(["dropdb", "--if-exists", DATABASE], capture_output=True, check=False)
    print(
        json.dumps(
            {
                "cli_e2e": "passed",
                "config_permissions": "0600",
                "temporary_database_removed": True,
            }
        )
    )


if __name__ == "__main__":
    main()
