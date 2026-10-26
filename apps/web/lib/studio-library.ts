import { getMe, request } from "./api";
import { createLoreEntry, type LoreEntry } from "./studio-data";
import { createCharacter, type StudioCharacter } from "./studio-project";

type Cursor = {created_at: string; id: string} | null;
type SourceLink = {serverId?: string; bookId?: string; pending?: boolean; raw?: Record<string, unknown>};
const linkKey = (owner: string, kind: string, localId: string) => `studio-library-v1:${owner}:${kind}:${localId}`;

/** Traverse existing owner endpoints with their full timestamp/ID cursor pair. */
async function pages<T>(path: string, field: string): Promise<T[]> {
  let cursor: Cursor = null;
  const result: T[] = [];
  const seen = new Set<string>();
  do {
    const query = new URLSearchParams({limit: "100"});
    if (cursor) {query.set("cursor_created_at", cursor.created_at); query.set("cursor_id", cursor.id);}
    const page: Record<string, unknown> & {next_cursor: Cursor} = await request(`${path}?${query}`);
    result.push(...page[field] as T[]);
    cursor = page.next_cursor;
    if (cursor && seen.has(cursor.id)) throw new Error("보관함 페이지가 반복돼요. 다시 조회해 주세요.");
    if (cursor) seen.add(cursor.id);
  } while (cursor);
  return result;
}

/** Import server text as independent browser originals, retaining separate server IDs.
 * Unsupported entry modes are reported and skipped; existing browser edits are
 * preserved by the caller. Media in original libraries is not copied by this path.
 */
export async function loadServerLibrary() {
  const owner = await getMe();
  const characters: StudioCharacter[] = [];
  const lorebooks: LoreEntry[] = [];
  let skipped = 0;
  for (const raw of await pages<Record<string, unknown>>("/characters/me", "characters")) {
    const id = `server-original:${owner.id}:character:${raw.id}`;
    characters.push({...createCharacter(), id, name: String(raw.name), persona: String(raw.persona_prompt), introduction: String(raw.description ?? "")});
    localStorage.setItem(linkKey(owner.id, "character", id), JSON.stringify({serverId: raw.id, raw}));
  }
  for (const book of await pages<{id: string; title: string}>("/lorebooks/me", "lorebooks")) {
    for (const raw of await pages<Record<string, unknown>>(`/lorebooks/me/${book.id}/entries`, "entries")) {
      const options = (raw.metadata as Record<string, unknown>)?.activation_options as Record<string, unknown> | undefined;
      if (!["always", "keyword", "manual"].includes(String(raw.activation_type)) || raw.entry_type === "start_set" || raw.match_mode !== "contains" || (options && options.version !== 1)) {skipped++; continue;}
      const id = `server-original:${owner.id}:lore:${raw.id}`;
      const entry: LoreEntry = {...createLoreEntry(), id, title: String(raw.title ?? "이름 없는 로어"), folder: book.title, content: String(raw.content), keywords: raw.key_triggers as string[] ?? [], enabled: Boolean(raw.is_enabled), activation: raw.activation_type as LoreEntry["activation"], priority: Number(raw.priority) >= 100 ? "필수" : Number(raw.priority) >= 75 ? "높음" : Number(raw.priority) >= 50 ? "보통" : "낮음", tokenBudget: Number(raw.token_budget ?? 800), placement: raw.placement === "near_user_message" ? "after" : "before", match: options?.match === "all" ? "all" : "any", scanDepth: Number(options?.scan_depth ?? 9), searchTarget: options?.search_target === "user" ? "user" : "all", partialMatch: options?.partial_match !== false, caseSensitive: options?.case_sensitive === true, order: Number(options?.order ?? 100), exclusiveGroup: String(options?.exclusive_group ?? "")};
      lorebooks.push(entry);
      localStorage.setItem(linkKey(owner.id, "lore", id), JSON.stringify({serverId: raw.id, bookId: book.id, raw}));
    }
  }
  return {characters, lorebooks, skipped};
}

/** Save an explicitly selected original through existing CRUD, never its work copies.
 * New-create response loss is marked uncertain because these legacy APIs have no
 * create request key. Retry must first reconcile via server import; it cannot
 * silently repeat creation. Existing originals retain their visibility/metadata.
 */
export async function saveServerSource(kind: "character" | "lore", row: StudioCharacter | LoreEntry) {
  const owner = await getMe();
  const key = linkKey(owner.id, kind, row.id);
  let link: SourceLink = JSON.parse(localStorage.getItem(key) ?? "null") ?? {};
  if (link.pending) throw new Error("이전 생성 결과를 확인하지 못했어요. 서버 원본 가져오기로 확인한 뒤 편집해 주세요.");
  if (kind === "character") {
    const character = row as StudioCharacter;
    const value = {name: character.name, persona_prompt: [character.persona, character.dialogue, character.relationships].filter(Boolean).join("\n\n"), description: character.introduction || null, visibility: link.raw?.visibility ?? "private", default_model_id: link.raw?.default_model_id ?? null};
    if (!link.serverId) localStorage.setItem(key, JSON.stringify({...link, pending: true}));
    const result = await request<{character: {id: string}}>("/characters", {method: link.serverId ? "PUT" : "POST", body: JSON.stringify({...value, ...(link.serverId ? {character_id: link.serverId} : {tags: character.tags})})});
    localStorage.setItem(key, JSON.stringify({serverId: result.character.id, raw: value}));
    if (character.assets.length) return "텍스트 원본을 저장했어요. 보관함 원본 이미지는 이 경로에서 업로드하지 않으며 작품 저장 시 업로드해요.";
  } else {
    const lore = row as LoreEntry;
    if (!link.bookId) {
      localStorage.setItem(key, JSON.stringify({pending: true}));
      const result = await request<{lorebook: {id: string}}>("/lorebooks", {method: "POST", body: JSON.stringify({title: lore.title, tags: lore.tags})});
      link = {bookId: result.lorebook.id};
      localStorage.setItem(key, JSON.stringify(link));
    }
    const value = {lorebook_id: link.bookId, title: lore.title, content: lore.content, entry_type: link.raw?.entry_type ?? "world", activation_type: lore.activation, key_triggers: lore.keywords.length ? lore.keywords : null, match_mode: "contains", priority: {필수: 100, 높음: 75, 보통: 50, 낮음: 25}[lore.priority], token_budget: lore.tokenBudget, placement: lore.placement === "before" ? "before_history" : "near_user_message", is_enabled: lore.enabled, metadata: {...link.raw?.metadata as object, activation_options: {version: 1, match: lore.match, scan_depth: lore.scanDepth, search_target: lore.searchTarget, partial_match: lore.partialMatch, case_sensitive: lore.caseSensitive, order: lore.order, exclusive_group: lore.exclusiveGroup}}};
    if (!link.serverId) localStorage.setItem(key, JSON.stringify({...link, pending: true}));
    const result = await request<{entry: {id: string}}>("/lorebooks/entries", {method: link.serverId ? "PUT" : "POST", body: JSON.stringify({...value, ...(link.serverId ? {entry_id: link.serverId} : {})})});
    localStorage.setItem(key, JSON.stringify({...link, serverId: result.entry.id, pending: false, raw: value}));
  }
  return "서버 원본을 저장했어요. 기존 작품의 복사본은 독립적으로 유지돼요.";
}
