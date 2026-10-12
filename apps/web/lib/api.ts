import { AUTH_CHANGED_KEY, setRecentChatOwner } from "./recent-chats";

export type AuthUser = { id: string; email: string; email_verified: boolean };
export type StartOption = { id: string; title: string };
export type PublishedWork = {
  product_id: string;
  snapshot_id: string;
  version: number;
  title: string;
  description: string | null;
  start_options: StartOption[];
  model_notice: unknown;
};
export type CatalogItem = { id: string; title: string; description: string | null; snapshot_id: string; created_at: string };
export type CursorPage<T> = { items: T[]; next_cursor_created_at: string | null; next_cursor_id: string | null };
export type OwnedConversation = { id: string; product_id: string; title: string | null; created_at: string; last_message: string | null };
export type CreditBalance = { balance_credit: number; reserved_credit: number; available_credit: number };
export type ConversationStart = {
  opening_mode: string;
  opening_message: string | null;
  start: { title: string; content: string } | null;
  participants: { character_id: string | null; product_character_id: string | null; role_order: number }[];
  primary_product_character_id: string | null;
};
export type ChatMessage = {
  id: string;
  conversation_id: string;
  sender_type: string;
  content: string;
  position: number;
  revision: number;
  product_character_id: string | null;
};
export type Answer = {
  generation_id: string;
  status: string;
  content: string | null;
  error_code: string | null;
  retryable: boolean;
  uncertain: boolean;
  price_credit?: number | null;
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

let csrfToken: string | null = null;
let csrfPromise: Promise<string> | null = null;
let refreshPromise: Promise<void> | null = null;
const REFRESH_UNCERTAIN_KEY = "moseori_refresh_uncertain";

export async function getCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  csrfPromise ??= request<{ csrf_token: string }>("/auth/csrf").then((value) => value.csrf_token);
  try {
    csrfToken = await csrfPromise;
    return csrfToken;
  } finally {
    csrfPromise = null;
  }
}

async function send<T>(path: string, options: RequestInit = {}, recoverCsrf = true): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method)) headers.set("X-CSRF-Token", await getCsrf());
  const response = await fetch(`/backend${path}`, { ...options, headers, credentials: "include", cache: "no-store" });
  if (!response.ok) {
    let detail: unknown;
    try { detail = await response.json(); } catch { detail = null; }
    // The answer endpoint returns a typed generation result for completed failures.
    // Keep its retryable flag so the chat can offer a new attempt for the saved message.
    if (path.endsWith("/answers") && detail && typeof detail === "object" && "generation_id" in detail && "status" in detail) {
      return detail as T;
    }
    const payload = detail as { error?: { code?: string }; detail?: string | { code?: string }; error_code?: string } | null;
    const code = payload?.error?.code ?? payload?.error_code ?? (typeof payload?.detail === "object" ? payload.detail?.code : undefined) ?? `http_${response.status}`;
    const message = typeof payload?.detail === "string" ? payload.detail : code;
    if (code === "csrf_failed") {
      // The server rejected this request before executing the mutation.
      csrfToken = null;
      if (recoverCsrf) return send<T>(path, options, false);
    }
    throw new ApiError(response.status, code, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function refreshSession(): Promise<void> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    // Refresh tokens rotate on every use. A per-tab promise alone is unsafe.
    if (typeof navigator === "undefined" || !navigator.locks) {
      throw new ApiError(401, "session_refresh_unavailable", "다시 로그인해 주세요.");
    }
    await navigator.locks.request("moseori-auth-refresh", async () => {
      // Another tab/request may already have refreshed while we waited.
      try { await send<AuthUser>("/auth/me"); return; }
      catch (cause) {
        if (!(cause instanceof ApiError) || cause.status !== 401 || cause.code !== "invalid_token") throw cause;
      }
      if (localStorage.getItem(REFRESH_UNCERTAIN_KEY)) {
        throw new ApiError(401, "refresh_uncertain", "갱신 결과를 확인할 수 없어 다시 로그인이 필요합니다.");
      }
      // Persist before sending: a closed tab or lost response must not replay
      // an old refresh token and revoke an otherwise valid token family.
      localStorage.setItem(REFRESH_UNCERTAIN_KEY, "1");
      try {
        await send<AuthUser>("/auth/refresh", { method: "POST" });
        localStorage.removeItem(REFRESH_UNCERTAIN_KEY);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status < 500) localStorage.removeItem(REFRESH_UNCERTAIN_KEY);
        throw cause;
      }
    });
  })();
  try { await refreshPromise; }
  finally { refreshPromise = null; }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  try { return await send<T>(path, options); }
  catch (cause) {
    // Credential errors and invalid/revoked sessions are not access expiry.
    if (cause instanceof ApiError && cause.status === 401 && cause.code === "invalid_token" && (!path.startsWith("/auth/") || path === "/auth/me")) {
      try {
        await refreshSession();
        return await send<T>(path, options);
      } catch (refreshError) {
        setRecentChatOwner(null);
        throw refreshError;
      }
    }
    if (cause instanceof ApiError && cause.status === 401) setRecentChatOwner(null);
    throw cause;
  }
}

export async function getPublishedWork(id: string): Promise<PublishedWork> {
  try { return await request<PublishedWork>(`/products/catalog/${encodeURIComponent(id)}`); }
  catch (cause) {
    if (cause instanceof ApiError && cause.status === 404) return request<PublishedWork>(`/products/${encodeURIComponent(id)}`);
    throw cause;
  }
}
function pageQuery(cursor?: { createdAt: string; id: string }): string {
  const query = new URLSearchParams({ limit: "30" });
  if (cursor) { query.set("cursor_created_at", cursor.createdAt); query.set("cursor_id", cursor.id); }
  return query.toString();
}
export const listCatalog = (cursor?: { createdAt: string; id: string }) =>
  request<CursorPage<CatalogItem>>(`/products/catalog?${pageQuery(cursor)}`);
export const listOwnedConversations = (cursor?: { createdAt: string; id: string }) =>
  request<CursorPage<OwnedConversation>>(`/conversations/mine?${pageQuery(cursor)}`);
export const getCreditBalance = () => request<CreditBalance>("/account/credits");
export const startConversation = (productId: string, startSetId: string | null) =>
  request<{ id: string }>("/conversations", { method: "POST", body: JSON.stringify({ product_id: productId, start_set_id: startSetId }) });
export const getConversationStart = (id: string) => request<ConversationStart>(`/conversations/${encodeURIComponent(id)}/start`);
export const listMessages = (id: string, cursor?: string) =>
  request<{ items: ChatMessage[]; next_cursor: string | null }>(`/conversations/${encodeURIComponent(id)}/messages?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
export async function listConversationMessages(id: string): Promise<ChatMessage[]> {
  const messages = new Map<string, ChatMessage>();
  const seen = new Set<string>();
  let cursor: string | undefined;
  do {
    const page = await listMessages(id, cursor);
    for (const message of page.items) messages.set(message.id, message);
    cursor = page.next_cursor ?? undefined;
    if (cursor && seen.has(cursor)) throw new Error("Message cursor did not advance.");
    if (cursor) seen.add(cursor);
  } while (cursor);
  return [...messages.values()].sort((a, b) => a.position - b.position);
}
export const createMessage = (id: string, content: string, requestKey: string) =>
  request<ChatMessage>(`/conversations/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify({ request_key: requestKey, content }) });
export const generateAnswer = (id: string, message: ChatMessage, productCharacterId: string, requestKey: string, signal?: AbortSignal) =>
  request<Answer>(`/conversations/${encodeURIComponent(id)}/answers`, { method: "POST", signal, body: JSON.stringify({ request_key: requestKey, input_message_id: message.id, expected_revision: message.revision, product_character_id: productCharacterId }) });
export async function login(email: string, password: string): Promise<AuthUser> {
  const user = await request<AuthUser>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  localStorage.removeItem(REFRESH_UNCERTAIN_KEY);
  setRecentChatOwner(user.id);
  localStorage.setItem(AUTH_CHANGED_KEY, crypto.randomUUID());
  window.dispatchEvent(new Event(AUTH_CHANGED_KEY));
  return user;
}
export async function getMe(): Promise<AuthUser> {
  const user = await request<AuthUser>("/auth/me");
  setRecentChatOwner(user.id);
  return user;
}

export const register = (email: string, password: string) =>
  request<{ message: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
export const resendVerification = (email: string) =>
  request<{ message: string }>("/auth/email/resend", { method: "POST", body: JSON.stringify({ email }) });
export const verifyEmail = (token: string) =>
  request<AuthUser>("/auth/email/verify", { method: "POST", body: JSON.stringify({ token }) });
export const requestPasswordReset = (email: string) =>
  request<{ message: string }>("/auth/password/reset/request", { method: "POST", body: JSON.stringify({ email }) });
export const resetPassword = (token: string, password: string) =>
  request<void>("/auth/password/reset", { method: "POST", body: JSON.stringify({ token, password }) });
export async function logout(): Promise<void> {
  await request<void>("/auth/logout", { method: "POST" });
  setRecentChatOwner(null);
  localStorage.setItem(AUTH_CHANGED_KEY, crypto.randomUUID());
  window.dispatchEvent(new Event(AUTH_CHANGED_KEY));
}
