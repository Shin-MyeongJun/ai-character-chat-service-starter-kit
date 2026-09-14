# Prompt 모듈

소유 테이블은 없다. `service.load_template`는 서버 고정 JSON 리소스를 시작 시 로드하고 프로세스 수명 동안 캐시한다. 경로/템플릿 ID를 사용자에게 받지 않으며 누락·파싱·규칙·버전 오류는 TemplateConfigurationError다. hot reload와 코드 대체 규칙은 없다.

`build_prompt(BuildPromptCommand)`는 공개 값 타입만 받아 service 규칙(system), 사용자 제공 reference_data(user), 위치순 user/assistant 이력, 현재 입력을 조합한다. 현재 입력은 ID로 제외 후 한 번 삽입한다. 역할·설정 문구는 JSON이 소유하고 Python은 구조와 검증만 소유한다. 사용자 페르소나는 기존 runtime settings에 있는 경우에만 전달한다.

공급자 중립 JSON envelope `chat_message_format=1`을 기존 GenerateTextCommand.request_json으로 전달한다. llm adapter가 API 형식으로 변환한다. 최종 메시지 UTF-8 byte 수 + 메시지당 32 + 전체 32를 보수적으로 추정한다. tokenizer가 없으므로 정확한 모델별 계산은 아니며 유효한 큰 문맥을 거절할 수 있다. 공급자 usage는 별도의 실제 사용량이다.
