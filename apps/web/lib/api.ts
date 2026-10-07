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
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

let csrfToken: string | null = null;
let csrfPromise: Promise<string> | null = null;

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

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
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
    if (code === "csrf_failed") csrfToken = null;
    throw new ApiError(response.status, code, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const getPublishedWork = (id: string) => request<PublishedWork>(`/products/${encodeURIComponent(id)}`);
export const startConversation = (productId: string, startSetId: string | null) =>
  request<{ id: string }>("/conversations", { method: "POST", body: JSON.stringify({ product_id: productId, start_set_id: startSetId }) });
export const getConversationStart = (id: string) => request<ConversationStart>(`/conversations/${encodeURIComponent(id)}/start`);
export const listMessages = (id: string, cursor?: string) =>
  request<{ items: ChatMessage[]; next_cursor: string | null }>(`/conversations/${encodeURIComponent(id)}/messages?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
export const createMessage = (id: string, content: string, requestKey: string) =>
  request<ChatMessage>(`/conversations/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify({ request_key: requestKey, content }) });
export const generateAnswer = (id: string, message: ChatMessage, productCharacterId: string, requestKey: string) =>
  request<Answer>(`/conversations/${encodeURIComponent(id)}/answers`, { method: "POST", body: JSON.stringify({ request_key: requestKey, input_message_id: message.id, expected_revision: message.revision, product_character_id: productCharacterId }) });
export const login = (email: string, password: string) =>
  request<{ id: string; email: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const getMe = () => request<{ id: string; email: string }>("/auth/me");
