"use client";
import { useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login, ApiError, errorMessage } from "@/lib/api";
import { safeReturnPath } from "@/lib/filters";
import { Brand, Button, Input } from "./ui";
export function LoginForm() {
  const router = useRouter(); const query = useSearchParams();
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const values = new FormData(form);
    setBusy(true); setError("");
    try { await login(String(values.get("email")), String(values.get("password"))); form.reset(); router.replace(safeReturnPath(query.get("returnTo"))); }
    catch (cause) {
      setError(cause instanceof ApiError && cause.code === "invalid_credentials" ? "이메일 또는 비밀번호를 확인해 주세요." : cause instanceof ApiError && cause.status === 422 ? "이메일과 비밀번호 입력 형식을 확인해 주세요. 비밀번호는 12~128자입니다." : errorMessage(cause));
      setBusy(false);
    }
  }
  return <main className="login-layout"><section className="login-story"><Brand /><div><h1>운영에 필요한 기록을,<br />명확하게.</h1><p>Studio 관리자 웹</p><p>생성 프롬프트를 검색하고<br />기록된 원문을 확인합니다.</p></div><small>STUDIO · ADMIN</small></section>
    <section className="login-panel"><form className="login-form" onSubmit={submit} aria-busy={busy}>
      <h2>관리자 로그인</h2><p className="login-intro">관리자 계정으로 로그인해 주세요.</p>
      {query.get("reason") === "expired" && <p className="notice" role="status">세션이 만료되었거나 유효하지 않습니다. 다시 로그인해 주세요.</p>}
      <label htmlFor="email">이메일</label><Input id="email" name="email" type="email" autoComplete="username" required maxLength={254} placeholder="admin@example.com" disabled={busy} />
      <label htmlFor="password">비밀번호</label><Input id="password" name="password" type="password" autoComplete="current-password" required minLength={12} maxLength={128} disabled={busy} aria-describedby={error ? "login-error" : undefined} />
      {error && <p id="login-error" className="error-text" role="alert">{error}</p>}
      <Button variant="primary" type="submit" disabled={busy}>{busy ? "로그인 중…" : "로그인"}</Button>
      <p className="fine-print">관리자 권한이 있는 계정만 이용할 수 있습니다.</p>
    </form></section></main>;
}
