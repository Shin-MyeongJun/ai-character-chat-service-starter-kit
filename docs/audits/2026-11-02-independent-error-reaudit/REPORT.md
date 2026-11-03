# 독립 오류 감사 재검사

실행일: **2026-11-02, Asia/Seoul**. 대상은 `C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit`의 미커밋 변경을 포함한 현재 작업 트리다.

## 최종 판단과 이전 판정의 정정

**확정 결함은 P2 3건이다. 이전 IEA-02·03·04는 재확인했고, IEA-01은 확정 목록에서 제외해 조건부 후보로 변경한다.** 기존 보고서를 그대로 승인하거나 테스트 실패 수를 결함 수로 환산하지 않았다. 이번 범위에서 별개의 신규 결함이나 현재 미커밋 정리로 생긴 회귀를 추가 확정하지 않았다.

| ID | 우선순위·종류 | 재검사 결과 | 강화한 증거 |
| --- | --- | --- | --- |
| IEA-02 | P2 · 기존 잔여 | 확정 유지: 다른 작품의 신규 태그 생성 순서가 교차해 발행 실패 | 실제 HTTP 두 요청에서 **200/500**, 실제 PG **40P01**. 재시도하면 둘 다 200이며 snapshot 총 2개 |
| IEA-03 | P2 · 기존 잔여 | 확정 유지: 무변경 발행 성공의 revision 영수증 누락 | 실제 HTTP **성공 200 → 이후 초안 저장 → 같은 요청 409**. 원래 revision 1 영수증은 계속 200 |
| IEA-04 | P2 · 기존 잔여 | 확정 유지, 영향 범위 한정: S3 reader의 명시적 회수 누락 | ASGI 2.3 연결 종료 후 설치된 Uvicorn 종료 취소 경로에서 **close 0회**, read 종료 후에도 raw stream 열림 |
| IEA-01 | 확정 우선순위 부여 보류 | **확정 → 조건부 후보**: 취소를 삼키는 대역에서는 재현되지만 현재 기본 SDK 경로의 발생 전제 미입증 | 설치 SDK 취소 대조 4건 통과. OpenAI SDK와 실제 PG 정산 연결 2건도 **차감 0·예약 0** |

P2는 특정 입력·실행 순서의 기능/자원 계약 위반이다. 전체 서비스 중단, 영구 교착, 운영의 장기 자원 누수 또는 데이터 유실을 입증했다는 뜻이 아니다. IEA-04의 운영 영향은 아래에 별도로 제한한다.

앱 코드·기존 테스트·공통 REPORT·WORKLOG·이전 감사 파일은 수정하지 않았다. 이번 새 폴더의 감사 자료만 작성했다. commit/push, reset/clean/복원/기존 파일 삭제, 별도 대화·서브에이전트, 외부 공급자 요청, 앱 DB migration/초기화는 실행하지 않았다. 실제 수정은 후속 승인된 작업으로 남긴다.

## 기준 상태와 증거의 유효 범위

- 시작·종료 HEAD: `31de1428aba2ea67fc887b004221f7bc3884cf0a`.
- 시작 시 기존 staged 0, tracked unstaged 46개(삭제 표시 7개 포함). 이전 untracked 4개와 이전 감사 폴더가 존재했다. 원문 porcelain 상태는 [시작 기준](baseline-start.json)에 보존했다. 해당 상태에는 기준 수집 도구를 먼저 만든 이번 감사 폴더도 별도로 표시된다.
- 현재 작업 트리의 **904개 기존 파일**을 기준으로 해시를 수집했다. 종료 비교에서 **변경 0·누락 0·이번 감사 폴더 밖 추가 0**, HEAD 동일이다. 환경 비밀 파일은 제외했다. [종료 기준](baseline-end.json).
- 이전 감사가 추적한 기존 890개 파일과 이전 감사 산출물/로그 25개도 모두 해시가 일치한다. 최신 통합 검사의 683개 소스도 모두 일치한다. [대조 결과](source-comparisons.json).
- 관련 unstaged diff를 직접 확인했다. generation/context의 LLM import 경로 이동, BaseLLMAdapter 별칭 제거, lorebook 상수 참조 이동은 현재 재현의 원인을 새로 만든 변경으로 확인되지 않았다. 확정 3건의 핵심 구현은 HEAD에도 존재한다. 원인 도입 commit 전체를 역추적한 것은 아니다.
- 현재 코드 발췌·줄 번호는 [code-evidence.md](code-evidence.md), 선택 검토 파일과 검토 깊이/해시는 [reviewed-scope.json](reviewed-scope.json)에 있다. 해시 수가 전수 정독 수를 뜻하지 않는다.
- 실제 PG는 기존 `tools/run_postgres_audit_tests.py`의 localhost·DB명·계정 범위 검사와 기존 UUID 스키마 fixture를 그대로 이용했다. PostgreSQL **17.11 / READ COMMITTED**, 종료 후 두 전용 DB의 테스트 스키마 잔량은 각각 0이다. [환경 로그](logs/environment-final.txt).

## IEA-02 — 구성요소별 신규 태그 생성이 서로 다른 발행을 교착시킴

**P2 / 기존 잔여.** 정상 소유자의 서로 다른 작품 발행이 특정 공유 태그 순서에서 HTTP 500으로 실패한다. PG가 한 트랜잭션을 중단하므로 영구 교착은 아니며, rollback과 재시도 후 성공까지 확인했다.

**현재 위치와 공개 경로**

- [HTTP 발행 진입점:112](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/http/studio_publication.py:112): `POST /products/{product_id}/studio-publication`.
- `publish_studio` → [캐릭터 생성/태그 해석:312](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:312) → 같은 트랜잭션의 [로어북 생성/태그 해석:390](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:390). 기존 복사본도 각각 305·379에서 태그 교체를 호출한다.
- [tag/repository.py:55](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/tag/repository.py:55): 각 `resolve_tags` 안에서만 이름을 정렬하고 62행의 INSERT ON CONFLICT와 공유 잠금을 실행한다.

**입력·동시 실행 순서**

1. 태그 alpha/beta가 아직 없는 상태에서 서로 다른 작품 A/B를 같은 소유자가 정상 저장한다. 각 요청은 별도 AsyncSession/PG 연결을 사용한다.
2. A의 캐릭터 태그는 alpha, 로어 태그는 beta다. B는 캐릭터 beta, 로어 alpha다.
3. 첫 `resolve_tags`가 실제 SQL을 마친 직후 장벽으로 둘 다 미커밋 신규 이름을 확보했음을 보장한다. SQL/잠금/반환값은 대역으로 바꾸지 않는다.
4. A의 다음 INSERT는 B의 beta 확정을 기다리고, B의 다음 INSERT는 A의 alpha 확정을 기다린다. 실제 PG 오류 `40P01`을 SQLAlchemy 오류 이벤트에서 수집한다.

**기대와 실제**: 독립 작품의 유효한 발행 두 건이 성공하거나 내부의 명시된 충돌 복구로 수렴해야 한다. 실제 HTTP 상태는 `[200, 500]`, 최초 snapshot은 1개다. 장벽을 제거하고 두 요청을 재전송하면 `[200, 200]`, snapshot은 2개로 수렴한다. 영구 불능·이중 snapshot·초안 유실 주장은 하지 않는다. alpha/beta가 미리 commit된 대조군은 처음부터 `[200, 200]`, 교착 오류 0이다.

**재현**: [test_http_publication.py](test_http_publication.py)의 `test_http_two_publications_cross_component_tags`; [HTTP 로그](logs/http-publication.txt). 이전 서비스 수준 재현도 동일하게 나왔다. [서비스 재검사 로그](logs/prior-pg-recheck.txt).

**기존 방어와 테스트의 빈틈**: 작품별 advisory→product→draft 순서는 서로 다른 작품의 전역 태그 INSERT 순서를 정하지 않는다. 단일 resolve 내부 정렬과 FOR SHARE 호환성도 구성요소 사이의 미커밋 UNIQUE 대기를 없애지 못한다. U25의 단일 묶음·배치 경계·관리자 경합 검사는 발행이 여러 resolve를 반대 순서로 조합하는 경우를 검증하지 않는다. HTTP errors는 이 DBAPI 교착에 재시도를 제공하지 않는다.

**최소 수정 방향과 보존 계약**: 발행 전체에서 필요한 신규 이름의 획득 순서를 통일하거나, 원자적 전체 트랜잭션의 교착 재시도를 명시적으로 설계한다. 임의의 전역 배타 잠금을 추가하기보다 실제 공유 자원 순서를 다룬다. 비활성 태그의 기존 연결 유지, 관리자 변경 fencing, authored 반환 순서, 소유권·원자적 snapshot/영수증 및 rollback 계약을 보존해야 한다.

## IEA-03 — 무변경 발행 성공에 현재 revision의 영수증이 남지 않음

**P2 / 기존 잔여.** 수락한 요청의 응답 유실 복구 계약을 위반한다. 과거 snapshot 자체가 변경되거나 새 snapshot이 중복 생성되는 결함은 아니다.

**현재 위치와 공개 경로**: 같은 발행 HTTP → `publish_studio`. [222행](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:222)은 revision별 receipt를 조회하고, 237행은 현재 revision을 검사한다. [241행](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:241)의 동일 content digest 경로는 기존 ReleaseInfo를 바로 반환해 [493행](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:493)의 receipt 저장에 도달하지 않는다. HTTP 129행은 이후 충돌을 409로 변환한다.

**입력·실행 순서**

1. D 문서를 revision 1로 저장·발행하여 snapshot S와 영수증 1을 만든다.
2. E로 편집해 revision 2를 저장하고, D로 되돌려 revision 3을 저장한다.
3. revision 3의 요청 R을 발행하면 HTTP 200과 S가 반환된다. 즉시 같은 R을 재전송해도 200이다.
4. E를 다시 저장하여 revision 4가 된 후 동일 R을 재전송하면 HTTP 409다. 원래 revision 1의 요청은 여전히 200으로 S를 반환한다.

**기대와 실제**: `publish_studio` docstring 및 `use_cases/ARCHITECTURE.md:100–108`은 같은 요청이 최신 초안 revision과 무관하게 기존 영수증을 재생한다고 약속한다. 실제 수락한 revision 3에는 영수증이 없고 `receipts` 키는 `['1']`뿐이다. 서비스 재현에서 snapshot 수 1과 과거 snapshot JSON 동일성도 확인했다.

**재현**: [test_http_publication.py](test_http_publication.py)의 `test_http_noop_publication_replay_after_new_save`; [HTTP 로그](logs/http-publication.txt). 서비스 재현과 snapshot 보존 확인은 [test_reproductions.py](test_reproductions.py), [PG 로그](logs/prior-pg-recheck.txt).

**기존 방어와 테스트의 빈틈**: 소유권·CAS·digest 비교는 실행되지만, 재사용한 snapshot이 현재 revision의 요청 fingerprint/성공 영수증을 대신하지 못한다. 일반 발행의 영수증 재생 테스트는 통과한다. 편집→미발행 변경 되돌리기→무변경 발행 성공→다음 편집의 조합이 빠져 있다.

**최소 수정 방향과 보존 계약**: snapshot을 재사용하는 성공 경로에도 현재 revision/fingerprint의 영수증을 원자적으로 남긴다. 불필요한 snapshot·문서 revision 증가 없이 과거 영수증·매핑·snapshot 불변성, 다른 파라미터 충돌, 소유권과 CAS를 보존한다.

## IEA-04 — HTTP 정리 중 취소가 S3 close를 실행 전에 제거함

**P2 / 기존 잔여.** 정상 반환된 reader의 명시적 회수 계약 위반이다. 실행기 포화와 close 대기 중 취소가 필요하다. 장기 운영의 소켓/핸들 증가량, 프로세스 종료 뒤 자원 잔류 또는 실제 S3 장애는 입증하지 않았다.

**현재 위치와 공개 경로**

- `GET /characters/media/{id}/content` 또는 상품 버전 미디어 GET → 권한 확인·정상 reader 획득 → [MediaStreamingResponse.__call__:88](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/http/media.py:88)의 finally.
- [AssetReadInfo.aclose:184](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/asset_storage/types.py:184)는 실제 종료보다 먼저 `_closed=True`로 만든다.
- [S3 reader:78](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py:78)의 read와 84행의 close는 보호된 작업 소유 없이 `asyncio.to_thread`를 기다린다.

**실행 순서와 관찰 결과**

1. 설치된 실제 botocore StreamingBody와 S3StorageAdapter/MediaStreamingResponse를 사용한다. get_object와 raw stream만 로컬 대역이며 외부 요청은 없다. 실행기 한 worker와 threading Event로 모든 worker가 바쁜 순서를 최소화한다.
2. Uvicorn h11과 같은 **ASGI spec 2.3**으로 응답을 실행한다. 실제 Starlette가 `http.disconnect`를 받아 진행 중 read await를 취소한다. 스레드 read는 gate에 남아 있다.
3. finally의 close 진입과 실행기 큐 1개를 확인한다. `_closed=True`지만 close는 아직 실행되지 않았다.
4. 설치된 Uvicorn의 실제 `Server.shutdown()`을 실행한다. 이 테스트는 graceful shutdown 예산을 0으로 지정해 해당 응답 task의 취소 분기를 실행한다. 대기 중 close Future가 취소된다.
5. read gate를 해제하고 종료 Event와 실행기 barrier를 통과한 뒤 `opened.aclose()`를 다시 호출한다. 결과는 **close 0회 / raw_closed=False / reader_marked_closed=True**다. 연결 종료만 있고 추가 서버 취소가 없는 대조군은 close 1회·닫힘으로 통과한다.

**재현**: [test_s3_disconnect_shutdown.py](test_s3_disconnect_shutdown.py), [보강 로그](logs/sdk-http-lifetime-final.txt). 이전 ASGI 2.4 직접 반복 task 취소 재현도 동일했다. [이전 조건 재검사 로그](logs/prior-s3-recheck.txt). 감사 테스트 자체는 finally에서 합성 body를 직접 닫고 실행기를 회수한다.

**운영 도달성의 한계**: 설치된 Uvicorn의 종료 취소 분기는 실제 코드지만, 저장소 Docker/운영 기본 실행 명령은 `timeout_graceful_shutdown`을 지정하지 않는다. 설치 버전 기본값은 `None`이다. 따라서 기본 실행의 평범한 연결 종료만으로 이 결함이 발생한다고 말할 수 없다. 유한 graceful shutdown 예산을 설정한 지원 실행 또는 응답 정리 중 외부 task 취소가 있어야 한다. 프로세스 종료/GC가 자원을 나중에 회수할 수 있으므로 이 재현을 영구 누수의 증거로 사용하지 않는다. 증명한 것은 close 완료 전에 닫힘으로 확정되어 명시적 정리와 재시도가 사라지는 현상이다.

**기존 방어와 테스트의 빈틈**: U08은 획득 도중 취소된 늦은 reader를 shield로 회수한다. 정상 반환 후의 개별 read/close에는 적용되지 않는다고 아키텍처에도 명시돼 있다. local adapter의 보호 역시 S3 reader에 적용되지 않는다. 기존 HTTP 테스트의 AsyncMock `aclose` 호출 확인은 실행기 큐에서 실제 close가 취소되는 것을 검증하지 못한다.

**최소 수정 방향과 보존 계약**: 실제 close 완료까지 정리 작업을 소유하거나, 취소된 close를 다시 완료할 수 있는 상태를 유지한다. 진행 중 read와의 순서, idempotency, 최초 취소/예외 우선순위, 반환 reader와 주입 client 소유권, streaming 메모리 사용 계약을 보존한다. U28 업로드 중 DB 잠금 대체 설계와는 별개다.

## IEA-01 판정 변경 — 대역 재현은 유지되나 기본 경로의 결함 확정은 보류

이전 보고서는 “공급자가 CancelledError를 삼켜 정상 결과를 반환한다”는 조건을 테스트에서 직접 만들고, 이후 실제 PG 성공 저장·10 CREDIT 차감을 확인했다. 이번에도 그 **두 assertion 실패는 동일하게 재현됐다**. `answers.py:589–620`에 timeout 만료 상태나 반환 후 취소 상태를 별도로 재검사하지 않는다는 코드 관찰도 맞다.

그러나 감사의 확정 기준에는 현재 지원되는 실제 공개 경로에서 그 전제가 성립하는지 확인하는 단계가 필요하다. `main.py:148–167`의 기본 구성은 OpenAI/Anthropic/Mock adapter다. 해당 adapter와 text service에는 취소를 성공으로 바꾸는 catch가 없고, 설치 SDK/HTTPX의 확인한 취소 경로도 취소를 전파한다. 임의 주입 가능한 대역의 행동만으로 기본 앱의 잘못된 과금을 확정한 것은 근거 수준을 넘었다.

이번 반증·대조:

- 실제 **OpenAI 2.54.0 / Anthropic 0.125.0** SDK → 앱 adapter → TextGenerationService를 실행했다. HTTP transport만 Event에서 기다리는 대역이다. 두 SDK × deadline/호출자 취소 **4건 모두 결과 없이 취소를 전파**했다. [검증 코드](test_sdk_cancel_controls.py), [로그](logs/sdk-http-lifetime-final.txt).
- 실제 OpenAI SDK → AnswerOrchestrator → 실제 PG 완료/정산도 실행했다. deadline은 failed/timeout, 호출자 취소는 cancelled이며, 둘 다 **잔액 20 유지·예약 0·차감 0**이다. [검증 코드](test_sdk_answer_controls.py), [로그](logs/answer-sdk-and-regression.txt).
- memory workflow의 U29는 명시적으로 공급자 취소 흡수와 동기 처리 지연까지 방어한다. 그 방어의 존재가 답변의 실제 SDK에서도 취소 흡수가 발생한다는 증거는 아니다.

따라서 IEA-01은 **“특정 하위 구현이 취소를 흡수하면 발생하는 방어 공백 / 운영 경로 미입증”**으로 남긴다. 모든 SDK 내부 경합을 안전하다고 증명하거나 향후 custom adapter의 필요 방어를 부정한 것도 아니다. 현재 기본 경로에서 취소 흡수나 그에 준하는 지연 성공을 재현하면 재평가한다. 이번에는 확정 결함 수나 확정 우선순위에 넣지 않는다. 이전 보고서는 보존하고 이 보고서에서 판정을 정정한다.

## 주요 반박·보류·기록 불일치

- **“태그의 FOR SHARE가 두 발행을 막지 않으므로 교착이 아니다”**: 반박됐다. 원인은 호환 공유 잠금 자체가 아니라 구성요소 사이 미커밋 신규 이름 INSERT의 UNIQUE 대기다. 실제 SQLSTATE 40P01과 HTTP 500이 증거다.
- **“발행 receipt가 있으므로 모든 같은 내용 재시도가 안전하다”**: 일반 receipt 경로는 안전하지만 현재 revision의 no-op 조기 반환에는 receipt가 없다. 같은 revision 즉시 재시도 및 원래 revision 1 재생은 성공하는 대조군으로 구분했다.
- **“정상 disconnect만으로 S3가 항상 누수된다”**: 반박됐다. 추가 취소가 없는 두 종류의 대조군은 닫혔다. IEA-04는 정리 대기 중 취소라는 조건으로 제한한다.
- **“답변 취소 대역 실패가 곧 기본 SDK의 실제 과금 오류다”**: 확정하기에 부족하다. 위 이유로 IEA-01을 하향했다.
- **이전 getMe 계정 전환 의심**: 이번에는 브라우저/프런트 실행을 추가하지 않았다. 이전의 미확정을 그대로 유지하며 새 결함으로 승격하지 않는다.
- **문서 불일치**: U06의 최신 문서가 약속한 모든 수락 revision의 응답 유실 재생은 IEA-03에서 깨진다. U25는 모든 실행 순서의 교착 부재를 보장하지 않는다고 스스로 제한한다. U08도 정상 반환 reader의 전체 취소 정책은 미개편이라고 기록하므로 그 제한을 수정 회귀라고 재분류하지 않는다. 이전 감사의 “확정 4건”은 이번의 더 엄격한 판정과 다르다.
- **알려진 보류 U19**: 이미지 구조/선택 정책 및 studio·chat·발행·기존 데이터 호환 재설계는 새 결함으로 반복하지 않았다.
- **알려진 보류 U28**: 외부 저장 중 DB 잠금/전체 업로드 deadline 대체 설계는 그대로 보류다. 구현된 해싱 offload·취소 시 파일 수명과 구별했다.

## 이번 검토 범위와 미검사 범위

이번 요청은 직전 감사의 재검사로 해석해 **기존 확정 4건의 도달성·대역 전제·반대 증거**를 우선 추적했다. AGENTS, 두 기준 문서, 관련 ARCHITECTURE, 역사 REPORT의 최신 판정, U01/U04/U25 및 최신 통합 기록의 관련 절을 대조했다. 모든 역사 문서·모듈을 다시 같은 깊이로 정독한 감사는 아니다.

| 영역 | 이번에 직접 확인한 범위 | 이번에 새로 실행하지 않은 범위 |
| --- | --- | --- |
| 답변·메모리·과금 | 실제 답변 취소/timeout·staging/finalize·lease 방어, 설치 SDK, 실제 PG 과금, 기존 nonstream 및 memory deadline 계약 | 긴 이력·claim 경합·요약 다배치·수동 복구 전체를 다시 실행하지 않음. 동일 소스의 직전 PG 기록을 참고 |
| 인증·권한·메일 | 발행 HTTP의 Owner/Session 의존성과 서비스 소유권 경계 확인 | 실제 인증은 테스트에서 이미 인증된 owner로 주입. 관리자·정지 계정·Outbox·SMTP/브라우저 경합 새 실행 없음 |
| 스튜디오·태그·신고 | 실제 HTTP DTO→공개 서비스→PG의 저장/발행, 신규/기존 태그 대조, rollback·재시도·영수증, 기존 재발행 계약 | 신고 그래프·관리자 태그 변경 전체 재실행 없음 |
| 저장소·배포 | 실제 botocore body·스레드·Starlette ASGI 2.3/2.4·Uvicorn 종료 코드, 테스트 DB 환경과 스키마 정리 | 실제 S3/네트워크/소켓 누수량·컨테이너 종료 E2E·운영 배포·migration 실행 없음 |

HTTP 검증은 실제 FastAPI router와 인메모리 ASGITransport를 사용했다. 브라우저 E2E나 실제 인증 쿠키/HTTP 서버 소켓 검증은 아니다. PG 서비스 동작은 실제 DB이며 SQLite/mock 잠금으로 표현하지 않았다. 외부 LLM/SMTP/S3/Voyage, 운영 DB, 물리적 commit 응답 유실, 전체 부하 시험은 미실행이다.

기존 통합 소스 683개가 그대로이고 앱 패턴을 변경하지 않았으므로 전체 pytest·quality·build는 반복하지 않았다. 기존 1706/2149 통과를 이번 실행에 합산하지 않는다. 설치된 런타임 버전은 [runtime-versions.json](runtime-versions.json)에 별도 기록했다.

## 정확한 실행 집계

아래는 **최종 채택 실행의 서로 다른 테스트 ID 90건**이다. 같은 결함의 서비스/HTTP 재현은 서로 다른 테스트지만 결함 수로 중복 세지 않는다.

| 최종 실행 | passed | failed | skipped | setup errors | collection errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| [이전 PG 재현/대조](logs/prior-pg-recheck.txt) | 3 | 4 | 0 | 0 | 0 |
| [이전 S3 재현/대조](logs/prior-s3-recheck.txt) | 1 | 1 | 0 | 0 | 0 |
| [실제 발행 HTTP + PG](logs/http-publication.txt) | 1 | 2 | 0 | 0 | 0 |
| [설치 SDK 4건 + ASGI 2.3 정리 2건](logs/sdk-http-lifetime-final.txt) | 5 | 1 | 0 | 0 | 0 |
| [실제 SDK/PG 2건 + 기존 nonstream 16건](logs/answer-sdk-and-regression.txt) | 18 | 0 | 0 | 0 | 0 |
| [기존 관련 계약 4파일](logs/focused-contracts.txt) | 53 | 0 | 0 | 0 | 0 |
| [최종 DB 읽기 확인](logs/environment-final.txt) | 1 | 0 | 0 | 0 | 0 |
| **합계** | **82** | **8** | **0** | **0** | **0** |

실패 8건 중 **6건은 확정 결함 3개의 재현**, **2건은 IEA-01의 대역 조건부 재현**이다. 8개 운영 결함 또는 8개 수정 회귀가 아니다. 기존 업무 회귀는 69 passed다. [기계 판독 집계](verification-results.json).

중간 시도도 보존했다. [sdk-http-lifetime.txt](logs/sdk-http-lifetime.txt)는 4 passed/2 failed/skip·setup·collection 0이었다. 실패 1건은 감사 테스트가 transport 진입 전에 0.25초 기한을 켜 진입 장벽에 도달하지 못한 **감사 하네스 오류**다. 첫 SDK 호출의 초기화 지연으로 추정하지만 내부 소요 구간을 별도로 측정하지 않았다. 새 감사 테스트에서 실제 transport 진입 때 기한을 설정하도록 고친 뒤 최종 4개 SDK 대조군이 통과했다. 다른 실패 1건은 S3 재현이다. 이 중간 실행은 위 합계에 다시 넣지 않는다. 증거 발췌 생성기의 최초 실행도 파일 끝을 한 줄 초과해 IndexError가 있었고, 새 감사 도구의 발췌 상한만 보완해 완료했다. 이는 pytest setup/앱 오류가 아니다.

## 재실행 명령과 산출물

저장소 루트 PowerShell에서 실행한다. 로그 stem은 매번 새 이름을 사용한다. 새 launcher는 기존 감사 로그 덮어쓰기를 거절한다.

```powershell
$audit = 'docs/audits/2026-11-02-independent-error-reaudit'
.venv/Scripts/python.exe "$audit/run_checks.py" pg rerun-http-01 "$audit/test_http_publication.py"
.venv/Scripts/python.exe "$audit/run_checks.py" offline rerun-sdk-s3-01 "$audit/test_sdk_cancel_controls.py" "$audit/test_s3_disconnect_shutdown.py"
.venv/Scripts/python.exe "$audit/run_checks.py" pg rerun-sdk-pg-01 "$audit/test_sdk_answer_controls.py"
.venv/Scripts/python.exe "$audit/run_checks.py" pg rerun-prior-pg-01 "$audit/test_reproductions.py"
.venv/Scripts/python.exe "$audit/run_checks.py" offline rerun-prior-s3-01 "$audit/test_s3_reader_lifetime.py"
```

현재 코드에서는 HTTP 2건·S3 각 1건·조건부 답변 2건의 계약 assertion 실패가 예상된다. SDK 정상 취소 대조군의 통과가 조건부 후보의 원천적 불가능성을 증명하지는 않는다.

[run_checks.py](run_checks.py)는 project Python, provider/TEST 환경 제거, 고유한 짧은 basetemp, URL/DB 매개변수 제거 로그를 사용한다. PG만 기존 범위 검사 도우미가 전용 URL을 다시 넣는다. 이전 테스트의 기대값/skip/설정은 변경하지 않았다. [evidence.py](evidence.py)와 [collect_evidence.py](collect_evidence.py)는 새 감사 폴더 안의 기준·해시·집계·발췌만 작성한다. 수정 제안은 구현하지 않았다.
