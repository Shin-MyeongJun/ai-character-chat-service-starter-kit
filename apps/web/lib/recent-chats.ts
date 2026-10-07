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

export function readRecentChats(): RecentChat[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(RECENT_CHATS_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is RecentChat =>
      item !== null && typeof item === "object" && typeof item.id === "string" && typeof item.title === "string"
    ).slice(0, 20);
  } catch {
    return [];
  }
}

export function upsertRecentChat(next: RecentChat): void {
  const saved = readRecentChats();
  const previous = saved.find((item) => item.id === next.id);
  const merged = { ...previous, ...next, updatedAt: Date.now() };
  localStorage.setItem(RECENT_CHATS_KEY, JSON.stringify([merged, ...saved.filter((item) => item.id !== next.id)].slice(0, 20)));
  window.dispatchEvent(new Event(RECENT_CHATS_EVENT));
}

export function updateRecentChatMessage(id: string, lastMessage: string): void {
  const previous = readRecentChats().find((item) => item.id === id);
  if (previous) upsertRecentChat({ ...previous, lastMessage });
}
