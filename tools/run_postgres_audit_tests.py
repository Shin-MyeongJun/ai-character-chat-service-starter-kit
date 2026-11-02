"""Run selected tests against provisioned local audit DBs, without live providers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS = (
    "apps/api/tests/test_use_case_transaction.py",
    "apps/api/tests/test_tag_management_db.py::test_dictionary_concurrent_same_name_reuses_one_id",
    "apps/api/tests/test_hypha_memory.py::test_durable_queue_coalesces_requests_arriving_during_a_lease",
    "apps/api/tests/test_billing_lifecycle_integration.py",
    "apps/api/tests/test_identity_auth.py::test_register_verify_login_refresh_logout_http",
)


def main() -> int:
    settings = dotenv_values(ROOT / ".env.audit-test.local", interpolate=False)
    env = os.environ.copy()
    databases: list[str] = []
    for key, prefix in (
        ("TEST_DATABASE_URL", "chatkit_audit_test_"),
        ("TEST_AUTH_DATABASE_URL", "chatkit_auth_test_"),
    ):
        value = settings.get(key)
        if not value:
            raise SystemExit("Missing dedicated audit test DB configuration.")
        parsed = urlsplit(value)
        database = parsed.path.removeprefix("/")
        if (
            parsed.scheme != "postgresql+asyncpg"
            or parsed.hostname not in ("127.0.0.1", "localhost")
            or not database.startswith(prefix)
            or not (parsed.username or "").startswith("chatkit_test_")
            or not parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise SystemExit("Refusing a URL outside the dedicated local audit DBs.")
        env[key] = value
        databases.append(database)
    for key in (
        "VOYAGE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "RUN_ASSET_STORAGE_S3_INTEGRATION",
        "PYTEST_ADDOPTS",
    ):
        env.pop(key, None)
    env["PYTHONPATH"] = str(ROOT / "apps/api")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    arguments = sys.argv[1:]
    if any(arg.startswith("--basetemp") for arg in arguments):
        raise SystemExit("This runner supplies a fresh short basetemp automatically.")
    print(f"Local test databases: {', '.join(databases)}", flush=True)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "pytest_asyncio.plugin",
            "-q",
            "-rs",
            "--tb=short",
            f"--basetemp=tmp/pgt-{uuid4().hex[:8]}",
            *(arguments or DEFAULT_TESTS),
        ],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
