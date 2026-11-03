# Tag 사전 영역

## Gemini 검토 후 관리자 변경 교착 방지 (2026-11-03)

관리자 update/deactivate는 인가 후 행 잠금 전에 `LOCK TABLE tags IN EXCLUSIVE MODE NOWAIT`를
획득해 최상위 트랜잭션 종료까지 유지한다. resolve/create의 INSERT가 보유하는 ROW EXCLUSIVE와
FOR SHARE의 ROW SHARE 모두와 충돌하며 일반 SELECT는 허용한다. 기존 beta 잠금과 신규 alpha
UNIQUE 대기가 순환하던 경로에서 관리자가 잠금을 기다리지 않고 업무 충돌로 전체 rollback한다.
상위 트랜잭션이 이미 태그 행/쓰기 잠금을 가진 경우와 500개 경계도 같은 fencing에 포함된다.
단순한 이름순 정렬, 대기하는 advisory/table lock 또는 실패한 트랜잭션 재시도로 해결하지 않는다.

55P03만 기존 ValueError HTTP 경계의 `Tag dictionary is busy; retry the request.`(422)로
변환한다. 상위가 이를 잡아도 use_case_transaction의 rollback-only로 전체 쓰기를 취소한다.
자동 재시도·savepoint·내부 commit·외부 부작용은 없다. UNIQUE 23505는 기존 이름 충돌이다.
관리자가 먼저 fence를 확보하면 resolve/create는 기존 DB 대기 후 변경 결과를 다시 읽는다.
resolve/create끼리는 테이블 배타 잠금 없이 기존 INSERT/SHARE·정렬·500개 배치를 유지한다.
trim/정확한 이름/반환 순서·기존 메타데이터·비활성/retained_ids 정책도 유지한다.

이 선택은 드문 관리자 변경에 넓은 충돌 범위를 허용한다. 무관한 태그 writer가 있어도
관리자 변경은 즉시 충돌할 수 있고, 관리자 최상위 트랜잭션이 길면 사전 writer가 기다린다.
임의 순서로 상위에서 조합한 모든 잠금의 교착 부재를 보장하지는 않는다. 아래 날짜별
전역 잠금 없음/관리자 대기 설명은 이전 구현 이력이며 현재 정책은 이 절을 따른다.
test_tag_admin_locking_db는 독립 연결/장벽으로 이전 40P01 대조군과 새 업무 충돌,
2/501개·단건 create 후 resolve·상위 선행 잠금/쓰기 및 caught-error 전체 rollback을 검증한다.

## IEA-02 조합 전체 이름 선획득 (2026-11-03)

공개 `service/command.acquire_tag_names(AcquireTagNamesCommand)`는 상위 조합이 필요로
하는 전체 이름 집합을 기존 repository.resolve_tags의 정확한 이름순 INSERT/SHARE로
획득한다. 호출자는 콘텐츠 인가와 상위 트랜잭션을 소유하며 구성요소별 사전 획득 전에
한 번 호출한다. 반환은 None이며 연결·retained_ids·비활성 허용을 결정하지 않는다.
비활성 이름도 fencing만 수행하고 실제 연결은 각 부모 잠금 아래 얻은 retained_ids로
기존 resolve_tags를 반드시 통과한다. 다른 부모의 기존 연결 ID를 공유하지 않는다.

trim/중복 제거·정확한 이름·500개 배치·관리자 변경 fencing은 기존 저장소를 재사용한다.
누락 이름은 기존 동시 이름 변경 오류이며 실패·취소는 상위 전체 트랜잭션을 rollback한다.
전역 배타 잠금·재시도·사전 결과 캐시나 검증 생략 옵션은 추가하지 않는다. 이 순서 보장은
전체 이름을 선획득하는 studio 발행 조합의 범위이며 임의의 모든 writer 교착 부재 보장은 아니다.

`tags`를 소유한다. 정확한 이름 UNIQUE이며 이름의 앞뒤 공백만 제거한다. 내부 공백·대소문자·유니코드 표기·동의어는 통합하지 않는다. normalized_name·kind·개수 제한·태그 snapshot은 없다.

## U25 태그 이름 resolve 배치화 (2026-10-30)

공개 service/command.resolve_tags의 Command·TagInfo tuple과 정규화·반환 순서는 유지한다.
repository.resolve_tags는 정확한 이름을 중복 제거·Python 이름순 정렬한 뒤 최대 500개씩
INSERT ON CONFLICT DO NOTHING과 SELECT FOR SHARE로 처리한다. 잠금 SELECT의 ORDER BY
CASE는 VALUES와 같은 이름 순번을 사용하므로 DB collation에 순서를 맡기지 않는다.
populate_existing으로 identity map의 이전 이름/활성 상태를 갱신한다. SQL 한 쌍의 바인딩은
INSERT 최대 500개, SELECT 최대 1,500개다. 입력/결과 전체의 메모리는 여전히 이름 수에 비례한다.

service는 모든 raw Entity를 mapper로 먼저 변환한 뒤 이름별 Info를 해석한다. 정렬된 이름 중
누락이 있으면 기존 동시 이름 변경 재시도 오류를, 허용된 retained_ids에 없는 비활성 ID는
기존 신규 연결 거절 오류를 낸다. 반환은 trim 후 중복을 제거한 원래 입력 순서다. 부모 잠금
아래 읽은 기존 연결 ID만 신뢰하는 정책과 설명/활성 상태/기존 ID의 보존은 같다.
관리자 create_tag가 쓰는 단건 repository.resolve_tag와 관리자 인가·변경 정책은 유지한다.

하나의 use_case_transaction에 모든 배치와 콘텐츠 연결이 참여한다. 저장소는 commit/
rollback/savepoint를 추가하지 않고 같은 AsyncSession을 순차 실행한다. 중간 실패·취소나
상위 실패는 전체를 rollback하며, 내부 실패를 상위가 잡아도 rollback-only 상태를 유지한다.

기존 이름별 INSERT→SHARE의 교차 실행은 배치별 INSERT→SHARE로 바뀐다. 각 단계의 이름
정렬과 공유 잠금 모드는 유지하지만 모든 잠금 획득 시점이 이전과 같다는 뜻은 아니다.
동시 관리자 이름 변경·생성·비활성화와 겹치는 resolve의 실제 PostgreSQL 대기/경합은
후속 `test_u25_postgres_concurrency.py`로 검증했다. INSERT 전 이름 변경과 INSERT/SELECT
사이 변경의 서로 다른 결과, 비활성 신규 거절/retained 유지, 500개 경계와 대기 중 취소의
전체 rollback도 확인한다. 한 PG 버전·collation·READ COMMITTED의 지정 순서 검증이며
모든 교착 부재를 증명하지 않는다. 새로운 advisory lock·격리 수준·범용 재시도 정책은 없다.

test_tag_resolve_batch_contracts의 실제 SQLite SQL 검증기에서 1,001개 이름의 INSERT/SELECT가
각 1,001회에서 3회로 줄었다. PostgreSQL SQL 컴파일로 FOR SHARE·CASE 순서·바인딩 상한을
검사했으며 실제 PG 잠금/격리를 검증한 것은 아니다. 상세 측정·회귀·통합 명령은 감사 기록의
U25-TAG-WORKLOG.md에 남긴다. 세 콘텐츠 도메인의 태그 정책 공통화(U16)는 이 범위가 아니다.
2026-11-02 실제 PG 후속 결과와 통계/전체 API 통합·한계는 감사 기록의
U25-PG-INTEGRATION.md를 따른다. 이 후속 검증에서는 제품 코드·공개 계약을 바꾸지 않았다.

## 공개 서비스와 저장 책임

이 모듈의 사전 CRUD는 백엔드 작성 규칙의 첫 기준 사례다. session은 AsyncSession,
repository 결과는 Tag/None, mapper는 overload로 미존재와 존재를 구분하고 공개 결과는
기존 TagInfo다. `tags_by_name`은 이름별 해결 결과를 보관한다. 입력 정규화·인가·이름순
잠금·반환 순서·기존 오류 의미는 바꾸지 않는다. UPDATE 결과의 비어 있지 않음은 같은
트랜잭션의 선행 FOR UPDATE로 확보하며 해당 service의 cast에 근거를 기록한다.

- `service/query.py`: GetTagCommand/GetTagByNameCommand/GetTagsCommand 기반 단건·정확한 이름·ID 묶음 조회. HTTP에 사전 검색/목록을 노출하지 않는다. get_admin_tag는 최신 active admin을 검사한다.
- `service/command.py`: resolve_tags는 콘텐츠 서비스가 인가·부모 잠금 후 전달한 이름을 재사용/생성한다. create_tag/update_tag/deactivate_tag는 identity.require_admin으로 최신 DB 역할·상태를 검사한다. 공유 이름 수정은 관리자 전용이며 비활성화는 기존 연결을 보존한다. 생성 시 기존 이름의 설명을 덮어쓰지 않는다.
- `repository.py`: tags만 접근한다. PostgreSQL ON CONFLICT DO NOTHING으로 동시 이름 생성을 처리하고 SELECT FOR SHARE로 이름·활성 상태를 연결 쓰기가 끝날 때까지 고정한다. 이름 묶음은 정렬하여 잠금을 취득하고 결과는 입력 순서로 복원한다. 여러 태그 작업을 조합하는 호출자는 일관된 콘텐츠/태그 잠금 순서를 유지한다.
- `mapper/persistence.py`: Entity → 불변 TagInfo 변환만 한다. public types에는 Command·사전 Info·태그 연결 값·응답 조합 값만 있다.

호출자는 use_case_transaction을 시작하거나 동일 범위에 참여한다. 독립된 autobegin 트랜잭션은 채택하지 않는다. resolve_tags의 retained_ids는 콘텐츠 저장소에서 부모 잠금 아래 읽은 기존 연결 ID만 사용한다. 비활성 사전은 기존 연결 유지에만 허용하고 신규 연결은 거절한다. 사전 물리 삭제 API는 없다.

## 콘텐츠 연결과 HTTP 경계

product/character/lorebook이 각자 공개·내부 연결을 소유한다. 이 영역은 해당 연결 ORM·repository를 참조하지 않는다. 콘텐츠가 사전 공개 service/types로 사전을 조회하고 자기 mapper에서 조합한다. 현재 연결의 태그 이름 변경은 재발행 없이 반영된다. 공개 응답에는 내부 출처·부여 사용자를 포함하지 않는다.

관리자 HTTP는 governance/admin/tag_router.py가 소유하고 app/http/contracts/tags.py의 공통 DTO를 사용한다. 내부 사전 표현을 일반 사전 검색/자동완성으로 공개하지 않는다. 태그명과 공개 연결 이름은 사용자에 의해 노출될 수 있으므로 내부 비밀 원문을 이름에 저장하는 설계가 아니다.

ORM은 app/db/models/tag.py에 분리되어 있다. 마이그레이션 0028/0029와 초기 SQL 019를 그대로 사용하며 이번 API 구현은 스키마를 변경하지 않는다. 유저·작가·독자·이벤트 연결과 검색·추천·프런트는 추가하지 않았다.

API와 예제·검증 범위: [태그 관리](../../../../../../references_document/reference/content-tags.md).


## U16 공개 연결 정책 (2026-10-30)

`service/policy.py`는 세 콘텐츠 서비스가 공유하는 순수 업무 판단이다.
- select_public_tag_ids(SelectPublicTagIdsCommand): 추가는 기존 순서 뒤에 요청 ID를
  중복 없이 붙이고 교체는 요청 순서를 사용한다. 빈 교체는 전체 해제다.
- plan_internal_tag_changes(PlanInternalTagChangesCommand): 제거/설정할 ID tuple을
  InternalTagChangesInfo로 반환한다. 관리자는 시스템 연결을 인수·교체할 수 있고
  시스템은 관리자 지정 연결을 설정/제거 대상에서 제외한다.
- validate_internal_tag_removal(ValidateInternalTagRemovalCommand): 시스템의 관리자
  연결 삭제는 기존 ValueError 문구로 거절하고 없는 연결 삭제는 허용한다.

입력은 부모 잠금 아래 얻은 연결 Info와 resolve_tags 결과 ID다. 이 정책은 인가나
비활성 검증을 대체하지 않으며 호출자가 DB 쓰기를 수행한다. 세션/ORM/현재 시각/
외부 I/O를 사용하지 않고 입력도 변경하지 않는다. 공유 업무 판단만 추출하므로
콘텐츠 repository/mapper/router 및 HTTP/Python 기존 인터페이스는 유지한다.
U25의 이름 정규화·배치 SQL·이름순 잠금·반환 순서·트랜잭션은 변경하지 않는다.
