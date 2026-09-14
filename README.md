# Character AI Starter Kit

개인 개발자와 서비스 운영자가 캐릭터 AI 채팅 서비스를 빠르게 구축하고 사업화를 시작할 수 있도록 돕는 스타터킷입니다. 상품 등록, 대화 처리, 로어북 검색, 프롬프트 구성, 대화 압축 등 공통 기능을 제공해 초기 개발 부담을 줄이는 것을 목표로 합니다.

> **개발 및 검증 진행 중**
>
> 핵심 백엔드 기능을 구현하고 동작 검증과 구조적 문제 점검을 진행하고 있습니다. 즉시 상용 운영할 수 있는 완성된 배포판은 아직 제공하지 않습니다.

## 목표와 제공 방향

첫 번째 목표는 환경 변수와 LLM API 키를 설정한 뒤 Docker Compose로 기본 서비스를 실행할 수 있게 하는 것입니다. 개인 개발자나 운영자가 초기 구축에 드는 시간을 줄이고 자신의 서비스 구성에 집중할 수 있도록 합니다.

현재는 기능 구현과 검증에 집중합니다. 이후 설치·설정·문서를 정리하고 클라우드 배포와 운영 편의성을 개선할 계획입니다. 필요한 모듈만 가져가 확장하는 구성은 후속 목표이며, MSA 전환은 독립적인 배포나 확장이 필요한 영역에 한해 검토합니다.

## 현재 개발 상태

아래의 ‘검증 중’은 구현된 흐름의 정확성과 통합 동작을 확인하는 단계이며, 전체 검증 완료를 의미하지 않습니다.

| 영역 | 현재 상태 |
| --- | --- |
| 상품 등록 및 구성 | 구현된 기능과 관련 처리 흐름 검증 중 |
| 대화 처리 및 추출 | 입력 처리, 대화 조회·추출, 답변 생성과 저장 흐름 검증 중 |
| 로어북 검색 및 프롬프트 조합 | 대화에 사용할 정보 검색과 프롬프트 구성 검증 중 |
| 대화 압축 및 메모리 | 요약·임베딩·검색, 대화 변경에 따른 메모리 무효화 검증 중 |
| 요청 및 실패 처리 | 중복 요청, 생성 실패, 재시도와 동시성 관련 동작 검증 중 |
| 회원가입 등 사이트 기본 기능 | 개발 예정. 현재 API의 기본 인증 훅은 미연결 상태 |
| 결제 및 크레딧 정책 | 추가 개발 필요. 초기 범위는 결제 연동 인터페이스와 일부 구현까지 |
| 감독·관리 및 통계 | 일부 기반 구현이 있으며 운영 기능 완성을 위한 추가 개발·검증 필요 |
| 프런트엔드 | 개발 예정 |

실제 결제 서비스 연동과 실결제 검증은 초기 백엔드 완료 범위에서 제외합니다. 결제 관련 코드나 사용량 기록이 존재하더라도 결제 승인·크레딧 차감 등 상용 결제 흐름 전체가 완성된 상태를 뜻하지 않습니다.

## 기술 구성

| 영역 | 기술 |
| --- | --- |
| 백엔드 | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| 데이터 저장 | PostgreSQL 17, pgvector |
| 개발 인프라 | Docker Compose, Redis 7 |
| LLM·임베딩 연동 | OpenAI, Anthropic, Voyage AI 어댑터 및 텍스트 생성 Mock 어댑터 |
| 테스트 | pytest, pytest-asyncio, PostgreSQL 통합 테스트 |
| 프런트엔드 기반 의존성 | Next.js, React, TypeScript — 화면 구현은 개발 예정 |

공급자별 실제 API 동작과 전체 서비스 통합 검증은 진행 중입니다.

## 저장소 구조

```text
apps/api/
  app/
    http/             # HTTP 진입점과 의존성 연결
    modules/          # 콘텐츠, 대화, LLM, 저장소 등 도메인별 기능
    use_cases/        # 여러 모듈을 조합하는 처리 흐름
    db/               # 데이터 모델 및 트랜잭션
  alembic/            # 데이터베이스 마이그레이션
  tests/              # 단위·통합 테스트
infra/postgres/init/  # PostgreSQL 초기 설정
references_document/  # 설계 및 개발 참고 문서
```

모듈별 책임과 공개 인터페이스는 각 모듈의 `ARCHITECTURE.md`에서 관리합니다.

- [모듈 아키텍처 및 명명 규칙](references_document/reference/module-architecture-and-naming.md)
- [유스케이스 구성](apps/api/app/use_cases/ARCHITECTURE.md)
- [채팅 모듈](apps/api/app/modules/chatting/chat/ARCHITECTURE.md)
- [대화 메모리 모듈](apps/api/app/modules/chatting/memory/ARCHITECTURE.md)
- [프롬프트 모듈](apps/api/app/modules/chatting/prompt/ARCHITECTURE.md)
- [상품 모듈](apps/api/app/modules/content/product/ARCHITECTURE.md)

## 현재 개발 환경 준비

현재 `docker-compose.yml`은 **PostgreSQL과 Redis만 실행**합니다. API와 프런트엔드를 포함한 전체 서비스의 Compose 실행은 향후 목표입니다.

아래 명령은 저장소 루트에서 실행하는 PowerShell 기준입니다. Docker Compose, Python 3.12가 필요하며, pnpm 명령을 사용할 경우 Node.js 22와 `package.json`에 지정된 pnpm 버전을 준비합니다.

### 1. 환경 설정

기존 `.env`가 없다면 예제 파일을 복사합니다.

```powershell
Copy-Item .env.example .env
```

사용할 공급자의 API 키와 저장소 설정은 [.env.example](.env.example)을 참고해 설정합니다. 예제의 `LLM_PROVIDER=mock`은 실제 모델 응답 검증을 대신하지 않습니다.

예제의 `postgres`, `redis` 호스트명은 컨테이너 네트워크 기준입니다. API를 호스트에서 직접 실행할 때는 `DATABASE_URL`과 `REDIS_URL`의 호스트를 `localhost`로 바꾸고 실제 포트에 맞춰야 합니다. 로컬 파일 저장 경로인 `ASSET_TEST_LOCAL_ROOT`도 자신의 실행 환경에 맞게 설정합니다.

### 2. 데이터베이스와 Redis 실행

```powershell
docker compose up -d
docker compose ps
```

종료:

```powershell
docker compose down
```

같은 작업을 `pnpm infra:up`, `pnpm infra:down`으로 실행할 수도 있습니다.

### 3. Python 개발 의존성 설치

새 개발 환경에서는 가상환경을 만들고 의존성과 API 패키지를 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e apps/api
```

### API 실행 전 확인 사항

현재 ASGI 진입점은 `apps/api/app/main.py`의 `app`입니다. 기본 인증 훅은 미연결 상태로, 인증이 필요한 요청에 503을 반환합니다. 배포 애플리케이션은 `create_app(authenticate=...)`에 검증된 인증 의존성을 제공해야 합니다.

API를 통한 전체 기능 사용에는 환경 변수 로딩, 데이터베이스 마이그레이션, 인증 및 모델 설정 연결이 필요합니다. `.env` 복사와 인프라 기동만으로 가입·상품 등록·채팅을 바로 이용할 수 있는 상태는 아닙니다. 이 과정을 최소 설정으로 통합하는 작업은 로드맵에 포함됩니다.

## 테스트와 검증

테스트 코드는 [apps/api/tests](apps/api/tests)에 있습니다. 대화와 상품 처리, 프롬프트, 메모리, 외부 공급자 어댑터, 저장소 및 모듈 경계 등을 검증하는 테스트를 작성하고 있습니다.

개발 의존성 설치 후 다음 명령으로 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests
```

PostgreSQL 통합 테스트는 `TEST_DATABASE_URL`이 필요합니다. 테스트용 데이터베이스는 별도로 준비해야 하며, 이름에 `test`가 포함되어야 합니다. 기본 Compose 설정은 이 데이터베이스를 자동 생성하지 않습니다.

```powershell
# 별도로 생성한 테스트 DB의 접속 정보로 설정합니다.
$env:TEST_DATABASE_URL = "postgresql+asyncpg://chatkit:chatkit@localhost:5432/chatkit_test"
.\.venv\Scripts\python.exe -m pytest apps/api/tests
```

`TEST_DATABASE_URL`이 없으면 해당 DB fixture를 사용하는 통합 테스트는 건너뜁니다. 외부 API·S3 등 별도 환경이 필요한 테스트도 있으므로 성공·실패뿐 아니라 건너뛴 항목과 조건을 함께 확인해야 합니다. `VOYAGE_API_KEY`가 설정되어 있으면 실제 임베딩 API를 호출하는 테스트도 실행됩니다. 테스트 코드의 존재나 일부 테스트 통과를 전체 기능 검증 완료로 표시하지 않습니다.

## 개발 로드맵

아래 일정은 **2026년 개발 목표**이며, 검증 결과와 작업 범위에 따라 조정될 수 있습니다.

| 목표 시점 | 목표 범위 |
| --- | --- |
| 10월 첫째 주 | 실결제 연동을 제외한 백엔드 목표 범위 구현·검증, AWS 등 클라우드 테스트 환경에서 동작 확인 |
| 10월 말 | 프런트엔드 구현 및 주요 사용자 흐름의 백엔드 연동 |
| 11월 말 | 최소 설정으로 시작할 수 있도록 설치·설정·코드 구성·문서를 개선해 스타터킷 형태 정리 |
| 11월 이후 최우선 | 앞선 클라우드 검증 결과를 바탕으로 배포 절차 단순화와 운영 편의성 개선 |
| 후속 검토 | 선택적 모듈 구성, 추가 기능, 필요한 영역의 독립 서비스 분리 |

클라우드 테스트 환경에서의 동작 확인과, 운영자가 쉽게 배포할 수 있도록 배포 과정을 제품화하는 작업은 별도 단계로 진행합니다.

## 개발 과정의 AI 활용

개발 과정에서 AI를 다음 용도로 활용하고 있습니다.

- 자료 조사 및 참조 코드 분석
- 코드 구조와 설계 방향에 대한 의견 검토
- 테스트 코드 작성
- TODO로 정의한 작업 범위의 코드 작성

현재는 구현된 코드에 대한 테스트와 구조적 문제 확인을 진행하고 있습니다.

## 라이선스

라이선스 및 이용 조건은 현재 검토 중입니다. 상업적 이용을 포함한 구체적인 허용 범위는 아직 확정하지 않았으며, 외부 사용을 위한 공개 배포 전에 정리할 예정입니다.
