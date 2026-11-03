# IEA-02·IEA-03 스튜디오 발행 수정 보고서

실행일: **2026-11-03, Asia/Seoul**. 대상은 미커밋 변경을 포함한 현재 작업 트리다.

## 결과와 검증 한계

**두 결함의 앱 코드 수정·프로젝트 회귀 추가·오프라인 검증·보고서 작성을 완료했다. 실제 PostgreSQL 수정 전후 재현은 전용 감사 DB 연결 거부로 검증하지 못했다.** 교착 해소를 실제 PG에서 입증했다고 판정하지 않는다.

- IEA-02: 발행 전체의 태그 이름 집합을 한 순서로 획득한다. 개별 resolve 내부 정렬을 반복하는 것에 그치지 않는다. 기존 부모 잠금 뒤, 구성요소별 태그 쓰기 전에 수행한다.
- IEA-03: 같은 snapshot을 반환하는 성공도 현재 revision/fingerprint의 영수증을 같은 트랜잭션에 저장한다. 새 snapshot·문서 revision을 만들지 않는다.
- 최종 관련 19파일: **234 passed / 0 failed / 51 skipped / 0 setup errors / 0 collection errors**. PG 의존 51건의 skip을 통과에 넣지 않았다.
- 필수 품질 검사: **종료 코드 0**, 기준선 진단 0, Ruff 388파일, mypy 367소스, 아키텍처/검사기 **13 passed**. 관련 234건과 별도다.
- 변경 테스트 중 엄격 검사한 3파일의 Ruff format/check·mypy 통과. 전체 API·운영·브라우저 E2E 검증 결과로 확대하지 않는다.

## 시작 상태와 병렬 작업 경계

시작·종료 HEAD는 `31de1428aba2ea67fc887b004221f7bc3884cf0a`다. 시작 시 staged 0, 기존 tracked unstaged 46개였다. 삭제 표시와 기존 untracked 감사 폴더도 그대로 유지했다. 기준 수집 전에 새 실행기를 만들었으므로 [baseline.json](baseline.json)의 untracked 8항목에는 이 작업 폴더도 포함된다. 시작 porcelain·staged/unstaged stat·대상 및 참고 자료 **268파일 SHA-256**을 이 파일에 기록했다. HEAD만 별도 checkout하지 않았다.

[validation-end.json](validation-end.json)에서 시작 기준 268파일 중 변경은 이 작업의 기존 파일 8개뿐이며, 다른 파일 변경 0·누락 0이다. 신규 프로젝트 테스트 1개와 이 전용 감사 폴더는 별도 추가다. use_cases/ARCHITECTURE.md에 있던 기존 미커밋 변경은 보존하고 이번 절만 추가했다. 기존 감사 재현/REPORT·공통 REPORT/WORKLOG·검사 설정·타입 기준선은 편집하지 않았다.

작업 중 다른 작업이 `asset_storage`, `http/media.py`, S3 회귀·전용 감사 폴더를 변경한 것이 최종 git 상태에 나타난다. 이 작업은 해당 파일을 쓰거나 복구하지 않았다. 해당 변경은 이번 수정 목록과 검증 주장에 포함하지 않는다. 답변·과금 코드도 수정하지 않았다.

최종 품질 검사 직전 [validation-start.json](validation-start.json), 직후 [validation-end.json](validation-end.json)으로 앱·테스트·도구·참고 문서의 해시를 대조했다. **그 구간의 변경 0개**다. 관련 회귀의 최종 로그는 최종 스튜디오/태그 소스 및 테스트를 대상으로 한다. 전체 앱 품질 결과에는 당시 병렬 작업의 코드도 포함되며, 이후 외부 변경까지 보증하지 않는다. 최초 기준은 대상 중심 268파일이므로 그 밖의 파일이 작업 내내 불변이었다고 주장하지 않는다.

## 확인한 자료와 실제 호출 경로

AGENTS.md, 모듈 아키텍처·명명 규칙, 백엔드 작성 규칙, 독립 재감사 REPORT와 두 재현 파일, use_cases 및 product/character/lorebook/tag의 ARCHITECTURE를 확인했다. U04-WORKLOG, 공통 REPORT의 U06 후속 발행 계약 확정 절, U25-TAG-WORKLOG·U25-PG-INTEGRATION, 최신 INTEGRATION-2026-11-02.json의 결과·해시·미검증 범위를 대조했다. 과거 1706/2149 통과를 이번 실행 수에 합산하지 않았다.

공개 경로는 다음과 같다. HTTP DTO·인증 의존성과 응답 계약은 변경하지 않았다.

1. `app/http/studio_publication.py:112`의 POST → `publish_studio_draft` → `PublishStudioCommand` → `use_cases/studio_publication.publish_studio`.
2. product 공개 `get_studio_draft_for_publication` → 상품 ID advisory → product 소유권/FOR UPDATE → draft FOR UPDATE. `component_mapping`과 revision별 fingerprint 확인을 이어 수행한다.
3. 변경 발행은 character 생성/갱신, lorebook 생성/갱신, product 프로필 갱신을 공개 service로 조합한다. 각 콘텐츠 태그 service는 자기 부모를 잠그고 기존 연결 ID를 읽은 뒤 tag 공개 `resolve_tags`를 호출한다.
4. tag command는 trim·중복·비활성 정책을 판단한다. tag repository는 이름을 Python 순서로 정렬하여 500개씩 INSERT ON CONFLICT DO NOTHING → 같은 순서의 SELECT FOR SHARE/populate_existing을 실행한다. 관리자 변경은 FOR UPDATE를 사용한다.
5. product release service → publication builder → snapshot/release repository, 마지막으로 product 공개 `mark_studio_publication` → studio repository가 JSONB 영수증을 flush/refresh한다.

최외곽 `use_case_transaction`이 한 번 commit/rollback한다. 하위 서비스는 같은 트랜잭션에 참여하고, 하위 실패를 잡아도 rollback-only가 유지된다. 저장소의 자체 commit이나 savepoint는 없다.

## IEA-02 원인과 수정

기존 작품별 advisory와 단일 태그 묶음 정렬은 서로 다른 작품의 공유 신규 이름을 정렬하지 못했다. 작품 A가 캐릭터 alpha를 INSERT하고 작품 B가 캐릭터 beta를 INSERT한 뒤, 각 로어북에서 상대 이름을 요청하면 미커밋 UNIQUE 확인이 서로 기다릴 수 있다. SHARE 잠금끼리의 충돌이 원인은 아니다. HTTP에는 이 DB 오류의 재시도 정책이 없다.

수정은 다음 순서를 사용한다.

`상품 advisory → product → draft → 기존 character ID순 → 기존 lorebook → 발행 전체 태그 이름순 INSERT/SHARE → 구성요소별 쓰기 → snapshot/release/영수증`

기존 부모를 먼저 잠그므로 단독 콘텐츠 태그 쓰기의 부모→사전 순서도 유지한다. 새 복사본은 commit 전 다른 트랜잭션에 보이지 않는다. 기존 로어북의 공개 소유 조회 결과는 갱신 단계에서 재사용한다.

새 tag 공개 `acquire_tag_names(AcquireTagNamesCommand)`는 **사전 이름 생성과 fencing만 담당하고 None을 반환**한다. 기존 repository의 정렬·배치를 재사용한다. 전체 work·character·lorebook의 이름을 모두 모아 한 번 호출하므로 구성요소별 신규 이름 생성 순서가 교차하지 않는다. 사전 전체를 잠그지 않고, 추가 advisory·전역 배타 잠금·자동 재시도를 도입하지 않았다.

비활성 이름의 선획득은 연결 허가가 아니다. 기존 각 콘텐츠 service가 자기 부모 잠금 아래 읽은 `retained_ids`로 다시 resolve한다. 선획득 ID를 retained_ids로 전달하거나 서로 다른 부모 사이에 공유하지 않는다. 따라서 기존 연결은 유지할 수 있고 새 부모 연결은 거절된다. 관리자 rename/deactivate fencing, 정확한 이름·trim·중복 제거·입력 반환 순서·기존 ID/설명은 유지한다. 선획득·연결·발행 실패는 전체 rollback이다.

## IEA-03 원인과 수정

기존 코드는 영수증을 먼저 확인한 뒤, 현재 문서 digest가 마지막 발행 digest와 같으면 기존 ReleaseInfo를 바로 반환했다. D 발행(rev 1) → E 저장(2) → D 저장(3) → 발행 성공에는 rev 3 영수증이 없었다. 다음 저장(4) 뒤 rev 3 요청은 영수증을 찾지 못하고 CAS 409가 됐다.

정상 발행과 snapshot 재사용 성공이 `_record_publication_receipt`를 공유한다. 현재 expected_revision에 fingerprint와 기존 release 필드를 추가하고 product 공개 `mark_studio_publication`을 같은 트랜잭션에서 호출한다. 저장 실패는 성공으로 바뀌지 않는다. legacy no-op도 기존 `component_mapping`의 서버 ID 채택 경로를 거쳐 영수증을 기록한다. 모호한 legacy 구성의 기존 명시적 migration 충돌 검증은 생략하지 않는다.

기존 mapping을 깊은 복사한 결과에 현재 영수증만 추가하므로 이전 영수증과 구성 ID를 보존한다. 이미 저장된 revision의 같은 요청은 쓰기 없이 기존 결과를 반환하고, 다른 fingerprint는 기존 충돌이다. 소유권 조회와 CAS 순서는 유지하며, no-op에서 구성요소 갱신·freeze·release 생성은 호출하지 않는다. 문서 revision/digest/본문과 과거 snapshot을 수정하지 않는다.

## 이번 변경 파일과 위치

아래 9개가 이 작업의 코드·프로젝트 테스트·소유 문서 변경이다. 새 감사 폴더의 실행기·증거·로그·보고서는 별도 산출물이다. repository SQL과 HTTP 구현은 변경하지 않았다.

| 파일 | 주요 위치·변경 |
| --- | --- |
| `apps/api/app/use_cases/studio_publication.py` | 188 영수증 공통 저장, 262 snapshot 재사용 저장, 302 기존 부모 잠금, 329 전체 태그 선획득, 544 정상 발행 영수증 저장 |
| `apps/api/app/modules/content/tag/types.py` | 39 AcquireTagNamesCommand |
| `apps/api/app/modules/content/tag/service/command.py` | 22 이름 선획득 공개 서비스, 연결 검증과 분리 |
| `apps/api/app/use_cases/ARCHITECTURE.md` | 3 조합의 새 잠금 순서·영수증 책임 |
| `apps/api/app/modules/content/tag/ARCHITECTURE.md` | 3 공개 API 책임·retained_ids 경계 |
| `apps/api/tests/test_studio_publication.py` | 55 legacy 영수증 저장 검증 보강, 83 최초 발행 전체 태그 전달 검증. 기존 성공 기대는 유지 |
| `apps/api/tests/test_studio_republication_contracts.py` | 304 원자적 no-op 영수증/저장 실패/다음 revision 재생, 366 부모→사전→쓰기 순서, 405 선획득 실패 rollback, 426 실제 HTTP 200 재생/409 충돌 |
| `apps/api/tests/test_tag_resolve_batch_contracts.py` | 219 선획득 뒤 inactive retained/신규 거절·정규화·rollback, 255 이름 누락 오류·rollback |
| `apps/api/tests/test_studio_publication_db.py` (신규) | 77 독립 PG 연결/장벽/구 순서 40P01 대조/수정 순서, 192 D→E→D HTTP 영수증·snapshot 검증, 256 관리자 fencing, 280 저장 후 실패 rollback/재시도, 325 부모별 비활성 정책, 383 legacy 매핑 보존 |

정확한 최종 SHA-256은 validation-end.json의 owned_sha256에 기록했다. 공용 검사 설정과 기준선 변경으로 통과시키지 않았다.

## 수정 전후 실행 결과

중복 실행을 합산하지 않는다. collection errors는 아래 모든 pytest 실행에서 0이다.

| 단계·로그 | passed | failed | skipped | setup errors | 판정 |
| --- | ---: | ---: | ---: | ---: | --- |
| 수정 전 기존 감사 HTTP, [before-http-approved](logs/before-http-approved.txt) | 0 | 0 | 0 | 3 | 실제 PG 연결 거부, 결함 assertion 미도달 |
| 수정 전 기존 감사 서비스 studio만, [before-services](logs/before-services.txt) | 0 | 0 | 0 | 3 | 같은 연결 거부, 답변 테스트 4건 deselected |
| 수정 전 새 no-op 계약, [before-receipt-approved](logs/before-receipt-approved.txt) | 0 | 2 | 0 | 0 | 저장 호출 누락, 저장 실패 주입에도 성공 반환으로 실패 |
| 수정 후 초기 집중 검사, [focused-first](logs/focused-first.txt) | 47 | 0 | 0 | 0 | SQL/정책·서비스 대역 검사 |
| 부모 잠금 보강 후 관련 검사, [related-final](logs/related-final.txt) | 233 | 0 | 51 | 0 | 최종 HTTP 추가 전 실행 |
| 새 HTTP 하네스 첫 통합, [related-complete](logs/related-complete.txt) | 233 | 1 | 51 | 0 | unbound AsyncSession에 bind 속성이 없는 하네스 오류 |
| 하네스 수정 후 영수증 계약, [http-contract-final](logs/http-contract-final.txt) | 9 | 0 | 0 | 0 | 실제 router/DTO, 하위 DB 서비스는 대역 |
| **최종 관련 19파일**, [related-verified](logs/related-verified.txt) | **234** | **0** | **51** | **0** | 최종 소스 기준 |
| 수정 후 실제 PG 재시도, [post-pg-unavailable](logs/post-pg-unavailable.txt) | 0 | 0 | 0 | 1 | -x로 첫 setup 오류 후 중단, 나머지 PG 검사는 미실행 |
| **최종 필수 품질**, [quality-verified](logs/quality-verified.txt) | **13** | **0** | **0** | **0** | 패턴·format·lint·mypy 포함 종료 0 |

별도 [test-types-verified](logs/test-types-verified.txt), [test-style-verified](logs/test-style-verified.txt), [test-format-verified](logs/test-format-verified.txt)는 변경 엄격 테스트 3파일의 최종 통과 로그다. 중간 직접 검사에서는 JSON union의 중첩 접근·import 순서, 이후 record(None) 반환값을 사용한 테스트 lambda의 타입 진단이 있었다. 명시적 JSON 근거/검사와 타입 있는 테스트 함수를 사용해 고쳤으며 앱 기준선/ignore를 늘리지 않았다. 중간 2개 타입 진단 로그 [test-types](logs/test-types.txt)도 보존했다.

최초 제한 환경의 PG 실행과 오프라인 asyncio 실행은 출력 없이 대기해 중단했다. 결과·완료 로그가 없어 passed/failed/setup 수로 계산하지 않았다. 이후 같은 실행을 제한 밖에서 수행해 위의 정확한 결과를 얻었다. [environment-notes](logs/environment-notes.txt)에 중단 및 DB/Docker 확인 결과를 구분해 기록했다.

## 실제 PG 하네스와 미실행 범위

실제 PG 실행은 오직 기존 `tools/run_postgres_audit_tests.py`로 시도했다. localhost·전용 DB/계정 이름·URL 범위 검사를 변경하지 않았다. 프로젝트 `.venv/Scripts/python.exe`를 사용했다. 기존 UUID 스키마 fixture를 유지하며 앱 DB migration/초기화/삭제, Docker 볼륨 변경, 외부 LLM/SMTP/S3 요청은 수행하지 않았다.

전용 DB는 `ConnectionRefusedError [WinError 1225]`를 반환했다. 읽기 전용 `docker ps -a`도 Docker Desktop Linux engine pipe 부재로 실패했다. DB/daemon을 새로 만들거나 기동하지 않았다. 연결 전에 setup이 실패하여 이번 PG assertion은 실행되지 않았다. 종료 DB 접속도 불가능하므로 잔여 스키마 0이라고 주장하지 않는다. 다른 작업의 스키마를 조사·삭제하지 않았다.

신규 PG 테스트 11건은 별도 작업 세션/pg_backend_pid, 실행 장벽, 실제 pg_blocking_pids 관찰로 신규 태그 대기를 확인하도록 작성했다. 구 순서 대조는 전체 선획득만 끈 뒤 첫 구성요소 SQL 완료 장벽으로 실제 40P01/HTTP 500을 요구한다. 수정 경로는 전체 선획득 진입 전에 장벽을 두고, 선행 트랜잭션이 상대의 실제 PG 대기를 관찰한 뒤 진행한다. 기존 이름 대조는 양쪽 SHARE 획득 뒤 장벽을 통과한다. 임의 sleep이나 mock 잠금만으로 교착 해결을 판정하지 않는다. polling은 실제 PG 상태 조건을 확인하기 위한 것이며 전체/statement/lock 기한과 task 회수를 둔다.

원래 감사의 신규 이름 테스트는 **첫 개별 resolve SQL 뒤 장벽**을 둔다. 수정 후에는 그 전에 전체 이름 획득에서 상대가 대기하므로 해당 장벽을 그대로 양쪽 통과 조건으로 쓰면 하네스 timeout이 된다. 기존 감사 파일은 수정하지 않았으며, 수정 순서의 PG 검증은 새 프로젝트 테스트가 담당하도록 했다. 이번에는 DB 연결 자체가 안 되어 이 timeout도 실행·관찰된 결과로 집계하지 않는다.

PG가 없어서 미검증인 항목: 실제 40P01의 수정 전/후 비교, 실제 PG 관리자 변경 fencing, 영속 rollback 후 재시도, D→E→D→무변경 발행→다음 저장→HTTP 200 재생의 영속 상태, 실제 snapshot 수/기존 JSON/서버 매핑·영수증 보존. 오프라인 검사에서는 조합 순서, SQLite SQL의 정규화/배치/rollback, 부모별 정책을 전달하는 기존 회귀, 실제 HTTP의 영수증 재생과 충돌을 검증했다. 이 결과를 PG 잠금·내구성 증명으로 대체하지 않는다.

## 재실행

저장소 루트에서 실행한다. 실행기는 TEST_*·DB URL·외부 공급자/SMTP/S3 환경을 제거하고, PG 모드만 기존 범위 검사 실행기가 전용 URL을 주입한다. 고유한 짧은 basetemp와 로그 덮어쓰기 거절, URL/SQL 세부 제거를 사용한다.

```powershell
.venv/Scripts/python.exe docs/audits/2026-11-03-iea-studio-fix/run_checks.py pg rerun-pg-01 apps/api/tests/test_studio_publication_db.py apps/api/tests/test_u25_postgres_concurrency.py apps/api/tests/test_studio_locking_db.py apps/api/tests/test_tag_management_db.py
.venv/Scripts/python.exe docs/audits/2026-11-03-iea-studio-fix/run_checks.py pg rerun-noop-01 docs/audits/2026-11-02-independent-error-reaudit/test_http_publication.py::test_http_noop_publication_replay_after_new_save docs/audits/2026-11-02-independent-error-reaudit/test_reproductions.py::test_noop_publication_retry_must_survive_later_draft_save
.venv/Scripts/python.exe docs/audits/2026-11-03-iea-studio-fix/run_checks.py offline rerun-contract-01 apps/api/tests/test_studio_publication.py apps/api/tests/test_studio_republication_contracts.py apps/api/tests/test_tag_resolve_batch_contracts.py
.venv/Scripts/python.exe docs/audits/2026-11-03-iea-studio-fix/run_checks.py command rerun-quality-01 tools/check_backend_quality.py
```

## 남은 위험과 완료 범위

코드 수정과 실행 가능한 회귀·보고서는 제공했으나, 전용 감사 DB가 다시 가용해진 뒤 위 PG 검사를 실행해야 실제 교착·내구성 수락을 완료할 수 있다. 새 PG 테스트도 이번에는 collection/타입/정적 검사까지만 검증됐다.

전체 이름을 선획득하지 않는 임의 writer 조합, 복잡한 관리자 rename 교차, 다른 PG 격리 수준/collation, 운영 부하·프로세스 종료·물리적 commit 응답 유실, 전체 API·인증 브라우저 E2E·외부 공급자는 검증하지 않았다. 모든 DB 교착 부재나 자동 복구를 보장하지 않는다. legacy 서버 매핑을 안전하게 채택할 수 없는 데이터에는 기존 명시적 충돌 처리가 필요하다. 태그 선획득의 추가 SQL/잠금 시간은 운영 부하로 측정하지 않았다.

commit/push·새 대화·서브에이전트·별도 checkout은 만들지 않았다. 금지 범위의 변경과 공용 검사/기대값/skip 완화는 없다.
