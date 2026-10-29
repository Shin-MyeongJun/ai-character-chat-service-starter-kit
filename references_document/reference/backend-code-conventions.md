# 백엔드 코드 작성 규칙

이 문서는 [모듈 아키텍처·명명 규칙](module-architecture-and-naming.md)을 보완한다.
router/service/repository/mapper/types, Command/Info/View 및 현재 모듈 소유권을 유지한다.
필수는 신규·변경 코드의 완료 조건, 기본은 이유가 있을 때 달리할 수 있는 선택이다.
기존 외부 HTTP/Python 호출·DB·저장 JSON 계약은 이름 정리만으로 바꾸지 않는다.

## 1. 이름과 역할 — 필수

같은 역할은 같은 용어로 표현하고, 자료형이 같아도 역할이 다르면 구분한다.

| 의미 | 이름/형태 |
|---|---|
| 현재 DB 세션 | `session` |
| 인자 없이 호출해 비동기 세션 범위를 여는 의존성 | `session_factory`, `app.db.types.SessionFactory` |
| 업무 요청 | `command`; HTTP 요청 객체는 `request` |
| 공급자 원시 응답 | `provider_response`; HTTP 응답은 `response` |
| 여러 객체가 함께 존재하는 처리 | `product_entity`, `product_row`, `product_info`, `product_view` 등 역할 명시 |
| 단순 함수에서 유일한 값 | `entity`, `row`, `info`, `item` 허용 |
| 목록 / ID 목록 / 사전 | `products`, `product_ids`, `products_by_id`, `tags_by_name` |
| 단위 | `timeout_seconds`, `elapsed_ms`, `size_bytes`, `estimated_tokens`, `attempt_count` |
| 상태/가능 여부 | `is_active`, `has_more`, `can_retry` 등 의미 명시 |

- `user_id`/`actor_id`/`owner_id`, `worker_id`/`claim_token`은 합치지 않는다. 요청자·소유자·프로세스·개별 실행의 의미를 구별한다.
- `revision`, `version`, `digest`는 필요하면 `history_revision`, `document_version`, `content_digest`처럼 대상을 붙인다. 기존 저장값과 계산 규칙은 보존한다.
- `data`, `value`, `result`는 작은 범위에서 의미가 명확할 때만 사용한다. 한 함수에서 여러 업무 단계를 같은 이름에 덮어쓰지 않는다.
- 함수 인자 이름 변경은 키워드 호출도 검색한다. `self.sessions`처럼 기존 호출자가 있는 속성은 호환 조사 없이 바꾸지 않고 예외로 기록한다.
- import 별칭과 파일·함수·클래스 이름은 상위 아키텍처 문서를 따른다.

## 2. 타입 — 필수

- 공개·내부 명명 함수와 메서드의 매개변수 및 반환을 명시한다. `self`/`cls`는 생략하고 생성자는 `-> None`을 쓴다. async 함수에는 await 후 결과 타입을 쓴다.
- 지역 변수는 추론이 명확하면 생략한다. 빈 컨테이너와 여러 구조가 섞이는 값은 필요할 때 명시한다.
- bare `Callable`, `dict`, `list`, `tuple`, `set` 등 대신 실제 인자/요소/반환 타입을 쓴다. `Callable`을 `Any`로 바꾸어 우회하지 않는다.
- `session: AsyncSession`과 `session_factory: SessionFactory`를 구분한다. 세션 팩토리는 async 함수 자체가 아니라 호출 후 `async with`로 여는 의존성이다.
- `Any`는 외부 SDK/동적 JSON 경계 등 필요한 위치에 한정한다. `cast`·`type: ignore`에는 타입 검사기가 표현하지 못한 실제 근거를 남긴다. 검사 통과만을 위해 추가하지 않는다.
- 타입 힌트는 실행 시 입력 검증을 대체하지 않는다. 타입 보완 중 발견한 실제 오류는 별도 동작 변경으로 다룬다.
- ORM 타입은 repository/mapper 안에서만 사용한다. DB 실행 의존성 타입은 DB 기반 코드에 두며 업무 types에 ORM을 끌어들이지 않는다.

## 3. 데이터 표현과 호출 — 기본

| 대상 | 기본 표현 |
|---|---|
| HTTP 입출력 | 기존 schemas 검증 모델 |
| 업무 요청/결과 | 기존 Command/Info/View dataclass |
| 고정 JSON 구조 | TypedDict 등으로 키/값 표현 + 별도 실행 시 검증 |
| 반복 사용되는 여러 의미의 결과 | 이름 있는 내부 결과 타입 |
| 단순하고 자연스러운 쌍 | 명시된 tuple 허용 |
| 제한된 상태 | 도메인에서 쓰는 Literal/enum 유지, 저장 문자열 불변 |
| 자유로운 metadata | 값 범위를 표현하고 경계에서 검증 |

- 여러 ID나 옵션을 받는 Command는 키워드로 생성한다. 공개 dataclass를 무조건 `kw_only=True`로 바꾸지는 않는다.
- `None`, 필드 누락, 빈 문자열/빈 목록의 의미를 구분한다. 부분 수정의 유지/해제/전체 제거를 임의로 합치지 않는다.
- `frozen=True`는 중첩 가변 데이터를 불변으로 만들지 않는다. 공유·복사의 책임을 명시한다. scalar의 불필요한 deepcopy는 피하되 JSON 격리는 보존한다.
- slots/enum/tuple 전환도 직렬화·호출·상속 계약에 영향을 줄 수 있다. 단순 포맷 변경과 분리한다.

## 4. 함수·클래스와 표현 — 기본

- 순수 계산/검증/mapper 및 세션을 받는 단일 업무는 함수로 작성할 수 있다.
- 같은 의존성이나 자원 수명을 보관할 때 클래스를 사용한다. 묶기 위한 static 클래스나 범용 BaseService를 만들지 않는다.
- 공유 서비스 객체에는 요청별 현재 사용자/command/세션을 저장하지 않는다.
- 긴 표현식은 이름 있는 단계로 나눈다. 파일/함수 줄 수보다 책임·변경 이유·추적 비용을 기준으로 분리한다.
- 의미 있는 공통 정책만 추출한다. 비슷한 도메인을 거대한 옵션 함수나 공통 repository로 합치지 않는다.
- 공통 포맷은 Ruff이며 구문 기준은 패키지 최소 버전 3.11이다. 타입 검사는 .python-version/API Docker의 3.12 환경에 맞춘다(설치된 NumPy stub도 3.12 구문을 사용). 전체 포맷 변경은 동작 수정과 분리한다.

## 5. 검증·오류·저장 — 필수

- schemas는 형식, service는 권한/존재/상태/업무 규칙, repository/DB는 저장과 제약, mapper는 순수 변환을 소유한다.
- trim/대소문자/기본값 정책은 대상별로 정의한다. 비밀번호·사용자 원문을 일반 문자열처럼 일괄 정규화하지 않는다.
- repository 미존재는 기본 None, 목록은 빈 결과다. service의 선택 조회/필수 조회 및 삭제 성공의 의미를 명시한다.
- 입력/업무 충돌/권한/일시 공급자 실패/영구 실패/내부 오류/취소/commit 불확실성을 구분한다. HTTP 번역은 HTTP 경계에서 수행한다.
- 예상 제약만 업무 오류로 변환한다. 오류 메시지 문자열로 분기하거나 예외를 빈 결과로 숨기지 않는다. 넓은 catch는 복구·정리 이유가 있어야 한다.
- 트랜잭션 소유자, 잠금 순서, 재시도·멱등성 계약을 보존한다. 잠금/예외/쿼리 변경은 이름·타입 정리와 별도 검증한다.
- 이미 검증한 상태를 재사용하려고 범용 `skip_validation` 우회 옵션을 만들지 않는다.

## 6. 자원·시간·조회 — 필수

- 자원을 만든 쪽이 정리하고 반환으로 소유권을 넘기면 문서화한다. 세션·스트림·클라이언트·태스크에 적용한다.
- 같은 AsyncSession을 병렬 태스크에 공유하지 않는다. 취소와 공급자 스레드 종료는 다르며 늦게 반환되는 자원도 회수한다.
- 요청 timeout, 전체 deadline, lease는 별개다. 기존 종료 대기/잠금을 제거하려면 대체 보장을 먼저 설계한다.
- 동기 파일/해싱/SDK 작업의 실행 위치를 확인한다. 무제한 병렬 처리와 미회수 태스크를 만들지 않는다.
- 시각 비교·저장은 aware UTC를 기본으로 하며 경과 시간은 단조 시계를 사용한다. 테스트에서 필요한 시각은 주입하거나 명시적으로 전달한다.
- 바이트/문자/추정 토큰/실측 usage를 구분하고 금액·크레딧의 기존 정밀도를 유지한다.
- 페이지 정렬·보조 키·커서·인가 범위를 명시한다. 전체 수집과 정확한 총 개수 계산의 비용을 숨기지 않는다.

## 7. 문서·로그 — 기본

- 주석은 잠금 순서·복구 이유·불변 조건을 설명한다. 책임/공개 계약 변경은 해당 ARCHITECTURE.md와 함께 갱신한다.
- 로그에는 요청/작업/실행 식별과 오류 종류·횟수를 남기되 비밀·원문을 무분별하게 기록하지 않는다. 중복 로그를 줄인다.
- 기준 규칙을 여러 문서에 복사하지 않는다. AGENTS.md는 이 문서와 상위 아키텍처 문서로 연결한다.

## 8. 자동 검사와 점진 적용

저장소 루트에서 프로젝트 가상환경 Python으로 실행한다.

```powershell
.venv/Scripts/python.exe tools/check_backend_quality.py
.venv/Scripts/python.exe tools/check_backend_patterns.py --inventory
```

- 전체 `apps/api/app`의 함수 입력/반환 누락, bare generic, 직접 Any 표기를 진단한다. 기존 진단은 `tools/backend-pattern-baseline.json`에 경로/심볼/규칙 단위로 보존하고 새 진단은 실패시킨다.
- 해결한 진단은 `--prune-baseline`으로 제거한다. 새 진단이 있으면 prune도 실패한다. 기준선을 재생성해 새 위반을 숨기지 않는다.
- 이름의 업무 의미, JSON 검증, 잠금 안전성을 이 검사만으로 보장하지 않는다. 타입 검사/아키텍처 검사/업무 테스트를 함께 사용한다.
- 단계별 엄격 검사 대상은 `tools/backend-quality-scope.json`에 기록한다. 이 범위에는 포맷·린트·타입 검사를 적용한다. 의존 모듈은 mypy가 읽되 해당 모듈의 오류는 이 단계에서 출력하지 않는다(`follow_imports = silent`; skip이 아님).
- 기준 사례: tag 사전의 query/command/repository/mapper, chat의 기억 workflow, DB 세션 팩토리. 독립 업무 검증과 기존 잠금/재시도 정책을 유지한다.
- 테스트는 관찰 가능한 결과와 계약을 검증한다. 내부 함수 배치·구현 문법에 불필요하게 종속시키지 않는다.
- 패턴 통일은 표현 → 내부 타입 계약 → 실행 의미 순으로 진행한다. 실행 의미 변경은 감사 U항목의 수정/회귀 검증과 묶는다.

## 9. 현재 호환 예외

- 기존 미주석/bare/Any 시그니처는 기준선의 각 항목으로 한정한다. 정리한 심볼에는 새 예외를 추가하지 않는다.
- 기존 `AnswerOrchestrator.sessions`, `CharacterMediaService.sessions`, `ProductMediaService.sessions`, `AuthenticationService.sessions`와 기존 생성자 `sessions`는 호출/테스트 호환을 보존한다. 타입은 공통 세션 팩토리로 표현하되 이름 변경은 호출부 조사 후 진행한다.
- 기존 DB/HTTP/저장 JSON 이름, 오류 상태, 위치 인자 지원, 호출자가 사용하는 반환 형태는 이 단계에서 유지한다.
- 기반 규칙 도입은 감사 결함 수정 완료를 의미하지 않는다. 실제 진행 상태와 검증 한계는 `docs/audits/2026-10-26-pattern-standardization/REPORT.md`에 기록한다.
