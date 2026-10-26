# 두 외부 감사 보고서 통합 및 사실 검증

검토일: 2026-10-23~24, Asia/Seoul. 대상: `CHAT_STARTER_KIT/chat_kit`의 현재 작업 트리.

**두 보고서 모두 실제 문제를 포함한다. 다만 첫 보고서의 광범위한 P1 판정과 즉시 잠금 제거 처방은 그대로 채택하지 않는다. 두 번째 보고서는 발생 조건·설계 이유·검증 한계를 더 잘 구분하며, 이번 독립 재현에서도 주요 결함이 확인됐다.**

이 문서는 두 보고서의 주장을 원인별로 합쳐 검증한 결과다. 새로운 전체 코드베이스 전수 감사를 완료했다고 주장하지 않는다. 애플리케이션 Python 파일 수 363개는 다시 집계했지만, 모든 파일을 같은 깊이로 읽거나 전체 테스트·운영 환경을 검증하지 않았다. 코드의 AI 생성 여부는 결함의 근거로 사용하지 않았다.

## 1. 기준과 검증 범위

- 보고서 A: [첫 번째 원문](source-report-a.txt). 항목 식별자는 `A-P1-01` 등의 원래 번호를 사용한다.
- 보고서 B: [두 번째 원문](source-report-b.txt). 항목 식별자는 `B-01`~`B-16`이다.
- 기준 HEAD: `0f36336246f03a06217d8d8ab96f32e6284960ce`. 기존 미커밋 변경이 다수 있으므로 HEAD만으로 대상 상태를 특정할 수 없다.
- 검증 시작 시 소스·관련 문서·테스트 587개 파일의 SHA-256을 [source-baseline.json](source-baseline.json)에 저장했다. 업무 코드 수정 없이 새 감사 문서와 검증 도구만 작성했다.
- 기존 아키텍처·명명 규칙, 관련 ARCHITECTURE.md, 호출부·repository·모델·마이그레이션 및 일부 테스트를 대조했다.
- 실제 DB 접속, 마이그레이션 실행, 외부 LLM·SMTP·S3 호출, 브라우저 E2E, 부하 시험은 수행하지 않았다. HTTP 확인은 ASGI 메모리 전송과 인증·세션 대역을 사용했다.

판정의 의미:

| 판정 | 의미 |
|---|---|
| 재현 확인 | 실제 함수·훅을 실행하고 대역으로 조건을 제어해 현상을 재현했다. 운영 발생률까지 입증한 것은 아니다. |
| 정적 확인 | 실제 호출·SQL·조건 분기에 근거가 있다. 동시 실행 결과·성능 크기는 별도 측정이 필요하다. |
| 부분 확인 | 구조 일부는 사실이나 원문이 영향·원인·안전한 수정 범위를 과도하게 확정했다. |
| 반박/미입증 | 지정한 경로는 다른 결과를 반환하거나, 삭제·장애 주장의 근거가 부족하다. |

우선순위는 원문과 별도로 정했다. P1은 재현된 핵심 기능 진행 불능, P2는 조건부 기능 결함·동시성 위험·규모 의존 비용, P3는 제한된 개발 환경 또는 유지보수 개선이다. 정책 결정이 필요한 사항은 순위와 함께 보류 조건을 적었다.

## 2. 검증 결과 요약

29개 통합 항목 중 **재현 확인 6개, 정적 확인 17개, 부분 확인 6개**다. 하나의 통합 항목에 여러 하위 주장이 있으면 각 하위 주장에 다른 판정이 있을 수 있다. 별도로 커서 500 주장 등에 반례를 기록했다.

| ID | 통합 문제 | 원문 대응 | 판정 | 우선순위 |
|---|---|---|---|---|
| U01 | 답변 예산과 요약 조건 불일치로 진행 불능 | A-P1-01, B-01 | 재현 확인 | P1 |
| U02 | 계정 전환 뒤 오래된 추가 페이지 혼입 | B-02 | 재현 확인 | P2 |
| U03 | 메모리 claim별 실행 식별 부족 | B-03 | 정적 확인 | P2 |
| U04 | 스튜디오 저장의 잠금 순서 역전 | B-04 | 정적 확인 | P2 |
| U05 | 답변 준비의 전체 이력 반복 조회와 상한 | A-P1-06, B-05 | 정적 확인 | P2 |
| U06 | 재발행 문서·구현 불일치와 로어북 동기화 누락 | A-P1-10 일부, B-06 | 정적 확인 | P2 |
| U07 | 스튜디오 중첩 JSON 구조 검증 누락 | A-P2-01 일부, B-07 | 재현 확인 | P2 |
| U08 | 취소 우선순위와 늦게 반환된 읽기 자원 회수 | B-08, A-P1-09 관련 | 재현 확인 | P2 |
| U09 | 일반 답변 준비의 공유 스냅샷 배타 잠금 | A-P1-02, B-09 | 정적 확인 | P2 |
| U10 | 일반 인증 잠금과 비밀번호 계산 중 잠금 | A-P1-03, B-10 | 정적 확인 | P2 |
| U11 | 대화 페이지마다 전체 사용자 대화 수집·정렬 | A-P1-05, B-11 | 정적 확인 | P2 |
| U12 | 웹의 전체 메시지·소유 상품 재수집 | B-12 | 정적 확인 | P2 |
| U13 | 생성 완료 서비스 조합의 반복 상태 조회 | A-P2-04, B-13 | 정적 확인 | P2 |
| U14 | 발행 중 항목별 조회·flush | A-P1-11, B-14 | 정적 확인 | P2 |
| U15 | 로어 v1 exact·정규식 옵션 의미 불일치 | A-P1-08, B-15 | 재현 확인 | P2 |
| U16 | 세 도메인의 태그 정책 중복 | A-P2-05 일부, B-16 | 정적 확인 | P3 |
| U17 | 종료된 답변 lease 잔류와 복구 인덱스 | A-P1-04 | 부분 확인 | P2·측정 |
| U18 | 답변 예외 분류와 복구 진단의 한계 | A-P1-07 | 부분 확인 | P2 |
| U19 | 이미지 기본값·감정 태그 중복의 DB 오류 노출 | A-P1-10 일부 | 정적 확인 | P2 |
| U20 | 신고 그래프 변경의 전역 잠금 | A-P1-12 | 정적 확인 | P2·측정 |
| U21 | billing→credit 중첩 SAVEPOINT·반복 잠금 | A-P1-13 | 정적 확인 | P2·측정 |
| U22 | SMTP 결과·지연을 통한 계정 구분 경로 | A-P1-14 | 정적 확인 | P2 |
| U23 | test_local 저장소 키 캐시와 Windows 파일 충돌 | A-P1-15 | 재현 확인 | P3 |
| U24 | 기본 관리자·모더레이터 인증 훅 미연결 | A-P2-02 | 정적 확인 | P2·기능 범위 결정 |
| U25 | 통계 재예약·태그 해석의 단건 반복 | A-P2-03 | 정적 확인 | P2·규모 측정 |
| U26 | 보고 타입·매퍼 중복과 불필요한 변환 비용 | A-P2-05 일부, A-P3-01 | 부분 확인 | P3 |
| U27 | 빈 파일·legacy 모델·미사용 주장 | A-P3-02 | 부분 확인 | P3·삭제 보류 |
| U28 | 미디어 업로드 중 잠금과 동기 해싱 | A-P1-09 | 부분 확인 | P2·설계 검토 |
| U29 | SDK 내부 오류 분류와 메모리 작업 기한 | A-P2-06 | 부분 확인 | P2 |

## 3. 통합 항목별 근거와 수정 조건

### U01. 답변이 요약을 요구해도 워커가 아무 작업도 하지 않음

- **재현 확인 / P1.** [answer_preparation.py:109](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/workflow/answer_preparation.py:109)는 rendered 경로에서 바이트+32로 미요약 원문을 계산한다. [summarization.py:16](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/memory/service/command/summarization.py:16)은 role 표기를 포함한 바이트÷4를 사용하고, 74행에서 임계치 미만이면 계획을 만들지 않는다. 워커는 계획이 없으면 완료 처리한다.
- 이번 재현: 800자 ASCII 사용자 메시지 11개, 최대 8,000, 고정 문맥 1,000, 응답 예약 1,200. 답변 경로의 이력 비용은 **9,152**, 가용 예산은 **5,800**, 요약 경로는 **2,222**로 기본 임계치 **4,000**보다 작았다. 실제 함수가 `summary_required=True`와 `plan=None`을 동시에 반환했다. B의 8,320/2,227을 그대로 인용하지 않고 이 재현의 입력과 결과를 보존했다.
- A의 특정 바이트 구간·한국어 과대평가 비율을 모든 설정에 일반화할 수 없다. 공통 단위만 맞추는 것으로도 작은 문맥·큰 고정 문맥에서 진행 보장이 남을 수 있다. 요약 요청 시 축약 필요량을 전달하고 최근 원문 보호로 축약 불가능한 상태를 구분해야 한다. 검증은 ASCII·한글·작은 문맥에서 요약 요청→실제 축약→새 요청 성공까지 이어져야 한다.

### U02. 계정 변경 후 이전 계정의 추가 페이지가 섞임

- **재현 확인 / P2.** [recent-conversations.tsx:29](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/web/components/recent-conversations.tsx:29)의 첫 페이지는 sequence와 active를 확인하지만 56행의 `loadMore`는 확인하지 않는다. 오래된 응답이 현재 목록·커서·로딩 상태를 변경할 수 있다.
- 실제 훅을 TypeScript로 변환해 최소 useState/useEffect 대역과 지연 API로 실행했다. B 계정 첫 목록 `B-first`가 표시된 뒤 A 계정의 늦은 추가 페이지가 도착하면 **`[B-first, A-old-page]`**가 됐다. 브라우저 E2E 또는 서버 인가 우회 재현은 아니다.
- 모든 조회·추가 페이지에 계정/요청 세대 확인을 적용한다. 취소는 보조 수단이며 응답 적용 시 검사도 필요하다. 계정 전환·포커스 갱신·언마운트와 지연 응답 순서를 교차 검증한다.

### U03. 메모리 작업의 lease가 개별 실행을 구별하지 못함

- **정적 확인 / P2.** [repository.py:355](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/memory/repository.py:355)의 재claim은 owner·scope를 재사용할 수 있다. 완료·실패 WHERE에는 conversation/status/owner/scope만 있고 claim별 토큰·attempt·lease 시각 비교가 없다. [memory_worker.py:109](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/memory_worker.py:109)의 owner는 프로세스별 hostname:pid다.
- 동시성 2 이상에서 한 작업이 lease를 넘고 다른 슬롯이 비면 동일 프로세스 재claim이 가능하다. 이전 실행이 새 실행과 같은 owner·scope로 완료/실패를 반영할 수 있다. 결과 저장은 history revision·source UNIQUE를 검사하지만 현재 claim 소유권 전체를 대체하지 않는다. 실제 PostgreSQL 경쟁 실행은 수행하지 않았다.
- claim별 고유 토큰을 추가하고 상태 변경·결과 반영에서 검증한다. lease 갱신 또는 작업 전체 기한을 함께 정의한다. 외부 API의 정확히 한 번 호출을 보장한다고 표현하면 안 된다.

### U04. 스튜디오 저장 경로의 잠금 순서가 서로 다름

- **정적 확인 / P2.** [studio_components.py:64](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_components.py:64)의 revision 지정 저장은 publication 조회를 통해 product→draft를 잠근 뒤 save를 호출한다. [studio.py:38](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/service/command/studio.py:38)의 직접 저장은 advisory→product→draft 순서다.
- 같은 상품에서 기존 revision 수정과 revision 없는 동일 내용 재시도가 겹치면 product를 가진 요청이 advisory를 기다리고, advisory를 가진 요청이 product를 기다리는 순환이 가능하다. 정상 재시도 계약에도 관련된다. 실제 DB deadlock 검출은 아직 실행하지 않았다.
- 모든 진입점에서 같은 잠금 순서를 사용한다. advisory를 단순 삭제하지 않는다. 두 PostgreSQL 연결과 실행 장벽으로 교차 실행·CAS 충돌·동일 내용 재시도를 검증한다.

### U05. 전체 메시지 조회·digest 반복과 10,000개 상한

- **정적 확인 / P2.** [answers.py:90](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/workflow/answers.py:90)와 186·279행의 호출, [answer_preparation.py:61](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/workflow/answer_preparation.py:61), [types.py:180](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/types.py:180)를 대조했다. 정상 신규 준비 경로는 전체 범위 메시지를 세 차례 읽고 준비 digest를 두 차례 계산한다. 일찍 실패하거나 기존 요청을 재생하는 경로까지 항상 세 번이라는 뜻은 아니다.
- 최초 준비는 truncated이면 요약 여부와 관계없이 중단한다. 원문을 삭제하지 않는 요약 정책 아래 10,000개 초과 대화는 계속 같은 상한에 걸릴 수 있다. 전송·할당·직렬화 비용은 사실이나 이벤트 루프 정지 시간·멀티 MB 규모는 측정하지 않았다.
- lore 검색 범위·미요약 범위·요약 이전 꼬리를 필요한 만큼 조회한다. A의 간단한 `(history_revision, current_message, snapshot_id)` 비교로 즉시 바꾸면 runtime·모델 설정·참여자 변경 감지가 빠질 수 있다. digest가 보호하는 모든 입력에 대해 동등한 버전 검증을 마련해야 한다.

### U06. 재발행 문서·구현 불일치와 로어북 상위 정보 미갱신

- **정적 확인 / P2.** [ARCHITECTURE.md:9](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/ARCHITECTURE.md:9)와 [ARCHITECTURE.md:20](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/ARCHITECTURE.md:20)은 변경 문서 재발행 거절을 설명한다. 실제 [studio_publication.py:133](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:133) 이후는 기존 사본 갱신·재발행을 지원한다. 154행 기존 `book_id` 분기는 ID만 사용하고 생성 분기에 있는 제목·설명·태그를 갱신하지 않는다.
- 캐릭터·로어 항목의 수정과 로어북 제목·설명·합산 태그가 달라질 수 있다. 태그를 지워도 이전 연결이 남는 경로다. 공식 재발행 계약 확정이 필요하다.
- 문서에 맞춰 무조건 거절을 복원하기보다 현재 제품 의도를 먼저 결정한다. 재발행 지원이면 메타데이터 동기화·문서·테스트를 함께 맞추고, 미지원이면 허용 경로를 닫는다. 기존 ID·스냅샷 불변성·발행 영수증 멱등성을 보존한다.

### U07. 스튜디오의 중첩 JSON 검증이 소비 조건을 보장하지 않음

- **재현 확인 / P2.** [studio.py:15](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/service/command/studio.py:15)는 크기·버전·프로필 일부만 검사한다. [studio_publication.py:78](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/studio_publication.py:78)의 asset 검사는 이후 145행의 id·mediaId·usage 사용 조건을 충분히 보장하지 않는다.
- 유효한 mediaId를 갖되 `usage: 3`인 asset이 실제 `_publication_content`를 통과하고 `publish_studio`의 문자열 결합에서 TypeError를 발생시켰다. DB 쓰기는 대역이었다. KeyError는 공통 LookupError→404 변환에 섞일 수 있다.
- 초안의 구조 검증과 발행의 업무상 필수 검증을 분리한다. 미완성 초안을 허용하면서 잘못된 자료형·참조는 명시적 입력 오류로 거절한다. A의 커서 500 주장은 이 문제와 분리하며 아래 반례를 참고한다.

### U08. 저장소 취소 후 예외·읽기 자원을 제대로 수거하지 못함

- **재현 확인 / P2.** [media.py:12](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/character/service/workflow/media.py:12)에서 취소를 기억한 뒤 공급자 await가 일반 예외로 끝나면 CancelledError 복원 분기에 도달하지 않는다. 취소 후 공급자 실패 재현에서 최종 예외는 **ValueError**였다.
- [adapter.py:245](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py:245)의 get_object 스레드 대기 중 취소되면 나중에 반환된 Body를 닫을 소유자가 없다. 주입한 가짜 S3 클라이언트에서 늦게 반환된 Body의 close가 호출되지 않았다. 실제 S3 연결 누적 규모를 입증한 것은 아니다.
- 공급자 작업 종료·결과/예외 회수 후 취소 우선순위를 적용하고, 획득 중 취소된 읽기 자원을 정리한다. 현재 shield 대기를 제거해 잠금을 조기 해제하는 처방은 피한다.

### U09. 정상 모델 경로도 공유 스냅샷을 배타적으로 잠금

- **정적 확인 / P2.** [replacement.py:59](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/llm/service/command/replacement.py:59)는 모델 교체 필요 여부를 알기 전에 스냅샷을 `lock=True`로 읽는다. [publication.py:22](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/repository/publication.py:22)는 FOR UPDATE를 실행한다. 답변 준비 두 경로가 이를 호출한다.
- 같은 스냅샷을 사용하는 여러 사용자의 준비 트랜잭션이 경합할 수 있다. LLM 호출 전체 동안 유지되는 잠금은 아니다. A의 정상 경로 비율 99.99% 및 다른 경로와의 deadlock은 입증되지 않았다. 특히 후자는 반대 순서의 실제 경로가 추가로 필요하다.
- 일반 읽기와 교체 결정 경로를 분리하고, 변경 시 잠금 아래 재검증한다. `lock=False`나 ON CONFLICT만으로 교체·버전 종료 정책 전체가 보존된다고 가정하지 않는다.

### U10. 일반 인증 잠금과 비밀번호 계산 동안의 사용자 잠금

- **정적 확인 / P2.** [authentication.py:223](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/identity/service/authentication.py:223)의 로그인은 FOR UPDATE 사용자 조회 후 Argon2 검증·재해시를 기다린다. 같은 파일의 `_require_session`과 `get_authenticated_user`도 사용자·세션 행을 잠근다. [repository.py:30](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/identity/repository.py:30) 및 121행이 실제 SQL 근거다.
- 같은 사용자의 요청 간 경합은 존재하지만 인증 트랜잭션은 인증 함수 반환 시 끝난다. 모든 HTTP 업무 처리 내내 직렬화한다는 해석은 과장이다. 비밀번호 해싱은 to_thread이므로 이벤트 루프에서 직접 실행하는 것도 아니다.
- 일반 access 검증과 refresh/폐기 경로를 구분하고, 비밀번호 검증은 잠금 밖에서 수행한 뒤 해시·상태를 재확인하는 방안을 검토한다. 재설정 직전 비밀번호로 폐기에서 빠진 새 세션이 만들어지지 않는다는 보안 계약을 보존한다.

### U11. 대화 한 페이지를 위해 전체 대화를 읽고 정렬

- **정적 확인 / P2.** [conversation_directory.py:34](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/use_cases/conversation_directory.py:34)는 JOIN 금지를 이유로 명시하고, 44~58행에서 100개 배치 전체 수집→활동 조회→전체 정렬→슬라이싱을 수행한다.
- 수집 O(N), 정렬 O(N log N). 기본 주요 조회 구조는 비어 있지 않은 배치마다 대화·활동 두 번이다. A의 2,000개/약 40회는 정적 예시로 타당하지만 운영 측정값이 아니다. 추가 인증 쿼리 등을 포함한 전체 HTTP SQL 수와 구분한다.
- 소유자 조건을 보존한 제한적 읽기 projection에서 ORDER BY/LIMIT을 처리하는 예외를 검토한다. 새 활동으로 인한 커서 이동·빈 대화의 생성 시각 fallback·총 개수 계약을 보존한다. 별도 집계 컬럼 추가가 반드시 첫 선택일 필요는 없다.

### U12. 웹이 페이지 API를 다시 전체 수집 API로 사용

- **정적 확인 / P2.** [api.ts:169](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/web/lib/api.ts:169)의 메시지 헬퍼는 커서가 끝날 때까지 순차 수집한다. [page.tsx:133](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/web/app/chats/[id]/page.tsx:133)과 141행은 입력 저장 후와 답변 종료 후 이를 다시 호출한다.
- [account.ts:31](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/web/lib/account.ts:31)는 소유 상품 전체를 읽고 계정 개요의 Promise.allSettled에 포함한다. useAccount는 결과를 저장하지만 실제 비미리보기 작품 화면은 별도의 페이지 상태를 사용한다. 따라서 정상 계정 화면이 불필요한 전체 상품 수집 완료를 기다리는 구조다.
- 정상 append는 ID 기반 반영, 수정·삭제·revision 불일치 때는 재동기화하도록 범위를 줄인다. 먼저 실제로 사용하지 않는 전체 상품 조회를 제거할 수 있다. 재시도·복구·메시지 중복 제거 의미는 보존한다.

### U13. 생성 완료 계층이 같은 상태를 반복 조회

- **정적 확인 / P2.** [answers.py:530](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/workflow/answers.py:530) → 같은 파일 775행 → [generation.py:151](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/command/generation.py:151)의 정상 pending 성공 경로에서 generation 상태 SELECT 8회, conversation 잠금 조회 3회를 정적으로 추적할 수 있다. 결제·통계·메모리의 다른 SQL은 제외한다.
- [repository.py:181](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/repository.py:181)는 명시적인 select라 identity map이 있어도 조회를 생략하지 않는다. 반면 session.get을 사용하는 다른 호출까지 무조건 SQL로 세면 안 된다. 독립 공개 서비스의 진입 검사는 이유가 있다.
- 같은 모듈 내부에서 이미 잠긴 상태를 처리하는 경로를 분리하거나 상태 전이 결과를 반환해 재사용한다. ORM을 모듈 간 공개하는 방식으로 우회하지 않는다. 완료·크레딧·메모리 예약의 원자성과 재전송 멱등성을 SQL 수와 함께 검증한다.

### U14. 발행 중 항목별 저장·flush·단건 조회

- **정적 확인 / P2.** [publication.py:125](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/service/command/publication.py:125) 이후 연결마다 저장하고 시작 항목을 개별 조회한다. [publication.py:100](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/repository/publication.py:100) 이후 target/start 등은 즉시 flush한다. 스튜디오도 구성요소별 공개 서비스를 순차 호출한다.
- 항목 수에 따라 DB 왕복과 잠금 구간이 늘어난다. 단, 모든 flush가 불필요한 것은 아니며 FK·스냅샷 ID 확보 단계는 필요하다. `await flush()`를 “동기식 DB 호출”이라고 부르는 A의 표현은 부정확하다.
- 일괄 조회·add_all 및 단계별 flush를 사용하되 같은 AsyncSession을 병렬 태스크로 실행하지 않는다. UUID를 미리 만드는 것만으로 DB 제약과 삽입 순서가 모두 해결되지는 않는다.

### U15. 로어 v1의 정규식·exact 옵션 계약 불일치

- **재현 확인 / P2.** [activation.py:31](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/lorebook/service/activation.py:31)와 [matching.py:12](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/lorebook/service/util/matching.py:12)를 실제 호출했다. `case_sensitive=True`인 regex `ABC`가 `abc`에 일치했고, v1 `exact`가 `prefix ABC suffix`에 일치했다.
- exact 문제는 v1 옵션이 있는 분기에 한정된다. 옵션 없는 legacy exact는 완전 일치 분기가 있다. 스튜디오 v1은 주로 contains를 생성하므로 모든 정상 스튜디오 로어가 exact 오류를 겪는 것은 아니다. 잘못된 regex에는 InvalidLorebookRegex가 발생하지만 모든 HTTP 경로가 500인지는 별도다. 스튜디오 진단의 공통 ValueError→422와 저장 시 검증을 고려해야 한다.
- v1 옵션을 컴파일 플래그·캐시 키에 반영하고 exact 의미를 명시한다. legacy의 대소문자 무시·선형 시간 정규식 엔진을 유지한다. 라이브 query가 legacy 정책인 사실만으로 최신 snapshot 경로와 무조건 통합하면 의미가 바뀔 수 있다.

### U16. 태그 정책의 세 도메인 복제

- **정적 확인 / P3.** character/lorebook/product의 `service/tags.py`, `mapper/tags.py`, `mapper/tag_schema.py`, `tag_router.py`를 대조했다. 12개 파일은 맞지만 현재 물리적 줄 수는 **982줄**이다. A의 1,100줄·95~100% 중복률은 동일 기준으로 재현되지 않았다.
- 순서·보존·비활성 태그·admin/system 보호 정책은 반복된다. 부모 테이블·인가 조건·공개 접근 정책은 도메인마다 정당한 차이가 있다. `/me` 경로 차이가 곧 결함이라는 증거도 없다.
- 공유할 것은 태그 선택·보존·제거의 순수 정책과 계약 테스트다. 공통 repository 프레임워크·도메인 테이블 통합으로 확대하지 않는다. 근거: [tags.py:54](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/character/service/tags.py:54), [tags.py:54](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/lorebook/service/tags.py:54), [tags.py:56](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/service/tags.py:56).

### U17. 종료 lease 잔류와 복구 인덱스 비용

- **부분 확인 / P2·측정.** [repository.py:275](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/repository.py:275)는 종료 시 lease를 NULL로 만들지 않는다. 244행의 복구 쿼리는 status=pending과 lease 만료를 필터링한다. [0018_nonstream_answers.py:16](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/alembic/versions/0018_nonstream_answers.py:16)은 lease 단일 인덱스다.
- 완료 행이 복구 결과에 포함되는 기능 오류는 아니다. 데이터가 누적되면 불필요한 인덱스 후보가 늘 가능성은 있지만 PostgreSQL이 언제나 전체 인덱스·힙을 선형 스캔한다는 A의 단정은 실행 계획 없이 확정할 수 없다.
- pending partial index를 검토하고 분포별 EXPLAIN ANALYZE로 확인한다. 종료 lease의 이력적 의미를 확인한 뒤 정리한다. NULL 업데이트만으로 모든 인덱스 비용이 사라지는 것도 아니다.

### U18. 답변 예외 분류·복구 진단의 한계

- **부분 확인 / P2.** [answers.py:265](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/chatting/chat/service/workflow/answers.py:265)는 예상 밖 준비 오류를 실패 metadata로 변환한다. 491행의 완료 조율은 넓은 예외를 저장 복구 대기로 변환하고, 669행의 복구 로그는 오류 종류만 기록한다. 결정론적 내부 결함이 반복 복구될 가능성은 있다.
- 그러나 동일 request_key에 저장된 실패를 재생하는 것은 멱등성 설계 일부다. 모호한 commit 뒤 새 LLM 호출·중복 결제를 막기 위한 넓은 예외 경계도 필요하다. A의 “모든 except Exception 제거” 식 처방은 위험하다.
- 단계별 오류 분류·상관 ID·반복 횟수·안전하게 정제된 stack 진단을 보강한다. 원문·공급자 메시지·자격증명이 포함될 수 있는 traceback을 무조건 운영 로그에 출력하지 않는다. 복구 재시도 상한·격리 정책은 미확정 commit의 처리 계약과 함께 정한다.

### U19. 중복 이미지 제약 오류가 도메인 오류로 변환되지 않음

- **정적 확인 / P2.** [character.py:82](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/db/models/character.py:82)는 감정 태그 UNIQUE와 기본 이미지 partial UNIQUE를 갖는다. [media.py:260](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/character/service/media.py:260)의 신규 첨부는 기존 기본 이미지 해제·중복 감정 태그의 명시적 변환 없이 repository 삽입으로 간다. character router는 IntegrityError를 변환하지 않는다.
- A의 “유니크 제약조건 누락”은 잘못된 설명이다. **제약은 있고 충돌 처리 계약이 부족한 것**이다. 두 번째 기본 이미지 신규 첨부 등의 조건에서 DB 오류가 노출될 정적 경로다. 실제 PostgreSQL HTTP 500 재현은 이번 범위에 없다.
- 새 기본 이미지가 기존 것을 대체해야 하는지, 아니면 명시적 선택 API를 쓰게 해야 하는지 결정한다. 자동 기본값 해제를 곧바로 적용하지 않는다. 예상 제약 충돌만 업무 오류로 변환하고 동시 삽입도 검증한다.

### U20. 신고 그래프의 전역 잠금과 단건 탐색

- **정적 확인 / P2·측정.** [reports.py:149](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/governance/moderation/service/command/reports.py:149)와 [assessments.py:96](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/governance/moderation/service/command/assessments.py:96)은 같은 graph advisory lock을 사용한다. 접수의 중복 체인과 평가 대상 신고를 단건 조회한다.
- 서로 다른 대상까지 직렬화하는 것은 사실이지만, 그래프 순환·접수 상태 변경과 평가의 충돌을 막는 목적도 코드에 있다. 운영자 수·경합이 없는데 치명적 확장 장애라고 단정할 수 없다.
- 중복 링크가 같은 target으로 제한되는 점을 활용한 target별 잠금은 후보가 된다. 모든 graph reader/writer가 동일 규칙을 사용하고 target 불변성·잠금 후 재검증을 확보해야 한다. 미리 ID를 아는 평가 목록은 배치 조회할 수 있지만 next_id를 따라가는 체인을 단순 IN 하나로 대체할 수는 없다.

### U21. billing→credit의 중첩 SAVEPOINT와 반복 잠금

- **정적 확인 / P2·측정.** [credits.py:95](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/commerce/billing/service/credits.py:95)와 [command.py:80](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/commerce/credit/service/command.py:80) 등에서 실제 begin_nested가 겹친다. billing이 신용 계정을 잠근 뒤 하위 credit 경로가 다시 잠그고 조회한다.
- 공통 use_case_transaction 자체는 SAVEPOINT를 만들지 않지만 이 두 모듈은 별도로 만든다. 같은 트랜잭션이 같은 행을 다시 잠근다고 다른 트랜잭션처럼 자기 대기에 빠지는 것은 아니다. 주요 비용은 반복 SQL·savepoint 왕복이다.
- 하위 실패 후 상위가 예외를 잡고 계속하는 계약·세션 오류 복구 필요성을 확인한 뒤 경계를 줄인다. 계정 락과 billing request 락은 보호 대상이 다르므로 함께 삭제하지 않는다. 실제 SQL 수와 충돌/잔액 부족/멱등 재시도를 확인한다.

### U22. 메일 발송 유무·실패를 통한 계정 구분 경로

- **정적 확인 / P2.** [mail.py:12](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/identity/service/workflow/mail.py:12)는 대상이 None이면 즉시 반환하고, 대상이 있으면 SMTP 완료를 기다린다. [adapters.py:32](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/identity/adapters.py:32)는 SMTP 오류를 mail_unavailable로 바꾸며 [http_security.py:30](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/identity/http_security.py:30)은 이를 503으로 노출한다. 정상 요청 응답은 202다.
- 따라서 실패·응답 지연 차이의 정보 경로는 있다. A의 5ms/10초 실제 응답 수치와 “전수 판별” 성공률은 검증되지 않았다. SMTP는 asyncio.to_thread에서 실행하므로 이벤트 루프를 직접 막는다는 뜻도 아니다. identity 문서는 타이밍 동일성을 현재 보장하지 않는다고 명시한다.
- 요구하는 계정 비공개 수준을 정하고 큐/Outbox 및 외부 응답 통일을 검토한다. 실패를 숨겨 메일 발송 성공으로 오인시키지 않도록 재시도·관측성을 함께 설계한다.

### U23. test_local의 키 캐시와 Windows 읽기/삭제 충돌

- **재현 확인 / P3.** [adapter.py:70](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/asset_storage/adapters/test_local_storage/adapter.py:70)의 키별 Lock 사전은 제거되지 않는다. read_asset은 파일을 연 뒤 락을 풀고 reader를 반환한다.
- 실제 로컬 어댑터·임시 파일을 사용해 열린 reader가 있는 동안 삭제하면 Windows PermissionError가 access_denied AssetStorageError로 변환되는 것을 확인했다. 테스트의 21개 lock 키도 남았다. 장시간 메모리 증가율은 측정하지 않았다.
- A의 별도 “메타데이터 롤백 오류로 파일 유실”은 입력·실패 지점·재현 없이 확정할 수 없다. 코드에는 이전 metadata 복원 분기가 있다. reader 전체 수명 동안 락을 유지하면 느린 스트리밍이 삭제를 오래 막으므로 파일 수명·참조 계수·버전 객체 정책도 검토한다. 운영 S3 장애와 같은 P1로 취급하지 않는다.

### U24. 기본 관리자·모더레이터 훅이 503으로 닫혀 있음

- **정적 확인 / P2·기능 범위 결정.** [main.py:224](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/main.py:224) 이후는 session과 owner만 override한다. [character_dependencies.py:37](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/http/character_dependencies.py:37), lorebook 및 product 관리자 훅은 기본적으로 503을 반환한다. 라우트가 이 훅을 사용하는 사실도 확인했다.
- 문서화된 fail-closed 미연결 기능이다. 기대한 관리 기능이 제공되지 않는 문제와 인가 우회 취약점은 구분한다. content query가 HTTP 호출자의 인가를 전제로 한다고 해서 누구나 외부에서 호출할 수 있다는 뜻은 아니다.
- 현재 제공해야 할 관리자 기능 범위를 확정한 뒤 실제 권한 검증을 연결한다. 서비스 경계의 신뢰 주체·역할 정책을 문서화하고 일반 사용자·정지 관리자·미설정 배포에서의 거절을 검증한다.

### U25. 통계 재예약·태그 해석의 단건 반복

- **정적 확인 / P2·규모 측정.** [statistics.py:36](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/service/command/statistics.py:36)는 전체 발행 상품×(days+1)회 mark_statistics_dirty를 순차 호출한다. [statistics_queue.py:13](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/service/command/statistics_queue.py:13)는 건별 upsert다. [command.py:18](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/tag/service/command.py:18)도 정렬된 이름마다 resolve를 수행한다.
- A의 16만 번은 실제 현재 데이터 건수가 아니다. 예를 들어 상품 5,000개×32일이면 160,000개 upsert가 되는 식이다. 통계 집계 저장 전체가 항상 단건 삽입인 것도 아니며 repository의 일부 사실/통계 삽입은 이미 배치화되어 있다.
- 큐 upsert와 이름 resolve의 배치를 검토하되 이름별 잠금 순서·unique 충돌·비활성 태그 보존 정책을 유지한다. repair 빈도·상품 수·태그 수에 따라 우선순위를 정한다.

### U26. 보고 매퍼 중복·deepcopy·형식적 전달 함수

- **부분 확인 / P3.** [persistence.py:71](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/governance/moderation/mapper/persistence.py:71)에는 항등 scalar 매퍼가 있다. [persistence.py:120](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/product/mapper/persistence.py:120) 및 moderation의 필드 반영 매퍼는 scalar까지 deepcopy한다. JSON·가변 metadata의 깊은 복사는 격리에 의미가 있다.
- creator/operations의 metrics·day 매퍼는 상당히 비슷하지만 현재 reporting 매퍼는 fields/getattr 방식이며 deepcopy를 사용하지 않는다. operations에는 추가 prompt 조회 타입도 있어 “타입·매퍼 전부 100% 동일”은 부정확하다. 별도 공개 타입은 노출 필드·역할 경계를 유지하는 이유가 있다.
- 이번 정의에서 단일 return Call/await Call 함수는 307개였으나 생성자·매핑도 포함해 “무의미한 패스스루” 수가 아니다. A의 273개는 분류 기준·대상 스냅샷 없이 검증할 수 없다. 작은 함수/파일 개수만으로 계층 삭제를 권하지 않는다. 불필요한 scalar 복사·항등 변환부터 좁게 줄이고 실제 hotspot을 측정한다.

### U27. 빈 파일은 존재하나 legacy 모델의 안전한 삭제는 미입증

- **부분 확인 / P3·삭제 보류.** 비-__init__ 0바이트 파일 5개는 재확인했다: chat/stream.py, memory/schemas.py, billing/router.py, billing/schemas.py, admin/router.py. 15줄 이하 Python 파일은 물리적 줄 수 기준 90개였으며 A의 99개와 다르다.
- SubscriptionPlan/UserSubscription/ModerationFlag는 모델 등록·FK·기존 스키마와 문서에 남아 있다. 업무 서비스 사용이 적다는 사실만으로 과거 데이터·마이그레이션·외부 소비자까지 없는 dead code라고 볼 수 없다. 미구현 정책 스텁이 DB에 저장된다는 A-P3-01의 구체적 주장은 대상 식별이 부족하다.
- 빈 호환 경로는 import·배포 진입점부터 확인하고 제거할 수 있다. DB 모델·테이블은 데이터 조사·이전/롤백 계획 없이 삭제하지 않는다. 삭제 후보와 삭제 가능 확정을 분리한다.

### U28. 업로드 중 잠금과 동기 파일 fingerprint

- **부분 확인 / P2·설계 검토.** [media.py:48](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/character/service/workflow/media.py:48) 이후는 저장 종료까지 DB 잠금을 유지한다. [media.py:35](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/content/character/service/media.py:35)의 fingerprint는 동기 seek/read/SHA-256이며 이벤트 루프에서 실행될 경로다.
- 긴 잠금·파일 처리 비용은 실재한다. 그러나 [adapter.py:79](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py:79)에 connect/read timeout과 retry 설정이 있으며 실제 전송은 to_thread다. “S3 타임아웃 전무·전체 전송이 이벤트 루프를 정지”라는 해석은 맞지 않는다. 워크플로 전체 deadline이 없다는 별도 지적은 가능하다.
- 잠금은 취소된 공급자 스레드와 재시도/GC의 경쟁을 막는 명시적 계약이다. 해싱 offload는 좁은 개선 후보지만 스레드가 끝나기 전에 업로드 스트림을 닫지 않아야 한다. 네트워크 I/O를 잠금 밖으로 옮기는 변경은 execution token·상태 소유권·정리 배제 같은 대체 보장을 설계한 뒤 수행한다.

### U29. SDK 내부 오류 분류와 메모리 작업 전체 기한

- **부분 확인 / P2.** [openai.py:100](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/llm/adapters/openai.py:100)와 Anthropic의 catch-all은 [base.py:125](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/llm/adapters/base.py:125)에 status가 없는 TypeError도 전달해 retryable PROVIDER 오류로 만들 수 있다. 메모리 작업은 이 retryable을 보고 기본 최대 횟수 안에서 다시 예약한다.
- 다만 Voyage의 catch-all은 retryable=False이므로 모든 SDK 오류가 5회 재시도되는 것은 아니다. [openai.py:46](C:/Users/smj/Desktop/CHAT_STARTER_KIT/chat_kit/apps/api/app/modules/llm/adapters/openai.py:46)와 Anthropic에는 기본 60초 timeout이 있고 embedding도 worker에서 설정한다. “타임아웃이 전혀 없다”는 주장은 과장이다.
- SDK 통신 예외와 프로그래밍/파싱 오류를 구분한다. 요청별 timeout과 작업 전체 deadline·lease 갱신은 별개로 정의한다. 잘못된 공급자 응답·내부 TypeError·실제 timeout에 대한 재시도 분류를 각각 검증한다.

## 4. 원문에서 그대로 채택하지 않은 주장

| 원문 주장 | 검증 결과와 처리 |
|---|---|
| A-P2-01: 커서 변환이 오류 context 밖이므로 잘못된 요청은 500 | character/lorebook의 불완전 cursor_id 요청을 실제 ASGI로 보내 **422**를 확인했다. DTO validator가 pair·timezone을 먼저 검사한다. mapper의 방어 분기가 밖에 있다는 사실만으로 외부 입력 500을 입증하지 못한다. 다른 미제시 경로까지 모두 안전하다고 결론내리지는 않는다. |
| A-P1-09: S3 timeout이 없음 | SDK connect/read timeout과 retry 설정이 있다. 전체 workflow deadline 부재와 구분한다. |
| A-P1-10: 이미지 UNIQUE 제약 누락 | 제약은 있다. 충돌을 업무 오류로 번역하는 계약이 부족한 문제다. |
| A-P1-02: 일반 모델 경로 99.99%, 다른 작업과 deadlock | 비율 측정·반대 잠금 순서가 제시되지 않았다. 공유 행 경합은 별도로 확인했다. |
| A-P1-04: 항상 전체 인덱스·힙 선형 스캔 | 실제 실행 계획 없이 확정할 수 없다. partial index 후보와 기능 버그를 구분한다. |
| A-P3-02: legacy ORM은 바로 삭제 가능한 dead code | 등록·FK·기존 데이터/마이그레이션 계약이 남아 있다. 안전한 삭제는 미입증이다. |
| A의 42곳 잠금·99개 짧은 파일·1,100줄 태그 중복 | 현재 소스 기준 direct with_for_update 호출 31개+해당 keyword 7개, 짧은 파일 90개, 지정한 태그 12파일 982줄이다. 전체 FOR UPDATE 가능 경로 수와 AST 위치 수는 다르며 집계 기준 없이 원 숫자를 사용하지 않는다. |
| 두 보고서가 주장한 기존 검증 실적 | 이번에 실행한 검증만 아래에 독립적으로 기록했다. 원문이 주장한 전체 파일 독해·과거 실행 결과는 그대로 인증하지 않는다. |

## 5. 아키텍처 규칙과 테이블 분리의 통합 판단

1. **조회 projection 예외를 좁게 검토한다.** U11은 모듈 간 결과 JOIN 금지가 직접 전체 수집을 유도한 사례다. 읽기 모델의 소유자·사용 컬럼·인가 조건·변경 책임을 명시하고, 타 모듈 쓰기나 repository 임의 접근을 허용하는 예외로 넓히지 않는다.
2. **독립 공개 진입점과 내부 조합을 구분한다.** U13·U21처럼 이미 획득한 잠금·검증을 내부에서 재사용할 계약이 필요하다. 반대로 모든 서비스의 검사를 제거하면 독립 호출 안전성이 사라진다.
3. **계층 수보다 역할과 비용으로 평가한다.** Command/Info는 공개 경계에서 가치가 있고 mapper의 가변 데이터 격리는 필요하다. 내부 항등 변환·불필요한 scalar deepcopy는 별도로 줄인다. “273개 함수가 짧으니 전부 합친다”는 식의 변경은 권하지 않는다.
4. **행 잠금·트랜잭션은 보호하는 불변 조건과 함께 바꾼다.** 미디어 공급자 종료 대기, 인증 재설정과 세션 발급, 결제 멱등성, 신고 그래프는 대비 구조라는 이유만으로 제거할 수 없다.
5. **동작 계약·아키텍처 문서·테스트를 같이 갱신한다.** U06은 규칙 준수 검사만으로 업무 계약 변화를 잡지 못하는 사례다. 진행 보장·잠금 순서·계정 변경·취소·재시도 검증이 필요하다.

현재 두 보고서와 이번 대조에서 **구체적으로 안전한 테이블 통합 후보가 확정되지는 않았다.** 원본/스냅샷의 가변성·보존 기간, 견적/예약/결과 연결의 상태 전이·소유권, 지갑/원장의 현재값과 사실 이력, 선택적 대용량 prompt, 공개/내부 태그의 인가 차이는 분리의 근거다. 모든 테이블이 최적이라는 의미는 아니며, 테이블별 cardinality·접근 빈도·항상 함께 변경되는지·보존/삭제 정책을 추가 조사해야 한다. 조회가 비효율적이라는 이유로 저장 테이블을 먼저 합치지 않는다.

## 6. 실행 순서와 검증 기준

| 단계 | 대상 | 완료 기준 |
|---|---|---|
| 1. 기능 진행·정보 경계 | U01, U02 | 요약 필요 상태가 실제 축약 또는 명시적 불가능 상태로 진행하고, 이전 계정 응답이 현재 상태에 적용되지 않음 |
| 2. 동시성 소유권 | U03, U04, U08 | stale claim이 상태를 바꾸지 못함, 실제 PG 교차 잠금 시험 통과, 취소 후 공급자/읽기 자원 정리 |
| 3. 입력·발행·로어 계약 | U06, U07, U15, U19 | 공식 재발행 계약 결정, 메타데이터/태그 동기화, 잘못된 구조의 명시적 오류, 옵션별 일치 동작 |
| 4. 긴 대화와 큰 데이터 | U05, U11, U12 | 10,000개 경계 해결, 페이지 비용이 전체 이력/전체 소유 목록에 불필요하게 비례하지 않음 |
| 5. 반복 SQL·잠금 비용 | U09, U10, U13, U14, U17, U20, U21, U25, U28 | SQL 수·잠금 시간·실행 계획 전후 비교와 기존 경쟁/멱등 계약 통과 |
| 6. 오류·운영 기능 | U18, U22, U24, U29 | 안전한 오류 분류/진단, 계정 정보 노출 수준 결정, 관리자 기능 범위 및 fail-closed 검증 |
| 7. 유지보수 정리 | U16, U23, U26, U27 | 공통 순수 정책 적용, 로컬 저장 수명 정의, 호환 경로/DB 데이터 확인 후 좁은 정리 |

이는 수정 계획 후보이며 구현 승인이 완료됐거나 각 최소안의 안전성이 검증됐다는 의미가 아니다. 이번 작업은 통합·사실 검증까지이며 업무 코드를 변경하지 않았다.

## 7. 재현 도구·실행 결과

- [verify_claims.py](verify_claims.py): 실제 Python 함수, 가짜 세션/공급자, ASGI 요청 및 임시 로컬 파일로 검증. DB·외부 API 불사용.
- [verify_frontend.cjs](verify_frontend.cjs): 실제 훅을 TypeScript transpile 후 최소 hook harness에서 실행. 실제 React renderer/브라우저 E2E는 아님.
- [verification-results.json](verification-results.json), [frontend-verification.json](frontend-verification.json), [python-verification.log](python-verification.log): 입력·관찰 결과·집계 기준.
- [pytest.log](pytest.log): 기존 관련 테스트 **80개 중 79개 통과, 1개 실패**. 실행 파일은 test_studio_publication, test_studio_draft_guard, test_lorebook_snapshot_activation, test_asset_storage, test_identity_security다. TEST_DATABASE_URL은 이 자식 실행 환경에서 제거했다.
- 실패한 test_edit_after_first_publication_does_not_change_product_visibility는 SimpleNamespace 대역에 product_id가 없어 mapper에서 AttributeError가 났다. 이는 기존 fixture/계약 불일치의 증거이며, 이 실패 하나를 운영 재발행 장애 재현으로 해석하지 않는다. 테스트를 고치거나 기대 계약을 임의 변경하지 않았다.
- [source-verification.json](source-verification.json): 검증 종료 시 baseline 파일의 변경 여부와 문서 링크 확인 결과를 기록한다.

재실행 명령(저장소 루트, PowerShell):

```powershell
.venv/Scripts/python.exe docs/audits/2026-10-23-structural-review/verify_claims.py
node docs/audits/2026-10-23-structural-review/verify_frontend.cjs
$env:PYTHONPATH = (Join-Path (Get-Location) 'apps/api')
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p no:cacheprovider apps/api/tests/test_studio_publication.py apps/api/tests/test_studio_draft_guard.py apps/api/tests/test_lorebook_snapshot_activation.py apps/api/tests/test_asset_storage.py apps/api/tests/test_identity_security.py -q --tb=short
```

첫 번째 보고서의 넓은 성능·삭제 주장을 보수적으로 교정하고, 두 번째 보고서의 구체적 기능·동시성 지적을 통합한 문서다. 다음 판단에 필요한 운영 자료는 이력 크기 분포, 모델 문맥/요약 정책 조합, 작업 처리 시간과 lease 분포, PG 잠금 대기·실행 계획, 발행 구성요소 수와 SQL 수다.
