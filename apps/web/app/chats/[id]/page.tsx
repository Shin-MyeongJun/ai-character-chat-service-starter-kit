"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowUp, RotateCcw, Sparkles } from "lucide-react";
import { ApiError, createMessage, generateAnswer, getConversationStart, getCreditBalance, getMe, listConversationMessages, type ChatMessage, type ConversationStart, type CreditBalance } from "@/lib/api";
import { demoWorkById, isDemoWork } from "@/lib/works";
import { SiteHeader } from "@/components/site-header";
import { updateRecentChatMessage } from "@/lib/recent-chats";

type DisplayMessage = { id: string; sender_type: string; content: string; position: number; revision: number };
type Pending = { ownerId: string; content: string; messageKey: string; answerKey: string; participant: string; message?: ChatMessage; retryFailed?: boolean };

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
          const answer = await generateAnswer(id, message, value.participant, value.answerKey, controller.signal);
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
      else setError(errorText(cause));
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
    const value: Pending = { ownerId, content, messageKey: crypto.randomUUID(), answerKey: crypto.randomUUID(), participant };
    savePending(value); setDraftValue(""); await continuePending(value);
  }

  const title = demo?.title ?? "대화";
  const selectedDemoStart = demo?.startOptions.find((option) => option.id === params.get("start"));
  const opening = demo ? `${selectedDemoStart?.preview ? `${selectedDemoStart.preview}\n\n` : ""}${demo.opening}` : (start?.opening_mode === "snapshot" ? start.start?.content : null);
  const hasOpening = Boolean(opening?.trim());

  return <div className="chat-layout"><SiteHeader />
    <main className="chat-main"><header className="chat-header"><Link href="/chats" className="icon-button" aria-label="내 대화로 돌아가기"><ArrowLeft size={21} /></Link><div><strong>{title}</strong><small>{demo ? "화면 시연 · 실제 AI 아님" : "연결된 대화"}</small></div><span className="chat-header-star">✳</span></header>
      <div className="chat-scroll"><div className="chat-content">
        {loading && <div className="loading-panel">대화를 불러오는 중...</div>}
        {!loading && <><div className="chat-welcome"><span className="welcome-symbol">✳</span><span className="section-kicker">A STORY BEGINS</span><h1>{demo ? demo.title : start?.start?.title ?? "당신의 이야기"}</h1><p>{demo ? "이 화면의 대화는 시연용입니다. 실제 AI 답변은 생성되지 않습니다." : "대화가 시작되었습니다. 첫 문장을 보내보세요."}</p></div>
          {hasOpening && <div className="opening-card"><span>첫 장면</span><p>{opening}</p></div>}
          {messages.map((message) => <div key={message.id} className={`message-row ${message.sender_type === "user" ? "user" : "character"}`}><div className="message-avatar">{message.sender_type === "user" ? "나" : "✳"}</div><div className="message-body"><span className="message-name">{message.sender_type === "user" ? "나" : demo?.title ?? "캐릭터"}</span><div className="message-text">{message.content}</div></div></div>)}
          {busy && <div className="thinking-row"><span>✳</span><div><strong>이야기를 이어가고 있어요</strong><div className="thinking-dots"><i /><i /><i /></div></div><button type="button" onClick={() => answerController.current?.abort()}>대기 중단</button></div>}
          {notice && <div className="chat-notice" role="status">{notice}</div>}
          {error && <div className="chat-error" role="alert"><span>{error}</span>{!demo && error.includes("로그인") && <Link href={`/login?next=${encodeURIComponent(`/chats/${id}`)}`}>로그인</Link>}</div>}
          {pending && !busy && <button className="resume-button" type="button" onClick={() => continuePending(pending)}><RotateCcw size={16} /> {pending.retryFailed ? "저장된 메시지로 답변 다시 시도하기" : "같은 요청으로 결과 확인하기"}</button>}
        </>}
        <div ref={bottomRef} /></div></div>
      <div className="composer-wrap"><form className="composer" onSubmit={submit}><textarea aria-label="메시지 입력" placeholder={loading ? "대화를 불러오는 중..." : "당신의 다음 장면을 적어보세요..."} value={draft} disabled={loading || busy || !!pending || !!error && !demo && !start} onChange={(event) => setDraftValue(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={2} /><div className="composer-bottom"><span><Sparkles size={14} /> {demo ? "시연 대화" : balance ? `사용 가능 ${balance.available_credit.toLocaleString("ko-KR")} 크레딧` : balanceUnavailable ? "크레딧 잔액 확인 불가" : "크레딧 잔액 확인 중"}</span><button type="submit" disabled={loading || busy || !!pending || !draft.trim()} aria-label="메시지 보내기"><ArrowUp size={20} /></button></div></form><p className="composer-hint">Enter로 전송 · Shift+Enter로 줄바꿈{answerPrice !== null ? ` · 최근 답변 예약 가격 ${answerPrice.toLocaleString("ko-KR")} 크레딧` : " · 가격은 답변 요청 시 서버가 계산합니다."}</p></div>
    </main>
  </div>;
}

export default function ChatPage() { return <Suspense><ChatContent /></Suspense>; }
