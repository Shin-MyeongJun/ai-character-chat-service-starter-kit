# 모듈 외부의 통계 조립

현재 이 계층은 `product_statistics.py`만 유지한다. 대화 시작은 conversation/service/command, 답변 생성·문맥 준비·완료·기억 실행은 chat/service/workflow가 소유한다. 이전 구현과 호환 재노출은 남기지 않는다.

- `rebuild_day(RebuildDayCommand)`: conversation 방/버전 사실, chat 생성 사실, billing 사용량/매출 사실을 product 공개 통계 저장 Command로 조합한다.
- `process_pending(ProcessPendingCommand)`: 날짜 작업 잠금·재집계·완료를 한 트랜잭션으로 처리한다. 실패하면 큐를 보존한다.
- `enqueue_recent`는 기존 product 통계 기능을 재노출한다. `product/statistics_job.py`는 기존 CLI 조립 진입점이다.

향후 통계는 reporting 별도 모듈로 분리할 방향이다. 이번에는 통계 실행·저장·큐 소유권과 배포 진입점을 변경하지 않으며 reporting 모듈/주입 인터페이스를 미리 만들지 않는다. use_cases 디렉터리 삭제는 완료 목표가 아니다.
