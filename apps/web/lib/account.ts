import { getCreditBalance, getMe, listOwnedConversations, request, type AuthUser, type CreditBalance, type OwnedConversation } from "./api";

export type OwnedProduct = { id: string; title: string; description: string | null; visibility: string; status: string; has_publication?: boolean; created_at: string; updated_at: string };
export type Resource<T> = { status: "loading" | "ready" | "error"; data: T; error?: string };
export type OrderStatus = "pending" | "succeeded" | "failed" | "uncertain";
export type Order = { id: string; credits: number; amount: number; createdAt: string; status: OrderStatus };
export type LedgerEntry = { id: string; date: string; kind: "사용" | "획득"; title: string; credits: number };
export type CreditTransaction = { id: string; operation: string; amount: number; free_amount: number | null; paid_amount: number | null; created_at: string };
export type CreditHistory = { items: CreditTransaction[]; next_cursor_created_at: string | null; next_cursor_id: string | null };
/** Send movement direction before server pagination; zero adjustments remain in all history. */
export function listCreditHistory(start?: string, cursor?: { createdAt: string; id: string }, direction?: "usage" | "acquisition") {
  const query = new URLSearchParams({ limit: "50" });
  if (start) query.set("start", start);
  if (direction) query.set("direction", direction);
  if (cursor) { query.set("cursor_created_at", cursor.createdAt); query.set("cursor_id", cursor.id); }
  return request<CreditHistory>(`/account/credits/transactions?${query}`);
}
export type AccountPreview = { user: AuthUser; balance: CreditBalance; conversations: OwnedConversation[]; products: OwnedProduct[]; orders: Order[]; ledger: LedgerEntry[]; state?: "empty" | "loading" | "error" | "credit" };
export function validAccountSection(parts: string[], preview = false) {
  return !parts.length || (parts.length === 1 && ["settings", "works", "wallet", "topup", "purchases", "checkout", ...(preview ? ["chat"] : [])].includes(parts[0])) || (parts.length === 2 && parts[0] === "purchases") || (parts.length === 3 && parts[0] === "purchases" && ["result", "recheck"].includes(parts[2]));
}
export const formatCredit = (value: number) => value.toLocaleString("ko-KR");
export const formatDate = (value: string) => new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
export const orderLabels: Record<OrderStatus, string> = { pending: "◷ 확인 중", succeeded: "✓ 완료", failed: "! 실패", uncertain: "◷ 미확정" };
// A lookup never infers payment/fulfillment from navigation, elapsed time or retries.
export const recheckPreviewOrder = (order: Order): Order => ({ ...order, status: order.status === "succeeded" ? "succeeded" : "uncertain" });
export function filterOrders(orders: Order[], status: string, days: number, now = Date.now()) {
  return orders.filter(order => (status === "전체" || (status === "확인 중" ? ["pending", "uncertain"].includes(order.status) : status === "완료" ? order.status === "succeeded" : order.status === "failed")) && (!days || now - new Date(order.createdAt).getTime() <= days * 86400000));
}
/** Search the entire owner scope on the server while retaining the array helper contract. */
export async function listOwnedProducts(search = ""): Promise<OwnedProduct[]> {
  const items: OwnedProduct[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await request<OwnedProduct[]>(`/products/mine?offset=${offset}&limit=100${search ? `&search=${encodeURIComponent(search)}` : ""}`);
    items.push(...page);
    if (page.length < 100) return items;
  }
}
export async function readAccountOverview() {
  // Totals are independently aggregated by each owning module.
  const user = await getMe();
  // Keep a failed balance separate from a zero balance, and preserve partial results.
  const [balance, conversations, products, counts] = await Promise.allSettled([getCreditBalance(), listOwnedConversations(), listOwnedProducts(), request<{conversations: number; products: number}>("/account/overview-counts")]);
  return { user, balance, conversations, products, counts };
}
