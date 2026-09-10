# LLM 모듈

- 소유 테이블: `providers`, `models`, `model_replacements`.
- `service/__init__.py`: 공급자 어댑터를 선택하는 LLMService. `generate_text(GenerateTextCommand)` → LLMResultInfo, `list_model_options()` → ModelOptionInfo 목록. 세션 종료와 컨텍스트 매니저 메서드는 요청 유스케이스가 아닌 자원 수명 관리다.
- `adapters/`: 외부 SDK 호출·결과·오류 정규화. SDK 어댑터의 generate 인자는 내부 공급자 프로토콜이며 모듈 공개 업무 요청은 GenerateTextCommand로 묶는다.
- `service/query.py`: 자체 ModelInfo/ProviderInfo 조회와 모델 설정 검증.
- `service/command/replacement.py`: 모델 종료 공지, 실행 모델 결정 및 멱등적인 대체 이력 저장. 쓰기는 use_case_transaction에 참여한다.
- `service/views/replacement.py`: 상품 스냅샷 설정과 모델 가용성을 조합한 읽기 전용 ModelNoticeView.
- `service/util/replacement_policy.py`: 허용 대체 범위·effort 근접 선택 보조 함수. DB·공급자 호출을 하지 않는다.
- `service/replacement.py`: 역할별 공개 함수의 호환 재노출.
- `repository.py`, `mapper/persistence.py`: 모델/공급자/대체 이력 저장 및 순수 값 변환.

상품 버전은 product 공개 query/types로만 읽으며 상품 스냅샷은 수정하지 않는다. identity 공개 서비스로 관리자 인가를 확인한다. 원본 종료 전 대체 계획, 전환 시점, 허용 모델이 없는 경우의 기존 중단 정책을 유지한다. 반환 ExecutionView는 조합된 실행 설정이다. 타 모듈 JOIN 예외는 없다.

공급자 HTTP 호출은 DB 트랜잭션과 원자적이라고 가정하지 않는다. 이번 검증은 공급자 mock 기반이며 실제 API 키, 네트워크 호출, 운영 알림·주기 작업 배포는 포함하지 않는다. 모델 공지/실행 변경과 읽기 전용 안내를 분리하고 순수 선택 로직만 util에 두었다.
