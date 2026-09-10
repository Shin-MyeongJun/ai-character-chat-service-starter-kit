# 백엔드 구조 점검 및 리팩터링 결과

기준: [모듈 아키텍처 및 명명 규칙](module-architecture-and-naming.md). 기준 문서는 완화하거나 수정하지 않았다.

점검 범위는 `apps/api/app`의 현재 Python 구현, 모듈 간 호출부, HTTP 라우터, 기존 테스트 및 변경한 경로의 회귀 테스트다. 원래 비어 있거나 연결되지 않은 기능을 구현 완료로 간주하지 않는다. 사용자 기준 문서와 기존 작업은 보존했고, 이번 작업용 변환 스크립트는 제거했다.

## 확인한 위반과 교정

| 위치 | 위반한 규칙 또는 문제 | 실제 교정 |
|---|---|---|
| `content/product/service/{composition,settings,publication,snapshots}.py` | 타 모듈 ORM 접근 및 조회·변경 책임 혼재: §0.2, B, C | character/lorebook 공개 Command와 Info로 소유권·잠금·동결·시작 항목을 조회한다. 상품 저장은 `repository/{composition,publication}.py`로 이동했다. |
| `chatting/conversation/{service,generation,versions}.py` | 서비스의 SQL·Entity 필드 해석, 타 모듈 데이터 직접 참조: B.5, C.1 | 자체 repository → mapper → Info 흐름으로 바꾸고 `service/command/{generation,versions,context}.py`로 역할을 분리했다. 상품·LLM·billing 접근은 공개 service/types를 사용한다. |
| `commerce/billing/attribution.py` | 결제 ORM 소비와 상품 ORM 직접 조회: B, C.1 | 저장소 조회·갱신을 repository로 옮기고 PaymentInfo/PaymentEventInfo로 검증한다. 매출·환불 반환은 PaymentEventInfo이며 모든 호출부의 ID 사용을 갱신했다. |
| `content/product/service/statistics.py` | conversation/billing 테이블을 직접 집계, 날짜 큐 저장 책임 분산: §0.2, C | 각 공개 서비스에서 통계 사실 Info를 받고 순수 집계 mapper를 거쳐 product 저장소에 반영한다. 조회·쓰기 구현을 분리하고 큐 갱신도 product 공개 Command를 통해 요청한다. |
| `content/{character,lorebook}/service/command.py` | service의 Entity 필드 변경, mapper의 입력 수정: C.1, D | 검증은 Info로 수행하고 실제 Entity 생성·필드 변경은 repository가 수행한다. 재조회는 동일한 소유자 조건과 잠금을 유지한다. |
| `content/{character,lorebook}/repository.py`, `chatting/memory/repository.py` | 공개 페이지 타입으로 ORM을 운반: C.1, E | 저장소 전용 PageRow를 정의했다. 서비스 반환은 mapper가 만든 Info 페이지다. |
| `content/lorebook/service/query.py`, `conversation/mapper/persistence.py` | 원본 기반 업무 판단, mapper의 활성 항목 정책: B.5, D | 키워드는 EntryInfo로 변환한 뒤 판단하고, 런타임 활성 항목 선택은 service에서 수행한다. mapper는 선택된 값만 조합한다. |
| `governance/admin/product_policy.py`, `llm/replacement.py` | 다른 모듈 ORM을 이용한 인가·정책 변경: §0.2, F.2 | identity 공개 관리자 검사 및 product 공개 정책 Command로 변경했다. HTTP 오류는 공통 HTTP 처리기로 변환한다. |
| `content/{character,lorebook}/router.py` | 서로 다른 접근 주체 혼재: A.6 | 관리자 조회는 governance/admin, 상태 변경 라우팅은 governance/moderation으로 이동했다. `app/http/routes.py`가 고정 경로를 먼저 조립한다. |
| 서비스 입력·반환과 mapper 함수명 | 원시 인자/Query/Write 입력, UUID·int 반환, 대상 없는 변환명: B.3, B.1, Part 2 | 공개 업무 입력을 Command로 바꾸고 호출부·테스트를 함께 갱신했다. Info/View 결과와 mapper의 대상·출처·결과 이름, 계층별 import 별칭을 정리했다. LLM 공개 생성 요청도 GenerateTextCommand를 사용한다. |
| 쓰기 서비스들의 `session.begin()` 및 런타임 준비 | 조합된 내부 호출의 트랜잭션 소유 불명확: F.1 | 공통 `use_case_transaction`으로 조합한다. 내부 실패를 잡아도 전체 범위는 rollback-only이며 내부 commit은 없다. 모델 대체 이력을 기록할 수 있는 런타임 준비도 Command로 분류했다. |

실제 발행 → 소스 동결 → 릴리스 노트, 대화 시작 → 버전 전환 → 생성 완료 → 사용량/통계 큐, 결제 배분 → 환불 → 통계 재집계 호출 흐름과 PostgreSQL 동시성·실패 경로를 확인했다. 문자열 검색만으로 준수를 판정하지 않았다.

## 구조를 분리하거나 유지한 이유

상품 구성·발행·릴리스·통계는 데이터 수명과 변경 이유가 달라 service 및 repository의 기능 파일로 분리했다. 대화 시작·생성·버전 전환·런타임 준비도 별도 유스케이스다. 반면 캐릭터와 로어북의 원본·미디어·스냅샷 저장은 연결된 수명 주기를 가지므로 현재 repository 파일을 유지했다.

정규식 매칭과 모델 대체 후보 선택은 service/util로 옮겼다. 독립된 업무 기능을 util에 넣지 않았다. 패키지 전환에 필요한 `__init__.py` 외에 형식적인 빈 업무 계층은 추가하지 않았다. 이전 Python import의 명시적 재노출과 실제 구현은 문서에 구분했다.

변경한 10개 모듈의 `ARCHITECTURE.md`에 소유 테이블, 공개 서비스, 파일 책임, 트랜잭션·삭제/멱등 반환 계약, 분리 이유를 기록했다. memory의 Conversation 소유권 스코핑을 제한된 저장소 인가 예외로 명시했다.

## 외부 계약 보존

- 변경 전 저장한 `tests/fixtures/backend-openapi.json`과 현재 개별 라우터 및 공통 조립 라우터의 OpenAPI 전체를 각각 비교한다. 경로·JSON 스키마·상태 코드·operationId가 동일하다.
- 기존 ResponseDto 이름 중 새 권장 명명과 차이가 있는 것은 OpenAPI 및 생성 클라이언트 계약 보존 요구를 우선해 유지했다. 기준 문서 자체를 바꾸지는 않았다. 생성 클라이언트 재생성은 실행하지 않았으며 입력 스키마의 동일성을 검증했다.
- 접근 주체가 함께 쓰는 HTTP DTO만 `app/http/contracts`에 공유한다. 다른 모듈 schemas를 우회 참조하지 않는다. 기존 dependency override 함수의 동일성과 미연결 시 503 동작을 유지한다.
- DB 모델과 Alembic 마이그레이션의 변경은 없다. 운영 DB 마이그레이션이나 배포는 수행하지 않았다.

## 검증

저장소 루트에서 `.venv` Python과 `PYTHONPATH=apps/api`, UTF-8을 사용한다. PostgreSQL 테스트는 별도의 테스트 DB에 매 테스트 전용 스키마를 만들고 제거한다.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='apps/api'
# TEST_DATABASE_URL은 별도 테스트 DB 연결 문자열로 설정
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q --tb=short
.\.venv\Scripts\python.exe -m ruff check apps/api
.\.venv\Scripts\python.exe -m mypy apps/api/app --ignore-missing-imports
git diff --check
```

검증 결과: 테스트 226개 통과(PostgreSQL 포함), Ruff 통과, Mypy 189개 소스 파일 통과. 새 회귀 검증은 OpenAPI 동일성, 모듈 공개 import 경계, service/router SQL 차단, Command 입력 및 반환 명시, mapper 외부 호출 차단, 접근 주체별 인가 차단, 중첩 트랜잭션 단일 commit/전체 rollback/무관한 기존 트랜잭션 거절을 포함한다. 기존 권한·발행 잠금·버전 동의·stale·결제·환불·통계 실패/재시도 테스트의 동작 검증은 유지했다.

## 남은 범위와 검증의 한계

- 실제 DB 세션/인증 dependency 훅, 로그인/OAuth, chat 스트리밍 조립, credit/구독/외부 결제 실행, moderation 신고·감사 처리, memory 쓰기/추출·임베딩 공급자 연결은 원래의 미구현 범위다. 이번 구조 정리에서 새 기능으로 구현하지 않았다.
- 실제 OpenAI/Anthropic 호출, 운영 인증 시스템, 운영 스케줄러·알림 배포, 운영 데이터 성능/부하 검증은 수행하지 않았다. LLM은 mock 기반으로 검증했다.
- Mypy는 위 명령의 기본 검사 범위이며 모든 내부 함수에 엄격한 타입 검사를 강제하는 설정은 아니다. AST 회귀 검증도 동적인 모든 호출·ORM lazy loading 가능성을 수학적으로 증명하지 않는다. 실제 경로 검토와 DB 테스트를 함께 사용했다.
- 확인 범위의 주요 경계 위반은 교정했지만, 기존 골격까지 포함한 프로젝트 전체의 기능 구현 완료 또는 모든 미래 호출에서의 완전 준수를 선언하지 않는다.
