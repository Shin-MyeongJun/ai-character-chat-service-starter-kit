"""Reuse the repository's UUID-schema-isolated PG fixture unchanged."""

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api/tests"))
spec = importlib.util.spec_from_file_location(
    "independent_audit_project_fixtures", ROOT / "apps/api/tests/conftest.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
db = module.db
