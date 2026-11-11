# 모듈 외부의 유스케이스 조립

## U19 a4 스튜디오 이미지 발행

revision 영수증 재생 이후 잠긴 초안에서 이미지 항목과 시작 장면 배치를 검증한다.
새 요청은 무변경 후보도 같은 작품의 ready 파일을 UUID 순으로 잠가 확인한다.
모델 설정과 이미지 digest가 이전 스냅샷과 같을 때 기존 영수증 재사용 경로를 유지한다.
스튜디오 로컬 ID를 서버 복사본 ID로 변환해 product의 발행 Command에 전달한다.
새 카탈로그와 시작 블록, 파일 보존 참조, 릴리스, revision 영수증을 함께 커밋한다.

## Gemini 검토 후 발행 동일성 보완 (2026-11-03)

기록된 revision/fingerprint 영수증은 기존 순서대로 먼저 재생하며 다른 요청은 409다.
영수증이 없는 새 요청은 무변경 발행도 release note를 검증한다. 문서 digest가 같을 때
product 공개 snapshot 조회로 이전 불변 snapshot의 model.id/reasoning_effort를 비교한다.
현재 상품의 가변 설정이나 이전 요청 fingerprint로 발행 설정을 추정하지 않는다.
설정이 다르거나 legacy snapshot에 비교할 모델 정보가 없으면 정상 발행 경로를 실행한다.
모델·추론 설정의 하위 검증, 원본/설정/스냅샷/매핑/영수증의 단일 트랜잭션을 유지한다.
기존 snapshot은 수정하지 않는다. 문서와 발행 설정이 같은 경우 유효한 메모만 바꿔도
기존 무변경 생략 정책으로 이전 release를 반환하고 현재 revision 영수증을 저장한다.
legacy 매핑 채택·영수증 복구도 같은 snapshot 비교를 통과한다. 저장 JSON은 바꾸지 않는다.

태그 관리자 변경은 tag 모듈의 비대기 테이블 fencing을 따른다. 아래 이전 절의
전역 배타 잠금 없음은 당시 구현 이력이며 관리자 변경의 새 충돌 정책은 tag 문서가 기준이다.

## IEA-02/03 스튜디오 발행 (2026-11-03)

`publish_studio`는 advisory → product → draft 잠금과 revision/영수증 검사를 유지한다.
변경 발행은 문서·로어/장면 값을 검증하고 기존 character를 ID순으로, 기존 lorebook을
공개 소유 조회로 먼저 잠근다. 단독 콘텐츠 태그 쓰기의 부모→사전 순서를 유지한다.
이후 work·전체 character·lorebook의 태그 이름을 모아 tag 공개 `acquire_tag_names`로
먼저 획득한다. 사전 전체가 아닌 요청 이름 집합만
정확한 이름순 INSERT/SHARE로 확보한 뒤 기존 구성요소 쓰기를 순차 실행한다.
여러 개별 resolve의 정렬만으로 신규 이름 UNIQUE 대기가 교차하던 순서를 제거한다.

선획득은 연결 권한을 부여하지 않는다. 각 콘텐츠 서비스는 자기 부모 잠금 아래 읽은
기존 연결 ID로 resolve_tags를 다시 호출해 비활성 유지/신규 거절을 검사한다. 관리자
이름·활성 변경 fencing, 원래 입력 순서와 정규화, 소유권·원자적 rollback은 유지한다.
전역 배타 잠금·예외 재시도·내부 commit·외부 공급자 호출은 추가하지 않는다.

snapshot 재사용 성공도 `_record_publication_receipt`로 현재 revision/fingerprint와
기존 release를 같은 트랜잭션에 저장한다. legacy receipt는 기존 component_mapping의
서버 ID 채택 경로를 거쳐 기록한다. 이전 영수증·매핑·snapshot JSON과 문서 revision은
보존하며 snapshot을 새로 만들지 않는다. 이미 기록된 요청의 재생은 쓰기 없이 반환하고,
같은 revision의 다른 인자는 기존대로 충돌한다. 영수증 저장 실패는 성공으로 반환하지 않는다.

회귀는 test_studio_publication_db의 독립 연결·실행 장벽·pg_blocking_pids 관찰과
HTTP D→E→D→무변경 발행→다음 저장→재생, rollback/재시도·관리자 fencing·비활성
연결 범위를 포함한다. 실행 여부와 환경 제한은 새 전용 감사 보고서에 구분해 기록한다.

## U27 호환 경로 정리 (2026-11-02)

conversation_directory.py 호환 연결을 제거했다. 조회/조합 책임이 이미 chat 공개
service/views에 있으므로 HTTP와 HTTP mapper가 chat 공개 service/types를 직접 참조한다.
HTTP cursor_created_at 이름과 활동 시각 의미, View 기본값·권한·페이지 계약은 유지한다.
통계 및 스튜디오의 교차 모듈 유스케이스 조립 책임은 이 계층에 유지한다.
아래 날짜별 conversation_directory 설명은 제거 전 이력이다.

## U04 스튜디오 저장 교차 잠금 (2026-10-30)

revision 지정 `save_studio`, `prepare_components`, `publish_studio`의 공통 진입점인
product 공개 `get_studio_draft_for_publication`은 advisory → product → draft를 잠근다.
직접 저장과 같은 `product-studio-draft` 키를 사용해 기존 product/draft → advisory
역전을 없앴다. 상위 조립부가 미리 행 잠금을 잡거나 advisory를 임의로 해제하지 않는다.
legacy 매핑 채택 뒤 저장, 영수증 재시도, U06 후속 발행과 U14 저장 단계 및 최외곽
트랜잭션 책임은 유지한다. CAS 충돌 시 매핑 채택도 함께 rollback된다.

U04 전용 PostgreSQL 테스트에서 두 독립 작업 연결의 실제 advisory 대기를 관찰하고
양방향 교차 실행·CAS 충돌·동일 내용 재시도·rollback을 검증했다. 이전 잠금 순서는 대조
경로에서 실제 deadlock 40P01을 재현한다. 앞선 U14 절의 미검증 설명은 당시 측정 범위이며,
현재 U04 검증은 스튜디오 저장 경합 범위다. 전체 외부 공급자/E2E 검증을 뜻하지 않는다.

## U14 상품 발행 배치 저장 연결 (2026-10-29)

studio_publication의 원본 갱신·태그/미디어·구성/설정·release·영수증 순서를 유지한다.
그 아래 product의 발행 builder가 이미 읽은 구성/모델/시작 항목 Info를 재사용하고
repository가 스냅샷 슬롯 부모와 대상/시작 자식을 두 단계로 모아 저장한다.
이 조립부는 타 모듈 repository/ORM에 접근하거나 공개 인가를 생략하지 않는다.
character/lorebook의 독립 공개 freeze와 필요한 부모 flush는 유지한다. 측정한 SQL/flush
감소는 product release 경로이며 studio 원본 준비·영수증 저장의 전체 비용 측정이 아니다.
U06의 발행 후 초안 저장/후속 발행, 기존 snapshot·revision 영수증 및 다른 fingerprint
거절은 기존 회귀로 유지한다. 실제 PostgreSQL 경합·격리 검증은 수행하지 않았다.

## 조회·통계 조립부 타입 정리 (2026-10-28)

account_overview/conversation_directory/product_statistics의 실행 세션을 AsyncSession으로
명시해 use_cases 전체를 엄격 검사에 편입했다. 본인 건수는 소유 모듈의 공개 서비스에서
읽고 기존 정수 사전으로 반환한다. HTTP overview-counts는 response_model=None으로
기존 무필터 응답과 빈 OpenAPI 스키마를 유지한다.

최근 대화 목록은 기존 소유 metadata의 100개 단위 순회, 해당 ID의 chat 활동 조회,
활동 시각/UUID 역순 정렬·커서 제외·원래 소유 총건수를 유지한다. 빈 대화는 생성 시각을
활동 시각으로 쓰며 cursor 쌍/시간대 검증도 같다. 키 helper의 cast는 모든 조립 행이
활동/생성 시각을 받는 전제와 앞선 cursor 쌍 검증을 표현한다. 공개 View의 선택적
last_activity_at 기본값은 유지한다. 라이브 조회를 snapshot 페이지로 바꾸지 않았다.

http/mapper/conversation_directory.py는 RecentConversationsPageView를 기존 HTTP DTO로
변환한다. 모양이 다른 View를 ConversationListPageInfo 전용 mapper에 전달하지 않는다.
같은 Pydantic model_validate/from_attributes 경로라 미리보기·활동 시각·총건수와 응답
계약은 같다. 교차 도메인 View 조합은 이 계층, HTTP 변환은 HTTP mapper가 담당한다.

통계는 같은 트랜잭션의 날짜 잠금·도메인 사실 조회·전체 재집계·완료 순서를 유지한다.
chat의 알려진 정수 출력 건수를 product의 legacy None 허용 목록 요소 타입으로 연결할
때 같은 값의 목록을 만든다. 0/None을 바꾸지 않으며 날짜·통화·실패 rollback 정책도 같다.

## studio 조립부 타입 정리 (2026-10-28)

studio_components/content/diagnostics/publication과 http/studio_publication.py를 엄격
검사에 편입했다. 세션·소유자·문서/구성/발행 결과와 HTTP 반환 타입을 명시했다.
타 모듈의 공개 service/types만 조합하며 SQL/ORM이나 새 계층은 추가하지 않았다.
문서 필드 뷰는 studio_content.py, 서버 매핑/영수증 뷰는 studio_components.py에 두어
기존 관련 기능 파일 안에서 공유한다. JSON 구조를 별도 업무 모듈로 재설계하지 않는다.

TypedDict/cast는 기존 편집 문서 필드와 서버가 기록한 매핑/영수증을 읽고, 같은 객체를
product의 재귀 JSON 계약에 전달하는 정적 경계다. 로어/장면 값은 공개 lorebook의
LorebookEntryCommandFields를 재사용한다. 기존 필드 검사·하위 도메인 검증·누락 키와
손상 값의 오류·기본값·확장 키·깊은 복사를 유지한다. 읽기 뷰 자체는 새로운 JSON 검증을
수행하지 않는다. Any/ignore/기준선 예외는 추가하지 않았다.

legacy 구성의 순서/제목 대응과 모호성 충돌, revision CAS·발행 영수증·request digest,
업로드 대상 복사본 재사용, character/lore/product/settings/release의 호출·잠금 순서와
상위 트랜잭션을 유지한다. 영수증 재전송의 **kwargs도 유지해 예상치 못한 저장 필드의
기존 TypeError를 숨기지 않는다. 캐릭터 이미지 목적과 불필요한 연결 삭제, 시작 항목
분리/삭제, 이전 snapshot 보존 정책은 같다.

HTTP의 진단 입력은 계속 자유 객체 목록이며 새 TypedDict 입력 검증을 추가하지 않는다.
진단/업로드 준비는 response_model=None으로 기존 무필터 응답과 빈 OpenAPI 스키마를
유지한다. 저장/발행의 기존 DTO, 인증 의존성·409/422 오류 변환도 같다.

아래 과거 재발행 거절 설명과 현재 재발행 구현의 충돌은 기존 감사 U06이다. 이번 타입
정리에서 발행 정책·product 구현·실패 테스트 기대를 변경하지 않았다.

## 기존 조립 책임과 설계 이력

현재 이 계층은 `product_statistics.py`와 스튜디오 저장·구성·발행 조립부를 유지한다. 대화 시작은 conversation/service/command, 답변 생성·문맥 준비·완료·기억 실행은 chat/service/workflow가 소유한다. U11의 conversation_directory는 기존 HTTP/Python 진입점과 View 이름을 보존하는 얇은 연결이며 목록 조회 책임은 chat 공개 views에 있다.

- `rebuild_day(RebuildDayCommand)`: conversation 방/버전 사실, chat 생성 사실, billing 사용량/매출 사실을 product 공개 통계 저장 Command로 조합한다.
- `process_pending(ProcessPendingCommand)`: 날짜 작업 잠금·재집계·완료를 한 트랜잭션으로 처리한다. 실패하면 큐를 보존한다.
- `enqueue_recent`는 기존 product 통계 기능을 재노출한다. `product/statistics_job.py`는 기존 CLI 조립 진입점이다.
- `list_recent_conversations`는 기존 Command의 커서 이름을 chat의 활동 커서 Command로 연결한다. chat 공개 views가 소유자 범위의 DB 페이지와 정확한 COUNT를 반환한다.
- `publish_studio`는 저장된 소유자 문서 revision을 잠그고 캐릭터·로어·상품 구성·모델 설정·첫/후속 릴리스를 한 트랜잭션으로 조합한다. 발행 후 초안 편집과 후속 발행을 허용하며 초안 저장만으로 현재 상품 프로필/태그/승인 상태를 바꾸지 않는다. 기존 구성 ID와 이전 스냅샷을 보존하고 기록된 revision 영수증으로 응답 유실 재호출을 복구한다.

향후 통계는 reporting 별도 모듈로 분리할 방향이다. 이번에는 통계 실행·저장·큐 소유권과 배포 진입점을 변경하지 않으며 reporting 모듈/주입 인터페이스를 미리 만들지 않는다. use_cases 디렉터리 삭제는 완료 목표가 아니다.


스튜디오 태그는 work.tags를 작품 현재 공개 연결로 전달하고 characters[].tags를 각 캐릭터 생성/태그 교체 Command로 전달한다. lorebooks[]는 독립 로어북이 아니라 서버 복사본 로어북 하나의 항목 배열이다. 첫 발행은 항목 태그를 입력 순서대로 합쳐 생성 Command에 전달하고 후속 발행은 공개 태그 교체 서비스에 전달한다. 빈 목록은 기존 연결 제거를 뜻한다. 사전 재사용/중복 제거는 하위 tag 서비스가 수행한다. 같은 발행 트랜잭션에서 처리하며 영수증 재호출은 태그를 다시 변경하지 않는다. 태그를 snapshot에 복사하지 않는다.

## U06 후속 발행 계약 확정 (2026-10-29)

사용자 결정에 따라 후속 발행을 공식 지원한다. 기존 book_id 경로는 공개 소유 조회를
lock=True로 호출한 뒤 제목과 worldRules 설명을 갱신하고, 기존 visibility/status는
유지한다. 항목 태그를 모두 제거하면 부모 태그도 제거한다. 계정 소유권/태그 검증/
발행 실패는 상위 transaction으로 rollback되며 영수증을 남기지 않는다. 이전 스냅샷을
수정하지 않고 같은 요청 재시도는 최신 초안 revision과 무관하게 기존 영수증을 반환한다.
새 형식 영수증의 같은 revision에 다른 요청 파라미터를 사용하면 409다. legacy 영수증의
기존 복구 경로도 유지한다. 초안 CAS 충돌·승인 정책·이미지 준비 검증은 바꾸지 않았다.

## U07 스튜디오 중첩 입력 검증 (2026-10-29)

product의 공개 validate_studio_document_shape를 저장/업로드 준비/발행에서 사용한다.
문서/구성/이미지의 자료형, 비어 있거나 중복된 로컬 ID, 비어 있지 않은 문서 내부 참조,
mediaId UUID와 usage를 쓰기 전에 검사한다. 누락된 선택 필드·빈 authored text·서버
업로드 전 이미지·확장 키를 초안에서 유지하며 input dict를 필터/변환하지 않는다.

prepare_components는 모든 대상의 name/persona를 확인한 뒤 첫 서버 복사본을 만든다.
publish_studio는 로어 옵션·장면 값 변환을 첫 도메인 쓰기 앞으로 옮겨 늦은 입력 오류를
방지한다. 영수증 재시도는 기존대로 최신 문서 검증보다 먼저 반환하며 U06 계약·revision/
digest·과거 snapshot은 유지한다. 정상 형식 media UUID의 소유권/ready 상태는 기존
character 서비스가 검사한다. 서버 저장 매핑/영수증 손상 전체의 복구 정책까지 바꾸지는 않는다.

unsaved lore diagnostics도 category/priority/placement의 문자열 자료형을 검사하므로
비해시 가능 JSON 값이 사전 조회 TypeError로 새지 않는다. 광범위한 TypeError/KeyError
catch로 내부 오류를 숨기지 않으며 ValueError가 기존 HTTP errors 경계에서 422가 된다.


## U11 대화 목록 전체 수집 제거 (2026-10-29)

위 2026-10-28의 100개 단위 전체 순회·Python 정렬 설명은 당시 구현 이력이다.
현재 conversation_directory는 기존 공개 함수/Conversation Command를 chat의
ListRecentConversationsCommand에 연결한다. 두 공개 View 이름은 chat types의 같은
모양 dataclass를 재노출해 HTTP mapper/Python 호출과 기본값을 유지한다. SQL/ORM과
타 모듈 repository를 이 계층에 추가하지 않았다. 전체 수집·정렬·커서 필터와 두 cast를
제거했고 새 테이블이나 조립 계층을 만들지 않았다.

제한된 읽기 projection 예외는 규칙 C.2 및 chat/conversation ARCHITECTURE에 명시했다.
소유권/활동순·빈 대화·정확한 COUNT·live cursor 정책은 그대로이고 COUNT+DB 페이지
두 번으로 연결한다. 요청 사이 새 활동의 커서 이동과 COUNT/페이지 시점 차이는 남는다.
