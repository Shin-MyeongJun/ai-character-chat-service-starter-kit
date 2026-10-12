import { isDemoWork } from "./works";

export type RecentChat = {
  id: string;
  title: string;
  lastMessage?: string;
  updatedAt?: number;
  imageUrl?: string;
  color?: string;
  accent?: string;
  symbol?: string;
};

export const RECENT_CHATS_KEY = "moseori_recent_chats";
export const RECENT_CHATS_EVENT = "moseori:recent-chats-updated";
export const AUTH_CHANGED_KEY = "moseori_auth_changed";
let currentOwner: string | null = null;

export function setRecentChatOwner(owner: string | null): void {
  if (currentOwner === owner) return;
  currentOwner = owner;
  if (typeof window !== "undefined") window.dispatchEvent(new Event(RECENT_CHATS_EVENT));
}

function storageKey(owner: string | null): string {
  return `${RECENT_CHATS_KEY}:v2:${owner ? `user:${owner}` : "demo"}`;
}

function readStoredChats(key: string): RecentChat[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is RecentChat =>
      item !== null && typeof item === "object" && typeof item.id === "string" && typeof item.title === "string"
    ).slice(0, 20);
  } catch {
    return [];
  }
}

export function readRecentChats(owner: string | null = currentOwner): RecentChat[] {
  // Only demo rows have a known scope in the old shared cache. Never assign
  // legacy real conversations to whichever account happens to log in next.
  const demos = readStoredChats(storageKey(null));
  const legacyDemos = readStoredChats(RECENT_CHATS_KEY).filter(item => isDemoWork(item.id));
  const owned = owner ? readStoredChats(storageKey(owner)) : [];
  const rows = new Map<string, RecentChat>();
  for (const item of [...legacyDemos, ...demos, ...owned]) rows.set(item.id, item);
  return [...rows.values()].sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0)).slice(0, 20);
}

export function upsertRecentChat(next: RecentChat, owner: string | null = currentOwner): void {
  const demo = isDemoWork(next.id);
  if (!demo && !owner) return;
  const key = storageKey(demo ? null : owner);
  const saved = readStoredChats(key);
  const previous = saved.find((item) => item.id === next.id);
  const merged = { ...previous, ...next, updatedAt: Date.now() };
  localStorage.setItem(key, JSON.stringify([merged, ...saved.filter((item) => item.id !== next.id)].slice(0, 20)));
  window.dispatchEvent(new Event(RECENT_CHATS_EVENT));
}

export function updateRecentChatMessage(id: string, lastMessage: string, owner: string | null = currentOwner): void {
  const previous = readRecentChats(owner).find((item) => item.id === id);
  if (previous) upsertRecentChat({ ...previous, lastMessage }, owner);
}
