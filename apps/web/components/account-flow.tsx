"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, LockKeyhole, Mail } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { ApiError, register, resendVerification, requestPasswordReset, resetPassword, verifyEmail } from "@/lib/api";

type Flow = "register" | "verify" | "forgot" | "reset";
const labels: Record<Flow, { title: string; intro: string; button: string }> = {
  register: { title: "계정 만들기", intro: "가입 후 이메일 인증을 완료해 주세요.", button: "가입하고 인증 메일 받기" },
  verify: { title: "이메일 인증", intro: "메일 링크에서 열었다면 인증 코드가 자동으로 준비됩니다.", button: "이메일 인증하기" },
  forgot: { title: "비밀번호 재설정", intro: "계정의 이메일로 재설정 링크를 보냅니다.", button: "재설정 메일 받기" },
  reset: { title: "새 비밀번호", intro: "메일의 링크로 열어 새 비밀번호를 입력해 주세요.", button: "비밀번호 변경하기" },
};

export function AccountFlow({ flow }: { flow: Flow }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  useEffect(() => {
    if (flow !== "verify" && flow !== "reset") return;
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const capturedToken = fragment.get("token");
    if (capturedToken) setToken(capturedToken);
    // Remove the one-time token from visible browser history after capture.
    if (fragment.has("token")) history.replaceState(null, "", window.location.pathname);
  }, [flow]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setDone("");
    try {
      if (flow === "register") await register(email, password);
      else if (flow === "verify") await verifyEmail(token);
      else if (flow === "forgot") await requestPasswordReset(email);
      else await resetPassword(token, password);
      setDone(flow === "register" || flow === "forgot" ? "요청을 처리했습니다. 이메일을 확인해 주세요." : flow === "verify" ? "이메일 인증이 완료되었습니다. 로그인해 주세요." : "비밀번호를 변경했습니다. 다시 로그인해 주세요.");
      setPassword(""); setToken("");
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === "rate_limited" ? "요청이 많아요. 잠시 후 다시 시도해 주세요." : "요청을 완료하지 못했어요. 입력과 서버 연결을 확인해 주세요.");
    } finally { setBusy(false); }
  }

  async function resend() {
    if (!email) { setError("인증 메일을 받을 이메일을 입력해 주세요."); return; }
    setBusy(true); setError("");
    try { await resendVerification(email); setDone("요청을 처리했습니다. 이메일을 확인해 주세요."); }
    catch { setError("메일을 보내지 못했어요. 잠시 후 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }

  return <><SiteHeader /><main className="auth-page"><div className="auth-art"><span>✳</span><p>이야기를 이어갈<br />준비를 해볼까요?</p></div><div className="auth-form-wrap"><form className="auth-form" onSubmit={submit}>
    <span className="section-kicker">ACCOUNT</span><h1>{labels[flow].title}</h1><p>{labels[flow].intro}</p>
    {(flow === "register" || flow === "forgot" || flow === "verify") && <label><span>이메일{flow === "verify" ? " · 재발송 시 입력" : ""}</span><div className="field"><Mail size={19} /><input type="email" required={flow !== "verify"} autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com" /></div></label>}
    {(flow === "register" || flow === "reset") && <label><span>비밀번호 · 12자 이상</span><div className="field"><LockKeyhole size={19} /><input type="password" minLength={12} maxLength={128} required autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /></div></label>}
    {(flow === "verify" || flow === "reset") && !token && !done && <p className="inline-notice" role="alert">유효한 메일 링크에서 다시 열어 주세요.</p>}
    {error && <p className="inline-notice" role="alert">{error}</p>}{done && <p role="status">{done}</p>}
    <button className="button button-primary" disabled={busy || !!done || ((flow === "verify" || flow === "reset") && !token)} type="submit">{busy ? "처리 중..." : labels[flow].button}<ArrowRight size={18} /></button>
    {flow === "verify" && <button className="text-link" type="button" disabled={busy} onClick={resend}>인증 메일 다시 받기</button>}
    <Link className="text-link" href="/login">로그인으로 돌아가기</Link>
  </form></div></main></>;
}
