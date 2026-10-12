"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { ConversationAvatar, useConversationDirectory } from "@/components/recent-conversations";

export default function ChatsList() {
  const { recent, loadMore, hasMore, loading, error } = useConversationDirectory();
  return <><SiteHeader /><main id="user-content" tabIndex={-1} className="page-container chats-list-page"><div className="page-intro"><span className="section-kicker">YOUR CONVERSATIONS</span><h1>이어갈 이야기</h1><p>로그인한 계정의 대화와 이 브라우저의 시연 대화입니다.</p></div>{error && <p className="inline-notice" role="alert">{error}</p>}{loading && !recent.length && <p>대화 목록을 불러오는 중...</p>}{recent.length ? <div className="recent-list">{recent.map((item) => <Link href={`/chats/${item.id}`} key={item.id}><ConversationAvatar chat={item} /><span className="recent-list-text"><strong>{item.title}</strong><small>{item.lastMessage || "대화를 시작해 보세요"}</small></span><ArrowRight size={19} /></Link>)}</div> : !loading && <div className="empty-state"><span>✳</span><h2>아직 시작한 대화가 없어요</h2><p>끌리는 작품을 골라 첫 장면을 열어보세요.</p><Link className="button button-primary" href="/explore">작품 찾기 <ArrowRight size={18} /></Link></div>}{hasMore && <button type="button" className="button button-primary" disabled={loading} onClick={loadMore}>{loading ? "불러오는 중..." : "대화 더 보기"}</button>}</main></>;
}
