# 상품 개발·검증 실행 메모

진행 상태와 미완료 항목은 [작업 계획](product-implementation-plan.md)을 기준으로 한다.

## Schema·type·mapper 경계

기존 character/lorebook과 동일하게 HTTP 입출력은 `schemas.py`의 Pydantic DTO,
서비스 명령·조회·결과는 `types.py`의 dataclass로 분리한다. schemas와 types는
서로 import하지 않는다. `ProductSchemaMapper`, `ConversationSchemaMapper`,
`AdminSchemaMapper`가 요청/조회 DTO를 application type으로, 서비스 결과를
응답 DTO로 변환한다. ORM 결과 변환은 `mapper/persistence.py`에서 수행한다.

상품 설정 타입은 `product.types.Settings`, 발행 명령은 `product.types.ReleasePublish`,
발행 결과는 `product.types.ReleaseInfo`를 사용한다. 서비스 파일에서 타입을
가져오지 않는다. 서비스가 HTTP 요청 DTO를 직접 받거나 application dataclass를
FastAPI request/response_model로 등록하지 않는다.

상품 소개·업데이트 안내·통계, 대화 생성/버전 전환/생성 예약, LLM 실행 및
종료 안내 결과는 dataclass다. 내부 호출자는 `result.created`, `result.totals`,
`context.execution`처럼 속성으로 접근한다. GenerationResult와 GeneratedMessage는
`conversation.types`에서 import한다. HTTP 응답은 mapper가 UUID·날짜·중첩 결과를
직렬화 가능한 DTO로 변환한다. 내부 스냅샷 JSON 및 집계 계산용 딕셔너리는
HTTP 응답 타입으로 사용하지 않는다.

`test_product_boundaries.py`는 HTTP DTO의 중첩 변환, 미허용 필드 거부, 신뢰한
사용자 ID 전달, 조회 파라미터 검증, 응답 직렬화와 계층 간 import 방향을 검증한다.

## 테스트

프로젝트 루트 PowerShell에서 실행한다.

```powershell
$env:PYTHONPATH = (Resolve-Path apps/api).Path
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
```

PostgreSQL 통합 테스트는 `TEST_DATABASE_URL`이 없으면 skip한다. pgvector가
설치된 별도 테스트 DB를 준비하고 해당 환경 변수에 asyncpg URL을 설정한다.
DB 이름에는 `test`가 포함되어야 한다. 각 테스트는 고유한 `test_*` 스키마를
만들고 종료 시 해당 스키마만 삭제한다. 운영 DB URL을 사용하지 않는다.

## 마이그레이션

`DATABASE_URL`에 대상의 `postgresql+asyncpg://...` URL을 설정한다.

```powershell
.\.venv\Scripts\python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

빈 DB는 0001 baseline부터 적용한다. 이미 테이블이 있는 DB는 백업·스키마
비교·데이터 조사 후 기준 버전을 명시적으로 정해야 한다. 일부 테이블이
있다는 이유만으로 `stamp`하지 않는다. 새 대화 버전 FK는 nullable로 추가해
검증 불가능한 과거 기록을 그대로 보존하며, 자동 백필은 수행하지 않는다.

신규 Docker DB는 기존 001~003 초기화 SQL 다음 004를 실행한다. 초기화 SQL은
기존 볼륨에는 자동 재적용되지 않는다. 004는 Alembic 0001 이후 SQL에서
alembic_version 갱신만 제외한 파일이며 반복 실행용 스크립트가 아니다.

## 앱 연결

`app.http.routes.router`를 FastAPI 앱에 포함한다. 이 조립 지점은
소유자·관리자·모더레이터 경로를 함께 등록하고 고정 경로를 UUID 경로보다
먼저 배치한다. `product.dependencies.get_product_session`은 요청마다
독립 AsyncSession을 제공하고 `get_current_owner_id`는 인증된 사용자 ID를
반환해야 한다. 인증 조회와 쓰기 command가 같은 열린 트랜잭션을 공유하지
않도록 한다. 미설정 상태는 503으로 거부한다. 클라이언트 owner_id를 신뢰하지
않는다. 관리자 기능은 DB의 활성 admin 역할도 검사한다.

대화 생성은 `conversation.service.command.generation.begin_generation`으로 먼저 예약한다.
사용자별 request_key와 입력 해시가 같으면 기존 실행을 돌려준다. 반환값의
`created`가 false이면 제공사를 다시 호출하지 않는다. pending 실행의 대사와
프로세스 중단 복구는 실제 제공사 오케스트레이터에서 처리해야 한다.

`prepare_runtime_context(PrepareRuntimeContextCommand)`는 서버 내부용이며 HTTP로
반환하지 않는다. 이 쓰기 유스케이스가 트랜잭션을 소유하며 결과를 받은 뒤 `UUID(context.product_snapshot_id) == reservation.product_snapshot_id`인지
확인한다. 다르면 제공사를
호출하지 않고 예약을 cancelled로 마감한다. 실제 제공사 호출에는 예약에
고정된 model_id/model_name/reasoning_effort를 사용한다. 컨텍스트 조회에는
모델 대체 계획 기록이 포함될 수 있으므로 공통 use_case_transaction이 성공 시 커밋한다.
여러 Command를 조합할 때는 같은 공통 범위에 참여시킨다.

제공사 응답/실패/취소 후 `finish_generation`에 GenerationResult를 담은 FinishGenerationCommand를 전달한다.
메시지, 실제 토큰/비용, 종료 상태를 한 트랜잭션으로 저장한다. 같은 결과의
재전송은 중복 저장하지 않는다. 생성 도중 버전 전환/만료가 발생하면 stale로
기록하고 AI 메시지는 저장하지 않으며 발생한 비용은 보존한다. 제거된
append_generated_message 경로 대신 이 완료 인터페이스를 사용한다.

`billing.service.command.attribution.record_sale/record_refund`는 검증된 billing 내부 호출만
허용하는 계약이다. 공개 HTTP로 노출하지 않는다. 결제별 귀속 합계는 원결제
이하, 부분 환불 합계는 원귀속 이하로 제한하며 event_key로 중복을 막는다.
입력은 RecordSaleCommand/RecordRefundCommand이며 저장된 PaymentEventInfo를 반환한다.
한 결제의 여러 배분은 같은 결제 완료 시각을 전달한다. 실제 결제 실행과
크레딧 잔액 변경은 별도 billing 작업이다.

## 통계 실행

성공 턴은 저장 완료된 생성 실행 1회다. 여러 캐릭터 메시지 수와 구분한다.
실패/취소/stale의 실제 비용도 포함한다. 시각은 UTC로 저장하고 Asia/Seoul
일자를 집계한다. 기간 고유 사용자는 일별 활동에서 DISTINCT로 계산한다.
매출과 환불은 통화별 Decimal 문자열이며 늦은 환불도 원거래 일자를 갱신한다.

운영 스케줄러에서 다음 CLI를 시간별 실행하고, 매일 --repair-recent로 당일과
이전 7일을 재집계 대상으로 등록한다. 한 번에 최대 limit개 일자를 처리하므로
대기량이 크면 반복 실행한다. 실제 스케줄러 등록은 아직 하지 않았다.

```powershell
$env:PYTHONPATH = (Resolve-Path apps/api).Path
# DATABASE_URL은 배포 환경의 DB 연결 설정을 사용한다.
.\.venv\Scripts\python.exe -m app.modules.content.product.statistics_job --limit 100
.\.venv\Scripts\python.exe -m app.modules.content.product.statistics_job --repair-recent --limit 1000
```

이벤트와 재집계 큐 등록은 같은 트랜잭션이다. 작업자는 FOR UPDATE SKIP LOCKED로
일자를 가져오고 실패하면 큐를 보존한다. 기간 조회는 소유자 전용
GET /products/{product_id}/statistics?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD이며
snapshot_id로 버전을 필터링한다. pending_days가 있으면 해당 날짜는 아직
최신 이벤트를 반영하지 않은 상태다. 분석 데이터 자동 삭제는 구현하지 않았다.

LLM 종료 안내는 상품 소개/대화 업데이트 조회의 model_notice 및 제작자 전용
GET /products/{product_id}/releases/{snapshot_id}/availability로 읽는다. 조회는
대체 실행을 발생시키지 않는다. 제공사 공지 수집·정기 준비 작업·alarm 전달은
별도 연결해야 한다.

## 파일 보존

이미지·에셋의 URL은 불변 저장소 객체를 가리켜야 한다. DB에서 URL 문자열을
복사하는 것만으로 실제 파일의 덮어쓰기/삭제를 방지할 수는 없다. 저장소
연동 시 `media_is_referenced` 검사 및 참조 보존 정책을 적용해야 한다.
