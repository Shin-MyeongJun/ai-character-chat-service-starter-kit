"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass, House, Menu, MessageCircle, PanelLeftClose, PanelLeftOpen, PencilLine, Search, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { RecentConversations } from "@/components/recent-conversations";
import { getMe, logout } from "@/lib/api";

const SIDEBAR_STATE_KEY = "moseori_sidebar_open";

export function SiteHeader() {
  const path = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [authError, setAuthError] = useState("");
  const activeChatId = path.startsWith("/chats/") ? path.slice("/chats/".length) : undefined;

  useEffect(() => {
    setSidebarOpen(localStorage.getItem(SIDEBAR_STATE_KEY) === "true");
    void getMe().then(() => setSignedIn(true)).catch(() => setSignedIn(false));
  }, []);

  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    try { await logout(); setSignedIn(false); setMobileMenuOpen(false); setAuthError(""); }
    catch { setAuthError("로그아웃에 실패했어요. 다시 시도해 주세요."); }
    finally { setSigningOut(false); }
  }

  function toggleSidebar() {
    setSidebarOpen((current) => {
      localStorage.setItem(SIDEBAR_STATE_KEY, String(!current));
      return !current;
    });
  }

  return <>
    <header className={`site-header ${sidebarOpen ? "sidebar-open" : "sidebar-collapsed"}`}>
      <div className="sidebar-shell">
        <div className="sidebar-head">
          <Link className="sidebar-brand" href="/" aria-label="모서리 홈"><span className="brand-mark">✳</span><span className="sidebar-brand-name">모서리</span></Link>
          <button className="sidebar-toggle" type="button" aria-label={sidebarOpen ? "내 대화 사이드바 접기" : "내 대화 사이드바 펼치기"} aria-controls="recent-conversations-panel" aria-expanded={sidebarOpen} onClick={toggleSidebar}>
            {sidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
          </button>
        </div>
        <div id="recent-conversations-panel" className="sidebar-panel"><RecentConversations activeId={activeChatId} /></div>
      </div>
      <div className="topbar-inner">
        <nav className="desktop-nav" aria-label="주요 메뉴">
          <Link className={path === "/" ? "active" : ""} href="/"><House size={17} /> 발견</Link>
          <Link className={path === "/explore" ? "active" : ""} href="/explore"><Compass size={17} /> 둘러보기</Link>
          <Link href="/studio"><PencilLine size={17} /> 제작 스튜디오</Link>
        </nav>
        <div className="header-actions">
          <Link className="header-search" href="/explore"><Search size={18} /><span>작품 검색</span></Link>
          {signedIn ? <button className="header-login" type="button" disabled={signingOut} onClick={() => void signOut()}><UserRound size={18} /><span>{signingOut ? "로그아웃 중" : "로그아웃"}</span></button> : <Link className="header-login" href="/login"><UserRound size={18} /><span>로그인</span></Link>}
        </div>
      </div>
      <div className="mobile-header">
        <button className="icon-button menu-button" type="button" aria-label="메뉴 열기" aria-expanded={mobileMenuOpen} onClick={() => setMobileMenuOpen(!mobileMenuOpen)}><Menu size={22} /></button>
        <Link className="brand" href="/" aria-label="모서리 홈"><span className="brand-mark">✳</span><span>모서리</span></Link>
        <Link className="mobile-search" href="/explore" aria-label="작품 검색"><Search size={21} /></Link>
      </div>
    </header>
    {authError && <p className="inline-notice" role="alert">{authError}</p>}
    {mobileMenuOpen && <div className="mobile-menu"><Link href="/" onClick={() => setMobileMenuOpen(false)}>발견</Link><Link href="/explore" onClick={() => setMobileMenuOpen(false)}>둘러보기</Link><Link href="/studio" onClick={() => setMobileMenuOpen(false)}>제작 스튜디오</Link><Link href="/chats" onClick={() => setMobileMenuOpen(false)}>내 대화</Link>{signedIn ? <button type="button" onClick={() => void signOut()}>로그아웃</button> : <Link href="/login" onClick={() => setMobileMenuOpen(false)}>로그인</Link>}</div>}
    <nav className="bottom-nav" aria-label="모바일 메뉴">
      <Link href="/" className={path === "/" ? "active" : ""}><Compass size={21} /><span>발견</span></Link>
      <Link href="/explore" className={path === "/explore" ? "active" : ""}><Search size={21} /><span>둘러보기</span></Link>
      <Link href="/chats" className={path.startsWith("/chats") ? "active" : ""}><MessageCircle size={21} /><span>내 대화</span></Link>
      {signedIn ? <button type="button" onClick={() => void signOut()}><UserRound size={21} /><span>로그아웃</span></button> : <Link href="/login" className={path === "/login" ? "active" : ""}><UserRound size={21} /><span>로그인</span></Link>}
    </nav>
  </>;
}
