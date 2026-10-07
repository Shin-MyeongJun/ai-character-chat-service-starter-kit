"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { ConversationAvatar, useRecentConversations } from "@/components/recent-conversations";

export default function ChatsList() {
  const recent = useRecentConversations();
  return <><SiteHeader /><main className="page-container chats-list-page"><div className="page-intro"><span className="section-kicker">YOUR CONVERSATIONS</span><h1>이어갈 이야기</h1><p>최근 이 브라우저에서 시작한 대화입니다.</p></div><div className="inline-notice">서버의 내 대화 목록 API가 아직 없어 이 브라우저에서 시작한 대화만 표시합니다. 다른 기기에서는 복원되지 않습니다.</div>{recent.length ? <div className="recent-list">{recent.map((item) => <Link href={`/chats/${item.id}`} key={item.id}><ConversationAvatar chat={item} /><span className="recent-list-text"><strong>{item.title}</strong><small>{item.lastMessage || "대화를 시작해 보세요"}</small></span><ArrowRight size={19} /></Link>)}</div> : <div className="empty-state"><span>✳</span><h2>아직 시작한 대화가 없어요</h2><p>끌리는 작품을 골라 첫 장면을 열어보세요.</p><Link className="button button-primary" href="/explore">작품 찾기 <ArrowRight size={18} /></Link></div>}</main></>;
}
