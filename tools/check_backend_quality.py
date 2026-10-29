"""Run backend pattern, reference-scope typing/style, and architecture checks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    paths = json.loads(
        (ROOT / "tools/backend-quality-scope.json").read_text(encoding="utf-8")
    )["paths"]
    config = "apps/api/pyproject.toml"
    commands = [
        ["tools/check_backend_patterns.py"],
        ["-m", "ruff", "format", "--check", "--config", config, *paths],
        ["-m", "ruff", "check", "--config", config, *paths],
        ["-m", "mypy", "--config-file", config, *paths],
        [
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "apps/api/tests/test_architecture_contracts.py",
            "apps/api/tests/test_backend_pattern_checks.py",
            "-q",
            "--tb=short",
        ],
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "apps/api")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    # This command is an offline quality gate, not a database integration run.
    env.pop("TEST_DATABASE_URL", None)
    failed = False
    for command in commands:
        print(f"Running: python {' '.join(command)}", flush=True)
        result = subprocess.run(
            [sys.executable, *command], cwd=ROOT, env=env, check=False
        )
        failed |= result.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
