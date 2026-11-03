"""Record source hashes and scoped working-tree changes without reading secrets."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[2]
OWNED = {
    "apps/api/app/use_cases/studio_publication.py",
    "apps/api/app/use_cases/ARCHITECTURE.md",
    "apps/api/app/modules/content/tag/types.py",
    "apps/api/app/modules/content/tag/service/command.py",
    "apps/api/app/modules/content/tag/ARCHITECTURE.md",
    "apps/api/tests/test_studio_publication.py",
    "apps/api/tests/test_studio_republication_contracts.py",
    "apps/api/tests/test_tag_resolve_batch_contracts.py",
    "apps/api/tests/test_studio_publication_db.py",
}


def hashes() -> dict[str, str]:
    paths = set()
    for base in ("apps/api/app", "apps/api/tests", "tools", "references_document/reference"):
        paths.update(
            path for path in (ROOT / base).rglob("*")
            if path.is_file() and path.suffix in {".py", ".md", ".json", ".toml"}
        )
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def main() -> None:
    stage = sys.argv[1]
    if stage not in {"start", "end"}:
        raise SystemExit("Expected start or end")
    current = hashes()
    result: dict[str, object] = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "status": subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=ROOT, text=True),
        "sha256": current,
    }
    if stage == "end":
        before = json.loads((AUDIT / "validation-start.json").read_text(encoding="utf-8"))
        result["changed_during_final_checks"] = [
            path for path, digest in before["sha256"].items() if current.get(path) != digest
        ]
        baseline = json.loads((AUDIT / "baseline.json").read_text(encoding="utf-8"))
        changed = [
            path for path, digest in baseline["sha256"].items()
            if (ROOT / path).is_file()
            and hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest
        ]
        result["baseline_changed_owned"] = sorted(set(changed) & OWNED)
        result["baseline_changed_other"] = sorted(set(changed) - OWNED)
        result["baseline_missing"] = [path for path in baseline["sha256"] if not (ROOT / path).is_file()]
        result["owned_sha256"] = {path: current[path] for path in sorted(OWNED)}
        print(json.dumps({key: value for key, value in result.items() if key not in {"status", "sha256", "owned_sha256"}}, ensure_ascii=False, indent=2))
    output = AUDIT / f"validation-{stage}.json"
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
