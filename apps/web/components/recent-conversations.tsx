"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { demoWorkById } from "@/lib/works";
import { AUTH_CHANGED_KEY, readRecentChats, RECENT_CHATS_EVENT, type RecentChat } from "@/lib/recent-chats";
import { getMe, listOwnedConversations, type OwnedConversation } from "@/lib/api";

export function ConversationAvatar({ chat }: { chat: RecentChat }) {
  const work = demoWorkById(chat.id);
  const color = chat.color ?? work?.color ?? "#34304b";
  const accent = chat.accent ?? work?.accent ?? "#d7aa80";
  return <span className="conversation-avatar" style={{ "--avatar-base": color, "--avatar-accent": accent } as React.CSSProperties} aria-hidden="true">
    {chat.imageUrl || work?.coverImage ? <img src={chat.imageUrl ?? work?.coverImage} alt="" /> : <span>{chat.symbol ?? work?.symbol ?? "✦"}</span>}
  </span>;
}

export function useConversationDirectory() {
  const [local, setLocal] = useState<RecentChat[]>([]);
  const [server, setServer] = useState<OwnedConversation[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // Share the lifetime and synchronous request lock across refreshes and pages.
  const requests = useRef<{
    active: boolean;
    sequence: number;
    busy: boolean;
    cursor: { createdAt: string; id: string } | null;
  }>({ active: false, sequence: 0, busy: true, cursor: null });
  useEffect(() => {
    const request = requests.current;
    request.active = true;
    const refresh = () => { if (request.active) setLocal(readRecentChats()); };
    const verify = async () => {
      if (!request.active) return;
      const current = ++request.sequence;
      const isCurrent = () => request.active && current === request.sequence;
      request.busy = true;
      request.cursor = null;
      setLocal(readRecentChats(null)); setServer([]); setHasMore(false); setLoading(true); setError("");
      try {
        await getMe();
        if (!isCurrent()) return;
        const page = await listOwnedConversations();
        if (isCurrent()) {
          setServer(page.items);
          request.cursor = page.next_cursor_id && page.next_cursor_created_at ? { createdAt: page.next_cursor_created_at, id: page.next_cursor_id } : null;
          setHasMore(!!request.cursor);
        }
      } catch (cause) {
        if (isCurrent() && !(cause instanceof Error && "status" in cause && cause.status === 401)) setError("대화 목록을 불러오지 못했어요.");
      } finally {
        if (isCurrent()) { request.busy = false; setLoading(false); refresh(); }
      }
    };
    const storage = (event: StorageEvent) => {
      if (event.key === AUTH_CHANGED_KEY || event.key === null) void verify();
      else refresh();
    };
    void verify();
    window.addEventListener(RECENT_CHATS_EVENT, refresh);
    window.addEventListener(AUTH_CHANGED_KEY, verify);
    window.addEventListener("storage", storage);
    window.addEventListener("focus", verify);
    return () => { request.active = false; request.sequence++; window.removeEventListener(RECENT_CHATS_EVENT, refresh); window.removeEventListener(AUTH_CHANGED_KEY, verify); window.removeEventListener("storage", storage); window.removeEventListener("focus", verify); };
  }, []);
  async function loadMore() {
    const request = requests.current;
    if (!request.active || !request.cursor || request.busy) return;
    const current = request.sequence;
    const isCurrent = () => request.active && current === request.sequence;
    request.busy = true;
    setLoading(true); setError("");
    try {
      const page = await listOwnedConversations(request.cursor);
      if (!isCurrent()) return;
      setServer(current => {
        const rows = new Map(current.map(row => [row.id, row]));
        for (const row of page.items) rows.set(row.id, row);
        return [...rows.values()];
      });
      request.cursor = page.next_cursor_id && page.next_cursor_created_at ? { createdAt: page.next_cursor_created_at, id: page.next_cursor_id } : null;
      setHasMore(!!request.cursor);
    } catch { if (isCurrent()) setError("다음 대화 목록을 불러오지 못했어요."); }
    finally { if (isCurrent()) { request.busy = false; setLoading(false); } }
  }
  const saved = new Map(local.map(item => [item.id, item]));
  const demos = local.filter(item => item.id.startsWith("demo-"));
  const recent = [...server.map(row => {
    const prior = saved.get(row.id);
    return { ...prior, id: row.id, title: row.title || "대화", lastMessage: row.last_message ?? prior?.lastMessage ?? "", updatedAt: Date.parse(row.last_activity_at ?? row.created_at) };
  }), ...demos];
  return { recent, loadMore, hasMore, loading, error };
}

export function useRecentConversations() { return useConversationDirectory().recent; }

export function RecentConversations({ activeId }: { activeId?: string }) {
  const { recent, loading, error } = useConversationDirectory();
  return <section className="sidebar-conversations" aria-label="내 대화">
    <div className="sidebar-conversations-heading"><span>내 대화</span><Link href="/chats" aria-label="내 대화 전체 보기"><ArrowRight size={17} /></Link></div>
    <div className="sidebar-conversations-list">
      {recent.length ? recent.map((chat) => <Link key={chat.id} href={`/chats/${chat.id}`} className={`conversation-link ${activeId === chat.id ? "active" : ""}`} aria-current={activeId === chat.id ? "page" : undefined}>
        <ConversationAvatar chat={chat} />
        <span className="conversation-link-text"><strong>{chat.title}</strong><small>{chat.lastMessage || "대화를 시작해 보세요"}</small></span>
      </Link>) : <p className="sidebar-conversations-empty" role="status">{loading ? "대화를 확인하는 중…" : error || <>아직 시작한 대화가 없어요.<br />마음에 드는 작품을 골라보세요.</>}</p>}
    </div>
    <span className="sidebar-conversations-note">서버 대화 · 브라우저 시연 대화</span>
  </section>;
}
