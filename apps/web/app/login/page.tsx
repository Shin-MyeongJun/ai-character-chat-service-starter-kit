"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ArrowRight, LockKeyhole, Mail } from "lucide-react";
import { ApiError, login } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      await login(email, password);
      const destination = params.get("next") ?? "/";
      router.replace(destination.startsWith("/") && !destination.startsWith("//") ? destination : "/");
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === "invalid_credentials" ? "이메일과 비밀번호를 확인해 주세요." : "로그인할 수 없어요. API 연결과 인증 설정을 확인해 주세요.");
    } finally { setBusy(false); }
  }
  return <main id="user-content" tabIndex={-1} className="auth-page login-page"><div className="auth-art"><span>✳</span><p>모든 이야기는<br />당신이 돌아오기를<br />기다리고 있어요.</p></div><div className="auth-form-wrap"><form className="auth-form" onSubmit={submit}><span className="section-kicker">WELCOME BACK</span><h1>다시 오셨군요.</h1><p>계속하고 싶은 이야기가 기다리고 있어요.</p><label><span>이메일</span><div className="field"><Mail size={19} /><input type="email" required autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></div></label><label><span>비밀번호</span><div className="field"><LockKeyhole size={19} /><input type="password" required autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호" /></div></label>{error && <p className="inline-notice" role="alert">{error}</p>}<button className="button button-primary" disabled={busy} type="submit">{busy ? "로그인 중..." : "로그인"}<ArrowRight size={18} /></button><Link className="text-link" href="/register">새 계정 만들기</Link><Link className="text-link" href="/forgot-password">비밀번호를 잊으셨나요?</Link><Link className="text-link" href="/">홈으로 돌아가기</Link></form></div></main>;
}

export default function LoginPage() { return <Suspense><LoginForm /></Suspense>; }
