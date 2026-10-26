# 모서리 프런트 프로토타입

홈 → 작품 상세 → 시작 설정 → 채팅을 볼 수 있는 Next.js 프런트다. 샘플 작품은 화면 시연용이며 서버·AI·크레딧을 사용하지 않는다. 실제 작품 UUID가 설정되면 같은 상세·채팅 화면에서 API를 호출한다.

## 화면 시연

저장소 루트에서 Node.js 22와 pnpm 11을 준비한 뒤:

```powershell
pnpm install
pnpm web:dev
```

브라우저에서 <http://localhost:3000>을 연다. 표지·작품명·시연 대화는 자체 제작 샘플이다. 시연 메시지는 현재 브라우저의 로컬 저장소에 남는다.

데스크톱은 좁은 왼쪽 레일의 버튼으로 최근 대화 사이드바를 펼친다. 모바일은 하단 메뉴의 **내 대화**에서 같은 목록을 본다. 로그인한 계정의 목록은 서버에서 가져오고, 시연 대화는 현재 브라우저에 보관한다. 서버 목록의 표지는 현재 기본 표지를 사용한다.

## 제작 스튜디오 시연

`/studio`에서 제작 스튜디오를 연다. 서비스 상단 메뉴와 모바일 메뉴에도 진입 링크가 있다. 사용자 제공 Figma PNG와 저장된 생성 코드를 기준으로 구성한 화면이며, 작품 개요·캐릭터·시작 장면·기본/고급 로어 편집과 폴더·태그 검색을 제공한다. 화이트·다크 테마를 지원하고 모바일에서는 자료/편집/미리보기를 하단 메뉴로 전환한다.

전체 작업실은 `chat-kit-studio-workspace-v3` 키로 현재 브라우저에 자동 저장된다. 기존 v1·v2 초안은 원본을 보존하며 이전한다. 로그인한 사용자는 작품별 **서버에 저장**과 **서버 초안 가져오기**를 사용할 수 있다. 발행은 저장된 문서에서 캐릭터·로어·시작 장면·모델을 조합해 첫 릴리스를 만든다. 같은 문서의 발행 재시도는 기존 결과를 반환한다. 후속 버전 발행과 캐릭터 이미지 업로드는 아직 지원하지 않으며, 이미지가 포함된 작품은 발행 전에 막는다. 이미지 파일은 IndexedDB에 별도로 저장하므로 JSON과 함께 원본 파일도 보관해야 한다. **테스트**는 로컬 미리보기이며 AI를 호출하지 않는다.

로어 미리보기와 초안 복원의 검증:

```powershell
node --test apps/web/tests/studio-preview.test.cjs apps/web/tests/studio-project.test.cjs
```

구현 범위와 검증 결과는 [제작 스튜디오 구현 기록](../../docs/creator-studio-implementation.md)에 정리했다.

## 실제 API 연결 방법

API가 `http://127.0.0.1:8000`에서 실행 중인 경우 Next.js는 `/backend/*`를 API에 전달한다. 다른 주소라면 `apps/web/.env.example`을 `apps/web/.env.local`로 복사해 `CHAT_KIT_API_URL`을 바꾼다. 다음 항목도 준비한다.

1. API의 `DATABASE_URL`, 인증 키·메일 설정, 최신 Alembic 마이그레이션을 준비한다.
2. API 환경에 `CORS_ORIGINS=http://localhost:3000`, `AUTH_PUBLIC_ORIGIN=http://localhost:3000`을 설정한다. 로컬 HTTP에서는 `AUTH_SECURE_COOKIES=false`가 필요하다. 이메일 인증·비밀번호 재설정 메일 링크가 프런트 페이지로 돌아오게 해야 한다.
3. 발행된 작품, 사용 가능한 모델, 가격표(`BILLING_PRICING_CONFIG_PATH`), 사용자 크레딧을 준비한다. 그렇지 않으면 답변 요청이 설정/잔액 오류로 종료될 수 있다.
4. 공개 작품은 홈의 **연결된 작품**과 `/explore`에 자동 표시된다. 필요하면 발행 작품 UUID를 `NEXT_PUBLIC_FEATURED_PRODUCT_IDS`에 쉼표로 넣어 홈의 우선 노출 항목을 지정한다.
5. `/register`에서 가입하고 메일 링크로 인증한 뒤 `/login`에서 로그인한다. `/forgot-password`, `/reset-password`로 비밀번호를 재설정할 수 있다.

로그인 쿠키는 브라우저의 HttpOnly 쿠키를 사용하며 프런트는 Access/Refresh 토큰을 저장하지 않는다. Access 만료 시 `/auth/refresh`로 한 번 복구한다. Web Locks로 탭 사이 갱신을 직렬화하며, 갱신 응답이 유실되면 재로그인이 필요하다. Web Locks가 없는 환경도 재로그인으로 복구한다. CSRF 토큰은 `/auth/csrf` 응답으로 받아 상태 변경 요청 헤더에 넣고 CSRF 실패 시 한 번 재발급한다.

공개 작품 카탈로그는 승인된 전체 공개 발행본만, 내 대화 목록은 로그인 사용자가 소유한 대화만 서버에서 조회한다. 실제 채팅은 `GET /conversations/{id}/start`, 메시지 저장/조회, 비스트리밍 답변 API를 사용한다. 잔액과 생성 후 예약 가격을 표시하며 부족 오류를 구분한다. 대기 중단은 브라우저의 기다림만 끝내고 서버 작업은 지속될 수 있다. 결과가 불확실하면 같은 요청 키로 다시 확인하도록 세션 저장소에 정보를 보관한다.

실제 대화의 최근 목록과 작성 중 메시지는 로그인 사용자별 키로 저장한다. 로그인 확인 전에는 시연 대화만 표시한다. 이전 공용 키의 실제 대화는 소유자를 알 수 없어 자동 이관하지 않으며 원본 저장 값은 남긴다. 메시지는 오름차순 커서를 끝까지 조회하므로 100개 이후의 답변도 표시한다. 이 방식은 긴 이력 전체를 읽으므로 대용량 대화의 최신 페이지 전용 조회·가상화는 후속 개선 대상이다.

## 확인

계정·크레딧 v10 화면은 `/account`에서, 개발 전용 상태 시연은 `/dev/design-v10`에서 확인한다. 작품별 진입은 `/studio?work={browserWorkId}` 또는 `/studio?product={serverProductId}`를 사용한다. 실제 연결 범위, 결제/프로필 미연동 항목, 검증 결과는 [v10 구현 기록](../../docs/design-account-credit-v10-implementation.md)에 정리했다.

```powershell
pnpm web:typecheck
pnpm web:build
node --test apps/web/tests/*.test.cjs
```

프런트 구현 범위와 이후 API 보강은 [프런트 프로토타입 계획](../../docs/frontend-prototype-plan.md)에 정리했다.
