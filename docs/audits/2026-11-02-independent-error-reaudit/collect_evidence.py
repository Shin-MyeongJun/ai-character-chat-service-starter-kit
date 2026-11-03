"""Generate comparison/scope/counts without touching any application artifacts."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import subprocess
import sys

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    (AUDIT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def compare(mapping, base=ROOT):
    return {'count': len(mapping),
            'changed': [p for p, h in mapping.items() if (base / p).is_file() and sha(base / p) != h],
            'missing': [p for p in mapping if not (base / p).is_file()]}

def main():
    integration = json.loads((ROOT / 'docs/audits/2026-10-26-pattern-standardization/INTEGRATION-2026-11-02.json').read_text(encoding='utf-8'))
    previous_path = ROOT / 'docs/audits/2026-11-02-independent-error-audit'
    previous = json.loads((previous_path / 'baseline-end.json').read_text(encoding='utf-8'))
    comparisons = {
        'latest_integration_sources': compare(integration['sources']['sha256_by_path']),
        'previous_audit_existing_files': compare(previous['sha256_by_path']),
        'previous_audit_artifacts_including_logs': compare(previous['audit_file_sha256'], previous_path),
    }
    write('source-comparisons.json', comparisons)
    groups = {
        '기준·관련 계약절·기존 판정 재검토; 전체 문서 동일 깊이 검토 아님': [
            'AGENTS.md', 'references_document/reference/module-architecture-and-naming.md',
            'references_document/reference/backend-code-conventions.md',
            'docs/audits/2026-10-23-structural-review/REPORT.md',
            'docs/audits/2026-10-26-pattern-standardization/REPORT.md',
            'docs/audits/2026-10-26-pattern-standardization/U01-WORKLOG.md',
            'docs/audits/2026-10-26-pattern-standardization/U04-WORKLOG.md',
            'docs/audits/2026-10-26-pattern-standardization/U25-TAG-WORKLOG.md',
            'docs/audits/2026-10-26-pattern-standardization/U25-PG-INTEGRATION.md',
            'docs/deployment-readiness-2026-11-02.md', 'docs/operations-runbook.md',
            *[f'apps/api/app/{p}/ARCHITECTURE.md' for p in ['modules/chatting/chat', 'modules/llm', 'modules/asset_storage', 'modules/content/tag', 'use_cases']],
            'docs/audits/2026-11-02-independent-error-audit/REPORT.md',
        ],
        '현재 호출 경로·예외/잠금/취소 방어 선택 추적': [
            'apps/api/app/main.py', 'apps/api/Dockerfile', 'apps/api/app/db/transaction.py',
            'apps/api/app/modules/chatting/chat/router/answers.py',
            'apps/api/app/modules/chatting/chat/service/workflow/answers.py',
            'apps/api/app/modules/chatting/chat/service/workflow/memory.py',
            'apps/api/app/modules/chatting/chat/service/command/answers.py',
            'apps/api/app/modules/llm/service/text_generation.py',
            *[f'apps/api/app/modules/llm/adapters/{p}.py' for p in ['base','openai','anthropic','mock']],
            'apps/api/app/http/dependencies.py', 'apps/api/app/http/studio_publication.py',
            'apps/api/app/use_cases/studio_publication.py',
            'apps/api/app/modules/content/product/service/command/studio.py',
            'apps/api/app/modules/content/product/service/query/studio.py',
            'apps/api/app/modules/content/tag/service/command.py',
            'apps/api/app/modules/content/tag/repository.py',
            'apps/api/app/http/media.py', 'apps/api/app/modules/asset_storage/types.py',
            'apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py',
        ],
        '미커밋 diff 확인': [
            'apps/api/app/modules/chatting/chat/service/command/generation.py',
            'apps/api/app/modules/chatting/conversation/service/command/context.py',
            'apps/api/app/modules/content/lorebook/service/command.py',
        ],
        '검증 도우미·대역 조건 검토 또는 실행; 앱 소스 감사와 구별': [
            'tools/run_postgres_audit_tests.py', 'apps/api/tests/conftest.py',
            *[f'apps/api/tests/{p}.py' for p in ['test_nonstream_answers','test_studio_publication','test_studio_locking_db',
                'test_studio_republication_contracts','test_llm_sdk_contracts','test_memory_deadlines','test_media_cancellation_contracts']],
            *[f'docs/audits/2026-11-02-independent-error-audit/{p}.py' for p in ['test_reproductions','test_s3_reader_lifetime','conftest','run_checks','finalize_evidence']],
        ],
        '설치된 의존성의 취소·종료 관련 부분만 확인': [
            *[f'.venv/Lib/site-packages/{p}' for p in ['openai/_base_client.py','anthropic/_base_client.py',
                'httpx/_client.py','starlette/responses.py','uvicorn/config.py','uvicorn/server.py','uvicorn/protocols/http/h11_impl.py']],
        ],
    }
    write('reviewed-scope.json', {'groups': {g: [{'path': p, 'sha256': sha(ROOT / p)} for p in ps] for g, ps in groups.items()},
          'note': '해시 일치가 파일 전체 읽기·전체 조합의 안전성 증명을 뜻하지 않는다.'})
    runs = []
    for stem in ['prior-pg-recheck','prior-s3-recheck','http-publication','sdk-http-lifetime-final','answer-sdk-and-regression','focused-contracts','environment-final']:
        content = (AUDIT / 'logs' / f'{stem}.txt').read_text(encoding='utf-8')
        summary = next(line.strip() for line in reversed(content.splitlines()) if re.search(r'\d+ (?:passed|failed).* in [0-9]', line))
        counts = dict((k, int(n)) for n, k in re.findall(r'(\d+) (passed|failed|skipped|errors?)', summary))
        runs.append({'log': f'logs/{stem}.txt', 'summary': summary, 'counts': {k: counts.get(k, 0) for k in ['passed','failed','skipped','errors']}})
    write('verification-results.json', {
        'canonical_runs': runs,
        'total': {k: sum(r['counts'][k] for r in runs) for k in ['passed','failed','skipped','errors']},
        'setup_errors': 0, 'collection_errors': 0,
        'failed_confirmed_defect_assertions': 6, 'failed_conditional_candidate_assertions': 2,
        'distinct_confirmed_defects': 3,
        'superseded_attempt': {'log': 'logs/sdk-http-lifetime.txt', 'passed': 4, 'failed': 2,
            'setup_errors': 0, 'collection_errors': 0, 'note': '1 failure was audit timer arming before SDK cold-start; 1 was S3 reproduction. Not added to canonical sum.'},
    })
    write('runtime-versions.json', {'python': sys.version.split()[0], 'platform': sys.platform,
        'packages': {p: version(p) for p in ['openai','anthropic','httpx','httpcore','starlette','uvicorn','botocore','pytest','SQLAlchemy']}})
    ranges = {
        'apps/api/app/use_cases/studio_publication.py': [(185,255),(297,325),(375,403),(487,508)],
        'apps/api/app/modules/content/tag/repository.py': [(55,81)],
        'apps/api/app/http/studio_publication.py': [(108,132)],
        'apps/api/app/modules/asset_storage/types.py': [(174,197)],
        'apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py': [(69,88),(278,310)],
        'apps/api/app/http/media.py': [(70,92)],
        'apps/api/app/modules/chatting/chat/service/workflow/answers.py': [(588,635)],
        '.venv/Lib/site-packages/uvicorn/server.py': [(287,304)],
    }
    excerpts = ['# 재검사에서 확인한 현재 코드 발췌\n']
    for p, spans in ranges.items():
        lines = (ROOT / p).read_text(encoding='utf-8').splitlines()
        excerpts.append(f'\n## {p}\nSHA-256: `{sha(ROOT / p)}`\n')
        for start, end in spans:
            excerpts.append('```text\n' + '\n'.join(f'{i}: {lines[i-1]}' for i in range(start,min(end,len(lines))+1)) + '\n```\n')
    (AUDIT / 'code-evidence.md').write_text('\n'.join(excerpts), encoding='utf-8')
    print(json.dumps(comparisons))
    print('canonical_counts', {k: sum(r['counts'][k] for r in runs) for k in ['passed','failed','skipped','errors']})

if __name__ == '__main__':
    main()
