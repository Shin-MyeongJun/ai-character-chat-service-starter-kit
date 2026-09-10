# 최상위 유스케이스 조립

도메인 모듈을 역방향으로 호출하게 만들지 않고 여러 모듈의 공개 service/types만 조합한다. 자체 테이블·repository·HTTP DTO는 없다. router와 배치 조립 코드가 진입하고, 도메인 service는 이 계층을 호출하지 않는다.

- `conversations.start_conversation(StartConversationCommand)`: conversation의 방/상품 버전/참여 캐릭터 생성과 chat의 첫 캐릭터 메시지 저장을 동일 use_case_transaction으로 처리한다. 기존 ConversationStartedInfo 및 POST /conversations 계약을 유지한다.
- `product_statistics.rebuild_day(RebuildDayCommand)`: conversation의 방/버전 전환 사실, chat의 생성 사실, billing의 사용량/매출 사실을 받아 product 공개 통계 저장 Command에 전달한다.
- `product_statistics.process_pending(ProcessPendingCommand)`: 날짜 작업 잠금·재집계·완료를 한 트랜잭션으로 처리한다. 실패하면 큐가 보존된다. 최근 날짜 재요청은 product 자체 기능을 명시적으로 재노출한다.

대화 시작과 통계 집계는 변경 이유가 달라 별도 파일이다. 외부 호출 없이 DB 트랜잭션만 조정한다. product.statistics_job은 배포용 실행 조립 코드로 이 계층을 호출한다.
