# Tag 사전 영역

`tags`를 소유한다. 정확한 이름 UNIQUE이며 이름의 앞뒤 공백만 제거한다. 내부 공백·대소문자·유니코드 표기·동의어는 통합하지 않는다. normalized_name·kind·개수 제한·태그 snapshot은 없다.

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
