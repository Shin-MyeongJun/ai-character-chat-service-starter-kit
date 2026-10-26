# 백엔드 아키텍처 및 코드 검토 보고서

기준일: 2026-10-21 (Asia/Seoul). 브랜치 `master`, 커밋 `0f36336246f03a06217d8d8ab96f32e6284960ce` 이후의 미커밋 변경을 포함한 작업 트리 기준이다. 애플리케이션 코드·스키마·기존 설정은 수정하지 않았다.

전체 PDF는 108페이지이며, `backend-review-source.zip`에는 PDF·편집 원본·48개 도표·근거·재생성 스크립트·시각 검수 이미지가 함께 들어 있다. 압축을 푼 뒤 `README.md`부터 읽는다. 무결성 해시는 `manifest.json`에 있다.

## 읽는 순서와 산출물

- `backend-review.pdf`: 한국어 보고서. 요약 → 전체 구조 → 핵심 흐름 → 발견 사항 순서로 읽기를 권한다. 부록에 전체 API와 테이블 사전을 수록했다.
- `backend-review.md`: 수정 가능한 원본. Markdown과 `diagrams/*.json`을 편집한 뒤 PDF를 다시 만들 수 있다.
- `diagrams/`: 48개 도표의 편집용 JSON과 SVG·벡터 PDF·PNG. JSON의 노드·간선·단계를 수정하면 된다. 외부 다이어그램 서비스는 필요 없다.
- `inventory.json`: 520개 조사 파일의 해시·Python 심볼·import·ORM 메타데이터·HTTP 라우트·조사 시 Git 상태. 기존 사용자 변경을 포함한다.
- `coverage.csv`: 파일별 조사 깊이와 근거. 목록 수집과 구현 확인을 구분한다.
- `evidence.json`: 보고서에서 인용한 경로·심볼·줄 번호·해시 172개. 줄 번호는 이 작업 트리 기준이다.
- `schema.json`, `relationships.csv`: 73개 테이블, 600개 컬럼, 139개 FK의 원본 선언. DB 실조회 결과가 아니다.
- `api-inventory.csv`, `module-dependencies.json`: 114개 메서드·경로와 정적 모듈 의존 간선.
- `schema-comparison.json`: 선별한 최신 마이그레이션 SQL과 초기화 SQL의 비교. 전체 이력의 실DB 동등성을 증명하지 않는다.
- `pytest-verified.log`, `tests.xml`, `test-exit.txt`: 기존 전체 테스트 결과(529 passed, 4 failed, 290 skipped). 상세 실패 원인과 한계는 보고서 10·11장 참고.
- `ruff.json`, `alembic-heads.log`: 정적 검사와 마이그레이션 head 확인 결과.
- `probes.py`, `probes.json`: F01~F03의 합성 입력·대역 객체 재현. PostgreSQL이나 외부 API를 호출하지 않는다.
- `source-integrity.json`: 조사 파일 해시 보존 확인.
- `qa/`: 전체 PDF 페이지 이미지, 축소판, 텍스트 추출·경계 검사 결과, 수동 시각 검수 기록.

## PDF 재생성

저장소 루트에서 PowerShell을 실행한다. 아래 번들 Python 경로는 이 PC의 환경이다. 다른 PC에서는 Python 3.11 이상에 `reportlab`, `Pillow`, `pdfplumber`를 준비하고 `$docPython`을 바꾼다. 앱 가상환경은 PDF 제작 라이브러리를 제공하지 않는다. 재생성은 네트워크를 사용하지 않는다.

```powershell
$reviewDir = 'output/pdf/backend-review-2026-10-21'
$docPython = 'C:/Users/smj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $docPython "$reviewDir/render_report.py"
& $docPython "$reviewDir/render_assets.py"
& $docPython "$reviewDir/verify_artifacts.py"
```

`render_report.py`는 Windows의 `C:/Windows/Fonts/malgun.ttf`, `malgunbd.ttf`를 PDF에 포함한다. 다른 OS에서는 스크립트의 폰트 파일 경로를 한글 지원 TTF로 바꾼다. SVG는 시스템 글꼴을 참조하므로 공유 시 글꼴이 포함된 PDF 또는 PNG를 사용하면 모양을 유지할 수 있다. PDF 본문은 이미지가 아닌 검색·복사 가능한 텍스트다.

`render_assets.py`는 PATH의 Poppler `pdftoppm`을 사용한다. PDF 전 페이지는 85 dpi, 개별 도표 PNG는 긴 변 1800픽셀로 출력한다. 페이지 수를 줄인 뒤 재생성했다면 `qa/final/page-*.png` 중 현재 PDF 페이지 번호를 초과하는 오래된 파일을 정리해야 한다. `verify_artifacts.py`는 페이지 경계·텍스트 추출·원본 해시를 확인하고 축소판을 만든다. 마지막에는 반드시 각 페이지 및 중요한 도표를 눈으로 다시 검수한다. 자동 경계 검사만으로 겹침을 검증할 수 없다.

`author_report.py`는 조사 데이터와 수작업 분석을 합쳐 Markdown과 도표 JSON을 처음 만드는 작성 스크립트다. **이 스크립트를 다시 실행하면 원본의 수동 수정이 덮어써진다.** 일반 문서 편집 후에는 위 세 명령만 사용한다. 새 코드 기준 보고서를 만들려면 자동 인벤토리 갱신뿐 아니라 근거 재검토, 테스트, 발견 사항 재판단이 필요하다.

## 조사·검증 재현

현재 코드를 다시 조사할 때 사용하는 명령이다. 기존 `inventory.json`과 기준 증거를 덮어쓰므로, 이번 검토 기록을 보존하려면 별도 새 폴더에서 실행해야 한다. 스크립트는 저장소의 `output/pdf/<폴더>` 위치를 전제로 루트를 계산한다.

```powershell
& .venv/Scripts/python.exe "$reviewDir/inspect_backend.py"
& .venv/Scripts/python.exe "$reviewDir/probes.py"
& .venv/Scripts/python.exe "$reviewDir/local_pytest.py" *> "$reviewDir/pytest-verified.log"
```

`local_pytest.py`는 테스트 프로세스의 DB·외부 서비스 opt-in 환경변수를 제거하고, 앱 테스트만 실행한다. `.env`를 직접 읽지 않으며 pytest 캐시는 끈다. `pytest-temp`는 이 보고서 전용 임시 경로이고 재실행 시 pytest가 정리할 수 있다. 다른 데이터를 넣지 않는다. 실제 DB 테스트는 의도적으로 건너뛴다. 이번 Windows 제한 실행 환경에서는 TestClient 요청이 멈춰 중단한 후, 동일 스크립트를 일반 로컬 권한에서 실행해 완료했다. 테스트 실패 4개 때문에 종료 코드는 1이며 정상 기록이다.

Ruff는 앱·테스트 대상으로 `ruff check app tests --output-format json`, Alembic은 `apps/api`에서 `alembic heads`로 확인했다. `alembic upgrade`, 서버 시작, 실제 DB·공급자 호출은 수행하지 않았다. 스키마 비교는 파일 내용 비교에 한한다.

## 검토 범위와 한계

18개 업무 모듈과 공통 HTTP·DB·use case·작업 진입점을 조사했다. 363개 앱 Python 파일은 전수 목록·AST·import를 확인하고, 보고서에 인용한 대표 구현과 위험 경계는 직접 읽었다. 모든 함수의 모든 분기를 수작업 감사한 것은 아니다. `coverage.csv`의 확인 수준을 참고한다.

운영 DB 현황, 실제 PostgreSQL 트랜잭션·동시성, 마이그레이션 실행, S3·LLM·SMTP·OIDC의 실통신, 부하·배포·백업 복구, 프런트엔드 구현은 검증하지 않았다. 실패한 테스트가 곧 운영 버그라는 뜻은 아니며, 정적 위험과 합성 재현 및 실행 확인을 보고서에서 구분했다. 현재 검토 자료를 새로운 코드 기준의 자동 보증으로 사용하지 않는다.
