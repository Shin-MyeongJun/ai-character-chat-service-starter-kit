# PostgreSQL 감사 작업 테스트 환경 준비

작성일: 2026-10-30 (Asia/Seoul)

사용자가 Docker를 실행하고 작업 전 준비를 요청했다. 이 요청에 따라 전용 테스트 DB와
테스트용 임시 스키마의 생성/정리를 허용된 범위로 적용했다. 앱 DB 초기화·삭제나 앱 DB에
대한 migration은 실행하지 않았다. U03/U21 구현은 아직 시작하지 않았다.

## 준비 상태

- 기존 Compose의 PostgreSQL(pgvector/pgvector:pg17), Redis, Mailpit은 healthy였다.
  컨테이너 재생성·이미지 교체·볼륨 정리 없이 그대로 사용했다.
- API 테스트 DB: `chatkit_audit_test_12310f`
- 인증 테스트 DB: `chatkit_auth_test_12310f`
- 전용 계정: `chatkit_test_12310f`. NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION으로
  생성했고 두 테스트 DB만 소유한다. 앱 DB `chatkit`의 CREATE 권한은 없다.
- 두 테스트 DB에 pgvector 0.8.6을 준비했다. 앱 DB의 데이터/설정/권한은 변경하지 않았다.
- 접속 URL은 `.env.audit-test.local`에만 보관했다. 이 파일은 기존 .gitignore 규칙으로
  제외되며 Git 추적 대상이 아님을 확인했다. 비밀번호는 로그·이 문서·소스에 기록하지 않는다.
- 전역/사용자 환경 변수나 앱 `.env`의 DATABASE_URL은 바꾸지 않았다.

## 실행 방법

저장소 루트에서 프로젝트 Python으로 실행한다.

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py
```

기본 실행은 준비 확인용 기존 테스트를 실행한다. 선택한 파일/테스트를 실행하려면 뒤에
pytest 인자를 전달한다.

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_billing_lifecycle_integration.py
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_hypha_memory.py::test_durable_queue_coalesces_requests_arriving_during_a_lease
```

실행 도우미는 다음을 수행한다.

- Git 제외 파일에서 두 테스트 URL을 읽고 localhost 및 전용 이름/계정 접두사를 확인한다.
- 해당 **자식 테스트 프로세스에만** TEST_DATABASE_URL/TEST_AUTH_DATABASE_URL을 설정한다.
- live 공급자 키·live S3 실행 플래그와 상속된 PYTEST_ADDOPTS를 제거한다.
- 플러그인 자동 로딩을 끄고 pytest_asyncio만 명시적으로 로드한다.
- 실행마다 짧고 새로운 `tmp/pgt-<id>`를 사용하므로 병렬 작업의 basetemp가 겹치지 않는다.

기본 DB fixture는 UUID 스키마를 생성하고 테스트 후 해당 스키마만 삭제한다.
서로 다른 pytest 프로세스도 기존 fixture의 스키마 격리를 사용한다. 전용 DB 자체를
작업 종료마다 삭제하거나 재생성하지 않는다. Docker는 작업 중 실행 상태를 유지한다.
샌드박스의 Docker 파이프 또는 Windows asyncio socket 제한이 있으면 동일한 전용 DB
명령에 대해 실행 권한을 조정한다. 비밀번호를 출력하는 docker config/환경 덤프는 피한다.

## 확인한 결과

실제 PostgreSQL에서 기본 준비 확인 테스트 **12 passed / 0 failed / 0 skipped**:

- 최외곽 transaction commit 1회, 잡힌 중첩 실패의 전체 rollback, autobegin 채택 거절
- 두 세션의 같은 태그 이름 resolve 및 ID 재사용
- lease 중 새 요청을 합치는 기존 메모리 큐 경로
- quote→reserve→finalize·재생, 저장 가격 보존, 전체 credit lifecycle rollback
- 별도 인증 DB의 가입·검증·로그인·refresh·logout (메일/외부 인증은 기존 대역)

로그: [postgres-audit-setup-smoke.txt](../../../tmp/postgres-audit-setup-smoke.txt).
테스트 후 두 DB의 test_/auth_test_ 임시 스키마 수가 각각 **0개**임을 확인했다.
전용 계정의 superuser/createdb/createrole이 모두 false이고 앱 DB CREATE 권한이 없는
것도 접속 계정으로 확인했다. 도우미의 Ruff format/check·mypy 1소스 검사도 통과했다.

## 범위와 다음 작업

이 결과는 **테스트 환경 준비 확인**이며 U03 claim fencing 또는 U21 최적화의 구현·경쟁
검증 완료가 아니다. 두 작업에서 새 경합 시나리오와 회귀를 추가하고 이 도우미로 실제 PG
검증을 실행한다. 기존 오프라인 품질 검사기는 계속 자체 오프라인 환경을 사용한다.

전용 계정은 CREATE DATABASE 권한이 없다. 별도 DB 생성/삭제를 수행하는 일부 migration
테스트까지 제한 없이 실행할 수 있는 관리자 계정은 아니다. 해당 검증은 테스트별 요구와
대상을 검토해 별도로 준비하며 앱 DB 계정으로 우회하지 않는다. 전체 API의 DB 활성화
회귀나 실제 외부 공급자/브라우저 E2E는 이번 준비 범위에서 실행하지 않았다.

기존 staged/unstaged/untracked 변경과 공통 감사 REPORT·검사 설정은 보존했다.
별도 대화·서브에이전트·commit/push는 만들지 않았다.
