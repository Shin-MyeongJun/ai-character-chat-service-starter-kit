"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { logout, ApiError, errorMessage } from "@/lib/api";
import { Button } from "./ui";
export function LogoutButton({ label = "로그아웃" }: { label?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    setBusy(true); setError("");
    try { await logout(); router.replace("/login"); router.refresh(); }
    catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) { router.replace("/login?reason=expired"); return; }
      setError(errorMessage(cause)); setBusy(false);
    }
  }
  return <div className="logout"><Button disabled={busy} onClick={submit}>{busy ? "로그아웃 중…" : label}</Button>{error && <p className="error-text" role="alert">{error}</p>}</div>;
}
