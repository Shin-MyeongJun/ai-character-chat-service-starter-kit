import { statuses, type GenerationStatus } from "./contracts";
export type Filters = { date_from: string; date_to: string; conversation_id: string; status: string; page: number; page_size: number };
export const listPath = "/generation-prompts";
export const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function defaults(now = new Date()): Filters {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const from = new Date(`${today}T00:00:00Z`);
  from.setUTCDate(from.getUTCDate() - 6);
  return { date_from: from.toISOString().slice(0, 10), date_to: today, conversation_id: "", status: "", page: 1, page_size: 50 };
}
export function readFilters(query: URLSearchParams, now = new Date()): Filters {
  const base = defaults(now);
  const integer = (key: string, fallback: number, max: number) => {
    const raw = query.get(key);
    return raw && /^\d+$/.test(raw) && Number.isSafeInteger(Number(raw)) && Number(raw) >= 1 && Number(raw) <= max ? Number(raw) : fallback;
  };
  return {
    date_from: query.get("date_from") ?? base.date_from,
    date_to: query.get("date_to") ?? base.date_to,
    conversation_id: query.get("conversation_id") ?? "", status: query.get("status") ?? "",
    page: integer("page", 1, 2147483647), page_size: integer("page_size", 50, 100),
  };
}
export function validateFilters(filters: Filters): string | null {
  const validDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  if (!validDate(filters.date_from) || !validDate(filters.date_to)) return "시작일과 종료일을 올바르게 입력해 주세요.";
  const days = (Date.parse(filters.date_to) - Date.parse(filters.date_from)) / 86400000;
  if (days < 0) return "종료일은 시작일 이후여야 합니다.";
  if (days > 730) return "조회 기간은 시작일과 종료일을 포함해 최대 731일입니다.";
  if (filters.conversation_id && !uuidPattern.test(filters.conversation_id.trim())) return "대화 ID는 UUID 전체를 입력해 주세요.";
  if (filters.status && !Object.hasOwn(statuses, filters.status)) return "지원하지 않는 생성 상태입니다.";
  return null;
}
export function serializeFilters(filters: Filters): string {
  const query = new URLSearchParams({ date_from: filters.date_from, date_to: filters.date_to, page: String(filters.page), page_size: String(filters.page_size) });
  if (filters.conversation_id.trim()) query.set("conversation_id", filters.conversation_id.trim());
  if (filters.status) query.set("status", filters.status as GenerationStatus);
  return query.toString();
}
export function safeReturnPath(value: string | null): string {
  if (!value || /[\\\r\n]/.test(value)) return listPath;
  try {
    const parsed = new URL(value, "https://admin.invalid");
    if (parsed.origin !== "https://admin.invalid" || !/^\/generation-prompts(?:\/[0-9a-f-]{36})?$/i.test(parsed.pathname)) return listPath;
    return parsed.pathname + parsed.search;
  } catch { return listPath; }
}
export function seoulTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  const parts = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(date);
  return parts;
}
