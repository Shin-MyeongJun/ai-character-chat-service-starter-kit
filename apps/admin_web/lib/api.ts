import type { AuthUser } from "./contracts";
export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); this.name = "ApiError"; }
}
let csrf: string | null = null;
let csrfPending: Promise<string> | null = null;
let refreshPending: Promise<void> | null = null;
const uncertainKey = "studio_admin_refresh_uncertain"; // A boolean only; never tokens or response data.
const lockName = "studio-admin-auth-session";
export const authTabId = typeof window === "undefined" ? "server" : crypto.randomUUID();
function broadcastAuth(type: "login" | "logout") {
  const channel = new BroadcastChannel("studio-admin-auth");
  channel.postMessage({ type, source: authTabId }); channel.close();
}
async function getCsrf(): Promise<string> {
  if (csrf) return csrf;
  csrfPending ??= send<{ csrf_token: string }>("/auth/csrf").then(data => data.csrf_token);
  try { csrf = await csrfPending; return csrf; } finally { csrfPending = null; }
}
async function send<T>(path: string, options: RequestInit = {}, recoverCsrf = true): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(options.method ?? "GET")) headers.set("X-CSRF-Token", await getCsrf());
  const response = await fetch(`/backend${path}`, { ...options, headers, credentials: "include", cache: "no-store" });
  if (!response.ok) {
    // Only extract fixed error codes. Never retain or log error payloads (422 may reflect input).
    let code = `http_${response.status}`;
    try {
      const payload = await response.json();
      code = payload?.error?.code ?? (typeof payload?.detail === "string" ? payload.detail : code);
    } catch { /* Non-JSON proxy errors retain the status. */ }
    if (code === "csrf_failed") {
      csrf = null;
      if (recoverCsrf) return send<T>(path, options, false);
    }
    throw new ApiError(response.status, code);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
async function withSessionLock<T>(callback: () => Promise<T>): Promise<T> {
  if (!navigator.locks) throw new ApiError(401, "session_refresh_unavailable");
  return navigator.locks.request(lockName, callback);
}
async function refresh(): Promise<void> {
  refreshPending ??= withSessionLock(async () => {
    try { await send<AuthUser>("/auth/me"); return; }
    catch (error) { if (!(error instanceof ApiError) || error.status !== 401 || error.code !== "invalid_token") throw error; }
    if (localStorage.getItem(uncertainKey)) throw new ApiError(401, "refresh_uncertain");
    localStorage.setItem(uncertainKey, "1");
    try {
      // Do not inherit an aborted read's signal: rotating refresh must finish once sent.
      await send<AuthUser>("/auth/refresh", { method: "POST" });
      localStorage.removeItem(uncertainKey);
    } catch (error) {
      if (error instanceof ApiError && error.status < 500) localStorage.removeItem(uncertainKey);
      // An ambiguous rotation is never retried, including after reload.
      if (!(error instanceof ApiError) || error.status >= 500) throw new ApiError(401, "refresh_uncertain");
      throw error;
    }
  });
  try { await refreshPending; } finally { refreshPending = null; }
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  try { return await send<T>(path, options); }
  catch (error) {
    if (error instanceof ApiError && error.status === 401 && error.code === "invalid_token" && (!path.startsWith("/auth/") || path === "/auth/me")) {
      await refresh();
      return send<T>(path, options);
    }
    throw error;
  }
}
export async function login(email: string, password: string): Promise<AuthUser> {
  return withSessionLock(async () => {
    const user = await send<AuthUser>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    localStorage.removeItem(uncertainKey);
    csrf = null;
    broadcastAuth("login");
    return user;
  });
}
export async function logout(): Promise<void> {
  await withSessionLock(() => send<void>("/auth/logout", { method: "POST" }));
  csrf = null;
  localStorage.removeItem(uncertainKey);
  broadcastAuth("logout");
}
export function authDestination(error: unknown, currentPath: string): string | null {
  if (!(error instanceof ApiError)) return null;
  if (error.status === 401) return `/login?reason=expired&returnTo=${encodeURIComponent(currentPath)}`;
  if (error.status === 403 && error.code === "forbidden") return "/forbidden";
  return null;
}
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "origin_forbidden") return "관리자 접속 주소가 API 허용 Origin에 등록되지 않았습니다.";
    if (error.status === 422) return "조회 조건을 확인해 주세요. 날짜 범위와 대화 ID 형식이 올바른지 확인해 주세요.";
    if (error.status === 429) return "요청이 많습니다. 잠시 후 다시 시도해 주세요.";
    if (error.code === "auth_not_configured") return "API 인증 설정을 확인해 주세요.";
  }
  return "요청을 처리하지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.";
}
