# 패턴 통일 1차: 기준·검사·대표 적용

## 최신 통합 검증·배포 준비 점검 (2026-11-02)

현재 미커밋 변경을 포함한 전체 API는 오프라인 **1706 passed / 446 skipped**,
전용 실제 PostgreSQL·Mailpit 실행은 **2149 passed / 3 skipped / 0 failed**다.
남은 skip은 실제 S3 2건·Voyage 1건이며 실행 간 중복 건수는 합산하지 않는다.
필수 품질(타입 기준선 0·Ruff 388파일·mypy 367소스·13 passed), 웹/관리자 계약
81건·양쪽 typecheck/build, 관리자 합성 API 브라우저 26건과 사용자 production 렌더
20건이 통과했다. 전체 PG의 경고는 Alembic path_separator 20건·Starlette 422 2건이다.

발견한 지갑 온라인 migration 테스트의 CREATEDB 의존·고정 0031 기대값을 격리 스키마와
현재 head 확인으로 고쳤다. 기존 지갑 전체 제약/기본값·잔액 검증은 유지한다.
온라인 head 0036·초기 SQL 026의 76테이블 비교, worker/정리 CLI 4개 빈 큐 실행도
확인했다. payments UNIQUE 이름 1곳의 차이는 별도 기록하고 DDL은 변경하지 않았다.

공통 감사 표의 후속 상태와 U27 추가 정리를 반영하고 누락된 U05 기록을 보완했다.
아래 이전 단계별 수치·미완료 설명은 해당 시점 기록이다. U19 재설계와 U28 잔여
잠금/deadline, 외부 공급자/S3·운영 HTTPS·실제 사용자 웹/API E2E는 여전히 별도다.
운영 배포·앱 DB 변경·commit/push는 수행하지 않았다.
[최신 통합 점검](../../deployment-readiness-2026-11-02.md)과
[운영 절차](../../operations-runbook.md)에 명령·증거·한계를 연결했다.

## U27 사용 조사·안전한 정리 (2026-11-02)

1차에서 미사용 0바이트 파일 5개를 제거했다. 비서비스 상태라는 사용자 지시에 따른
후속 정리에서는 호출부를 현재 소유 경로로 옮기고 호환 파일 7개를 추가 제거했다.
content 3개 dependency 파일, lorebook constraints, product 통계 조회 재노출,
LLM replacement 재노출, use_cases conversation_directory가 대상이다.
미사용 BaseLLMAdapter 별칭과 billing의 크레딧 모델 3개 재노출도 제거했다.
FK·migration·실제 읽기/검증에 연결된 legacy 코드와 견적 JSON의 가격 정책은 유지한다.
오래된 Python 호환 경로는 더 이상 제공하지 않으며 HTTP·DB·저장 JSON 계약은 유지한다.

OpenAPI 84경로·114연산 전체 JSON, ORM 76테이블의 PostgreSQL DDL/인덱스,
58개 모델 export가 전후 동일했다. 후속 실행 진입점 8개 import, 필수 품질 검사
(기준선 0·Ruff 388파일·mypy 367소스·아키텍처/패턴 13건), 관련 회귀
**364 passed / 0 failed / 0 skipped**, 전체 테스트 **2152건 수집**이 통과했다.
삭제 후보의 AST 참조는 23곳에서 0건이 됐다. 실제 DB/외부 공급자는 실행하지
않았다. 조사 범위·사용 근거·환경 제약과 재실행 명령은 [U27 작업 기록](U27-WORKLOG.md)에 있다.

작업일: 2026-10-26, Asia/Seoul. 기준 HEAD: `f6d456c4f6b1767581261cbb45fb3430b9d56079`.
시작 시 추적 파일 변경은 없었다. 기존 tmp 일부의 접근 권한 경고는 있었으며 해당 파일을 건드리지 않았다.

## U24 관리자·검수 권한 연결 (2026-11-02)

제공 기능·역할 정책을 [권한 문서](../../admin-authorization.md)로 확정하고 기본 앱의
관리자·검수 훅 5개를 검증된 사용자 UUID와 최신 DB 활성 admin 인가에 연결했다.
인가 조회는 별도 세션에서 종료해 상태 변경 트랜잭션과 충돌하지 않는다. 독립 라우터의
미설정 503, 기존 owner 훅 정체성·경로·DTO 및 상태 변경의 소유자 제한을 유지한다.
토큰/세션/CSRF와 일반 사용자·정지 관리자·미설정·외부 인증 주입의 거절을 검증했다.
구현·실행 결과와 실제 DB 검증 한계는 [U24 작업 기록](U24-WORKLOG.md)에 기록한다.

## 완료 범위

이번 변경은 전체 패턴 통일의 기반과 대표 적용 단계다. 기존 계층/모듈 구조를 유지한다.
감사 보고서 U01~U29의 기능·동시성 결함 수정 완료를 의미하지 않는다.

1. [소스 기준](source-baseline.json)에 수정 전 애플리케이션 Python 363개 파일의 SHA-256과 타입 표기 현황을 기록했다.
2. [코드 작성 규칙](../../../references_document/reference/backend-code-conventions.md)에 역할별 변수명, 타입, 데이터 표현, 함수/클래스, 검증/오류, 자원 수명, 조회/시간, 로그 및 점진 적용 기준을 정의했다. 상위 아키텍처와 AGENTS.md에서 연결한다.
3. 기존 규칙 문서가 `.gitignore`에 가려져 있어 상위 규칙과 작성 규칙 두 파일만 제외 규칙의 예외로 지정했다. 다른 로컬 참고 문서는 공개하지 않는다.
4. `app.db.types.SessionFactory`를 추가하고 답변·기억·인증·캐릭터/상품 미디어의 세션 생성 의존성에 적용했다. 기존 `sessions` 인자/속성은 호환 예외로 명시했다.
5. tag 사전 CRUD의 입력/반환/mapper 타입, 이름별 사전 명명, Command 키워드 호출을 정리했다. mapper는 존재/미존재를 overload로 구분한다.
6. chat의 기억 workflow 내부 함수까지 입력·반환 계약을 명시했다. 기존 원문 tuple, 요약/색인/완료 순서와 재시도 정책은 유지했다.
7. 전체 소스의 새 시그니처 진단을 막는 검사와, 7개 기준 파일의 Ruff/mypy 검사를 연결했다. 아키텍처/API 계약 검사와 새 검사기의 5개 테스트도 실행한다.

## 보존한 계약과 타입 선택

- 외부 API 필드/상태 코드, DB 모델/마이그레이션, 저장 JSON, digest, 잠금 순서, 요약 정책은 변경하지 않았다.
- SessionFactory는 `Callable[[], AbstractAsyncContextManager[AsyncSession]]`이다. 실제 async_sessionmaker 할당도 mypy로 별도 확인했다. 단순 Callable이나 await 가능한 함수와 구분한다.
- tag repository의 `session.scalar(stmt)`를 typed `session.scalars(stmt).first()`로 표현했다. SELECT/UPDATE 조건·잠금·execution_options·SQL 횟수 및 첫 결과/None 의미는 동일하다.
- tag update/deactivate의 결과는 선행 존재 확인과 같은 트랜잭션의 FOR UPDATE로 확보된다. service의 두 cast는 이 불변 조건을 표현한다. 새로운 오류 정책이나 자동 기본값을 넣지 않았다.
- 타입 검사는 설치 런타임/.python-version/API Docker와 같은 3.12를 사용한다. 설치된 NumPy stub이 3.12 구문을 사용해 3.11 타입 검사에서는 파싱 오류가 났다. 패키지 최소 버전은 변경하지 않았고 Ruff 구문 기준은 3.11이다.
- mypy는 `follow_imports=silent`로 관련 모듈의 타입을 읽되 해당 의존 모듈의 기존 오류를 이번 범위의 오류로 출력하지 않는다. 전체 애플리케이션 strict typing을 통과했다는 뜻은 아니다.

## 진단과 검증

함수/메서드/중첩 함수 전체를 집계한다. 새 mapper overload 두 개도 함수 정의로 집계된다.

| 항목 | 변경 전 | 변경 후 |
|---|---:|---:|
| Python 파일 | 363 | 364 |
| 함수/메서드 정의 | 1,368 | 1,370 |
| 반환 타입 미표기 | 375 | 360 |
| self/cls 외 매개변수가 있는 정의 | 1,277 | 1,279 |
| 입력 타입 일부 미표기 정의 | 597 | 571 |
| 시그니처 진단 항목 | 1,598 | 1,533 |

시그니처 진단은 함수 개수가 아니라 경로/심볼/인자·반환/규칙 조합이다. 미표기, bare generic,
직접 Any 표기를 포함한다. 줄 번호를 키로 쓰지 않아 포맷 변경으로 기준선이 바뀌지 않는다.
같은 개수의 새 결함으로 대체해도 실패한다. 해결된 65개는 기준선에서 제거했다.
이 검사는 함수 시그니처의 구문 검사이며 모든 별칭의 의미, 지역/클래스 필드 타입,
업무 변수명의 적합성, 경쟁 실행 안전성을 증명하지 않는다.

| 실행 | 결과 |
|---|---|
| 업무 코드 변경 전 전체 pytest | 501 passed, 1 failed, 288 skipped |
| 변경 후 전체 pytest | 503 passed, 1 failed, 288 skipped |
| 통합 품질 명령 | 전체 시그니처 기준선 검사 통과, Ruff 포맷/린트 7파일 통과, mypy 7파일 통과, 계약/검사기 13테스트 통과 |
| 실제 세션 팩토리의 타입 대입 | async_sessionmaker → SessionFactory 확인 통과 |

변경 전 실행에는 초기 검사 도구 테스트 3개, 변경 후에는 5개가 포함된다. 기존 업무 테스트의
통과/실패 결과는 동일하다. 실패는 `test_edit_after_first_publication_does_not_change_product_visibility`의
SimpleNamespace에 `product_id`가 없는 기존 fixture 오류다. 기대 계약을 임의로 변경하지 않았다.

테스트 자식 환경에서는 TEST_DATABASE_URL을 제거했고, PostgreSQL 통합 테스트는 수행하지 않았다.
건너뛴 검사를 통과로 계산하지 않는다. SDK/S3/SMTP/브라우저 운영 검증도 수행하지 않았다.
Windows 샌드박스에서는 asyncio socketpair 생성이 accept에서 멈추고 pytest 임시 경로 생성도
제한되어, 동일 검사를 일반 실행 환경에서 재실행했다. 애플리케이션/테스트의 이벤트 루프를
다른 구현으로 바꾸어 우회하지 않았다. 불필요한 외부 pytest 플러그인 자동 로딩은 끄고
전체 실행에서는 pytest_asyncio/anyio 플러그인만 명시했다.

집계와 결과는 [verification-results.json](verification-results.json)에 저장했다.
원시 실행 로그 `pytest-before.log`, `pytest-after.log`, `quality-after.log`는 이 폴더에 로컬 보존하며
기존 *.log 제외 정책을 유지한다.

## 재실행

저장소 루트에서:

```powershell
.venv/Scripts/python.exe tools/check_backend_quality.py
.venv/Scripts/python.exe tools/check_backend_patterns.py --inventory
```

가상환경이 활성화되어 있으면 `pnpm api:quality`도 같은 명령이다.
정리한 진단 제거는 `--prune-baseline`을 사용한다. 새 진단이 있으면 기준선 수정 없이 실패한다.

전체 회귀 확인(실제 DB 없이):

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'apps/api')
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p anyio.pytest_plugin -p no:cacheprovider apps/api/tests -q --tb=short
```

## 기반 도입 당시 남은 순서

| 단계 | 상태/완료 기준 |
|---|---|
| 현재 상태 기록·규칙 확립 | 완료 |
| 기준 CRUD/workflow·검사 도입 | 완료 |
| 모듈별 적용 확대 | 진행 중. memory 전체, chat 조회/mapper, lorebook CRUD/query/repository/mapper 및 character 기본 CRUD 경계·query/persistence/schema mapper 정리를 적용했다. character command/repository/types 전체, chat 쓰기·나머지 repository/types, lorebook 활성화·태그 service 등은 후속 범위다. 각 범위에서 실제 타입과 테스트를 확보한 뒤 엄격 검사 대상에 추가한다. |
| 고위험 계약 정리 | 미완료. 잠금/트랜잭션/오류/재시도 변경은 감사 결함 재현과 함께 진행한다. |
| 감사 결함 수정 | 미착수. U01/U02 우선순위 유지. 남은 진단 정리가 끝날 때까지 핵심 결함을 무기한 미루지 않는다. |

전역 정규식으로 session 타입을 채우거나, 검사 실패를 Any/cast/ignore로 일괄 감추지 않는다.
기준선은 남은 작업의 명시적 목록이며 영구 면제 완료 목록이 아니다.

## 모듈별 적용 1차: memory (2026-10-26)

위 기반 도입 시점의 수치와 verification-results.json은 이전 검증 기록으로 유지한다.
이번 범위는 chatting/memory 전체 14개 Python 파일이며, 기존 파일·계층 구조를 유지한다.

- 저장·예약·무효화 서비스와 repository의 세션 입력에 AsyncSession을 명시했다.
  삭제 대상 대화 ID는 UUID, mapper 입력은 MemoryPageRow 또는 Entity/점수 쌍의 Iterable이다.
- EmbeddedSummaryInfo.settings의 bare dict를 EmbeddingSettings TypedDict로 바꿨다.
  기존 부분 dict 입력을 표현하도록 키를 선택적으로 두며 현재 생성기는 네 키를 모두 기록한다.
  실행 시 검증, JSON 값/키 변경, 모델/토큰/재시도 정책 변경은 없다.
- 최신 요약·미인덱싱 요약·임베딩 저장의 SQL은 유지하고 결과 추출을 scalars(stmt).first()로
  표현했다. 기존 첫 행 또는 None 반환과 populate_existing 옵션을 유지한다.
- 재시도 지연 지역 변수 delay를 retry_seconds로 바꿔 단위를 드러냈다.
- 엄격 검사 범위에 memory 디렉터리를 추가했다. 이후 해당 폴더의 새 파일도 검사한다.
  새 Any/cast/ignore를 추가하지 않았고 해결된 시그니처 진단 16개만 기준선에서 제거했다.

| 검증 | 결과 |
|---|---|
| 변경 전 memory 업무 테스트 | 27 passed, 1 skipped |
| 변경 후 memory 업무 테스트 | 29 passed, 1 skipped |
| 전체 API 회귀 | 505 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,517개, 새 위반 없음; Ruff 통과; mypy 21 source files 통과; 계약/검사기 13 passed |

추가된 두 테스트는 SQLite에서 pending/failed 조회의 정렬·소유권·빈 결과와,
임베딩 저장의 revision 가드·ready 재저장 거절·기존 ORM 객체 갱신·JSON 보존을 확인한다.
기존 전체 테스트 실패는 여전히 studio fixture의 product_id 누락이며 새 실패는 없다.
TEST_DATABASE_URL을 제거한 오프라인 실행으로, PostgreSQL/pgvector 실제 실행과 외부 공급자
연동은 검증하지 않았다. 잠금·lease·토큰 예산 관련 감사 결함은 이번 타입 정리의 완료 범위가 아니다.

## 모듈별 적용 2차: chat 조회·mapper (2026-10-26)

`chat/service/query`와 `chat/mapper`의 10개 Python 파일을 엄격 검사 범위에 추가했다.
이들이 사용하는 repository 조회 시그니처와 공개 통계 tuple 요소 타입도 보완했다.
폴더 구조나 공개 함수 이름·키워드 인자, HTTP 입력/출력 형식은 변경하지 않았다.

- 조회의 session은 AsyncSession, 미리보기 반환은 UUID→str, 활동 반환은 UUID→Info로 명시했다.
- repository에 SQL Row/집계 쌍의 타입 별칭을 두었다. 원래 SQL Row 반환과 공개 list/tuple을
  유지하고, 생성 단건 조회는 같은 SQL·잠금 옵션으로 scalars(stmt).first()를 사용한다.
- 메시지·생성 상태·프롬프트의 getattr 기반 일괄 복사를 명시적 필드 매핑으로 바꾸었다.
  메시지 페이지와 기억 원문이 단건 변환을 재사용한다. None 반환은 overload로 구별한다.
- 프롬프트 목록의 선택 컬럼 순서와 mapper 입력을 연결했다. 원문 누락은 nullable 값으로
  유지한다. COUNT 쿼리는 GROUP BY가 없어 빈 범위에서도 non-null 한 행을 반환한다는
  불변 조건을 assert로 명시했다. 새로운 입력 검증이나 오류 은폐는 추가하지 않았다.
- 커서 지역 변수 value/cid를 message_cursor/cursor_conversation_id로 바꿨다.
  새 Any/cast/ignore 없이 기존 시그니처 진단 91개를 제거했다(1,517 → 1,426).

| 검증 | 결과 |
|---|---|
| 기존 관련 테스트, 변경 전·후 | 각각 42 passed, 16 skipped |
| 추가 회귀 테스트 | 4 passed |
| 전체 API 회귀 | 509 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,426개, 새 위반 없음; Ruff 통과; mypy 31 source files 통과; 계약/검사기 13 passed |

추가 테스트는 메시지 페이지/기억 원문 일치, 커서 왕복과 종료 경계, 매핑 후 메시지 변경 격리,
공개 통계 tuple/미기록 상태의 0건, 실제 SQLite SQL Row의 프롬프트 필드 대응·OUTER JOIN·
빈 목록을 확인한다. 최소 테스트 테이블에는 원문/answer_metadata 컬럼 자체가 없어 목록의
비민감 projection 유지도 확인한다. PostgreSQL 동시성·잠금 검증을 대체하지 않는다.

전체 테스트의 유일한 실패는 기존 studio fixture의 product_id 누락이다. TEST_DATABASE_URL을
제거했으므로 실제 PostgreSQL과 외부 공급자 연동은 미검증이다. repository 단독 mypy에는
이번에 정리하지 않은 쓰기/기타 함수의 기존 진단 16개가 남는다. repository/types 전체나
chat 전체의 패턴 통일을 완료한 것으로 해석하지 않는다.

## 모듈별 적용 3차: lorebook CRUD·조회 (2026-10-26)

`repository.py`, `service/command.py`, `service/query.py`, `mapper/`의 8개 Python 파일을
엄격 검사 범위에 추가했다. 기존 폴더와 LorebookSchemaMapper 클래스, 공개 호출 계약을 유지한다.

- 생성/수정/삭제·발행 저장소의 반환, 세션·UUID 목록·잠금 플래그·태그 연결 입력을 명시했다.
  저장소 반환 누락 때문에 서비스 결과에 전파되던 Any를 제거했다.
- 원본·항목·스냅샷 및 태그 mapper에 실제 Entity/Info의 Iterable 타입을 지정했다.
  태그 HTTP mapper에도 UUID/DTO/Info 입력과 반환 타입을 명시하고 Command는 키워드로 생성한다.
- Info 순회 변수 entity는 entry_info, 태그 사전 by_id는 tags_by_id,
  연결 정렬 지역 변수 order는 sort_order로 바꿨다.
- 태그 대상 조회의 scalar를 scalars(...).first()로 표현했다. SQL·잠금·populate_existing을
  유지하며, 기존 객체 갱신과 미존재 None을 SQLite에서 lock 옵션 두 경우로 검증했다.
- 진단 결과·활성 항목 mapper의 값 전달 경계는 dict[str, object]로 표현한다.
  활성화/스냅샷 필드별 타입 계약과 실행 검증의 완성으로 보지 않는다. 실행 정책은 유지한다.
- 새 Any/cast/ignore나 기준선 예외를 추가하지 않고 진단 83개를 제거했다(1,426 → 1,343).

| 검증 | 결과 |
|---|---|
| 변경 전 lorebook 4개 테스트 파일 | 77 passed |
| 변경 후 lorebook 및 태그 관리/스키마 테스트 | 97 passed, 4 skipped (신규 회귀 2건 포함) |
| 전체 API 회귀 | 511 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,343개, 새 위반 없음; Ruff 통과; mypy 39 source files 통과; 계약/검사기 13 passed |

유일한 전체 실패는 기존 studio fixture의 product_id 누락이다. TEST_DATABASE_URL을 제거한
실행이며 PostgreSQL 잠금/동시성과 외부 연동은 미검증이다. 기존 테스트는 소유권·부모 잠금 요청,
입력 검증·트랜잭션 종료, embedding 보존, 스냅샷 활성화/깊은 복사와 HTTP 변환을 확인한다.
새 SQLite 검사는 잠금 옵션 전달 시 조회 결과를 확인할 뿐 실제 FOR UPDATE 경쟁을 증명하지 않는다.
남은 lorebook 범위는 types의 스냅샷 JSON, activation/tags service, HTTP 라우터 등이다.

## 모듈별 적용 4차: character 기본 CRUD 경계·조회·mapper (2026-10-27)

시작 시 staged/unstaged 변경과 기존 character 미디어 SessionFactory 적용을 확인하고
보존했다. 기본 CRUD의 저장소→서비스 반환과 조회→mapper 입력을 우선 정리했다.
파일 분리·새 클래스를 도입하지 않았고 외부 작업의 수명과 결합된 미디어는 별도 범위로 남겼다.

- 생성/수정/상태 변경 저장소 반환은 Character, 삭제는 None으로 명시했다. 기존
  Command/Info 필드는 이미 구체적이어서 기본 CRUD의 공개 타입 구조를 바꾸지 않았다.
  생성·수정·상태 변경 서비스로 전파되던 반환 Any 오류 3개를 해소했다.
- 서비스의 Entity/Info 지역 변수 역할을 구분하고 생성 시 PublicTagsCommand를 키워드로
  구성했다. 소유권 검사, 선택 필드 해제, 상태 변경, 삭제 LookupError, 트랜잭션·잠금·
  재조회·flush 순서는 유지한다. SQL과 populate_existing 정책도 변경하지 않았다.
- 소유 목록·스냅샷 조회/발행 경계에 AsyncSession, UUID tuple, bool 및 반환 타입을 명시했다.
  persistence mapper에는 실제 Entity/Row/Iterable 입력을 지정했다.
- SnapshotMediaManifestItem은 실제 이미지 4필드/에셋 5필드 tuple을 나타낸다. 저장 JSON을
  변경하지 않으며, frozenset·중복 제거·is_default 제외·URL/출처 ID 비교 의미를 보존한다.
  스냅샷 JSON의 깊은 복사와 원본 삭제 후 character_id=None도 유지한다.
- 새 Any/cast/type: ignore를 추가하지 않았다. 기존 Literal cast는 모델 CHECK 제약과
  일치함을 확인해 근거를 주석으로 남겼다. snapshot_data의 bare dict는 여전히 후속 과제다.
- query.py, mapper/persistence.py, mapper/schema.py의 **3개 파일**이 실제 Ruff/mypy 검사를
  통과한 뒤 strict scope에 추가됐다. schema mapper는 기존 계약을 검토하고 검사 대상에
  추가했으며 코드 변경은 없었다. 해결된 시그니처 진단 **23개만 제거했다(1,343 → 1,320)**.

| 검증 | 결과 |
|---|---|
| 변경 전 character command/query | 43 passed |
| 변경 후 character command/query/mapping/media, 태그 관리/DB/스키마, product lifecycle/integration | 63 passed, 51 skipped |
| 전체 API 회귀 | 513 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,320개, 새 위반 없음; Ruff 43파일 통과; mypy 42 source files 통과; 계약/검사기 13 passed |
| 미완료 범위 별도 진단 | command.py 2개, repository.py 19개, types.py 1개 mypy 오류 잔존; strict scope에서 제외 |

test_character_mapping.py의 신규 2개 테스트는 보존 스냅샷 JSON의 중첩 변경 격리와
발행 비교 값의 기존 형태/중복/기본 이미지 무관성/URL 변경 감지를 확인한다. 기존 업무
테스트는 입력·소유권·commit/rollback·선택 필드 해제·상태 보존·커서 및 조회 범위를 검증한다.

전체 테스트의 유일한 실패는 이전과 같은
test_studio_draft_guard.py::test_edit_after_first_publication_does_not_change_product_visibility의
SimpleNamespace.product_id 누락이다. 관련 없는 fixture를 수정하거나 테스트를 약화하지 않았다.
TEST_DATABASE_URL을 제거한 오프라인 실행이고, 기존 Windows asyncio 제한 기록에 따라
테스트/필수 품질 검사는 require_escalated로 실행했다. skipped는 통과가 아니며 실제
PostgreSQL 잠금·동시성·pgvector와 외부 서비스 연동은 검증하지 않았다.

**완료 경계:** character 기본 CRUD의 반환·명명 및 query/persistence/schema mapper의 엄격
검사 적용이다. command.py 전체에는 _attach_character_media에서 오는 반환 Any 오류 2개가
남는다. 이를 cast/예외로 숨기거나 검사 통과만을 위해 파일을 쪼개지 않았다. repository의
next_version·미디어/태그 함수와 types의 JSON 구조, media/tags service·HTTP 라우터는 미완료다.
follow_imports=silent이므로 의존 파일 전체의 타입 검증 완료로 해석하지 않는다.

**당시 제안한 다음 순서(아래 사용자 결정으로 변경됨):** 감사 U01(요약 요청 후 진행 불능), U02(계정 전환 후 이전 응답 혼입)의 재현과
수정을 우선한다. 모든 타입 부채 해소를 선행 조건으로 두지 않는다. 다음 character 패턴 단계는
미디어 첨부의 image/asset 입력·반환 분기 계약과 repository 의존 범위를 좁게 정리한 뒤
command 전체를 strict scope에 넣는다. 외부 저장 종료 대기·잠금 정책 변경은 U08/U28의
별도 설계/회귀 검증과 함께 다룬다. 이번 작업은 감사 결함 수정 완료를 뜻하지 않는다.

## 타입 정리 우선 1차: character 미디어·저장소 (2026-10-27)

사용자가 남은 타입 진단 정리를 먼저 진행하도록 선택했다. 현재 우선순위는 타입 계약의
점진적 정리이며, 위 U01/U02 우선 제안은 적용하지 않는다. 감사 결함 수정은 별도 작업으로
남긴다. 기존 staged/unstaged 작업을 유지한 상태에서 다음 5개 파일을 엄격 검사에 추가했다.

- service/command.py: 미디어 첨부 반환 타입 전파로 남아 있던 오류 2개 해소.
- service/media.py: 세션·업로드 지문·저장소 선택을 명시하고 image/asset 입력과 반환을
  overload 및 분기로 연결. 잠근 예약 행이 상태 갱신 뒤에도 존재함을 assertion으로 명시.
- service/workflow/media.py: 공급자 종료 대기의 입력 Coroutine과 반환을 같은 TypeVar로 연결.
- repository.py: 버전 계산, 미디어 및 태그 저장/조회 함수의 입력·반환을 명시.
  image/asset 조회·생성의 반환을 overload로 구별하고 참조 조회의 범위를 명시적 분기로 표현.
- mapper/media.py: 미존재 None과 존재 Info를 구별하고 ORM 필드를 명시적으로 매핑.

미디어 생성도 getattr 기반 dataclass 일괄 복사에서 명시적 필드 전달로 바꿨다.
첨부의 isinstance assertion은 내부 kind/Command 쌍의 불변 조건을 표현한다. 유효한 공개
호출의 소유권·콘텐츠 타입·binding·URL 검사와 신규/재전송/삭제된 연결 결과는 유지한다.
태그 대상 조회는 동일한 SQL·잠금·populate_existing을 scalars(...).first()로 표현했다.
저장소 I/O 순서, 트랜잭션 소유권·잠금 수명·취소 후 종료 대기 정책은 바꾸지 않았다.

새 Any/cast/type: ignore나 기준선 예외 없이 해결된 시그니처 진단 **82개를 제거했다
(1,320 → 1,238)**. 이 수치는 시그니처 검사 기준선이며 전체 mypy 오류 수는 아니다.

| 검증 | 결과 |
|---|---|
| 변경 전 character command/query/mapping/media 및 media HTTP | 47 passed, 30 skipped |
| 신규 첨부/참조 범위 및 기존 command 회귀 | 33 passed (신규 7건 포함) |
| 전체 API 회귀 | 520 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,238개, 새 위반 없음; Ruff 48파일 통과; mypy 47 source files 통과; 계약/검사기 13 passed |

신규 테스트 6건은 image/asset 각각의 신규 첨부·재전송·삭제된 연결의 결과와 생성 여부를
확인한다. 나머지 SQLite 테스트는 정리 작업의 전체 참조와 허가된 스냅샷 범위, 빈 목록,
다른 스냅샷 및 미참조 미디어를 구별한다.

전체 테스트의 유일한 실패는 이전과 같은 test_studio_draft_guard.py의
test_edit_after_first_publication_does_not_change_product_visibility이며 fixture의
SimpleNamespace.product_id 누락이다. 이번에 수정하지 않았다. TEST_DATABASE_URL을
제거한 오프라인 실행이고 실제 PostgreSQL 잠금·동시성 및 외부 저장소는 미검증이다.
Windows 실행 제한 때문에 테스트/품질 검사는 require_escalated로 수행했다.

**완료 경계와 다음 순서:** character command/repository/media의 엄격 검사 적용까지다.
전체 백엔드 타입 정리는 아직 완료되지 않았다. 다음은 character 태그 service/mapper와
types의 JSON 경계를 점검하고, 의존 관계에 따라 남은 모듈을 같은 방식으로 확장한다.
JSON 타입을 임의로 넓히거나 진단 예외를 늘려 통과시키지 않는다. follow_imports=silent이므로
의존 파일 전체가 검증됐다고 해석하지 않는다. U01/U02 등 감사 결함은 별도로 남아 있다.

## 타입 정리 우선 2차: character 태그·스냅샷 JSON (2026-10-27)

service/tags.py, mapper/tags.py, mapper/tag_schema.py, types.py의 4개 파일을 엄격
검사에 추가했다. 기존 폴더·공개 함수명·Command 필드와 위치 인자 호환을 유지한다.

- 세션·UUID·Command·Info 반환을 명시하고 Entity/Info 목록 입력을 Iterable로 표현했다.
  반환 tuple/list와 순서는 유지한다. by_id/retained/requested/protected/actor 지역 이름을
  tags_by_id/retained_tag_ids/requested_tag_ids/protected_tag_ids/actor_id로 구체화했다.
- 내부 관리자/시스템 태그 함수는 Command와 source의 대응을 overload로 명시한다.
  관리자 분기에는 해당 Command 불변 조건을 assertion으로 표현했다. 시스템의 공개
  쓰기는 기존처럼 추가 경로만 호출하며 관리자 지정 태그의 덮어쓰기/삭제 보호를 유지한다.
  Command 구성은 키워드 인자를 사용한다. 잠금·인가·트랜잭션·비활성 태그 정책은 유지한다.
- snapshot_data의 bare dict를 재귀 JSON 값으로 바꿨다. 새 v2 본문은 별도 TypedDict로
  name/description/persona_prompt를 표현하고 repository에서 getattr 없이 직접 저장한다.
  읽기에는 과거/확장 필드를 포함한 전체 JSON과 deepcopy를 유지한다. 읽기 데이터가 v2로
  검증됐다고 주장하지 않으며, 공유 ORM SnapshotMixin의 기존 Any 선언도 남아 있다.

새 Any/cast/type: ignore나 예외를 추가하지 않고 시그니처 진단 **54개를 제거했다
(1,238 → 1,184)**. 기준선은 함수 시그니처를 세므로 types의 필드 타입 수정은 이 감소 수에
포함되지 않는다. 시작 시 대상 4파일의 mypy 진단 34개는 해소됐다.

| 검증 | 결과 |
|---|---|
| 변경 전 태그 관리/DB/스키마, character mapping/command | 46 passed, 11 skipped |
| 전체 API 회귀 | 522 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,184개, 새 위반 없음; Ruff 52파일 통과; mypy 51 source files 통과; 계약/검사기 13 passed |

신규 2건은 repository의 스냅샷 생성과 mapper 결과에서 v2 필드 구성, description의
None/빈 문자열 구별, 원문 공백, 버전 증가 및 사전 복사를 확인한다. 세션은 mock이며
실제 DB 동시성 검증이 아니다. 기존 테스트가 태그 인가·보호·정렬·롤백·HTTP 경계와
스냅샷 확장 필드의 중첩 변경 격리를 확인한다.

전체 테스트의 유일한 실패는 이전과 같은 studio fixture의 SimpleNamespace.product_id
누락이다. 해당 fixture는 수정하지 않았다. TEST_DATABASE_URL을 제거한 실행이고,
PostgreSQL 잠금·동시성 및 외부 서비스 연동은 미검증이다. Windows 실행 제한 때문에
필수 품질 검사와 회귀 테스트는 require_escalated로 수행했다.

**다음 범위:** character의 HTTP 경계(router/tag_router 및 관련 조립 의존성)를 점검한다.
현재 character의 시그니처 기준선에는 tag_router 반환 누락 4개가 남는다. 기준선 감소만으로
HTTP 경계 전체의 mypy 통과를 단정하지 않는다. 이후 lorebook의 태그/활성화 및 JSON 경계를
이어 정리한다. 전체 백엔드 타입 정리와 감사 결함 수정은 아직 완료되지 않았다.

## 타입 정리 우선 3차: character HTTP 경계 (2026-10-27)

character/tag_router.py의 반환 누락 4곳을 해결했다. 조회·추가·교체는 DTO list, 삭제는
None이다. 일반 router의 value 지역 변수는 command로 구체화했고, 태그 Command의
대상·소유자·태그 ID는 키워드로 구성한다. 공개 인자명·경로·응답 모델·인증 훅은 유지한다.
공유 http/dependencies.py의 errors도 Iterator[None]으로 명시했다. 오류 번역 동작은 유지한다.

기존 character 개별 파일 목록을 모듈 디렉터리 전체로 확장했다. schemas/dependencies의
호환 재노출 파일도 검사하며 http/character_dependencies.py, http/contracts/character.py,
http/contracts/tags.py, http/dependencies.py를 직접 검사 범위에 추가했다. 기존 타입이
충분한 파일은 검증 후 범위에 포함했으며 억지로 코드 변경을 만들지 않았다.

새 Any/cast/type: ignore나 예외 없이 시그니처 진단 **5개를 제거했다(1,184 → 1,179)**.
character 모듈의 시그니처 기준선 항목은 0개다. 전체 백엔드의 완료를 의미하지 않으며
follow_imports=silent인 의존 파일에는 별도 진단이 남을 수 있다.

| 검증 | 결과 |
|---|---|
| 변경 전 character 전체 및 관련 HTTP 3파일 mypy | 21 source files 중 tag_router의 반환 누락 4개 |
| 신규 HTTP 회귀 | 8 passed (전체 API 실행에 포함) |
| 전체 API 회귀 | 530 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,179개, 새 위반 없음; Ruff 63파일 통과; mypy 61 source files 통과; 계약/검사기 13 passed |

새 테스트는 FastAPI의 실제 요청/응답 처리를 거쳐 태그 4개 경로의 JSON/204 빈 본문,
OpenAPI의 204 content 부재, 신뢰된 owner/session 전달, LookupError/ValueError의 404/422,
미설정 DB/owner 의존성 각각의 503 및 서비스 미호출을 확인한다. 서비스 mock을 사용하므로
실제 DB 정책 검증을 대체하지 않는다.

전체 실패 1건은 기존 test_studio_draft_guard의 SimpleNamespace.product_id 누락이다.
TEST_DATABASE_URL을 제거했고 실제 PostgreSQL·외부 서비스는 미검증이다. Windows 실행
제한 때문에 필수 품질 검사와 전체 회귀는 require_escalated로 수행했다.

**다음 범위:** lorebook 태그/활성화 서비스 및 JSON 타입 경계를 정리한다. 타입 정리 우선
방침을 유지하며 U01/U02 등 감사 결함 수정은 별도 작업으로 남긴다.

## 타입 정리 우선 4차: lorebook 태그·활성화·JSON 경계 (2026-10-27)

service/tags.py, service/activation.py, types.py를 엄격 검사 범위에 추가했다.
기존 query/persistence mapper도 새 계약을 연결하도록 보완했다. 시작 시 세 파일의
mypy 진단 30개를 해소했고 시그니처 진단 **44개를 제거했다(1,179 → 1,135)**.
types의 필드 타입 보완은 함수 시그니처 기준선의 감소 수에 포함되지 않는다.

- 태그 서비스에 세션·UUID·Command·Info 타입을 명시하고 character의 관리자/시스템
  overload와 같은 패턴을 적용했다. 지역 이름을 retained_tag_ids/requested_tag_ids/
  protected_tag_ids/actor_id로 구체화하고 Command는 키워드로 구성했다.
- 활성화 옵션, 스냅샷 본문/항목, 진단 결과를 TypedDict로 표현했다. 과거 선택 필드,
  확장 필드, metadata 및 깊은 복사를 보존한다. 진단 사유·순서·바이트 추정값의 타입을
  명시했고 메시지/수동 ID는 Sequence로 표현했다.
- 옵션 정렬의 order는 기존 검증 후 채워진 기본값을 직접 읽는다. nullable token_budget은
  같은 조건 안에서 지역 변수로 좁혀 비교한다. 선택·정렬·예산·그룹 처리 순서는 유지한다.
- cast 3곳은 기존 JSONB 저장 계약, 실제 검증을 마친 옵션, id만 제거한 생성 요청 필드에
  한정하고 근거를 주석으로 남겼다. Any/type: ignore/기준선 예외는 추가하지 않았다.
  저장 JSON의 버전별 런타임 검증이나 공유 ORM mixin의 기존 Any까지 해소한 것은 아니다.
- query/ARCHITECTURE의 오래된 설명을 기존 v1 옵션/수동 선택 구현에 맞게 보완했다.
  이번 타입 정리에서 새로운 활성화 정책을 도입한 것은 아니다.

| 검증 | 결과 |
|---|---|
| 관련 lorebook/활성화/워크플로/태그 기존 테스트, 변경 전·후 | 각각 91 passed, 3 skipped |
| 신규 회귀 | 8 passed (전체 API 실행에 포함) |
| 전체 API 회귀 | 538 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,135개, 새 위반 없음; Ruff 66파일 통과; mypy 64 source files 통과; 계약/검사기 13 passed |
| lorebook 전체 추가 mypy 점검 | 20파일 중 tag_router 반환 누락 4개 잔존 |

신규 회귀는 옵션의 기존 버전 비교(1/1.0/True), 입력 비변경·기본값, 불리언/정수 구별과
알 수 없는 옵션 거절, mapper→활성화에서 원본 삭제/누락 선택 필드/확장 필드와 깊은 복사,
초안의 알 수 없는 생성 필드 거절을 확인한다. 기존 테스트는 legacy 순서, 키워드 모드,
v1 검색 깊이/대소문자·단어 경계, 수동 선택 범위, 배타 그룹·항목 예산 및 태그 보호를 확인한다.

전체 실패 1건은 기존 studio fixture의 SimpleNamespace.product_id 누락이다.
TEST_DATABASE_URL을 제거한 오프라인 실행이며 PostgreSQL 잠금·동시성과 외부 연동은
미검증이다. Windows 실행 제한 때문에 필수 품질 검사와 회귀는 require_escalated로 실행했다.

**다음 범위:** lorebook HTTP 경계(router/tag_router, 호환 재노출 및 관련 HTTP 계약/의존성)를
점검하고 모듈 디렉터리 전체로 엄격 검사를 확장한다. 권장 모델은 GPT-6.1 Sol,
추론 Medium이다. character에서 검증한 패턴을 적용하고 HTTP 응답·인증 계약을 확인하는
범위이므로 이 설정으로 진행한다는 작업별 판단이다. 전체 백엔드 타입 정리는 계속 남아 있다.

## 타입 정리 우선 5차: lorebook HTTP 경계 (2026-10-27)

tag_router.py의 반환 누락 4곳을 해결하고 태그 Command의 대상·소유자·태그 ID를 키워드로
구성했다. 일반 router.py의 요청 지역 변수 value를 command로 통일했다.
기존 개별 파일 검사 범위를 lorebook 디렉터리 전체로 확장하고 공유 HTTP 계약과 의존성
훅도 직접 검사한다. 기존 타입이 충분한 파일은 검증 후 검사 범위에 포함했다.

Any/cast/type: ignore나 기준선 예외를 추가하지 않고 시그니처 진단 **4개를 제거했다
(1,135 → 1,131)**. lorebook의 시그니처 기준선 항목은 0개이며 character도 0개다.
이는 전체 백엔드 또는 의존 파일 전체의 타입 정리 완료를 의미하지 않는다.

| 검증 | 결과 |
|---|---|
| 변경 전 lorebook 전체·HTTP 계약/의존성 mypy | 22 source files 중 tag_router 반환 누락 4개 |
| 신규 HTTP 회귀 | 8 passed (전체 API 실행에 포함) |
| 전체 API 회귀 | 546 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,131개, 새 위반 없음; Ruff 78파일 통과; mypy 75 source files 통과; 계약/검사기 13 passed |

test_lorebook_http는 FastAPI의 실제 요청/응답 처리를 통해 태그 4개 경로의 DTO list와
204 빈 본문, OpenAPI의 204 content 부재, 신뢰된 owner/session 전달, 404/422 번역,
미설정 DB/owner 각각의 503 거절 및 서비스 미호출을 확인한다. 기존 경로·인자명·DTO와
dependency override 호환, 인증·오류 문구를 보존한다. 서비스 mock을 사용하므로 DB
인가/잠금 검증을 대신하지 않는다.

전체 실패 1건은 기존 studio fixture의 SimpleNamespace.product_id 누락이다.
TEST_DATABASE_URL을 제거한 실행이며 PostgreSQL·외부 연동은 미검증이다. Windows 실행
제한 때문에 필수 품질 검사와 전체 회귀는 require_escalated로 실행했다.

**다음 범위:** product의 기본 CRUD·조회 타입 경계를 점검한다. 먼저 types/mapper와
repository/core의 연결을 확인하고 실제 의존 범위에 맞춰 검사 대상을 확장한다.
현재 product에는 시그니처 기준선 368개가 남아 있어 한 번에 전체 모듈을 바꾸지 않는다.
권장 모델은 GPT-6.1 Sol, 추론 High다. product는 기본 원본과 스냅샷·상품 표시 값의 관계를
추적해야 하므로 직전 HTTP 범위보다 높은 추론 강도를 권한다는 작업별 판단이다.
타입 정리 우선 방침과 기존 API/저장 계약을 유지한다.

## 타입 정리 우선 6차: product 기본 CRUD·조회 (2026-10-27)

repository/core.py, service/command/__init__.py, service/query/__init__.py의 3개 파일을
엄격 검사에 추가했다. 기존 파일·패키지 및 공개 함수/인자 위치를 유지한다.

- 저장소의 세션·UUID·페이지/검색·잠금·프로필 입력과 Entity/목록 반환을 명시했다.
  COUNT의 non-null 단일 행과 잠근 상품의 존재는 근거를 붙인 assertion으로 표현한다.
- 프로필의 asdict/동적 setattr를 4개 필드의 명시적 생성/갱신으로 바꿨다.
  상태·모델·발행 링크는 보존한다. None 설명과 빈 opening_message를 구별한다.
- 기본 상품/상태/스냅샷 mapper를 명시적 필드 매핑으로 바꾸고 중첩 JSON의 깊은 복사를
  유지했다. 상품 단건의 None→None overload, 카탈로그 Row/tuple, 릴리스 목록과
  스냅샷 구성 mapper의 입력/반환을 보완해 조회 서비스에서 반환 Any가 전파되지 않게 했다.
- repository/publication.py의 get_product_snapshot 한 함수만 타입을 추가했다.
  단건은 기존 scalar 호출을 유지하며 SELECT의 구체적인 Entity 투영을 지역 타입으로
  표현한다. 실제 회귀에서 scalar만 제공하는 기존 세션 대역의 호환성도 확인했다.
- 서비스의 세션·현재 시각을 명시하고 여러 ID를 받는 태그/소유자 Command는 키워드로
  구성한다. 공개 API·소유권·잠금·트랜잭션·검색/페이지 정책은 유지한다.

새 Any/cast/type: ignore나 기준선 예외 없이 시그니처 진단 **61개를 제거했다
(1,131 → 1,070)**. product의 기준선은 368개에서 307개로 줄었다.

| 검증 | 결과 |
|---|---|
| 변경 전 product draft/catalog/lifecycle/integration/boundaries/expiry | 18 passed, 12 skipped |
| 신규 SQLite 및 기존 draft/catalog 회귀 | 12 passed (신규 4건 포함) |
| 전체 API 회귀 | 550 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,070개, 새 위반 없음; Ruff 81파일 통과; mypy 78 source files 통과; 계약/검사기 13 passed |
| 미완료 mapper 별도 mypy | persistence.py에 기존 진단 11개 잔존; strict scope에 추가하지 않음 |

새 SQLite 검사는 소유자/검색 COUNT와 페이지 범위·리터럴 %/_·동률 ID 정렬, 캐시 갱신과
None, 프로필 생성/수정의 상태·발행 링크 보존 및 선택 필드 해제, 정책 JSON 격리,
실제 카탈로그 SQL Row의 발행 제목/선택 설명·커서와 스냅샷 JSON 격리를 확인한다.
SQLite용 최소 테이블을 사용하므로 PostgreSQL FK·정리 정책·잠금 경쟁을 증명하지 않는다.

전체 실패 1건은 기존 studio fixture의 SimpleNamespace.product_id 누락이다. 해당 fixture는
수정하지 않았다. TEST_DATABASE_URL을 제거한 실행이며 실제 PostgreSQL·외부 연동은
미검증이다. Windows 실행 제한 때문에 품질 검사와 회귀는 require_escalated로 실행했다.

**완료 경계:** 기본 저장소와 CRUD/조회 서비스의 엄격 검사 적용이다. types.py는 기존 기본
Command/Info를 사용했으며 전체 파일의 JSON·통계 tuple 타입은 이번에 바꾸지 않았다.
mapper/publication 저장소도 파일 전체 검증 완료가 아니다. follow_imports=silent인
의존 파일에 남은 진단을 기준선 예외로 숨기거나 검사용 파일 분리로 우회하지 않았다.

**다음 범위:** product mapper의 구성·발행·스튜디오·통계 변환과 연결된 types 계약을
정리하고 mapper 전체를 엄격 검사에 넣을 수 있는 범위를 확정한다. JSON 저장 구조를
임의로 넓히지 않고 의미별 경계를 확인한다. 권장 모델은 GPT-6.1 Sol, 추론 High다.
여러 책임과 기존 JSON/tuple 계약이 같은 파일에 있어 호출부 추적이 필요한 범위라는 판단이다.

## 타입 정리 우선 7차: product persistence mapper·types (2026-10-27)

mapper/persistence.py 전체와 types.py 전체를 엄격 검사에 추가했다. 기존 mapper 진단
11개와 types의 bare generic 필드 16개를 해소했다. 새 Any/type: ignore/기준선 예외 없이
시그니처 진단 **21개를 제거했다(1,070 → 1,049)**. product 기준선은 307 → 286개다.
클래스 필드 타입 보완은 함수 시그니처 기준선 감소 수에 포함되지 않는다.

- 구성·스튜디오·통계·발행 조합의 Entity/Row/Info/notice 입력을 명시했다. 순회 사전은
  character_ids_by_link_id로 구체화해 원본 캐릭터 ID와 구성 링크 ID의 대응을 드러냈다.
- 원본/발행 구성·시작 항목·통계의 getattr/필드 일괄 복사를 명시적 매핑으로 바꿨다.
  목록/tuple 순서·None·노트 없는 업데이트 제외와 중첩 JSON 격리는 보존한다.
- RevenueValues/StatisticsMetricsValues TypedDict와 사실 tuple 별칭을 추가했다.
  UUID/정수/Decimal/문자열/결제 ID 목록의 위치를 표현하고 기존 통화별 dict·금액 문자열을
  유지한다. 집계 계산·환율·반올림·조회 SQL·기간 사용자 중복 제거 정책은 변경하지 않았다.
- 스튜디오 문서/매핑/영수증/대체 정책은 JSON 원시값·배열·객체의 재귀 타입으로 표현한다.
  발행 스냅샷 profile은 TypedDict로 표현한다. 실행 시 버전별 검증의 대체물이 아니며
  기존 확장 필드와 과거 데이터는 깊게 복사해 보존한다.
- cast 3곳은 ProductLorebook의 scope/role CHECK 제약 2곳과 기존 발행 스냅샷 저장
  계약 1곳에 한정하고 근거를 주석으로 남겼다. 이 cast가 실행 시 JSON을 검증하지는 않는다.
- StartOptionInfo.title은 실제 원본·발행 시작 항목에서 오는 nullable 값을 표현하도록
  str | None으로 보완했다. None을 임의의 문자열로 바꾸거나 HTTP DTO를 완화하지 않았다.
  기존 F02(제목 없는 시작 옵션의 HTTP 응답 검증 실패)는 여전히 별도 수정 과제다.

| 검증 | 결과 |
|---|---|
| product core/composition/boundaries/statistics 기존 회귀, 변경 전·후 | 각각 15 passed, 3 skipped |
| 신규 mapper 회귀 | 4 passed (전체 API 실행에 포함) |
| 전체 API 회귀 | 554 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,049개, 새 위반 없음; Ruff 83파일 통과; mypy 80 source files 통과; 계약/검사기 13 passed |

신규 test_product_mapping은 구성 링크 ID와 원본 ID/대상 순서·역할 대응, 스튜디오 문서와
발행 영수증의 중첩 변경 격리, 통화별 정확한 문자열(0.1000, 음수, 정수 표기)과 별도 건수,
일별 통계 매핑, nullable 시작 제목·발행 슬롯 ID·발행 프로필 표시를 확인한다.

전체 테스트의 유일한 실패는 기존 studio fixture의 SimpleNamespace.product_id 누락이다.
해당 fixture는 수정하지 않았다. TEST_DATABASE_URL을 제거했고 실제 PostgreSQL·외부
연동은 미검증이다. Windows 실행 제한 때문에 품질 검사·회귀는 require_escalated로 실행했다.

**완료 경계:** product의 공개 types와 persistence mapper의 엄격 검사 적용이다.
mapper/statistics·schema·reporting, repository의 구성·발행·통계 등과 관련 service 전체는
아직 미완료다. follow_imports=silent이므로 의존 파일 전체의 검증 완료로 해석하지 않는다.

**다음 범위:** product repository/composition.py와 관련 구성·설정 서비스 및 조회를
정리한다. 저장소의 소유권 잠금과 기존 링크 재사용·대표 캐릭터 갱신 순서를 추적한다.
권장 모델은 GPT-6.1 Sol, 추론 High다. 구성 변경의 트랜잭션·잠금 및 source/slot ID 관계를
함께 확인해야 하는 범위라는 작업별 판단이다. 기존 감사 결함 수정은 별도 과제로 남긴다.

## 타입 정리 우선 8차: product 구성·설정 (2026-10-27)

repository/composition.py, service/command/composition.py, service/command/settings.py,
service/query/composition.py의 4개 파일을 엄격 검사 범위에 추가했다. 시작 시 대상 4파일의
mypy 진단 10개를 해소했다. Any/cast/type: ignore나 기준선 예외를 추가하지 않고
시그니처 진단 **23개를 제거했다(1,049 → 1,026)**. product 기준선은 286 → 263개다.

- 저장소의 세션·UUID·구성/설정·시작 항목 Info 목록과 반환 목록을 명시했다.
  모델 검증은 ModelInfo, 발행 전 검증은 기존 character 선택 tuple과 start Info list의
  쌍으로 표현한다. 새 결과 객체나 파일을 만들지 않았다.
- 원본별 Entity 사전과 원본→구성 링크 ID 사전을 구분하고 character/lorebook Entity·
  selection·link를 역할별 이름으로 표현했다. 유지 링크의 ID와 SQL·정렬·변경 순서는 유지한다.
- 대표 플래그 해제 후 flush → 새 대표 설정 및 로어 링크 갱신 후 flush → 대상 연결 추가
  순서를 유지한다. 상품 → 캐릭터 → 로어북의 소유권/잠금 확인도 유지한다.
- 여러 ID를 받는 Command는 키워드로 구성했다. 설정의 잠긴 상품 존재는 근거를 붙인
  assertion으로 표현한다. 모델/시작 항목 검증, scope/model_ids/unavailable JSON과
  문자열 UUID·시작 순서 및 트랜잭션 정책은 유지한다.

| 검증 | 결과 |
|---|---|
| 변경 전 composition/integration/boundaries/mapping/studio publication | 27 passed, 9 skipped |
| 신규 구성·설정 및 기존 구성 검증 | 9 passed (신규 8건 포함) |
| 전체 API 회귀 | 562 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 1,026개, 새 위반 없음; Ruff 87파일 통과; mypy 84 source files 통과; 계약/검사기 13 passed |

신규 SQLite 검사는 대표 캐릭터 부분 유일 인덱스를 두고 전환을 실행하며, 기존 링크 ID
재사용·제거/신규 구성·대상 재연결, 구성 조회의 캐릭터 순서, 정책 JSON 및 시작 항목
sort_order를 확인한다. 대상 연결 SELECT에는 ORDER BY가 없으므로 대상 ID 순서를 새로
보장한다고 주장하지 않는다. 서비스 테스트는 상품/캐릭터/로어북 확인 순서와 각 실패 시
저장 미호출, 구성에 포함된 시작 항목 조회·미존재 거절, 트랜잭션 종료를 확인한다.
테스트 fixture 재사용 이름의 린트를 보완한 뒤 신규 파일 8건을 다시 통과했다.

전체 실패는 이전과 같은 studio fixture의 SimpleNamespace.product_id 누락 1건이다.
TEST_DATABASE_URL을 제거했으며 실제 PostgreSQL FK cascade·잠금 경쟁과 외부 모델 연동은
미검증이다. Windows 실행 제한 때문에 품질 검사와 회귀는 require_escalated로 수행했다.

**다음 범위:** product의 발행·릴리스 repository와 service를 정리한다. 버전/스냅샷 ID,
정책 JSON과 콘텐츠 digest, 미디어 비교 및 릴리스 노트 결과의 타입 관계를 확인한다.
권장 모델은 GPT-6.1 Sol, 추론 High다. 여러 구성요소의 잠금·스냅샷 조합과 발행 정책이
연결된 범위이므로 이 설정을 권한다는 작업별 판단이다. 전체 product 타입 정리는 아직 남아 있다.

## 타입 정리 우선 9차: product 발행·릴리스 (2026-10-27)

repository/publication.py, repository/releases.py, service/command/publication.py,
service/command/releases.py의 4파일을 엄격 검사에 추가했다. 시작 시 대상 mypy 진단 24개를
해소하고 시그니처 진단 **69개를 제거했다(1,026 → 957)**. product 기준선은 263 → 194개다.
새 Any/type: ignore나 기준선 예외는 추가하지 않았다.

- 저장소의 세션·UUID·잠금·본문·구성/시작 항목 입력과 Entity/ID/목록 반환을 명시했다.
  기존 scalar 조회와 SQL·정렬·버전 계산·flush 순서를 유지한다.
- 발행 입력의 profile/canonical character/canonical lorebook/envelope를 TypedDict로
  표현한다. 데이터·키 이름·정렬과 JSON 직렬화/SHA-256 규칙은 유지한다. 최종 본문은
  profile.copy() → 선택 scene 옵션 → digest 삽입 순서로 기존 전개를 명시한다.
- 구성/생성/완료 Row와 원본/구성 링크/발행 슬롯 ID 사전을 구분하는 이름을 사용한다.
  여러 ID를 받는 Command는 키워드로 구성한다. 기존 공개 인자명은 유지한다.
- 기존 검증·잠금이 보장하는 모델/effort/시작 항목과 생성·정정 대상 존재를 assertion으로
  표현했다. 올바른 요청의 정책을 바꾸거나 새 입력 검증을 도입하지 않았다.
- cast 2곳은 OUTER JOIN 결과의 노트 None(SQLAlchemy stub 한계)과 JSONB에서 받은
  개방형 scene 옵션의 JSON 값 경계에 한정하고 근거를 남겼다. 실제 SQL Row와 확장 JSON을
  보존한다. 저장소의 dict(data)는 TypedDict 본문의 최상위 dict 표현이며 저장 키/값은 같다.

| 검증 | 결과 |
|---|---|
| 변경 전 integration/lifecycle/expiry/studio publication/core | 18 passed, 12 skipped |
| 신규 발행·릴리스 및 기존 만료 검증 | 8 passed (신규 7건 포함) |
| 전체 API 회귀 | 569 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 957개, 새 위반 없음; Ruff 91파일 통과; mypy 88 source files 통과; 계약/검사기 13 passed |

신규 builder 검사는 실제 SQLite 저장소와 공개 서비스 대역을 조합해 명시한 canonical
본문의 digest, profile/scene 옵션 보존, latest 링크 및 원본·구성 링크·발행 슬롯 ID 관계를
확인한다. 저장소 검사는 실제 OUTER JOIN의 노트 부재와 버전 범위, 정정 전 summary/body/
editor 이력을 확인한다. 정책 5건은 initial→choice, media의 요청별 automatic/choice,
digest 변경/미디어 제거의 content→choice와 트랜잭션 종료를 확인한다.

전체 실패 1건은 이전과 같은 studio fixture의 SimpleNamespace.product_id 누락이다.
fixture는 수정하지 않았다. TEST_DATABASE_URL을 제거한 실행이며 실제 PostgreSQL
동시 발행·FK·잠금 및 외부 freeze/모델 연동은 미검증이다. Windows 실행 제한 때문에
필수 품질 검사와 회귀는 require_escalated로 수행했다.

**다음 범위:** product 스튜디오 저장·조회(repository/studio.py와 command/query studio)를
정리한다. revision/digest/발행 영수증 및 재전송 계약을 확인한다. 기존 studio 실패도 해당
테스트가 유효한 타입/필드의 대역을 제공하는지 함께 점검하되 동작 검증을 약화하지 않는다.
권장 모델은 GPT-6.1 Sol, 추론 High다. JSON 문서와 revision·digest·발행 응답 복구의 관계를
추적해야 하는 범위라는 작업별 판단이다. 전체 product 및 백엔드 타입 정리는 아직 남아 있다.

## 타입 정리 우선 10차: product 스튜디오 저장·조회 (2026-10-27)

repository/studio.py, service/command/studio.py, service/query/studio.py의 3파일을 엄격
검사에 추가했다. 시작 시 대상 mypy 진단 13개를 해소하고 시그니처 진단 **21개를 제거했다
(957 → 936)**. product 기준선은 194 → 173개다. Any/cast/type: ignore나 예외는 추가하지 않았다.

- 세션·UUID·revision/digest·JSON 문서/영수증·nullable publication_digest 및 Entity 반환을
  명시했다. draft mapper의 None/Info overload로 저장 결과의 타입을 연결했다.
- 기존 scalar SQL과 잠금/populate_existing/flush/refresh, raw JSON digest 직렬화·2 MiB
  제한·문서 버전·profile/scene 해석·동일 문서 우선 재전송·revision 비교 순서를 유지했다.
- JSON 태그의 배열/문자열 요소 형태를 좁혀 tuple Command로 전달한다. 비배열/비문자열은
  기존 태그 서비스와 같은 ValueError이며 공백·trim·중복 정책은 공유 태그 서비스가 담당한다.
  공개 범위 라벨은 Literal 결과로 표현하되 raw 값의 기존 처리 의미를 유지한다.
- mapper Info의 존재 확인으로 보장되는 잠긴 draft와 저장 후 행 존재는 근거를 붙인
  assertion으로 표현한다. 컴포넌트 매핑 쓰기는 revision/content_digest를 바꾸지 않고
  기존 영수증 필드를 보존한다. 발행 시점의 기존 JSON 계약은 유지한다.

**기존 실패의 원인 설명 보완:** 앞선 기록에서 studio 실패는 필수 필드가 없는 fixture에서
막혀 있었다. 이번에는 실제 Product/ProductStudioDraft 대역과 정상 mapper를 사용하고,
기대 충돌 예외 및 저장 미호출 assertion을 유지했다. 실제 코드 변경 전에도 유효한 대역에서
예외 미발생(DID NOT RAISE)이 재현됐다. 따라서 fixture 보완만으로 통과하는 문제는 아니었다.
감사 U06은 이미 재발행 거절 문서/테스트와 재발행 지원 구현의 불일치를 기록한다. 현재
실패는 이 계약 충돌이며 운영 재발행 장애로 단정하지 않는다. 기대를 완화하거나 skip/xfail로
숨기지 않았고, 이번 타입 정리에서 거절 정책을 임의로 복원하지 않았다. product ARCHITECTURE는
현재 동작과 U06 미결 상태를 구별하도록 보완했다.

| 검증 | 결과 |
|---|---|
| 유효한 기존 대역 보완 후 코드 변경 전 studio guard/publication/mapping | 17 passed, 1 failed (DID NOT RAISE) |
| 신규 studio 및 기존 publication/mapping | 28 passed (신규 11건 포함) |
| 전체 API 회귀 | 580 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 936개, 새 위반 없음; Ruff 94파일 통과; mypy 91 source files 통과; 계약/검사기 13 passed |

신규 검증은 stale revision이라도 같은 digest이면 저장하지 않는 재전송, 생성/갱신의
profile 투영·버전·digest, 타인/삭제/충돌/태그 형태 오류의 저장 차단, 발행 영수증 및
컴포넌트 매핑의 revision/content_digest 보존, 읽기의 소유자/잠금·미존재를 확인한다.
최소 SQLite 테이블에서 실제 생성/수정/영수증 저장 및 잠금 조회의 캐시 갱신도 확인한다.
PostgreSQL advisory/row lock 경쟁·외부 발행 연동은 미검증이다. TEST_DATABASE_URL을
제거했으며 Windows 실행 제한 때문에 품질 검사/회귀는 require_escalated로 실행했다.

**다음 범위:** product의 스냅샷 runtime/공개 안내/업데이트·가용성 views와 미디어 읽기
서비스를 점검한다. 소유권·스냅샷 소속·만료 및 nullable 원본/버전 타입의 연결을 확인한다.
권장 모델은 GPT-6.1 Sol, 추론 High다. 여러 도메인 공개 Info와 접근 정책을 조합하는
범위라는 작업별 판단이다. U06의 제품 계약 결정과 전체 백엔드 타입 정리는 별도로 남아 있다.

## 타입 정리 우선 11차: product snapshot·notice·media views (2026-10-27)

service/views/ 디렉터리 전체 4파일을 엄격 검사 범위에 추가했다. 시작 시 mypy 진단 6개
(세션 누락 및 nullable 부모 연결)을 해소했고 시그니처 진단 **5개를 제거했다(936 → 931)**.
product 기준선은 173 → 168개다. Any/cast/type: ignore나 예외는 추가하지 않았다.

- runtime/공개 안내/업데이트·가용성/참조 조회의 세션 타입을 명시했다. snapshot ID와
  소유자 Command는 의미가 드러나는 키워드로 구성하고 books 지역 이름은 lorebooks로
  맞췄다. 이미 타입이 충분한 미디어 서비스는 검증 후 범위에 포함했다.
- 대화 상품은 필수 RESTRICT FK이며 기존 안내 mapper도 부모 존재를 요구한다.
  조회된 부모 Info가 None이 아니라는 기존 가정을 assertion으로 드러냈다. 정상 결과와
  접근 정책은 유지한다. 누락 원본을 성공/빈 목록으로 숨기거나 새로운 404 정책을 만들지
  않았다. 대화·상품의 동시 삭제와 읽기 경합까지 FK만으로 보장한다고 해석하지 않는다.
- 기존 만료 버전의 안내 표시, runtime의 호출자 선행 인가/만료 책임, 미디어의 접근·만료·
  상품 소속 확인과 세션 종료 뒤 읽기 순서, reader 반환 후 호출자의 close 책임을 유지한다.

| 검증 | 결과 |
|---|---|
| 변경 전 conversation runtime/product boundaries/lifecycle/character media/media HTTP | 14 passed, 33 skipped |
| 신규 views 회귀 | 12 passed |
| 전체 API 회귀 | 592 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 931개, 새 위반 없음; Ruff 98파일 통과; mypy 95 source files 통과; 계약/검사기 13 passed |

test_product_views는 snapshot 슬롯 ID와 component snapshot ID 구별·원본 삭제 보존,
미발행 조회 거절·만료 버전 안내·모델 공지 전달, 대화 소유권과 legacy/부모 누락 실패,
노트 없는 업데이트 제외, 소유자 버전 소속 검증을 확인한다. 미디어 4건은 접근/만료/다른
상품 버전 실패 시 파일 읽기를 차단하고, 성공 시 검증된 character snapshot ID만 전달하며
실제 AsyncSession 범위가 끝난 뒤 읽고 caller가 reader를 닫는 계약을 확인한다.

전체 실패 1건은 유효한 fixture로 확인된 기존 U06의 재발행 거절 기대/구현 불일치다.
기대를 완화하거나 정책을 임의 변경하지 않았다. TEST_DATABASE_URL을 제거했으며 실제
PostgreSQL 잠금/동시성·외부 모델/저장소 연동은 미검증이다. Windows 제한 때문에 필수
품질 검사와 회귀는 require_escalated로 수행했다.

**다음 범위:** product 태그 repository/service/mapper를 정리한다. 기존 character/lorebook
패턴을 적용하되 product 공개 태그의 소유자 또는 approved + 비private 조회 정책과
소유자 쓰기, 관리자/시스템 보호를 유지한다. 권장 모델은 GPT-6.1 Sol, 추론 High다.
구조는 검증된 패턴이지만 공개 조회 인가 차이와 태그 유지/해제 계약을 확인해야 하는 범위라는
작업별 판단이다. 전체 product/백엔드 타입 정리는 아직 남아 있다.

## 타입 정리 우선 12차: product 태그 저장소·서비스·mapper (2026-10-27)

repository/tags.py, service/tags.py, mapper/tags.py, mapper/tag_schema.py의 4파일을 엄격
검사에 추가했다. 시작 시 mypy 진단 40개를 해소했고 시그니처 진단 **83개를 제거했다
(931 → 848)**. product 기준선은 168 → 85개다. Any/cast/type: ignore나 예외는 추가하지 않았다.

- 세션·UUID·잠금·Sequence ID 목록·nullable 시스템 actor와 Entity/목록/None 반환을
  명시했다. 조회의 scalar SQL/populate_existing, 정렬 및 upsert 정책은 유지한다.
- character/lorebook의 태그 패턴을 적용하면서 product의 ProductStateInfo와 분리된
  repository/tags 진입점을 유지했다. 관리자/시스템 source와 Command는 overload로
  연결하고 관리자 분기의 내부 불변 조건은 assertion으로 표현했다.
- retained_tag_ids/requested_tag_ids/protected_tag_ids/actor_id와 mapper의 tags_by_id,
  저장소의 sort_order를 사용한다. HTTP 요청→Command는 UUID/DTO/키워드 입력으로,
  Entity/Info→값/응답은 Iterable 입력과 기존 tuple/list 반환으로 표현한다.
- product 고유의 공개 조회 조건(소유자 또는 approved + 비private)을 유지한다. unlisted
  조회 허용과 public catalog 조건은 다르다. 소유자 쓰기, 관리자 재검증·시스템 보호,
  비활성 태그·순서·정확한 이름·원본 연결/스냅샷 분리 정책은 유지한다.

| 검증 | 결과 |
|---|---|
| 변경 전 tag management/DB/schema 및 studio 연결 | 29 passed, 11 skipped |
| 변경 후 같은 범위 및 product core | 41 passed, 11 skipped (신규 8건 포함) |
| 전체 API 회귀 | 600 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 848개, 새 위반 없음; Ruff 102파일 통과; mypy 99 source files 통과; 계약/검사기 13 passed |

신규 접근 조합 7건은 소유자의 draft/rejected private 조회, 비소유자의 approved public/
unlisted 허용과 approved private/draft public/rejected unlisted 거절을 확인한다.
비소유자는 공개 태그를 읽을 수 있어도 추가할 수 없으며 사전 항목이 생성되지 않음을
확인한다. 나머지 SQLite 검사는 잠금 옵션을 사용한 부모 조회의 기존 객체 갱신과
미존재 None을 확인한다. 기존 범용 태그 테스트가 관리자/시스템 보호·롤백 등도 확인한다.

전체 실패는 기존 U06의 재발행 거절 기대/구현 충돌 1건이다. 기대 완화나 skip/xfail은
추가하지 않았다. TEST_DATABASE_URL을 제거한 실행이며 PostgreSQL upsert 경합·FK·
부모 잠금 및 외부 연동은 미검증이다. Windows 실행 제한 때문에 품질 검사와 회귀는
require_escalated로 실행했다.

**다음 범위:** product 통계 집계 mapper/statistics와 관련 repository/command/query를
정리한다. 일별/기간 순사용자·상태별 카운터·통화별 Decimal·재계산 결과 및 큐 작업 타입을
연결한다. 권장 모델은 GPT-6.1 Sol, 추론 High다. 여러 사실 tuple과 금액/개수·중복 제거·
재계산 트랜잭션을 함께 추적해야 하는 범위라는 작업별 판단이다. 전체 타입 정리는 아직 남아 있다.

## 타입 정리 우선 13차: product 통계 집계·저장·작업 큐 (2026-10-27)

mapper/statistics.py, repository/statistics.py, service/command/statistics.py,
service/command/statistics_queue.py, service/query/statistics.py 및
app/db/product_stats_queue.py의 6파일을 엄격 검사에 추가했다. 시작 시 통계 5파일의
mypy 진단 20개를 해소했고 시그니처 진단 **42개를 제거했다(848 → 806)**.
product 기준선은 85 → 47개다. 기존 Any 기반 누적 사전을 구체화했으며
Any/cast/type: ignore나 기준선 예외는 추가하지 않았다.

- 세션·UUID·날짜·재생성 Command/BuildInfo와 Entity/목록/None 반환을 명시했다.
  repository의 StatisticsReportRow는 일별 Entity 목록·기간 DISTINCT 사용자 수·대기
  날짜를 전달하는 내부 tuple이다. service에는 mapper를 거친 Info만 전달한다.
- 카운터는 Literal 키와 StatisticsMetricsValues로, 결제·기간 매출 누적값은 내부
  TypedDict로 표현한다. 서로 다른 facts 목록을 같은 rows 변수에 덮어쓰지 않고
  snapshot_id/user_id로 역할을 드러낸다. 동적 getattr 누적은 명시적 필드 접근으로 바꿨다.
- 통화별 Decimal 계산과 문자열 출력, 결제 ID의 판매 건수 중복 제거·환불 건수 합산,
  버전/상품/기간의 서로 다른 사용자 집계 범위를 유지한다. pending/알 수 없는 상태의
  기존 KeyError도 유지하며, 쿼리가 반드시 완료 상태만 준다는 보장을 추가하지 않는다.
- 버전별 조회 조건은 해당 버전 Entity 열로 명시했다. GROUP BY 없는 COUNT DISTINCT의
  non-null 반환 가정은 assertion으로 표현했다. 날짜·버전 소속·인가·정렬·조회 범위,
  재계산 삭제/교체와 상위 트랜잭션 책임, 큐 SKIP LOCKED/upsert 정책은 유지한다.
- 서울 날짜의 aware 검증·UTC 반열린 구간과 오늘을 포함한 days+1일 예약도 유지한다.
  외부 HTTP/JSON 계약이나 테이블·마이그레이션은 변경하지 않았다.

| 검증 | 결과 |
|---|---|
| 변경 전 product statistics/mapping/boundaries | 14 passed, 3 skipped |
| 변경 후 같은 범위 및 신규 통계 계약 | 20 passed, 3 skipped (신규 6건) |
| 전체 API 회귀 | 606 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 806개, 새 위반 없음; Ruff 108파일 통과; mypy 105 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |

신규 6건은 소수 금액·복수 통화·상태별 카운터, 버전 간/날짜 간 사용자 중복 제거와
판매 결제 ID 중복 제거, 빈 facts/예상 밖 상태를 확인한다. SQLite 최소 테이블에서
같은 날짜 재생성 반복, 버전 필터·빈 결과·대기 날짜, 삭제 도중 오류 전파와 호출자 롤백,
큐의 오래된 작업 선택·상품/날짜별 삭제를 확인한다. 실제 AsyncSession과 서비스 대역으로
서울 자정 기준의 오늘 포함 예약과 트랜잭션 종료도 확인한다.

SQLite 테이블은 FK를 복제하지 않았으며 롤백 테스트의 savepoint는 테스트 호출자
소유다. 운영 코드의 트랜잭션을 savepoint로 바꾸지 않았다. TEST_DATABASE_URL을 제거한
실행이므로 PostgreSQL SKIP LOCKED 경합·upsert·FK 및 외부 연동은 미검증이다.
전체 실패 1건은 기존 U06의 발행 후 편집 거절 기대/실제 재발행 허용 간 계약 충돌이다.
기대 완화나 skip/xfail, 제품 정책 변경은 하지 않았다. Windows 실행 제한으로 품질 검사와
회귀는 require_escalated로 실행했다.

**다음 범위:** product reporting의 repository/mapper/query를 정리한다. 일별 집계와
기간 순사용자, 기록된 0과 미집계 날짜, dirty/갱신 범위 및 소유자·관리자 조회를 연결한다.
권장 모델은 GPT-6.1 Sol, 추론 High다. 집계 존재 여부·기간·인가 경계를 함께 추적해야
하는 범위라는 작업별 판단이다. 전체 product/백엔드 타입 정리는 아직 남아 있다.

## 타입 정리 우선 14차: product reporting 조회 (2026-10-27)

repository/reporting.py, mapper/reporting.py, service/query/reporting.py의 3파일을
엄격 검사에 추가했다. 시작 시 mypy 진단 17개를 해소했고, 시그니처·bare generic
기준선 진단 **23개를 제거했다(806 → 783)**. product 기준선은 47 → 24개다.
Any/cast/type: ignore나 기존 예외를 추가하지 않았다.

- 세션·UUID·날짜·조회 Command/Info를 명시했다. ProductReportingRow는 상품별 또는
  버전별 일별 Entity 목록, 부모 집계, 기간 순사용자 수와 대기 날짜를 전달한다.
  상품 전체 조회의 rows/root_rows가 같은 목록을 가리키는 기존 관계도 유지한다.
- ServiceReportingRow의 object 필드는 집계 14개 열과 큐 2개 열의 내부 tuple 별칭으로
  표현한다. COUNT 정수·빈 MIN/MAX의 None·bigint SUM의 int/Decimal을 구분하며
  mapper의 기존 int 변환을 유지한다. SQLAlchemy Result.tuples()는 런타임의 기존
  Result/Row를 유지하면서 위치별 타입을 표현하며 requirements의 >=2.0 범위를 지원한다.
  의존성 하한이나 반환 데이터를 새 형식으로 바꾸지 않았다.
- mapper의 일별 Entity→Info 및 합산 필드를 명시적 접근으로 바꿨다. 기간 순사용자는
  일별 합이 아닌 별도 DISTINCT 값이며 전체 조회는 상품 간 사용자도 중복 제거한다.
  금액/revenue·개인정보는 reporting 결과에 포함하지 않는다.
- 버전 활동 조건은 해당 Entity 열로 명시하고 GROUP BY 없는 COUNT의 non-null 가정을
  assertion으로 표현했다. SQL 필터·열 순서·정렬·집계 범위는 유지한다.
- 활성 소유자/관리자 확인, 상품 존재·소유권과 버전 소속 검증, 날짜 검증 순서와
  no_autoflush 범위를 유지한다. Command는 역할이 드러나는 키워드로 구성한다.
  pending 우선 상태와 부모 집계 없는 날의 None, 부모 집계가 있는 무활동 버전의 0,
  미집계/dirty일 때 확정 totals 미제공, 기록된 부분 합계의 범위를 보존한다.

| 검증 | 결과 |
|---|---|
| 변경 전 reporting/DB 회귀 | 12 passed, 4 skipped |
| 변경 후 reporting/DB·신규 계약·기존 통계 계약 | 32 passed, 4 skipped (신규 14건 포함) |
| 전체 API 회귀 | 620 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 783개, 새 위반 없음; Ruff 111파일 통과; mypy 108 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |

test_product_reporting_contracts의 신규 14건은 실제 SQLite 조회로 상품·버전·포함 날짜
필터, 기간/상품 간 DISTINCT, 10개 카운터의 필드 순서·합계, 미집계/알려진 0/dirty,
일별 갱신 시각과 기간/전체 큐 범위, 빈 집계의 NULL 시각을 확인한다. 별도 순수 변환은
큰 Decimal 정수의 정확한 int 반환을 확인한다. 공개 경계 대역과 실제 AsyncSession으로
소유자/관리자 성공, 비활성/비소유자/비관리자/부모 누락/다른 상품 버전 거절,
잘못된 기간·비관리자의 전체 조회 차단, no_autoflush 복원과 actor ID 전달을 확인한다.

SQLite는 기존 통계 계약의 최소 테이블을 재사용하며 FK를 복제하지 않는다. identity와
상품 인가 서비스의 실제 사용자 상태 갱신·DB 잠금은 대역 범위 밖이다. TEST_DATABASE_URL을
제거한 실행이므로 PostgreSQL READ ONLY·동시성·FK 및 외부 연동은 미검증이다.
전체 실패 1건은 기존 U06의 발행 후 편집 거절 기대/재발행 허용 구현 간 계약 충돌이며
기대 완화·skip/xfail·제품 정책 변경은 하지 않았다. 필수 품질 검사와 회귀는 Windows
실행 제한으로 require_escalated에서 수행했다.

**다음 범위:** product의 router/tag_router와 연결된 HTTP 타입 경계를 정리한다.
기존 응답 DTO·인증 의존성·오류 변환·본문 없는 삭제 응답을 유지한다. 권장 모델은
GPT-6.1 Sol, 추론 High다. HTTP 계약과 다수 Command/응답 타입 연결을 함께 검증해야
하는 범위라는 작업별 판단이다. product 기준선은 router 17개, tag_router 4개,
statistics_job 3개가 남아 있으며 전체 백엔드 타입 정리도 계속 필요하다.

## 타입 정리 우선 15차: product HTTP 경계 (2026-10-28)

router.py, tag_router.py, mapper/schema.py, schemas.py의 4파일을 엄격 검사에 추가했다.
시작 시 해당 범위의 mypy 진단 23개(반환 미표기 21개·DTO bare dict 2개)를 해소했다.
시그니처 기준선 **21개를 제거했다(783 → 762)**. product 기준선은 24 → 3개다.
클래스 필드 보완은 기준선 감소 수에 포함되지 않는다. Any/type: ignore나 기준선 예외는
추가하지 않았다. HTTP JSON→업무 JSON 경계의 cast 1곳은 아래 근거에 한정한다.

- 일반/태그 라우터 반환을 기존 ResponseDto·목록·None으로 명시했다. catalog-tags의
  list/dict 요소와 mine/count의 정수 값도 명시하며 response_model=None으로 기존 raw
  응답 처리를 유지했다. 삭제 204와 본문 없음, 라우팅 순서·경로·필드명·인증 훅을 보존한다.
- 여러 ID/옵션을 받는 Command를 키워드로 구성하고 요청 변환 지역 이름은 command로
  맞췄다. schema mapper의 character/lorebook 순회 이름을 구체화했다.
- 스튜디오 DTO document는 dict[str, object]로 자유로운 HTTP 객체를 표현한다.
  이 DTO를 소비하는 app/http/studio_publication.py의 저장 호출도 확인했다. 새 schema
  mapper studio_draft_request_to_command가 경로 ID·신뢰된 owner·revision·document를
  조합하여 업무 Command로 넘긴다. HTTP 파서가 JSON 호환 값만 공급한다는 근거로
  이 지점에서만 재귀 ProductJsonObject로 cast한다. 중첩 값 검증/trim을 새로 도입하거나
  service의 구조·크기·digest 검증을 생략하지 않는다. 직접 Python DTO 생성에 대한 JSON
  검증 보장은 아니다. 공유 HTTP 파일 전체의 기존 미완료 진단 5개는 별도 범위로 남는다.
- 단독 상품 router의 OpenAPI 정렬 JSON은 변경 전후 SHA-256이 동일하다.
  16경로·27스키마이며 digest는
  63996fa403c18bc7d14ce4b261fd55844bc94a09746a0853483175be0b2f7280이다.
  기존 nullable 시작 제목 F02와 U06의 제품 정책은 변경하지 않았다.

| 검증 | 결과 |
|---|---|
| 변경 전 catalog/draft/boundaries/tag management | 39 passed |
| 변경 후 같은 범위 및 신규 HTTP 계약 | 59 passed (신규 20건 포함) |
| 전체 API 회귀 | 640 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 762개, 새 위반 없음; Ruff 115파일 통과; mypy 112 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |
| product 전체 추가 mypy 점검 | 43 source files 중 statistics_job.run의 미표기 함수 1건 잔존 |

test_product_http의 신규 20건은 실제 FastAPI 요청·응답으로 태그 4경로의 DTO와 204,
신뢰된 owner/session 전달, 카탈로그 커서/UUID/검색 필터와 잘못된 시각 거절,
소유자 목록·전체 개수의 응답 모양을 확인한다. 태그 생략/null 유지·빈 목록 해제,
일반 삭제 204, 노트 정정의 정책 변경 거절, 스튜디오 응답의 영수증 필드 제외와
중첩 문자열 공백·bool/int/float/null 보존, 통계의 날짜/버전·금액 문자열·대기 날짜,
404/422 번역과 미설정 의존성의 서비스 미호출도 확인한다.

서비스를 대역으로 바꾼 HTTP 계약 검사이며 DB 인가·잠금과 외부 연동은 미검증이다.
TEST_DATABASE_URL을 제거한 전체 실행의 실패 1건은 기존 U06의 발행 후 편집 거절 기대와
재발행 허용 구현 사이의 계약 충돌이다. 기대 완화·skip/xfail은 추가하지 않았다.
필수 품질 검사와 회귀는 Windows 실행 제한 때문에 require_escalated로 수행했다.

**다음 범위:** product statistics_job의 인자/반환 타입과 엔진·세션 종료 계약을 정리하고
product 디렉터리 전체를 엄격 검사 범위로 묶는다. 기준선의 남은 3항목은 run의 limit,
repair 및 반환이다. 권장 모델은 GPT-6.1 Sol, 추론 Medium이다. 짧은 실행 조립 코드의
기존 실행·정리 동작과 모듈 전체 검사 범위를 확인하는 작업이라는 판단이다.
전체 백엔드 타입 정리와 감사 결함 수정은 계속 남아 있다.

## 타입 정리 우선 16차: product 통계 실행·모듈 전체 검사 편입 (2026-10-28)

statistics_job.run의 limit/repair/반환 타입을 int/bool/None으로 명시하고, 처리 결과 이름을
count에서 processed_info로 바꿨다. 기존 호출 인자명·위치 인자와 CLI 기본값·옵션,
출력 문구, 최근 날짜 예약→처리 순서, 세션/엔진 수명은 유지한다.
시그니처 기준선 **3개를 제거했다(762 → 759)**. product 기준선은 3 → 0개이며
character/lorebook도 계속 0개다. Any/cast/type: ignore나 예외는 추가하지 않았다.

개별 product 파일·하위 디렉터리 목록을 전체 product 디렉터리 1항목으로 교체했다.
그동안 직접 검사하지 않았던 재노출/패키지 파일도 포함하며, product 전체의 Ruff는
44파일, mypy는 43 source files를 통과한다. 필수 검사 전체의 파일 수는 아래와 같다.
의존 ORM 모델·최상위 use case·공유 HTTP 파일까지 모두 완료한 것은 아니며
follow_imports=silent을 바꾸거나 검사 제외 예외를 추가하지 않았다.

| 검증 | 결과 |
|---|---|
| 변경 전 product 전체 추가 검사 | mypy 함수 미표기 1건, Ruff 인자/반환 미표기 3항목 |
| 변경 전 신규 실행/정리 계약 | 5 passed |
| 변경 후 product 전체 추가 mypy | 43 source files 통과 |
| 전체 API 회귀 | 645 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 759개, 새 위반 없음; Ruff 123파일 통과; mypy 119 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |

신규 test_product_statistics_job의 5건은 repair 유무별 정상 처리, 재집계 요청 실패,
배치 처리 실패, CancelledError 전달을 확인한다. 실제 AsyncSession을 연결 없이 사용하며
대역 업무가 남긴 트랜잭션도 session.close에서 끝나고 그 뒤 engine.dispose가 호출됨을
확인한다. 원래 예외 객체를 전달하고 실패 시 성공 문구를 출력하지 않는다. 성공 시
기존 건수 문구, 환경 URL 전달, expire_on_commit=False와 limit 전달도 확인한다.
실제 DB 접속·CLI 프로세스 실행·반복 취소·운영 스케줄러는 이 검사의 범위가 아니다.

전체 실패 1건은 기존 U06의 발행 후 편집 거절 기대/재발행 허용 구현 간 계약 충돌이다.
기대 완화·skip/xfail·제품 정책 변경은 하지 않았다. TEST_DATABASE_URL을 제거했으므로
PostgreSQL 잠금/동시성·FK와 외부 연동은 미검증이다. 품질 검사와 회귀는 기존 Windows
실행 제한에 따라 require_escalated로 수행했다. F02 및 다른 감사 결함 수정도 별도다.

**다음 범위:** chatting/conversation의 repository·조회 서비스·persistence mapper부터
타입을 정리한다. 대화 소유권·목록 커서·참여 캐릭터와 통계 사실의 반환 경계를 먼저 맞추고
버전 전환/실행 컨텍스트 쓰기 정책은 후속 범위로 나눈다. 권장 모델은 GPT-6.1 Sol,
추론 High다. 대화/상품 버전·참여자 ID와 잠금·nullable 과거 데이터의 연결을 함께 확인해야
하는 범위라는 작업별 판단이다. 전체 백엔드 기준선은 759개로 남아 있다.

## 타입 정리 우선 17차: conversation 저장소·조회·persistence mapper (2026-10-28)

repository.py, service/query.py, mapper/persistence.py와 관련 공개 types.py의 4파일을
엄격 검사에 추가했다. 시작 시 직접 진단은 첫 3파일 22개와 types의 bare generic 필드
5개였다. 시그니처 기준선 **60개를 제거했다(759 → 699)**. conversation에는 쓰기/뷰/
HTTP의 11항목이 남는다. 필드 타입 보완은 기준선 감소 수에 포함되지 않는다.
Any/type: ignore/기준선 예외는 추가하지 않았으며 JSON 경계의 cast 2곳은 아래에 한정한다.

- 저장소의 세션·UUID·시각·Command/Sequence와 Entity/목록/None 반환을 명시했다.
  scalar SQL·잠금·populate_existing·flush·참여자 교체·현재/최초 버전 처리 순서를 유지한다.
  커서 쌍, COUNT의 non-null, 상위에서 잠근 전환 대상 존재를 근거 있는 assertion으로 표현한다.
- query의 소유권 실패·페이지 크기/커서 검증·참여자 조회 전 소유권 확인을 유지한다.
  생성 시각/ID 내림차순과 limit+1, 전체 개수의 커서 독립성, 참여자 role_order/ID 순서도 같다.
- Info의 동적 getattr 필드 복사를 명시적 접근으로 바꾸고 캐릭터·로어북·대상 이름을
  구체화했다. 원본/스냅샷/상품 슬롯 ID를 구분하며 생성 Command는 키워드로 구성한다.
- 내부 ConversationStatisticsRows는 repository에 두고 SQLAlchemy Result.tuples()로
  기존 Row를 유지하며 위치별 타입을 표현한다. mapper는 공개 list[tuple[UUID,int]]로
  변환한다. 최초 snapshot IS NOT NULL과 상품별 [start,end) 조회를 유지하며 COUNT를
  임의 기본값으로 바꾸지 않는다.
- runtime의 JSON/로어 항목·설정과 통계 요소 타입을 명시했다. 시작 제목 및 runtime의
  시작 객체는 실제 반환에 맞게 nullable로 보완한다. 빈 문자열/장면 합성이나 HTTP DTO
  완화는 하지 않는다. scene opening의 빈 문자열/None, legacy 첫 대사 없음과 기존
  default 키의 eager 조회로 발생하는 KeyError도 유지한다.
- cast 2곳은 발행 snapshot TypedDict.items()의 JSON 값 소실과 저장된 scene 옵션의
  source_entry_id→opening 구조를 표현한다. 새 JSON 검증이나 보정은 아니다. settings의
  최상위 사전 생성과 중첩 JSON·캐릭터 data·활성 로어 목록의 기존 참조 관계를 유지한다.

| 검증 | 결과 |
|---|---|
| 변경 전 opening/runtime/statistics/boundaries | 19 passed, 9 skipped |
| 변경 후 같은 범위 및 신규 계약 | 36 passed, 9 skipped (신규 17건 포함) |
| 전체 API 회귀 | 662 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 699개, 새 위반 없음; Ruff 127파일 통과; mypy 123 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |

신규 test_conversation_query_contracts는 SQLite에서 소유자 범위·동일 시각의 ID 커서,
nullable 제목과 빈 방 포함 개수, 잠금 옵션 조회의 캐시 갱신·참여자 순서/nullable ID,
미소유/미존재 및 잘못된 커서의 후속 조회 차단을 확인한다. 생성·history_revision 증가·
버전 전환에서 최초 snapshot/start 보존과 참여자 교체·active model 초기화를 확인한다.
통계는 최초/현재 버전 구별·다른 상품 제외·시작 포함/종료 제외·NULL 최초 버전 제외와
일반 tuple 반환을 확인한다. 순수 mapper는 원본 삭제 후 슬롯 대응, JSON 참조 관계,
scene/빈 문자열/null/legacy opening 및 기존 missing default 오류를 확인한다.

SQLite는 FK/UNIQUE를 복제하지 않은 최소 테이블이며 실제 PostgreSQL 잠금/경합·복합 FK는
미검증이다. TEST_DATABASE_URL을 제거했다. 전체 실패 1건은 기존 U06 계약 충돌이며
기대 완화·skip/xfail은 추가하지 않았다. F02 및 감사 결함 수정도 별도다. Windows 실행
제한으로 필수 품질 검사와 회귀는 require_escalated로 수행했다.

**완료 경계/추가 진단:** conversation의 쓰기·views·HTTP와 다른 디렉터리의 소비부 전체는
아직 엄격 검사 범위가 아니다. 별도 mypy 점검한 chatting/prompt/service.py에는 6진단이
남는다(runtime.start nullable 직접 접근 2개, references의 구체적 JSON 추론 4개).
이것은 이번 실행에서 새로 발생한 기능 회귀라는 뜻은 아니며 이전의 느슨한 타입이 가렸던
소비부 가정을 드러낸 것이다. 기존 동작을 임의의 장면 기본값·오류 정책으로 변경하지 않았다.

**다음 범위:** conversation의 시작/버전 전환/원문 세대/실행 컨텍스트 command와 views를
정리하고, 시작/runtime을 사용하는 prompt 경계의 남은 진단도 함께 점검한다.
권장 모델은 GPT-6.1 Sol, 추론 High다. 잠금·최초/현재 버전·시작 정보·로어 활성화 및
nullable 소비 조건을 함께 추적해야 하는 범위라는 작업별 판단이다.

## 타입 정리 우선 18차: conversation 쓰기·views·prompt 소비부 (2026-10-28)

conversation service/command의 4파일·service/views.py와 prompt/service.py의 6파일을
정리했다. 시작 시 직접 mypy 진단은 세션 미표기 6개와 prompt nullable/JSON 소비 6개,
합계 12개였다. 해당 범위와 기존 query/재노출까지 conversation/service 전체를 검사하고
prompt 디렉터리 전체도 필수 범위에 추가했다. 직접 검사한 service/prompt 11 source files가
통과한다. 이 작업의 시그니처 해결은 **6개**이며 conversation에는 router 5항목이 남는다.
Any/cast/type: ignore나 검사 예외는 추가하지 않았다.

**병렬 기준선 구분:** 작업 시작 공용 기준선은 699개였고 prune 시 실제 항목은 576개였다.
감소 123개 중 이 대화의 conversation 6개, 다른 대화의 credit 16개와 moderation 101개를
구분한다. 공용 검사 소유자인 주 대화에서 새 위반 0개를 확인한 후 --prune-baseline으로
해결된 시그니처만 제거했다. 다른 대화 모듈의 전체 타입/업무 완료 판정이나 엄격 검사 편입은
그 결과 수령 후 별도로 확인한다. 이번 검사 범위에는 credit/moderation을 추가하지 않았다.

- 쓰기·views의 AsyncSession, 초기 snapshot/start/current primary의 nullable 지역 값을
  명시했다. 상품 snapshot/dirty Command를 키워드로 구성하고 시작 ID membership의
  non-null 전제를 assertion으로 표현했다. 같은 모듈 내 버전 전환은 구체적 query에서
  get_owned_conversation을 참조한다. character_commands·start_option·lorebook·snapshot_id·
  known_entry_ids 등으로 역할을 구별한다.
- 시작의 자동/명시 선택·primary 검증·상품 잠금, 전환의 대화 잠금·같은 버전 멱등 성공·
  순방향·노트·동의·구성 검증, history 잠금과 runtime의 실행 순서를 유지한다. 최초 시작과
  현재 참여자/primary 구분, legacy 수동 목록 빈 결과, pinned snapshot의 수동 ID 필터도 같다.
- prompt 참조 구조를 내부 TypedDict로 명시해 서로 다른 문자열·JSON·로어 목록이
  Collection[str]로 합쳐지던 추론 문제를 해소했다. lore metadata의 옵션 truthiness를
  내부 함수로 구분하며 옵션을 새로 검증/정규화하지 않는다. seen은 UUID 집합이다.
- prompt는 기존부터 시작 객체/metadata에 직접 접근해 None에서 실패했다. 이를 내부
  non-null assertion으로 명시했다. **이 두 무효 내부 입력의 예외는 AttributeError에서
  AssertionError로 바뀐다.** 성공 결과를 만들거나 빈 값으로 보정하지 않는다. 답변 대상·
  현재 역할 검증 순서와 정상 입력의 출력·JSON 순서·로어 배치·이력·추정식은 유지한다.

| 검증 | 결과 |
|---|---|
| 변경 전 prompt/runtime/query/lore activation/opening/integration | 55 passed, 15 skipped |
| 신규 command/views·prompt 계약 | 37 passed (대화 26건, prompt 11건) |
| 전체 API 회귀 — 병렬 변경 포함 시점 | 719 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 576개, 새 위반 없음; Ruff 138파일 통과; mypy 133 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |

command/views의 26건은 실제 AsyncSession과 서비스 대역으로 시작 옵션/권한 입력,
미발행·잘못된 옵션·primary 부재 거절, 전환 멱등 성공·모드·버전/노트 범위·통계 시각,
legacy/다른 상품/역방향/노트 부재/동의/구성 오류 시 쓰기 차단을 확인한다. 원문 세대 잠금,
최초 장면과 현재 참여자 primary 구별, 수동 항목 필터·스냅샷별 ID 선택·잘못된 runtime의
실패와 트랜잭션 종료도 확인한다. 저장소 대역이므로 실제 DB 쓰기 원자성/잠금은 미검증이다.

prompt 11건은 변경 전 HEAD의 기존 구현으로 산출한 고정 입력 기준과 비교한다.
최종 request_json SHA-256은
d85cff1b1487f9058994c06408ae8ad2a5a755d348d091d7b243bf94e10393f9,
추정 토큰은 1,625로 동일하다. 장면 null 제목·한국어·대상 로어·before/after history·
빈 옵션과 legacy·첫 대사·현재 ID 중복 제거·입력 비변경을 확인한다. opening None/빈 문자열,
이력 ID/순서/역할 오류 및 두 내부 non-null 전제의 실패도 확인한다.

전체 테스트 수에는 병렬 대화에서 추가한 테스트도 포함되며 이번 대화의 추가분은 37건이다.
TEST_DATABASE_URL을 제거한 실행이고 PostgreSQL·실제 모델/저장소 연동은 미검증이다.
실패 1건은 이전부터 남은 U06 계약 충돌이며 기대 완화·skip/xfail은 하지 않았다.
F02와 다른 감사 결함 수정은 별도다. 기존 Windows 실행 제한에 따라 품질 검사와 회귀는
require_escalated로 수행했다.

**다음 범위:** conversation의 HTTP router/schema mapper/schemas를 확인하고 모듈 전체
엄격 검사 편입을 마무리한다. nullable 시작 제목의 기존 HTTP 계약 충돌은 별도 이슈로
구분한다. 권장 모델은 GPT-6.1 Sol, 추론 Medium이다. 이미 정리한 서비스에 HTTP 타입을
연결하고 인증·응답·오류 계약을 검증하는 범위라는 작업별 판단이다.

## 타입 정리 우선 19차: 병렬 결과 정식 편입·conversation HTTP 완료 (2026-10-28)

credit 전체와 moderation의 완료 4파일을 직접 Ruff/mypy로 재확인한 후 필수 엄격 검사에
편입했다. credit은 8 source files, moderation은 repository/review.py,
mapper/persistence.py, types.py, service/util/validation.py만 포함한다. moderation의
연결 보완 command 파일 전체를 완료로 간주하지 않는다. 남은 서비스 6파일은 후속 범위다.
병렬 결과의 16+101=117항목은 18차 공용 prune에 이미 반영돼 중복 제거하지 않았다.

conversation router의 반환 미표기 5곳을 해소하고 디렉터리 전체를 필수 범위로 묶었다.
모듈 전체 15 source files의 mypy가 통과하며 conversation 기준선은 0개다.
이 단계의 시그니처 감소는 **5개(576 → 571)**다. Any/cast/type: ignore나 예외는
추가하지 않았다. credit 기준선도 0개이며 moderation은 남은 서비스 23항목이 있다.

- 기존 ResponseDto 반환을 명시하고 manual-lore의 raw dict/tuple에는 구체적 요소 타입과
  response_model=None을 사용했다. mapper는 포맷만 정리했다. DTO 이름·입출력 필드·
  인증 의존성·상태 코드·오류 변환·서비스 연결은 유지한다.
- 단독 conversation router의 전후 OpenAPI 정렬 JSON SHA-256이 동일하다.
  5경로·12스키마이며 digest는
  038ce3d43748781dec578d8270ec29e59311c22021d03f93d899e20f00c739f6이다.
- RuntimeStart.title=None을 시작 HTTP 스키마가 거절하는 기존 동작을 확인했다.
  실제 errors 경계에서는 ValidationError를 422로 변환한다. nullable 제목을 문자열로
  바꾸거나 HTTP 계약을 완화하지 않았다. 관련 제품 계약/결함은 별도 과제다.

| 검증 | 결과 |
|---|---|
| 병렬 완료 범위 직접 정적 검사 | credit 전체+moderation 4파일 Ruff 13파일 통과; mypy 12 source files 통과 |
| 병렬 결과 재검증+신규 대화 HTTP | 64 passed, 6 skipped (신규 HTTP 12건 포함) |
| 전체 API 통합 회귀 | 731 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 571개, 새 위반 없음; Ruff 157파일 통과; mypy 150 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |

신규 test_conversation_http의 12건은 실제 FastAPI 처리로 생성 201·버전 전환 changed=false,
신뢰된 owner/session과 경로/본문 UUID, 업데이트 만료·노트, snapshot/legacy 시작 내용·
nullable 참여자, manual 항목의 raw 응답 및 빈 OpenAPI 스키마를 확인한다. 서비스 오류의
404/422, 미연결 DB/인증의 503과 서비스 미호출, 요청 본문의 user_id 거절도 확인한다.
nullable 시작 제목은 기존 422 실패를 그대로 검증한다. 서비스 대역이며 실제 DB 인가·
잠금 검증을 대신하지 않는다.

통합 실행에서 credit 조회/account history 15건과 moderation 지정 범위 37건이 다시
통과했다. PostgreSQL 6건을 통과로 계산하지 않는다. 전체 실행은 TEST_DATABASE_URL을
제거했으며 DB 잠금·SAVEPOINT 경합·외부 모델/저장소는 미검증이다. 실패 1건은 기존
U06의 발행 후 편집 거절 기대/재발행 허용 구현 간 계약 충돌이다. 기대 완화·skip/xfail은
하지 않았다. Windows 실행 제한에 따라 필수 품질 검사와 회귀는 require_escalated로 실행했다.

**후속 병렬 권장:** 주 대화는 chatting/chat의 메시지 command·repository·관련 types,
credit 담당 대화는 commerce/billing의 저장소/mapper/usage·매출 귀속,
moderation 담당 대화는 남은 command/query 서비스 6파일을 맡는다. 모두 GPT-6.1 Sol,
추론 High를 권장한다. public service/types 계약을 보존하고 타 담당 모듈은 수정하지 않는다.
공용 기준선·검사 범위·통합 보고서는 주 대화에서만 갱신한다. 기능 감사 결함 수정은 별도다.

## 타입 정리 우선 20차: chat 메시지 쓰기·공유 저장소·관련 타입 (2026-10-28)

repository.py, service/command/messages.py, types.py의 3파일을 엄격 검사에 추가했다.
시작 시 mypy 진단 35개를 해소했다. 이 대화가 제거한 시그니처 항목은 **96개**
(repository 68개, messages 27개, AnswerConfig 반환 1개)다. metadata 필드 2개의 bare dict
보완은 시그니처 감소 수에 포함되지 않는다. Any/type: ignore/기준선 예외는 추가하지 않았다.
cast 1곳은 DELETE의 CursorResult/rowcount 반환 계약에 한정한다.

**병렬 기준선 구분:** 시작 공용 기준선 571개에서 prune 시 실제 항목은 404개였다.
이 대화의 96개 외에 billing 48개와 moderation 서비스 23개, 합계 71개의 해결이 관측됐다.
새 위반 0개를 확인한 주 대화가 --prune-baseline으로 시그니처만 제거했다. 이번에 그
모듈들의 엄격 검사 범위나 전체 완료 판정을 추가하지 않았으며 담당 대화의 최종 결과를
수령해 별도로 통합한다. chat에는 생성/답변 command·workflow·HTTP의 60항목이 남는다.

- 저장소의 세션·UUID·시각·Command/Info와 Entity/목록/None을 명시했다. get_message는
  삭제 영수증의 nullable message_id를 받아 기존 조회/충돌 흐름을 유지한다. scalar SQL,
  populate_existing·생성/입력 저장 분기·flush·lease 필터·history 갱신 조건은 같다.
- create_generation_prompt의 **values를 기존 호출의 다섯 키워드 필드로 명시했다.
  시각은 계속 DB 기본값이며 원문·digest·provider·출력 예산의 저장값은 같다.
  finish_generation은 상위의 확인/잠금 전제를 assertion으로 표현한다. DELETE는 SQLAlchemy
  일반 Result 타입에 없는 rowcount를 실제 DML CursorResult 계약으로 연결했다.
- 메시지 helper는 사용자/캐릭터 Command와 character Literal의 overload를 사용한다.
  캐릭터 경로의 타입 assertion은 내부 공개 wrapper의 입력 전제다. 영수증/메시지/마지막/
  교체 결과 Entity의 지역 이름을 분리하며 Entity 판단은 기존 mapper 뒤 Info로 수행한다.
- 기존 digest의 sender·str(slot)·content 직렬화, 영수증의 선행 재전송 반환, 교체/삭제 후
  재생성 거절, idle/참여자/버전/마지막 메시지/revision 검증을 유지한다. 파괴적 이력 변경은
  기존 memory 무효화→generation history 표시→메시지 변경 순서와 상위 트랜잭션에 참여한다.
- 답변 metadata를 재귀 AnswerJsonValue/AnswerMetadata로 표현해 v1/v2·확장 키를 보존한다.
  저장 JSON·깊은 복사/공유·runtime 검증·실행권/lease/과금 정책을 바꾸지 않았다.
  구체화된 metadata의 나머지 답변 소비부는 다음 엄격 검사 범위에서 함께 확인한다.

| 검증 | 결과 |
|---|---|
| 변경 전 messages/HTTP/query mapping/prompt command/product usage | 17 passed, 17 skipped |
| 변경 후 같은 범위 및 신규 메시지 계약 | 41 passed, 17 skipped (신규 24건 포함) |
| 전체 API 회귀 — 병렬 변경 포함 시점 | 774 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 404개, 새 위반 없음; Ruff 160파일 통과; mypy 153 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 정적 검사 | Ruff lint/format 통과; git diff --check 통과 |

test_chat_message_contracts의 24건은 사용자/내부 캐릭터 저장의 신뢰된 owner와 slot/digest,
pending 중 정확한 재전송 허용, 다른 입력/삭제/교체된 요청의 충돌, 편집·되돌리기의 무효화
순서, sender/버전/revision/마지막 메시지/진행 중 생성 거절, 기억 장애 시 쓰기 미호출,
인가 실패 및 잘못된 입력의 조회 차단을 확인한다. 저장소 대역과 실제 AsyncSession을
사용한 범위이며 실제 memory·DB 쓰기의 원자성을 증명하지 않는다.

SQLite SQL 검사는 메시지 조회의 대화 범위·캐시 갱신, ID/position 보존과 revision 증가,
AI/생성/model/token/emotion 출처 제거, 포함 삭제 건수·다른 대화 보존과 receipt SET NULL을
확인한다. 입력 참조 유무에 따른 생성 입력 저장, 사용자별 요청 조회, AI 출력 출처,
metadata/만료 lease·최초 history 무효화 시각·완료 결과 보존, 정확한 프롬프트 원문도 확인한다.
position은 테스트용 증가 함수이며 실제 PostgreSQL Identity가 아니다. receipt FK와 메시지
position UNIQUE만 복제한 최소 테이블이므로 전체 FK/CHECK/잠금/경합 검증은 아니다.

전체 실행에는 다른 대화의 신규 테스트도 포함되며 이번 대화의 추가분은 24건이다.
TEST_DATABASE_URL을 제거했고 실제 PostgreSQL·외부 모델/저장소 연동은 미검증이다.
실패 1건은 기존 U06 계약 충돌이며 기대 완화·skip/xfail은 하지 않았다. F02 등 감사 결함
수정도 별도다. 품질 검사와 회귀는 기존 Windows 제한에 따라 require_escalated로 실행했다.

**다음 범위와 병렬 권장:** 주 대화는 chat 생성/답변/프롬프트 저장 command의 실행권·
nullable·metadata 소비 타입을 정리한다. 이미 병렬 변경이 관측된 billing/moderation은
담당 결과를 받아 통합한다. 새 추가 대화는 identity의 repository/query/persistence/types와
reporting 세 모듈을 분리해 맡길 수 있다. 두 작업은 타 담당 폴더·공용 검사 파일을 수정하지
않고 기존 인가·비밀정보 노출·읽기 전용 정책을 유지한다. 권장 모델은 GPT-6.1 Sol,
추론 High다. 각각 인증 저장 계약과 조회 주체별 정보 경계를 함께 확인해야 하는 범위라는
작업별 판단이다.

## 타입 정리 우선 21차: billing·moderation 통합 및 chat 생성/답변 command (2026-10-28)

담당 대화의 최종 결과를 받아 billing·moderation 전체를 직접 재검사했다. 두 모듈은
Ruff format 42파일/check와 mypy 40 source files를 통과했다. billing 전체와 기존
moderation 4파일 대신 moderation 디렉터리를 공용 엄격 검사에 편입했다. 담당자가
보고한 기준선 해결 48+23개는 20차에 이미 제거했으므로 중복 감소로 계산하지 않는다.
통합 과정에서 두 모듈의 업무 코드는 수정하지 않았다.

주 대화는 chat의 service/command/generation.py, answers.py, prompts.py를 정리했다.
시작 mypy 진단 12개를 해소했고 command 전체 5파일이 Ruff/mypy를 통과했다.
generation의 결과 digest는 GenerationResult → str이며 입력 검증·직렬화는 같다.
세션은 AsyncSession으로 명시했고 저장 결과는 generation_entity로 구별했다.
answer_metadata의 재귀 JSON 값은 기존 비교·저장 계약으로 연결되며 새 Any/cast/ignore,
JSON 기본값/보정/복사 또는 기준선 예외는 추가하지 않았다.

프롬프트 저장의 잠금 후 재조회에는 앞선 존재 확인과 conversation 잠금의 전제를
assertion으로 표현했다. 전제가 깨진 None 경로는 AttributeError 대신 AssertionError다.
정상 경로의 원문/digest·provider·예산, 기존 기록 재전송 선행 반환, 실행권·예약·lease
검사 및 잠금/트랜잭션 순서는 유지한다. 생성의 stale 처리·사용량·청구 크레딧과
terminal 결과 멱등성, 답변의 실행 스냅샷·result_ready 불변성도 변경하지 않았다.

**기준선 구분:** 공용 기준선 404개에서 실제 해결 항목만 --prune-baseline으로 제거해
284개가 됐다. 이번 주 대화의 해결은 9개이며, 나머지 111개는 진행 중인 identity와
reporting 병렬 변경에서 관측됐다. 새 위반은 0개다. 해당 병렬 모듈의 완료 판정과
엄격 검사 편입은 담당 결과를 수령한 뒤 별도로 수행한다. chat의 남은 시그니처는
workflow/answers.py 44개와 router 7개, 합계 51개다.

| 검증 | 결과 |
|---|---|
| billing·moderation 전체 직접 정적 검사 | Ruff format/check 통과; mypy 40 source files 통과 |
| chat command 전체 직접 정적 검사 | Ruff format/check 통과; mypy 5 source files 통과 |
| chat 생성/답변/프롬프트·billing persistence·moderation 관련 회귀 | 108 passed, 63 skipped |
| 전체 API 회귀 — 병렬 변경 포함 시점 | 833 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 284개, 새 위반 없음; Ruff 202파일 통과; mypy 193 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

새 테스트를 추가하지 않고 기존 회귀를 사용했다. 전체 테스트 증가분은 병렬 작업을
포함하며 이번 주 대화의 추가 테스트 수가 아니다. TEST_DATABASE_URL을 제거했고
실제 PostgreSQL·외부 모델 호출은 미검증이다. skipped를 통과로 계산하지 않는다.
실패 1개는 기존 U06의 발행 후 편집 거절 기대/재발행 허용 구현 사이 계약 불일치다.
기대 완화·skip/xfail 또는 해당 제품 코드를 수정하지 않았다. 품질 검사와 회귀는
Windows asyncio의 로컬 소켓을 허용하기 위해 require_escalated로 실행했다.

**다음 작업:** chat/service/workflow/answers.py의 세션 팩토리·준비/재개·JSON metadata
소비·결과 staging/완료/복구 타입을 정리한다. LLM 호출 전후 트랜잭션과 실행권/lease,
불확실한 호출 재실행 금지, billing 예약 확정/해제 계약을 함께 추적해야 한다.
GPT-6.1 Sol, 추론 High를 권장한다. 병렬 identity/reporting은 담당 결과 통합을 기다리고,
추가 작업은 workflow와 겹치지 않는 chat HTTP router 또는 llm 경계의 사전 조사로
나눌 수 있다. 공용 검사 범위·기준선·통합 보고서는 주 대화에서만 갱신한다.

## 타입 정리 우선 22차: chat 답변 workflow (2026-10-28)

service/workflow/answers.py의 초기 mypy 진단 61개를 해소했다. 준비 결과의 기존 5요소
tuple은 명시적 타입 별칭으로, 완료 outcome은 기존 Literal 집합으로 표현했다.
세션·세션 팩토리·UUID·metadata·lease·예외와 helper/준비/재개/staging/완료/복구의
반환을 명시했다. self.sessions와 기존 Python 호출 인자 이름을 유지한다.
workflow 전체 4파일이 직접 지정 Ruff/mypy를 통과해 memory.py 단일 경로 대신
workflow 디렉터리를 공용 엄격 검사에 편입했다.

저장 metadata는 개방형 AnswerMetadata를 유지한다. 소비 필드만 표현한 내부
_StoredIdentity/_StoredBilling/_StoredAnswer의 TypedDict 읽기 뷰를 추가했다.
staging token·복구 token·완료 결과·응답 변환의 네 cast는 이 workflow의 기존 v1/v2
작성 규칙을 근거로 한다. runtime JSON 검증·복사·변환·기본값 추가가 아니며,
누락 키·손상 타입의 기존 오류 정책과 확장 키/참조 공유를 그대로 둔다.
Any/ignore/기준선 예외는 추가하지 않았다. 손상 JSON에 대한 새 정책은 별도다.

- 요청 identity의 manual_entry_ids는 기존대로 비어 있으면 키를 생략하고, 값이 있으면
  문자열을 정렬한 목록이다. JSON 재귀 목록의 불변성 문제는 명시적 요소 타입으로
  표현했으며 값·정렬·중복 처리와 digest 입력은 같다.
- 실행 token은 기존과 같은 한 번의 UUID 문자열을 지역 변수에 보관해 prompt 저장에
  전달한다. 예약 metadata와 값이 같으며 실행권·lease·불변 스냅샷 정책은 같다.
- digest 직렬화·공급자 결과/usage 검증·실패 분류를 유지했다. 알 수 없거나 범위를
  벗어난 usage는 기존 정수 저장 경계에서 0이며 원본 TokenUsageInfo의 None과 구분한다.
- 기존 요청 선행 확인, 준비 후 재검증, quote/generation/credit/prompt의 같은 예약
  트랜잭션, commit 반환 뒤 외부 호출, calling/result_ready staging, 불확실 호출
  재실행 금지, 만료 lease 복구를 유지한다. 완료의 예약 확정/해제·금액 일치 확인과
  memory 작업 예약도 그대로다. 이 단계는 해당 계약의 실제 DB 검증 완료가 아니다.

**기준선 구분:** 284개에서 새 위반 없이 실제 해결 항목을 prune해 201개가 남았다.
주 대화의 workflow 시그니처 해결은 44개다. 나머지 39개는 병렬 chat HTTP 7개와
LLM 저장소/mapper/query 32개다. 해당 병렬 범위의 엄격 검사 편입과 완료 판정은
담당 결과를 받은 뒤 별도로 통합한다. chat 전체의 알려진 시그니처 항목은 현재 0개지만,
이것이 HTTP 담당 결과를 수령했거나 chat 전체를 직접 검사했다는 뜻은 아니다.

| 검증 | 결과 |
|---|---|
| chat workflow 전체 직접 정적 검사 | Ruff format/check 통과; mypy 4 source files 통과 |
| prompt workflow/command·answer prompt·nonstream·과금·가격/HTTP·생성 관련 회귀 | 41 passed, 57 skipped |
| 전체 API 회귀 — 병렬 변경 포함 시점 | 909 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 201개, 새 위반 없음; Ruff 205파일 통과; mypy 196 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

새 테스트를 추가하지 않고 기존 업무 회귀를 사용했다. 전체 테스트 증가분은 다른
대화의 병렬 변경을 포함한다. TEST_DATABASE_URL을 제거했으며 실제 PostgreSQL
잠금·동시성·원자성과 공급자 호출은 미검증이다. skipped를 통과로 계산하지 않았다.
실패 1건은 기존 U06의 발행 후 편집 거절 기대/재발행 허용 구현 사이 계약 불일치다.
해당 테스트의 기대·skip/xfail과 product 코드를 수정하지 않았다. 품질 검사/회귀는
Windows asyncio 로컬 소켓 허용을 위해 require_escalated로 실행했다.

**다음 범위:** 담당 결과 수령 시 chat HTTP·LLM 및 identity/reporting의 공용 엄격 검사
편입을 우선한다. 독립적인 주 작업은 governance/admin의 태그 관리·모델/작품 관리
경계 타입이다. 관리자 재검증·공개 service/types 호출·기존 HTTP 계약을 함께 검토해야
하므로 GPT-6.1 Sol, 추론 High를 권장한다. 진행 중인 병렬 범위와 공용 검사 파일의
소유권은 유지한다.

## 타입 정리 우선 23차: admin 태그·상품 정책·모델 종료 경계 (2026-10-28)

governance/admin의 5개 코드 파일에서 mypy 23건·Ruff 25건을 해결했다. 모듈 전체
Ruff format/check와 mypy 16 source files를 직접 확인하고 admin 디렉터리를 공용
엄격 검사에 편입했다. Any/cast/ignore·기준선 예외는 추가하지 않았다.

- tag_router의 16개 handler에 목록 DTO·단건 DTO·본문 없는 None 반환을 명시했다.
  여러 ID/행위자/태그 목록을 가진 Command 생성은 키워드로 구별했다. target_id,
  actor_id, tag_id, names와 description의 값·누락/None 의미는 같다.
- mapper/tags는 공개 TagInfo와 Iterable[InternalTagInfo]를 받는 순수 DTO 변환이다.
  기존 Pydantic model_validate와 from_attributes, 목록 순서 및 반복자 소비를 유지한다.
  tuple/list/generator를 위해 입력을 불필요하게 한 컨테이너 타입으로 좁히지 않았다.
- 상품 정책 command의 세션을 AsyncSession으로 명시하고 product 공개 Command의
  snapshot/product/actor ID·만료·reason·status를 키워드로 전달한다. 상품 만료 router는
  기존 ExpiryChangedResponseDto를, 상품 상태와 모델 종료의 204 handler는 None을
  반환한다고 명시했다.
- 경로·본문·응답·상태 코드·공유 의존성 함수 정체성·HTTP 오류 변환을 유지한다.
  tag/content/product/llm 공개 서비스의 최신 활성 관리자 재검증 책임, 태그 source와
  assigned_by의 서비스 결정, 미연결 인증 훅의 기존 실패 동작도 바꾸지 않았다.
  새 SQL/조회/트랜잭션/인증 연결과 구조 재편은 없다.

기준선은 새 위반 없이 --prune-baseline으로 201개에서 176개로 줄었다. 제거한 25개는
이번 admin 범위에 한정된다(tag router 16, mapper 4, command 2, product router 2,
model router 1). 병렬 작업의 완료 판정·공용 엄격 범위 편입은 추가하지 않았다.

| 검증 | 결과 |
|---|---|
| admin 전체 직접 정적 검사 | Ruff format/check 통과; mypy 16 source files 통과 |
| 태그·관리 HTTP·상품 만료/발행·모델 대체·콘텐츠 역할 관련 회귀 | 43 passed, 10 skipped |
| 전체 API 회귀 — 현재 병렬 변경 포함 | 909 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 176개, 새 위반 없음; Ruff 222파일 통과; mypy 212 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

새 테스트는 추가하지 않고 기존 계약 테스트를 사용했다. TEST_DATABASE_URL을 제거했으며
실제 PostgreSQL 관리자 역할 변경·잠금/경합·트랜잭션과 공급자 연동은 미검증이다.
skipped를 통과로 계산하지 않았다. 실패 1건은 기존 U06의 발행 후 편집 거절 기대와
재발행 허용 구현 사이 계약 불일치다. product 구현·테스트 기대·skip/xfail은 수정하지
않았다. 품질 검사와 회귀는 Windows asyncio 로컬 소켓 허용 환경에서 실행했다.

**다음 범위:** 병렬 담당 결과를 받으면 chat HTTP·LLM 및 identity/reporting의 엄격
검사 편입을 우선한다. 독립 주 작업은 app/use_cases/studio_*와 http/studio_publication.py의
조립부 타입 정리다. 콘텐츠 간 Command/Info/View 연결과 트랜잭션 계약을 보존하고,
기존 U06의 재발행 정책은 타입 정리 중 변경하지 않는다. GPT-6.1 Sol, 추론 High를
권장한다.

## 타입 정리 우선 24차: studio 상위 유스케이스·HTTP 조립부 (2026-10-28)

studio_components/content/diagnostics/publication과 http/studio_publication.py의 5파일에서
초기 mypy 진단 57개를 해소했다. 해당 파일들을 공용 엄격 검사에 편입했다. 새 테스트를
포함한 6파일 직접 지정 mypy와 Ruff lint/format도 통과했다. Any/ignore·기준선 예외는
추가하지 않았다. 기준선은 이번 범위의 해결 21개만 prune해 176개에서 155개가 됐다.

- 편집 문서의 work/character/asset/lore/scene 필드 뷰는 기존 studio_content.py에,
  서버 매핑·영수증·저장 release 뷰는 studio_components.py에 TypedDict로 표현했다.
  새 도메인 모듈/계층을 만들거나 기존 파일 책임을 옮기지 않았다. 반환용 로어 값은
  공개 LorebookEntryCommandFields를 재사용한다.
- cast 18곳은 기존 필드 검사 후의 편집 값, 서버 작성 receipt/mapping, 이 객체를
  product의 재귀 JSON으로 넘기는 경계, 로어 helper가 만든 진단 항목을 표현한다.
  기존 legacy/editor JSON의 구조 전제와 손상 데이터 오류를 유지하는 정적 뷰이며
  새로운 런타임 검증·정규화·복사가 아니다. activation 등 하위 도메인이 검증하는
  옵션은 계속 전달한다. 잘못된 저장 JSON을 타입만으로 안전하다고 판단하지 않는다.
- 구성 매핑의 깊은 복사와 확장 키, legacy character 순서·lore 제목 대응 및 모호성
  충돌, 원본과 서버 복사본 ID 구별, 업로드 준비 재사용을 유지했다. 페이지 cursor는
  실제 LorebookCursor로, 생성 캐릭터/다음 항목 ID와 이미지 ID 집합은 UUID로 명시했다.
- 발행 fingerprint·revision/영수증 재전송 순서, source별 캐릭터 수정·이미지 연결/삭제,
  lorebook/entry 생성·갱신·삭제, 시작 항목 분리 후 설정, product/release/receipt 쓰기와
  상위 트랜잭션은 같다. 기존 이미지 입력과 기존 asset Info 변수만 구별했다.
  release 영수증의 **kwargs를 유지해 예상치 못한 저장 필드의 기존 TypeError를 숨기지
  않는다. Product visibility의 반환 Literal도 명시했다.
- HTTP 입력은 자유 객체 목록을 유지하며 새 TypedDict 입력 모델로 바꾸지 않았다.
  진단·업로드 준비의 response_model=None은 새 반환 주석으로 인한 응답 필터링/스키마
  변경을 막는다. 기존 DTO·신뢰된 owner/session·409/422·무형식 응답 계약은 같다.
- use_cases ARCHITECTURE에 현재 조립 타입을 기록하고 과거 재발행 거절 설명과 현재
  구현의 불일치가 U06임을 명시했다. 발행 정책·product 구현·실패 테스트는 변경하지 않았다.

| 검증 | 결과 |
|---|---|
| 대상 5파일과 신규 테스트 직접 정적 검사 | Ruff format/check 통과; mypy 6 source files 통과 |
| 기존 studio·repository workflow·lore 진단·product HTTP/발행 회귀 | 76 passed, 3 skipped |
| 신규 studio JSON/HTTP 호환 회귀 | 8 passed |
| 전체 API 회귀 — 현재 병렬 변경 포함 | 917 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 155개, 새 위반 없음; Ruff 227파일 통과; mypy 217 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

test_studio_type_contracts의 8건은 실제 FastAPI→로어 진단의 한국어/확장 입력,
id/keywords/enabled/tokenBudget/activation 오류의 기존 422, 진단/업로드 준비의 빈
OpenAPI 응답 스키마, 신뢰된 소유자·revision과 무필터 응답·409, 기존 서버 매핑의
깊은 복사와 확장 데이터 보존을 확인한다. 서비스 대역과 unbound AsyncSession을
쓰며 실제 DB 인가/동시성/원자성을 검증한 것으로 해석하지 않는다.

TEST_DATABASE_URL을 제거했고 실제 PostgreSQL과 외부 미디어/모델 연동은 미검증이다.
skipped를 통과로 계산하지 않았다. 전체 실패 1건은 기존 U06 계약 불일치이며 기대
완화·skip/xfail은 하지 않았다. 품질 검사와 회귀는 Windows asyncio 로컬 소켓을
허용하는 환경에서 실행했다.

**다음 범위:** 병렬 범위(chat HTTP·LLM·identity/reporting)의 직접 검증과 엄격 검사
편입을 우선 정리하고, 독립 타입 작업은 나머지 조회/통계 use_cases와 공용 HTTP
조립부다. 공개 서비스의 소유자/페이지/집계 결과와 기존 읽기 계약을 보존한다.
GPT-6.1 Sol, 추론 High를 권장한다.

## 타입 정리 우선 25차: 병렬 결과 직접 통합·조회/통계 조립부 (2026-10-28)

주 대화가 현재 작업 트리의 병렬 범위를 직접 검사해 공용 엄격 검사에 편입했다.
chat 전체, reporting 세 모듈 전체, identity의 repository/mapper/persistence/service/query/
types 4파일, llm의 repository/mapper/persistence/service/query 3파일이다. 경로 표현에서
mapper/persistence와 service/query는 각각 .py 파일을 뜻한다. identity 인증/보안과
LLM 어댑터/모델 대체 전체를 완료한 것은 아니다. 별도 최종 메시지를 수령했다고
가정하지 않고 현재 파일의 직접 검사와 통합 회귀를 근거로 범위를 확장했다.

초기 병렬 62소스 지정 mypy에서는 chat dependencies의 no-any-return 1건만 남았다.
main이 설정한 앱 상태의 AnswerOrchestrator를 cast로 연결해 기존 None→503 및 실행/
테스트 대역을 유지했다. 새 isinstance 검사나 인증 연결은 없다. 병렬 대상의 Ruff
format/check는 66파일에서 통과했고 확대한 공용 mypy도 모두 통과했다. 다른 담당
모듈의 업무 코드는 수정하지 않았다.

나머지 use_cases와 조회 HTTP에서는 초기 22건 중 별도 미디어 범위 8건을 제외한
14건을 해소했다. 위 dependencies 1건을 포함해 이번 주 대화의 초기 진단 15건을
해소했다. use_cases 전체와 조회 HTTP/mapper/credit 계약을 엄격 범위에 편입했다.
기준선은 이번 해결 11개만 prune해 155개에서 144개가 됐다. 이전에 제거한 병렬
범위의 기준선 항목을 다시 해결 수에 포함하지 않는다. Any/ignore/예외는 추가하지 않았다.

- account_overview·conversation_directory·product_statistics의 세션을 AsyncSession으로
  명시했다. 본인 건수의 소유 공개 서비스 호출과 정수 사전 결과를 유지한다.
- 최근 대화는 소유 metadata 100개 단위 스캔→해당 ID의 chat 활동 조회→활동 시각/UUID
  역순 정렬→cursor 제외/페이지 추출을 유지한다. 빈 대화는 생성 시각을 쓰고 total은
  cursor 적용 전 소유 전체 건수다. 공개 View의 last_activity_at=None 기본값은 유지한다.
  두 cast는 조립 행의 확정 시각과 기존 cursor 쌍 검증을 표현한다. 라이브 조회의 이동/
  중복 가능성이나 페이지 일관성 정책을 바꾸지 않았다.
- http/mapper/conversation_directory.py를 추가해 RecentConversationsPageView를 기존
  ConversationListPageResponseDto로 변환한다. 이 View를 ConversationListPageInfo 전용
  mapper에 넘기지 않는다. 기존 Pydantic from_attributes 변환을 유지해 preview/activity/
  total을 보존하며 도메인 mapper가 상위 use_cases 타입을 역으로 참조하지 않는다.
- 통계의 generation 사실 목록은 같은 요소 값의 목록으로 product의 legacy None 허용
  요소 타입에 연결한다. 0/None·통화·날짜·조회 순서와 날짜 트랜잭션/큐 완료 정책은 같다.
- credit DTO validator는 Self 반환을 명시했다. credit cursor의 cast는 DTO의 쌍 검증
  근거이며 원본 시각/ID를 그대로 전달한다. malformed DTO 우회 생성에 새 검사를 추가하지
  않았다. 목록·잔액·카탈로그는 기존 DTO 반환, overview-counts는 response_model=None으로
  기존 빈 응답 스키마와 무필터 동작을 유지한다.

| 검증 | 결과 |
|---|---|
| 병렬 통합+조회/통계 관련 기존 회귀 | 171 passed, 7 skipped |
| 신규 활동 페이지·HTTP mapper 회귀 | 6 passed; 직접 Ruff/mypy 통과 |
| 전체 API 회귀 — 현재 작업 트리 | 923 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 144개, 새 위반 없음; Ruff 284파일 통과; mypy 269 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

test_read_composition_contracts의 6건은 여러 metadata batch를 넘는 활동 정렬, 동률 UUID
보조 키, cursor 전후 total 보존·끝 페이지, 빈 대화 생성 시각/nullable title, 소유자 범위·
bounded scan, preview/activity를 가진 HTTP DTO 변환과 잘못된 cursor/limit의 조회 이전
거절을 확인한다. 서비스 대역과 unbound AsyncSession을 사용하므로 실제 DB 인가/경합을
검증하지 않는다. 통합 기존 회귀에는 reporting·identity/LLM persistence·chat HTTP·credit
내역·통계·repository workflow가 포함된다.

TEST_DATABASE_URL을 제거했으며 실제 PostgreSQL·외부 모델/메일/저장소는 미검증이다.
skipped를 통과로 계산하지 않았다. 전체 실패는 기존 U06 발행 계약 불일치 1건이며
해당 구현·테스트 기대·skip/xfail은 수정하지 않았다. 품질 검사와 회귀는 Windows
asyncio 로컬 소켓을 허용하는 환경에서 실행했다.

**다음 범위:** http/media.py의 미디어 의존성·업로드 body·다운로드 stream/응답 타입을
정리한다. 업로드 크기 제한·소유권·임시 파일 수명·취소/실패 정리와 기존 헤더/상태 계약을
유지해야 하므로 GPT-6.1 Sol, 추론 High를 권장한다. 이후 identity 인증/보안, LLM
어댑터/대체, 저장소·실행 진입점이 남는다.

## 타입 정리 우선 26차: 미디어 바이너리 HTTP·ASGI 스트림 (2026-10-28)

http/media.py의 초기 mypy 8건을 해소했다. contextmanager는 Iterator[None], chunk
생성기는 AsyncIterator[bytes], 응답 호출은 Starlette Scope/Receive/Send → None으로
명시하고 다운로드 반환은 MediaStreamingResponse다. Command의 여러 ID/헤더 필드는
기존 값 그대로 키워드로 구별한다. 맨 앞의 분리된 workflow import도 import 구역으로
옮겼으며 새 계층·서비스나 반환 wrapper는 만들지 않았다.

cast는 3곳이다. 두 미디어 서비스는 main이 app.state에 조립한 실제 서비스 타입을
연결하며 실행/테스트 대역을 유지한다. 상태 누락의 기존 AttributeError를 새 fallback/
503으로 바꾸지 않았다. 기본 w+b SpooledTemporaryFile은 downstream fingerprint와
저장소가 쓰는 seek/read binary 동작을 제공하지만 stub의 명목 타입이 BinaryIO가
아니므로 업로드 경계에서 연결한다. 새 바이너리 wrapper·복사·rewind는 추가하지 않았다.
Any/ignore/기준선 예외는 추가하지 않았다.

32 MiB 수신 한도와 1 MiB spool 임계값, HTTP 수신 후 파일 EOF 상태 및 서비스의
기존 rewind 책임, 64 KiB 전송, with/finally 자원 정리 순서를 유지한다. 기존 owner
의존성·경로·201/413·입력/저장 오류 번역, 상품/버전/media/user 전달, Content-Length/
MIME/private no-store/nosniff/inline 헤더도 같다. stream 시작 뒤 읽기 오류/취소는
기존대로 전파되며 media_errors에서 JSON 오류로 재변환하지 않는다.

공용 http 전체를 직접 Ruff/mypy로 확인한 뒤 개별 경로 대신 디렉터리로 공용 엄격
범위를 통합했다. 직접 mypy는 HTTP 20소스에서 통과했으며 신규 테스트 포함 21소스도
통과했다. 기준선은 새 위반 없이 이번 media의 9개 항목만 prune해 144개에서 135개가
됐다. asset_storage 어댑터 전체의 엄격 검사 완료를 뜻하지 않는다.

| 검증 | 결과 |
|---|---|
| HTTP 전체+신규 테스트 직접 정적 검사 | Ruff format/check 통과; mypy 21 source files 통과 |
| 기존 media HTTP·character media 계약/서비스·asset storage 회귀 | 29 passed, 30 skipped |
| 신규 미디어 전송 회귀 | 9 passed |
| 전체 API 회귀 — 현재 작업 트리 | 932 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 135개, 새 위반 없음; Ruff 289파일 통과; mypy 274 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

test_media_transport_contracts의 9건은 1 MiB를 넘는 binary payload의 실제 spool
seek/read·열린 수명과 정상/ValueError/RuntimeError 후 종료, 축소한 한도로 수신 초과
시 서비스 미호출/파일 종료, ASGI 정상·읽기 오류·CancelledError의 원래 전파와 reader
종료를 확인한다. 실제 FastAPI 캐릭터/상품 읽기의 서로 다른 신뢰된 owner, Command
스코프·byte 응답·보안 헤더·기존 빈 OpenAPI 응답 스키마도 확인했다. 기존 send 실패
종료 테스트는 유지한다. 서비스/reader는 대역이므로 실제 DB 인가·S3·네트워크 단절·
공급자 스레드 종료까지 증명하지 않는다.

TEST_DATABASE_URL을 제거했다. 실제 PostgreSQL·S3·외부 공급자는 미검증이며 skipped를
통과로 계산하지 않았다. 전체 실패 1건은 기존 U06 발행 계약 불일치다. 해당 product
구현·테스트 기대·skip/xfail은 수정하지 않았다. 회귀와 품질 검사는 Windows asyncio
로컬 소켓을 허용하는 환경에서 실행했다.

**다음 범위:** LLM 모델 대체의 command/views/util과 관련 공개 타입을 정리한다.
후보 허용 범위·모델 활성/종료 시각·reasoning effort 선택·대체 이력 계약을 보존한다.
GPT-6.1 Sol, 추론 High를 권장한다. 실제 SDK 호출은 별도 검증 범위로 둔다.

## 타입 정리 우선 27차: LLM 모델 대체·공개 타입 (2026-10-28)

types.py와 service/command/replacement.py·views/replacement.py·util/replacement_policy.py의
초기 mypy 12건을 해소했다. 공개 capabilities 구체화에 연결되는 service/query.py와
http/model_catalog.py도 보완했다. repository/mapper·공개 types·service 전체 직접 지정
mypy 15소스와 Ruff를 통과해 service 디렉터리·types.py·mapper 디렉터리를 공용 엄격
검사에 편입했다. LLM 어댑터 전체의 완료 판정은 추가하지 않았다.

- ModelInfo.capabilities의 bare dict를 DB JSONB의 개방형 재귀 ModelCapabilityValue 사전으로
  표현했다. 임의 확장 키와 중첩 값은 유지하며 기존 깊은 복사를 바꾸지 않는다.
  ModelCapabilities는 알려진 family/effort를 읽는 별도 TypedDict 뷰다. 공개 사전 자체를
  닫힌 schema로 바꾸거나 런타임 입력 검증·정규화를 추가하지 않았다.
- SnapshotModelSettings는 product snapshot의 id/reasoning_effort 문자열 소비 계약이다.
  세션은 AsyncSession, 후보·지원 effort는 Iterable, 정책은 Mapping, 선택 결과와 순위
  tuple은 구체 타입으로 표현했다. model_entity/replacement_entity를 구별하며 service는
  기존 mapper 뒤 Info/존재 여부로 판단한다.
- cast 7곳은 catalog effort(query/정책/HTTP) 3곳, allowlist container, snapshot 설정
  2곳, notice unavailable 문자열이다. 기존 catalog/product 작성 계약을 연결하며
  membership·알 수 없는 effort 제거·기본값·손상 입력 오류를 유지한다. 새 Any/ignore·
  기준선 예외는 없다. HTTP의 비문자열 effort 필터도 유지한다.
- same_family/same_provider/allowlist와 원본/비활성/종료/미지원 후보 제외, 같은 계열→
  같은 provider→effort 거리→UUID 문자열 순위 및 effort 동률의 낮은 단계 우선을 유지한다.
- deadline=max(공지 시각,종료-1일), 원본 사용 가능 여부에 따른 계획/즉시 전환, 대체
  불가 시 pause/use_original_until_shutdown 정책, snapshot 잠금과 상위 트랜잭션,
  snapshot/from/to 이력 존재 확인/삽입은 같다. 이력은 대상을 영구 고정하지 않는다.
  notice는 쓰지 않고 매 실행에서 다시 판단하며 SDK 호출은 없다.

기준선은 이번 대체 command/views/util의 12개 해결 항목만 prune해 135개에서 123개로
줄었다. capabilities 필드의 bare dict 제거는 시그니처 기준선 감소 수에 포함하지 않는다.

| 검증 | 결과 |
|---|---|
| LLM 저장소/mapper/types/service 전체 직접 정적 검사 | Ruff format/check 통과; mypy 15 source files 통과 |
| 연결된 product 발행·HTTP catalog·신규 테스트 포함 직접 mypy | 18 source files 통과 |
| 모델 대체·LLM persistence·product lifecycle/views·LLM/embedding 회귀 | 93 passed, 3 skipped (신규 10건 포함) |
| 전체 API 회귀 — 현재 작업 트리 | 942 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 123개, 새 위반 없음; Ruff 301파일 통과; mypy 286 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 Ruff/mypy·변경 범위 git diff --check | 통과 |

test_model_replacement_contracts의 10건은 마감 직전·정각·원본 종료 시점의 안내/실행
일치, 안내의 무쓰기, 대체 불가 시 원본 사용 한계, 기존 대상 이력의 삽입 생략과 새
후보 재선택, 종료/비활성/미지원/원본 후보 제외와 UUID/effort 동률, 관리자 거절의
쓰기 차단 및 미존재 오류를 확인한다. 실제 타입의 Info와 unbound AsyncSession을
사용하고 공개 서비스/저장소는 대역이므로 행 잠금·DB 유일 제약/동시성 검증은 아니다.

TEST_DATABASE_URL을 제거했다. 실제 PostgreSQL·외부 공급자 호출은 미검증이며 skipped를
통과로 계산하지 않았다. 전체 실패 1건은 기존 U06 발행 계약 불일치이고 해당 구현·
테스트 기대·skip/xfail은 수정하지 않았다. 회귀/품질 검사는 Windows asyncio 로컬
소켓을 허용하는 환경에서 실행했다.

**다음 범위:** LLM 공급자 어댑터의 SDK client/응답·오류·종료 타입을 정리한다.
OpenAI/Anthropic/Voyage별 검증과 호출/취소/자원 종료 계약을 유지하며 실제 SDK 요청은
수행하지 않는다. GPT-6.1 Sol, 추론 High를 권장한다.

## 타입 정리 우선 28차: LLM 공급자 SDK client·응답·오류·종료 (2026-10-28)

초기 어댑터 8파일은 mypy 진단 없이 통과했지만 OpenAI/Anthropic의 client·응답 helper와
Voyage client에 명시적 Any가 남아 있었다. 이 시그니처 7항목을 정리하고 요청 kwargs의
Any 사전 2곳도 제거했다. 따라서 이번 성과는 기존 mypy 오류 수가 아니라 Any 경계의
구체화다. 기준선은 123개에서 해당 7개만 prune해 116개가 됐다. 새 Any/ignore/예외는 없다.

- adapters/sdk.py에 실제 사용하는 client 호출 Protocol, OpenAI/Anthropic 요청 TypedDict와
  dict/속성 읽기·문자열/정수/반복 필드의 정적 투영을 모았다. 기존 두 _attr의 중복을
  공유하며 private import 별칭은 유지한다. 새 실행 계층·SDK wrapper·자원 보관 객체는 없다.
- client 경계 cast 3곳은 설치 SDK 및 주입 client의 실제 호출 subset을 표현한다.
  response 투영 cast 3곳은 SDK 필드 타입만 연결한다. 같은 원본 값·참조·default를 반환하며
  dict/SDK 객체/SimpleNamespace를 모두 유지한다. 잘못된 bool/count/text를 변환하거나
  필터·검증·fallback하지 않는다. 오류 필드도 기존 status/request ID 값 그대로다.
- 원시 결과 변수는 provider_response다. OpenAI output_text·output refusal·incomplete
  사유와 상세 usage, Anthropic text-only 결합·cache 포함 알려진 token 합계와 stop 사유,
  Voyage의 입력/목적·벡터/차원/유한 수치·usage 검증을 유지한다. 원래 SDK 호출만 오류로
  번역하며 호출 후 extraction 오류를 새 LLMError로 숨기지 않는다. 추가 재시도는 없다.
- 종료 책임은 OpenAI/Anthropic의 선택적 async close(주입 client 포함), Voyage의
  자체 생성 client만 sync/async 종료하는 기존 정책이다. close 미존재 no-op과 close
  실패 전파, SDK 설정과 요청 body·reasoning·store=False·출력 예산도 같다.

설치 SDK openai 2.54.0·anthropic 0.125.0·voyageai 0.5.0의 로컬 시그니처를 확인했다.
OpenAI Docs 스킬을 적용하고 [output_text 공식 계약](https://developers.openai.com/api/docs/guides/text?lang=python),
[client 종료 설명](https://developers.openai.com/api/reference/python)도 대조했다. SDK/API/
모델 업그레이드·실제 공급자 요청·API 키 설정 변경은 수행하지 않았다.

LLM 모듈 전체를 직접 지정한 Ruff format/check와 mypy 25소스를 통과해 기존 세부 경로를
llm 디렉터리로 통합했다. 신규 테스트 포함 직접 mypy도 26소스에서 통과했다.

| 검증 | 결과 |
|---|---|
| LLM 전체 직접 정적 검사 | Ruff format/check 통과; mypy 25 source files 통과 |
| 기존 LLM·embedding·프롬프트·모델 대체/persistence 회귀 | 92 passed |
| 신규 SDK dict/usage/종료 회귀 | 11 passed; 직접 Ruff/mypy 통과 |
| 전체 API 회귀 — 현재 작업 트리 | 953 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 116개, 새 위반 없음; Ruff 312파일 통과; mypy 296 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

test_llm_sdk_contracts의 11건은 dict response의 누락 usage/0/손상 bool 원본 보존,
OpenAI의 total 미제공과 Anthropic의 알려진 값 합계 구분, malformed Anthropic usage의
호출 후 TypeError 및 재시도 없음, 주입 client의 close 미존재/실패 전파를 확인한다.
SDK 객체/예외 subclass·메시지 변환·거절/미완료·usage 상세·Voyage client 소유권 등은
기존 회귀로 다시 확인했다. SDK/네트워크 계약 자체를 외부 요청으로 검증한 것은 아니다.

TEST_DATABASE_URL을 제거했으며 실제 PostgreSQL·OpenAI/Anthropic/Voyage 요청은 미검증이다.
skipped를 통과로 계산하지 않았다. 전체 실패 1건은 기존 U06 발행 계약 불일치이며
해당 product 구현·기대·skip/xfail은 수정하지 않았다. 품질/회귀는 Windows asyncio의
로컬 소켓을 허용하는 환경에서 실행했다.

**다음 범위:** asset_storage의 S3/로컬 어댑터·팩토리 타입을 정리한다. 주입 client
소유권·동기 SDK 작업의 종료·stream 수명·오류 및 객체 키/메타데이터 계약을 보존한다.
실제 S3 요청은 수행하지 않으며 GPT-6.1 Sol, 추론 High를 권장한다.

## 타입 정리 우선 29차: asset_storage S3·로컬 어댑터·팩토리 (2026-10-28)

초기 mypy는 로컬 reader/open의 주석 누락 2건과 boto3/botocore stub 부재 4건이었다.
requirements-dev.txt에 boto3-stubs[s3]를 추가해 import 검사를 생략하거나 ignore하지
않고 해소했다. stub 적용 뒤 드러난 S3UploadFailedError 재노출 지점의 attr 진단도
원래 정의인 boto3.exceptions에서 가져오도록 정리했다. 설치 환경에서 기존/새 import가
같은 클래스 객체임을 확인했으므로 기존 예외 분류는 같다.

실제 설치는 boto3-stubs 1.43.93·botocore-stubs 1.43.120·mypy-boto3-s3 1.43.106·
types-s3transfer 0.19.3이다. botocore-stubs는 SDK와 같은 patch 배포가 없어 boto3-stubs의
의존성 resolver가 선택한 1.43 계열을 사용했다. boto3/botocore 런타임 1.43.93은
변경하지 않았다. pip check도 통과했다. production API requirements는 바꾸지 않았으며
새 개발 환경은 기존 requirements-dev.txt 설치 절차로 stub을 받는다. 설치 방식은
[boto3-stubs 배포 안내](https://pypi.org/project/boto3-stubs/)를 참고했다.

- 로컬 file_object와 _open_sync 반환을 BinaryIO/tuple[AssetMetadataInfo, BinaryIO]로
  명시했다. 파일 복사·원자적 교체/복구·키 경로/잠금 정책은 같다. settings.py는 Ruff
  형식만 조정했으며 설정값/기본값/분기를 변경하지 않았다.
- S3StorageClient는 실제 keyword-only upload/get/head/delete subset을 표현하고,
  S3ResponseBody는 동기 read/close를 표현한다. 설치 stub의 실제 S3Client와 테스트
  client가 이 타입으로 연결됨을 확인했다. 팩토리의 s3_client도 같은 타입이다.
  Any 시그니처 5개를 제거했고 새 wrapper·실행 계층·Any/ignore/예외는 추가하지 않았다.
- 메타데이터는 Mapping[str, object]로 읽고 두 cast는 SDK ContentLength 정수와
  get_object의 열린 body만 연결한다. 원래 int/str 변환·MIME fallback·ETag 정리·
  LastModified datetime 판정을 유지한다. 파싱 오류 body 종료와 원래 오류 cause도 같다.
- 원시 응답은 provider_response로 구별했다. 기존 현재 stream offset, seek 가능
  길이 사전 검증/non-seekable 선언 크기 신뢰, 호출자 입력 stream 수명·반환 reader
  종료, prefix/키·추가 HEAD 없음·존재하지 않는 키 삭제 성공·SDK 오류/retryable을 유지한다.
  to_thread와 SDK retry 설정·소유 client의 선택적 close도 같다. 기존 falsey 주입 client의
  client-or-default 정책은 기능 변경 없이 유지했다.

asset_storage 전체 직접 Ruff format/check와 mypy 12소스를 확인해 공용 엄격 검사에
편입했다. 신규 테스트 포함 13소스 mypy도 통과했다. 기준선은 이번 S3 4·local 2·factory
1항목만 prune해 116개에서 109개가 됐다. stub import 오류는 시그니처 기준선 수와 다르다.

| 검증 | 결과 |
|---|---|
| asset_storage 전체+신규 테스트 직접 정적 검사 | Ruff format/check 통과; mypy 13 source files 통과 |
| 기존 asset storage·미디어 HTTP/전송·character media 계약 회귀 | 38 passed, 2 skipped |
| 신규 S3 타입 경계 회귀 | 7 passed |
| 전체 API 회귀 — 현재 작업 트리 | 960 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 109개, 새 위반 없음; Ruff 325파일 통과; mypy 308 source files 통과; 계약/검사기 13 passed |
| pip check·변경 범위 git diff --check | 통과 |

test_asset_storage_type_contracts의 7건은 메타데이터 누락/잘못된 ContentLength의 body
종료, 기존 문자열 크기/MIME/ETag/시각 변환과 reader 수명, 업로드 시작 offset/입력
소유권·non-seekable 크기 신뢰, read/close timeout의 원인/오류 범위와 반복 종료를
가짜 client/메모리 stream으로 확인한다. 임시 로컬 파일/FakeS3Client의 기존 공통
저장·덮어쓰기·삭제·오류·스레드/소유권 계약도 다시 실행했다.

TEST_DATABASE_URL을 제거했다. 실제 AWS 자격 증명/버킷/객체를 읽거나 변경하지 않았고
실제 PostgreSQL·S3·네트워크/동시성은 미검증이다. skipped를 통과로 계산하지 않았다.
전체 실패 1건은 기존 U06 발행 계약 불일치이며 product 구현·기대·skip/xfail은
수정하지 않았다. 품질/회귀는 Windows asyncio 로컬 소켓을 허용하는 환경에서 실행했다.

**다음 범위:** identity 인증 서비스부터 세션 발급·갱신·토큰 소모·메일 workflow의 타입을
정리한다. 사용자/세션 잠금·refresh 재사용 폐기·실패 commit/rollback·원문 토큰 비노출
계약을 유지한다. HTTP/Google 보안 연결은 후속 범위로 구분하며 GPT-6.1 Sol, 추론 High를
권장한다.

## 타입 정리 우선 30차: identity 인증·세션/토큰·메일·JWT (2026-10-28)

service/authentication.py와 service/workflow/mail.py의 초기 mypy 진단 12건을 해소했다.
JWT claim 반환 연결에 필요한 security.py의 초기 3건과 AuthSettings 반환 주석도 함께
정리했다. 변경된 types와 이 네 파일을 직접 Ruff/mypy로 확인하고 네 파일을 엄격 범위에
추가했다. HTTP/Google 연결과 외부 어댑터 전체를 완료한 것은 아니다.

- SessionFactory의 sessions 인자/속성은 기존 호환 이름을 유지한다. 내부 현재 세션·
  UUID·시각·rate helper와 CredentialInfo/LoginInfo/UserInfo 및 tuple 반환을 명시했다.
  메일 의존성은 기존 MailSender Protocol이며 새 service/실행 계층은 추가하지 않았다.
- AuthTokenClaims는 기존 PyJWT와 codec의 type/jti/정수 시각/UUID 검증을 통과한 claim
  계약이다. 같은 사전과 확장 키를 그대로 반환한다. issuer/audience·고정 알고리즘·
  만료/재발급·비밀번호 강도·설정 검증을 바꾸지 않았다.
- cast 3곳은 이메일 ASCII 필드(기존 AttributeError→invalid_input 유지), 검증 뒤 JWT
  사전, 성공한 verify_password에 존재하는 저장 hash를 연결한다. 변환/기본값/추가 검증은
  없다. refresh에서 재사용이 아닌 경로는 LoginInfo를 생성했다는 assertion을 추가했다.
  이를 어기는 잘못된 override의 None 반환은 AssertionError이며 정상/실패/재사용의
  외부 계약은 같다. Any/ignore/기준선 예외는 추가하지 않았다.
- 사용자→세션 잠금, 대기 뒤 현재 시각 재확인, refresh 해시 회전과 절대 만료 유지,
  재사용 폐기 commit 후 refresh_reused, 일회용 조건부 소모와 비밀번호/증명/세션 폐기,
  중복 가입의 기존 자격증명 유지·rate limit·메일 전송 전 DB 확정을 보존한다.
  민감 원문은 repr 제외와 메일 fragment 전달에 한정하고 로그/응답에 추가하지 않았다.

기준선은 이번 authentication 25·mail workflow 4·security 3·settings 1항목만 prune해
109개에서 76개가 됐다. 기존 조회/저장소나 타 모듈 기준선을 다시 해결 수로 계산하지
않았다. 직접 변경 5파일+신규 테스트 mypy는 6 source files에서 통과했다.

| 검증 | 결과 |
|---|---|
| 대상 5파일+신규 테스트 직접 정적 검사 | Ruff format/check 통과; mypy 6 source files 통과 |
| 인증·JWT/OIDC·쿠키·persistence 관련 회귀 | 94 passed, 17 skipped (신규 17건 포함) |
| 전체 API 회귀 — 현재 작업 트리 | 977 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 76개, 새 위반 없음; Ruff 329파일 통과; mypy 312 source files 통과; 계약/검사기 13 passed |
| 신규 테스트 Ruff/mypy·변경 범위 git diff --check | 통과 |

test_identity_auth_contracts의 17건은 실제 JWT/mapper·연결 없는 AsyncSession transaction
event와 저장소/메일 대역으로 refresh 폐기 commit 후 오류, 회전 hash/절대 만료와 민감
repr, 비활성/미인증/미존재/다른 소유/폐기/만료 세션 거절, 세션 해시 저장·access TTL,
정상 재설정과 만료/소모/용도/조건부 소모 경쟁 실패의 쓰기 차단, 토큰 commit 뒤 메일
실패 보존·fragment/해시 대응, 중복 가입 무변경, 확장 JWT claim 보존을 확인한다.
Argon2는 테스트에서 작은 실제 비용으로 대체하며 운영 보안 파라미터 검증을 대신하지
않는다. SQL 대역이므로 실제 DB 잠금·동시성/폐기 영속성을 증명하지 않는다.

TEST_DATABASE_URL뿐 아니라 TEST_AUTH_DATABASE_URL도 제거했다. 실제 PostgreSQL·SMTP·
Google 통신은 미검증이며 skipped를 통과로 계산하지 않았다. 기존 Auth DB 17건은
실행하지 않았다. 전체 실패 1건은 기존 U06 발행 계약 불일치이고 해당 product 구현·
기대·skip/xfail은 수정하지 않았다. 품질/회귀는 Windows asyncio 로컬 소켓을 허용하는
환경에서 실행했다.

**다음 범위:** identity의 Google OIDC 서비스·workflow 및 SMTP/Google 외부 어댑터 타입을
정리한다. OAuth state 선소모·PKCE/nonce·provider/sub 연결과 검증 실패·메일 전송/종료
계약을 유지하며 실제 Google/SMTP 통신은 수행하지 않는다. GPT-6.1 Sol, 추론 High를
권장한다.

## 타입 정리 우선 31차: identity Google OIDC·workflow·SMTP 어댑터 (2026-10-28)

service/google.py, service/workflow/google.py, adapters.py를 직접 지정한 초기 엄격 mypy
진단 11건을 해결했다. 실행 세션·생성자·메일 내부 함수의 주석 누락과 SMTP의 동적
생성자 keyword 사전 전달이 원인이었다. 세 파일을 공용 엄격 범위에 추가했다.

- state 생성/소모 및 계정 연결의 session은 AsyncSession이다. GoogleLoginService의
  의존성은 AuthenticationService와 기존 GoogleVerifier Protocol이며 설정은
  AuthSettings다. 새 service/실행 계층·범용 wrapper는 만들지 않았다.
- 자체 생성한 Fernet 쿠키의 _GoogleFlow와 Google 응답의 _GoogleTokenResponse를
  내부 TypedDict로 표현했다. 두 JSON cast에는 생성자/공급자 계약 근거를 기록했다.
  실행 시 검증이 아니며 원본 값을 변환/필터하거나 기본값을 만들지 않는다. 기존
  복호화 TTL·state/redirect 검사·JWT 검증과 오류 번역 범위는 같다.
- SMTP는 SSL과 일반 생성자를 분기해 SSLContext를 SSL에만 전달한다. timeout=10,
  STARTTLS→선택적 login→send_message와 context 종료·오류 cause를 유지한다.
  SMTP/ID token 검증의 기존 to_thread 및 HTTP client 종료 후 검증 순서도 같다.
- state 선소모 commit→외부 검증→계정 연결+세션 발급 단일 트랜잭션, google sub→email
  잠금, provider/sub 기준 계정 식별, 같은 이메일 자동 병합 금지와 비활성/미인증 거절을
  유지한다. 고정 Google endpoint·client timeout/redirect 정책·scope·PKCE·nonce·
  issuer/audience/azp/서명/email_verified 검증·재시도 정책도 변경하지 않았다.

Any·ignore·기준선 예외는 추가하지 않았다. 시그니처 기준선은 이번 adapters 5·google
service 3·workflow 3항목만 prune해 76개에서 65개가 됐다. SMTP의 mypy 인자 오류 수와
시그니처 기준선 항목 수는 다른 집계다. 신규 테스트 포함 직접 정적 검사도 통과했다.

| 검증 | 결과 |
|---|---|
| 대상 3파일+신규 테스트 직접 정적 검사 | Ruff format/check 통과; mypy 4 source files 통과 |
| 인증·Google/JWT·쿠키·persistence 관련 회귀 | 120 passed, 17 skipped (신규 26건 포함) |
| 전체 API 회귀 — 현재 작업 트리 | 1003 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 65개, 새 위반 없음; Ruff 332파일 통과; mypy 315 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

신규 test_identity_google_contracts는 실제 Fernet 쿠키/PKCE 및 연결 없는 AsyncSession
transaction event와 저장소/검증기 대역을 사용한다. state 저장 해시·10분 기한·최소
scope, state 소모 commit 후 검증·공급자 실패 뒤 재사용 차단, 세션 저장 실패 rollback,
서명/state/형식/redirect/만료 쿠키의 외부 호출 차단과 계정 충돌/비활성/미인증 거절을
확인했다. 기존 sub 계정의 이메일이 공급자 변경으로 바뀌지 않는 것도 확인했다.

SMTP 대역은 none/starttls/ssl 및 인증 유무 6조합, 전송 오류의 context 종료와 예상
SMTP 오류/예상 밖 오류의 번역 범위를 확인한다. httpx.MockTransport는 고정 token 요청
본문·client 종료 후 원본 id_token 전달과 손상 응답 5형태의 거절을 확인한다. 기존 실제
RSA 서명 기반 OIDC claim 검증도 다시 실행했다. 이는 실제 외부 통신 검증이 아니다.

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했으며 실제 PostgreSQL·Google/JWKS·
SMTP/TLS 통신은 수행하지 않았다. SQL 대역은 실제 state 소모 원자성·잠금/경합·rollback
영속성을 증명하지 않는다. skipped를 통과로 계산하지 않았다. 전체 실패 1건은 기존
U06 발행 계약 불일치이고 product 구현·기대·skip/xfail은 수정하지 않았다. 품질/회귀는
Windows asyncio 로컬 소켓과 임시 파일을 허용하는 환경에서 실행했다.

**다음 범위:** identity의 http_security.py·router.py와 연결 HTTP 의존성/mapper 타입을
정리한다. 쿠키 수명·CSRF/Origin·오류 응답·access 복구와 refresh 폐기 계약을 유지한다.
GPT-6.1 Sol, 추론 High를 권장한다.

## 타입 정리 우선 32차: identity HTTP 보안·router·의존성 (2026-10-28)

identity 전체 직접 검사에서 초기 mypy 26건과 Ruff 47건을 해결했다. http_security.py의
인자/반환 주석과 router 13개 endpoint 반환 주석, get_verified_user_id의 Any 반환 전파가
대상이었다. http_security.py/router.py/dependencies.py를 변경하고 기존 DTO/schema
mapper도 검사해 identity 모듈 전체를 공용 엄격 범위로 통합했다.

- 쿠키 helper는 Response/AuthSettings/LoginInfo와 str/int 인자를 사용한다. CSRF 발급/
  검증은 AuthenticationService, 오류 renderer는 AuthError/Request→JSONResponse다.
  middleware는 Starlette RequestResponseEndpoint, route handler는 Request→coroutine→
  Response, 로그 filter는 LogRecord→bool로 표현했다. 기존 필터/분기/오류 범위는 같다.
- app.state의 선택적 authentication 3곳은 main의 조립 계약을 cast로 연결한다. 없을 때
  get_authentication의 auth_not_configured와 renderer/middleware의 선택적 처리를
  유지한다. 이를 필수 getter로 통합해 미설정 동작을 바꾸지 않았다.
- dependencies에 메일/Google workflow의 타입을 연결하는 getter 두 개를 추가했다.
  직접 app.state 속성을 읽던 다섯 router 호출이 이를 사용한다. 두 cast는 main의
  기존 workflow 조립 근거를 기록했으며 새 실행 계층·런타임 검사·fallback은 없다.
  속성이 없는 불완전한 조립의 기존 AttributeError도 유지한다.
- router는 기존 DTO·Response·RedirectResponse를 명시한다. user 응답의 공개 3필드,
  202 일반 메일 메시지, 204 빈 본문, Google callback 303과 cookie 전달 계약이 같다.
  의존성은 검증된 UserInfo.id를 UUID로 반환하며 DB/ORM을 HTTP에 전달하지 않는다.
- 쿠키 수명·보안 속성, 요청 제한/CSRF/Origin 순서와 오류 상태·본문/헤더, 민감 입력을
  반사하지 않는 422, access invalid_token의 refresh 복구와 refresh 폐기 쿠키 정리,
  callback flow 정리 및 기존 middleware 조기 거절 헤더를 유지한다.

새 Any·ignore·기준선 예외는 없다. 기준선은 이번 HTTP 보안 34·router 13항목만 prune해
65개에서 18개가 됐다. 기존 의존성의 Any 반환 오류는 별도 mypy 진단이며 기준선에
추가 집계하지 않았다. 남은 기준선은 main/worker/정리 CLI·공통 DB/오류 유틸에 있다.

| 검증 | 결과 |
|---|---|
| identity 전체+신규 테스트 직접 검사 | Ruff format/check 22파일 통과; mypy 21 source files 통과 |
| 인증 HTTP·Google/JWT·쿠키·persistence 관련 회귀 | 151 passed, 17 skipped (신규 31건 포함) |
| 전체 API 회귀 — 현재 작업 트리 | 1034 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 18개, 새 위반 없음; Ruff 342파일 통과; mypy 324 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

test_identity_http_contracts는 실제 FastAPI/ASGITransport·DTO·JWT와 서비스/workflow
대역을 사용한다. 로그인/갱신/현재 사용자/이메일 증명 Command 및 공개 필드 투영,
세션의 남은 절대 수명에 따른 cookie Max-Age 0/단기/900초 제한, 메일 202, 세션 종료/
재설정의 204·4쿠키 정리, Origin/CSRF 실패 6종, 입력 반사 없는 422, 외부 라우트의
쿠키 쓰기 middleware, Google start/callback 303·실패 시 flow만 정리, 검증 UUID와
rate_limited/미설정 서비스의 429/503 및 선택적 middleware 동작을 확인했다. 기존
지연 access 401의 refresh 복구·refresh 폐기 정책도 cookie_recovery 회귀로 재검증했다.

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했다. 실제 PostgreSQL·Google/JWKS·
SMTP·브라우저/프록시 통신은 미검증이며 skipped를 통과로 계산하지 않았다. 전체 실패
1건은 기존 U06 발행 계약 불일치이고 product 구현·기대·skip/xfail은 변경하지 않았다.
품질/회귀는 Windows asyncio 로컬 소켓과 임시 파일을 허용하는 환경에서 실행했다.

**다음 범위:** main 조립·lifespan과 worker/정리 CLI의 실행 의존성·자원 수명 타입을
정리한다. 기존 설정/주입·시작/종료·취소/복구·작업 실패 정책을 유지한다. 공통 DB
transaction/idempotency와 ReportingError는 이어서 정리한다. GPT-6.1 Sol, 추론 High를
권장한다.

## 타입 정리 우선 33차: main 조립·lifespan·worker·정리 CLI (2026-10-28)

main.py/memory_worker.py/media_cleanup.py/auth_cleanup.py의 초기 mypy 16건과 Ruff
14건을 해결했다. 네 파일을 공용 엄격 검사에 편입했으며 신규 회귀 11건을 추가했다.

- get_database_session은 AsyncIterator[AsyncSession]이며 동적 app.state의 factory는
  lifespan 조립 근거로 SessionFactory cast를 사용한다. lifespan 내부 sessions 지역명은
  session_factory로 통일했다. 기존 서비스 생성자/속성 이름과 키워드 호출 계약은 같다.
- create_app의 authenticate는 FastAPI가 해석하는 Callable[..., object] | None이다.
  sync/async 등 기존 callable 주입의 인자 해석을 FastAPI에 남기며 새 wrapper·반환값
  검증은 없다. asset_read_settings는 Iterable[AssetStorageSettings]로 generator/목록의
  기존 소비/순회 시점을 보존한다. read_storages와 LLM/embedding 어댑터 목록은 기존
  설정/서비스/Protocol로 표현했다. lifespan은 FastAPI→AsyncIterator[None]이다.
- 선택 설정의 cast 3곳(main 현재/과거, media cleanup)은 AssetStorageSettings 생성자의
  필수 설정 불변 조건을 표현한다. 원본 객체를 그대로 사용하고 새 None 처리나 검증은
  없다. Starlette 오류 handler는 Exception을 받아 등록된 AuthError로 cast한다. factory
  cast와 합쳐 이번 cast는 5곳이며 Any/ignore/기준선 예외는 추가하지 않았다.
- worker process는 MemoryWorkInfo→None, active는 Task[None] 집합이다. concurrency·
  once drain·작업 오류 격리·취소/종료 순서·lease/재시도 정책을 바꾸지 않았다.
- 미디어 cleanup은 Iterable[UUID]/datetime→int, CLI main은 NoReturn이다. 명시 ID별
  처리·건별 예외 이후 계속·일부 실패 1 반환과 출력의 예외 종류만 노출하는 정책을
  유지한다. auth cleanup은 None 반환만 명시하며 기존 finally의 engine 정리가 같다.

기준선은 이번 main 7·media cleanup 4·worker 2·auth cleanup 1항목만 prune해 18개에서
4개가 됐다. worker 지역 Task의 bare generic과 설정/어댑터/handler mypy 진단은
시그니처 기준선과 다른 집계다. 남은 기준선은 DB transaction/idempotency와
ReportingError에 있다. 기준선 4개가 전체 앱의 mypy 진단 총수라는 뜻은 아니다.

| 검증 | 결과 |
|---|---|
| 대상 4파일+신규 테스트 직접 검사 | Ruff format/check 통과; mypy 5 source files 통과 |
| 실행 진입점·기존 answer HTTP/lifespan·인증 HTTP 회귀 | 53 passed (신규 11건 포함) |
| 전체 API 회귀 — 현재 작업 트리 | 1045 passed, 1 failed, 288 skipped |
| 필수 품질 검사 | 기준선 4개, 새 위반 없음; Ruff 346파일 통과; mypy 328 source files 통과; 계약/검사기 13 passed |
| 변경 범위 git diff --check | 통과 |

test_runtime_entrypoint_contracts는 DB engine·저장소·공급자·작업 대역을 사용한다.
인증 설정 실패/과거 저장소 identity 중복 시 이미 생성한 자원의 역순 close, 정상
lifespan의 복구 태스크 취소 대기 후 Voyage/Anthropic/OpenAI/저장소/engine 종료,
소비자 예외 시 session factory context 종료, worker once의 여러 작업 drain과 건별
실패 뒤 계속 처리 및 서비스/engine 종료를 확인한다. 명시 미디어 ID의 generator
순회·cutoff 전달·부분 실패 1과 다음 ID 처리/자원 종료, auth cleanup 정상/설정 실패/
서비스 실패의 engine 정리와 원래 예외 전파도 확인한다.

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했다. 실제 PostgreSQL·S3·Google·SMTP·
LLM/embedding 요청은 수행하지 않았고 skipped를 통과로 계산하지 않았다. worker의
자원 검사 범위는 작업 실행 루프 진입 후 정상/건별 실패이며 공급자 초기화 중 실패와
실제 프로세스 signal·lease 경합은 미검증이다. 전체 실패 1건은 기존 U06 발행 계약
불일치이며 product 구현·기대·skip/xfail은 수정하지 않았다. 품질/회귀는 Windows
asyncio 로컬 소켓과 임시 파일을 허용하는 환경에서 실행했다.

**다음 범위:** 공통 DB transaction/idempotency와 ReportingError의 남은 기준선 4개를
정리하고, 전체 앱 직접 타입/린트 검사로 엄격 범위 밖 잔여 진단을 확인한다. 트랜잭션
중첩·rollback-only·멱등성 잠금·오류 계약을 유지한다. GPT-6.1 Sol, 추론 High를 권장한다.

## 타입 정리 우선 34차: 공통 DB 실행 계약·오류·전체 앱 검사 (2026-10-28)

db/transaction.py, db/idempotency.py, core/reporting.py를 정리하고 공용 엄격 범위에
추가했다. 기존 함수 시그니처 기준선의 마지막 4항목을 prune해 0개가 됐다. 이는
전체 앱 mypy 완료를 뜻하지 않는다. 직접 전체 검사에서 ORM JSON 진단 13건을 확인했다.

- use_case_transaction은 AsyncSession→AsyncIterator[None]인 asynccontextmanager다.
  lock_key는 AsyncSession/str/str→None이고 ReportingError 생성자는 None 반환이다.
  실행 본문·SQL·해시·예외 코드와 args·트랜잭션 소유권/잠금 정책은 바꾸지 않았다.
- 최외곽 한 번 commit, 잡힌 중첩 BaseException도 rollback-only, 다음 독립 범위 복구,
  표식 없는 기존 트랜잭션 거절과 advisory xact lock을 유지한다. savepoint/재시도/
  결과 캐시를 추가하지 않았고 Any·ignore·cast·기준선 예외도 추가하지 않았다.
- 전체 앱 최초 mypy는 366소스에서 16건이었다. 이번 공통 유틸의 3진단을 해결한 뒤
  8개 ORM 파일의 bare dict/list 요소 타입 13건이 남았다. ReportingError 생성자의
  반환 누락은 Ruff/시그니처 진단이며 mypy 해결 건수에 추가하지 않았다.
- 전체 앱 Ruff check는 초기 4건에서 0건이 됐다. 전체 format --check는 387파일 중
  db/models/product.py 1파일의 기존 포맷 차이가 남는다. 이 파일은 JSON 타입 후속
  범위와 함께 정리하며 이번에 무관한 모델 소스를 수정하지 않았다.

| 검증 | 결과 |
|---|---|
| 대상 3파일+신규 테스트 직접 검사 | Ruff format/check 통과; mypy 4 source files 통과 |
| 공통 DB·기존 transaction·reporting 회귀 | 63 passed, 7 skipped (신규 7건 포함) |
| 전체 API 회귀 — 현재 작업 트리 | 1052 passed, 1 failed, 288 skipped |
| 필수 품질 검사 — 현재 엄격 범위 | 기준선 0개, 새 위반 없음; Ruff 349파일 통과; mypy 331 source files 통과; 계약/검사기 13 passed |
| 전체 앱 직접 mypy | 실패: 366소스 중 ORM 모델 8파일에 13진단 |
| 전체 앱 직접 Ruff | check 통과; format은 product.py 1파일 미완료 |
| 변경 범위 git diff --check | 통과 |

신규 test_db_execution_contracts의 7건은 연결 없는 실제 AsyncSession의 transaction
event와 execute 대역을 사용한다. 중첩 단일 commit, 잡힌 ValueError/CancelledError의
전체 rollback과 이후 독립 commit, 기존 트랜잭션의 소유권 보존, 음수 signed/Unicode
고정 해시 벡터와 기존 SQL/인자·자체 commit 없음, 잠금 실행 오류의 동일 예외 전파와
소유자 rollback을 확인한다. SQL 실행과 영속 데이터·SAVEPOINT·실제 advisory lock
직렬화를 검증한 것은 아니다. 기존 PostgreSQL transaction 3건/reporting DB 4건은
환경변수가 없어 skipped이며 이를 통과로 계산하지 않았다.

후속 ORM 진단의 정확한 범위는 다음과 같다. 함수 기준선 검사기가 아닌 전체 mypy의
클래스 속성 진단이므로 기준선 0개와 모순되지 않는다.

| 모델 경로 (apps/api/app/db/models/) | 진단 수 | 위치 |
|---|---|---|
| product_statistics.py | 1 | 53 |
| product_usage.py | 1 | 79 |
| product.py | 3 | 88, 103, 105 |
| moderation_review.py | 4 | 82, 85, 155, 160 |
| moderation.py | 1 | 75 |
| model_routing.py | 1 | 52 |
| memory.py | 1 | 98 |
| lorebook.py | 1 | 192 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했다. 실제 PostgreSQL·migration·외부
공급자 호출은 수행하지 않았다. 전체 실패 1건은 기존 U06 발행 계약 불일치이며
product 구현·기대·skip/xfail은 변경하지 않았다. 품질/회귀는 Windows asyncio 로컬
소켓과 임시 파일을 허용하는 환경에서 실행했다.

**다음 범위:** ORM JSON 13진단을 저장 JSON·legacy/nullable·mapper/생성 입력 계약과
연결해 정리하고 product 모델 포맷을 적용한다. 타입을 채운 뒤 드러나는 컨테이너
불변성/소비부 진단도 함께 확인하며 전체 앱 엄격 검사 편입을 목표로 한다. SQL 컬럼·
default·migration·저장 구조는 유지한다. GPT-6.1 Sol, 추론 High를 권장한다.

## 타입 정리 우선 35차: ORM JSON·앱 전체 엄격 검사 완료 (2026-10-28)

db/models의 8파일에 남은 mypy 진단 13건을 해결했다. product 모델의 기존 포맷 차이를
적용하고 공용 품질 범위를 apps/api/app 디렉터리 하나로 통합했다. 현재 앱 전체가
직접 Ruff format/check·mypy 검사 대상이며 기존 시그니처 기준선도 0개다.

- 신규 db/json_types.py는 도메인/ORM 의존성이 없는 재귀 JsonValue/JsonObject 별칭이다.
  nullable scalar·중첩 array/object·확장 키를 유지하며 실행 시 검증/변환을 하지 않는다.
  도메인 공개 types의 구조적으로 같은 기존 별칭을 일괄 교체하거나 모델에서 도메인
  types를 역참조하지 않았다. 새 계층·serializer·JSON wrapper는 없다.
- product replacement_policy·document·선택적 publication_release와 chat의 선택적
  answer_metadata, moderation evidence_snapshot/signals·attachment/recommendation 배열·
  감사 metadata, model capabilities와 선택적 memory embedding_settings를 연결했다.
  기존 domain mapper/저장 입력과 전체 타입 검사로 호환을 확인했다. 기존 deepcopy·
  legacy/확장 키 처리·nullable·오류 동작에 실행 변경은 없다.
- 로어북 metadata는 공개 입력의 dict[str, object]를 유지했다. 통계 JSON은 통화별
  RevenueBucket TypedDict로 sales/refunds/net의 정확한 문자열 금액과 sale_count/
  refund_count 정수를 명시했다. 기존 RevenueValues/Info와 구조적으로 연결되며,
  통화 간 합산 금지·Decimal 계산·날짜/버전별 집계·저장 형식은 같다.
- SQLAlchemy의 기존 JSON/JSONB 컬럼과 nullable/default/FK/CHECK/index는 유지했다.
  타입만 바뀌어도 nullable 추론에 영향을 줄 수 있어 변경 전에 PostgreSQL dialect의
  CreateTable/CreateIndex를 캡처하고 변경 후 대조했다. 73개 테이블의 정의·인덱스가
  전부 동일했다. 실제 DB에 migration·초기화·조회·쓰기를 실행하지 않았다.

Any·ignore·cast·기준선 예외는 추가하지 않았다. 앱 전체 직접 mypy의 13진단은 0건이
됐고 숨겨진 의존 파일에만 검사를 의존하지 않는다. 기존 follow_imports=silent 등
mypy 설정은 유지한다. 현재 설정에서 진단이 없다는 의미이며 기존 외부/동적 경계의
Any까지 모두 제거했다거나 tests/alembic/tools 전체를 엄격 편입했다는 의미는 아니다.

| 검증 | 결과 |
|---|---|
| 앱 전체 Ruff format/check | 388파일 통과 |
| 앱 전체 직접 mypy | 367 source files 통과; 0진단 |
| 필수 품질 검사 | 앱 전체 Ruff/mypy·기준선 0개·계약/검사기 13 passed; 종료 코드 0 |
| 관련 JSON/mapper·studio·통계·moderation·memory/lorebook·LLM/답변 회귀 13파일 | 168 passed, 22 skipped |
| 전체 API 회귀 — 현재 작업 트리 | 1052 passed, 1 failed, 288 skipped |
| 변경 전후 PostgreSQL 테이블/인덱스 DDL | 73테이블 모두 동일 |
| 변경 범위 git diff --check | 통과 |

이번 변경은 모델 타입 주석·타입 별칭·포맷이므로 이를 따라 쓰는 테스트를 새로
추가하지 않았다. 기존 회귀의 중첩 JSON/복사 격리·nullable/legacy·정밀 매출·증거/
capabilities/답변 metadata 경계와 compiled DDL 대조를 사용했다. TEST_DATABASE_URL/
TEST_AUTH_DATABASE_URL을 제거했으며 실제 PostgreSQL 저장/복원·잠금·동시성과 외부
공급자 통신은 미검증이다. skipped를 통과로 계산하지 않았다.

전체 실패 1건은 기존 U06의 test_edit_after_first_publication_does_not_change_product_visibility다.
현재 테스트/문서는 변경 문서의 재발행 거절을 기대하고 구현은 갱신을 허용하는 계약
불일치다. 이번에는 product 업무 구현·기대·skip/xfail을 수정하지 않았다. 품질/회귀는
Windows asyncio 로컬 소켓과 임시 파일을 허용하는 환경에서 실행했다.

**다음 범위:** 타입 정리 단계의 현재 목표는 완료했다. 기능 감사로 전환해 U06의
재발행 허용/거절·공개 상태·로어북 메타데이터 동기화 계약을 문서/테스트/구현과
대조하고 결정된 계약에 맞춰 수정·회귀 검증한다. GPT-6.1 Sol, 추론 High를 권장한다.

## 기능 감사 수정 1차: U06 재발행 계약·로어북 동기화 (2026-10-29)

사용자가 **후속 버전 발행 허용**을 선택했다. 발행 후 초안 편집을 허용하고 초안 저장은
현재 상품 프로필·공개 범위·승인 상태·태그에 영향을 주지 않으며 명시적 발행에서 반영하는
계약으로 확정했다. 첫 발행만 허용하던 과거 문서/테스트 기대를 이 결정에 맞춰 갱신했다.
실패를 숨기기 위한 skip/xfail이나 반환 성공값은 추가하지 않았다.

- use_cases/studio_publication.py의 기존 book_id 분기를 보완했다. 공개 소유 조회의
  lock=True로 로어북 값을 읽고 update_lorebook으로 제목·worldRules 설명을 갱신한다.
  기존 visibility를 전달하고 status는 변경하지 않는다. 소유 검증/잠금을 유지하면서
  기존 공개 입력을 조합하므로 새 repository 접근·ORM 전달·도메인 역의존성은 없다.
- 로어 항목 태그의 기존 입력 순서로 replace_public_tags를 호출한다. 항목/태그를 전부
  제거한 경우에도 빈 tuple을 전달해 이전 연결이 남지 않게 한다. 사전/중복/비활성 태그
  처리는 기존 하위 서비스가 맡는다. 현재 태그를 과거 snapshot에 복사하지 않는다.
- 기존 character/book/entry ID와 과거 snapshot은 보존하고 동일 상위 트랜잭션에서
  구성·상품 프로필·settings·새 release·영수증을 저장한다. 새 조회는 기존 부모 로어북
  1개에 대한 소유 조회/잠금이며, update 서비스의 기존 잠금과 같은 세션에서 수행한다.
  별도 commit·재시도·migration·새 컬럼은 없다. U04 잠금 순서 감사까지 해결한 것은 아니다.
- revision 영수증 재시도는 제목/태그를 다시 쓰지 않는다. 더 최신 초안이 저장된 뒤에도
  이전 revision의 동일 요청은 영수증을 반환하고 파라미터가 다른 요청은 409다. 기존
  legacy receipt 복구·이전 snapshot 읽기/선택·승인 정책은 바꾸지 않았다.
- use_cases/product/lorebook ARCHITECTURE와 서버 매핑 문서·web README의 오래된
  후속 발행 미지원 설명을 수정했다. 최초 감사 원문은 남기고 U06 후속 상태를 덧붙였다.

test_studio_draft_guard의 기존 거절 기대는 private/public/unlisted 3가지의 허용/보존
검증으로 교체했다. title/introduction/opening/tags가 바뀐 초안은 revision을 갱신하지만
현재 상품 프로필·visibility·approval·latest_snapshot_id·공개 태그는 그대로임을 확인한다.

신규 test_studio_republication_contracts의 4건은 후속 발행의 부모 제목/설명/태그 갱신과
기존 visibility/ID/과거 영수증 보존, 규칙/태그 제거, 태그 실패 시 rollback·발행/영수증
차단, 응답 유실 뒤 최신 revision과 무관한 재시도/다른 요청 거절을 확인한다. 실제
AsyncSession transaction event와 공개 서비스 대역을 사용한다. SQL 영속 rollback이나
실제 PG 잠금 경쟁 검증을 대신하지 않는다. 과거 snapshot 보존은 기존 발행 회귀도 실행했다.

| 검증 | 결과 |
|---|---|
| 초안·후속/최초 발행·studio JSON/HTTP·snapshot 관련 6파일 | 46 passed |
| 수정 테스트 2파일 직접 Ruff format/check·mypy | 통과 |
| 필수 앱 전체 품질 검사 | Ruff 388파일·mypy 367소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1059 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했으며 실제 PostgreSQL·외부 저장소·
Google/SMTP/LLM 호출은 수행하지 않았다. 브라우저 발행 통합·PG 교차 잠금·rollback
영속성은 미검증이다. skipped를 통과로 계산하지 않았다. Windows asyncio 로컬 소켓과
임시 파일을 허용하는 환경에서 검증했다. Any·ignore·cast·기준선 예외는 추가하지 않았다.

**다음 범위:** U07 스튜디오 중첩 JSON 검증을 정리한다. 미완성 초안 저장과 발행 필수
조건을 구분하고 asset id/mediaId/usage 등 잘못된 형식·참조를 쓰기 전에 명시적 422로
거절한다. 새로운 재발행 계약과 revision/영수증은 유지한다. GPT-6.1 Sol, 추론 High를
권장한다.

## 기능 감사 수정 2차: U07 스튜디오 중첩 JSON 검증 (2026-10-29)

product/service/studio_validation.py를 공유 공개 검증 서비스로 추가했다. 기존 product
소유의 편집 문서 구조를 검사하며 저장·준비·발행 사이에 같은 형식 계약을 적용한다.
상위 use case를 하위 service에서 가져오거나 새 실행 계층/범용 검증 엔진을 만들지 않았다.

- 배열과 구성 객체, 알려진 text/list/bool/int 필드, 빈/중복 로컬 ID와 비어 있지 않은
  default scene/scene character 참조를 검사한다. character별 asset ID는 중복을 거절하고
  usage는 portrait/expression/scene, 명시된 mediaId는 UUID 문자열이어야 한다.
  usage 생략의 기존 expression 기본값은 유지한다. UUID 값은 변환해 재저장하지 않는다.
- 누락된 선택 필드와 빈 캐릭터/로어 본문, 기본 장면 미선택, 업로드 전 이미지는 초안에
  보존한다. 실제 저장의 기존 제목·프로필/버전·2 MiB 검사는 유지한다. 확장 키를 제거하거나
  입력 dict를 수정하지 않는다. 타입이 잘못된 값/존재하지 않는 비빈 로컬 참조는 422다.
- product의 직접 save_studio_draft와 상위 save_studio가 구조를 확인한다. 상위 검증은
  legacy 구성 adoption 쓰기보다 먼저 실행하며 하위 직접 호출도 같은 검증을 거친다.
  prepare_components는 저장 문서 및 모든 대상의 name/persona를 먼저 확인한 뒤 생성한다.
- 발행 필수 조건(인물·장면·유효한 기본 장면·본문·업로드 완료)은 별도로 유지한다.
  lore_entry_value/scene_entry_value의 순수 변환/옵션 검증을 기존 로어북 생성 뒤에서
  첫 character 쓰기 앞으로 이동해 유효하지 않은 옵션 때문에 일부 쓰기부터 시작하지 않는다.
- unsaved diagnostics의 category/priority/placement는 문자열인지 먼저 확인한다.
  list/dict가 사전 lookup에 들어가 TypeError가 되는 경로를 닫았다. 광범위한 예외 catch나
  기본값으로 오류를 숨기지 않으며 ValueError를 기존 HTTP 경계가 422로 번역한다.
- 정상 형식 media UUID의 실제 소유권·캐릭터 연결·ready 상태/미존재는 기존 character
  서비스가 계속 검사한다. 해당 인가/존재 오류를 무조건 422로 바꾸지 않았다. 서버가
  기록한 _studio 매핑/영수증 손상 전체의 복구 정책은 이번 범위가 아니다.
- U06의 후속 발행 허용·초안 비노출·기존 구성 ID/과거 snapshot·revision/digest/영수증을
  유지한다. 이미 처리한 요청의 영수증 반환은 최신 초안 구조 검증보다 먼저 수행한다.

신규 test_studio_validation_contracts의 55건은 실제 FastAPI/ASGITransport·DTO와 공개
서비스 대역을 사용한다. 중첩 입력 20형태×저장/발행의 40건은 422와 도메인 쓰기 없음,
미완성 초안/확장 원문 보존, 로어 옵션 preflight 3건, 모든 업로드 대상 선검증,
diagnostics 2건, 구성 ID 중복 3건, 직접 저장 서비스 선검증, 업로드 전/정상 이미지와
기본 usage·소유자 Command, 더 최신 손상 문서가 있어도 기존 영수증 재시도를 확인한다.
실제 DB 영속성/이미지 소유권 조회와 브라우저 실행 검증을 대체하지 않는다.

| 검증 | 결과 |
|---|---|
| 신규 테스트 직접 Ruff format/check·mypy | 통과 |
| 신규/기존 studio 저장·진단·업로드 준비·후속 발행 관련 6파일 | 94 passed (신규 55건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 389파일·mypy 368소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1114 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했으며 실제 PostgreSQL·외부 저장소·
Google/SMTP/LLM 요청은 수행하지 않았다. 실제 PG 잠금/rollback 영속성과 브라우저 통합은
미검증이다. skipped를 통과로 계산하지 않았다. Windows asyncio 로컬 소켓과 임시 파일을
허용하는 환경에서 검증했다. 새 Any·ignore·cast·기준선 예외는 추가하지 않았다.

**다음 범위:** U08 미디어 공급자 취소 우선순위와 S3 get_object 취소 후 늦게 반환된
Body 자원 회수를 수정한다. 공급자 작업 종료까지 잠금을 유지하고 결과/예외를 회수한
뒤 취소를 복원한다. 실제 S3 요청 없이 지연/실패/반복 취소 대역으로 검증한다.
GPT-6.1 Sol, 추론 xHigh를 권장한다.

## 기능 감사 수정 3차: U08 취소 우선순위·S3 늦은 읽기 자원 회수 (2026-10-29)

character workflow의 공급자 대기에서 ValueError가 CancelledError를 덮어쓰는 경로와
S3 get_object 대기 중 취소되면 반환 Body의 소유자가 없어지는 경로를 수정했다.
두 모듈의 기존 책임·트랜잭션/저장소 수명 경계 안에서 처리하고 공통 실행 계층을
추가하지 않았다. SDK 작업을 조기에 버리거나 잠금을 먼저 푸는 변경도 하지 않았다.

- _settle_storage는 shield에서 일반 공급자 예외가 발생해도 task.result를 거친다.
  취소를 받은 경우 공급자 성공/실패를 회수한 뒤 CancelledError를 전달하며 작업이
  종료되기 전에는 트랜잭션을 벗어나지 않는다. 취소가 없으면 원래 예외/값을 전달한다.
- S3 read_asset는 기존 get_object·메타데이터 해석·reader 생성을 _open_asset로 옮기고
  그 태스크를 소유한다. 취소 후에도 acquisition 결과를 기다려 reader가 생기면 aclose
  태스크를 소유해 기다린 뒤 첫 취소 객체를 전달한다. 반복 취소가 get/close를 버리지 않는다.
- 획득 실패와 손상 메타데이터/close 실패도 회수하며 이미 받은 취소가 최종 결과다.
  close 실패를 재시도하거나 성공으로 단정하지 않는다. 취소는 SDK 작업과 cleanup이
  끝날 때까지 지연된다. 중단할 수 없는 스레드에 새 강제 종료·timeout을 추가하지 않았다.
- 정상 반환의 reader 소유권/idempotent close와 주입 client 소유권, 기존 오류 kind/cause,
  SDK timeout/retry 설정·업로드/삭제 멱등성·키/메타데이터 변환을 유지했다. 정상 reader
  반환 뒤의 모든 read/close 취소나 로컬 adapter 수명을 일괄 변경한 것은 아니다.
- 업로드 예약/deleting 선행 commit, 공급자 실행 중 잠금, 취소 후 ready/deleted 확정
  차단과 재시도 가능한 DB 상태는 기존 정책이다. 새로운 DB 쓰기·migration·외부 요청·
  Any/ignore/cast/기준선 예외는 추가하지 않았다.

신규 test_media_cancellation_contracts의 15건은 다음을 확인한다.

- upload/cleanup×공급자 성공/실패×1/3회 취소의 8조합에서 연결 없는 실제 AsyncSession
  event의 선행 commit→공급자 종료→rollback과 완료 확정 없음·caller 입력 stream 수명.
- 취소가 없을 때 공급자의 원래 ValueError가 같은 객체로 전파됨.
- 손상 metadata 유무×close 실패 유무 4조합에서 실제 get/close 테스트 스레드를 gate로
  지연시켜 get 대기/close 중 반복 취소·Body close 1회·첫 취소 메시지 보존을 확인함.
  정상 close 때만 closed를 보장하고 close 실패 때는 시도 종료/실패 회수를 확인함.
- 취소 뒤 get 자체 실패도 소비하고 Body close가 불필요함, 정상 reader 반환·읽기와
  기존 두 번 aclose 호출의 단일 실제 close를 확인함.

| 검증 | 결과 |
|---|---|
| 수정 소스 2파일·신규 테스트 직접 Ruff format/check·mypy | 통과 |
| 신규 취소·asset storage·미디어 전송/HTTP·character media 관련 7파일 | 60 passed, 30 skipped (신규 15건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 389파일·mypy 368소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1129 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했다. SQL event는 실제 PostgreSQL 행
잠금·rollback 영속성/경합을 증명하지 않고, 테스트 스레드는 실제 S3/TLS·운영 ASGI의
연결 종료/프로세스 강제 종료를 증명하지 않는다. 실제 DB/외부 공급자는 호출하지
않았으며 skipped를 통과로 계산하지 않았다. Windows asyncio 로컬 소켓과 임시 파일을
허용하는 환경에서 검증했다.

**다음 범위:** U09 정상 모델 선택 경로의 불필요한 스냅샷 배타 잠금을 줄인다. 일반 읽기와
모델 교체 쓰기를 분리하고, 교체가 필요할 때 잠금 아래 상태를 재확인해 버전 종료/대체
정책을 보존한다. GPT-6.1 Sol, 추론 xHigh를 권장한다.


## 기능 감사 수정 4차: U09 정상 모델의 스냅샷 잠금 제거 (2026-10-29)

정상 실행까지 공유 상품 스냅샷을 FOR UPDATE로 읽던 경로를 분리했다.

- resolve_execution은 일반 조회와 교체 검토의 두 단계로 판단한다. 원본 모델/공급자가
  활성이고 종료 전이며 공지 시작 전이면 lock=False 조회만으로 원본 실행 설정을
  반환한다. 후보·대체 이력 읽기/쓰기는 수행하지 않는다.
- 교체 검토가 필요할 때만 같은 트랜잭션에서 lock=True로 스냅샷을 재조회한다.
  두 단계 모두 product의 공개 ensure_snapshot_available을 사용하여 만료를 확인하고,
  잠금 대기 중 만료됐으면 기존 만료 오류로 중단한다. product 저장소/HTTP 계약은 같다.
- GetModelCommand/GetProviderCommand에 기본 False인 refresh를 추가했다. 후보 조회는
  선택적 ListCandidateModelsCommand(refresh=True)를 받으며 기존 인자 없는 호출도
  지원한다. 저장소의 populate_existing으로 세션 캐시를 갱신하고 판단은 Info로 한다.
- 모델 선택의 첫 조회와 잠금 후 조회, 후보 및 최종 공급자는 최신 DB 조회를 요청한다.
  단순히 같은 session.get을 두 번 호출해 이전 Entity가 재사용되는 문제를 피했다.
- 명시적 now가 없으면 각 단계의 읽기 뒤 현재 UTC를 평가한다. 잠금을 기다리다 종료/
  전환 시각을 넘은 경우 이전 시각으로 원본을 계속 선택하지 않는다. 명시적 now는
  두 단계 모두 동일하다. 공지가 철회되면 두 번째 판단에서도 원본으로 돌아갈 수 있다.
- 후보 순위·effort·대체 계획 시각·일시 원본 사용/중단 정책 및 snapshot/from/to 이력
  존재 확인/삽입은 유지한다. 교체 이력 접근은 잠금 획득 뒤이며 중첩 트랜잭션의
  commit/rollback 소유자는 같다. 새 migration·외부 요청·Any/ignore/cast/기준선 예외는 없다.

기존 두 계약 테스트 파일에 회귀 13건을 추가했다. 정상/미래 공지의 스냅샷 비잠금,
공지 철회·정책 변경·스냅샷/모델/공급자 미존재의 재검사, 잠금 대기 중 버전 만료와
모델 종료·전환, 명시적 now 보존을 검증한다. SQLite에서 ORM을 직접 거치지 않는
갱신으로 캐시와 DB 값을 다르게 만든 후, 모델/공급자/후보가 실제 갱신되는지도 확인했다.
기존 깊은 복사 테스트의 중첩 JSON 접근에는 isinstance 좁히기를 추가해 직접 mypy도
통과시켰다. 테스트 fixture의 여러 mock은 역할별 키워드로 연결한다.

| 검증 | 결과 |
|---|---|
| LLM 전체 및 수정 테스트 Ruff format/check·직접 mypy | 통과; mypy 27소스 |
| 모델 대체/LLM 저장소/상품 수명/프롬프트 workflow/답변 회귀 6파일 | 49 passed, 19 skipped (신규 13건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 389파일·mypy 368소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1142 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했고 실제 DB/외부 공급자는 호출하지
않았다. skipped는 통과로 계산하지 않았다. Windows 임시 파일 권한 때문에 첫 공용
검사의 테스트가 실행되지 않아 허용 환경에서 다시 전체 공용 검사를 통과시켰다.
신규 테스트 작성 중 드러난 fixture 연결과 Command 입력 계약도 바로잡았다.
SQLite/순차 mock은 PostgreSQL 실제 FOR UPDATE 대기·격리·동시 삽입/유일 제약을
증명하지 않는다. 정상 경로의 경합 감소량/운영 처리량도 측정하지 않았다. 교체 경로는
재조회가 추가되며, 일반 조회 이후의 모든 관리자 변경과 실행을 원자적으로 묶는
보장은 추가하지 않는다. LLM ARCHITECTURE와 원본 감사 U09 상태를 갱신했다.

**다음 범위:** U10 일반 access 인증과 refresh/폐기 잠금을 구분하고, 비밀번호 검증을
잠금 밖에서 수행한 뒤 최신 해시·계정 상태를 재확인하는 방안을 적용한다. 비밀번호
재설정/비활성화와 로그인 경합에서 낡은 인증으로 새 세션이 생기지 않는 계약이 핵심이다.
GPT-6.1 Sol, 추론 xHigh를 권장한다.


## 기능 감사 수정 5차: U10 access 비잠금·비밀번호 검증 구간 분리 (2026-10-29)

일반 인증이 사용자/세션 행을 배타적으로 잠그고, 로그인에서 Argon2 검증·재해시 중에도
사용자 잠금을 유지하던 경로를 분리했다. 기존 서비스/저장소/mapper 구조를 유지한다.

- access 인증은 users/auth_sessions를 한 SQL로 JOIN하고 claim의 사용자 ID·세션 ID와
  소유 관계를 제한한다. mapper가 내부 AuthenticatedSessionRow를 두 Info로 옮기고
  서비스가 기존 활성/인증·소유자·폐기·절대 만료 조건을 판단한다. FOR UPDATE와 쓰기는
  없으며 여러 시점의 SELECT 두 개를 별도로 조합하지 않는다.
- 로그인은 lock=False 이메일 조회 후 읽기 트랜잭션과 세션을 종료한다. 이후 기존
  to_thread에서 비밀번호 검증(미존재/Google-only의 더미 포함)과 필요한 재해시를 한다.
  비밀번호 작업 중 DB 연결/세션·사용자 잠금을 보유하지 않는다.
- 최종 쓰기 트랜잭션에서 사용자 행을 잠그고 최신 계정 상태·인증·이메일·검증에 사용한
  해시의 정확한 일치를 확인한다. 일치할 때만 재해시 갱신과 세션 저장을 같은 범위에서
  수행한다. 조회한 Entity를 서비스가 읽거나 새 실행 계층/범용 우회 옵션을 추가하지 않았다.
- 재설정 commit이 먼저면 낡은 해시로 로그인/덮어쓰기를 하지 않는다. 로그인 발급이
  먼저면 같은 사용자 잠금을 기다린 재설정이 새 세션까지 폐기한다. 세션 저장 실패는
  재해시 갱신과 함께 rollback한다. 서명·쿠키/CSRF·암호 비용·요청 제한은 그대로다.
- get_user_by_email은 기존 호출의 lock=True를 유지하고 로그인만 lock=False를 명시한다.
  get_locked_user/get_session 및 access 조회에 populate_existing=True를 적용해 캐시된
  상태로 판단하지 않는다. refresh 회전·재사용 폐기 commit 후 오류·로그아웃/reset의
  사용자→세션/토큰 잠금과 절대 만료 검증을 유지한다.
- 동시 정상 로그인에서 다른 요청이 같은 비밀번호를 재해시해도 저장 해시가 달라지면
  현재 요청은 invalid_credentials로 거절될 수 있다. 최신 해시로 새 로그인을 요청해야
  한다. 내부 자동 재시도·유예를 추가하지 않았다. 인증 시점 이후의 업무를 소급 취소하는
  보장이나 격리 수준/처리량 보장은 추가하지 않았다.

신규 test_identity_locking_contracts의 21건은 다음을 검증한다.

- 정상/재해시 성공에서 검증/해시 작업 중 세션 없음, 사용자 잠금 후 세션 발급.
- 실제 비밀번호 작업 스레드를 gate로 중단하고 reset을 실행한 두 순서(검증 중/재해시 중)에서
  reset commit 후 낡은 로그인 실패·새 해시 미덮어쓰기·새 세션 없음.
- asyncio 잠금으로 DB 잠금 수명을 모델링한 반대 순서에서 로그인 commit 후 기다리던
  reset이 발급된 세션 ID까지 폐기함. 모델이 실제 PostgreSQL 동작을 증명하지는 않는다.
- 최종 재검사 시 미존재/정지/미인증/이메일 변경/비밀번호 제거/다른 재해시의 거절 6조합,
  초기 인증 실패 6조합의 기존 검증/더미 경로와 잠금/쓰기 없음.
- 세션 저장 실패 시 같은 트랜잭션 rollback, access의 읽기 전용 경계와 logout-all의 잠금,
  PostgreSQL SQL 컴파일의 JOIN/ID/잠금/캐시 옵션, SQLite에서 오래된 Entity의 실제 갱신.

기존 test_identity_auth_contracts의 access 대역은 새 읽기 경계로 연결했고 기존 6개
거절 조건 검증은 유지했다. 새 Any/ignore/cast/기준선 예외·migration은 없다.

| 검증 | 결과 |
|---|---|
| identity 전체·수정/신규 테스트 Ruff format/check·직접 mypy | 통과; mypy 22소스 |
| 인증/저장소/암호/쿠키/HTTP/Google/DB opt-in 회귀 8파일 | 172 passed, 17 skipped (신규 21건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 389파일·mypy 368소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1163 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했고 실제 PostgreSQL·SMTP·Google/외부
공급자는 호출하지 않았다. skipped를 통과로 계산하지 않았다. SQLite/SQL 컴파일·스레드/
asyncio 잠금 대역은 실제 PostgreSQL 경합·격리·폐기/rollback 영속성을 증명하지 않는다.
테스트 Argon2 비용은 작게 설정했으며 운영 보안 파라미터/성능을 바꾸지 않았다.
Identity ARCHITECTURE·인증 연동 문서·원본 감사 U10 상태를 갱신했다.

**다음 범위:** U11 대화 목록의 전체 수집/정렬을 DB 페이지 조회로 줄인다. 소유권 스코프,
빈 대화의 생성 시각 fallback, 활동 시각/ID 정렬·커서·총 개수 계약을 확인하고 제한적인
읽기 projection의 모듈 경계를 먼저 정리한다. GPT-6.1 Sol, 추론 xHigh를 권장한다.


## 기능 감사 수정 6차: U11 최근 대화 DB 페이지 조회 (2026-10-29)

최근 대화 한 페이지를 위해 모든 소유 metadata를 100개씩 순회하고 메시지 활동을
수집한 뒤 Python에서 정렬/필터하던 경로를 DB 페이지로 바꿨다.

- 규칙 module-architecture-and-naming.md의 C.2에 해당 목록만을 위한 읽기 projection
  예외를 명시했다. chat.repository.list_recent_conversations가 conversations의 지정한
  5컬럼과 자기 messages를 읽는다. 소유권은 커서/정렬/LIMIT 전에 user_id로 제한하고
  타 모듈 repository/mapper 호출·쓰기·잠금·데이터 소유권 변경은 추가하지 않았다.
- 마지막 생존 메시지는 created_at/position DESC로 선택한다. 메시지가 없을 때만 대화
  생성 시각을 쓰고, 활동 시각/대화 UUID DESC·엄격한 이전 커서·limit+1을 SQL에 적용한다.
  선택된 페이지의 미리보기도 같은 SQL에서 읽는다. 빈 문자열·nullable title·대화 생성보다
  오래된 메시지 시각을 원래대로 유지하며 메시지 삭제 후 현재 생존 내용으로 재계산한다.
- chat.service/views가 공개 Command의 limit·커서 쌍/시간대를 검증한다. COUNT는
  conversation 공개 service로 같은 소유 범위를 정확히 계산하고 mapper가 raw 6컬럼
  Row를 공개 View로 옮긴다. 전체 대화가 서비스 메모리로 넘어오지 않는다.
- 기존 use_cases의 함수/Command/두 View 이름과 HTTP DTO/필드는 유지했다. 내부 새
  Command는 cursor_activity_at을 사용하고 HTTP/Python의 cursor_created_at 이름을
  어댑터에서 연결한다. last_activity_at=None/total=0 기본값도 유지한다. 전체 순회·정렬과
  기존 cast 2개는 제거했다. 새 Any/ignore/cast/기준선 예외·migration은 없다.
- SQL은 COUNT+페이지 2회, 목록 반환은 최대 limit+1이다. DB 내부에서는 소유 범위의
  활동 평가/정렬과 정확한 COUNT 비용이 남는다. 전체 작업이 O(limit)라고 주장하지 않는다.
  COUNT/페이지의 READ COMMITTED 시점 차이와 여러 요청 사이 새 활동이 기존 커서 앞으로
  이동하는 live 조회 정책도 유지한다. 고정 snapshot이나 새 통계 컬럼은 추가하지 않았다.

기존 test_read_composition_contracts의 6건을 실제 SQL 검증으로 바꾸고 11건을 추가해
17건으로 보강했다. 최소 SQLite 테이블에서 전체 요청 경로의 SELECT/COUNT를 실행한다.
SQLite가 반환에서 잃는 UTC tzinfo만 테스트 어댑터에서 복구하며 정렬·소유권·필터·LIMIT을
대역이 처리하지 않는다. 원래 별도 공개 조회 두 개의 호출 배치를 단정하던 검증은
행동·결과와 DB 반환량/호출 수 검증으로 교체했다.

검증 대상은 소유권(더 최근인 타인 메시지 제외), 활동/UUID 동률·미리보기, 마지막 메시지의
timestamp 우선/position 동률, 빈 content·삭제 후 생존 메시지/빈 방 fallback, 생성보다
오래된 메시지, 빈 소유 범위/커서 끝 이후 총건수, 삭제된 커서 행, 요청 사이 활동 이동,
기존 View/Command·HTTP DTO·잘못된 커서다. 소유 방 353개×limit 1/7/100에서 SQL 2회와
최대 limit+1 반환을 확인했고 PostgreSQL SQL 컴파일로 조건/정렬/LIMIT/비잠금도 확인했다.

| 검증 | 결과 |
|---|---|
| 수정 소스·chat 전체·목록 테스트 Ruff format/check·직접 mypy | 통과; mypy 34소스 |
| 목록/대화 query/chat 메시지/repository workflow 회귀 4파일 | 61 passed, 3 skipped (목록 계약 17건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 390파일·mypy 369소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1174 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거하고 실제 PostgreSQL/외부 공급자를
호출하지 않았다. skipped는 통과로 계산하지 않았다. 실제 PostgreSQL 실행 계획·인덱스
선택·운영 처리량/지연·동시 갱신의 격리 검증은 남아 있다. 기존 messages의
(conversation_id, created_at) 인덱스를 유지했다. chat/conversation/use_cases ARCHITECTURE와
원본 감사 U11 상태를 갱신했으며 공용 검사 예외/기준선을 늘리지 않았다.

**다음 범위:** U12 웹의 불필요한 전체 수집을 줄인다. 계정 개요의 사용하지 않는 전체
상품 조회부터 제거하고, 대화 메시지는 정상 append의 ID 기반 반영과 수정/삭제·revision
불일치 시 재동기화를 구분한다. 복구·재시도·중복 제거 계약을 보존한다.
GPT-6.1 Sol, 추론 xHigh를 권장한다.


## 기능 감사 수정 7차: U12 웹 증분 메시지 조회·계정 개요 정리 (2026-10-29)

계정 개요의 사용하지 않는 전체 상품 수집과 정상 메시지 추가마다 전체 이력을 다시 읽는
동작을 줄였다. Next.js 16.3.3의 설치된 client/fetch 문서를 확인하고 기존 client 화면과
service/repository/mapper 구조를 유지했다. 패키지/프레임워크를 교체하지 않았다.

- readAccountOverview는 getMe 뒤 잔액·최근 대화 한 페이지·정확한 COUNT만 독립적으로
  읽는다. 전체 products 조회와 useAccount의 해당 실데이터 state를 제거했다. 실제
  작품 화면의 별도 페이지 hook, 부분 실패 처리·시연 상품과 기존 목록 helper는 유지한다.
- 메시지 페이지 응답에 선택적 history_revision/sync_cursor만 추가했다. 기존 필드·커서
  형식·최대 크기·인가/오류는 그대로다. 마지막 페이지에도 동기화 위치를 반환하고 빈 증분
  페이지는 입력 위치를 보존한다. lookahead 행을 사용하지 않으므로 누락을 만들지 않는다.
- MessagePageInfo의 기본 None으로 기존 생성/대역을 지원한다. query가 기존 공개 소유권
  Info의 원문 revision을 mapper에 전달하며 별도 SQL·잠금·쓰기·migration은 없다.
  OpenAPI 검사는 추가한 두 선택 필드만 예외로 비교하고 기존 구조는 계속 고정한다.
- 새 chat-history 모듈은 페이지를 ID로 병합하고 위치순으로 정렬한다. 최초 진입은 전체
  이력을 읽고, 정상 저장은 반환 메시지를 즉시 반영하며 답변 완료/포커스 복귀는 기존
  sync_cursor 이후만 읽는다. 입력 저장 직후 전체 GET은 제거했다. 저장 응답으로 커서를
  앞당기지 않아 다른 탭에서 그 사이 추가한 메시지를 건너뛰지 않는다.
- 원문 revision 불일치나 같은 ID의 내용/revision 충돌은 기존 이력을 버리고 전체를 다시
  읽는다. 여러 페이지 사이 변경도 한 번만 전체 재시도하고 반복되면 오류로 끝낸다.
  메타데이터 없는 이전 서버는 기존 전체 읽기로 복구한다. 반복 커서 차단은 유지한다.
- 부분 읽기 실패·취소에는 기존 캐시/체크포인트를 유지한다. 버전 번호로 오래된 읽기의
  덮어쓰기를 막고 방/계정 전환·중복 읽기/저장 시 이전 조회를 취소한다. 늦은 성공/오류도
  버리며 이력 캐시는 해당 방/계정 메모리에만 둔다. auth 변경 이벤트로 방을 다시 로드한다.
- 답변 폴링 횟수/간격·request_key·실패 후 새 answerKey·수동 로어·입력 expected_revision·
  401/402/429/CSRF/불확실한 결과·사용자별 pending 복구는 유지했다. 확정 4xx 충돌은
  원래처럼 전체 재동기화한다. 대기 중단/페이지 이동은 클라이언트 기다림만 중단하며
  서버 생성 작업을 취소하거나 저장된 요청을 제거한다는 뜻이 아니다.

신규 백엔드 8건은 최초/증분×빈/마지막/lookahead 6조합과 schema 왕복·소유권 거절·
nullable 기본값을 확인한다. 기존 ASGI/DTO 회귀도 두 선택 필드를 검증한다.
프런트 18건을 추가하고 계정 부분 실패 테스트를 강화했다. 실제 request/JSON 경계의
fetch 대역으로 205개 이력 3페이지 후 입력 ID 반영은 추가 GET 없이, 다음 답변 동기화는
기존 205번 이후 한 번의 GET으로 206~208번만 병합함을 확인한다. 더미 커서 루프,
수정/되돌리기·동시 원문 변경의 제한 재시도, 이전 서버, 부분 읽기 실패, 옛 save 재전송,
겹친 읽기, 방/계정 전환의 늦은 응답/오류, 취소 signal과 캐시 보존도 확인했다.
UUID 경로의 대소문자·축약/brace/URN 표기와 API의 표준 UUID 문자열도 같은 방으로
비교해 기존 경로 호환을 유지했다.

| 검증 | 결과 |
|---|---|
| 웹 전체 Node 테스트 5파일 | 50 passed, 0 failed (신규 18건 포함) |
| 웹 tsc --noEmit 및 격리된 Next.js production build | 통과 |
| chat 전체·신규/수정 테스트 Ruff format/check·직접 mypy | 통과; mypy 34소스 |
| 메시지 sync/query mapper/router/CRUD/HTTP 회귀 5파일 | 57 passed, 13 skipped (신규 8건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 390파일·mypy 369소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1182 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거하고 실제 PostgreSQL·외부 공급자를
호출하지 않았다. skipped는 통과로 계산하지 않았다. Node fetch 대역/ASGI·빌드는 실제
브라우저 렌더링/복수 탭·운영 proxy·PostgreSQL 격리를 증명하지 않는다. 초기 조회와
변경 재동기화의 전체 이력/DOM·Map 메모리 비용은 남으며 최신 페이지만 시작하는 UI/
가상화·실시간 push는 추가하지 않았다. 원문 revision과 메시지 SQL 사이/읽기 이후의
동시 수정은 다음 동기화에서 관측될 수 있다. 고정 snapshot을 새로 보장하지 않는다.

격리 빌드의 생성 폴더와 이번 빌드가 자동으로 추가한 Next 타입 설정만 정리했고 기존
개발 빌드/사용자 소스 변경은 유지했다. chat ARCHITECTURE·웹 README·원본 감사 U12
상태를 갱신했다. 새 Any/ignore/cast/타입 기준선 예외는 추가하지 않았다.

**다음 범위:** U13 생성 완료 계층의 반복 조회를 줄인다. 같은 모듈 내부에서 이미 잠근
상태와 상태 전이 결과를 재사용하되 독립 공개 서비스의 진입 검증·완료/크레딧/메모리
예약 원자성·재전송 멱등성을 보존한다. SQL 호출 수와 회귀 계약을 함께 검증한다.
GPT-6.1 Sol, 추론 xHigh를 권장한다.


## 기능 감사 수정 8차: U13 생성 완료 상태·잠금 재사용 (2026-10-29)

정상 답변 완료가 _finalize→기억 예약 조립→public finish_generation으로 내려가면서 같은
생성 상태와 대화 잠금을 반복 조회하던 경로를 정리했다. 기존 계층·테이블 소유권과
외부 API/공개 Python 함수의 입력/반환은 유지한다.

- command/generation의 내부 _locked_generation이 사용자 범위 생성의 대화 ID를 조회하고
  conversation→generation 순서로 잠가 최신 Info를 만든다. 내부 scope는 세션·transaction·
  대화/생성 Info를 보관하고 유효 수명 밖의 사용을 거절한다. workflow는 repository를
  직접 호출하거나 Entity/Row를 해석하지 않는다. 공용 skip_validation 옵션은 없다.
- 독립 public finish_generation은 결과 digest를 기존처럼 먼저 검사하고 같은 잠금 경계와
  내부 저장 함수를 실행한다. public finish_generation_and_schedule_memory도 직접 호출 시
  독립 인가/잠금을 유지한다. _finalize에서는 한 번 얻은 내부 scope를 재사용한다.
- 내부 완료는 저장된 최신 state와 실제 pending→terminal 전이 여부를 반환한다.
  성공으로 새로 전이한 경우만 메모리를 예약하고 terminal 재전송은 추가 메시지·사용량·
  통계·메모리 예약 없이 기존 결과를 반환한다. 다른 digest는 기존 ValueError다.
- metadata update의 공개 경계도 같은 잠금 기능으로 연결했다. 만료 lease 복구에서만
  이미 잠긴 범위를 재사용하고 execution token·lease·snapshot 불변·result_ready 검증은
  그대로 수행한다. metadata/lease 갱신은 scope의 Info에도 반영한다. 최종 응답은 완료
  반환 Entity를 변환한 state로 만들어 완료 후 상태 SELECT를 제거했다.
- 버전 전환/만료의 stale, 실패/취소 사용량과 0 비용, 참여자 확인, credit commit/release·
  금액 일치·summary_required 예약과 legacy/v2 과금 검증은 유지했다. 같은 세션의 중첩
  use_case_transaction도 유지해 내부 오류를 잡아도 바깥 범위가 rollback-only가 된다.

정상 result_ready 성공 경로의 변경 전후를 같은 SQLite 검증기에서 측정했다.
변경 전 파일이 작업 시작 시 깨끗했던 HEAD b3c7af1의 command/generation과 workflow/answers를
별도 프로세스 메모리에서만 실행하고 같은 product/billing/memory 경계 대역을 유지했다.
작업 트리 파일을 덮어쓰거나 checkout/reset하지 않았다.

| 해당 완료 계층의 조회 | 변경 전 | 변경 후 |
|---|---:|---:|
| 실제 generation 상태 SELECT | 8 | 2 |
| conversation FOR UPDATE 조회 요청(PG SQL 컴파일) | 3 | 1 |

실제 SQLite SQL event로 SELECT를 세고 잠금 요청은 PG dialect 문장으로 확인했다.
잠금 scope가 ORM reference를 수명 동안 유지하므로 repository.finish_generation의
session.get도 추가 SQL을 만들지 않았다. 다른 도메인에서 독립적으로 수행하는 소유권/
과금/기억/통계 SQL과 참여자 조회의 기존 소유권 확인은 제거하거나 전체 호출 수로
포장하지 않았다. 운영 처리량·잠금 대기 시간은 측정하지 않았다.

새 test_generation_completion_contracts 30건은 다음을 확인한다.

- 정상 완료/재전송과 직접 public 완료·원자적 메모리 조립의 독립 호출, 다른 결과 충돌.
- failed/cancelled·버전 전환/만료 stale의 사용량·0 비용·출력 없음과 예약 해제.
- usage/statistics/memory/credit 실패와 reserved 금액 불일치에서 메시지·상태·대역 정산/
  기억 쓰기 모두 rollback, result_ready 유지 후 복구의 단일 효과.
- preparing/calling 만료 lease의 metadata 갱신/불확실성, live/lease 없는 legacy의 보류.
- 소유권·사전 잘못된 usage·종료 scope 재사용 거절, 잡힌 내부 오류의 rollback-only.
- execution token·lease·immutable metadata·이미 저장된 결과 보호, 잠금 전 terminal 변경
  재조회, v2 과금 누락 거절과 unbilled summary_required 예약.

실제 AsyncSession 트랜잭션 event를 SQLite store commit/rollback에 연결해 자체 ORM/SQL과
효과 테이블의 되돌림을 검사했다. SQLite의 UUID/identity/UTC 표현만 테스트에서 보완한다.
외부 도메인 서비스는 같은 session의 효과 테이블 대역이며 실제 credit/memory 구현의
PostgreSQL 영속성·동시성·유일 제약을 증명하지 않는다. 기존 opt-in 복구 테스트 두 파일은
실패를 주입하는 위치만 실제 내부 완료 함수로 옮겨 기존 검증 의도를 유지했다.

| 검증 | 결과 |
|---|---|
| 수정 command/workflow·신규 테스트 Ruff format/check·직접 mypy | 통과; mypy 33소스 |
| 완료/트랜잭션/메시지/답변/과금/프롬프트/사용량/통계 회귀 8파일 | 62 passed, 58 skipped (신규 30건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 390파일·mypy 369소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1212 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 제거했고 실제 DB/외부 공급자를 호출하지
않았다. skipped를 통과로 계산하지 않았다. 실제 PostgreSQL 행 잠금 대기/경합·격리와
기존 DB 통합 58건은 이번 지정 실행에서 미검증이다. 외부 LLM 호출·새 migration·
Any/ignore/cast/기준선 예외·공개 API/DB 계약 변경은 추가하지 않았다.
chat ARCHITECTURE와 원본 감사 U13 수정 상태를 갱신했다.

**다음 범위:** U14 발행 과정의 항목별 조회·flush를 줄인다. 일괄 조회/저장과 단계별 flush로
정리하되 FK·스냅샷 ID·소유권/잠금 순서·발행 실패 rollback 및 영수증 멱등성을 보존한다.
같은 AsyncSession을 병렬 태스크로 실행하지 않는다. GPT-6.1 Sol, 추론 xHigh를 권장한다.


## 기능 감사 수정 9차: U14 발행 조회 재사용·단계별 저장 (2026-10-29)

상품 스냅샷의 슬롯/대상/시작 항목마다 flush하고, 일괄 검증한 시작 항목을 건별로
다시 조회하던 부분을 정리했다. 기존 product/character/lorebook/use_cases의 책임과
공개 HTTP/Python 입력·반환, DB 스키마·저장 JSON 계약은 유지한다.

- builder가 상품 잠금 뒤 조회한 구성 Info를 내부 설정 검증에 전달한다. 내부 반환
  _PublicationSettings가 모델 Info·시작 설정·ID별 시작 항목 Info를 보관한다.
  같은 구성의 3 SELECT와 시작 항목별 재조회, 모델의 중복 검증을 제거했다.
  시작 항목의 연결 로어북 범위·enabled/start_set·설정 부모를 확인하고 동일 잠금
  범위에서 snapshot title/content와 studio_start_options에 재사용한다.
- 원본 캐릭터/로어북 freeze는 순차 실행하고 독립 인가·버전 MAX+1·이미지/에셋/항목
  복사 및 부모 flush를 유지한다. 새로운 공개 freeze API나 skip_validation은 없다.
  상품→캐릭터→로어북 잠금과 정렬된 원본 ID 처리는 그대로다.
- repository.add_snapshot_composition이 새 캐릭터/로어북 슬롯을 add_all 후 flush하고
  그 부모를 참조하는 대상/시작 행을 add_all 후 flush한다. 슬롯 생성은 원본 링크 ID와
  구별하며 역할·순서·primary·scope·target·nullable 시작 제목/본문을 그대로 복사한다.
  UUID 선생성만으로 FK 순서를 보장한다고 가정하지 않는다.
- 상품 snapshot 생성 flush도 유지한다. 마지막 snapshot 본문과 이미 존재하는 부모를
  가리키는 latest_snapshot_id 갱신만 한 flush로 합친다. 두 Entity를 먼저 읽어 중간
  autoflush를 막으며 service는 Entity를 해석하지 않고 mapper에 전달한다.
- studio_publication의 원본/태그/미디어 준비·구성/설정·release·영수증 조립 순서와 U06의
  발행 후 초안 편집·명시적 후속 발행·기존 snapshot/영수증 보존은 유지한다.
  범용 공통 계층·새 transaction/commit·동일 AsyncSession 병렬 실행은 추가하지 않았다.

### 변경 전후 측정

작업 시작 시 깨끗했던 product 발행/설정/repository 파일을 tmp/u14-baseline에 보관하고,
구현 변경 전 동일 test_publication_batch_contracts 검증기를 먼저 실행했다.
당시 작업 트리를 checkout/reset하거나 다른 변경을 되돌리지 않았다. SQLite 메모리 DB의
FK를 실제로 켜고 관계의 FK/복합 FK·유일 제약을 복제했다. 실제 공개 character/lorebook
소유 조회·freeze와 product builder/release 저장 SQL을 사용한다. 모델 검증과 공급자 조회
두 경계만 대역이다. AsyncSession의 SQL 메서드는 동기 SQLite Session 어댑터이고 실제
AsyncSession transaction event를 store commit/rollback에 연결했다.

캐릭터 3·로어북 3·대상 3·시작 6, 미디어 행 없는 첫 product release를 같은 조건으로 측정했다.

| 측정 범위 | 변경 전 | 변경 후 |
|---|---:|---:|
| 실제 SQLite SELECT event | 41 | 32 |
| 명시적 session.flush 호출 | 28 | 14 |
| 실제 변경이 있는 before_flush event | 25 | 11 |
| 상품의 슬롯/대상/시작 연결 저장 flush | 15 | 2 |
| 마지막 snapshot 본문/latest 포인터 갱신 flush | 2 | 1 |
| 모델 검증 호출(대역; SQL 수에 미포함) | 2 | 1 |

SELECT 9회 감소는 구성 3회와 시작 재조회 6회다. INSERT/UPDATE SQL 수가 flush 수와
같다는 뜻은 아니다. 원본 freeze의 항목별 버전·미디어·항목 조회와 studio 원본 준비/
영수증 저장 SQL은 배치화하지 않았고 이 결과를 studio 전체 왕복/운영 성능으로 제시하지
않는다. 실제 PostgreSQL 계획·잠금 대기 시간·동시 발행 격리·처리량은 측정하지 않았다.

### 회귀와 검증

신규 test_publication_batch_contracts 17건은 실제 SQLite SQL/FK로 다음을 확인한다.

- 첫 발행의 SQL/flush 수, 슬롯 개수·원본/새 슬롯 ID 대응·시작 순서·nullable title,
  PG dialect 컴파일로 상품→정렬된 캐릭터→정렬된 로어북 잠금 요청과 freeze의 독립 인가.
- 동일 내용 후속 발행의 새 버전·동일 digest·media 분류, 원본 편집 후 content 분류,
  이전 snapshot/소스별 1·2·3 버전 보존.
- 슬롯 부모·대상/시작 자식·최신 포인터·릴리스 저장의 실제 flush 직후 실패 4조합에서
  모든 새 snapshot/연결/릴리스와 최신 포인터 rollback, 재시도 버전 2의 정상 복구.
- 상품/캐릭터/로어북 미소유 3조합, 독립 공개 서비스의 미존재 3조합,
  비활성/일반 항목으로 변경된 시작·빈 시작 설정의 쓰기 전 거절, 부모 불일치 FK 거절,
  상위 transaction 없는 builder 거절.

기존 payload/digest 계약 테스트의 대역을 새 내부 검증 결과와 add_all에 맞췄다.
PG opt-in의 private 검증 호출도 ORM 대신 mapper를 거친 Info/구성으로 연결하고 같은
파일의 타입·존재 assertion을 보완했다. 해당 PG 테스트는 이번에 실행하지 않았다.
기존 studio 회귀의 발행 성공/후속 발행·영수증 재시도·fingerprint 충돌·실패 rollback도
함께 검증했으며 studio 상위 도메인 서비스 대역 검증임을 유지한다.

| 검증 | 결과 |
|---|---|
| product 전체·신규/수정 3테스트 Ruff format/check·직접 mypy | 통과; mypy 47소스 |
| 신규 배치/상품 발행/studio 발행·후속/상품 통합·구성/character·lorebook command 8파일 | 116 passed, 0 failed, 9 skipped (신규 17건 포함) |
| 필수 앱 전체 품질 검사 | Ruff 390파일·mypy 369소스·계약/검사기 13 passed; 기준선 0개; 종료 코드 0 |
| 전체 API 회귀 | 1229 passed, 0 failed, 288 skipped |
| 변경 범위 git diff --check | 통과 |

모든 검증은 프로젝트 .venv/Scripts/python.exe로 실행하고 TEST_DATABASE_URL 및
TEST_AUTH_DATABASE_URL을 제거했다. Windows 샌드박스의 asyncio 로컬 소켓 대기와
기본 임시 폴더 권한 오류는 승인된 오프라인 테스트 실행/프로젝트 전용 basetemp로
해결했다. 최초 품질 실행의 임시 폴더 오류 2건은 최종 13 passed로 재검증했으며 실패를
건너뛰어 통과로 세지 않았다. skipped 288건도 통과에 포함하지 않았다.
실제 PostgreSQL·외부 DB migration/초기화/삭제·외부 공급자는 실행하지 않았다.
SQLite 제약과 SQL 컴파일은 실제 PostgreSQL 행 잠금/경합·격리를 증명하지 않는다.
새 Any/ignore/cast/기준선 예외·공개 API/DB 계약 변경은 없다. product/use_cases ARCHITECTURE와
원본 감사 U14 수정 상태를 갱신했고 기존 staged/unstaged/untracked 변경을 보존했다.

**다음 범위:** U15 로어 v1의 exact·regex 옵션 의미를 수정한다. legacy 정책을 유지하면서
case_sensitive와 정규식 컴파일/캐시 키, exact의 전체 일치 및 studio 진단/발행본 활성화
계약을 회귀로 고정한다. GPT-6.1 Sol, 추론 high를 권장한다. 범위가 정해진 규칙 수정과
호환성 검증이라는 업무 판단이며 모델 간 성능 비교를 수행한 것은 아니다.
OpenAI Docs의 [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)과
[추론 수준 안내](https://developers.openai.com/api/docs/guides/reasoning)를 확인했다.

## 기능 감사 수정 10차: U15·U25 통계 범위 통합 점검 (2026-10-29)

U15 로어 활성화와 U25 통계 재예약 배치 변경을 동일 작업 트리에서 대조하고 전체 API를
검증했다. 추가 제품 코드 수정이나 별도 merge/commit/push는 하지 않았다. 기존
staged/unstaged/untracked 변경과 두 모듈 ARCHITECTURE의 앞선 U06/U14 기록을 보존했다.
병렬 구현 중 개별 작업은 공통 REPORT를 수정하지 않았고, 이번 통합 단계에서 상태와
실행 결과를 반영한다. 상세 명령·로그·한계는 [U15-U25-INTEGRATION.md](U15-U25-INTEGRATION.md)에 있다.

- **U15 완료:** exact는 기존 casefold 후 전체 문자열 비교이며 partial_match와 관계없이
  접두/접미 문자열에 일치하지 않는다. regex의 case_sensitive를 컴파일 정책과 캐시 키에
  반영했다. 옵션 없는 legacy·라이브 query의 대소문자 무시, pydantic-core 선형 시간
  엔진과 기존 오류/HTTP 번역, 입력·metadata·스냅샷 비변경을 유지한다. 실제 studio 변환은
  contains를 생성하며 도메인 exact/regex 진단과 구분해 검증했다. 신규 회귀 75건의
  단독 작업 근거는 [U15-WORKLOG.md](U15-WORKLOG.md)에 남겼다.
- **U25 통계 재예약 완료·태그 범위 미완료:** 상품×서울 날짜 키를 지연 생성하고 저장소가
  최대 500개 입력 키씩 중복 제거 후 다중 VALUES upsert를 순차 실행한다. 기존 단건
  API·날짜·DB now() 시각·상위 rollback·claim/complete 정책을 유지한다. 같은 SQLite
  검증기에서 16상품×32일의 upsert 512→2회(상품 SELECT는 전후 각 1회)를 확인했다.
  신규 회귀 33건의 근거는 [U25-STATISTICS-WORKLOG.md](U25-STATISTICS-WORKLOG.md)에 있다.
  태그 이름 resolve 배치화는 남아 있으므로 U25 전체 완료가 아니다.

| 통합 검증 | 결과 |
|---|---|
| U15/U25 변경 Python 7파일 직접 Ruff format/check·mypy | 통과, mypy 7소스 |
| 필수 tools/check_backend_quality.py | Ruff 390파일·mypy 369소스·13 passed / 0 failed / 0 skipped·기준선 0개 |
| 전체 API 오프라인 회귀 | **1337 passed / 0 failed / 288 skipped**, 기존 422 상수 경고 2개 |
| 변경 범위 git diff --check | 통과 |

전체 API의 1337 passed는 U14 기준 1229건에 U15 신규 75건과 U25 신규 33건이 더해진 수다.
품질 검사 13건은 전체 API에도 포함되므로 전체 통과 수에 다시 더하지 않는다. skipped도
passed에 포함하지 않는다. 모든 실행은 프로젝트 .venv/Scripts/python.exe를 사용했고
TEST_DATABASE_URL과 TEST_AUTH_DATABASE_URL을 제거했다.

첫 전체 실행은 긴 basetemp 아래 로컬 저장소의 269자 임시 파일 경로에서 3건이 실패했다
(1334 passed / 3 failed / 288 skipped). 짧은 새 프로젝트 경로에서 실패 3건이 모두 통과했고,
동일한 전체 API를 새 짧은 경로로 다시 실행해 위 최종 결과를 확인했다. 저장소 제품 코드나
검사 설정을 바꾸거나 실패 테스트를 제외하지 않았다. 실제 PostgreSQL 행 잠금·경합·격리,
동시 재예약/claim·실행 계획·운영 처리량은 미검증이며 DB migration/초기화/삭제와 외부
공급자 요청은 실행하지 않았다. 다음 U25 범위는 태그 이름 resolve 배치화다.

## 기능 감사 수정 11차: U23 로컬 reader·파일·락 수명 (2026-10-29)

test_local의 누적 키 락을 WeakValueDictionary로 바꾸고, Windows에서 삭제 공유를 허용한
파일 handle을 BinaryIO로 넘긴다. 열린 reader는 읽기 시작 시점의 본문·metadata를 유지한다.
삭제 후 새 조회는 미존재이며 같은 키를 즉시 재사용할 수 있다. Windows의 열린 대상 교체
거절은 기존 이름의 임시 .old 이동→새 본문 발행→이전 이름 unlink로 처리하고, 발행/정리
실패 시 본문과 sidecar 복원을 시도한다. 영속 레이아웃·공개 API/키·metadata 필드·S3는
변경하지 않았고 전체 파일 복사나 reader 수명 전체의 키 잠금도 추가하지 않았다.

to_thread 작업은 첫 취소를 보존하면서 실제 I/O 종료까지 회수한다. store/delete/metadata의
키 락과 reader의 read/close 락을 그 뒤 해제한다. 취소된 read 획득의 늦은 reader도 닫는다.
취소된 쓰기는 이미 반영됐을 수 있고 취소 반환은 I/O 종료까지 지연될 수 있다. 호출자의
입력 stream·반환 reader 종료 책임, 기존 오류와 cause·idempotent delete/close를 유지한다.

수정 전 신규 회귀 10건이 모두 실패하는 것을 확인한 뒤, 최종 22건으로 확대했다.
실제 Windows 파일과 제어된 worker thread로 삭제/재사용·열린 reader의 연속 덮어쓰기,
복원·native handle 회수, 반복 취소·동일 키 대기·다른 키 진행·read/close 순서·락 회수를
검증했다. Windows/Linux 대상 직접 Ruff/mypy, 필수 품질 검사(Ruff 390파일·mypy 369소스·
13 passed·기준선 0개), 관련 7파일 **86 passed / 0 failed / 2 skipped**, 전체 API
**1359 passed / 0 failed / 288 skipped**가 통과했다. 기존 422 경고 2개는 유지한다.
전체 API는 U15/U25 통합 기준 1337건에 이번 신규 22건을 포함하며 skipped와 품질 검사
13건을 다시 더하지 않는다. 프로젝트 .venv/Scripts/python.exe와 짧은 새 basetemp를 쓰고
TEST_DATABASE_URL과 TEST_AUTH_DATABASE_URL을 제거했다.

기존 U08 S3/아키텍처 변경과 다른 staged/unstaged/untracked 변경을 보존했다.
Any/ignore/cast/기준선 예외·공통 검사 설정을 추가하지 않았고 commit/push는 하지 않았다.
Linux 런타임·다중 프로세스·네트워크 파일시스템·중단/복원 자체 실패의 완전 복구·장시간
RSS와 실제 DB/S3는 미검증이다. DB migration/초기화/삭제 및 외부 공급자 요청은 없었다.
정책·출처·실행 명령과 로그는 [U23-WORKLOG.md](U23-WORKLOG.md)에 기록했다.

## 후속 작업 범위 조정: U19 이미지 기능 전반 구조 개편 (2026-10-30)

사용자 요청에 따라 U19를 오류 처리 보완에서 **이미지 기능 전반의 구조 개편 과제**로
재정의한다. 감정 태그 중심의 현재 구조에 한정하지 않고 상황·장면·대화 맥락에 맞는
이미지를 다루는 데이터 구조·분류/연결·선택/전환/기본값 정책, 스튜디오 관리·채팅 표시와
발행 스냅샷·미디어 참조·기존 데이터 호환을 함께 검토한다. 구체적인 모델과 선택 방식은
아직 결정하지 않았고 구현도 착수하지 않았다. 기본 이미지/감정 태그 제약 오류 번역만으로
U19를 완료로 처리하지 않는다. 원본 감사의 제약 오류 근거는 보존했다.
상세 범위는 [U19-REDESIGN-NOTE.md](U19-REDESIGN-NOTE.md)에 기록한다.

U19 이외의 다음 작업 후보는 **U25의 남은 태그 이름 resolve 배치화**를 우선하고,
그다음 **U29의 SDK 예외 분류·메모리 작업 기한**을 검토한다. 현재 tag.resolve_tags는
정렬된 이름마다 단건 resolve를 호출하므로 U25 잔여 범위가 남아 있다. U29도 OpenAI/
Anthropic의 catch-all과 상태 없는 예외의 재시도 분류가 남아 있어 별도 검증이 필요하다.
U16 태그 공통화는 U25 태그 경계가 정리된 뒤 진행하고, U28의 이미지 업로드 수명 변경은
U19 개편과 공유하는 책임을 확인한다. 이 순서는 현 코드·감사 범위에 따른 작업 제안이며
이번에 해당 구현을 시작하거나 별도 대화를 생성한 것은 아니다.

이번 변경은 문서만 수정했다. 앱 코드·DB·테스트·공통 검사 설정은 변경하지 않았고
테스트를 재실행하지 않았다. 기존 U23의 전체 API 1359 passed / 288 skipped는 이전
실행 결과로 보존하며 이번 문서 수정의 신규 검증 결과로 제시하지 않는다.

## 기능 감사 수정: U29 SDK 오류 분류·메모리 작업 전체 기한 (2026-10-30)

OpenAI/Anthropic의 상태 없는 TypeError·JSON 파싱·일반 RuntimeError·미분류 SDK
APIError는 기존 PROVIDER 오류를 유지하면서 retryable=False로 전달한다. 명시적인
SDK timeout·연결·rate limit, 상태 코드 기반 4xx/5xx와 cause/metadata, 호출 뒤 응답
추출 오류·취소·클라이언트 소유권·Voyage의 기존 계약은 유지했다.

ProcessMemoryWorkCommand에 호환 기본값 timeout_seconds=240.0을 추가했다. workflow는
하나의 단조 시계 기한을 pending 색인·원문 읽기·새 요약·저장·임베딩·완료에 공유한다.
기한 초과는 MemoryWorkDeadlineExceededError로 구분하고 같은 태스크의 취소/DB 정리를
기다린 뒤 기존 5회·5~300초 backoff 큐에 기록한다. 늦은 공급자 결과는 다음 저장 전에
기한을 재확인한다. worker는 MEMORY_WORK_TIMEOUT_SECONDS의 유한 양수와
timeout<lease(기본 240<300), 기존 lease 1~3600초를 자원 생성 전에 검증한다.

| 검증 | 결과 |
|---|---|
| 수정 전 분류식만 별도 프로세스 메모리에 복원 | 신규 SDK 회귀 8 failed / 4 passed로 결함 재현 |
| 신규 회귀 | SDK 12건 + 메모리/worker 22건 = 34건 |
| SDK·임베딩·memory·worker 관련 7파일 | **113 passed / 0 failed / 1 skipped** |
| 필수 tools/check_backend_quality.py | Ruff 390파일·mypy 369소스·13 passed·기준선 0개 |
| 전체 API 오프라인 회귀 | **1418 passed / 0 failed / 288 skipped**, 기존 422 경고 2개 |
| 변경 파일 Ruff·git diff --check | 통과 |

전체 API 결과는 기존 미커밋 변경을 포함한 현재 작업 트리의 통합 결과다. 신규 34건과
품질 검사 13건은 전체 API에도 포함되므로 다시 더하지 않는다. PostgreSQL·live Voyage
검사는 환경 변수를 제거해 건너뛰었고 skipped는 passed에 포함하지 않았다.

기한은 workflow 진입부터 한 시도에 적용된다. claim DB 대기·모든 재시도 누적 SLA,
취소를 무시하는 코드·동기 파싱·rollback/commit·실패 기록의 벽시계 상한은 보장하지
않는다. lease 갱신/claim별 토큰은 추가하지 않았고 U03의 실행 소유권 과제는 남는다.
실제 PostgreSQL 잠금·경합·격리와 live 공급자 동작은 미검증이다.

기존 staged/unstaged/untracked 변경·외부 API/DB/저장 JSON을 보존했다. 기준선·공통 검사
설정·SDK 버전 변경, migration/DB 초기화·삭제, 실제 공급자 요청, commit/push는 없다.
샌드박스의 Windows asyncio socketpair 제한은 승인된 오프라인 실행으로, pytest 기본
임시 경로 권한 오류는 프로젝트 내부 새 basetemp로 해결했다. 제품/검사 코드를 우회하지
않았다. 실행 명령·정책·출처·한계는 [U29-WORKLOG.md](U29-WORKLOG.md)에 남겼다.


## U16 태그 정책 공통화 (2026-10-30)

세 콘텐츠의 태그 추가/교체 순서와 내부 선택/제거·관리자 지정 보호를
content/tag/service/policy.py의 순수 공개 서비스로 모았다. 호출은 공개 Command/Info만
사용하며 도메인별 인가·부모 잠금·저장·응답과 U25 이름 해석/배치 SQL은 유지한다.
공통 repository나 router/mapper 프레임워크는 추가하지 않았다.

품질 검사(Ruff/mypy/시그니처 및 아키텍처/패턴 13건) 통과, 태그 정책·서비스·U25·
스키마 회귀 72 passed / 11 skipped, 콘텐츠 HTTP·스튜디오 회귀 63 passed.
PG 11건은 TEST_DATABASE_URL 미설정으로 skip했으며 실제 잠금/경합 검증은 남아 있다.
전체 변경과 명령·환경 우회·검증 한계는 [U16-WORKLOG.md](U16-WORKLOG.md)를 따른다.

## U18 오류 분류·복구 진단 (2026-10-30)

예약 전 문맥 준비의 내부/저장소 오류는 실패 receipt로 request_key를 소진하지 않는다.
예상 예산·공급자·timeout 실패는 기존 unbilled receipt를 유지한다. 결과 검증은 전용
예외의 code로 분류하고 임의 오류 메시지를 검증 실패로 해석하지 않는다. billing binding/
예약액 불변 조건은 기존 AnswerStorageError의 하위 타입인 AnswerStateError로 식별한다.

workflow 단계·diagnostic_id→generation_id 연결·복구 attempt_count·타입 기반 원인 분류와
정제한 stack_frames를 기록한다. 예외 메시지·SQL·매개변수·원문·locals·source·절대 경로·
실행 token/request_key·raw traceback은 기록하지 않는다. 코드 위치 정제는 내부 service util에
분리하고 실행/DB 책임은 기존 workflow에 유지했다. chat/ARCHITECTURE.md를 갱신했다.

일반 완료·동일 키 재생·background 복구는 같은 완료/재조회 경계를 사용한다. commit 응답이
유실돼도 새 세션 terminal 확인으로 완료를 반환하고, 확인 실패 시 최초 cause와 재조회
오류를 각각 보존한다. 과금·staging 보존과 공급자 재호출 금지, 기존 HTTP 계약은 유지한다.
attempt_count는 인스턴스별 최근 1,024개 생성에 한정한 진단값이며 재시작/LRU 퇴출로
초기화된다. 복구 상한·격리·강제 해제·영속 횟수 정책은 미확정 commit 처리 계약과 함께
정할 별도 과제로 남겼다.

신규 진단 23건, 관련 답변/HTTP **111 passed**, 진단·메모리 기한 단독 **45 passed**.
필수 품질 검사(기준선 0·Ruff 393파일·mypy 372소스·아키텍처/패턴 13건)가 통과했다.
최종 전체 API는 **1463 passed / 0 failed / 288 skipped**, 기존 경고 2개다. 현재 작업 트리의
통합 결과이며 다른 미커밋 변경도 포함한다. PostgreSQL·live 공급자는 미검증이다.
실행 명령·초기 실패 교정·검증 한계와 운영 진단은 [U18-WORKLOG.md](U18-WORKLOG.md)를 따른다.

같은 날 재점검에서 최초 세션/요청/문맥 조회와 읽기 트랜잭션 종료에도 진단 경계를
추가했다. `preparation_read`의 DB 오류는 기존 503/동일 키 재시도 응답으로 번역하고,
생성·예약·공급자 호출 전이므로 storage_uncertain=False로 기록한다. SQLAlchemy의
LookupError 하위 타입도 저장소로 분류하며 기존 입력·인가·설정 예외와 취소 전파는
보존한다. 추가 16건을 포함한 관련 회귀는 **83 passed / 16 skipped**, 필수 품질 검사도
통과했다. 이 재점검에서는 전체 API·실제 PostgreSQL·live 공급자 검증을 재실행하지 않았다.

## U18 잔여 복구 정책 구현 (2026-11-02)

앞선 프로세스별 진단 횟수를 영속 admission으로 대체했다. 자동 복구 최대 5회와
30초 지수 대기(최대 900초), 결정론적 invariant/internal/storage_constraint 즉시 격리를
동일 키 재전송과 supervisor에 공통 적용한다. conversation → generation 잠금 아래
횟수/감사 행을 먼저 commit하고 기존 저장 결과의 완료만 재시도한다. 격리는 생성의
pending·metadata·예약액을 유지하며 공급자를 호출하거나 임의 해제하지 않는다.

운영자/사유를 요구하는 `app.answer_recovery --retry`는 한 번만 감사된 수동 복구를
실행하고 예산·격리를 초기화하지 않는다. 기본 실행은 사용자 범위의 정제된 상태/감사
조회다. Alembic 0036/초기 SQL 026을 추가하고 복구 기록이 있으면 downgrade를 거절한다.
절차·배포 중지·운영 관측은 [답변 복구 운영 정책](../../../references_document/reference/answer-recovery-policy.md),
검증과 남은 실제 네트워크/live 범위는 [U18-WORKLOG.md](U18-WORKLOG.md)를 따른다.

## U21 billing→credit 반복 잠금·SAVEPOINT 정리 (2026-10-30)

credit의 공개 `use_credit_write_scope(session)`로 billing 예약·확정·해제와 하위 credit
쓰기를 하나의 SAVEPOINT에 조합했다. 독립 credit 호출은 자체 경계를 열고, 참여한
하위 실패를 잡더라도 공유 scope 전체를 rollback한다. 상위 트랜잭션의 계속 실행과
동일 키 재시도, binding/잔액/예약/원장 원자성을 유지한다.

잠금 근거는 동일한 활성 상위 트랜잭션·SAVEPOINT·사용자/재화 범위에서만 재사용한다.
잔액은 매번 새로 읽고 다른 지갑·독립 하위 SAVEPOINT·새 트랜잭션에는 근거를 넘기지
않는다. billing 요청 키 → 지갑 → binding → 예약 순서, 지갑 대기 후 견적 만료 검사,
무료 우선 배분·기존 최종 상태 재생은 보존했다. 검증 생략 옵션이나 ORM/Row의 모듈 간
전달은 없고, 기존 command 실행 책임에 유지하며 두 모듈 아키텍처를 갱신했다.

실제 PostgreSQL 단일 호출 SQL은 신규 예약 **22→17**, 확정 **20→15**, 해제 **18→13**회다.
SAVEPOINT/지갑 FOR UPDATE/legacy 검사는 각각 2→1회, advisory lock은 3→2회로 줄었다.
기존 동일 키 예약 재생은 SQL 10회 그대로다. 운영 지연/처리량 개선율은 측정하지 않았다.

신규 scope·SQL 회귀 16건을 포함한 관련 PostgreSQL 8파일은 **152 passed / 0 failed /
0 skipped**다. 확장 검증에서 발견한 commit 응답 유실 테스트의 주입 위치도 현재
generation 잠금 경계에 맞춰 교정해 4단계의 실제 commit 후 응답 유실을 검증했다.
필수 품질 검사(기준선 0, Ruff 393파일, mypy 372소스, 아키텍처/패턴 13건)와 변경 파일
포맷·diff 검사가 통과했다. 전체 API/live 공급자/운영 부하 검증과는 구별한다.
측정 조건·명령·초기 실패 교정은 [U21-WORKLOG.md](U21-WORKLOG.md)를 따른다.

## U26 보고 매퍼·타입 중복 재점검 (2026-11-02)

현재 reporting 매퍼는 명시적 필드 선택을 사용하며 product/moderation의 불필요한
scalar 깊은 복사는 이미 제거돼 있었다. 작가·운영의 유사한 지표/일별/View는 영역별
공개 타입과 노출 계약을 소유하므로 유지했다. 범용 매퍼·공통 기반 타입을 추가하거나
다른 reporting 영역을 참조하지 않았다. JSON 깊은 복사도 격리 계약으로 보존했다.

잔여 항등 `moderation.scalar_row_to_value`와 전용 TypeVar, 호출 4곳을 제거했다.
저장소의 `UUID | None` 값을 service가 직접 판단하며 Row/Entity는 계속 mapper로
변환한다. SQL·잠금·상태 충돌·인가·DTO·금액/날짜 계약은 유지하고 모듈 아키텍처를
갱신했다. 현재 U26의 실익 범위 정리는 완료했다.

필수 품질 검사(패턴 진단/예외 0건·Ruff 396파일·mypy 375소스·아키텍처/패턴
13 passed)와 관련 11파일 **177 passed / 0 failed / 0 skipped**가 통과했다.
실제 PostgreSQL 신고/잠금·보고 검증을 포함하며 전체 API·운영 성능 측정은 수행하지
않았다. 초기 샌드박스 소켓 제한은 승인된 실행으로 해결했다. 기존 작업 트리 변경과
검사 설정을 보존했다. 판단 근거·명령·검증 한계는 [U26-WORKLOG.md](U26-WORKLOG.md)에
기록했다.


## U17 답변 복구 실행 계획·부분 인덱스·종료 lease (2026-11-02)

실제 repository SQL을 합성 10만 행의 네 분포에서 custom/generic 계획으로 비교했다.
종료 99,000행 뒤의 pending 조회는 기존 전체 인덱스 custom 50.902ms에서 최종 부분
인덱스 0.029ms, 복구 대상이 없는 경우는 32.789ms에서 0.009ms였다. pending 절반의
backlog에서는 기존도 0.048ms로 빠르므로 분포에 따른 차이를 유지해 해석한다.
바인딩된 status의 generic plan이 부분 인덱스를 쓰지 못하는 경우를 확인하고 복구의
고정 pending 조건을 SQL 상수로 표현했다. 최종 generic도 네 분포 모두 부분 인덱스를
선택했으며 0.012–0.042ms였다. 운영 지연·처리량 개선율을 측정한 결과는 아니다.

0035 / 초기 SQL 025 / ORM을 leased pending 부분 인덱스로 맞췄다. 종료 전이는 같은
트랜잭션에서 lease를 NULL로 만들고 상위 실패 시 원래 pending lease를 복원한다.
metadata/token/완료 사실·과금·같은 키 재생은 유지하며 기존 종료 행은 대량 갱신하지
않는다. 공개 API/계층을 추가하지 않았고 chat/DB 아키텍처를 갱신했다.

최종 관련 10파일은 **146 passed / 0 failed / 0 skipped**이며 실제 PostgreSQL의
4종 종료·rollback·generic 계획·migration 행 보존과 기존 복구/과금/HTTP 회귀를
포함한다. 필수 품질 검사(기준선 0, Ruff 396파일, mypy 375소스, 아키텍처/패턴 13건)와
신규 파일 lint/포맷·diff 검사도 통과했다. 운영에는 미적용이며 API/worker 중지 후
인덱스 migration이 필요하다. 조건·계획 증거·재현 명령·검증 한계는
[U17-WORKLOG.md](U17-WORKLOG.md), [측정 JSON](U17-RECOVERY-PLANS.json)을 따른다.

## U28 업로드 해싱 offload·취소 시 파일 수명 (2026-11-02)

character의 reserve_upload는 검증·seek/read·SHA-256 전체를 하나의 to_thread 태스크로
실행한다. 내부 보조 함수가 shield로 태스크 종료와 결과/오류 회수를 소유하고 첫
CancelledError를 보존하므로 반복 취소에도 HTTP 임시 파일을 조기 종료하지 않는다.
취소 후 예약/저장으로 진행하지 않으며 입력 stream의 호출자 소유권, 지문·크기·검증·
멱등성, 예약 선행 commit·외부 저장 중 잠금·GC/재시도 정책은 유지한다.

신규 16건을 포함한 오프라인 미디어 계약 **47 passed**, 전용 로컬 PostgreSQL의
기존 미디어/HTTP **32 passed**와 필수 품질 검사가 통과했다. 실제 worker thread의
읽기/최종 되감기에서 반복 취소·I/O 실패·파일 종료 순서를 확인했다. 새 타입 검사
예외는 없고 공개 API나 공통 실행 계층을 추가하지 않았다. 실제 S3 네트워크·브라우저
단절·프로세스 중단·운영 지연은 미검증이며 전송 중 잠금 재설계와 전체 deadline은
별도 범위다. [U28-WORKLOG.md](U28-WORKLOG.md)에 명령·결과·한계를 기록했다.

## U25 실제 PostgreSQL 경합 검증·감사 통합 완료 (2026-11-02)

통계 재예약과 태그 이름 resolve의 기존 500개 배치 구현을 함께 재점검했다. 통계
16상품×32일 upsert 512→2회, 태그 1,001이름 INSERT/SELECT 각각 1,001→3회의 앞선
SQLite 측정과 이번 실제 PG 검증을 모아 **U25 양쪽 범위를 완료**로 갱신한다.
2026-10-29 통계 단독 통합 당시의 태그 미완료 표기는 당시 상태의 기록이다.

신규 `test_u25_postgres_concurrency.py` **17건**은 독립 세션의 관리자 생성·이름 변경·
비활성화와 겹치는 resolve, 500개 경계·취소 rollback, 동시 repair·worker claim/
SKIP LOCKED/완료 및 rollback·단건 dirty 예약을 검증한다. 16건은 별도 관찰 연결의
pg_blocking_pids로 실제 대기를 확인한 뒤 선행 작업을 해제한다. 나머지 1건은 실제
INSERT/SELECT 사이에 관리자 rename을 commit하여 기존 재시도 오류와 전체 rollback을
확인한다. INSERT 전에 이름이 바뀌면 옛 이름의 새 ID를 만들 수 있는 기존 동작도 구분한다.

관련 태그·통계·HTTP·스튜디오 발행 15파일은 **201 passed / 0 failed / 0 skipped**,
전체 API 오프라인은 **1706 passed / 0 failed / 446 skipped / 2 warnings**다.
필수 품질 검사(진단·기준선 0, Ruff 395파일·mypy 374소스·아키텍처/패턴 13 passed),
신규 테스트 직접 Ruff/mypy 및 변경 파일 diff 검사가 통과했다. 두 실행의 중복 회귀를
합산하지 않으며 17건은 오프라인에서는 skip, PG 실행에서는 passed다. 경고는 기존
lorebook HTTP 테스트의 Starlette 422 상수 deprecation이다.

제품 코드·공개 API·스키마·잠금/격리/재시도 정책 및 검사 예외는 변경하지 않았다.
PG 17.11·en_US.utf8·READ COMMITTED에서 지정한 유한한 경합 검증이다. 모든 교착 부재·
다른 격리 수준/운영 환경·부하/계획/처리량을 보장하지 않는다. requested_at은 DB
트랜잭션 시작 시각이며 모든 실행에서 단조 증가한다는 보장도 추가하지 않았다.
전용 로컬 DB의 테스트별 격리 스키마만 생성·정리했고 전체 migration/운영 적용·live
외부 공급자는 검증하지 않았다. 조건·경합별 결과·재실행 명령·초기 테스트 교정·로그와
한계는 [U25-PG-INTEGRATION.md](U25-PG-INTEGRATION.md)를 따른다.
