# 백엔드 현황 점검 — 2026-10-06

현재 소스, HTTP 등록, 모듈 ARCHITECTURE 및 최근 작업 기록을 대조했다. 기능 코드와 기존 사용자 변경은 수정하지 않았다. 구현 여부와 이번 실행 검증을 구분한다.

## 현재 구현 범위

| 영역 | 확인 결과 |
| --- | --- |
| identity | 자체 가입, 이메일 인증, 재설정, Google OIDC, 쿠키 세션, CSRF, 인증 요청 제한 구현 |
| character / lorebook / product | 콘텐츠 CRUD, 상품 구성·발행·스냅샷·버전 정책 구현. 미디어 업로드·읽기·정리 workflow 존재 |
| conversation / chat | 대화·메시지 CRUD, 최초 시작 내용 별도 조회, 비스트리밍 단일 캐릭터 답변, 중복 요청·실패·저장 복구 구현 |
| prompt / memory / llm | 프롬프트 구성, 요약·임베딩·검색·무효화, durable memory worker, 공급자 어댑터 구현 |
| billing / credit | 가격 설정·견적, 재화별 FREE/PAID 지갑·지급·예약·확정·해제·원장, 답변 과금 연결 구현 |
| admin / moderation | 콘텐츠 조회·상태 변경 및 상품/모델 관리 일부 구현. character/lorebook 관리자·검수 HTTP 권한 훅은 기본 503 |
| 통계 | product 집계 저장·조회, use_cases/product_statistics.py 조합, 작업 큐 및 CLI 구현. reporting으로 독립하지 않음 |

구현된 핵심 경로가 있으나 신규 설치 후 곧바로 모든 서비스를 사용할 수 있는 완성 상태는 아니다. 가격 JSON과 사용 가능한 모델 설정, 사용자 지갑 준비·지급 경로가 필요하다. 지갑/가격 미설정 시 답변은 명시적으로 거절한다. 가입만으로 크레딧이 지급되지는 않는다.

## 권장 작업 순서

1. **첫 사용자 사용 흐름 완성**: 승인된 가격 설정, 신규 지갑 준비·지급 정책, 잔액/원장 조회 HTTP 연결. 기존 identity와 credit 공개 service를 조합하고 회원가입 서비스에 결제 책임을 넣지 않는다. 실결제 없이도 개발·체험 지급 정책으로 검증 가능하다.
2. **역할 권한 연결**: identity의 활성 사용자·역할 검증을 admin/moderation HTTP dependency에 연결. 역할별 허용/거절 및 변경 불가 검증이 필요하다.
3. **moderation 확장**: 신고 접수·조회·처리와 감사 기록. moderation_flags/audit_logs 모델의 존재는 기능 구현을 의미하지 않는다. 감사 기록을 여러 도메인이 공통 사용하게 되면 독립 audit 모듈을 검토한다.
4. **운영 실행 구성**: API·memory worker·통계·auth/media 정리 실행과 스케줄링, 상태 확인·관측, 배포 및 migration 절차. 현재 Compose는 PostgreSQL/Redis와 선택 Mailpit만 제공한다.
5. **payment 신규 모듈**: PG를 도입할 때 결제 주문·승인·웹훅 검증·중복 방지·취소/환불·대사를 소유한다. 검증된 결제만 credit 지급 및 billing 귀속 기록에 연결한다. 실결제가 현재 완료 범위 밖이면 후속으로 둔다.
6. **reporting 신규 모듈**: 현재 통계 조합의 이동 후보. 이미 통계가 있으므로 새로 만드는 것보다 실행·저장·큐 경계를 정하고 점진 이전한다. MVP의 선행 조건은 아니다.

구독이 필요하면 subscription 책임을 별도로 설계한다. 현재 subscription_plans/user_subscriptions는 모델만 있고 구독 업무는 미구현이다. profile·동의·본인확인은 요구가 생길 때 추가한다. 빈 모듈을 미리 만들 필요는 없다.

## 기존 기능의 후속 확인

- 스트리밍, 자동 다중 답변, 번역은 현재 비스트리밍 범위 밖이다. 우선 chat 확장으로 검토한다.
- 로어 placement/priority/token_budget 등의 저장과 실제 선택·배치·항목별 예산 정책은 구분해야 한다. lorebook/prompt 기존 모듈의 정책 작업이다.
- memory worker에는 lease 주기 갱신이 없다. 긴 공급자 호출과 재획득이 겹치는 비용·중복 호출 경계를 검증해야 한다.
- 과거 점검 F02의 시작 옵션 제목 문제는 현재 DTO도 title: str이므로 재검증 대상이다. F03의 기본 이미지 중복 오류 전달도 추가 검증 대상이다. 이번에 DB/HTTP로 재현한 결함으로 표현하지 않는다.
- 과거 F01의 버전 전환 후 최초 시작 조회 문제는 9월 27일 workflow 작업 기록에서 해결로 보고되어 있다.
- legacy 크레딧은 FREE/PAID 분류 근거 승인 전 차단하는 기존 계약을 유지한다. 임의 이관이나 guard 제거는 후속 작업으로 잡지 않는다.

## 검증 및 한계

이번 실행: 아키텍처/OpenAPI 경계와 프롬프트 순수 구성 테스트 **21 passed, 2 deselected**. 공급자 변환 2개는 제외했다. pytest 캐시 쓰기 권한 경고가 있었다.

전체 테스트 및 넓은 회귀 실행은 일부 테스트 이후 진행이 멈춰 중단했다. 완료 결과나 실패 원인은 확정하지 않는다. Docker API 접근도 permission denied여서 DB 통합 검증을 재실행하지 못했다. 외부 공급자·SMTP·S3·배포 검증은 이번에 수행하지 않았다.

이전 검증 참고: docs/backend-workflow-refactor-progress.md는 전체 실행 후 필요한 부분 재검증을 합쳐 656개 통과·외부 선택 4개 미실행을 기록한다. 이는 이번 실행 결과가 아니다.

references_document/backend_review의 9월 17일 기록에는 인증·차감 미구현 등 과거 상태가 남아 있다. 현재 현황은 최신 identity/credit/billing 문서와 billing-generation-integration.md, backend-workflow-refactor-progress.md를 우선해서 읽는다.
