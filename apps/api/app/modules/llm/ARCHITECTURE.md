# LLM 모듈

- 소유 테이블: `providers`, `models`, `model_replacements`.
- `service/text_generation.py`: `TextGenerationService`가 `TextGenerationAdapter`만 등록·선택한다. 기존 공개 이름 `LLMService`, `generate_text(GenerateTextCommand)` → `LLMResultInfo`, `list_model_options()` 계약은 호환 별칭으로 보존한다. 채팅·요약·프로필 추출은 이 단일 텍스트 생성 계약을 공유하며 전용 어댑터를 두지 않는다.
- `service/embedding.py`: `EmbeddingService`가 `EmbeddingAdapter`만 별도로 등록·선택하고 `embed_texts(EmbedTextsCommand)` → `EmbeddingResultInfo`를 제공한다. 텍스트 생성 모델 목록과 등록소를 공유하지 않으므로 같은 공급자 이름의 두 기능이 충돌하지 않는다.
- `adapters/protocols.py`: 서비스가 의존하는 공급자 중립 `TextGenerationAdapter`, `EmbeddingAdapter` Protocol. 모델 선택, 실행, 자원 종료 계약을 선언한다.
- `adapters/base.py`: OpenAI·Anthropic·Mock이 공유하는 텍스트 생성 검증과 오류 envelope 구현인 `BaseTextGenerationAdapter`. 과거 `BaseLLMAdapter` import는 호환 별칭으로만 유지하며 서비스 타입으로 사용하지 않는다.
- `adapters/voyage.py`: 텍스트 생성 base를 상속하지 않는 Voyage 비동기 임베딩 구현. 요청별 텍스트는 지역 값으로 복사하고, query/document·truncation·output dimension을 SDK에 그대로 전달하며 개수·동일 차원·유한 수치·사용량을 검증한다. memory 요약은 document, 답변 검색은 query로 호출한다.
- `types.py`: 텍스트 생성과 분리된 임베딩 Command/Info, 공급자·용도·오류 타입을 공개한다.
- `ModelInfo.context_window`는 기존 DB 모델의 창 크기를 공개해 요청별 예산 상한에 사용한다.
- `adapters/messages.py`는 `GenerateTextCommand.request_json`의 선택적 `chat_message_format=1` envelope를 검증한다. OpenAI는 역할별 input, Anthropic은 system과 user/assistant messages로 변환한다. 마커 없는 기존 문자열 입력과 기존 서비스/어댑터 시그니처는 유지한다. 사용자 HTTP에 envelope나 system 역할을 직접 받지 않는다.
- `service/query.py`: 자체 ModelInfo/ProviderInfo 조회와 모델 설정 검증.
- `service/command/replacement.py`: 모델 종료 공지, 실행 모델 결정 및 멱등적인 대체 이력 저장. 쓰기는 use_case_transaction에 참여한다.
- `service/views/replacement.py`: 상품 스냅샷 설정과 모델 가용성을 조합한 읽기 전용 ModelNoticeView.
- `service/util/replacement_policy.py`: 허용 대체 범위·effort 근접 선택 보조 함수. DB·공급자 호출을 하지 않는다.
- `service/replacement.py`: 역할별 공개 함수의 호환 재노출.
- `repository.py`, `mapper/persistence.py`: 모델/공급자/대체 이력 저장 및 순수 값 변환.

상품 버전은 product 공개 query/types로만 읽으며 상품 스냅샷은 수정하지 않는다. identity 공개 서비스로 관리자 인가를 확인한다. 원본 종료 전 대체 계획, 전환 시점, 허용 모델이 없는 경우의 기존 중단 정책을 유지한다. 반환 ExecutionView는 조합된 실행 설정이다. 타 모듈 JOIN 예외는 없다.

공급자 HTTP 호출은 DB 트랜잭션과 원자적이라고 가정하지 않는다. Voyage는 서버 이벤트 루프를 막지 않는 공식 `AsyncClient`를 사용한다. 재시도는 SDK의 `max_retries` 설정만 소유하고 기본값은 0이며 adapter/service는 추가 재시도를 하지 않는다. 주입 client는 호출자가 소유하고 adapter가 만들었을 때만 SDK가 제공하는 종료 메서드를 호출한다(현재 SDK 0.5.0 client는 종료 메서드가 없어 no-op). 인증·요청 제한·타임아웃·연결·잘못된 요청·잘못된 응답은 `EmbeddingError`로 구분하며 실패를 빈 벡터로 바꾸지 않는다.

공식 Text Embeddings 문서(https://docs.voyageai.com/docs/embeddings)와 API reference(https://docs.voyageai.com/reference/embeddings-api-1)를 2026-09-13에 확인했다. 최신 Voyage 4 계열은 기본 1024차원(선택 256/512/1024/2048)이고 query/document input type을 권장한다. 기존 memory 저장소가 1536차원 고정이고 대규모 재임베딩이 이번 범위 밖이므로 기본 예시는 legacy 호환 `voyage-large-2`(1536차원)를 유지한다. 이 모델은 공급자가 Voyage 3 이상으로 전환을 권고하는 상태다. 저장소 차원 변경과 전체 재임베딩을 함께 계획하기 전에는 Voyage 4 모델로 설정만 바꾸면 안 된다. 실제 공급자 호출은 기본 테스트에 포함하지 않고 `VOYAGE_API_KEY`를 설정한 opt-in 테스트로 구분한다.
