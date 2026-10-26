"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, request, createMessage, generateAnswer, getConversationStart, getCreditBalance, getMe, listConversationMessages, type ChatMessage, type ConversationStart, type CreditBalance } from "@/lib/api";
import { demoWorkById, isDemoWork } from "@/lib/works";
import { useUserTheme } from "@/components/user-theme";
import { ActionLink, Button, Card, Field, Section, StatusRow } from "@/components/account/account-ui";
import { ChatSettings, CreditShortageDialog } from "@/components/account/chat-settings";
import styles from "@/components/account/account.module.css";
import { updateRecentChatMessage } from "@/lib/recent-chats";

type DisplayMessage = { id: string; sender_type: string; content: string; position: number; revision: number };
type Pending = { ownerId: string; content: string; messageKey: string; answerKey: string; participant: string; message?: ChatMessage; retryFailed?: boolean; manualEntryIds?: string[] };

function errorText(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 401) return "로그인이 만료되었어요. 다시 로그인한 뒤 대화를 확인해 주세요.";
    if (cause.code === "csrf_failed") return "요청 인증을 갱신하지 못했어요. 저장된 요청으로 다시 시도해 주세요.";
    if (cause.status === 402) return "이용 가능한 크레딧이 부족해요.";
    if (cause.code === "credit_account_unavailable") return "크레딧 지갑을 사용할 수 없어요. 계정 상태를 확인해 주세요.";
    if (cause.code === "billing_not_configured") return "이 작품의 가격 설정이 준비되지 않았어요.";
    if (cause.code === "billing_conflict") return "가격 또는 결제 상태가 바뀌었어요. 같은 요청으로 결과를 다시 확인해 주세요.";
    if (cause.code === "storage_pending_recovery") return "답변 저장을 확인 중이에요. 같은 요청으로 다시 확인할 수 있습니다.";
    if (cause.code === "summary_required") return "긴 대화를 정리하는 중이에요. 잠시 후 다시 시도해 주세요.";
    if (cause.status === 429) return "요청이 많아요. 잠시 후 다시 시도해 주세요.";
    if (cause.status === 409) return "대화 상태가 바뀌었어요. 기록을 다시 확인해 주세요.";
  }
  return "요청 결과를 확인할 수 없어요. 같은 요청으로 다시 확인해 주세요.";
}

const demoReplies = [
  "잠시 침묵이 흐른다. 창밖에서 바람이 지나가고, 상대는 당신의 말을 천천히 되새긴다. ‘그렇게 생각했군요. 조금 더 들려줄래요?’",
  "상대는 뜻밖이라는 듯 웃었다. ‘그 선택을 할 줄은 몰랐어요.’ 바로 다음 순간, 멀리서 작은 소리가 들려왔다.",
  "‘좋아요. 이번에는 당신이 정해주세요.’ 상대가 손을 내밀었다. 이야기는 아직 끝나지 않았다.",
];

function ChatContent() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const demo = isDemoWork(id) ? demoWorkById(id) : undefined;
  const [manualLore, setManualLore] = useState<{id: string; title: string}[]>([]);
  const [manualIds, setManualIds] = useState<string[]>([]);
  const [manualError, setManualError] = useState("");
  const [start, setStart] = useState<ConversationStart | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [balance, setBalance] = useState<CreditBalance | null>(null);
  const [balanceUnavailable, setBalanceUnavailable] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [creditDialog, setCreditDialog] = useState(false);
  const { theme, toggleTheme } = useUserTheme();
  const [answerPrice, setAnswerPrice] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const answerController = useRef<AbortController | null>(null);
  const running = useRef(false);

  const pendingKey = (userId: string) => `moseori_pending_${userId}_${id}`;
  const draftKey = demo ? `moseori_draft_${id}` : ownerId ? `moseori_draft_${ownerId}_${id}` : null;

  const refreshMessages = useCallback(async () => {
    const items = await listConversationMessages(id);
    setMessages(items);
    const latest = items.at(-1);
    if (latest) updateRecentChatMessage(id, latest.content, ownerId);
  }, [id, ownerId]);

  useEffect(() => {
    setDraft(draftKey ? localStorage.getItem(draftKey) ?? "" : "");
  }, [draftKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setManualLore([]); setManualIds([]); setManualError("");
    setLoading(true); setMessages([]); setStart(null); setOwnerId(null); setPending(null); setError(null); setNotice(null); setAnswerPrice(null); setBalance(null); setBalanceUnavailable(false);
    if (demo) {
      try {
        const saved = JSON.parse(localStorage.getItem(`moseori_demo_${id}`) ?? "[]") as DisplayMessage[];
        setMessages(saved);
        if (saved.length) updateRecentChatMessage(id, saved[saved.length - 1].content);
      } catch { setMessages([]); }
      setLoading(false);
      return;
    }
    let active = true;
    getMe().then(async (user) => {
      const [opening, items] = await Promise.all([getConversationStart(id), listConversationMessages(id)]);
      if (!active) return;
      void getCreditBalance().then(value => { if (active) { setBalance(value); setBalanceUnavailable(false); } }).catch(() => { if (active) setBalanceUnavailable(true); });
      setOwnerId(user.id); setStart(opening); setMessages(items);
      void request<{items: {id: string; title: string}[]}>(`/conversations/${encodeURIComponent(id)}/manual-lore`).then(value => {if (active) setManualLore(value.items);}).catch(() => {if (active) setManualError("수동 로어 목록을 불러오지 못했어요.");});
      const latest = items.at(-1);
      if (latest) updateRecentChatMessage(id, latest.content, user.id);
      const key = `moseori_pending_${user.id}_${id}`;
      try {
        const stored = JSON.parse(sessionStorage.getItem(key) ?? sessionStorage.getItem(`moseori_pending_${id}`) ?? "null") as Pending | null;
        if (stored?.ownerId === user.id) setPending(stored);
      } catch { sessionStorage.removeItem(key); }
    }).catch((cause) => { if (active) setError(errorText(cause)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [demo, id]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages.length, busy]);

  function setDraftValue(value: string) { setDraft(value); if (draftKey) localStorage.setItem(draftKey, value); }
  function savePending(value: Pending | null) {
    setPending(value);
    if (value) sessionStorage.setItem(pendingKey(value.ownerId), JSON.stringify(value));
    else if (ownerId) sessionStorage.removeItem(pendingKey(ownerId));
    // The legacy value has been migrated only after checking its owner.
    sessionStorage.removeItem(`moseori_pending_${id}`);
  }

  async function continuePending(value: Pending) {
    if (running.current) return;
    running.current = true;
    const controller = new AbortController();
    answerController.current = controller;
    setBusy(true); setError(null); setNotice(null);
    try {
      let message = value.message;
      if (!message) {
        message = await createMessage(id, value.content, value.messageKey);
        value = { ...value, message };
        savePending(value);
        await refreshMessages();
      }
      for (let attempt = 0; attempt < 20; attempt += 1) {
        if (controller.signal.aborted) { setNotice("대기만 중단했어요. 저장된 요청으로 결과를 다시 확인할 수 있어요."); return; }
        try {
          const answer = await generateAnswer(id, message, value.participant, value.answerKey, controller.signal, value.manualEntryIds ?? []);
          if (typeof answer.price_credit === "number") setAnswerPrice(answer.price_credit);
          if (answer.status === "pending") { await new Promise((resolve) => setTimeout(resolve, 3000)); continue; }
          await refreshMessages();
          void getCreditBalance().then(value => { setBalance(value); setBalanceUnavailable(false); }).catch(() => setBalanceUnavailable(true));
          if (answer.status !== "succeeded") {
            if (answer.retryable) savePending({ ...value, answerKey: crypto.randomUUID(), retryFailed: true });
            else savePending(null);
            setError(answer.error_code === "summary_required"
              ? "긴 대화를 정리하는 중이에요. 잠시 후 답변을 다시 시도해 주세요."
              : `답변이 완료되지 않았어요: ${answer.error_code ?? answer.status}. ${answer.retryable ? "다시 시도할 수 있어요." : "대화 내용을 확인해 주세요."}`);
          } else savePending(null);
          return;
        } catch (cause) {
          if (cause instanceof ApiError && cause.code === "storage_pending_recovery") { await new Promise((resolve) => setTimeout(resolve, 3000)); continue; }
          if (cause instanceof ApiError && ![401, 402, 429].includes(cause.status) && cause.code !== "csrf_failed" && cause.status < 500) { savePending(null); await refreshMessages(); }
          throw cause;
        }
      }
      setNotice("답변을 계속 처리 중이에요. 같은 요청으로 다시 확인해 주세요.");
    } catch (cause) {
      if (controller.signal.aborted) setNotice("대기만 중단했어요. 저장된 요청으로 결과를 다시 확인할 수 있어요.");
      else { setError(errorText(cause)); if (cause instanceof ApiError && cause.status === 402) setCreditDialog(true); }
    }
    finally { answerController.current = null; running.current = false; setBusy(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy || pending) return;
    if (demo) {
      const now = Date.now();
      const next: DisplayMessage[] = [
        ...messages,
        { id: crypto.randomUUID(), sender_type: "user", content, position: now, revision: 1 },
        { id: crypto.randomUUID(), sender_type: "character", content: demoReplies[messages.length / 2 % demoReplies.length], position: now + 1, revision: 1 },
      ];
      setMessages(next); localStorage.setItem(`moseori_demo_${id}`, JSON.stringify(next)); updateRecentChatMessage(id, next[next.length - 1].content); setDraftValue(""); return;
    }
    const participant = start?.primary_product_character_id ?? start?.participants.find((item) => item.product_character_id)?.product_character_id;
    if (!participant || !ownerId) { setError("참여 캐릭터나 로그인 상태를 확인할 수 없어요."); return; }
    const value: Pending = { ownerId, content, messageKey: crypto.randomUUID(), answerKey: crypto.randomUUID(), participant, manualEntryIds: [...manualIds] };
    savePending(value); setDraftValue(""); await continuePending(value);
  }

  const title = demo?.title ?? "대화";
  const selectedDemoStart = demo?.startOptions.find((option) => option.id === params.get("start"));
  const opening = demo ? `${selectedDemoStart?.preview ? `${selectedDemoStart.preview}\n\n` : ""}${demo.opening}` : (start?.opening_mode === "snapshot" ? start.start?.content : null);
  const hasOpening = Boolean(opening?.trim());

  return <div className={styles.root} data-theme={theme}>
    <a href="#user-content" className={styles.skip}>본문으로 이동</a>
    <header className={styles.header}><Link href="/" className={styles.brand}><span className={styles.mark}>S</span>모서리</Link><nav className={styles.nav}><Link href="/">발견</Link> · <Link href="/chats">내 대화</Link></nav><Button onClick={toggleTheme}>{theme === "dark" ? "라이트 모드" : "다크 모드"}</Button><ActionLink primary href="/account">내 계정</ActionLink></header>
    <main id="user-content" tabIndex={-1} className={styles.main}>
      <ActionLink href={params.get("from") === "account" ? "/account" : "/chats"}>‹ {params.get("from") === "account" ? "마이페이지" : "내 대화"}</ActionLink>
      <div className={styles.grid}><div className={styles.content}>
        <h1>{title === "대화" ? start?.start?.title ?? "대화" : title}</h1><p className={styles.description}>{demo ? "화면 시연 · 실제 AI 답변과 크레딧 사용이 발생하지 않습니다." : "연결된 대화 · 나의 이야기를 이어가세요."}</p>
        {loading && <StatusRow>대화를 불러오는 중…</StatusRow>}
        {!loading && <>
          {hasOpening && <Section title="첫 장면"><Card><p className={styles.chatMessage}>{opening}</p></Card></Section>}
          {messages.map(message => <Section key={message.id} title={message.sender_type === "user" ? "나" : demo?.title ?? "캐릭터"}><Card><p className={styles.chatMessage}>{message.content}</p></Card></Section>)}
          {busy && <StatusRow><p>이야기를 이어가고 있어요.</p><Button onClick={() => answerController.current?.abort()}>대기 중단</Button></StatusRow>}
          {notice && <StatusRow>{notice}</StatusRow>}
          {error && <StatusRow error><p>{error}</p>{!demo && error.includes("로그인") && <ActionLink href={`/login?next=${encodeURIComponent(`/chats/${id}`)}`}>로그인</ActionLink>}{error.includes("부족") && <ActionLink href="/account/wallet">내 크레딧 지갑</ActionLink>}</StatusRow>}
          {pending && !busy && <Button onClick={() => void continuePending(pending)}>{pending.retryFailed ? "저장된 메시지로 답변 다시 시도하기" : "같은 요청으로 결과 확인하기"}</Button>}
        </>}
        <small>{demo ? "시연 대화" : balance ? `사용 가능 ${balance.available_credit.toLocaleString("ko-KR")} 크레딧` : balanceUnavailable ? "크레딧 잔액 확인 불가" : "크레딧 잔액 확인 중"}{answerPrice !== null ? ` · 최근 답변 예약 가격 ${answerPrice.toLocaleString("ko-KR")} 크레딧` : " · 가격은 답변 요청 시 서버가 계산합니다."}</small>
        <div className={styles.actions}><Button primary onClick={() => setSettingsOpen(true)}>대화 설정 ⚙</Button><ActionLink href="/account/wallet">내 지갑 →</ActionLink></div>
        {manualError && <StatusRow error>{manualError}</StatusRow>}{manualLore.length > 0 && <Section title="이번 답변에 수동 적용할 로어"><small>선택은 이 답변 요청에만 적용돼요.</small>{manualLore.map(entry => <label key={entry.id}><input type="checkbox" disabled={busy || !!pending} checked={manualIds.includes(entry.id)} onChange={event => setManualIds(ids => event.target.checked ? [...ids, entry.id] : ids.filter(id => id !== entry.id))} /> {entry.title}</label>)}</Section>}
        <form className={styles.form} onSubmit={submit}><Field label="메시지 입력"><textarea placeholder={loading ? "대화를 불러오는 중…" : "당신의 다음 장면을 적어보세요…"} value={draft} disabled={loading || busy || !!pending || !!error && !demo && !start} onChange={event => setDraftValue(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={2} /></Field><Button primary type="submit" disabled={loading || busy || !!pending || !draft.trim() || !!error && !demo && !start}>메시지 보내기 ↑</Button><small>Enter로 전송 · Shift+Enter로 줄바꿈</small></form><div ref={bottomRef} />
      </div><aside className={styles.aside}><h2>나의 대화</h2><p>이야기는 자동으로 저장돼요. 확인 중인 답변은 같은 요청으로 다시 확인할 수 있어요.</p><ActionLink href="/account">마이페이지 →</ActionLink><Button onClick={() => setSettingsOpen(true)}>대화 설정</Button></aside></div>
    </main>
    {settingsOpen && <ChatSettings onClose={() => setSettingsOpen(false)} />}
    {creditDialog && <CreditShortageDialog onClose={() => setCreditDialog(false)} />}
  </div>;
}

export default function ChatPage() { return <Suspense><ChatContent /></Suspense>; }
