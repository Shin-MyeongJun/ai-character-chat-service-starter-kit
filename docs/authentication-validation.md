# 인증 구현 검증 기록

실행일: 2026-09-18. Windows, Python 3.12, PostgreSQL 17.11, Mailpit 1.31.1에서 확인했다. 기존 미커밋 `references_document/` 내용과 실제 `.env`를 변경하지 않았다. 실제 비밀값은 추가하지 않았다.

## 최종 결과

- 백엔드 전체: **349 passed, 89 skipped, 실패 0**.
- 인증 전용 4개 파일: **50 passed**. 기존 아키텍처·OpenAPI 계약 7개를 함께 실행한 결과는 **57 passed**.
- 변경 Python 파일의 Ruff 검사와 format 검사 통과. `git diff --check` 통과.

Docker Desktop 자체 초기화 오류로 compose 테스트 DB를 시작하지 못했다. 대신 공식 EDB PostgreSQL Windows 바이너리의 별도 localhost 클러스터와 공식 Mailpit Windows 바이너리를 사용했다. 인증 테스트는 임의 스키마를 생성/삭제했고 제품 DB에는 마이그레이션을 실행하지 않았다. 테스트 SMTP 수신함은 외부로 메일을 전달하지 않는 로컬 Mailpit이다.

## 실제 실행한 범위

| 범위 | 확인 내용 |
|---|---|
| 자체 인증 HTTP | 가입→미인증 로그인 거절→이메일 확인→로그인→현재 사용자/검증된 UUID→갱신→현재 로그아웃 |
| 비밀번호 | Argon2id, 긴 Unicode 비밀번호, 길이 거절·무절단, 재설정 요청/완료 및 이전 비밀번호 거절 |
| 세션 | 현재/전체 폐기, 비밀번호 재설정의 전체 폐기, 폐기 Access 거절, 서버 절대 만료, 회전 시 만료 불연장 |
| 경쟁 조건 | 정규화 중복 가입 경합, 인증·재설정 토큰 동시 사용, refresh 동시 갱신 및 응답 유실 후 재사용 시 계열 폐기 |
| 요청 제한 | 독립 서비스/DB 연결 경합, **4개의 실제 자식 프로세스**에서 8회 요청 중 설정 한도 3회만 허용 |
| JWT/OIDC 암호 경계 | 위조 서명, 만료, issuer/audience/type/algorithm·필수 claim 오류, 임시 RSA 키를 이용한 Google 서명·nonce·azp·email_verified 검증 |
| Google HTTP 모의 흐름 | 최소 scope, 고정 callback, state/브라우저 flow 쿠키, PKCE challenge/verifier, nonce 전달, callback 재사용 거절, sub 식별, 이메일 충돌 비병합, 전용 계정 재설정 차단 |
| HTTP 보안 | Secure/HttpOnly/SameSite/host-only 쿠키, CSRF 누락·불일치, Origin 누락·외부 출처, CORS 비허용, 안전하지 않은 redirect, 다른 쿠키 인증 API의 상태 변경 보호 |
| 민감정보 | DB에 원본 일회용 토큰 대신 해시, 비밀번호 해시, 응답의 최소 사용자 필드, 422 입력 비반사, 비밀번호/이메일 로그 비노출, OAuth access log query 제거 |
| SMTP | **실제 Mailpit에 인증·재설정 메일 발송 후 수신 본문의 토큰을 HTTP로 사용**, SMTP 장애의 명시적 오류 |
| Alembic 0020 | 실제 PostgreSQL에서 legacy 사용자 보존, ORM과 migration 구조 일치, init SQL 동일성, 정규화 충돌 시 전체 중단, 인증 데이터가 있으면 downgrade 거절 |
| 기존 기능 | 기존 OpenAPI 경로/스키마 유지, 모듈 import/mapper/service 경계, 기존 앱 수명·의존성 조립과 실행 가능한 기존 회귀 검사 |

## 건너뛴 범위와 외부 확인 필요 사항

89개 skip 중 87개는 기존 공통 `db` fixture의 `TEST_DATABASE_URL` 미설정 때문이다. 해당 테스트는 전체 상품·채팅·메모리·미디어 스키마와 pgvector 확장을 요구한다. 이번 별도 PostgreSQL에는 vector 확장을 설치하지 않았고, 인증 전용 `TEST_AUTH_DATABASE_URL`로 인증 테이블을 실제 검증했다. 따라서 기존 전체 baseline→head 및 전체 init SQL/ORM 비교, 기존 상품·채팅·미디어의 DB 통합 검사가 통과했다고 주장하지 않는다.

나머지 2개는 실 S3 검증 플래그/설정, 실 Voyage API 키가 필요한 기존 외부 연동 검사다. 미디어 S3 검사는 위 DB fixture 제한에도 포함된다.

실제 Google 사용자 로그인·동의 화면·실 Google code 교환은 client ID/secret과 등록된 callback, 테스트 사용자 설정이 없어 확인하지 않았다. 자동 검사는 모의 공급자 응답과 로컬 RSA 서명으로 검증 경계를 확인했다. 운영 SMTP의 인증/TLS·외부 메일 도착률, 운영 HTTPS 프록시·브라우저 쿠키, 실제 운영 데이터 마이그레이션, 배포 스케줄러 실행은 별도 환경에서 확인해야 한다. [실행 및 연동 문서](authentication.md)에 절차를 제공한다.

초기 실행에서 발견한 테스트 임시 폴더 권한/Windows 긴 경로 오류는 새 짧은 `--basetemp`로 해결했다. 기존 앱 수명 테스트에는 새 필수 인증 설정의 임시 키를 추가했다. 마이그레이션의 Windows stdout 인코딩 문제는 오프라인 SQL 출력에서 설명 주석을 제외하여 수정했다. 위 최종 결과에는 해결 전 실패를 포함하지 않는다.

## 재실행 예

```powershell
$env:PYTHONPATH='apps/api'
$env:TEST_AUTH_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@localhost:5432/chatkit_auth_test'
$env:TEST_MAILPIT_HTTP_URL='http://localhost:8025'
$env:TEST_MAILPIT_SMTP_PORT='1025'
python -m pytest apps/api/tests -q -rs
```

전체 기존 DB 통합 검사까지 실행하려면 pgvector가 설치된 별도 테스트 DB를 `TEST_DATABASE_URL`에 지정한다. Windows 경로 길이 문제가 있으면 새롭고 짧은 임시 경로를 `--basetemp`로 지정한다. pytest가 그 경로를 관리하므로 기존 사용자 데이터 폴더를 지정하지 않는다.
