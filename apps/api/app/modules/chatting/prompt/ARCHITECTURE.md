# Prompt 모듈

소유 테이블은 없다. `service.load_template`는 서버 고정 JSON 리소스를 시작 시 로드하고 프로세스 수명 동안 캐시한다. 경로/템플릿 ID를 사용자에게 받지 않으며 누락·파싱·규칙·버전 오류는 TemplateConfigurationError다. hot reload와 코드 대체 규칙은 없다.

`build_prompt(BuildPromptCommand)`는 공개 값 타입만 받아 service 규칙(system), 사용자 제공 reference_data(user), 위치순 user/assistant 이력, 현재 입력을 조합한다. 현재 입력은 ID로 제외 후 한 번 삽입한다. 역할·설정 문구는 JSON이 소유하고 Python은 구조와 검증만 소유한다. 사용자 페르소나는 기존 runtime settings에 있는 경우에만 전달한다.

공급자 중립 JSON envelope `chat_message_format=1`을 기존 GenerateTextCommand.request_json으로 전달한다. llm adapter가 API 형식으로 변환한다. 최종 메시지 UTF-8 byte 수 + 메시지당 32 + 전체 32를 보수적으로 추정한다. tokenizer가 없으므로 정확한 모델별 계산은 아니며 유효한 큰 문맥을 거절할 수 있다. 공급자 usage는 별도의 실제 사용량이다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: `resources/default.json` → `load_template` → `build_prompt` → types → `llm/adapters/messages.py`. JSON은 실행 입력이므로 이번 점검에서는 변경하지 않았다. `test_answer_prompt`와 `test_llm`의 중립 봉투/사용량 경계를 대조한다.

설정·시작 장면·활성 로어·기억은 reference_data에 담긴다. 로어에 저장된 placement를 system 권한으로 승격하거나 항목별 token_budget을 여기서 적용하지 않는다. 미요약 원문을 버릴지 판단하는 책임은 앞선 answer_preparation에 있다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.

2026-09-22: 비스트리밍 답변은 이 기존 추정을 `utf8-bytes-plus-32-per-message-plus-32-v1`로 식별하여 billing 견적 입력에 사용한다. 견적에 사용한 동일 request_json을 실행하며 실제 usage 토큰으로 예약액을 재계산하지 않는다. 산정 알고리즘 자체는 변경하지 않았다.


2026-09-27: 자체 `PromptMessageInfo(id, sender_type, content, position)`를 입력으로 받는다. chat mapper가 순수 변환하며 prompt는 chat.types나 업무 서비스로 재료를 수집하지 않는다. runtime의 opening_message가 있으면 고정 assistant 시작 문맥으로 한 번 넣는다. 현재 버전 settings의 opening_message는 conversation 경계에서 제거하고 start는 최초 선택 장면을 사용한다. legacy에서는 opening_message=null이므로 기존 메시지 이력만 전달된다. 첫 대사도 최종 렌더링 예산에 포함하며 일반 메시지 요약에는 저장하지 않는다.

## 소비부 타입·참조 JSON 계약 (2026-10-28)

prompt 디렉터리 전체를 엄격 검사에 포함했다. 내부 _ReferenceData/_CharacterReference/
_SceneReference TypedDict로 캐릭터 JSON·설정·nullable 제목의 장면·활성 로어·기억 목록을
구분한다. 출력 키·순서와 일반 JSON dict/list 표현은 같다. history의 seen은 UUID 집합이다.
외부 모듈의 공개 types만 참조하며 DB/업무 서비스 의존성을 추가하지 않는다.

렌더러는 기존부터 start.title/content와 명시된 lore metadata의 get을 직접 사용했다.
이번에는 start 객체 및 supplied metadata가 None이 아니라는 전제를 assertion으로 명시한다.
장면 없음/명시적 null metadata는 계속 실패하며 빈 장면·빈 metadata로 보정하지 않는다.
이 두 잘못된 내부 입력의 예외는 이전 AttributeError에서 AssertionError로 바뀐다.
기존의 답변 캐릭터·현재 사용자 역할 검증이 먼저 실행되고 정상 입력의 정책은 같다.
metadata 생략은 {}, 빈 activation_options는 기존 truthiness에 따라 legacy 위치다.

_has_positioned_lore는 metadata의 activation_options truthiness만 구별한다. 옵션/placement
검증이나 로어 선택을 중복 수행하지 않는다. 레거시 로어는 기본 참조 메시지, 옵션이 있는
로어는 기존 before_history/after_history 메시지로 배치한다. 첫 대사·이력·현재 입력 순서,
권한 역할·현재 ID 중복 제거와 토큰 추정 알고리즘을 유지한다.

test_prompt_type_contracts의 11건은 기존 구현에서 산출한 고정 입력의 request_json SHA-256
d85cff1b1487f9058994c06408ae8ad2a5a755d348d091d7b243bf94e10393f9 및 1,625 추정 토큰을
확인한다. 한국어·선택 대상·장면 null 제목·로어 배치·첫 대사와 이력 순서, 입력 비변경,
opening 생략/빈 문자열 구분과 무효 내부 입력/이력/답변 대상 거절도 확인한다. 실제 모델의
응답 품질·정확한 tokenizer 비용·운영 호출은 검증하지 않는다.
