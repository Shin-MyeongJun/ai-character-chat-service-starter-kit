# 모듈 외부의 유스케이스 조립

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

현재 이 계층은 `product_statistics.py`, `conversation_directory.py`, `studio_publication.py`를 유지한다. 대화 시작은 conversation/service/command, 답변 생성·문맥 준비·완료·기억 실행은 chat/service/workflow가 소유한다. 이전 구현과 호환 재노출은 남기지 않는다.

- `rebuild_day(RebuildDayCommand)`: conversation 방/버전 사실, chat 생성 사실, billing 사용량/매출 사실을 product 공개 통계 저장 Command로 조합한다.
- `process_pending(ProcessPendingCommand)`: 날짜 작업 잠금·재집계·완료를 한 트랜잭션으로 처리한다. 실패하면 큐를 보존한다.
- `enqueue_recent`는 기존 product 통계 기능을 재노출한다. `product/statistics_job.py`는 기존 CLI 조립 진입점이다.
- `list_recent_conversations`는 conversation 소유 목록과 chat 소유 마지막 메시지 문구를 결합한다. 두 조회 모두 사용자 ID로 범위를 제한한다.
- `publish_studio`는 저장된 소유자 문서 revision을 잠그고 캐릭터·로어·상품 구성·모델 설정·첫 릴리스를 한 트랜잭션으로 조합한다. 같은 문서의 재호출은 기록된 발행 결과를 반환한다. 변경된 문서의 재발행은 별도 릴리스 편집 경로가 준비될 때까지 충돌로 거절한다.

향후 통계는 reporting 별도 모듈로 분리할 방향이다. 이번에는 통계 실행·저장·큐 소유권과 배포 진입점을 변경하지 않으며 reporting 모듈/주입 인터페이스를 미리 만들지 않는다. use_cases 디렉터리 삭제는 완료 목표가 아니다.


스튜디오 태그는 work.tags를 작품 현재 공개 연결로 전달하고 characters[].tags를 각 캐릭터 생성 Command로 전달한다. lorebooks[]는 독립 로어북이 아니라 생성 로어북 하나에 들어갈 항목 배열이므로 각 항목의 tags를 입력 순서대로 합쳐 로어북 생성 Command로 전달한다. 사전 재사용/중복 제거는 하위 tag 서비스가 수행한다. 같은 발행 트랜잭션에서 처리하며 발행 재호출의 기존 멱등 반환은 태그를 다시 변경하지 않는다. 태그를 snapshot에 복사하지 않는다.
