# 프로젝트 작업 지침

- 백엔드 코드를 수정하기 전에 [모듈 아키텍처 및 명명 규칙](references_document/reference/module-architecture-and-naming.md)을 읽고 적용한다.
- 작업 대상 모듈의 `ARCHITECTURE.md`가 있으면 함께 읽고, 책임이나 공개 인터페이스를 변경하면 갱신한다.
- 기존 기능과 외부 API 계약을 보존하고, 변경한 동작에 맞는 검증을 수행한다.
- 백엔드 작성 시 [코드 작성 규칙](references_document/reference/backend-code-conventions.md)을 함께 적용한다. 타입 누락의 기존 예외를 늘려 검사를 통과시키지 않는다.
- 패턴 변경 후 `python tools/check_backend_quality.py`를 실행한다(프로젝트 가상환경 Python 사용). 동작을 바꾸는 작업에는 해당 업무 테스트도 실행한다.
