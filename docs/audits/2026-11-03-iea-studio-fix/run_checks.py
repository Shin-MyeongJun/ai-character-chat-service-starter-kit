"""Safe audit launcher: project Python, no live providers, redacted saved output."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[2]


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[1] not in {"pg", "offline", "command"}:
        raise SystemExit("Usage: run_checks.py pg|offline|command LOG_STEM TARGET ...")
    mode, stem, *targets = sys.argv[1:]
    if not re.fullmatch(r"[a-z0-9-]+", stem):
        raise SystemExit("Unsafe log name")
    log = AUDIT / "logs" / f"{stem}.txt"
    if log.exists():
        raise SystemExit("Refusing to overwrite an existing audit log; choose a new stem")
    env = os.environ.copy()
    for key in tuple(env):
        if (
            key.startswith((
                "TEST_", "SMTP_", "AWS_", "S3_", "ASSET_STORAGE_", "ASSET_S3_",
                "OPENAI_", "ANTHROPIC_", "VOYAGE_", "AZURE_", "AUTH_SMTP_",
                "AUTH_GOOGLE_", "GOOGLE_",
            ))
            or key.endswith("_API_KEY")
            or key.startswith("RUN_")
            or key in {"PYTEST_ADDOPTS", "DATABASE_URL", "REDIS_URL"}
        ):
            env.pop(key, None)
    env.update(
        PYTHONIOENCODING="utf-8",
        PYTHONPATH=os.pathsep.join([str(ROOT / "apps/api"), str(ROOT / "apps/api/tests")]),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )
    common = ["--assert=plain", "-s", *targets]
    if mode == "command":
        env["PYTEST_ADDOPTS"] = f"--basetemp=tmp/iq-{uuid4().hex[:8]}"
        command = [sys.executable, *targets]
    elif mode == "pg":
        command = [sys.executable, "tools/run_postgres_audit_tests.py", *common]
    else:
        command = [
            sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
            "-p", "pytest_asyncio.plugin", "-q", "-rs", "--tb=short",
            f"--basetemp=tmp/ia-{uuid4().hex[:8]}", *common,
        ]
    # Do not print or save raw exception output: DBAPI exceptions can include SQL
    # parameters. Plain assertions and no locals also keep synthetic proof values out.
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True)
    output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
    output = output.replace("\r\n", "\n").replace("\r", "")
    output = re.sub(r"(?im)^Local test databases:.*$", "Dedicated local audit DBs (identifiers redacted).", output)
    output = re.sub(r"(?i)\b(?:postgres(?:ql)?(?:\+asyncpg)?|https?|s3|redis)://[^\s)\]>]+", "<url-redacted>", output)
    output = re.sub(r"(?im)^.*(?:\[SQL:|\[parameters:|Background on this error).*$", "<db-details-redacted>", output)
    with log.open("x", encoding="utf-8") as handle:
        handle.write(output + f"\nPROCESS_EXIT_CODE={result.returncode}\n")
    print(output, end="")
    print(f"PROCESS_EXIT_CODE={result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
