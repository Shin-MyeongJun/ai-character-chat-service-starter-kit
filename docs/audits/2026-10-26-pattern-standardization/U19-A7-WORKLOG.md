# U19 a7 · 답변 이미지 선택·저장·복구

2026-11-11. `75a9a25`에서 `tmp/worktrees/u19-a7`, `codex/u19-a7`을 생성했다.
a6 담당과 공통 블록 타입/응답 변환은 a6, 메시지 revision 인가/메시지 파일 endpoint는
a7로 합의했다. a6 원본 `64e519e3cb944cddea2c27afd559449ad3948726`을 선행 의존성
`7bcd79e`로 cherry-pick했다. a7 변경은 그 다음 단일 커밋이다.

## 구현

- 생성에 고정된 발행본의 답변 캐릭터와 활성 로어 `(snapshot_id, entry_id)`로 후보를
  구성한다. 최대 24개를 발행 순서로 제공하고 입력 예산이 부족하면 뒤에서 제거한다.
  모델에는 요청별 후보 키·종류·태그·설명만 전달하며 실행 fencing token/파일 UUID는 보내지 않는다.
- 기존 nonstream 답변에서 본문과 선택 제안을 같은 응답의 JSON envelope로 받는다.
  서버가 키와 문단 위치를 검증하고 본문 순서로 최대 3개를 삽입한다. 잘못된 제안은
  생략하고 같은 위치의 제안 순서 및 같은 이미지의 반복을 보존한다. 텍스트 연결은 원문과 같다.
- `result_ready.content_blocks`가 내구 저장 경계다. 복구는 이 결과를 그대로 읽는다.
  메시지·해금·usage·크레딧 정산·기억 예약은 기존 최상위 트랜잭션에서 원자적으로 확정한다.
  실패·취소·stale에는 해금이 없으며 terminal 재생은 쓰기나 공급자 재호출을 하지 않는다.
- 메시지의 실제 revision/블록 위치와 방 소유권으로 파일을 인가한다. 삭제/교정된 위치는
  404이고, 앨범 해금이나 버전 실행 만료는 생존 본문의 열람 조건이 아니다.
- `messages.content_blocks` nullable JSONB를 Alembic 0039/초기 SQL 029로 추가한다.
  구형 데이터는 NULL이다. 텍스트 교정은 블록을 지우고 해금은 유지한다. 기존 블록 없는
  `GenerationResult`의 digest 계산은 이전과 동일하다.

## 검증

프로젝트 루트의 `.venv/Scripts/python.exe`를 사용했다. 품질 검사에 예외를 추가하지 않았다.

- `tools/check_backend_quality.py`: 성공. signature 0 findings, Ruff format/lint,
  mypy 385 source files, 아키텍처/패턴 테스트 13건 통과.
- 관련 회귀 218건 통과: `test_answer_images`, `test_nonstream_answers`,
  `test_answer_billing_integration`, `test_chat_message_contracts`,
  `test_generation_completion_contracts`, `test_answer_http`,
  `test_generation_prompt_workflow`, `test_conversation_start_images`,
  `test_product_album`, `test_conversation_runtime`, `test_conversation_query_contracts`,
  `test_answer_recovery_policy`, `test_answer_recovery_policy_db`,
  `test_answer_error_diagnostics`, `test_product_usage`.
- 마지막 후보 namespace/공개 타입 정리 후 `test_answer_images` 21건 재실행 통과.
  로컬 저장소와 fake S3에서 동일하게 검증했다. 실제 PostgreSQL의 테스트별 UUID 스키마를
  사용했고, LLM 응답은 결정적 대역이다. 실제 외부 모델의 배치 선택 품질은 검증 대상이 아니다.
- 메시지·해금 쓰기 뒤 결제 실패의 전체 롤백, result_ready 복구, 동시 동일 키 재전송,
  result_ready 및 성공 commit ACK 유실, 1회 청구와 최초 해금 시각 유지,
  실패/취소/stale 미해금, 잘못된 후보/위치, 문단 구분자 보존, 예산 후순위 제거,
  소유자/revision/텍스트 위치/삭제 위치 거절, 만료 후 파일 읽기, 교정 후 해금 유지 검증.
- Alembic와 초기 SQL 경로에서 구형 메시지 보존 및 데이터 존재 시 downgrade 거절 검증.
  출력의 Alembic `path_separator` 경고는 기존 설정의 deprecation 안내다.
- Windows 샌드박스의 asyncio 루프 생성 정지 때문에 DB/async 테스트는 권한 확장으로 실행했다.
  DB 스키마와 파일 작업 범위는 테스트용으로 격리했다.

## 다음 작업에 넘길 계약

1. 통합에는 a6 `64e519e`와 이 a7 커밋이 필요하다. a6가 이미 있으면 a7 변경만 적용한다.
   원본 `75a9a25` 위에 이 브랜치 전체를 통합하면 a6 재적용은 필요 없다.
2. 배포 전 Alembic `0039`를 적용한다. 새 초기화는 `029_message_content_blocks.sql`을 사용한다.
3. UI는 GET messages의 `content_blocks`를 배열 순서대로 렌더링한다. null/누락이면
   기존 `content`로 폴백한다. 이미지는 `content_url`의 인증 스트림을 사용하며 파일 읽기
   실패 시 해당 `alt`를 표시한다. 답변 POST의 기존 응답 계약은 유지한다.
4. a8의 이력 복사/리롤/분기는 당시 블록의 항목 ID·파일 버전·순서를 그대로 복사한다.
   현재 파일이나 후보로 재선정하지 않는다. 현재 API는 생존하는 현재 revision만 인가한다.
5. a4의 snapshot 파일 pin과 메시지/생성 snapshot FK를 재사용한다. 향후 스냅샷 물리 삭제나
   참조 해제 작업은 result_ready/생존 본문이 참조하는 파일을 먼저 보존해야 한다.

## 응답 예시

GET `/conversations/{conversation_id}/messages`의 `items` 안 메시지 일부:

```json
{
  "id": "80000000-0000-4000-8000-000000000001",
  "conversation_id": "90000000-0000-4000-8000-000000000001",
  "revision": 1,
  "product_snapshot_id": "40000000-0000-4000-8000-000000000011",
  "content": "수리공이 웃었다.\n\n문이 열렸다.",
  "content_blocks": [
    {"type": "text", "text": "수리공이 웃었다.\n\n"},
    {
      "type": "image",
      "image_item_id": "20000000-0000-4000-8000-000000000001",
      "file_version_id": "30000000-0000-4000-8000-000000000001",
      "alt": "수리공의 미소",
      "content_url": "/conversations/90000000-0000-4000-8000-000000000001/messages/80000000-0000-4000-8000-000000000001/revisions/1/blocks/1/content"
    },
    {"type": "text", "text": "문이 열렸다."}
  ]
}
```
