# Memory 모듈

- 소유 테이블: `conversation_memories`.
- `service/query.py`: Get/List/GetLatestSummary/SearchMemoriesCommand를 받아 MemoryInfo, MemoryPage 또는 RetrievedMemoryInfo 목록을 반환한다. 검색은 인가 확인 후 주입받은 embedder를 호출한다. embedder는 실행 의존성이며 Command에 포함하지 않는다.
- `repository.py`: 커서 조회, 벡터 거리 계산, 저장소 벡터 형식 검증. `MemoryPageRow`와 ORM 검색 결과는 자기 persistence mapper에만 전달한다.
- `mapper/persistence.py`: ORM 및 이미 계산된 유사도를 값 타입으로 변환한다. 외부 호출과 입력 수정은 없다.
- `types.py`: 공개 Command/Info/페이지/커서 계약.

## 인가 스코핑 예외

`conversation_memories.conversation_id → conversations.id`를 JOIN하고 `conversations.user_id`로 접근 범위를 제한한다. Conversation 컬럼을 메모리 결과에 포함하지 않는다. 임베딩 호출 전 수행하는 소유권 존재 조회도 동일한 관계의 인가 가드이며 결과는 bool뿐이다. Conversation repository나 mapper를 호출하지 않는다.

조회는 트랜잭션을 종료하지 않는다. 임베딩 실패는 빈 결과로 숨기지 않는다. 작은 조회 모듈이므로 추가 계층 분할을 하지 않았다. 메모리 추출·쓰기 유스케이스·임베딩 공급자 연결·검색 재정렬은 기존 미구현 범위다. 빈 기존 command/embeddings 골격을 구현 완료로 간주하지 않는다.
