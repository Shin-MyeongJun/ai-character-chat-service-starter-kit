# AI 감사 보고서 F08–F29 대조 결과

검토일: 2026-10-30. 현재 워킹트리(기존 미커밋 변경 포함)를 기준으로 한다.
원본 보고서는 사용자 첨부 `Pasted text.txt`다. 이 검토에서는 백엔드 코드를 수정하지 않았다.

## 결론

실제 결함을 포함한 유용한 제보지만, 22개 항목을 모두 확정 결함이나 제시된 위험도로
수용할 수는 없다. 현재 검증 코드를 누락한 지적, 명시된 설계 계약을 결함으로 본 지적,
서로 다른 문제를 하나로 묶은 항목과 영향 범위의 과장이 섞여 있다.
특히 F08/F09는 먼저 대응할 근거가 충분하다. P0 여부는 실제 모델 전환 현황과
비공개 버전의 민감도·노출 범위를 확인하여 결정해야 한다.

## 항목별 판단

| ID | 판단 | 현재 코드 기준 근거와 보정 |
| --- | --- | --- |
| F08 | 핵심 원인 확인 | `llm/service/command/replacement.py`는 대체 실행의 `effective_at`을 현재 시각으로 다시 계산한다. 기존 대체 이력이 있어도 같다. `chat/service/workflow/answers.py:238`은 runtime 전체를 해싱하고 419행에서 두 준비 결과를 비교한다. 서로 다른 시각을 주입한 두 조회에서 실행 모델은 같지만 scheduled_at이 달라졌다. 대체 실행 중 답변 준비 충돌을 만드는 경로다. 실제 HTTP/DB 통합 재현까지 한 것은 아니다. 일반 모델·미도래 전환 전체가 실패한다는 뜻은 아니다. |
| F09 | 접근 통제 누락 확인 | `product/service/views/notices.py:get_pending_updates`는 대화 소유권만 확인하고 상품 공개/승인 상태를 재검사하지 않는다. `conversation/service/command/versions.py:switch_version`도 버전 소속·만료·순방향·릴리즈 동의만 검사한다. 비공개 신규 버전 노트 조회 및 전환을 막는 검사가 없다. 기존 버전 계속 사용 정책과 비공개 신규 버전 접근 정책은 구별해야 한다. 원문 프롬프트 전체의 직접 다운로드나 테넌트 전체 유출까지 입증된 것은 아니다. |
| F10 | 비용 손실 경로 확인, 표현 보정 필요 | 생성 중 버전 전환은 허용되고 이전 버전 결과는 stale 처리되어 크레딧이 해제된다. 다만 stale 답변은 메시지로 저장되지 않으므로 사용자가 무료로 정상 답변을 받는다는 주장은 틀리다. 외부 호출 비용 손실은 가능하다. `conversation/ARCHITECTURE.md`는 이 처리를 명시한다. 진행 중 전환을 막을지는 계약 변경이며, conversation에서 chat 내부 저장소를 역참조하는 수정은 아키텍처와 충돌한다. |
| F11 | 초기화 공백 확인 | 신규 이메일/Google 가입 경로에는 지갑 생성이 없다. 지갑 생성은 credit의 prepare/grant 경로에 있고, 잔액 조회와 0원 예약도 지갑이 없으면 실패한다. 신규 계정에 지갑을 제공하는 별도 운영 경로가 없다면 실제 온보딩 문제다. |
| F12 | 가입 선점 경로 확인, 영구 차단은 과장 | Google 최초 연결은 같은 이메일 행이 미인증·만료 대기 계정이어도 account_conflict로 거절한다. 다만 가입 대기는 7일이며 만료 정리 기능과 이메일 소유자의 인증/복구 경로가 있으므로 영구 차단으로 단정할 수 없다. 검증된 기존 계정까지 자동 병합하라는 수정으로 확장하면 안 된다. |
| F13 | 결과 처리 불일치 확인, 영구 중단은 과장 | 답변 검증은 incomplete/max_output_tokens와 completed/max_tokens 모두 거절한다. 요약은 status만 검사하여 Anthropic refusal/max_tokens를 통과시킬 수 있다. 출력 상한 도달 시 답변을 거절할지는 제품 정책이지만 공급자 간 요약 검증 불일치는 타당한 지적이다. 실패한 MemoryJob은 새 schedule 요청에서 pending으로 돌아가므로 대화방 기억이 영구 정지한다고 단정할 수 없다. |
| F14 | 일부 사실, 대표 재현 결과 오류 | 새 영수증에는 expected_revision별 요청 fingerprint가 있다. 같은 revision에서 model_id를 바꾼 재요청을 직접 실행하니 이전 결과를 조용히 반환하지 않고 StudioDraftConflictError가 발생했다. 본문이 같으면 새 revision도 생기지 않아 모델만 변경하는 발행 흐름은 여전히 제약된다. legacy 영수증 및 content_digest만 확인하는 조기 반환도 남아 있다. 모델만 변경할 수 없다는 문제와 모든 요청이 무시된다는 설명을 구별해야 한다. |
| F15 | 스튜디오와 미디어 계약 충돌 확인 | 스튜디오 purpose에는 usage가 들어가며 `character/service/media.py:332`는 최초 binding과 다른 metadata를 거절한다. 삭제 후 동일 미디어 재부착도 347행에서 거절한다. 이는 미디어 모듈의 명시적인 불변 연결 정책이다. 스튜디오 편집 흐름에 대한 보완은 타당하지만 전역 binding을 초기화하는 권고를 바로 적용하기보다 기존 스냅샷/미디어 수명 계약을 먼저 보존해야 한다. 새 업로드로 해결 가능하므로 작품이 영구 복구 불능인 것은 아니다. |
| F16 | 직접 재현 | `validate_regex('foo)(bar')`는 통과했다. 같은 패턴을 case_sensitive=True로 매칭하면 InvalidLorebookRegex가 발생했다. False에서도 foobar는 매칭되지만 FOOBAR는 실패하여 래퍼 탈출도 확인했다. 단독 패턴 검증이 필요하다. |
| F17 | 상당 부분 오래된 지적, 길이 문제는 존재 | `product/service/studio_validation.py`가 ID 누락, 비문자열/중복 ID, usage=null, activation=[] 등을 ValueError로 거절한다. save/publish/prepare 경로에 연결되어 있다. 또한 KeyError는 LookupError의 하위 클래스이므로 공통 errors 경계에서는 500이 아니라 404다. 반면 자동 로어북 제목과 worldRules→description 중복 저장의 길이 충돌, 캐릭터 service의 최대 길이 검사 부재는 남아 있다. 실제 현재 로어북 description 상한은 보고서의 5,000자가 아닌 4,000자이고 entry content 상한은 32,000자다. 194자 작품 제목+접미사(201자), worldRules 4,001자 실패를 검증했다. |
| F18 | 주된 결함 규정은 설계 오해, 일부 후속 검토 필요 | `moderation/ARCHITECTURE.md`는 복수 초기 평가, 다대다 신고 근거, 일반 조치는 violation만/해제는 다른 outcome도 허용하는 계약을 명시한다. 현재 함수는 관리자 전용 pending 요청을 저장하며 제재를 실제 해제하는 실행자가 아니다. 따라서 보고서대로 일반 권한 우회나 실제 제재 취소 성공으로 볼 수 없다. rejected 부모를 가리키는 기존 duplicate 자식 처리와 작품 평가→사용자 조치의 잠금 범위는 별도 불변식/후속 실행자 설계 문제로 검토할 가치가 있다. |
| F19 | 잠금 경로 확인, 전역 병목 단정은 과장 | 공지가 유효해졌거나 원본이 사용 불가이면 조회가 lock=False/True 두 단계를 돈다. 이미 대체 이력이 있는 경우에도 같은 snapshot 잠금을 재획득한다. 범위는 DB 전체나 동일 모델 전체의 단일 행이 아니라 각 상품 버전 행이다. 외부 LLM 호출 동안 잠금을 유지하는 경로도 아니다. 인기 버전의 직렬화 위험은 있으나 심각도/타임아웃은 부하 검증이 필요하다. |
| F20 | 핵심 경로 확인 | 최근 메시지로 만든 검색 질의에는 별도 길이 상한이 없고 query embedding은 truncation=False 기본값을 사용한다. 준비 중 업무 오류는 LLM 호출 전이어도 실패 generation을 만들 수 있어 동일 request_key가 이전 실패를 재사용한다. 단, 같은 키 소진은 모든 후속 요청의 영구 차단과 다르며 새 키는 별도 요청이다. 특정 공급자/모델의 실제 입력 한계 초과 응답은 호출하지 않았다. |
| F21 | 현상 확인, 비활성 의미 확인 필요 | catalog-tags 조회와 tag_id 검색에 is_active 필터가 없다. 다만 tag 계약은 기존 연결 보존/신규 연결 차단을 명시하고 있어 비활성화를 기존 분류의 공개 은닉과 같은 뜻으로 단정할 수 없다. 운영 요구가 은닉이라면 실제 결함이며 현재 보고서의 일괄 P1 평가는 근거가 부족하다. |
| F22 | 직접 재현 | activation_options 없는 contains 항목에 메시지 dragon과 trigger dragon을 전달했지만 선택 0건, keyword_mismatch가 반환됐다. `diagnose_entries`가 options 없는 경우 messages 대신 기본 빈 text를 사용한다. 초안 진단 결함이며 text를 별도로 전달하는 모든 런타임까지 같은 결과라는 뜻은 아니다. 추가 KeyError=500 주장은 F17과 같은 이유로 틀리다. |
| F23 | 현재 계약상 결함으로 단정 불가 | 동일 content_digest를 revision 검사보다 먼저 반환하는 것은 사실이다. 그러나 product 아키텍처는 동일 문서 재전송을 같은 결과로 처리하고 동일 문서 우선 재전송 순서를 유지한다고 명시한다. 기존 copy mapping을 저장하는 사전 부수효과가 있다는 점만으로 사용자 콘텐츠 덮어쓰기나 데이터 손상이 입증되지는 않는다. 엄격 CAS를 원한다면 계약 변경으로 다뤄야 한다. |
| F24 | 현상은 사실, lease 정책의 선택 | `_update_locked_answer`는 execution_token 일치 외에도 lease 유효성을 요구하므로 만료 직후 원 워커의 저장도 거절한다. 결과 폐기 가능성은 있다. 그러나 현재 lease 계약에 부합하는 동작이고, 만료된 실행을 계속 신뢰할지에 대한 변경이다. DB 지연만으로 실제 재현하지 않았으며 late result 허용은 복구 워커와 함께 검증해야 한다. |
| F25 | 스케줄링 문제 확인, 나머지는 운영 조건 | 일부 슬롯만 찬 경우에도 claimed=True이면 FIRST_COMPLETED를 timeout 없이 기다려 후속 작업 폴링이 늦어진다. 취소는 Exception 가드에 걸리지 않아 lease 만료 복구에 의존한다. 워커가 Voyage 어댑터를 항상 구성하는 것도 사실이지만 요약 provider=mock이 임베딩까지 mock이라는 뜻은 아니다. API 키 없는 기동 실패는 필수 운영 설정과 의도된 fail-fast인지도 확인해야 한다. |
| F26 | 일부 사실, 경계 오류/캐시 레이스는 입증 부족 | get_verified_user_id가 인증보다 CSRF를 먼저 검증하므로 무쿠키 쓰기에 403을 낼 수 있다. 401 우선이 필요한지는 HTTP 계약 문제다. exp/iat 초 절삭 자체는 존재하지만 기존 refresh token의 exp도 PyJWT가 먼저 검증하므로 단순히 만료 1초 미만이라는 이유만으로 보고서의 발급 시나리오가 성립하지는 않는다. 검증 후 DB 지연으로 경계를 넘는 경우는 별도 재현 대상이다. JWK 클라이언트 공유만으로 실제 실패/잘못된 인증이 입증되지는 않았다. |
| F27 | 핵심 멱등성/추적 상실 주장은 반박됨 | reference_id=uuid4()는 사실이나 quote/reservation 연결은 billing_credit_bindings가 PK/UNIQUE/복합 FK와 함께 담당한다. 재전송은 binding 확인 후 기존 예약을 반환한다. 따라서 추적 불가/멱등성 무력화는 코드 흐름을 빠뜨린 주장이다. 결제 조회의 populate_existing 누락은 실제 위험 검토 대상이다. refund는 원 sale 행 잠금·종류·시각·누적 금액을 검증하므로 부모 Payment 미조회만으로 잘못된 환불을 입증할 수 없다. |
| F28 | 서로 다른 사안을 혼합, 통계 주장은 정상 경로 근거 부족 | freeze의 ID 정렬과 옵션 없는 항목의 저장 순서 유지는 사실이며 legacy 계약과 관련된다. detail의 description 직접 인덱싱은 선택 필드 계약과 불일치하지만 현재 발행 builder는 해당 키를 항상 쓴다. KeyError의 공통 HTTP 변환은 404다. 통계 사용자는 SELECT DISTINCT, usage/방/전환은 snapshot별 GROUP BY 결과를 받으므로 정상 경로에서는 보고서가 가정한 중복 팩트가 나오지 않는다. 임의 중복 입력을 만든 것만으로 통계 배치 결함이 입증되지는 않는다. 삭제 경합은 실제 DB 재현이 필요하다. |
| F29 | 커서 주장은 현재 코드에서 틀림, Mock 제한은 사실 | chat/service/views.py:20이 utcoffset() 없는 커서를 거절하며 직접 호출에서도 DB 접근 전 ValueError를 확인했다. 형식이 잘못된 문자열도 fromisoformat ValueError→422다. Mock의 provider_reasoning_efforts는 빈 집합이라 명시된 low뿐 아니라 문자열 none도 거절한다. reasoning_effort=None은 통과한다. 보고서의 none 제외 설명도 정확하지 않다. Mock이 실제 provider 지원 제약을 흉내 내는지, 모든 effort를 수용해야 하는지는 테스트 계약을 정해야 한다. |

## 검증

프로젝트 `.venv/Scripts/python.exe`를 사용했다.

```powershell
$env:PYTHONPATH = 'apps/api'
.venv/Scripts/python.exe -m pytest apps/api/tests/test_model_replacement_contracts.py apps/api/tests/test_studio_republication_contracts.py apps/api/tests/test_studio_validation_contracts.py apps/api/tests/test_lorebook_activation_contracts.py apps/api/tests/test_billing_credit_scope.py apps/api/tests/test_conversation_http.py apps/api/tests/test_identity_google_contracts.py apps/api/tests/test_read_composition_contracts.py -q -p no:cacheprovider
```

결과: **210 passed, 16 skipped**. PostgreSQL 연결이 필요한 billing_credit_scope 16건은
TEST_DATABASE_URL 부재로 skip했다. 테스트 통과가 이 보고서의 모든 지적을 반증한다는 뜻은 아니다.

추가 일회성 검증:

- F08: 기존 대체 이력을 둔 대역으로 서로 다른 now를 전달. 신규 INSERT 없이 scheduled_at과 직렬화된 실행 값이 바뀜을 확인.
- F19: 위 두 조회 각각 snapshot 조회의 lock 인자가 False→True인 것을 확인.
- F16: 비대칭 괄호 패턴 저장 통과, case-sensitive 매칭 예외, ignore-case 래퍼 탈출을 확인.
- F22: 일반 keyword 초안의 실제 매칭 실패를 확인.
- F14: 정상 발행 영수증을 만든 뒤 같은 revision의 model_id만 바꾸면 StudioDraftConflictError임을 확인.
- F17: 잘못된 nested JSON을 ValueError로 차단, KeyError의 공통 변환이 404임을 확인. 현재 길이 제약 충돌을 확인.
- F13: 두 공급자 형태의 토큰 상한 종료 값을 답변 검증기가 거절함을 확인.
- F29: naive 커서의 DB 이전 거절과 Mock의 None/none/low 처리 차이를 확인.

비동기 실행은 샌드박스에서 이벤트 루프 생성이 정지해 동일 가상환경을 샌드박스 밖에서
실행했다. 실제 PostgreSQL 동시성, HTTP 전체 흐름의 공격 재현, 외부 LLM/임베딩 API 호출,
부하 측정은 수행하지 않았다. 백엔드 패턴 변경이 없어 품질 검사 스크립트는 실행하지 않았다.

## 우선 대응 제안

1. F08: 실행 조건 지문에서 변동하는 시각 메타데이터를 분리하고 두 준비 조회를 포함한 답변 통합 회귀 검증을 추가한다. 대체 모델 자체를 영구 고정하는 식으로 기존 재선택 정책을 바꾸지 않는다.
2. F09: 기존 버전의 계속 사용 정책을 유지할지와 별개로 비공개/미승인 신규 버전의 열람·전환 권한을 명시하고 차단한다.
3. F11/F16/F22 및 F17의 길이 충돌: 신규 계정·정상 입력을 막는 검증/초기화 불일치를 우선 정리한다.
4. F13/F15/F20/F25: 요약 종료 상태, 편집 가능한 미디어 metadata, 긴 검색 질의, 워커 폴링을 각각 독립된 문제로 수정한다.
5. F10/F18/F21/F23/F24/F26/F27/F28/F29의 혼합·정책성 주장은 현재 계약과 실제 재현을 붙여 재작성한다. 보고서 권고를 일괄 적용하지 않는다.
