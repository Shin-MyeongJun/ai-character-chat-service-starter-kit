# Memory 모듈

- 소유 테이블: `conversation_memories`.
- `service/query.py`: Get/List/GetLatestSummary/SearchMemoriesCommand를 받아 MemoryInfo, MemoryPage 또는 RetrievedMemoryInfo 목록을 반환한다. 검색은 인가 확인 후 llm의 공개 `EmbeddingService`에 공개 `EmbedTextsCommand`(query 용도)를 전달한다. 공급자 adapter를 직접 참조하지 않는다.
- `service/command.py`: `invalidate_conversation_memories(InvalidateConversationMemoriesCommand)`는 conversation 공개 service로 소유권과 대화방 잠금을 확인한 뒤 해당 방의 기억·요약을 모두 삭제한다. 상위 chat 교체/되돌리기의 동일 트랜잭션에 참여하므로 실패하면 메시지 변경도 롤백된다.
- `repository.py`: 커서 조회, 벡터 거리 계산, 1536차원 저장소 벡터 형식 검증. 벡터 검색은 공급자와 모델이 정확히 일치하고 metadata가 있는 행만 대상으로 한다. `MemoryPageRow`와 ORM 검색 결과는 자기 persistence mapper에만 전달한다.
- `mapper/persistence.py`: ORM 및 이미 계산된 유사도를 값 타입으로 변환한다. 외부 호출과 입력 수정은 없다.
- `types.py`: 공개 Command/Info/페이지/커서 계약.

## 인가 스코핑 예외

`conversation_memories.conversation_id → conversations.id`를 JOIN하고 `conversations.user_id`로 접근 범위를 제한한다. Conversation 컬럼을 메모리 결과에 포함하지 않는다. 임베딩 호출 전 수행하는 소유권 존재 조회도 동일한 관계의 인가 가드이며 결과는 bool뿐이다. Conversation repository나 mapper를 호출하지 않는다.

조회는 트랜잭션을 종료하지 않는다. 입력과 검색 옵션 검증 뒤 소유권을 확인하고, 권한이 있을 때만 외부 임베딩을 호출한다. 응답은 벡터 1개와 저장소의 1536차원인지 확인하며 임베딩 실패·불일치 응답은 빈 결과로 숨기지 않는다. `embedding_provider`와 `embedding_model`이 `NULL`인 기존 행은 출처가 불명확하므로 호환된 것으로 간주하지 않고 검색에서 제외한다. 이번 변경은 기존 벡터를 재임베딩하거나 metadata를 추정해서 채우지 않는다.

메시지 수정/되돌리기 때 단일 source_message_id는 요약과 파생 기억의 전체 입력 의존성을 표현하지 못하므로 출처가 없는 legacy 기억까지 해당 방 전체를 무효화한다. 다른 방 메모리는 유지한다. source_message_id의 기존 messages FK와 ON DELETE SET NULL은 유지하지만, chat 경유 변경은 먼저 공개 무효화를 수행해 오래된 내용이 남지 않게 한다. memory에서 메시지 ORM을 참조하지 않는다.

작은 모듈이므로 추가 계층 분할 없이 조회와 무효화 command만 분리했다. 임베딩 공급자 구현은 llm 모듈이 소유하므로 기존의 빈 `embeddings.py` 골격은 제거했다. 요약·새 메모리 생성, 기존 벡터 재임베딩, 검색 재정렬은 이번 범위가 아니다.
