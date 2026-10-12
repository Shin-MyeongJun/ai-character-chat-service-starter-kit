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
| identity.py | users 정규화 이메일/인증 상태, OAuth provider/sub, 인증 세션·일회용 토큰·OIDC state·DB 요청 제한. identity 서비스가 소유 |
| character.py, character_media.py | 원본 이미지/자산의 선택적 media_id. 캐릭터당 감정 태그 UNIQUE, 기본 이미지 부분 UNIQUE. 미디어 예약은 소유자/캐릭터 FK 없이 남음 |
| lorebook.py | title/token_budget nullable, metadata JSON, 1536차원 벡터. entry_type에 start_set 포함 |
| product.py | 편집 구성 링크·선택 대상·원본 시작 항목. 복합 FK로 같은 상품에 속한 링크만 연결 |
| tag.py | 공용 tags 사전과 작품·캐릭터·로어북의 공개/내부 연결 6개. 정확한 이름 UNIQUE, 대상 CASCADE·사전 RESTRICT·부여 사용자 SET NULL FK. tags는 content/tag, 각 연결은 해당 콘텐츠 모듈 소유. normalized_name·kind·태그 snapshot·개수 제한 없음 |
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
| 0020 | 이메일 정규화 사전 충돌 검사, 인증 상태·대기 만료, 인증 세션/증명/OIDC/제한 테이블. 초기 SQL 011과 대응 |

초기 SQL 004는 0002–0014의 누적 변경을 포함한다. 007/008/009/010은 각각 0015/0017/0018/0019 대응이다. SQL 원문과 Python의 SQL 문자열은 이번에 변경하지 않았다. 생성 형태의 고정 DDL 설명은 이 문서에 모았다.

대부분 초기 revision의 downgrade는 명시적으로 오류를 낸다. 0015–0018은 추가 구조를 제거하는 코드가 있고, 0019는 관리 미디어 행이 존재하면 downgrade를 거절한다. 어느 경우도 이번 점검에서 운영 DB에 실행하지 않았다.

`test_product_migrations`는 열 이름/타입/nullable·FK·UNIQUE를 비교하고 legacy 대화/메시지를 확인한다. CHECK 전체·일반 인덱스·서버 기본값까지 완전히 동일함을 보장하는 비교는 아니다. `test_media_migrations`는 기존 URL과 downgrade 가드를 확인한다.

## 작업 실행과 장애 후 재개

태그 스키마의 기존 revision `0028` 및 고정 SQL은 유지한다. `0029`는 kind/tag_kind를 제거하고 이름 UNIQUE·단일 사전 FK로 전환하며 캐릭터·로어북의 공개/내부 연결을 추가한다. 종류 간 동일 이름이 있으면 ID·설명·연결을 임의 병합하지 않고 upgrade를 거절한다. 이름/연결 정리 후 재시도한다. 태그 데이터가 있으면 종류를 재구성할 수 없어 downgrade를 거절한다. `alembic/sql/0029_content_tags.sql`은 신규 4개 연결의 고정 DDL이며 새 DB 초기 SQL `019_tags.sql`은 현재 7개 테이블을 생성한다. 기존 DB에 자동 실행하지 않는다. 현재 태그 API는 콘텐츠/tag 및 각 콘텐츠 service와 governance/admin/tag_router.py에서 제공하며 [태그 관리](../../../../references_document/reference/content-tags.md)에 정리했다. 유저/작가 태그는 추가하지 않았다.

| 진입점 | 실행 단위 | 재개 경계 |
| --- | --- | --- |
| main의 답변 supervisor | 15초 주기로 만료 답변 조회 | 저장 결과가 있으면 완료 저장, 없으면 preparing/calling 단계별 중단 실패. legacy lease 없음은 제외 |
| app.memory_worker | 대화별 memory job; 제한된 동시성 | lease 만료 재claim, pending 색인 먼저, 오류별 backoff. 주기 lease 갱신은 없음 |
| product.statistics_job | limit만큼 dirty day 처리 후 종료 | 집계/저장 실패 시 트랜잭션 롤백으로 큐 유지. --repair-recent는 최근 날짜 재요청 |
| app.media_cleanup | 사용자가 지정한 media ID별 처리 | deleting을 먼저 저장하고 외부 삭제 후 deleted. 참조 또는 보존 기간 안이면 삭제하지 않음 |

`memory_worker --once`는 한 건 처리 옵션이 아니다. 현재 claim 가능한 작업과 실행 중 작업이 없어지면 종료하므로 미래 backoff 작업은 남을 수 있다. statistics_job은 스케줄러를 등록하지 않는다. docker-compose.yml은 PostgreSQL/Redis만 정의하며 API·워커·통계/정리 일정은 별도 실행 환경에 달려 있다. 현재 backend 코드에서 Redis 작업 큐 사용은 확인되지 않았다.


## 고정 시작 내용 migration (2026-09-27)

0025 / 초기 SQL 016은 conversations.opening_mode를 추가한다. 기존 행과 server default는 legacy_messages, 신규 conversation 서비스는 snapshot을 명시한다. 메시지를 삭제/추정/합성하지 않는다. 최초 initial_snapshot_id/start_set_id를 읽고 현재 버전 변경과 분리한다. snapshot 대화가 있으면 downgrade를 거절한다. test_product_migrations와 test_credit_wallet_migrations는 head/초기 SQL/ORM 경로를 비교하고 test_conversation_opening은 downgrade 손실 방지를 검증한다.

## Moderation review migration (2026-10-14)

0027 (`down_revision=0026`) / 초기 SQL 018은 reports, assessments,
assessment_reports, actions를 추가한다. 고정 SQL은 alembic/sql/0027_moderation_review.sql에
있고 초기 SQL과 동일하다. moderation_review.py가 ORM 정의와 모델 등록을 담당한다.
기존 moderation_flags/audit_logs는 보존하며 flags를 같은 ID/request_key의 reports로
한 번 복사한다. 원래 검토 메타데이터는 legacy provenance JSON으로 보존하고 위반
평가를 추정하지 않는다. 신규 데이터가 존재하면 downgrade는 손실 방지를 위해 거절한다.
상세 이관·서비스 경계는 moderation/ARCHITECTURE.md를 따른다.
