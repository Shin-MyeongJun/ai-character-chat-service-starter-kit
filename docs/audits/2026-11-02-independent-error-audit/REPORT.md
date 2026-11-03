# 수정 후 독립 오류 감사

실행일: **2026-11-02, Asia/Seoul**. 대상 루트: `C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit`.

## 최종 판단

**확정 결함 4건(P2 4건)을 확인했다.** 실제 PG의 두 연결 교착, 발행 영수증 누락, 실제 PG 과금까지 진행하는 늦은 답변, HTTP 스트리밍 정리 중 S3 body 미회수다. 조건부 결함이므로 건수를 늘리거나 일반적인 P1 장애로 확대하지 않았다. 스타일·명명·추상화 선호는 결함에 포함하지 않았다.

| ID | 우선순위 | 확정 결함 | 관찰 결과 |
| --- | --- | --- | --- |
| IEA-01 | P2 | 답변 공급자가 취소를 흡수하면 기한/호출자 취소 후에도 성공 저장·과금 | 두 조건 각각 AI 메시지 1개, 차감 10, 예약 잔량 0 |
| IEA-02 | P2 | 서로 다른 작품의 발행이 구성요소별 신규 태그를 반대 순서로 만들면 교착 | 별도 PG 연결 2개에서 `40P01`; 한 요청 rollback |
| IEA-03 | P2 | 동일 문서로 돌아온 revision의 발행 성공에 영수증이 남지 않음 | revision 3 성공 후 revision 4 저장, 같은 요청은 충돌; 영수증은 1만 존재 |
| IEA-04 | P2 | HTTP 스트리밍 반복 취소가 S3 close를 취소하고 재회수도 막음 | 작업 read 종료 후에도 `body_close_calls=0`, 실제 raw stream 열림 |

실제 앱 수정·리팩터링·기존 테스트 기대값/skip/검사 설정 변경은 하지 않았다. 이 폴더의 감사 자료만 추가했다. reset/clean/checkout 복원, 기존 파일 삭제/덮어쓰기, 별도 대화·서브에이전트, commit/push는 수행하지 않았다. 수정은 후속 승인된 작업으로 남긴다.

## 기준 상태와 유효 범위

- 시작 HEAD: `31de1428aba2ea67fc887b004221f7bc3884cf0a`.
- 시작 상태: **staged 0, unstaged 추적 파일 46개, untracked 4개**. 삭제된 추적 파일도 대상에 포함했다. 상세 상태와 890개 파일의 SHA-256은 [baseline-start.json](baseline-start.json), 변경 요약은 [git-diff-stat.txt](git-diff-stat.txt)에 있다. 환경 비밀 파일은 해시 목록에서 제외했다.
- HEAD만 읽지 않고 현재 HTTP 연결·서비스·repository·테스트와 관련 unstaged diff를 확인했다. U27의 의존성/재노출 제거, conversation 목록 Command 연결, lorebook 상수 이동을 포함한다.
- 최신 기존 통합 기록의 **683개 대상 파일을 현재 바이트와 비교해 변경 0, 누락 0**을 확인했다. [대조 결과](integration-source-comparison.json). 이전의 전체 API/품질/build 성공은 기존 실행 기록이며 이번 직접 실행 건수에 합산하지 않는다.
- 네 결함의 핵심 코드 파일은 현재 HEAD에도 같은 내용으로 존재한다. 이번 미커밋 정리 때문에 새로 발생한 회귀라고 판정할 근거는 없다. 아래 종류는 **기존 잔여**로 분류하되, 네 구체적 재현은 이번에 새로 확정한 결과다. 원인 도입 commit까지의 전체 역사 감사는 하지 않았다.
- 종료 HEAD와 시작 파일 재해시 대조는 [baseline-end.json](baseline-end.json), 실제 검토 깊이와 파일별 해시는 [reviewed-scope.json](reviewed-scope.json)에 기록한다. 890개 파일을 해시했다는 것이 890개를 같은 깊이로 읽었다는 뜻은 아니다.
- **종료 대조 결과도 HEAD 동일, 기존 890개 파일 변경/삭제 0, 감사 폴더 밖 새 파일 0**이다. 따라서 위 코드 위치와 결과는 검토 시작부터 종료까지 유지된 동일 작업 트리에 유효하다. 검토 깊이를 구분해 목록화한 경로는 113개다.

## IEA-01 — 취소를 흡수한 늦은 답변을 성공 저장하고 과금

**P2 / 기존 잔여.** 취소를 흡수하거나 정상 결과로 바꿔 반환하는 하위 실행이라는 조건이 필요하다. 일반적인 모든 timeout에서 과금된다는 주장은 아니다. 그러나 해당 조건에서 사용자의 취소와 설정한 텍스트 호출 기한이 무시되고 잔액까지 변경된다.

**현재 위치**

- [answers.py:589](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/workflow/answers.py:589): `asyncio.timeout` 경계와 공급자 await.
- 같은 파일 601–620: 반환값 형식·usage를 검사하고 `outcome=succeeded`를 만든다. Timeout 객체의 `expired()/when()` 또는 호출자 취소 상태 재검사는 없다.
- 같은 파일 621–635: CancelledError가 밖으로 전파됐을 때만 취소를 기록한다. 655–660에서 staging·완료로 진행한다.
- [command/answers.py:111](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/command/answers.py:111): 실행 토큰·lease 검사. 실행 lease와 호출 timeout은 별개다.

**외부 호출 경로**

`POST /conversations/{conversation_id}/answers` → `router/answers.py:generate_answer` → `AnswerOrchestrator.generate_answer` → 예약/견적/크레딧 예약 commit → 공급자 → `_stage` → `_complete_staged/_finalize` → 메시지·usage·memory 예약·크레딧 확정.

**발생 순서와 기대/실제**

1. 정상 소유 사용자·마지막 사용자 입력·모델·가격·20 CREDIT 잔액을 준비한다.
2. 공급자 대역은 Event에서 기다리며 CancelledError를 받았다는 사실을 기록한 뒤 유효한 결과를 반환한다. 외부 LLM은 호출하지 않는다.
3. 한 경우에는 설정한 0.5초 텍스트 호출 timeout이 취소를 발생시킨다. 다른 경우에는 진입 Event를 확인한 호출자가 task를 취소한다.
4. 기대는 늦은 성공 결과를 반영하지 않고 기존 timeout/취소의 실패·불확실성 및 정산 정책을 적용하는 것이다. 호출자 취소는 전파돼야 한다.
5. 실제 두 경우 모두 `status=succeeded`, AI 메시지 1개, 크레딧 10 차감이 DB에 확정된다. `check_state`가 usage·예약 committed·소비 원장/배분·잔액 10·예약 잔량 0도 확인한다.

**재현 근거**: [test_reproductions.py](test_reproductions.py)의 `test_late_answer_must_not_be_saved_or_charged`, [최종 PG 로그](logs/reproductions-canonical-v2.txt). 취소 흡수 2건은 계약 assertion 실패, 같은 취소를 전파하는 대조군 2건은 통과했다. 대조군은 각각 failed/cancelled와 차감 0을 확인한다.

**방어가 막지 못하는 이유**: 결과의 형식·provider·usage는 정상이다. 실행 token은 그대로이고 lease는 timeout에 60초를 더한 값이므로 아직 유효하다. 이 검사는 만료된 소유자의 쓰기를 차단하지만, 이미 취소/기한이 지난 현재 소유자의 성공 반환을 구분하지 않는다.

**기존 테스트의 빈틈**: 공급자 timeout 예외와 취소 전파, lease 만료 뒤 늦은 결과는 검사한다. 취소를 정상 결과로 바꾸는 공급자 경계는 검사하지 않는다. U29의 같은 방어는 memory workflow에 있으며 답변 경계에 자동 적용되지 않는다.

**최소 수정 방향/보존 계약**: await 이후와 durable staging 이전에 관찰 가능한 기한·취소 상태를 재검사한다. timeout과 lease를 합치지 않는다. 동일 키 재생, 공급자 재호출 금지, 실패/불확실성 분류, 원자적 정산·rollback과 commit 응답 유실 복구를 유지한다.

**한계**: 공급자 경계는 제어된 대역이다. 운영 OpenAI/Anthropic SDK가 실제로 같은 취소 흡수 행동을 한다거나 그 발생률을 입증하지 않았다. DB 저장·정산은 실제 PG다. HTTP 연결 종료 자체가 항상 서버 task 취소를 뜻한다고 가정하지 않는다.

## IEA-02 — 구성요소별 신규 태그 생성의 교차 순서로 발행 교착

**P2 / 기존 잔여.** 실제 PG가 교착을 검출해 한 트랜잭션을 rollback한다. 모든 발행의 중단이나 영구 교착/데이터 유실로 확대하지 않는다. 서로 다른 작품의 정상 발행이 조건에 따라 실패하고 현재 HTTP에는 이 교착의 업무 재시도 처리가 없다.

**현재 위치**

- [studio_publication.py:312](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:312): 캐릭터별 생성과 태그 해석. 기존 캐릭터도 305에서 태그 교체를 호출한다.
- 같은 파일 379/390: 이후 로어북의 태그를 별도로 해석한다. 작품 태그 갱신은 더 뒤에 있다.
- [tag/repository.py:55](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/tag/repository.py:55): 각 resolve 호출의 이름을 정렬하고 62에서 INSERT ON CONFLICT DO NOTHING을 실행한다. 정렬 범위는 그 호출이다.

**외부 호출 경로**

`POST /products/{product_id}/studio-publication` → `http/studio_publication.py:publish_studio_draft` → `publish_studio` → character create/update·tags → lorebook create/update·tags → product 갱신·발행·영수증. 내부 호출은 한 상위 트랜잭션에 참여한다.

**실행 순서**

| 단계 | 작품 A 트랜잭션 | 작품 B 트랜잭션 |
| --- | --- | --- |
| 1 | 캐릭터 태그 alpha 신규 삽입 | 캐릭터 태그 beta 신규 삽입 |
| 2 | 실제 resolve 완료 뒤 공통 Barrier 도달 | 실제 resolve 완료 뒤 공통 Barrier 도달 |
| 3 | 로어 태그 beta INSERT → B 미확정 삽입 대기 | 로어 태그 alpha INSERT → A 미확정 삽입 대기 |
| 4 | PG가 한 요청을 `40P01`로 중단 | 다른 요청은 발행 성공 |

**기대/실제**: 다른 작품의 정상 발행 둘 다 진행해야 한다. 실제 별도 `pg_backend_pid` 2개에서 결과가 `['40P01', 'ReleaseInfo']`였다. snapshot은 1개, 두 초안은 보존됐다. alpha/beta를 먼저 commit한 대조군에서는 두 발행이 모두 성공하고 snapshot이 2개였다.

**재현 근거**: `test_two_studio_publications_must_not_deadlock_on_cross_component_tags`, [최종 PG 로그](logs/reproductions-canonical-v2.txt). DB 결과·잠금·트랜잭션을 대역으로 만들지 않았다. barrier는 실제 첫 resolve가 완료한 뒤 실행 순서만 제한한다. 임의 sleep으로 교착을 추정한 것이 아니다.

**방어가 막지 못하는 이유**: U04의 advisory→product→draft는 같은 작품을 보호한다. 두 작품의 잠금 키는 다르다. 각 resolve의 이름 정렬은 서로 다른 resolve 호출 사이의 전체 순서를 정하지 않는다. 충돌하는 것은 단순히 호환 가능한 FOR SHARE의 존재가 아니라 미확정 신규 사전 삽입의 unique 대기다.

**기존 테스트의 빈틈**: U25는 두 개의 독립된 단일 resolve의 이름 정렬·500개 경계·관리자 경합을 검사한다. U04는 같은 작품 저장 순서를 검사한다. 하나의 발행이 여러 콘텐츠에서 공유 사전을 반대 순서로 만나는 조합은 빠져 있다. 이번에 기존 관련 PG 테스트가 통과해도 새 재현은 실패했다.

**최소 수정 방향/보존 계약**: 발행 전체에서 사용할 태그 이름의 잠금/해석 순서를 먼저 일관되게 확보하거나, 전체 트랜잭션 교착 재시도에 대한 명시적인 계약을 마련한다. retained inactive 연결의 허용 범위, 관리자 rename/deactivate의 안정성, 콘텐츠별 인가, 발행·매핑·영수증 원자성은 유지한다. 잠금을 단순 제거하지 않는다.

## IEA-03 — 동일 문서 무변경 발행에서 현재 revision 영수증 누락

**P2 / 기존 잔여(U06 재시도 계약의 별도 경로).** 일반 사용자의 초안 편집·되돌림만으로 발생한다. 이미 성공 응답을 준 요청이 나중에는 409가 돼 응답 유실 재생 계약을 위반한다. 기존 snapshot 유실이나 중복 생성은 관찰하지 않았다.

**현재 위치**

- [studio_publication.py:222](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:222): revision별 영수증을 먼저 찾고, 없으면 237에서 현재 revision을 검사한다.
- [같은 파일:241](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:241): 현재 문서 digest가 기존 발행 digest와 같으면 이전 ReleaseInfo만 반환한다.
- 같은 파일 493–508의 현재 revision 영수증 저장까지 도달하지 않는다.

**외부 호출 경로**: `PUT /products/{id}/studio-draft` → `save_studio`로 편집/되돌림 → `POST /products/{id}/studio-publication` → `publish_studio`의 같은 digest 조기 반환.

**재현 순서**

1. 문서 D를 revision 1로 저장·발행한다. snapshot S와 영수증 1이 생긴다.
2. 문서 E로 편집해 revision 2를 저장하고, D로 되돌려 revision 3을 저장한다.
3. revision 3의 발행 요청 R은 성공하며 S를 반환한다. 새 snapshot이 필요 없는 것은 정상이다.
4. E를 다시 저장해 revision 4가 된다. R을 같은 인자 그대로 재전송한다.
5. 기대는 이미 수락한 R의 S를 재생하는 것이다. 실제 영수증에는 1만 있고 R은 `StudioDraftConflictError`가 된다. HTTP는 이 오류를 409로 변환한다.

**근거**: `test_noop_publication_retry_must_survive_later_draft_save`, [최종 PG 로그](logs/reproductions-canonical-v2.txt). `accepted_revision=3`, `later_revision=4`, `receipt_revisions=['1']`, `same_request_conflict=True`, snapshot 수 1을 관찰했다. 실제 공개 저장/발행 서비스와 실제 PG를 사용했다.

**기대 계약의 출처**: `publish_studio`의 docstring과 `use_cases/ARCHITECTURE.md`의 U06 계약은 응답 유실 재호출이 최신 초안 revision과 무관하게 기존 영수증을 반환한다고 명시한다. U06 후속 기록과 같은 revision의 다른 fingerprint 거절 정책도 같은 영수증에 의존한다.

**방어가 막지 못하는 이유**: 소유권·CAS·digest 검사 자체는 정상이다. snapshot 재사용이 현재 revision의 성공한 요청 영수증까지 대신하지 못한다. 이후에는 현재 revision 검사에 먼저 걸려 이전 성공을 알 수 없다.

**기존 테스트의 빈틈**: 일반 발행 경로에서 만든 영수증의 재생과 같은 revision 재시도는 확인하지만, 편집→미발행 변경 되돌림→새 revision의 같은 digest 성공→다음 편집의 조합을 확인하지 않는다.

**최소 수정 방향/보존 계약**: 무변경 발행으로 기존 snapshot을 재사용할 때도 수락한 현재 revision/fingerprint의 영수증을 같은 트랜잭션에 보존한다. 불필요한 snapshot·버전·문서 revision 증가는 피하고, 이전 영수증/매핑, 다른 인자 충돌, 소유권·CAS와 과거 snapshot 불변 계약을 유지한다.

## IEA-04 — 정상 획득 후 HTTP 반복 취소가 S3 close를 영구 건너뜀

**P2 / 기존 잔여(U08의 획득 이후 경로).** worker pool이 바쁘고 close 대기 중 취소가 한 번 더 들어오는 조건이 필요하다. 명시적 회수가 사라져 reader/transport 자원을 신뢰성 있게 반환할 수 없다. 운영에서 영원히 OS handle이 남는다거나 발생률을 측정했다는 뜻은 아니다.

**현재 위치**

- [asset_storage/types.py:184](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/asset_storage/types.py:184): 실제 close 완료 전에 `_closed=True`를 설정한다.
- [s3_storage/adapter.py:78](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py:78): read를 단순 to_thread로 기다린다. 84–88의 close도 task 소유/완료 보장 없이 to_thread를 기다린다.
- [http/media.py:88](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/http/media.py:88): HTTP 응답의 finally에서 `opened.aclose()`를 한 번 호출한다.

**외부 호출 경로**: `GET /characters/media/{id}/content` 또는 상품 버전 미디어 GET → 권한 검사·reader 정상 획득 → `MediaStreamingResponse.__call__` → `opened.read` → 응답 취소 → finally close.

**실행 순서와 결과**

1. 실제 `S3StorageAdapter`가 주입 get_object client에서 정상 reader를 얻는다. body는 **설치된 botocore의 실제 StreamingBody**, raw stream만 gate를 가진 로컬 BytesIO다.
2. 테스트 전용 실행기 한 스레드에서 read를 gate로 멈춘다. 이는 worker pool의 모든 worker가 바쁜 실행 순서를 최소화한 것이다.
3. 응답 task의 첫 취소가 read await를 끝내고 finally로 진입한다. close는 pool에 대기한다. 진입 Event와 실제 큐의 작업 1개를 확인한다.
4. 두 번째 취소가 대기 중 close Future를 취소한다. 이후 read를 해제하고 실행기 barrier까지 통과해 작업 종료를 확인한다.
5. caller가 `opened.aclose()`를 다시 해도 `_closed=True`라 아무 작업이 없다. 실제 `body_close_calls=0`, `raw_stream_closed=False`다.
6. 같은 경로의 단일 취소 대조군은 `body_close_calls=1`, `raw_stream_closed=True`로 통과한다. 테스트 finally는 자체 합성 stream을 직접 회수해 감사 실행이 자원을 남기지 않는다.

**근거**: [test_s3_reader_lifetime.py](test_s3_reader_lifetime.py), [최종 저장소 로그](logs/storage-final.txt). 실제 worker thread와 HTTP 응답을 실행했다. 외부 AWS/S3 요청·실제 네트워크 disconnect는 실행하지 않았다.

**방어가 막지 못하는 이유**: U08의 shield/cleanup 소유는 `read_asset` 획득 도중 취소한 경로에 있다. 이미 정상 반환한 reader와 HTTP finally에는 전파되지 않는다. local reader의 별도 수명 보호도 S3 reader에 적용되지 않는다. adapter 종료는 이미 반환한 reader를 일괄 닫지 않는다. botocore StreamingBody의 destructor도 raw stream을 닫는 대체 보장이 아니다.

**기존 테스트의 빈틈**: HTTP 정리는 AsyncMock reader의 `aclose` 호출 여부를 확인하고, U08은 늦은 reader 획득을 검사한다. 정상 획득 뒤 실제 thread read와 close가 겹치고, close가 executor에서 대기하는 동안 재취소되는 경우는 빠져 있다.

**최소 수정 방향/보존 계약**: 정상 반환 reader의 read/close 작업 수명과 실제 close 완료를 소유하고, 반복 취소에도 회수를 끝내거나 재시도 가능한 상태를 유지한다. idempotent close, 최초 취소/오류 정책, 입력/반환 stream 소유권, SDK timeout/retry와 스트리밍 메모리 계약을 보존한다. U28 업로드 중 DB 잠금의 대체 설계와는 별개다.

## 반박·미확정 후보와 확인한 방어

| 후보 | 판단과 근거 |
| --- | --- |
| 증명 소모가 요청 시작 시각만 사용해 만료 토큰을 허용 | 반박. `identity/repository.py:344`의 UPDATE 조건은 `expires_at > clock_timestamp()`다. 사용자→토큰 순서와 조건부 소모가 있다. 오래된 `now` 인자만 보고 결함으로 세지 않았다. |
| memory lease 만료 즉시 구 토큰 쓰기가 허용되는 것 자체가 결함 | 기록된 정책. U03은 재claim이 token을 대체하기 전까지 기존 token이 유효하다고 명시한다. 재claim 뒤 구 실행 저장/완료/실패는 실제 PG fencing 회귀에서 차단됐다. 이를 새 결함으로 세지 않았다. |
| 긴 이력/모델·참여자·runtime 변경이 준비 검증에서 빠짐 | 새 결함 미확인. 현재 preparation digest는 runtime·모델·참여자·snapshot·현재 입력·history version을 포함한다. 10,050/10,500 이력, 변경/재시도와 범위 동등성의 실제 PG 회귀가 통과했다. 아래 조회량도 직접 관찰했다. |
| commit 응답 유실이 공급자 재호출 또는 이중 과금을 유발 | 지정 경로에서 반박. staging/완료의 새 세션 재조회, 같은 키 재생, 예약/usage 원자성, 격리·수동 복구 회귀가 통과했다. 물리적 네트워크 단절 시험으로 표현하지 않는다. |
| 다른 신고 대상의 평가/접수가 항상 직렬화되거나 순환 생성 | 지정 순서에서 반박. 대상 advisory와 잠금 후 재조회·target-scoped 신고 행 잠금이 있고 실제 PG 그래프 회귀가 통과했다. 임의의 모든 순서에 대한 증명은 아니다. |
| 메일 HTTP 접수 202가 실제 송신 성공을 보장 | 계약 오해. HTTP는 계정/증명/Outbox commit의 접수 성공이다. SMTP는 worker의 별도 실행이며 at-least-once 한계가 기록돼 있다. rollback, claim fencing·5회 상한·만료/무효 증명·암호문 제거의 관련 PG 검사가 통과했다. 외부 메일은 보내지 않았다. |
| 활성 admin 훅 연결이 일반 사용자에게 전역 원본 권한을 줌 | 코드 확인에서 미확인. main의 owner 훅은 검증된 UUID이고 관리자 훅은 별도 세션의 최신 active admin 조회를 요구한다. 내부 공개 콘텐츠 서비스의 trusted caller 계약과 HTTP 인증을 혼동하지 않았다. 이번에 118건의 관리자 HTTP 검사를 새로 실행한 것은 아니며 같은 소스의 기존 통합 결과를 참고했다. |
| 오래된 getMe가 recent owner에 부수효과를 남김 | 미확정. `web/lib/api.ts:200`의 전역 owner 갱신은 hook의 세대 검사보다 먼저 일어날 수 있다. 그러나 조사한 실제 서버 대화 렌더/쓰기에는 별도 active/epoch 또는 명시적 owner가 있어 현재 사용자 기능의 교차 계정 노출·원문 유실을 재현하지 못했다. 확정 결함으로 올리지 않았다. 브라우저 E2E 미실행. |

성능 측정은 결함으로 확대하지 않았다. 긴 이력 회귀 출력에서 1,000/10,050 이력 모두 preparation **33 SELECT / 메시지 102행**, context **6 SELECT / 129행**, revalidation **33 SELECT / 102행**이었다. 신고 평가의 근거 1/10/100개 모두 신고 SELECT 1회·전체 SQL 8회였다. 이는 해당 합성 fixture의 실제 SQL event/행 수이고 운영 지연·throughput·모든 쿼리 계획 측정이 아니다. [로그](logs/selected-pg-contracts.txt).

## 알려진 보류 항목과 문서 대조

- **U19**: 감정·상황·장면별 이미지 표현·선택·스튜디오/채팅/발행 snapshot·기존 데이터 호환을 포함한 전반 재설계는 보류 상태 그대로다. 기존 설계 과제를 새 결함으로 반복하지 않았다.
- **U28 잔여**: 외부 저장 중 DB 잠금의 대체 설계와 전체 업로드 deadline은 보류다. 해싱 offload·취소 때 입력 파일 수명은 구현된 범위로 구분했고 관련 기존 검사가 통과했다. IEA-04는 이미 반환한 다운로드 reader의 별도 자원 회수 결함이다.
- 공통 REPORT의 2026-11-02 상단과 통합 JSON은 현재 683개 소스 해시와 일치했다. 아래 날짜별 과거 실패·미완료를 현재 결과로 옮기지 않았다.
- `U29-WORKLOG.md` 말미의 U03 미완료 설명과 옛 `U02-U05-INTEGRATION-REVIEW.md`의 PG setup 실패/U05 기록 누락은 후속 `U03-WORKLOG.md`, `U05-WORKLOG.md`, 최신 통합 검증으로 대체된 시점 기록이다. 같은 DB setup 실패를 현재 실패로 합산하지 않았다.
- U25 문서는 단일 PG 버전/지정 실행 순서만 검증하며 모든 교착 부재를 보장하지 않는다고 명시한다. IEA-02는 이 한계 안에서 새로 확정한 조합 오류다.
- U08 아키텍처도 정상 반환 후 개별 read/close의 취소 전체를 재설계하지 않았다고 명시한다. IEA-04는 그 제한을 실제 명시적 close 누락까지 재현한 것이다. 기존 완료 기록을 전면 부정하거나 수정 회귀라고 바꾸지 않는다.
- U06의 최신 문서가 약속한 revision 영수증 재생과 실제 무변경 조기 반환은 **IEA-03에서 불일치**한다. U05의 누락 기록은 현재 보완돼 있어 미완료로 보고하지 않는다.

기존 공통 REPORT·WORKLOG·운영 문서는 수정하지 않았다.

## 검토 범위와 검증 한계

| 범위 | 이번 확인 깊이 |
| --- | --- |
| 답변·메모리·과금 | 답변 준비→재검증→예약→calling/result staging→완료/복구, memory 범위/요약 계획·claim 저장/완료를 우선 추적했다. 실제 PG 관련 회귀와 새 결과 저장/과금 재현을 실행했다. 모든 결제·가격 정책 조합의 전수 감사는 아니다. |
| 인증·권한·메일 | 인증/소모/refresh/access, HTTP 관리자 연결, Outbox claim/전송/ack를 확인했다. Outbox는 실제 PG 대조 검사, 관리자 접근은 코드와 해시가 같은 기존 실행 기록을 참고했다. 실제 SMTP/Google/브라우저 쿠키 경합은 미실행. |
| 스튜디오·태그·신고 | 저장/CAS/영수증·조합 발행·tag resolve/관리자 변경과 신고 대상 잠금/평가 경로를 읽고 지정 PG 경합을 실행했다. 새 발행 교착·무변경 영수증을 실제 PG로 재현했다. |
| 저장소·배포 | S3 획득/반환 reader·HTTP finally·업로드 fingerprint를 추적하고 실제 로컬 파일/스레드 회귀를 실행했다. 0036 recovery 정책의 migration/init PG 검사는 포함됐다. 전체 migration/init/ORM/인덱스 비교는 같은 해시의 기존 통합 기록을 대조했으며 이번에 전부 재실행하지 않았다. |
| 프런트 | 최근 대화/계정/대화 화면과 API의 응답 수명 보호를 선택적으로 읽었다. 브라우저·React 실제 렌더러·인증 실 API E2E·빌드는 실행하지 않았다. |

읽은 기준은 AGENTS.md, 모듈 아키텍처/명명 및 백엔드 작성 규칙, 관련 모듈 ARCHITECTURE, 두 기존 REPORT의 현재 판정/관련 수정 구간, U01/U02/U03/U04/U05/U18/U20/U21/U22/U23/U24/U25/U28/U29 전용 기록과 관련 통합 검토·최신 배포/운영 기록이다. 큰 역사 문서와 관련 없는 모듈을 같은 깊이로 모두 읽었다고 주장하지 않는다. 범위/파일별 깊이는 별도 manifest에 있다.

미검사: 실제 LLM/embedding/SMTP/S3 공급자, 운영 DB/production 데이터, 외부 결제 게이트웨이, 실제 프로세스 kill/물리적 commit 응답 유실, 배포/HTTPS/proxy/키 교체 실행, 다중 호스트 시계 편차, 전체 부하·백업 복구, Linux 런타임, 모든 가능한 동시 실행 순서. 준비된 전용 감사 DB 외에는 접속하지 않았다. Docker/볼륨/앱 DB는 변경하지 않았다.

## 실제 실행 집계

아래 네 행은 **중복 없는 최종 집계 대상**이다. 새 재현 테스트는 기대 계약을 assertion하므로 실패가 결함 증거다. 대조군 성공을 결함 수정 완료로 해석하지 않는다.

| 실행 | passed | failed | skipped | setup errors | collection errors | 증거 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 감사 전용 PG 재현 7건 | 3 | 4 | 0 | 0 | 0 | [reproductions-canonical-v2.txt](logs/reproductions-canonical-v2.txt) |
| 기존 지정 PG 업무 회귀 8파일 | 204 | 0 | 0 | 0 | 0 | [selected-pg-contracts.txt](logs/selected-pg-contracts.txt) |
| S3 reader 재현/대조 2건 + 기존 저장소 회귀 62건, 오프라인 | 63 | 1 | 0 | 0 | 0 | [storage-final.txt](logs/storage-final.txt) |
| 최종 전용 DB 환경/잔량 읽기 확인 | 1 | 0 | 0 | 0 | 0 | [environment-after-v2.txt](logs/environment-after-v2.txt) |
| **합계(276건)** | **271** | **5** | **0** | **0** | **0** | 결함 4건, 실패 assertion 5건 |

신규 업무 재현/대조는 **9건 = 4 passed + 5 failed**다. 기존 업무 회귀는 **266 passed**, 환경 확인은 1 passed다. PG 업무 회귀에는 DB를 사용하지 않는 같은 파일의 사례도 포함되므로 204건 전부를 잠금 경합 시험이라고 부르지 않는다. PG 경고 5개는 기존 Alembic path_separator deprecation이다.

초기/중간 실행도 숨기지 않고 남겼다. 다음은 위 합계에 다시 더하지 않는다.

| 시도 | 결과 | 해석 |
| --- | --- | --- |
| `reproductions-first.txt` | 0 passed / 0 failed / 0 skipped / setup 0 / **collection error 1** | 감사 테스트의 기존 helper import 경로 누락. 이 폴더 conftest에서 경로만 보완했다. 앱 결함/DB setup 성공으로 세지 않는다. |
| sandbox `reproductions-second` | 출력/pytest 결과 없이 중단 1회 | 비동기 실행이 진행되지 않아 Ctrl-C로 종료했다. 정확한 내부 원인을 이번에 stack으로 확정하지 않았다. 승인된 동일 로컬 소켓/PG 실행으로 계속했다. 실패/skip/pass에 환산하지 않는다. 중단된 실행의 pytest 수집/실행 건수는 확인되지 않았고 로그도 생성되지 않았다. 현재 앱 결함으로 분류하지 않는다. |
| `reproductions-approved.txt` | 0 passed / 3 failed | 최초 PG 결함 확인. 최종 7건과 중복. |
| `reproductions-final.txt` | 3 passed / 3 failed | 취소/태그 대조군 추가 단계. 최종 7건에 포함. |
| `noop-receipt-reproduction.txt` | 0 passed / 1 failed | IEA-03 단독 확인. 최종 7건에 포함. |
| `s3-reader-reproduction.txt` | 0 passed / 1 failed | 초기 gated body 대역 확인. 최종은 실제 botocore StreamingBody와 단일 취소 대조군을 사용한다. |
| `environment-final.txt`, `environment-after-canonical.txt` | 각각 1 passed | 최종 재현 검증 보강 전의 읽기 확인. 최종 행과 중복. |
| `reproductions-canonical.txt` | 3 passed / 4 failed | snapshot JSON 보존 assertion 추가 전. 최종 v2와 같은 결함 결과이며 중복 합산하지 않는다. |

이번 감사에서는 앱 패턴을 변경하지 않았고, 같은 683개 소스의 전체 통합/품질 결과가 이미 있어 전체 pytest·build·quality를 반복하지 않았다. 기존의 1706/2149 passed와 이번 수치를 합산하지 않는다. URL·비밀번호·토큰·메일 링크·사용자 원문은 로그/보고서에 기록하지 않았으며 DB 예외의 SQL 매개변수 줄도 보존 전에 제거한다.

## 재실행과 산출물

저장소 루트 PowerShell에서 프로젝트 가상환경을 사용한다. 새 재현은 수정 전 현재 코드에서 실패하는 것이 예상 결과다.

```powershell
$audit = 'docs/audits/2026-11-02-independent-error-audit'
.venv/Scripts/python.exe "$audit/run_checks.py" pg rerun-reproductions "$audit/test_reproductions.py"
.venv/Scripts/python.exe "$audit/run_checks.py" offline rerun-s3 "$audit/test_s3_reader_lifetime.py"
```

기존 관련 회귀 명령:

```powershell
.venv/Scripts/python.exe "$audit/run_checks.py" pg rerun-contracts apps/api/tests/test_answer_history_windows.py apps/api/tests/test_memory_claim_fencing.py apps/api/tests/test_answer_billing_integration.py apps/api/tests/test_answer_recovery_policy_db.py apps/api/tests/test_studio_locking_db.py apps/api/tests/test_u25_postgres_concurrency.py apps/api/tests/test_moderation_graph_db.py apps/api/tests/test_identity_mail_outbox.py
.venv/Scripts/python.exe "$audit/run_checks.py" offline rerun-storage apps/api/tests/test_local_storage_lifecycle.py apps/api/tests/test_media_cancellation_contracts.py apps/api/tests/test_media_fingerprint_contracts.py apps/api/tests/test_media_transport_contracts.py
.venv/Scripts/python.exe "$audit/run_checks.py" pg rerun-environment "$audit/test_environment_scope.py"
```

[run_checks.py](run_checks.py)는 자식 환경에서 테스트 DB·외부 공급자 실행 변수/opt-in을 제거한다. PG 실행 때는 **기존 `tools/run_postgres_audit_tests.py`**가 전용 localhost DB·계정 검사를 거쳐 두 테스트 URL만 다시 넣는다. 기존 fixture의 UUID 스키마와 `create_all(checkfirst=False)`/이력 trigger 설치·자체 스키마 정리를 그대로 사용한다. offline은 두 DB URL 없이 실행한다. 두 모드 모두 고유한 짧은 basetemp를 사용한다. 새 실행 로그 이름을 지정해 기존 실행 증거를 보존할 수 있다.

원문 발췌는 [code-evidence.md](code-evidence.md), 파일 검토 깊이·해시는 [reviewed-scope.json](reviewed-scope.json), 실행 집계는 [verification-results.json](verification-results.json), 최종 상태·로그 해시는 [baseline-end.json](baseline-end.json)에 있다. 감사 도구의 초기 import 오류는 감사 도구만 수정했고 기존 테스트의 기대값/skip/설정은 변경하지 않았다.
