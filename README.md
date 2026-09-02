# Character AI Starter Kit Environment

구현 골격은 제거했고, 실행환경 확인에 필요한 최소 파일만 남겼습니다.

## 남긴 것

- Node.js/pnpm 환경: `.node-version`, `package.json`, `pnpm-lock.yaml`, `node_modules`
- Python 환경: `.python-version`, `.venv`, `requirements-dev.txt`
- 인프라 환경: `docker-compose.yml`, `infra/postgres/init/001_extensions.sql`
- 공통 환경 변수 예시: `.env.example`

## 확인 명령

```powershell
pnpm env:check
.\.venv\Scripts\python.exe -m pip list
docker compose config
```

PostgreSQL + pgvector와 Redis만 올릴 때:

```powershell
pnpm infra:up
pnpm infra:down
```

## IntelliJ 메모

기존 `.idea/modules.xml`이 존재하지 않는 `../chat_kit.iml`을 가리키고 있었습니다. 현재는 프로젝트 루트의 `chat_kit.iml`을 바라보도록 수정했습니다.
