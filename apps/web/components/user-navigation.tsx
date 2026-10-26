"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, Compass, MessageCircle, Moon, PanelLeftClose, PanelLeftOpen, PencilLine, Search, Sun, UserRound } from "lucide-react";
import { RecentConversations } from "@/components/recent-conversations";
import { StoryLink, StorySearch } from "@/components/discovery-controls";
import { useUserTheme } from "@/components/user-theme";
import { getMe } from "@/lib/api";
import { AUTH_CHANGED_KEY } from "@/lib/recent-chats";
import styles from "./discovery.module.css";

const SIDEBAR_KEY = "moseori_sidebar_open";
const links = [{ href: "/", label: "발견", icon: Compass }, { href: "/explore", label: "둘러보기", icon: Search }, { href: "/chats", label: "내 대화", icon: MessageCircle }];

export function UserNavigation() {
  const path = usePathname();
  const { theme, toggleTheme } = useUserTheme();
  const [open, setOpen] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  const isActive = (href: string) => href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
  const showSidebar = path !== "/login";
  useEffect(() => {
    let active = true;
    let sequence = 0;
    try { setOpen(localStorage.getItem(SIDEBAR_KEY) !== "false"); } catch { /* Keep the expanded layout. */ }
    const verify = async () => {
      const current = ++sequence;
      try { await getMe(); if (active && current === sequence) setSignedIn(true); }
      catch { if (active && current === sequence) setSignedIn(false); }
    };
    const storage = (event: StorageEvent) => { if (event.key === AUTH_CHANGED_KEY || event.key === null) void verify(); };
    void verify();
    window.addEventListener(AUTH_CHANGED_KEY, verify);
    window.addEventListener("storage", storage);
    window.addEventListener("focus", verify);
    return () => { active = false; sequence++; window.removeEventListener(AUTH_CHANGED_KEY, verify); window.removeEventListener("storage", storage); window.removeEventListener("focus", verify); };
  }, []);
  function toggleSidebar() {
    const next = !open;
    setOpen(next);
    try { localStorage.setItem(SIDEBAR_KEY, String(next)); } catch { /* Keep the in-memory preference. */ }
  }
  const account = <Link href="/account" className={styles.account} aria-label="마이페이지"><UserRound size={20} /><span>{signedIn ? "내 계정" : "마이페이지"}</span><ArrowRight size={16} /></Link>;
  return <>
    <a href="#user-content" className={styles.skipLink}>본문으로 이동</a>
    <header className={`user-navigation ${styles.navigation}`} data-sidebar={showSidebar ? open ? "open" : "closed" : "none"}>
      {showSidebar && <aside className={styles.sidebar} aria-label="이야기 메뉴">
        <div className={styles.brandRow}><Link href="/" className={styles.brand} aria-label="모서리 홈"><img src={theme === "dark" ? "/images/brand-dark.svg" : "/images/brand.svg"} alt="" width={28} height={28} /><span>모서리</span></Link><button type="button" className={styles.collapse} onClick={toggleSidebar} aria-expanded={open} aria-controls="user-sidebar-content" aria-label={open ? "사이드바 접기" : "사이드바 펼치기"}>{open ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}</button></div>
        <div id="user-sidebar-content" className={styles.sidebarContent} inert={!open} aria-hidden={!open}>
          <nav className={styles.primaryNav} aria-label="주요 메뉴">{links.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}><Icon size={20} />{label}</Link>)}</nav>
          <RecentConversations activeId={path.startsWith("/chats/") ? path.slice(7) : undefined} />
          <div className={styles.studioEntry}><PencilLine size={20} /><strong>내 이야기를 만들어요</strong><p>캐릭터와 세계를 담는 공간</p><StoryLink href="/studio">제작 스튜디오</StoryLink></div>
          <small className={styles.sidebarNote}>이야기가 시작되는 곳</small>
        </div>
      </aside>}
      <div className={styles.topbar}>
        <Link href="/" className={`${styles.brand} ${showSidebar ? styles.mobileBrand : styles.headerBrand}`} aria-label="모서리 홈"><img src={theme === "dark" ? "/images/brand-dark.svg" : "/images/brand.svg"} alt="" width={28} height={28} /><span>모서리</span></Link>
        <div className={styles.searchSlot}><StorySearch /></div>
        {/* AdultFilter stays absent until the server exposes authoritative permission and filtering. */}
        <button className={styles.themeToggle} type="button" onClick={toggleTheme} aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}>{theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}</button>
        {account}
        <nav className={styles.mobileTabs} aria-label="탐색 메뉴"><Link href="/" aria-current={path === "/" ? "page" : undefined}>발견</Link><Link href="/explore" aria-current={path === "/explore" ? "page" : undefined}>둘러보기</Link></nav>
      </div>
    </header>
    <nav className={styles.bottomNav} aria-label="모바일 메뉴">{[...links, { href: "/studio", label: "스튜디오", icon: PencilLine }, { href: "/account", label: "내 계정", icon: UserRound }].map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}><Icon size={20} /><span>{label}</span></Link>)}</nav>
  </>;
}
