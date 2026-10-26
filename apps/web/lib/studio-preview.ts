import type { LoreEntry } from "./studio-data";
import { request } from "./api";

export type PreviewMessage = { role: "user" | "character"; text: string };
export type LorePreviewResult = { entry: LoreEntry; included: boolean; reason: string; order?: number | null };
const reasons: Record<string, string> = {included: "적용", disabled: "비활성화", start_scene: "시작 장면", manual_not_selected: "수동 선택 대기", keyword_mismatch: "키워드 조건 불일치", entry_budget_exceeded: "항목 토큰 예산 초과 (UTF-8 바이트 상한 추정)", exclusive_group: "같은 그룹의 우선 항목 적용", semantic_not_supported: "의미 검색 미지원"};

/** Ask the runtime selector to evaluate transient draft values; never simulate an AI reply. */
export async function previewLore(entries: LoreEntry[], messages: PreviewMessage[], manualEntryIds: string[] = []): Promise<LorePreviewResult[]> {
  const result = await request<{items: {id: string; included: boolean; reason: string; order: number | null}[]; ai_called: false}>("/products/studio/lore-diagnostics", {method: "POST", body: JSON.stringify({entries, messages: messages.slice(-100), manual_entry_ids: manualEntryIds})});
  return result.items.map(row => ({entry: entries.find(entry => entry.id === row.id)!, included: row.included, reason: reasons[row.reason] ?? row.reason, order: row.order}));
}
