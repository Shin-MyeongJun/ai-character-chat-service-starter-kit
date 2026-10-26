"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { request, authDestination, errorMessage, authTabId } from "@/lib/api";
import { defaults, serializeFilters } from "@/lib/filters";
import { promptEndpoint, type AuthUser, type PromptPage } from "@/lib/contracts";
import { Brand } from "./ui";
import { QueryState } from "./query-state";
import { LogoutButton } from "./logout-button";

export function AdminShell({ children }: { children: React.ReactNode }) {
  const router = useRouter(); const path = usePathname(); const query = useSearchParams().toString();
  const [user, setUser] = useState<AuthUser | null>(null); const [error, setError] = useState(""); const [attempt, retry] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setUser(null); setError("");
    (async () => {
      try {
        const identity = await request<AuthUser>("/auth/me", { signal: controller.signal });
        // No /admin/session exists. A successful existing admin read is the server authority.
        await request<PromptPage>(`${promptEndpoint}?${serializeFilters({ ...defaults(), page_size: 1 })}`, { signal: controller.signal });
        if (active) setUser(identity);
      } catch (cause) {
        if (!active) return;
        const destination = authDestination(cause, path + (query ? `?${query}` : ""));
        if (destination) router.replace(destination); else setError(errorMessage(cause));
      }
    })();
    return () => { active = false; controller.abort(); };
    // Revalidate on route changes; search results themselves are independently authorized.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, attempt, router]);
  useEffect(() => {
    const channel = new BroadcastChannel("studio-admin-auth");
    channel.onmessage = event => {
      if (event.data?.source === authTabId) return;
      if (event.data?.type === "logout") { setUser(null); router.replace("/login?reason=expired"); }
      if (event.data?.type === "login") { setUser(null); retry(x => x + 1); }
    };
    const onPageShow = (event: PageTransitionEvent) => { if (event.persisted) { setUser(null); retry(x => x + 1); } };
    window.addEventListener("pageshow", onPageShow);
    return () => { channel.close(); window.removeEventListener("pageshow", onPageShow); };
  }, [router]);
  return <div className="admin-layout">
    <a className="skip-link" href="#main">본문으로 건너뛰기</a>
    <aside className="sidebar"><Brand /><div className="sidebar-divider" /><p className="sidebar-label">관리자 도구</p>
      <nav aria-label="관리자 메뉴"><Link prefetch={false} href="/generation-prompts" aria-current="page" className="nav-current">생성 프롬프트</Link></nav>
      <div className="sidebar-account">{user && <><strong>운영 관리자</strong><p title={user.email}>{user.email}</p></>}<LogoutButton /></div>
    </aside>
    <div className="workspace"><header className="topbar"><span>관리자 <span className="slash">/</span> <strong>생성 프롬프트</strong></span><span>모든 시각은 서울 기준 (UTC+9)</span></header>
      <main id="main" className="main">{user ? children : <QueryState title={error ? "관리자 접근을 확인하지 못했습니다." : "관리자 권한 확인 중…"} description={error || "서버에서 계정과 관리자 접근 권한을 확인하고 있습니다."} loading={!error} retry={error ? () => retry(x => x + 1) : undefined} />}</main>
    </div>
  </div>;
}
