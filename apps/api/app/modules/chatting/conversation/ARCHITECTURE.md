# Conversation 모듈

- 소유 테이블: `conversations`, `conversation_characters`, `messages`, `conversation_version_changes`, `product_generations`.
- `service/query.py`: 소유 대화 Info, product 통계에 제공할 ConversationStatisticsInfo.
- `service/command/__init__.py`: 공개 product snapshot/runtime 결과로 대화 시작.
- `service/command/versions.py`: 순방향 버전 전환, 동의 정책, 대상 구성 검증. 기록과 메모리를 삭제하지 않는다.
- `service/command/generation.py`: 요청 예약·완료, 멱등성, 결과 유효성·stale 판단, 메시지 저장 조율과 공개 billing 사용량 기록.
- `service/command/context.py`: `prepare_runtime_context(PrepareRuntimeContextCommand)`. 모델 대체 계획을 저장할 수 있으므로 쓰기 유스케이스로 분류하며 결과는 ConversationRuntimeView다.
- `repository.py`: 이 모듈 테이블만 조회/저장. 서비스는 반환값을 mapper로 바꾼 뒤 상태를 판단한다.
- `mapper/persistence.py`: 공개 product runtime View와 자체 결과의 순수 조합. 활성 항목 정책은 context service가 결정한 뒤 전달한다.
- `router.py` 및 `mapper/schema.py`: 시작·버전 전환·업데이트 조회의 기존 HTTP 표현.

## 계약과 분리 이유

product snapshot/릴리스/구성은 product 공개 service/types를 통해서만 읽는다. 모델 선택은 LLM, 과금 사실 기록은 billing 공개 Command로 위임한다. 같은 use_case_transaction을 공유하므로 메시지·사용량·통계 갱신 요청이 함께 성공하거나 롤백한다. 타 모듈 JOIN 예외는 없다.

시작 결과는 ConversationStartedInfo, 전환 결과는 VersionSwitchedInfo이며 changed=false는 이미 해당 버전인 멱등 성공을 뜻한다. 생성 결과 GenerationInfo.created는 신규 예약 여부다. 실패·취소·stale은 기존 저장 정책을 유지한다. Legacy 대화의 검증되지 않은 버전 매핑은 거절한다.

대화 시작, 버전 전환, 생성 완료, 런타임 준비는 변경 이유가 달라 command 하위 파일로 나눴다. 최상위 service/__init__.py는 명시적인 공개 재노출만 담당한다. HTTP 공유 ModelNotice DTO는 app/http에 두며 타 모듈 schemas를 가져오지 않는다. 실제 스트리밍/API 조립은 기존 chat 골격의 미완료 범위다.
