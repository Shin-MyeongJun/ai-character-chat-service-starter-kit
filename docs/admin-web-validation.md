# 관리자 프런트 검증

2026-10-22. `apps/admin_web`. Figma design context 첫 요청에서 Starter 호출 한도 응답을 받아 반복 호출하지 않았다. 최종 PNG `docs/assets/admin-web-design`와 디자인 기록을 확인해 구현했다. Figma/Studio 원본은 변경하지 않았다.

## 수행 결과

| 검증 | 결과 | 경계 |
| --- | --- | --- |
| `pnpm admin:typecheck` | 통과 | 실제 TypeScript |
| `pnpm admin:build` | 통과 | 실제 Next production build |
| `pnpm web:typecheck` | 통과 | 기존 사용자 웹, 루트 명령/lockfile 추가 영향 확인 |
| `pnpm admin:test` | 9 passed | 날짜·필터/URL·원문·fetch 대역 인증 |
| Edge 브라우저 | 26 passed | 실제 Next dev + 별도 합성 HTTP API + 쿠키/프록시/clipboard |
| 1440×1120 / 1280×1120 | 통과 | 실제 렌더/폰트/치수·스크린샷 육안 검수 |

production start(검사용 3101)에서도 로그인 렌더링과 실제 API 미실행 시 보호 본문 차단·재시도 안내, uncaught error 0건을 확인했다. 검사용 서버는 종료했고 개발 서버는 기본 실제 API 주소(8000)로 복구한다. 개발 fixture를 실제 로그인 성공으로 대신하지 않는다.

계약 검사는 서울 날짜 경계, 731일/불가능한 날짜/UUID/상태, 필터/페이지 복원과 외부 복귀 URL 거절, role 순서·원문/복사 보존, CSRF 단회 재시도, 401/403/Origin 분리, 두 독립 클라이언트의 한 번 refresh, 회전 응답 유실 뒤 reload 재전송 금지 및 명시적 로그인 복구를 확인한다.

브라우저는 로그인 진행/실패·직접 접근, 로그인→목록→검색/페이지→상세→복귀, 긴 UUID/모델/원문, 역할별/원본/줄바꿈, 미기록 200/404, 목록·상세 오류/재시도, 빈 결과/로딩, 지연된 이전 검색 차단, 권한 회수·비관리자·세션 만료, 실제 clipboard 성공/실패, 민감 storage 미사용, 탭 간 로그아웃, 키보드 focus와 uncaught error 0건을 확인한다.

표 내부 화면읽기 보조 요소가 문서 세로 길이를 늘리던 문제와, 현재 탭이 자신이 보낸 로그아웃 이벤트를 수신하던 문제를 수정했다. 최종 검사에서 페이지 가로 넘침·표/원문에 의한 불필요한 문서 세로 확장이 없다. 폰트 파일과 OFL은 독립 앱에 존재하며 화면 PNG를 앱 구현 자산으로 사용하지 않는다.

Windows/Edge에서 네이티브 clipboard의 LF→CRLF 정규화를 관찰했다. `writeText`에 전달한 문자열이 원문과 같음을 별도 검사하며, OS에서 읽은 값에는 줄끝 정규화만 허용했다. 앱은 원문을 재직렬화하지 않는다. 붙여넣기의 바이트/digest 동일성까지 보장한다고 표현하지 않는다.

기계 판독 결과: [verification.json](assets/admin-web-implementation/verification.json). [재현 명령](../apps/admin_web/README.md). fixture 검사들은 상태 서버/스크린샷 경로를 공유하므로 동시에 실행하지 않는다.

## 주요 스크린샷

모두 개발 fixture의 합성 계정/데이터다.

- [로그인](assets/admin-web-implementation/login-1440.png)
- [목록 1440](assets/admin-web-implementation/list-1440.png), [목록 1280](assets/admin-web-implementation/list-1280.png)
- [상세 1440](assets/admin-web-implementation/detail-1440.png), [상세 1280](assets/admin-web-implementation/detail-1280.png)
- [원본 JSON](assets/admin-web-implementation/raw-1440.png), [긴 원문 줄바꿈 끔](assets/admin-web-implementation/long-nowrap-1440.png)
- [미기록](assets/admin-web-implementation/unrecorded-1440.png), [생성 404](assets/admin-web-implementation/not-found-1440.png)
- [권한 없음](assets/admin-web-implementation/forbidden-1440.png), [로딩](assets/admin-web-implementation/loading-1440.png), [빈 결과](assets/admin-web-implementation/empty-1440.png), [오류](assets/admin-web-implementation/error-1440.png)

## 실환경 미검증

실제 API `127.0.0.1:8000`은 실행 중이지 않고 검증용 활성 관리자 세션/DB가 없다. backend 코드에서 계약을 확인했지만 실제 API/DB 인가가 통과했다고 보고하지 않는다. fixture는 HttpOnly 쿠키/CSRF/인가 응답을 제공하는 합성 서버이며 실제 DB 역할 검사/refresh rotation은 구현하지 않는다.

실제 관리자 로그인·Origin/CSRF·refresh 회전/응답 유실/로그아웃, 0030 DB 목록·상세·미기록·404, 일반 사용자/moderator/비활성 관리자 차단, 운영 HTTPS/Secure `__Host-` 쿠키, 여러 탭·사용자 웹 동시 사용은 **미검증**이다. [실행 문서](../apps/admin_web/README.md)의 환경을 준비한 뒤 확인해야 한다.

`/admin/session`과 관리자 표시명은 미제공 계약이다. 기존 관리자 목록 GET으로 접근을 확인하며 해당 제한이 해소됐거나 실연동 완료라고 보고하지 않는다.
