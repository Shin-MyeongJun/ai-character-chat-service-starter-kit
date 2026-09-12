# LLM 모듈

- 소유 테이블: `providers`, `models`, `model_replacements`.
- `service/text_generation.py`: `TextGenerationService`가 `TextGenerationAdapter`만 등록·선택한다. 기존 공개 이름 `LLMService`, `generate_text(GenerateTextCommand)` → `LLMResultInfo`, `list_model_options()` 계약은 호환 별칭으로 보존한다. 채팅·요약·프로필 추출은 이 단일 텍스트 생성 계약을 공유하며 전용 어댑터를 두지 않는다.
- `service/embedding.py`: `EmbeddingService`가 `EmbeddingAdapter`만 별도로 등록·선택하고 `embed_texts(EmbedTextsCommand)` → `EmbeddingResultInfo`를 제공한다. 텍스트 생성 모델 목록과 등록소를 공유하지 않으므로 같은 공급자 이름의 두 기능이 충돌하지 않는다.
- `adapters/protocols.py`: 서비스가 의존하는 공급자 중립 `TextGenerationAdapter`, `EmbeddingAdapter` Protocol. 모델 선택, 실행, 자원 종료 계약을 선언한다.
- `adapters/base.py`: OpenAI·Anthropic·Mock이 공유하는 텍스트 생성 검증과 오류 envelope 구현인 `BaseTextGenerationAdapter`. 과거 `BaseLLMAdapter` import는 호환 별칭으로만 유지하며 서비스 타입으로 사용하지 않는다.
- `adapters/voyage.py`: 텍스트 생성 base를 상속하지 않는 Voyage 비동기 임베딩 구현. 요청별 텍스트는 지역 값으로 복사하고, query/document·truncation·output dimension을 SDK에 그대로 전달하며 개수·동일 차원·유한 수치·사용량을 검증한다.
- `types.py`: 텍스트 생성과 분리된 임베딩 Command/Info, 공급자·용도·오류 타입을 공개한다.
- `service/query.py`: 자체 ModelInfo/ProviderInfo 조회와 모델 설정 검증.
- `service/command/replacement.py`: 모델 종료 공지, 실행 모델 결정 및 멱등적인 대체 이력 저장. 쓰기는 use_case_transaction에 참여한다.
- `service/views/replacement.py`: 상품 스냅샷 설정과 모델 가용성을 조합한 읽기 전용 ModelNoticeView.
- `service/util/replacement_policy.py`: 허용 대체 범위·effort 근접 선택 보조 함수. DB·공급자 호출을 하지 않는다.
- `service/replacement.py`: 역할별 공개 함수의 호환 재노출.
- `repository.py`, `mapper/persistence.py`: 모델/공급자/대체 이력 저장 및 순수 값 변환.

상품 버전은 product 공개 query/types로만 읽으며 상품 스냅샷은 수정하지 않는다. identity 공개 서비스로 관리자 인가를 확인한다. 원본 종료 전 대체 계획, 전환 시점, 허용 모델이 없는 경우의 기존 중단 정책을 유지한다. 반환 ExecutionView는 조합된 실행 설정이다. 타 모듈 JOIN 예외는 없다.

공급자 HTTP 호출은 DB 트랜잭션과 원자적이라고 가정하지 않는다. Voyage는 서버 이벤트 루프를 막지 않는 공식 `AsyncClient`를 사용한다. 재시도는 SDK의 `max_retries` 설정만 소유하고 기본값은 0이며 adapter/service는 추가 재시도를 하지 않는다. 주입 client는 호출자가 소유하고 adapter가 만들었을 때만 SDK가 제공하는 종료 메서드를 호출한다(현재 SDK 0.5.0 client는 종료 메서드가 없어 no-op). 인증·요청 제한·타임아웃·연결·잘못된 요청·잘못된 응답은 `EmbeddingError`로 구분하며 실패를 빈 벡터로 바꾸지 않는다.

기본 설정 예시는 고정된 memory 저장 차원과 맞는 `voyage-large-2`(1536차원)를 사용한다. 최신 Voyage 4 계열 기본 1024차원은 현재 memory 컬럼과 호환되지 않으므로 저장소 마이그레이션 및 재임베딩 없이 검색 모델로 전환하지 않는다. 실제 공급자 호출은 기본 테스트에 포함하지 않고 `VOYAGE_API_KEY`를 설정한 opt-in 테스트로 구분한다.
