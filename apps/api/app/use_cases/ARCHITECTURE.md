# 모듈 외부의 통계 조립

현재 이 계층은 `product_statistics.py`, `conversation_directory.py`, `studio_publication.py`를 유지한다. 대화 시작은 conversation/service/command, 답변 생성·문맥 준비·완료·기억 실행은 chat/service/workflow가 소유한다. 이전 구현과 호환 재노출은 남기지 않는다.

- `rebuild_day(RebuildDayCommand)`: conversation 방/버전 사실, chat 생성 사실, billing 사용량/매출 사실을 product 공개 통계 저장 Command로 조합한다.
- `process_pending(ProcessPendingCommand)`: 날짜 작업 잠금·재집계·완료를 한 트랜잭션으로 처리한다. 실패하면 큐를 보존한다.
- `enqueue_recent`는 기존 product 통계 기능을 재노출한다. `product/statistics_job.py`는 기존 CLI 조립 진입점이다.
- `list_recent_conversations`는 conversation 소유 목록과 chat 소유 마지막 메시지 문구를 결합한다. 두 조회 모두 사용자 ID로 범위를 제한한다.
- `publish_studio`는 저장된 소유자 문서 revision을 잠그고 캐릭터·로어·상품 구성·모델 설정·첫 릴리스를 한 트랜잭션으로 조합한다. 같은 문서의 재호출은 기록된 발행 결과를 반환한다. 변경된 문서의 재발행은 별도 릴리스 편집 경로가 준비될 때까지 충돌로 거절한다.

향후 통계는 reporting 별도 모듈로 분리할 방향이다. 이번에는 통계 실행·저장·큐 소유권과 배포 진입점을 변경하지 않으며 reporting 모듈/주입 인터페이스를 미리 만들지 않는다. use_cases 디렉터리 삭제는 완료 목표가 아니다.


스튜디오 태그는 work.tags를 작품 현재 공개 연결로 전달하고 characters[].tags를 각 캐릭터 생성 Command로 전달한다. lorebooks[]는 독립 로어북이 아니라 생성 로어북 하나에 들어갈 항목 배열이므로 각 항목의 tags를 입력 순서대로 합쳐 로어북 생성 Command로 전달한다. 사전 재사용/중복 제거는 하위 tag 서비스가 수행한다. 같은 발행 트랜잭션에서 처리하며 발행 재호출의 기존 멱등 반환은 태그를 다시 변경하지 않는다. 태그를 snapshot에 복사하지 않는다.
