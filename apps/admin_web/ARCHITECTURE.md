# 관리자 웹

독립 Next.js 앱이다. 사용자 웹의 컴포넌트·CSS·업무 모듈을 import하지 않는다.

| 경로 | 책임 |
| --- | --- |
| app | 라우트·레이아웃, 관리자 전용 tokens.css/globals.css |
| components/ui | 버튼·입력·배지·선택·브랜드 |
| components/admin-shell.tsx | 계정 및 서버 인가 확인, 공통 탐색/레이아웃·탭 인증 동기화 |
| components/query-state.tsx | 조회 로딩·오류·빈 상태 |
| components/generation-prompts | 기능 전용 표·필터·메타데이터·원문 뷰어 |
| lib/contracts.ts | 현재 backend DTO 타입·상태·엔드포인트 |
| lib/api.ts | no-store fetch·CSRF·쿠키 인증·refresh 잠금/응답 불확실성 |
| lib/filters.ts | 서울 날짜·허용 필터/페이지 URL·검증·안전 복귀 경로 |
| lib/prompt.ts | 역할별 순수 파싱·원본 문자열 복사 |
| tests | fetch 대역 계약 테스트·독립 개발 fixture·브라우저 검사 |

`/auth/me`는 식별만 담당한다. 권한은 기존 관리자 목록 GET의 성공으로 확인하고 각 조회에서 서버가 최신 DB 인가를 수행한다. `/admin/session`을 가정하거나 role·localStorage로 인가하지 않는다.

조회 데이터는 화면 메모리에만 둔다. 검색은 AbortController·effect 유효성·응답 query key로 이전 응답의 덮어쓰기를 막는다. 민감 원문은 상세에서만 받고 서버 컴포넌트 캐시/props, browser storage, 콘솔/분석 도구에 남기지 않는다.

회전형 refresh는 중복 전송 시 세션을 폐기하므로 같은 origin의 Web Locks로 로그인/로그아웃/refresh를 직렬화한다. 응답 불확실성의 불리언 하나만 localStorage에 둔다. 사용자/관리자 앱은 서로 다른 호스트와 host-only 쿠키로 격리한다. 포트만 다른 같은 호스트 배치는 지원 경계 밖이다.

실행·배포·현재 계약 제한과 실환경 미검증은 [README](README.md), [검증 기록](../../docs/admin-web-validation.md)에 둔다.
