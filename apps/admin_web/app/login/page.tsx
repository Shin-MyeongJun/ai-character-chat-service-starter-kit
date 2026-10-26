import { Suspense } from "react";
import { LoginForm } from "@/components/login-form";
export default function Page() { return <Suspense fallback={<p className="boot-state">로그인 화면 준비 중…</p>}><LoginForm /></Suspense>; }
