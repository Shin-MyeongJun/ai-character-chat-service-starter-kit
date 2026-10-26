"use client";
import { useEffect, useState } from "react";
import { ApiError, type AuthUser, type CreditBalance, type OwnedConversation, type CursorPage } from "@/lib/api";
import { readAccountOverview, type AccountPreview, type OwnedProduct, type Resource } from "@/lib/account";
import { AUTH_CHANGED_KEY } from "@/lib/recent-chats";
const loading = <T,>(data: T): Resource<T> => ({ status: "loading", data });
const resource = <T,>(result: PromiseSettledResult<T>, fallback: T): Resource<T> => result.status === "fulfilled" ? { status: "ready", data: result.value } : { status: "error", data: fallback, error: "정보를 불러오지 못했어요. 잠시 후 다시 확인해 주세요." };
/** Load independently failing account resources and exact server totals. */
export function useAccount(preview?: AccountPreview) {
  const [version, setVersion] = useState(0);
  const [session, setSession] = useState<"loading" | "ready" | "guest" | "error">("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [balance, setBalance] = useState<Resource<CreditBalance | null>>(loading(null));
  const [conversations, setConversations] = useState<Resource<CursorPage<OwnedConversation>>>(loading({ items: [], next_cursor_id: null, next_cursor_created_at: null }));
  const [products, setProducts] = useState<Resource<OwnedProduct[]>>(loading([]));
  const [counts, setCounts] = useState<Resource<{conversations: number; products: number} | null>>(loading(null));
  useEffect(() => {
    if (preview) return;
    let active = true;
    setSession("loading"); setUser(null); setBalance(loading(null)); setConversations(loading({ items: [], next_cursor_id: null, next_cursor_created_at: null })); setProducts(loading([])); setCounts(loading(null));
    void readAccountOverview().then(value => {
      if (!active) return;
      setUser(value.user); setSession("ready");
      setBalance(resource(value.balance, null)); setProducts(resource(value.products, []));
      setCounts(resource(value.counts, null));
      setConversations(resource(value.conversations, { items: [], next_cursor_id: null, next_cursor_created_at: null }));
    }).catch(cause => { if (active) setSession(cause instanceof ApiError && cause.status === 401 ? "guest" : "error"); });
    return () => { active = false; };
  }, [preview, version]);
  useEffect(() => {
    if (preview) return;
    const refresh = () => setVersion(value => value + 1);
    const storage = (event: StorageEvent) => { if (event.key === AUTH_CHANGED_KEY || event.key === null) refresh(); };
    window.addEventListener(AUTH_CHANGED_KEY, refresh); window.addEventListener("storage", storage);
    return () => { window.removeEventListener(AUTH_CHANGED_KEY, refresh); window.removeEventListener("storage", storage); };
  }, [preview]);
  if (preview) {
    const status = preview.state === "loading" ? "loading" : preview.state === "error" ? "error" : "ready";
    return { counts: {status, data: {conversations: preview.state === "empty" ? 0 : preview.conversations.length, products: preview.state === "empty" ? 0 : preview.products.length}}, session: "ready" as const, user: preview.user, balance: { status, data: status === "ready" ? preview.balance : null } as Resource<CreditBalance | null>, products: { status, data: preview.state === "empty" ? [] : preview.products } as Resource<OwnedProduct[]>, conversations: { status, data: { items: preview.state === "empty" ? [] : preview.conversations, next_cursor_id: null, next_cursor_created_at: null } } as Resource<CursorPage<OwnedConversation>>, retry: () => setVersion(v => v + 1) };
  }
  return { session, user, balance, conversations, products, counts, retry: () => setVersion(v => v + 1) };
}
