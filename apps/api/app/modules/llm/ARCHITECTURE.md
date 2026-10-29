# LLM 모듈

- 소유 테이블: `providers`, `models`, `model_replacements`.
- `service/text_generation.py`: `TextGenerationService`가 `TextGenerationAdapter`만 등록·선택한다. 기존 공개 이름 `LLMService`, `generate_text(GenerateTextCommand)` → `LLMResultInfo`, `list_model_options()` 계약은 호환 별칭으로 보존한다. 현재 답변과 메모리 요약이 이 텍스트 생성 계약을 사용한다. 별도 프로필 추출 유스케이스는 현재 코드에 없다.
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

## 저장소·mapper·조회 타입 계약

- `repository.py`와 `service/query.py`의 실행 의존성은 현재 세션인 `AsyncSession`이다. 세션 생성·종료나 commit/rollback을 맡지 않는다. 기존 위치/키워드 인자 이름과 호출 형태를 유지한다.
- 공개 조회 입력은 `GetModelCommand(model_id: UUID)`, `GetProviderCommand(provider_id: UUID)`, `ValidateModelCommand(model_id: UUID, reasoning_effort: str)`이다. 요청 값이 없는 `list_candidate_models(session)`에는 빈 Command를 추가하지 않는다.
- 저장소 단건 반환은 `Model | None`, `Provider | None`, `ModelReplacement | None`이며 후보 목록은 `list[Model]`이다. 현재 별도 Row 캐리어는 없다. service는 Entity를 임시 보유해 persistence mapper에 전달하며, 공개 반환은 `ModelInfo | None`, `ProviderInfo | None`, `list[ModelInfo]`로 한정한다.
- 모델/공급자 단건 조회는 UUID 기본 키만 사용하고 비활성·종료 모델도 반환한다. 미존재는 mapper를 거쳐 그대로 `None`이다. 후보 조회는 `Provider.is_enabled IS TRUE`인 공급자와의 내부 JOIN만 적용한다. 모델 활성·종료·capability 조건이나 ORDER BY를 추가하지 않는다. DB 결과 순서는 보장하지 않으며 mapper는 전달된 순서와 빈 목록을 보존한다.
- persistence mapper는 명시된 Entity 필드만 Info로 옮긴다. 모델/공급자 변환은 비-null 입력이면 비-null Info, `None`이면 `None`인 overload 계약이다. 모델의 nullable 종료 일정과 저장된 context window를 유지하며 capabilities만 깊게 복사해 중첩 가변 값까지 분리한다. 대체 이력 mapper는 `ModelReplacement | None`을 존재 여부 `bool`로 변환할 뿐 업무 판단·DB/공급자 호출을 하지 않는다.
- `validate_model`은 변환된 Info로 모델/공급자 활성 여부, `shutdown_at <= 현재 UTC`, 저장된 `reasoning_efforts` 포함 여부를 판단한다. 미존재·비활성·종료는 기존 `ValueError("Model is unavailable.")`, 미지원 effort는 기존 `ValueError("Model does not support this reasoning effort.")`를 유지한다. 별도 정규화나 SDK 지원 목록 검증은 추가하지 않는다.
- 대체 이력은 `snapshot_id`, `from_id`, `to_id` 세 UUID가 모두 일치하는 항목만 조회하며 미존재는 `None`이다. 생성은 전달된 effort 문자열·effective_at을 저장하고 flush 후 `None`을 반환한다. 종료 공지 갱신은 기존 모델 행 잠금(`with_for_update=True`) 후 일정을 저장·flush하고 `Model`을 반환하며 미존재는 flush 없이 `None`이다. 트랜잭션 경계는 기존 호출자가 소유한다.
- 이번 타입 정리 범위는 저장소·persistence mapper·query에 한정한다. `types.py`와 DB 모델의 기존 capabilities bare dict, replacement command/views/util 및 외부 호출부의 남은 타입 정리는 후속 연결 지점이다. 이 경계의 공개 계약이나 공급자 실행 경로는 변경하지 않는다.
- 전용 오프라인 검증: `test_llm_persistence_contracts`(SQLite 조회 조건, mapper 값/깊은 복사/순서, nullable 반환, 검증 오류, flush·잠금 요청). PostgreSQL의 실제 행 잠금·제약·동시성 보장은 이 테스트의 검증 범위 밖이다.

상품 버전은 product 공개 query/types로만 읽으며 상품 스냅샷은 수정하지 않는다. identity 공개 서비스로 관리자 인가를 확인한다. 원본 종료 전 대체 계획, 전환 시점, 허용 모델이 없는 경우의 기존 중단 정책을 유지한다. 반환 ExecutionView는 조합된 실행 설정이다. 타 모듈 JOIN 예외는 없다.

공급자 HTTP 호출은 DB 트랜잭션과 원자적이라고 가정하지 않는다. Voyage는 서버 이벤트 루프를 막지 않는 공식 `AsyncClient`를 사용한다. 재시도는 SDK의 `max_retries` 설정만 소유하고 기본값은 0이며 adapter/service는 추가 재시도를 하지 않는다. 주입 client는 호출자가 소유하고 adapter가 만들었을 때만 SDK가 제공하는 종료 메서드를 호출한다(현재 SDK 0.5.0 client는 종료 메서드가 없어 no-op). 인증·요청 제한·타임아웃·연결·잘못된 요청·잘못된 응답은 `EmbeddingError`로 구분하며 실패를 빈 벡터로 바꾸지 않는다.

공식 Text Embeddings 문서(https://docs.voyageai.com/docs/embeddings)와 API reference(https://docs.voyageai.com/reference/embeddings-api-1)를 2026-09-13에 확인했다. 최신 Voyage 4 계열은 기본 1024차원(선택 256/512/1024/2048)이고 query/document input type을 권장한다. 기존 memory 저장소가 1536차원 고정이고 대규모 재임베딩이 이번 범위 밖이므로 기본 예시는 legacy 호환 `voyage-large-2`(1536차원)를 유지한다. 이 모델은 공급자가 Voyage 3 이상으로 전환을 권고하는 상태다. 저장소 차원 변경과 전체 재임베딩을 함께 계획하기 전에는 Voyage 4 모델로 설정만 바꾸면 안 된다. 실제 공급자 호출은 기본 테스트에 포함하지 않고 `VOYAGE_API_KEY`를 설정한 opt-in 테스트로 구분한다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: text_generation/embedding 서비스 → adapters/protocols → 개별 adapter → types. DB 실행 모델 결정은 query → command/replacement → util/replacement_policy → repository의 별도 경로다.

대체 이력의 중복 방지는 동일 스냅샷·원본·대상 조합 범위다. resolve_execution은 후보를 매번 다시 선택하므로 이전 대상이 영구 고정된다는 뜻은 아니다. SDK 지원 모델 판정과 DB의 모델 활성/effort 검증도 별개다.

클라이언트 종료 책임은 어댑터별로 다르다. Voyage는 직접 만든 client만 닫지만 OpenAI/Anthropic은 주입 client에도 close가 있으면 호출한다. usage의 None은 미제공이며 0과 다르다. 공급자 문서·SDK 버전 언급은 위에 기록된 과거 확인 시점의 설명이고 이번 검토는 로컬 구현과 mock 테스트를 근거로 한다.

관련 테스트: `test_llm`, `test_embeddings`, `test_model_replacement`, `test_product_lifecycle`. `test_voyage_integration`은 VOYAGE_API_KEY가 있으면 실제 호출하므로 mock 검증과 구분한다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../references_document/backend_review/README.md)에 모았다.

## 모델 대체·공개 타입 정리 (2026-10-28)

types.py와 service 디렉터리 전체를 기존 repository/mapper와 함께 공용 엄격 검사에
편입했다. ModelInfo.capabilities는 DB JSONB의 개방형 재귀 JSON 사전으로 표현한다.
ModelCapabilities는 알려진 model_family/reasoning_efforts만 읽는 별도 TypedDict 뷰다.
확장 키·저장 JSON·mapper의 깊은 복사와 None/빈 값은 유지한다. ModelInfo의 사전 자체를
닫힌 TypedDict로 바꾸거나 새로운 런타임 JSON 검증을 추가하지 않았다.

SnapshotModelSettings는 product가 기록한 id/reasoning_effort 문자열의 읽기 뷰다.
종료 공지/실행 결정/읽기 전용 notice의 세션은 AsyncSession이며 후보/지원 effort는
Iterable, 정책은 Mapping으로 표현한다. 반환과 선택 후보의 순위 tuple도 명시했다.
원본 model_entity와 replacement_entity를 구별하고 업무 판단은 기존 mapper/Info 뒤다.

cast 7곳은 catalog effort 3개 소비부(query/정책/HTTP), allowlist container, snapshot 모델
설정 2곳, notice의 unavailable 문자열을 연결한다. 원래 membership·비문자열 effort
필터·누락 기본값·손상 데이터 오류를 바꾸지 않는다. Any/ignore/기준선 예외는 추가하지
않았다. HTTP 카탈로그의 비문자열 effort 제거도 그대로다.

same_family/same_provider/allowlist, 모델 활성/종료 경계, 같은 계열→같은 공급자→effort
거리→UUID 문자열의 후보 순위와 effort 동률의 낮은 단계 우선 규칙을 유지한다. 공지 후
deadline=max(공지,종료-1일) 계획과 해당 시각의 전환, 원본 임시 사용/일시 중단 정책,
snapshot 잠금·상위 트랜잭션·snapshot/from/to 단위 이력 존재 확인/삽입도 같다.
기존 이력은 후보를 고정하지 않으며 매 요청에서 현재 후보를 다시 선택한다.
notice는 이력을 쓰지 않는 안내이며 실행에서는 다시 판단한다. SDK 호출은 없다.

test_model_replacement_contracts는 종료/마감 전후 notice와 실행의 일치, 대체 불가 시
원본 사용 한계, 기존 대상 이력의 삽입 생략과 새 후보 재선택, disabled/종료/미지원 후보
배제·UUID/effort 동률, 관리자 거절과 미존재 오류를 오프라인으로 확인한다. 실제 행
잠금·유일 제약·동시성이나 외부 공급자 지원을 증명하지 않는다. 어댑터 디렉터리 전체의
엄격 타입 완료는 후속 범위다.

## 공급자 SDK 경계 타입 정리 (2026-10-28)

OpenAI/Anthropic/Voyage client와 응답 helper의 명시적 Any를 제거하고 LLM 모듈 전체를
엄격 검사에 편입했다. 초기 adapter mypy는 Any 때문에 진단 없이 통과하던 상태였으므로
이를 기존 mypy 오류 해결 수로 계산하지 않는다. 요청 kwargs의 Any 사전도 TypedDict로
표현했다. sdk.py는 기존 adapters 내부의 client Protocol·요청 필드·중복 dict/속성 읽기를
모으는 파일이며 새 실행 계층이나 SDK wrapper를 만들지 않는다.

client 생성/주입 경계 cast 3개와 문자열/정수/반복 응답 필드 읽기 cast 3개는 SDK 계약을
표현한다. 응답 투영은 dict·SDK 객체·SimpleNamespace 모두의 기존 기본값/참조를
보존하며 값 변환·필터·검증을 하지 않는다. 잘못된 bool/count 등 원래 전달되거나 실패하던
값을 조용히 정상화하지 않는다. 실제 유효성 검사는 기존 호출자 책임을 유지한다.

공급자 원시 응답 변수는 provider_response로 구별했다. OpenAI output_text·refusal·
incomplete 원인과 usage 상세, Anthropic text-only 블록 결합·cache 포함 알려진 토큰
합계와 stop 원인, Voyage 요청 검증·벡터/차원/유한 수치·usage 검증은 같다. SDK 호출
오류 변환과 호출 후 extraction 오류의 경계, SDK 설정 외 재시도 없음도 유지한다.
종료는 OpenAI/Anthropic의 주입 client 포함 선택적 async close, Voyage의 자체 생성
client만 sync/async 종료하는 기존 책임을 그대로 둔다.

로컬 설치 버전은 openai 2.54.0, anthropic 0.125.0, voyageai 0.5.0으로 확인했다.
실제 SDK response/exception 모델을 사용하는 기존 테스트와 mock 회귀를 실행했고
SDK 버전·API·모델을 업그레이드하거나 실제 공급자 요청을 보내지 않았다. OpenAI의
[output_text 계약](https://developers.openai.com/api/docs/guides/text?lang=python)과
[client 종료 설명](https://developers.openai.com/api/reference/python)도 공식 문서에서
대조했다. 문서는 설치 SDK 동작을 바꾸는 근거로 사용하지 않았다.

test_llm_sdk_contracts는 dict 응답의 누락 usage/0/손상 bool 원본, 공급자별 total 처리,
malformed Anthropic usage의 호출 후 TypeError, 선택적 close와 원래 종료 실패 전파를
오프라인으로 확인한다. 기존 SDK 모델/오류 subclass·메시지/usage·Voyage 소유권 검증도
유지한다. 실제 공급자 지원/네트워크/timeout/운영 SDK 업그레이드 검증은 아니다.
