"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { demoWorkById } from "@/lib/works";
import { readRecentChats, RECENT_CHATS_EVENT, type RecentChat } from "@/lib/recent-chats";

export function ConversationAvatar({ chat }: { chat: RecentChat }) {
  const work = demoWorkById(chat.id);
  const color = chat.color ?? work?.color ?? "#34304b";
  const accent = chat.accent ?? work?.accent ?? "#d7aa80";
  return <span className="conversation-avatar" style={{ "--avatar-base": color, "--avatar-accent": accent } as React.CSSProperties} aria-hidden="true">
    {chat.imageUrl ? <img src={chat.imageUrl} alt="" /> : <span>{chat.symbol ?? work?.symbol ?? "✦"}</span>}
  </span>;
}

export function useRecentConversations() {
  const [recent, setRecent] = useState<RecentChat[]>([]);
  useEffect(() => {
    const refresh = () => setRecent(readRecentChats());
    refresh();
    window.addEventListener(RECENT_CHATS_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => { window.removeEventListener(RECENT_CHATS_EVENT, refresh); window.removeEventListener("storage", refresh); };
  }, []);
  return recent;
}

export function RecentConversations({ activeId }: { activeId?: string }) {
  const recent = useRecentConversations();
  return <section className="sidebar-conversations" aria-label="내 대화">
    <div className="sidebar-conversations-heading"><span>내 대화</span><Link href="/chats" aria-label="내 대화 전체 보기"><ArrowRight size={17} /></Link></div>
    <div className="sidebar-conversations-list">
      {recent.length ? recent.map((chat) => <Link key={chat.id} href={`/chats/${chat.id}`} className={`conversation-link ${activeId === chat.id ? "active" : ""}`} aria-current={activeId === chat.id ? "page" : undefined}>
        <ConversationAvatar chat={chat} />
        <span className="conversation-link-text"><strong>{chat.title}</strong><small>{chat.lastMessage || "대화를 시작해 보세요"}</small></span>
      </Link>) : <p className="sidebar-conversations-empty">아직 시작한 대화가 없어요.<br />마음에 드는 작품을 골라보세요.</p>}
    </div>
    <span className="sidebar-conversations-note">이 브라우저에서 시작한 대화</span>
  </section>;
}
