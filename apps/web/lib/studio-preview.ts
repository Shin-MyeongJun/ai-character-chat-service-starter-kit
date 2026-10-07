import type { LoreEntry } from "./studio-data";

export type PreviewMessage = { role: "user" | "character"; text: string };
export type LorePreviewResult = { entry: LoreEntry; included: boolean; reason: string };

// A local keyword preview only. It does not represent the backend prompt engine.
export function previewLore(entries: LoreEntry[], messages: PreviewMessage[]): LorePreviewResult[] {
  const ranks = { "필수": 0, "높음": 1, "보통": 2, "낮음": 3 };
  const groups = new Set<string>();
  return [...entries].sort((a, b) => ranks[a.priority] - ranks[b.priority] || a.order - b.order).map(entry => {
    let reason = "";
    if (!entry.enabled) reason = "비활성화된 항목";
    else if (!entry.content.trim()) reason = "설정 내용이 비어 있음";
    else if (entry.activation === "manual") reason = "수동 적용 대기";
    else if (entry.activation === "keyword") {
      const history = messages.slice(-entry.scanDepth).filter(message => entry.searchTarget === "all" || message.role === "user");
      const normalize = (text: string) => entry.caseSensitive ? text : text.toLocaleLowerCase();
      const matches = entry.keywords.filter(keyword => history.some(message => {
        const text = normalize(message.text);
        const key = normalize(keyword);
        if (entry.partialMatch) return text.includes(key);
        // Boundaries include Unicode letters, so Korean words stay intact.
        const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        return new RegExp(`(^|[^\\p{L}\\p{N}_])${escaped}(?=$|[^\\p{L}\\p{N}_])`, "u").test(text);
      }));
      if (!entry.keywords.length) reason = "활성화 키워드가 없음";
      else if (entry.match === "all" ? matches.length !== entry.keywords.length : !matches.length) reason = "키워드 조건 불일치";
      else reason = `키워드 감지: ${matches.join(", ")}`;
    } else reason = "항상 적용";
    let included = reason === "항상 적용" || reason.startsWith("키워드 감지:");
    const group = entry.exclusiveGroup.trim();
    if (included && group) {
      if (groups.has(group)) { included = false; reason = "같은 그룹의 우선 항목이 이미 적용됨"; }
      else groups.add(group);
    }
    return { entry, included, reason };
  });
}
