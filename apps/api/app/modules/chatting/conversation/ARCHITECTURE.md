# Conversation 모듈

- 소유 테이블: `conversations`, `conversation_characters`, `conversation_version_changes`. 메시지와 `product_generations`는 chat 소유이며 이 모듈에서 읽거나 쓰지 않는다. `conversations.history_revision`은 기존 원문 변경 세대이며 단순 후속 append에는 증가하지 않는다.
- `service/query.py`: `get_owned_conversation(OwnedConversationCommand)`은 소유 방의 ConversationInfo를 반환하며 lock=true이면 FOR UPDATE를 획득한다. `list_conversation_characters`는 같은 소유권 조건의 실제 참여 캐릭터 Info를 반환한다. 통계 조회는 방 생성/버전 전환 사실만 제공한다.
- `service/command/__init__.py`: `create_product_conversation(StartConversationCommand)`은 공개 product snapshot/runtime으로 방·상품 버전·참여 캐릭터를 저장하고 PreparedConversationInfo에 검증된 첫 메시지 값도 제공한다. 첫 메시지 저장은 최상위 `app/use_cases/conversations.start_conversation`이 chat 공개 Command를 호출한다. 방 저장 실패나 첫 메시지 저장 실패 시 전체를 롤백한다.
- `service/command/versions.py`: 순방향 버전 전환, 동의 정책, 대상 구성 검증. 메시지·기억·생성 이력을 수정하지 않는다.
- `service/command/context.py`: `prepare_runtime_context(PrepareRuntimeContextCommand)`. 기존 모델 대체 계획을 저장할 수 있는 쓰기 유스케이스이며 ConversationRuntimeView를 반환한다. 로어 활성화는 lorebook 공개 서비스에 고정 스냅샷과 `activation_text`를 전달한다.
- `service/command/history.py`: `advance_history_revision(AdvanceHistoryRevisionCommand)`은 소유 대화를 잠그고 파괴적 chat 변경 세대를 증가시킨다. memory 무효화가 같은 최상위 트랜잭션에서 호출한다.
- `repository.py`: 자체 테이블만 조회/저장. `mapper/persistence.py`: 자체 Entity와 공개 snapshot/runtime 결과의 순수 변환.
- `router.py`, `mapper/schema.py`: 시작·버전 전환·업데이트 조회의 기존 HTTP 경로, DTO 이름, 필드, 상태 코드를 유지한다. 시작 라우터는 최상위 유스케이스에 연결한다.

## 계약과 분리 이유

대화방과 상품 버전은 conversation, 메시지 저장과 생성 수명주기는 chat 책임이다. conversation → chat 역방향 호출은 없다. chat이 공개 서비스로 소유권·현재 버전·참여 캐릭터를 검증한다. 생성과 기본 CRUD가 공통 대화방 잠금을 획득하도록 공개 lock 계약을 유지했다. 타 모듈 JOIN 예외는 없다.

최상위 조립 결과는 기존 ConversationStartedInfo, 전환 결과는 VersionSwitchedInfo이며 changed=false는 이미 해당 버전인 멱등 성공이다. 버전 변경은 pending 생성을 취소하지 않고 기존 완료 stale 처리와 연결된다. 메시지 되돌리기는 현재 버전·initial_snapshot_id·전환 이력을 바꾸지 않는다. version_changes는 메시지 FK가 없으며 방과 두 snapshot의 기존 참조를 유지한다. Legacy 대화의 검증되지 않은 버전 매핑은 계속 거절한다.

생성 Command/Info/mapper/repository 및 호출부는 chat으로 이동했다. 생성 통계와 방 통계의 조합은 최상위 `app/use_cases/product_statistics.py`로 이동해 product에서 chat을 역으로 호출하지 않는다. 관련 없는 기존 product pending-update View → conversation query 의존성은 유지한다.

런타임 `lorebooks[].entries`는 후보가 아닌 자동 활성화가 끝난 항목 목록이다. enabled 일반 항목 중 always와 `activation_text`에 매칭된 keyword만 포함한다. 텍스트는 호출자가 명시적으로 구성하며 메시지 이력을 암묵적으로 조회하지 않는다. 생략 시 빈 문자열로 처리하여 always만 포함한다. start_set은 별도 start 필드로 제공하며 semantic/manual 활성화, 토큰 예산 적용, 실제 프롬프트 구성은 범위 밖이다. 원본 로어북 조회로 스냅샷을 대체하지 않는다.

시작·버전 전환 schema mapper는 인증 사용자와 경로 ID를 받아 최종 Command를 생성한다. 업데이트 응답 변환도 같은 mapper 클래스에서 처리한다. ConversationInfo.product_id는 DB와 동일하게 필수이며 레거시 여부는 product_snapshot_id의 None 여부로 판단한다.

대화 생성·버전 전환·런타임 준비는 변경 이유가 달라 기능 파일로 나눴다. 런타임 준비는 쓰기 부수효과가 있으므로 command에 유지하고 순수 View 조립은 persistence mapper에 둔다. 공개 재노출은 `service/__init__.py`에서 명시한다. 실제 인증/세션 연결은 기존 503 훅 상태이며 운영 인증과 실제 외부 생성은 이번 작업에서 구현하지 않았다.
