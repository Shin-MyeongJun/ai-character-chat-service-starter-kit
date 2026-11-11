"use client";

import Link from "next/link";
import { ArrowDown, ChevronLeft, GitBranch, RotateCw, SlidersHorizontal, Trash2 } from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { Fragment, Suspense, useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { ApiError, createMessage, generateAnswer, getManualLore, getConversationStart, getCreditBalance, getMe, type ChatMessage, type ContentBlock, type ConversationStart, type CreditBalance, type ManualLore } from "@/lib/api";
import { demoWorkById, isDemoWork } from "@/lib/works";
import { useUserTheme } from "@/components/user-theme";
import { Dialog } from "@/components/account/account-ui";
import { CreditShortageDialog } from "@/components/account/chat-settings";
import accountStyles from "@/components/account/account.module.css";
import { ChatImageFrame, useConversationAlbum } from "@/components/chat/chat-images";
import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatReadingSettings, useReadingOptions } from "@/components/chat/chat-reading-settings";
import { designCharacter, designMessages, designOpening, designTitle, previewReply, previewShortcuts, type PreviewModel, type PreviewShortcut } from "@/components/chat/chat-preview-data";
import { useChatScroll, useChatViewport } from "@/components/chat/use-chat-viewport";
import styles from "@/components/chat/chat.module.css";
import { readChatText } from "@/lib/chat-text";
import { ConversationHistorySession, type ConversationHistory } from "@/lib/chat-history";
import { AUTH_CHANGED_KEY, readRecentChats, updateRecentChatMessage } from "@/lib/recent-chats";

type DisplayMessage = { id: string; sender_type: string; content: string; position: number; revision: number; content_blocks?: ContentBlock[] | null };
type Pending = { ownerId: string; content: string; messageKey: string; answerKey: string; participant: string; message?: ChatMessage; retryFailed?: boolean; manualEntryIds?: string[] };
type PreviewBranch = { messages: DisplayMessage[]; draft: string };
type PreviewAction = { kind: "reroll" | "branch" | "delete"; messageId: string };

const previewActionCopy = {
  reroll: { title: "답변을 다시 만들까요?", detail: "에린이 같은 대사에 새로 답하는 모습을 시연해요.", label: "리롤 시연" },
  branch: { title: "이 장면에서 분기할까요?", detail: "이 답변까지의 대화를 임시 시연에서 이어가요. 원본은 그대로 남아요.", label: "분기 시연" },
  delete: { title: "이 답변을 삭제할까요?", detail: "시연 대화에서 이 답변 한 건을 삭제해요.", label: "삭제" },
};

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

function ChatProse({ content, character = false }: { content: string; character?: boolean }) {
  return <div className={styles.prose}>{readChatText(content, character).map((paragraph, index) =>
    <p key={index} className={character && paragraph.every(part => !part.narration) ? styles.speechLine : undefined}>
      {paragraph.map((part, partIndex) => <span key={partIndex} className={part.narration ? styles.narration : styles.speech}>{part.text}</span>)}
    </p>,
  )}</div>;
}

function ChatBlocks({ blocks, content, showImages, opening = false, character = false }: {
  blocks?: ContentBlock[] | null;
  content: string;
  showImages: boolean;
  opening?: boolean;
  character?: boolean;
}) {
  const text = (value: string) => opening ? <p>{value}</p> : <ChatProse content={value} character={character} />;
  if (blocks == null) return text(content);
  return blocks.map((block, index) => block.type === "text"
    ? <Fragment key={index}>{text(block.text)}</Fragment>
    : showImages && <ChatImageFrame key={index} image={block} />);
}

function ChatContent({ id, preview, startChoice, fromAccount }: { id: string; preview: boolean; startChoice: string | null; fromAccount: boolean }) {
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [manualLore, setManualLore] = useState<ManualLore[]>([]);
  const [manualEntryIds, setManualEntryIds] = useState<string[]>([]);
  const [manualError, setManualError] = useState(false);
  const { album, refreshAlbum } = useConversationAlbum(id, ownerId, settingsOpen);
  const [creditDialog, setCreditDialog] = useState(false);
  const { theme } = useUserTheme();
  const [reading, setReading] = useReadingOptions();
  const [shortcuts, setShortcuts] = useState<PreviewShortcut[]>([]);
  const [previewModel, setPreviewModel] = useState<PreviewModel>("default");
  const [branch, setBranch] = useState<PreviewBranch | null>(null);
  const [previewAction, setPreviewAction] = useState<PreviewAction | null>(null);
  const [answerPrice, setAnswerPrice] = useState<number | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const answerController = useRef<AbortController | null>(null);
  const running = useRef(false);
  const historySession = useRef<ConversationHistorySession | null>(null);
  const [authVersion, setAuthVersion] = useState(0);

  const pendingKey = (userId: string) => `moseori_pending_${userId}_${id}`;
  const demoKey = preview ? `${id}_design_v2` : id;
  const draftKey = demo ? `moseori_draft_${demoKey}` : ownerId ? `moseori_draft_${ownerId}_${id}` : null;
  const visibleMessages = branch?.messages ?? messages;
  const activeDraft = branch?.draft ?? draft;
  const scroll = useChatScroll(branch ? `${id}:branch` : id, !loading, visibleMessages, preview && !branch);
  useChatViewport(rootRef);

  const publishHistory = useCallback((scope: ConversationHistorySession, history: ConversationHistory) => {
    if (historySession.current !== scope) return;
    setMessages(history.messages);
    const latest = history.messages.at(-1);
    updateRecentChatMessage(scope.conversationId, latest?.content ?? "", scope.ownerId);
  }, []);

  const refreshMessages = useCallback(async (reset = false, scope = historySession.current, signal?: AbortSignal) => {
    if (!scope || scope.conversationId !== id) return;
    const history = await scope.sync(reset, signal);
    if (history) publishHistory(scope, history);
  }, [id, publishHistory]);

  useEffect(() => {
    const changed = () => setAuthVersion(value => value + 1);
    const storage = (event: StorageEvent) => { if (event.key === AUTH_CHANGED_KEY || event.key === null) changed(); };
    window.addEventListener(AUTH_CHANGED_KEY, changed); window.addEventListener("storage", storage);
    return () => { window.removeEventListener(AUTH_CHANGED_KEY, changed); window.removeEventListener("storage", storage); };
  }, []);

  useEffect(() => {
    if (demo || loading || !ownerId) return;
    const sync = () => {
      if (running.current) return;
      const scope = historySession.current;
      void refreshMessages(false, scope).catch(cause => { if (scope === historySession.current) setError(errorText(cause)); });
    };
    window.addEventListener("focus", sync);
    return () => window.removeEventListener("focus", sync);
  }, [demo, loading, ownerId, refreshMessages]);

  useEffect(() => {
    try { setDraft(draftKey ? localStorage.getItem(draftKey) ?? "" : ""); }
    catch { setDraft(""); }
  }, [draftKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setManualLore([]); setManualEntryIds([]); setManualError(false);
    setLoading(true); setBusy(false); setMessages([]); setStart(null); setOwnerId(null); setPending(null); setError(null); setNotice(null); setAnswerPrice(null); setBalance(null); setBalanceUnavailable(false);
    if (demo) {
      try {
        const saved: DisplayMessage[] | null = JSON.parse(localStorage.getItem(`moseori_demo_${demoKey}`) ?? "null");
        const initial = Array.isArray(saved) ? saved : preview ? designMessages : [];
        setMessages(initial);
        if (!preview && initial.length) updateRecentChatMessage(id, initial[initial.length - 1].content);
      } catch { setMessages(preview ? designMessages : []); }
      setLoading(false);
      return;
    }
    let active = true;
    let scope: ConversationHistorySession | null = null;
    const controller = new AbortController();
    getMe().then(async (user) => {
      if (!active) return;
      scope = new ConversationHistorySession(id, user.id);
      historySession.current = scope;
      const [opening, history] = await Promise.all([getConversationStart(id), scope.sync(false, controller.signal)]);
      if (!active || !history) return;
      void getCreditBalance().then(value => { if (active) { setBalance(value); setBalanceUnavailable(false); } }).catch(() => { if (active) setBalanceUnavailable(true); });
      setOwnerId(user.id); setStart(opening); publishHistory(scope, history);
      void getManualLore(id, controller.signal).then(({ items }) => {
        if (active) setManualLore(items);
      }).catch(() => { if (active) setManualError(true); });
      const key = `moseori_pending_${user.id}_${id}`;
      try {
        const stored = JSON.parse(sessionStorage.getItem(key) ?? sessionStorage.getItem(`moseori_pending_${id}`) ?? "null") as Pending | null;
        if (stored?.ownerId === user.id) setPending(stored);
      } catch { sessionStorage.removeItem(key); }
    }).catch((cause) => { if (active) setError(errorText(cause)); }).finally(() => { if (active) setLoading(false); });
    return () => {
      active = false; controller.abort(); scope?.dispose();
      historySession.current = null;
      answerController.current?.abort(); answerController.current = null; running.current = false;
    };
  }, [demo, demoKey, preview, id, authVersion, publishHistory]);

  function setDraftValue(value: string) {
    if (branch) { setBranch(current => current && { ...current, draft: value }); return; }
    setDraft(value);
    try { if (draftKey) localStorage.setItem(draftKey, value); } catch { /* The current draft stays editable. */ }
  }
  function savePending(value: Pending | null) {
    setPending(value);
    if (value) sessionStorage.setItem(pendingKey(value.ownerId), JSON.stringify(value));
    else if (ownerId) sessionStorage.removeItem(pendingKey(ownerId));
    // The legacy value has been migrated only after checking its owner.
    sessionStorage.removeItem(`moseori_pending_${id}`);
  }

  async function continuePending(value: Pending) {
    if (running.current) return;
    const scope = historySession.current;
    if (!scope || scope.conversationId !== id || scope.ownerId !== value.ownerId) return;
    const isCurrent = () => historySession.current === scope;
    running.current = true;
    const controller = new AbortController();
    answerController.current = controller;
    setBusy(true); setError(null); setNotice(null);
    try {
      if (value.retryFailed) {
        // The new attempt already has its own key. Any later recovery must replay it.
        value = { ...value, retryFailed: false };
        savePending(value);
      }
      let message = value.message;
      if (!message) {
        message = await createMessage(id, value.content, value.messageKey);
        if (!isCurrent()) return;
        value = { ...value, message };
        savePending(value);
        const history = scope.append(message);
        if (history) publishHistory(scope, history);
      }
      for (let attempt = 0; attempt < 20; attempt += 1) {
        if (!isCurrent()) return;
        if (controller.signal.aborted) { setNotice("대기만 중단했어요. 저장된 요청으로 결과를 다시 확인할 수 있어요."); return; }
        try {
          const answer = await generateAnswer(id, message, value.participant, value.answerKey, controller.signal, value.manualEntryIds ?? []);
          if (!isCurrent()) return;
          if (typeof answer.price_credit === "number") setAnswerPrice(answer.price_credit);
          if (answer.status === "pending") { await new Promise((resolve) => setTimeout(resolve, 3000)); continue; }
          await refreshMessages(false, scope, controller.signal);
          if (!isCurrent()) return;
          void getCreditBalance().then(value => { if (isCurrent()) { setBalance(value); setBalanceUnavailable(false); } }).catch(() => { if (isCurrent()) setBalanceUnavailable(true); });
          if (answer.status !== "succeeded") {
            const canRetry = answer.retryable && !answer.uncertain;
            if (canRetry) savePending({ ...value, answerKey: crypto.randomUUID(), retryFailed: true });
            else savePending(null);
            setError(answer.error_code === "summary_required"
              ? "긴 대화를 정리하는 중이에요. 잠시 후 답변을 다시 시도해 주세요."
              : canRetry ? "답변을 만들지 못했어요. 같은 메시지로 다시 시도할 수 있어요."
                : "답변이 완료되지 않았어요. 대화 내용을 확인해 주세요.");
          } else {
            refreshAlbum();
            savePending(null);
          }
          return;
        } catch (cause) {
          if (!isCurrent()) return;
          if (cause instanceof ApiError && cause.code === "storage_pending_recovery") { await new Promise((resolve) => setTimeout(resolve, 3000)); continue; }
          if (cause instanceof ApiError && ![401, 402, 429].includes(cause.status) && !["csrf_failed", "billing_conflict"].includes(cause.code) && cause.status < 500) { savePending(null); await refreshMessages(true, scope, controller.signal); }
          throw cause;
        }
      }
      if (isCurrent()) setNotice("답변을 계속 처리 중이에요. 같은 요청으로 다시 확인해 주세요.");
    } catch (cause) {
      if (!isCurrent()) return;
      if (controller.signal.aborted) setNotice("대기만 중단했어요. 저장된 요청으로 결과를 다시 확인할 수 있어요.");
      else { setError(errorText(cause)); if (cause instanceof ApiError && cause.status === 402) setCreditDialog(true); }
    }
    finally { if (answerController.current === controller) { answerController.current = null; running.current = false; setBusy(false); } }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = activeDraft.trim();
    const standalone = preview && previewShortcuts.find(item => item.standalone && shortcuts.includes(item.id));
    if ((!content && !standalone) || busy || pending || running.current) return;
    if (demo) {
      const position = (visibleMessages.at(-1)?.position ?? 0) + 1;
      const selection = previewShortcuts.filter(item => shortcuts.includes(item.id)).map(item => item.name);
      const displayContent = preview ? [content, selection.join(" · ")].filter(Boolean).join("\n\n") : content;
      const next: DisplayMessage[] = [
        ...visibleMessages,
        { id: crypto.randomUUID(), sender_type: "user", content: displayContent, position, revision: 1 },
        { id: crypto.randomUUID(), sender_type: "character", content: preview ? previewReply(shortcuts, previewModel) : demoReplies[Math.floor(messages.length / 2) % demoReplies.length], position: position + 1, revision: 1 },
      ];
      if (branch) setBranch({ messages: next, draft: "" });
      else {
        setMessages(next);
        try { localStorage.setItem(`moseori_demo_${demoKey}`, JSON.stringify(next)); } catch { /* The demo still works in memory. */ }
        if (!preview) updateRecentChatMessage(id, next[next.length - 1].content);
        setDraftValue("");
      }
      setShortcuts([]);
      return;
    }
    const participant = start?.primary_product_character_id ?? start?.participants.find((item) => item.product_character_id)?.product_character_id;
    if (!participant || !ownerId) { setError("참여 캐릭터나 로그인 상태를 확인할 수 없어요."); return; }
    const value: Pending = { ownerId, content, messageKey: crypto.randomUUID(), answerKey: crypto.randomUUID(), participant, manualEntryIds };
    try { savePending(value); }
    catch {
      setPending(null);
      setError("요청을 준비하지 못했어요. 입력한 내용을 유지했어요.");
      return;
    }
    setManualEntryIds([]);
    setDraftValue(""); await continuePending(value);
  }

  function confirmPreviewAction() {
    if (!preview || !previewAction) return;
    const index = visibleMessages.findIndex(message => message.id === previewAction.messageId);
    if (index < 0) return;
    if (previewAction.kind === "branch") {
      setBranch({ messages: visibleMessages.slice(0, index + 1), draft: "" });
      setShortcuts([]);
    } else if (previewAction.kind === "delete") {
      const next = visibleMessages.filter(message => message.id !== previewAction.messageId);
      if (branch) setBranch({ ...branch, messages: next });
      else {
        setMessages(next);
        try { localStorage.setItem(`moseori_demo_${demoKey}`, JSON.stringify(next)); } catch { /* The demo still works in memory. */ }
      }
    } else {
      const next = visibleMessages.map((message, i) => i === index ? {
        ...message,
        content: "**에린은 은색 열쇠를 책상에 조심스레 내려놓았다.**\n\n“먼저 편지를 읽어 봐요. 그다음엔 어디로 갈지 함께 정해요.”",
        revision: message.revision + 1,
      } : message);
      if (branch) setBranch({ ...branch, messages: next });
      else setMessages(next);
    }
    setPreviewAction(null);
  }

  const recentTitle = ownerId ? readRecentChats(ownerId).find(item => item.id === id)?.title : undefined;
  const title = preview ? designTitle : demo?.title ?? recentTitle ?? start?.start?.title ?? "대화";
  const character = preview ? designCharacter : "캐릭터";
  const characterDetail = preview ? "기록실 안내인" : undefined;
  const selectedDemoStart = demo?.startOptions.find(option => option.id === startChoice);
  const opening = preview ? designOpening : demo
    ? `${selectedDemoStart?.preview ? `${selectedDemoStart.preview}\n\n` : ""}${demo.opening}`
    : start?.opening_mode === "snapshot" ? start.opening_message ?? start.start?.content : null;
  const openingBlocks = demo ? null : start?.content_blocks;
  const statusAnchor = pending?.message?.id;
  const inlineStatus = !loading && (busy || notice || error || pending) ? <div className={styles.status}>
    {busy && <><p role="status">이야기를 이어가고 있어요.</p><button className={styles.button} type="button" onClick={() => answerController.current?.abort()}>대기 중단</button></>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {error?.includes("로그인") && !demo && <Link href={`/login?next=${encodeURIComponent(`/chats/${id}`)}`}>로그인</Link>}
    {error?.includes("부족") && <Link href="/account/wallet">내 크레딧 지갑</Link>}
    {error && !demo && !start && !error.includes("로그인") && <button className={styles.button} type="button" onClick={() => setAuthVersion(value => value + 1)}>다시 불러오기</button>}
    {pending && !busy && <button className={styles.button} type="button" onClick={() => void continuePending(pending)}>{pending.retryFailed ? "같은 메시지로 답변 다시 시도" : "같은 요청으로 결과 확인"}</button>}
  </div> : null;

  return <div ref={rootRef} className={`${accountStyles.root} ${styles.root}`} data-chat="" data-theme={theme}
    style={{ "--chat-reading-size": `${reading.size}px`, "--chat-reading-line": `${reading.spacing}px` } as CSSProperties}>
    <a href="#user-content" className={styles.skip}>본문으로 이동</a>
    <header className={styles.header}>
      <Link href={fromAccount ? "/account" : "/chats"} className={styles.iconButton} aria-label={fromAccount ? "마이페이지로 돌아가기" : "내 대화로 돌아가기"}><ChevronLeft size={20} /></Link>
      <div className={styles.identity}><h1 title={title}>{title}</h1><p>{character}{characterDetail ? ` · ${characterDetail}` : ""}</p></div>
      {demo && <span className={styles.previewTag}>{branch ? "분기 시연" : "시연"}</span>}
      {branch && <button type="button" className={styles.button} onClick={() => { setBranch(null); setShortcuts([]); }}>원본</button>}
      <button type="button" className={styles.iconButton} aria-label="대화 설정" aria-expanded={settingsOpen}
        onClick={() => setSettingsOpen(value => !value)}><SlidersHorizontal size={19} /></button>
    </header>
    <div className={styles.workspace}>
      <div className={styles.conversation}>
        <main id="user-content" tabIndex={-1} className={styles.scroll} ref={scroll.scrollRef} onScroll={scroll.onScroll} aria-label="대화 본문">
          <div className={styles.column} ref={scroll.columnRef}>
            {loading && <p className={styles.status} role="status">대화를 불러오는 중…</p>}
            {!loading && (openingBlocks?.length || (openingBlocks == null && opening?.trim())) ? <section className={styles.opening} aria-label="첫 장면">
              <h2>{preview ? "첫 장면 · 비 내리는 기록실" : "첫 장면"}</h2><ChatBlocks opening blocks={openingBlocks} content={opening ?? ""} showImages={reading.showImages} />
            </section> : null}
            {!loading && visibleMessages.map(message => {
              const user = message.sender_type === "user";
              return <Fragment key={message.id}>
                <article key={message.revision} aria-label={user ? "내 메시지" : `${character} 답변`} className={`${styles.message} ${user ? styles.user : ""}`}>
                  {!user && <p className={styles.speaker}>{character}</p>}
                  <ChatBlocks blocks={message.content_blocks} content={message.content} character={!user} showImages={reading.showImages} />
                  {preview && !user && <div className={styles.messageActions}>
                    <button type="button" className={styles.button} onClick={() => setPreviewAction({ kind: "reroll", messageId: message.id })}><RotateCw size={15} />리롤</button>
                    <button type="button" className={styles.button} onClick={() => setPreviewAction({ kind: "branch", messageId: message.id })}><GitBranch size={15} />분기</button>
                    <button type="button" className={styles.button} onClick={() => setPreviewAction({ kind: "delete", messageId: message.id })}><Trash2 size={15} />삭제</button>
                  </div>}
                </article>
                {statusAnchor === message.id && inlineStatus}
              </Fragment>;
            })}
            {(!statusAnchor || !visibleMessages.some(message => message.id === statusAnchor)) && inlineStatus}
          </div>
        </main>
        <footer className={styles.footer}>
          {scroll.away && !loading && <div className={styles.jump}>
            {scroll.newAnswer && <small role="status">새 답변이 도착했어요</small>}
            <button type="button" className={styles.button} onClick={scroll.jumpToLatest}>최신 메시지로 <ArrowDown size={17} /></button>
          </div>}
          {manualError && <p className={styles.status} role="alert">수동 로어 목록을 불러오지 못했어요.</p>}
          <ChatComposer draft={activeDraft} onDraft={setDraftValue} onSubmit={submit} disabled={loading || busy || Boolean(pending) || !demo && !start}
            loading={loading} placeholder={preview ? "에린에게 이야기를 이어가세요…" : "다음 장면을 적어보세요…"}
            manualLore={manualLore} manualEntryIds={manualEntryIds}
            onManualLore={entry => setManualEntryIds(values => values.includes(entry) ? values.filter(value => value !== entry) : [...values, entry])}
            preview={preview} model={previewModel} onModel={setPreviewModel} shortcuts={shortcuts} onShortcut={id => setShortcuts(values => values.includes(id) ? values.filter(value => value !== id) : [...values, id])} />
        </footer>
      </div>
      {settingsOpen && <ChatReadingSettings title={title} character={character} description={characterDetail} preview={preview}
        album={album} onAlbumRefresh={refreshAlbum} options={reading} onOptions={setReading} balance={balance} balanceUnavailable={balanceUnavailable} answerPrice={answerPrice} onClose={() => setSettingsOpen(false)} />}
    </div>
    {creditDialog && <CreditShortageDialog onClose={() => setCreditDialog(false)} />}
    {preview && previewAction && <Dialog title={previewActionCopy[previewAction.kind].title} onClose={() => setPreviewAction(null)}>
      <p>{previewActionCopy[previewAction.kind].detail}</p>
      <div className={styles.confirmActions}>
        <button type="button" className={styles.button} onClick={() => setPreviewAction(null)}>취소</button>
        <button type="button" className={`${styles.button} ${styles.primary}`} onClick={confirmPreviewAction}>{previewActionCopy[previewAction.kind].label}</button>
      </div>
    </Dialog>}
  </div>;
}

function ChatRoute() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const preview = id === "demo-archive" && params.get("design") === "v2";
  return <ChatContent key={`${id}:${preview}`} id={id} preview={preview} startChoice={params.get("start")} fromAccount={params.get("from") === "account"} />;
}

export default function ChatPage() { return <Suspense><ChatRoute /></Suspense>; }
