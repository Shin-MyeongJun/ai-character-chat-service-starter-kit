"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useUserTheme } from "@/components/user-theme";
import { logout } from "@/lib/api";
import { filterOrders, formatCredit as n, formatDate, orderLabels, recheckPreviewOrder, type AccountPreview, type Order } from "@/lib/account";
import { migrateWorkspace, WORKSPACE_STORAGE_KEY, type WorkspaceWork } from "@/lib/studio-workspace";
import { PROJECT_STORAGE_KEY } from "@/lib/studio-project";
import { STUDIO_STORAGE_KEY } from "@/lib/studio-data";
import { ActionLink, Button, Card, ChoiceGroup, Dialog, Empty, Field, Section, StatusRow } from "./account-ui";
import { ChatSettings, CreditShortageDialog } from "./chat-settings";
import { useAccount } from "./use-account";
import { useCreditHistory } from "./use-credit-history";
import { WorkTile } from "@/components/studio/work-tile";
import styles from "./account.module.css";
import { useOwnedProducts } from "./use-owned-products";

/** Present server publication, search, activity and ledger contracts with explicit partial failures. */
export function AccountApp({ section, preview }: { section: string[]; preview?: AccountPreview }) {
  const account = useAccount(preview);
  const router = useRouter();
  const { theme, preference, toggleTheme, setTheme } = useUserTheme();
  const [filter, setFilter] = useState("전체");
  const [period, setPeriod] = useState("전체 기간");
  const [settingsTab, setSettingsTab] = useState("1 계정 정보");
  const [query, setQuery] = useState("");
  const [localWorks, setLocalWorks] = useState<WorkspaceWork[]>([]);
  const [localError, setLocalError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<"withdraw" | "settings" | "credit" | null>(null);
  const [previewOrders, setPreviewOrders] = useState(preview?.orders ?? []);
  const [previewMessages, setPreviewMessages] = useState(["오래된 지도를 찾고 싶어요.", "에린은 서가를 살피고 작은 열쇠를 꺼냈다.\n\n“지도라면 동쪽 서가에 있어요. 어떤 장소를 찾고 있나요?”"]);
  const [draft, setDraft] = useState("");
  const current = section[0] ?? "home";
  const base = preview ? "/dev/design-v10" : "/account";
  const href = (path = "") => `${base}${path ? `/${path}` : ""}`;
  const retry = () => preview ? router.push(href(section.join("/"))) : account.retry();
  const balance = account.balance.status === "ready" ? account.balance.data : null;
  const conversations = account.conversations.data.items;
  const creditText = balance ? n(balance.available_credit) : "—";
  const days = period === "7일" ? 7 : period === "30일" ? 30 : 0;
  const historyStart = useMemo(() => days ? new Date(Date.now() - days * 86400000).toISOString() : undefined, [days]);
  const history = useCreditHistory(account.user?.id ?? null, current === "wallet" && !preview, historyStart, filter === "사용" ? "usage" : filter === "획득" ? "acquisition" : undefined);
  const ownerWorks = useOwnedProducts(account.user?.id ?? null, current === "works" && !preview, query);
  const order = previewOrders.find(item => item.id === section[1]);
  const purchaseOrders = preview?.state === "empty" ? [] : previewOrders;
  const purchaseSummary = preview?.state === "loading" ? "구매 내역을 불러오는 중…" : preview?.state === "error" ? "구매 내역을 불러오지 못했어요." : `전체 ${purchaseOrders.length}건 · 완료 ${purchaseOrders.filter(o => o.status === "succeeded").length}건 / 확인 중 ${purchaseOrders.filter(o => ["pending", "uncertain"].includes(o.status)).length}건 / 실패 ${purchaseOrders.filter(o => o.status === "failed").length}건`;
  useEffect(() => { setFilter("전체"); setPeriod("전체 기간"); setNotice(""); setModal(preview?.state === "credit" && current === "chat" ? "credit" : null); }, [current, preview?.state]);
  useEffect(() => {
    if (current !== "works" || preview) return;
    try {
      const workspace = migrateWorkspace(localStorage.getItem(WORKSPACE_STORAGE_KEY), localStorage.getItem(PROJECT_STORAGE_KEY), localStorage.getItem(STUDIO_STORAGE_KEY));
      if (!workspace) setLocalError("이 브라우저의 작업실을 읽지 못했어요. 스튜디오에서 저장 데이터를 확인해 주세요.");
      else setLocalWorks(workspace.works);
    } catch { setLocalError("브라우저 저장소를 사용할 수 없어요."); }
  }, [current, preview]);
  async function signOut() {
    if (busy || preview) return;
    setBusy(true); setNotice("");
    try { await logout(); router.replace("/login"); account.retry(); }
    catch { setNotice("로그아웃하지 못했어요. 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }
  function recheck(item: Order) {
    // This is a development fixture transition, with no payment request or balance mutation.
    setPreviewOrders(rows => rows.map(row => row.id === item.id ? recheckPreviewOrder(row) : row));
    router.push(href(`purchases/${encodeURIComponent(item.id)}/recheck`));
  }
  const back = current === "home" ? <ActionLink href={href("settings")}>계정 설정 ⚙</ActionLink> : <ActionLink href={href(current === "purchases" && section.length > 1 ? "purchases" : "")}>‹ {current === "purchases" && section.length > 1 ? "구매 내역" : "마이페이지"}</ActionLink>;
  const balanceRow = <StatusRow>{balance ? `${n(balance.balance_credit)} 크레딧 · 가용 ${n(balance.available_credit)} / 예약 ${n(balance.reserved_credit)}` : account.balance.status === "error" ? <><span>잔액을 불러오지 못했어요.</span> <Button onClick={retry}>다시 조회</Button></> : "크레딧 잔액을 불러오는 중…"}</StatusRow>;
  const periodChoices = <Section title="조회 기간"><ChoiceGroup label="조회 기간" values={["전체 기간", "7일", "30일"]} value={period} onChange={setPeriod} /></Section>;
  const walletActions = <><div className={styles.actions}><ActionLink primary href={href("purchases")}>구매 내역</ActionLink><ActionLink href={href("topup")}>충전 상품 보기</ActionLink></div><ActionLink primary full href={href("topup")}>크레딧 충전하기 →</ActionLink></>;
  const conversationList = account.conversations.status === "loading" ? <StatusRow>대화를 불러오는 중…</StatusRow> : account.conversations.status === "error" ? <StatusRow error>대화를 불러오지 못했어요. <Button onClick={retry}>다시 조회</Button></StatusRow> : conversations.length ? <Card>{conversations.slice(0, 3).map(item => <Link className={styles.rowLink} key={item.id} href={preview ? href("chat") : `/chats/${encodeURIComponent(item.id)}?from=account`}><span><strong>{item.title || "제목 없는 대화"}</strong><p>{item.last_message || "첫 이야기를 기다리고 있어요."}</p></span><time dateTime={item.last_activity_at ?? item.created_at}>{formatDate(item.last_activity_at ?? item.created_at)} →</time></Link>)}</Card> : <Empty title="아직 시작한 대화가 없어요"><Link href="/explore">작품을 골라 첫 장면을 열어보세요 →</Link></Empty>;
  let content;
  if (current === "home") content = <>
    <h1><span className={styles.desktopOnly}>{preview ? "서리님의 이야기 공간" : "나의 이야기 공간"}</span><span className={styles.mobileOnly}>{preview ? "서리님의 마이페이지" : "나의 마이페이지"}</span></h1><p className={`${styles.description} ${styles.desktopOnly}`}>이어지는 대화와 직접 만든 세계, 모두 이곳에 있어요.</p><p className={`${styles.description} ${styles.mobileOnly}`}>{account.user?.email}{preview ? " · 이야기 수집가" : ""}</p>
    <div className={styles.desktopOnly}><Section title="프로필 · 계정 요약"><StatusRow>{preview ? "서리 · 이야기 수집가 · " : ""}{account.user?.email} · {account.user?.email_verified ? "✓ 이메일 인증 완료" : "이메일 인증 필요"}</StatusRow></Section></div>
    <div className={styles.mobileBalance}><Section title="총 보유 크레딧">{balanceRow}</Section></div>
    <Section title="이어지는 대화">{conversationList}<small>내 대화 {account.counts.status === "ready" ? account.counts.data?.conversations : "—"}개 · 서버 작품 {account.counts.status === "ready" ? account.counts.data?.products : "—"}개</small></Section>
    <div className={styles.actions}><ActionLink primary href={preview ? href("chat") : "/chats"}>내 대화 이어가기</ActionLink><ActionLink href={href("works")}>내 작품 관리</ActionLink></div><ActionLink primary full href={href("wallet")}>크레딧 지갑 · 충전하기 →</ActionLink>
  </>;
  else if (current === "wallet") {
    const source = preview ? preview.state === "empty" ? [] : preview.ledger : history.data.items.map(row => ({ id: row.id, date: row.created_at, kind: row.amount > 0 ? "획득" : row.amount < 0 ? "사용" : "조정", title: row.amount > 0 ? "크레딧 획득·환원" : row.amount < 0 ? "크레딧 사용·차감" : "잔액 변동 없음", credits: row.amount }));
    const ledger = preview ? source.filter(row => (filter === "전체" || row.kind === filter) && (!days || Date.now() - new Date(row.date).getTime() <= days * 86400000)) : source;
    const ledgerStatus = preview ? preview.state : history.status;
    content = <><h1>크레딧 지갑</h1><p className={styles.description}>이야기에 사용한 크레딧과 남은 잔액을 확인하세요.</p>
      <ChoiceGroup label="이용 내역 종류" values={["전체", "사용", "획득"]} value={filter} onChange={setFilter} />
      <Section title="총 보유 크레딧">{balanceRow}</Section>
      <Section title="최근 이용 내역" help={!preview ? "기간·사용·획득 조건을 서버 전체 내역에 적용합니다. 환원·조정은 잔액 변동 방향으로 분류해요." : undefined}>
        {ledgerStatus === "loading" ? <StatusRow>이용 내역을 불러오는 중…</StatusRow> : ledgerStatus === "error" ? <StatusRow error>이용 내역을 불러오지 못했어요. <Button onClick={preview ? retry : history.retry}>다시 조회</Button></StatusRow> : ledger.length ? <Card><div className={styles.ledger}>{ledger.map(row => <div className={styles.ledgerRow} key={row.id}><time dateTime={row.date}>{formatDate(row.date)}</time><span>{row.kind}</span><span>{row.title}</span><span>{row.credits > 0 ? "+" : ""}{n(row.credits)}</span></div>)}</div></Card> : <Empty title="표시할 이용 내역이 없어요" />}
        {!preview && history.error && history.status !== "error" && <StatusRow error>{history.error}</StatusRow>}
        {!preview && history.data.next_cursor_id && <Button disabled={history.moreBusy} onClick={() => void history.loadMore()}>{history.moreBusy ? "불러오는 중…" : "이전 이용 내역 더 보기"}</Button>}
      </Section>{periodChoices}{walletActions}</>;
  } else if (current === "settings") content = <>
    <h1>계정 설정</h1><p className={styles.description}>나를 소개하고, 편안하게 이야기를 즐길 환경을 설정하세요.</p>
    <ChoiceGroup label="계정 설정" values={["1 계정 정보", "2 보안", "3 화면"]} value={settingsTab} onChange={setSettingsTab} />
    {settingsTab === "1 계정 정보" && <div className={styles.form}><Field label="이메일"><input readOnly value={account.user?.email ?? ""} /></Field><Field label="닉네임" help="프로필 편집 기능을 준비하고 있어요."><input readOnly value={preview ? "서리" : ""} placeholder="아직 설정되지 않았어요" /></Field><Field label="프로필 소개"><textarea readOnly value={preview ? "느리게 읽고, 오래 기억하는 이야기를 좋아해요.\n오늘도 새로운 세계를 만나러 왔어요." : ""} placeholder="프로필 소개를 준비하고 있어요" /></Field><Button primary disabled>변경 사항 저장 · 준비 중</Button></div>}
    {(settingsTab === "1 계정 정보" || settingsTab === "3 화면") && <Section title="화면 테마"><ChoiceGroup label="화면 테마" values={["라이트", "다크", "시스템"]} value={preference === "dark" ? "다크" : preference === "system" ? "시스템" : "라이트"} onChange={value => setTheme(value === "다크" ? "dark" : value === "시스템" ? "system" : "light")} /></Section>}
    {(settingsTab === "1 계정 정보" || settingsTab === "2 보안") && <><Section title="계정 보안"><StatusRow>{account.user?.email_verified ? "✓ 이메일 인증 완료" : "이메일 인증이 필요해요"}</StatusRow></Section><div className={styles.actions}><ActionLink href="/forgot-password">비밀번호 재설정</ActionLink><Button disabled={busy || !!preview} onClick={() => void signOut()}>{busy ? "로그아웃 중…" : "로그아웃"}</Button></div><Button onClick={() => setModal("withdraw")}>계정 탈퇴 안내</Button></>}
  </>;
  else if (current === "works") {
    const products = preview ? (preview.state === "empty" ? [] : account.products.data).filter(item => `${item.title} ${item.description ?? ""}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())) : ownerWorks.items;
    const worksStatus = preview ? account.products.status : ownerWorks.status;
    content = <><h1>내 작품 관리</h1><p className={styles.description}>직접 만든 세계를 이어서 다듬고, 새로운 이야기를 시작하세요.</p><label><span className={styles.srOnly}>작품 검색</span><input className={styles.search} placeholder="작품 이름으로 검색" value={query} onChange={e => setQuery(e.target.value)} /></label>
      <Section title="서버에 저장한 작품">{!preview && account.session !== "ready" ? <Empty title="서버 작품은 계정 연결 후 확인할 수 있어요"><ActionLink href="/login?next=%2Faccount%2Fworks">로그인</ActionLink> <Button onClick={retry}>다시 확인</Button></Empty> : worksStatus === "loading" ? <StatusRow>작품을 불러오는 중…</StatusRow> : worksStatus === "error" ? <StatusRow error>서버 작품을 불러오지 못했어요. <Button onClick={preview ? retry : ownerWorks.retry}>다시 조회</Button></StatusRow> : products.length ? <div className={styles.workGrid}>{products.map((product, index) => <WorkTile key={product.id} index={index} title={product.title} description={product.description ?? ""} status={`${`${product.has_publication ? "발행본 있음" : "미발행"} · ${{approved: "승인", rejected: "반려", draft: "초안"}[product.status] ?? product.status}`} · ${formatDate(product.updated_at)}`}>{preview ? <ActionLink href="/studio">제작 스튜디오 열기</ActionLink> : <ActionLink href={`/studio?product=${encodeURIComponent(product.id)}`}>이 작품 편집하기 →</ActionLink>}</WorkTile>)}</div> : <Empty title={query ? "검색 결과가 없어요" : "서버에 저장한 작품이 없어요"} />}</Section>
      {!preview && <><small>{ownerWorks.total === null ? "개수 확인 중" : `검색 결과 전체 ${ownerWorks.total}개 · 현재 ${ownerWorks.items.length}개`}</small>{ownerWorks.error && <StatusRow error>{ownerWorks.error}</StatusRow>}{ownerWorks.total !== null && ownerWorks.items.length < ownerWorks.total && <Button disabled={ownerWorks.busy} onClick={() => void ownerWorks.more()}>작품 더 보기</Button>}</>}
      {!preview && <div id="browser-works"><Section title="이 브라우저의 작업실">{localError ? <StatusRow error>{localError}</StatusRow> : localWorks.length ? localWorks.filter(work => work.project.work.title.includes(query)).map(work => <Card key={work.id}><strong>{work.project.work.title}</strong><small>브라우저 초안 · 서버 작품과 별도로 보관돼요.</small><ActionLink href={`/studio?work=${encodeURIComponent(work.id)}`}>이 초안 편집하기 →</ActionLink></Card>) : <Empty title="이 브라우저에 저장된 초안이 없어요" />}</Section></div>}
      <ActionLink primary full href="/studio">제작 스튜디오 · 새 작품 만들기 →</ActionLink>
    </>;
  } else if (current === "topup") content = <><h1>크레딧 충전</h1><p className={styles.description}>더 많은 이야기를 만날 준비를 하고 있어요.</p><Section title="충전 서비스 안내"><StatusRow>크레딧 충전을 준비하고 있어요.</StatusRow><Card><p>결제 서비스와 판매 상품이 준비되면 이곳에서 충전할 수 있어요.</p><p>이미 사용 중인 크레딧과 대화는 지갑에서 확인하세요.</p></Card></Section><Button primary disabled>크레딧 구매 · 준비 중</Button><div className={styles.actions}><ActionLink href={href("wallet")}>내 지갑 보기</ActionLink><ActionLink href={href("purchases")}>구매 내역 보기</ActionLink></div>{preview && <ActionLink full href={href("checkout")}>상품 요약과 결제 · 개발 시연 →</ActionLink>}</>;
  else if (current === "checkout") content = <><h1>상품 요약과 결제</h1><p className={styles.description}>{preview ? "개발용 결제 흐름입니다. 실제 결제나 크레딧 지급은 발생하지 않습니다." : "판매 상품과 결제 서비스를 준비하고 있어요."}</p><div className={styles.choices}><span className={styles.badge}>1 상품 선택</span><span>2 결제</span><span>3 완료</span></div><Section title="선택한 충전 상품"><StatusRow>{preview ? "10,000 크레딧 · 10,000원 · 시연용 상품" : "구매 가능한 상품이 아직 없어요."}</StatusRow></Section><Section title="결제 전 확인"><Card><p>결제 승인과 충전이 모두 확인된 뒤 잔액에 반영돼요.</p><p>확인 중인 주문은 구매 내역에서 먼저 확인해 주세요.</p></Card></Section><Section title="결제 수단"><Button disabled>신용카드 · 준비 중</Button></Section><div className={styles.actions}><ActionLink href={href("purchases")}>구매 내역 보기</ActionLink><ActionLink href={href("topup")}>충전 상품 다시 보기</ActionLink></div>{preview ? <ActionLink primary full href={href("purchases/MC-20261019-001/result")}>결제 처리 화면 열기 · 시연 →</ActionLink> : <Button primary disabled>결제창 열기 · 준비 중</Button>}</>;
  else if (current === "purchases" && section.length === 1) {
    const orders = filterOrders(preview?.state === "empty" ? [] : previewOrders, filter, days);
    content = <><h1>구매 내역</h1><p className={styles.description}>충전 주문과 결제 결과를 확인하세요. 확인 중인 주문은 다시 결제하지 않아도 돼요.</p><ChoiceGroup label="주문 상태" values={["전체", "확인 중", "완료", "실패"]} value={filter} onChange={setFilter} /><Section title="구매 요약"><StatusRow>{preview ? purchaseSummary : "구매 내역 조회를 준비하고 있어요."}</StatusRow></Section><Section title="주문 목록">{preview ? preview.state === "loading" ? <StatusRow>구매 내역을 불러오는 중…</StatusRow> : preview.state === "error" ? <StatusRow error>구매 내역을 불러오지 못했어요.</StatusRow> : orders.length ? <div className={styles.list}>{orders.map(item => <Link className={styles.orderLink} key={item.id} href={href(`purchases/${item.id}${item.status === "pending" || item.status === "uncertain" ? "/result" : ""}`)}><p>{formatDate(item.createdAt)} · {item.id}</p><p>{n(item.amount)}원 · {n(item.credits)} 크레딧</p><p>{orderLabels[item.status]} · {item.status === "pending" ? "상태 재확인" : "상세 보기"} →</p></Link>)}</div> : <Empty title="조건에 맞는 구매 내역이 없어요" /> : <Empty title="구매 서비스가 아직 준비되지 않았어요">현재 크레딧 잔액은 지갑에서 확인할 수 있어요.</Empty>}</Section>{periodChoices}<div className={styles.actions}><ActionLink href={href("wallet")}>내 지갑 보기</ActionLink><ActionLink href={href("topup")}>충전 상품 보기</ActionLink></div>{preview && <ActionLink primary full href={href("checkout")}>상품 요약과 결제 · 시연 →</ActionLink>}</>;
  } else if (current === "purchases") {
    const result = section[2] === "result" || section[2] === "recheck";
    const status = section[2] === "recheck" && order?.status !== "succeeded" ? "uncertain" : order?.status;
    const success = status === "succeeded";
    const failed = status === "failed";
    content = !order ? <><h1>주문을 확인할 수 없어요</h1><StatusRow>{preview ? "해당 주문이 없어요. 구매 내역에서 주문을 다시 선택해 주세요." : "주문 상태 조회를 준비하고 있어요. 결제 결과는 이 화면에서 확정할 수 없습니다."}</StatusRow><ActionLink primary href={href("purchases")}>구매 내역 보기</ActionLink></> : <>
      <h1>{!result && success ? "구매 상세" : success ? "✓ 충전이 완료됐어요" : failed ? "! 결제를 완료하지 못했어요" : status === "uncertain" ? "◷ 아직 결과를 확인하고 있어요" : "◷ 결제 확인 중이에요"}</h1>
      <p className={styles.description}>{success ? `${n(order.credits)} 크레딧이 반영된 예시 화면이에요. 실제 지급은 발생하지 않습니다.` : failed ? "승인이 거절되어 크레딧이 지급되지 않은 예시예요. 먼저 처리 상태를 확인하세요." : "아직 결과가 확정되지 않았어요. 추가 결제 없이 구매 내역에서 확인해 주세요."}</p>
      <div className={styles.choices}><span className={styles.badge}>{orderLabels[status ?? "uncertain"]}</span><span>{success ? "충전 완료" : failed ? "미지급" : "충전 대기"}</span></div>
      <Section title="결제 요청 정보"><StatusRow>주문 {order.id} · {n(order.credits)} 크레딧 · {n(order.amount)}원 · {formatDate(order.createdAt)}</StatusRow></Section>
      <Section title={success ? "충전 상세" : failed ? "결제 실패 안내" : "확인 중에는 다시 결제하지 마세요"}><Card>{success ? <><p>충전 금액 {n(order.amount)}원 · 지급 크레딧 +{n(order.credits)} (시연)</p><p>결제 수단 신용카드 · 승인 일시 {formatDate(order.createdAt)}</p><p>취소·환불 가능 여부는 이용 내역과 판매 정책 확인 후 안내돼요.</p></> : <><p>{failed ? "실패 사유: 카드 승인 거절 · 크레딧 지급 없음 (시연)" : "결제 확인에 잠시 시간이 걸릴 수 있어요."}</p><p>추가 결제 없이 처리 상태를 다시 확인해 주세요.</p><p>잔액은 결제와 충전이 모두 확정된 뒤 반영됩니다.</p></>}</Card></Section>
      <div className={styles.actions}><ActionLink primary href={href("purchases")}>구매 내역 보기</ActionLink>{success ? <Button disabled>영수증 · 준비 중</Button> : <ActionLink href={href("wallet")}>내 지갑 보기</ActionLink>}</div>
      {success ? <ActionLink primary full href={preview ? href("chat") : "/chats"}>내 대화 이어가기 →</ActionLink> : <Button primary onClick={() => recheck(order)}>처리 상태 다시 확인</Button>}
    </>;
  } else if (current === "chat" && preview) content = <><h1>별빛 기록실</h1><p className={styles.description}>에린 · 달빛이 닿는 기록실에서</p>{previewMessages.map((message, i) => <Section key={i} title={i % 2 ? "에린" : "나"}><Card><p className={styles.chatMessage}>{message}</p></Card></Section>)}<small>개발용 대화 · 실제 AI 답변과 크레딧 사용이 발생하지 않습니다.</small><div className={styles.actions}><Button primary onClick={() => setModal("settings")}>대화 설정 ⚙</Button><ActionLink href={href("wallet")}>내 지갑 →</ActionLink></div><form className={styles.form} onSubmit={e => { e.preventDefault(); if (!draft.trim()) return; setPreviewMessages(rows => [...rows, draft.trim(), "“좋아요. 어떤 이야기가 기다리고 있을까요?” (시연 답변)"]); setDraft(""); }}><Field label="메시지"><textarea value={draft} onChange={e => setDraft(e.target.value)} /></Field><Button primary type="submit" disabled={!draft.trim()}>메시지 보내기 ↑</Button></form></>;

  const publicPage = ["topup", "checkout", "purchases", "works"].includes(current);
  return <div className={styles.root} data-theme={theme} data-screen={current}>
    <a href="#account-content" className={styles.skip}>본문으로 이동</a>
    {preview && <nav className={styles.previewBanner} aria-label="개발 시연"><strong>개발용 화면 시연 · 실제 계정·결제와 무관</strong><Link href={base}>기본</Link><Link href={`${href(current === "home" ? "" : section.join("/"))}?state=empty`}>빈 상태</Link><Link href={`${href(current === "home" ? "" : section.join("/"))}?state=loading`}>로딩</Link><Link href={`${href(current === "home" ? "" : section.join("/"))}?state=error`}>오류</Link><Link href="/account">실제 계정으로</Link></nav>}
    <header className={styles.header}><Link href="/" className={styles.brand}><span className={styles.mark}>S</span>모서리</Link><nav className={styles.nav} aria-label="서비스"><Link href="/">발견</Link> · <Link href="/chats">내 대화</Link></nav><Link className={styles.headerCredit} href={href("wallet")}>✓ {creditText} 크레딧</Link><Button onClick={toggleTheme}>{theme === "dark" ? "라이트 모드" : "다크 모드"}</Button><ActionLink primary href={base}>내 계정</ActionLink></header>
    {current === "works" && <aside className={styles.worksSidebar} aria-label="작업실 메뉴"><small>WORKSPACE</small><Link href={href("works")} aria-current="page">내 작품</Link><Link href={preview ? "#account-content" : "#browser-works"}>{preview ? "내 작품 목록" : "이 브라우저의 초안"}</Link><Link href="/studio">제작 스튜디오 →</Link><hr /><Link href={href()}>마이페이지로 돌아가기</Link></aside>}
    <main className={styles.main} id="account-content" tabIndex={-1}>{back}<div className={styles.grid}><div className={styles.content}>
      {!preview && account.session === "loading" ? <><h1>계정을 확인하고 있어요</h1><div className={styles.skeleton} role="status" aria-label="계정 불러오는 중" /></> : !preview && !publicPage && account.session !== "ready" ? <><h1>{account.session === "guest" ? "나의 이야기 공간" : "계정을 불러오지 못했어요"}</h1><p className={styles.description}>{account.session === "guest" ? "로그인하고 대화와 작품, 크레딧을 한곳에서 확인하세요." : "서버에 연결할 수 없어요. 잠시 후 다시 확인해 주세요."}</p><div className={styles.actions}><ActionLink primary href={`/login?next=${encodeURIComponent(href(section.join("/")))}`}>로그인</ActionLink><Button onClick={retry}>다시 확인</Button></div>{current === "works" && <ActionLink href="/studio">브라우저 작업실 열기 →</ActionLink>}</> : content}
      {notice && <StatusRow error>{notice}</StatusRow>}
    </div><aside className={styles.aside}><h2>{current === "settings" ? "내 계정 관리" : `나의 크레딧 · ${creditText}`}</h2>{current === "settings" ? <><p>{account.user?.email ?? "로그인 후 확인할 수 있어요"}</p><p>{account.user?.email_verified ? "✓ 이메일 인증 완료" : "계정 보안을 확인하세요"}</p><Button onClick={() => setModal("withdraw")}>회원 탈퇴 안내 →</Button></> : <><p>사용 가능　{creditText} 크레딧</p><p>사용 예약 중　{balance ? n(balance.reserved_credit) : "—"} 크레딧</p><Link href={href("wallet")}>충전·사용 내역 보기 →</Link><hr /><small>예약 금액은 답변 처리 후 확정됩니다.{preview ? " 표시된 잔액은 개발 시연용입니다." : ""}</small></>}</aside></div></main>
    <footer className={styles.mobileFooter}><Link href="/">발견</Link><Link href={href()}>마이페이지</Link><Button onClick={toggleTheme}>{theme === "dark" ? "라이트 모드" : "다크 모드"}</Button></footer>
    {modal === "withdraw" && <Dialog title="계정 탈퇴 안내" onClose={() => setModal(null)}><div className={styles.dialogBody}><p>탈퇴하면 대화와 작품에 접근할 수 없게 될 수 있어요. 탈퇴 서비스는 아직 준비 중입니다.</p><Button disabled primary>계정 탈퇴 · 준비 중</Button><Button onClick={() => setModal(null)}>취소</Button></div></Dialog>}
    {modal === "settings" && <ChatSettings onClose={() => setModal(null)} walletHref={href("wallet")} />}
    {modal === "credit" && <CreditShortageDialog onClose={() => setModal(null)} walletHref={href("wallet")} />}
  </div>;
}
