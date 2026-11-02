# U15·U25 통계 변경 통합 점검

작성일: 2026-10-29 (Asia/Seoul)

상태: **U15 완료, U25 통계 재예약 범위 완료, 통합 오프라인 회귀 통과.**
U25의 태그 이름 resolve 배치화와 실제 PostgreSQL 검증은 남아 있다.

## 점검 범위와 판단

사용자의 U25 완료 후 점검·통합 요청에 따라 현재 작업 상태와 두 전용 작업 기록,
변경 코드/테스트, lorebook/product ARCHITECTURE, 공통 감사 기록을 대조했다.
AGENTS.md와 모듈 아키텍처/명명·백엔드 작성 규칙을 확인했다.

- 두 변경은 같은 작업 트리에 이미 존재한다. git의 미해결 index 항목과 대상 파일의
  충돌 마커는 없다. 별도 브랜치 merge나 제품 코드 추가 수정 없이 통합 검증했다.
- U15는 activation.py/matching.py의 매칭 의미와 옵션별 캐시, U25는 product의
  통계 command/repository 배치 저장을 변경한다. 직접 겹치는 제품 코드가 없다.
- U15의 공개 스냅샷 선택기와 도메인 초안 진단은 같은 v1 규칙을 사용한다. 실제
  studio 변환의 contains와 라이브 query의 legacy 정책은 별개로 유지한다.
- U25는 500개 입력 키 버퍼·배치 내부 중복 제거·순차 upsert를 사용한다. 단건 예약도
  같은 구현에 한 키를 전달한다. 서울 날짜·DB now() 시각·상위 트랜잭션 원자성과
  실패 시 rollback-only, claim/complete 경로가 유지됨을 코드와 회귀로 확인했다.
- U25 전용 기록의 완료 범위는 통계 재예약이다. 태그 이름 resolve는 수정되지 않았으며
  U25 전체 완료로 표시하지 않는다.
- 기존 staged/unstaged/untracked 변경과 U06/U14의 아키텍처 설명을 보존했다.
  reset/clean·무관한 복원/삭제·별도 대화/서브에이전트·commit/push는 하지 않았다.

구현·단독 회귀의 상세 근거:
[U15-WORKLOG.md](U15-WORKLOG.md), [U25-STATISTICS-WORKLOG.md](U25-STATISTICS-WORKLOG.md).
이번 통합에서는 두 공통 REPORT와 두 전용 작업 기록의 상태/연결, 이 문서만 갱신했다.

## 통합 검증

모든 Python 명령은 프로젝트 `.venv/Scripts/python.exe`를 사용했다.
TEST_DATABASE_URL과 TEST_AUTH_DATABASE_URL을 제거하고 플러그인 자동 로딩을 비활성화했다.
실제 DB migration/초기화/삭제, 외부 공급자 요청은 실행하지 않았다.

| 검증 | passed | failed | skipped | 상세 |
|---|---:|---:|---:|---|
| U15/U25 변경 Python 7파일 직접 Ruff format/check·mypy | — | 0 | — | mypy 7소스, 오류 없음 |
| 필수 tools/check_backend_quality.py | 13 | 0 | 0 | Ruff 390파일·mypy 369소스·타입 패턴 기준선 0개 |
| 전체 API 최종 오프라인 회귀 | **1337** | **0** | **288** | 기존 Starlette 422 상수 경고 2개 |
| 변경 범위 git diff --check | — | 0 | — | 충돌 마커·미해결 index도 없음 |

전체 API는 기존 U14 기준 1229 passed에 신규 U15 75건과 U25 33건을 포함해 1337 passed다.
이는 같은 실행의 실제 최종 집계이며 이전 단독 회귀 결과를 합산한 대체 수치가 아니다.
품질 검사 13건은 전체 API에도 포함되므로 별도로 더하지 않는다. skipped 288건 역시
passed에 포함하지 않는다. PostgreSQL/인증 DB·live S3·live Voyage 등 환경이 필요한 검증은
skip 사유가 로그에 남아 있다.

실행 로그:

- [최종 전체 API](../../../tmp/u15-u25-integrated-api-final.txt)
- [필수 품질 검사](../../../tmp/u15-u25-integrated-quality.txt)
- [최초 전체 API 실패](../../../tmp/u15-u25-integrated-api.txt)
- [짧은 경로의 실패 3건 재검증](../../../tmp/u15-u25-path-check.txt)

## 첫 실행 실패와 재검증

첫 전체 API는 1334 passed / 3 failed / 288 skipped였다. 세 실패는 모두 기존
test_asset_storage.py의 로컬 저장소 경로였으며, 긴 basetemp 아래 metadata 임시 파일의
절대 경로 길이가 각각 269자였다. FileNotFoundError가 기존 AssetNotFoundError로 번역됐다.

긴 경로는 tmp/u15-u25-integrated-api-9e759c02d48946578c98a01b379fa942였다.
짧은 새 tmp/i1525-cd765d 경로에서 같은 실패 3건을 실행해 3 passed / 0 failed / 0 skipped를
확인했다. 이어 새 tmp/i1525-1772bc에서 **전체 API를 다시 실행**해 최종 1337 passed /
0 failed / 288 skipped를 확인했다. 특정 테스트 제외·제품 코드 수정·OS 설정 변경으로
실패를 우회하지 않았다. 첫 실패와 재검증 로그를 모두 보존했다.

## 재실행 명령

저장소 루트의 PowerShell에서 실행한다. 기존 디렉터리의 pytest basetemp 재사용은
내부 파일을 정리할 수 있으므로 매번 새 이름을 쓴다. 이 프로젝트의 Windows 경로에서는
로컬 저장소 metadata 임시 파일까지 고려해 **짧은 basetemp**를 사용한다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_AUTH_DATABASE_URL, Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
$integrationTemp = 'tmp/i1525-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests -q -rs --tb=short --basetemp=$integrationTemp

$env:PYTEST_ADDOPTS = '--basetemp=tmp/q1525-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue

.venv/Scripts/python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api/app/modules/content/lorebook/service/activation.py apps/api/app/modules/content/lorebook/service/util/matching.py apps/api/tests/test_lorebook_activation_contracts.py apps/api/app/modules/content/product/service/command/statistics.py apps/api/app/modules/content/product/repository/statistics.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_statistics_repair_batch_contracts.py
.venv/Scripts/python.exe -m ruff check --config apps/api/pyproject.toml apps/api/app/modules/content/lorebook/service/activation.py apps/api/app/modules/content/lorebook/service/util/matching.py apps/api/tests/test_lorebook_activation_contracts.py apps/api/app/modules/content/product/service/command/statistics.py apps/api/app/modules/content/product/repository/statistics.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_statistics_repair_batch_contracts.py
.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/app/modules/content/lorebook/service/activation.py apps/api/app/modules/content/lorebook/service/util/matching.py apps/api/tests/test_lorebook_activation_contracts.py apps/api/app/modules/content/product/service/command/statistics.py apps/api/app/modules/content/product/repository/statistics.py apps/api/tests/test_product_statistics_contracts.py apps/api/tests/test_statistics_repair_batch_contracts.py
```

## 잔여 범위와 한계

- U25 태그 이름 resolve 배치화: 이름별 잠금 순서·unique 충돌·비활성 태그 보존을
  별도 구현·검증해야 한다. U16 태그 공통화와의 작업 경계도 먼저 정한다.
- 실제 PostgreSQL의 행 잠금·경합·격리·동시 재예약/claim·실행 계획·처리량은 미검증이다.
  SQLite 제약·SQL 컴파일·대역 테스트나 이번 오프라인 전체 회귀로 대체하지 않는다.
- 전체 API 실행은 현재 작업 트리의 백엔드 회귀다. 웹 브라우저 E2E와 외부 공급자/실제 DB
  연동 검증을 완료했다는 의미가 아니다. 기존 경고 2개를 없애기 위한 HTTP 상수 변경은 하지 않았다.
- 이번 통합 검증을 위해 Any/ignore/cast/기준선 예외·공통 검사 설정을 추가하지 않았다.
