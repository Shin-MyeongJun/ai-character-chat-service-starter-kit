"""Hash-only evidence finalization; writes solely inside this new audit folder."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name, value):
    (AUDIT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    baseline = json.loads((AUDIT / "baseline-start.json").read_text(encoding="utf-8"))
    groups = {
        "기준·최신 기록·관련 계약절 확인(큰 역사 문서 전체 동일 깊이 검토 아님)": [
            "AGENTS.md",
            "references_document/reference/module-architecture-and-naming.md",
            "references_document/reference/backend-code-conventions.md",
            "docs/audits/2026-10-23-structural-review/REPORT.md",
            "docs/audits/2026-10-26-pattern-standardization/REPORT.md",
            "docs/audits/2026-10-26-pattern-standardization/INTEGRATION-2026-11-02.json",
            "docs/deployment-readiness-2026-11-02.md", "docs/operations-runbook.md",
        ],
        "관련 업무 계약절·후속 상태 대조": [
            *[f"docs/audits/2026-10-26-pattern-standardization/{name}.md" for name in (
                "U01-WORKLOG", "U02-WORKLOG", "U03-WORKLOG", "U04-WORKLOG", "U05-WORKLOG",
                "U18-WORKLOG", "U19-REDESIGN-NOTE", "U20-WORKLOG", "U21-WORKLOG", "U22-WORKLOG",
                "U23-WORKLOG", "U24-WORKLOG", "U25-TAG-WORKLOG", "U25-PG-INTEGRATION",
                "U28-WORKLOG", "U29-WORKLOG", "U01-U04-INTEGRATION-REVIEW",
                "U02-U05-INTEGRATION-REVIEW", "U03-U21-INTEGRATION-REVIEW", "U20-U22-INTEGRATION-REVIEW",
            )],
            *[f"apps/api/app/{name}/ARCHITECTURE.md" for name in (
                "db", "use_cases", "modules/chatting/chat", "modules/chatting/memory",
                "modules/chatting/conversation", "modules/commerce/billing", "modules/commerce/credit",
                "modules/identity", "modules/content/product", "modules/content/character",
                "modules/content/lorebook", "modules/content/tag", "modules/llm",
                "modules/governance/moderation", "modules/asset_storage",
            )],
        ],
        "A: 고위험 실행 경로 중심 코드 추적(파일별 선택 범위)": [
            "apps/api/app/modules/chatting/chat/service/workflow/answers.py",
            "apps/api/app/modules/chatting/chat/service/workflow/answer_preparation.py",
            "apps/api/app/modules/chatting/chat/service/workflow/memory.py",
            "apps/api/app/modules/chatting/chat/service/command/answers.py",
            "apps/api/app/modules/chatting/chat/service/command/answer_recovery.py",
            "apps/api/app/modules/chatting/chat/service/command/generation.py",
            "apps/api/app/modules/chatting/chat/service/query/messages.py",
            "apps/api/app/modules/chatting/chat/repository.py", "apps/api/app/modules/chatting/chat/types.py",
            "apps/api/app/modules/chatting/chat/router/answers.py",
            "apps/api/app/modules/chatting/conversation/service/command/context.py",
            "apps/api/app/modules/chatting/memory/repository.py",
            "apps/api/app/modules/chatting/memory/service/command/summarization.py",
            "apps/api/app/modules/chatting/memory/service/command/scheduling.py",
            "apps/api/app/modules/llm/service/text_generation.py",
            "apps/api/app/modules/llm/adapters/openai.py", "apps/api/app/db/transaction.py",
        ],
        "B: 인증·메일 실행 및 HTTP 조립 선택 추적": [
            "apps/api/app/modules/identity/service/authentication.py",
            "apps/api/app/modules/identity/service/query.py",
            "apps/api/app/modules/identity/service/mail_delivery.py",
            "apps/api/app/modules/identity/service/workflow/mail.py",
            "apps/api/app/modules/identity/repository.py",
            "apps/api/app/modules/identity/security.py", "apps/api/app/modules/identity/http_security.py",
            "apps/api/app/modules/identity/dependencies.py", "apps/api/app/http/authorization.py",
            "apps/api/app/main.py",
        ],
        "C: 발행·태그·신고 주요 경로 추적": [
            "apps/api/app/use_cases/studio_publication.py", "apps/api/app/use_cases/studio_components.py",
            "apps/api/app/http/studio_publication.py",
            "apps/api/app/modules/content/tag/repository.py",
            "apps/api/app/modules/content/tag/service/command.py",
            "apps/api/app/modules/content/character/service/tags.py",
            "apps/api/app/modules/content/lorebook/service/tags.py",
            "apps/api/app/modules/governance/moderation/service/command/reports.py",
            "apps/api/app/modules/governance/moderation/service/command/assessments.py",
            "apps/api/app/modules/governance/moderation/repository/review.py",
        ],
        "D: reader·HTTP 정리·해싱 수명 선택 추적": [
            "apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py",
            "apps/api/app/modules/asset_storage/types.py", "apps/api/app/http/media.py",
            "apps/api/app/modules/content/character/service/media.py",
            "tools/run_postgres_audit_tests.py", "apps/api/tests/conftest.py",
        ],
        "프런트: 수명·인가 응답 적용 코드 선별; 브라우저 미실행": [
            "apps/web/AGENTS.md", "apps/web/components/recent-conversations.tsx",
            "apps/web/lib/api.ts", "apps/web/lib/recent-chats.ts",
            "apps/web/app/chats/[id]/page.tsx", "apps/web/components/account/use-account.ts",
            "apps/web/components/account/use-owned-products.ts", "apps/web/components/account/use-credit-history.ts",
            "apps/web/tests/api-integration.test.cjs", "apps/web/tests/recent-conversations.test.cjs",
        ],
        "이번 직접 실행한 기존 테스트; 소스 선별 확인 깊이는 서로 다름": [
            *[f"apps/api/tests/{name}.py" for name in (
                "test_answer_history_windows", "test_memory_claim_fencing", "test_answer_billing_integration",
                "test_answer_recovery_policy_db", "test_studio_locking_db", "test_u25_postgres_concurrency",
                "test_moderation_graph_db", "test_identity_mail_outbox", "test_local_storage_lifecycle",
                "test_media_cancellation_contracts", "test_media_fingerprint_contracts", "test_media_transport_contracts",
            )],
            "apps/api/tests/test_nonstream_answers.py", "apps/api/tests/test_studio_publication.py",
            "apps/api/tests/test_studio_republication_contracts.py", "apps/api/tests/test_product_usage.py",
            "apps/api/tests/test_identity_auth.py",
        ],
    }
    scope = []
    for depth, paths in groups.items():
        for path in paths:
            if not (ROOT / path).is_file():
                raise RuntimeError(f"Scope file missing: {path}")
            scope.append({"path": path, "review_depth": depth, "sha256": digest(ROOT / path)})
    write_json("reviewed-scope.json", {"root": str(ROOT), "unique_paths": len({entry['path'] for entry in scope}), "files": scope})
    results = []
    for name, counts in (
        ("reproductions-canonical-v2.txt", (3, 4)), ("selected-pg-contracts.txt", (204, 0)),
        ("storage-final.txt", (63, 1)), ("environment-after-v2.txt", (1, 0)),
    ):
        content = (AUDIT / "logs" / name).read_text(encoding="utf-8")
        summary = next(line.strip() for line in reversed(content.splitlines()) if re.search(r"\d+ (?:passed|failed).* in [0-9]", line))
        actual = {kind: int(n) for n, kind in re.findall(r"(\d+) (passed|failed|skipped|errors?)", summary)}
        assert (actual.get("passed", 0), actual.get("failed", 0)) == counts
        results.append({"log": "logs/" + name, "summary": summary, "passed": counts[0], "failed": counts[1], "skipped": 0, "setup_errors": 0, "collection_errors": 0})
    write_json("verification-results.json", {
        "canonical_runs": results, "total": {"passed": 271, "failed": 5, "skipped": 0, "setup_errors": 0, "collection_errors": 0},
        "new_reproduction_and_controls": {"passed": 4, "failed": 5, "distinct_defects": 4},
        "existing_business_regressions_passed": 266, "environment_checks_passed": 1,
        "earlier_collection_errors_not_in_final_sum": 1, "interrupted_runs_without_pytest_outcome": 1,
        "prior_or_intermediate_runs_are_not_added_again": True,
    })
    current = {p: digest(ROOT / p) for p in baseline["sha256"] if (ROOT / p).is_file()}
    paths = set(subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0"))
    prefix = AUDIT.relative_to(ROOT).as_posix() + "/"
    new_outside = sorted(p for p in paths if p and p not in baseline["sha256"] and not p.startswith(prefix) and not p.startswith(".env") and (ROOT / p).is_file())
    changed = sorted(p for p, h in current.items() if h != baseline["sha256"][p])
    missing = sorted(set(baseline["sha256"]) - set(current))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    write_json("baseline-end.json", {
        "captured_at": datetime.now(timezone.utc).isoformat(), "head": head,
        "head_unchanged": head == baseline["head"], "baseline_file_count": len(baseline["sha256"]),
        "changed_baseline_files": changed, "missing_baseline_files": missing, "new_files_outside_audit": new_outside,
        "status": subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=ROOT).decode().splitlines(),
        "sha256_by_path": current,
        "audit_file_sha256": {p.relative_to(AUDIT).as_posix(): digest(p) for p in sorted(AUDIT.rglob("*")) if p.is_file() and "__pycache__" not in str(p) and p.name != "baseline-end.json"},
    })
    print(json.dumps({"head_unchanged": head == baseline["head"], "changed_baseline_files": changed, "missing_baseline_files": missing, "new_files_outside_audit": new_outside, "reviewed_unique_paths": len({entry['path'] for entry in scope}), "canonical_test_cases": 276}))
    if changed or missing or new_outside or head != baseline["head"]:
        raise SystemExit("Scope changed; qualify the report before delivery")


if __name__ == "__main__":
    main()
