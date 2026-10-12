"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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
  const [cursor, setCursor] = useState<{ createdAt: string; id: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let sequence = 0;
    const refresh = () => { if (active) setLocal(readRecentChats()); };
    const verify = async () => {
      if (!active) return;
      const current = ++sequence;
      setLocal(readRecentChats(null)); setServer([]); setCursor(null); setLoading(true); setError("");
      try {
        await getMe();
        const page = await listOwnedConversations();
        if (active && current === sequence) {
          setServer(page.items);
          setCursor(page.next_cursor_id && page.next_cursor_created_at ? { createdAt: page.next_cursor_created_at, id: page.next_cursor_id } : null);
        }
      } catch (cause) {
        if (active && current === sequence && !(cause instanceof Error && "status" in cause && cause.status === 401)) setError("대화 목록을 불러오지 못했어요.");
      }
      if (active && current === sequence) { setLoading(false); refresh(); }
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
    return () => { active = false; sequence++; window.removeEventListener(RECENT_CHATS_EVENT, refresh); window.removeEventListener(AUTH_CHANGED_KEY, verify); window.removeEventListener("storage", storage); window.removeEventListener("focus", verify); };
  }, []);
  async function loadMore() {
    if (!cursor || loading) return;
    setLoading(true); setError("");
    try {
      const page = await listOwnedConversations(cursor);
      setServer(current => {
        const rows = new Map(current.map(row => [row.id, row]));
        for (const row of page.items) rows.set(row.id, row);
        return [...rows.values()];
      });
      setCursor(page.next_cursor_id && page.next_cursor_created_at ? { createdAt: page.next_cursor_created_at, id: page.next_cursor_id } : null);
    } catch { setError("다음 대화 목록을 불러오지 못했어요."); }
    finally { setLoading(false); }
  }
  const saved = new Map(local.map(item => [item.id, item]));
  const demos = local.filter(item => item.id.startsWith("demo-"));
  const recent = [...server.map(row => {
    const prior = saved.get(row.id);
    return { ...prior, id: row.id, title: row.title || "대화", lastMessage: row.last_message ?? prior?.lastMessage ?? "", updatedAt: Date.parse(row.created_at) };
  }), ...demos];
  return { recent, loadMore, hasMore: !!cursor, loading, error };
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
    <span className="sidebar-conversations-note">이 브라우저에서 시작한 대화</span>
  </section>;
}
