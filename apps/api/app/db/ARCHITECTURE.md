# DB와 작업 실행 코드 읽기

이 문서는 현재 SQLAlchemy 모델·repository·마이그레이션을 연결해서 읽기 위한 안내다. 테이블이나 실행 로직은 변경하지 않았다. [전체 점검 목록](../../../../references_document/backend_review/checklist.md)과 [발견 사항](../../../../references_document/backend_review/findings.md)을 함께 본다.

## 트랜잭션과 잠금

1. `transaction.use_case_transaction`은 자신의 session.info 표식이 있으면 같은 범위에 참여한다. 안쪽 예외는 failed를 남겨 바깥에서 잡더라도 최외곽 종료 때 전체 롤백한다. savepoint가 아니다.
2. 표식 없는 기존 autobegin 트랜잭션은 자동으로 채택하지 않는다. 첫 use_case_transaction은 `session.begin()`을 호출하므로 이미 시작된 세션이면 오류가 난다. 조회 후 Command 조합을 할 때 이 차이를 확인한다.
3. `idempotency.lock_key`는 namespace:key 해시의 64비트 signed 정수로 `pg_advisory_xact_lock`을 요청한다. 행이 없어도 키별 실행을 직렬화한다. 충돌 내용 판정과 이전 결과 재사용은 각 서비스의 책임이다.
4. chat의 메시지/생성 변경은 conversation 행 잠금을 공유한다. 생성 완료는 conversation → generation 순서다. 상품 발행은 product → 정렬된 character → 정렬된 lorebook 순서다.
5. product.repository.core의 일반 `get_product(lock=True)`는 FOR SHARE, `get_owned_product(lock=True)`는 FOR UPDATE다. lock 인자 이름만으로 동일 잠금이라고 읽지 않는다.
6. memory 작업과 상품 통계 큐는 SKIP LOCKED를 사용한다. 잠금을 건 채 외부 호출을 지속하는지 여부는 호출 흐름마다 다르다. 답변/기억 유스케이스는 외부 호출 전 읽기 세션을 닫지만 character 미디어 저장은 잠금을 유지한 채 저장 완료를 기다린다.

관련 테스트: `test_use_case_transaction`, `test_product_usage`, `test_nonstream_answers`, `test_hypha_memory`, `test_product_statistics`, `test_character_media`.

## 모델의 관계와 제약

| 모델 파일 | 읽어야 할 연결 |
| --- | --- |
| identity.py | users role/status, OAuth 연결 스키마. 현재 런타임 인증 구현과 별개 |
| character.py, character_media.py | 원본 이미지/자산의 선택적 media_id. 캐릭터당 감정 태그 UNIQUE, 기본 이미지 부분 UNIQUE. 미디어 예약은 소유자/캐릭터 FK 없이 남음 |
| lorebook.py | title/token_budget nullable, metadata JSON, 1536차원 벡터. entry_type에 start_set 포함 |
| product.py | 편집 구성 링크·선택 대상·원본 시작 항목. 복합 FK로 같은 상품에 속한 링크만 연결 |
| snapshot/ | 원본별 version과 JSON schema version 구분. 원본 삭제 시 SET NULL, 참조된 구성요소 스냅샷은 RESTRICT |
| chat.py | 현재 버전과 최초 버전 분리, 시작 FK는 최초 버전. 메시지 position은 전역 identity, revision은 메시지 변경 번호 |
| product_usage.py | 사용자별 요청 키 UNIQUE, 생성-버전 복합 FK, answer metadata/lease, 매출/환불 귀속 |
| memory.py | 원문 범위·revision·prompt 버전 UNIQUE, ready 벡터 조건, 대화당 작업 하나와 요청/처리 세대 |
| billing.py | generation별 usage UNIQUE. 기존 nullable 참조·0 사용량과 실제 과금 부재를 구분 |
| product_release.py | media 변경만 automatic 허용, 노트 정정 전 이력 |
| product_statistics.py | 서울 날짜별 결과, 기간 사용자 중복 제거용 행, dirty-day 큐 |
| model_routing.py | 모델명과 DB ID, 활성 provider/model, 종료 공지와 대체 조합 UNIQUE |
| moderation.py | 신고·감사 스키마 존재와 현재 service 미사용 구분 |

`_mixins.UuidPkMixin`의 ID는 DB 기본값이다. `TimestampMixin.updated_at`의 onupdate는 SQLAlchemy가 UPDATE할 때 붙이는 값으로 DB 전체 UPDATE 트리거가 아니다. 스냅샷 payload는 서비스에서 새 발행으로 보존하지만 DB에 UPDATE 방지 트리거를 설치하지 않는다.

`pagination.fetch_cursor_page`는 호출자가 이미 지정한 조회 범위에 (created_at, id) 내림차순 커서를 추가하고 limit+1개를 읽는다. chat의 메시지 position 오름차순 커서는 별도 구현이다. 페이지를 나누어 읽는 동안 전체 결과가 고정되는 스냅샷 보장은 없다.

## 스키마를 만드는 두 경로

- Alembic: `apps/api/alembic/env.py` → `versions/0001_baseline.py`의 고정 SQL → 연결된 revision 순서. `down_revision`이 실제 연결이며 번호 사이 0009가 없는 것은 체인 단절이 아니다.
- 새 PostgreSQL 초기화: `infra/postgres/init/*.sql`을 파일명 순으로 실행한다. compose가 이 디렉터리를 초기화 경로에 mount한다. 기존 DB를 시작할 때마다 업그레이드하는 앱 로직은 없다.
- 두 경로를 같은 기존 DB에 무조건 겹쳐 실행하지 않는다. `create_all`은 테스트 fixture가 현재 ORM 스키마를 만드는 경로이며 운영 migration 대체가 아니다.

| revision | 변경 연결 |
| --- | --- |
| 0001 | 고정 baseline. 초기 SQL 001/002/003과 대응하는 초기 테이블 구조 |
| 0002–0004 | 선택 캐릭터 대상 로어, start_set 유형, 모델/대체 설정과 원본 시작 링크 |
| 0005–0007 | 캐릭터 스냅샷 미디어, 상품 발행 구성/시작 항목, 릴리스 노트 |
| 0008 → 0010 | 대화/메시지의 발행 버전, 최초 버전으로 시작 FK 변경, 전환 이력 |
| 0011–0012a | 만료 정책 이력, 모델 종료·대체 이력, 기억 원본 메시지 출처 |
| 0013–0014 | 생성·결제 귀속·usage 연결, 통계와 dirty-day 초기 채움 |
| 0015 | 메시지 identity position/revision, 기존 메시지 순서 채움, 재요청 영수증 |
| 0016 | 기억 임베딩 provider/model 식별. 초기 SQL 002에는 이미 포함 |
| 0017 | 기억 요약 출처·색인 상태·작업 큐, conversation history_revision |
| 0018 | 답변 metadata/복구 lease |
| 0019 | 관리 미디어 예약과 원본/발행 미디어 참조; 기존 URL 유지 |

초기 SQL 004는 0002–0014의 누적 변경을 포함한다. 007/008/009/010은 각각 0015/0017/0018/0019 대응이다. SQL 원문과 Python의 SQL 문자열은 이번에 변경하지 않았다. 생성 형태의 고정 DDL 설명은 이 문서에 모았다.

대부분 초기 revision의 downgrade는 명시적으로 오류를 낸다. 0015–0018은 추가 구조를 제거하는 코드가 있고, 0019는 관리 미디어 행이 존재하면 downgrade를 거절한다. 어느 경우도 이번 점검에서 운영 DB에 실행하지 않았다.

`test_product_migrations`는 열 이름/타입/nullable·FK·UNIQUE를 비교하고 legacy 대화/메시지를 확인한다. CHECK 전체·일반 인덱스·서버 기본값까지 완전히 동일함을 보장하는 비교는 아니다. `test_media_migrations`는 기존 URL과 downgrade 가드를 확인한다.

## 작업 실행과 장애 후 재개

| 진입점 | 실행 단위 | 재개 경계 |
| --- | --- | --- |
| main의 답변 supervisor | 15초 주기로 만료 답변 조회 | 저장 결과가 있으면 완료 저장, 없으면 preparing/calling 단계별 중단 실패. legacy lease 없음은 제외 |
| app.memory_worker | 대화별 memory job; 제한된 동시성 | lease 만료 재claim, pending 색인 먼저, 오류별 backoff. 주기 lease 갱신은 없음 |
| product.statistics_job | limit만큼 dirty day 처리 후 종료 | 집계/저장 실패 시 트랜잭션 롤백으로 큐 유지. --repair-recent는 최근 날짜 재요청 |
| app.media_cleanup | 사용자가 지정한 media ID별 처리 | deleting을 먼저 저장하고 외부 삭제 후 deleted. 참조 또는 보존 기간 안이면 삭제하지 않음 |

`memory_worker --once`는 한 건 처리 옵션이 아니다. 현재 claim 가능한 작업과 실행 중 작업이 없어지면 종료하므로 미래 backoff 작업은 남을 수 있다. statistics_job은 스케줄러를 등록하지 않는다. docker-compose.yml은 PostgreSQL/Redis만 정의하며 API·워커·통계/정리 일정은 별도 실행 환경에 달려 있다. 현재 backend 코드에서 Redis 작업 큐 사용은 확인되지 않았다.
