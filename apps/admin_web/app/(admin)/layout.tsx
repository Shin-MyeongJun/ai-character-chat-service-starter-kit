import { Suspense } from "react";
import { AdminShell } from "@/components/admin-shell";
export default function Layout({ children }: { children: React.ReactNode }) { return <Suspense fallback={<p className="boot-state">관리자 화면 준비 중…</p>}><AdminShell>{children}</AdminShell></Suspense>; }
