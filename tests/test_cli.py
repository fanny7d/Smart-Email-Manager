from typer.testing import CliRunner

from smart_email_manager.cli.main import app


def test_cli_help_exposes_automation_groups() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "auth",
        "config",
        "system",
        "fleet",
        "groups",
        "accounts",
        "health",
        "imports",
        "jobs",
        "mail",
        "codes",
        "proxies",
        "tags",
        "refresh",
        "schedules",
        "retention",
        "shares",
        "forwarding",
        "security",
        "projects",
        "audit",
    ):
        assert command in result.stdout


def test_cli_version_and_expanded_command_groups() -> None:
    runner = CliRunner()
    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert version.stdout.strip() == "0.1.0"

    expected = {
        "accounts": {"secrets-status", "secrets-set", "bulk-preview", "bulk-execute"},
        "config": {"init", "show", "set", "token-set", "validate"},
        "forwarding": {"destination-update", "destination-test", "destination-delete"},
        "jobs": {"watch", "pause", "resume", "cancel"},
        "projects": {"accounts-add", "status", "events", "heartbeat"},
        "proxies": {"update", "delete", "probe"},
        "retention": {"policies", "policy-show", "mail", "mail-show", "clear"},
        "shares": {"public-status", "public-mail", "public-show"},
    }
    for group, commands in expected.items():
        result = runner.invoke(app, [group, "--help"])
        assert result.exit_code == 0
        for command in commands:
            assert command in result.stdout
