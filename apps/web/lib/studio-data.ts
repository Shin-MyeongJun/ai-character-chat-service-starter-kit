export const STUDIO_STORAGE_KEY = "chat-kit-studio-draft-v1";

export type LoreEntry = {
  id: string;
  sourceId?: string;
  title: string;
  category: "장소" | "세계관" | "인물" | "사건";
  folder: string;
  content: string;
  tags: string[];
  keywords: string[];
  enabled: boolean;
  activation: "keyword" | "always" | "manual";
  match: "any" | "all";
  priority: "필수" | "높음" | "보통" | "낮음";
  scanDepth: number;
  searchTarget: "all" | "user";
  partialMatch: boolean;
  caseSensitive: boolean;
  tokenBudget: number;
  order: number;
  placement: "before" | "after";
  exclusiveGroup: string;
};

export const SAMPLE_LORE: LoreEntry[] = [
  {
    id: "starlight-library", title: "별빛 도서관", category: "장소", folder: "장소와 배경",
    content: "별빛 도서관은 달이 떠 있는 동안에만 열린다.\n책은 기록된 사건을 기억하지만 미래를 알려주지는 않는다.\n방문자는 사서에게 원하는 기록의 이름을 말할 수 있다.\n숨겨진 기록은 관련 사건을 겪기 전에는 공개되지 않는다.",
    tags: ["장소", "학교", "초반부"], keywords: ["도서관", "기록실", "library"],
    enabled: true, activation: "keyword", match: "any", priority: "높음", scanDepth: 9,
    searchTarget: "all", partialMatch: true, caseSensitive: false, tokenBudget: 800,
    order: 150, placement: "before", exclusiveGroup: "도서관 · 시간대",
  },
  {
    id: "world-rules", title: "기록실의 규칙", category: "세계관", folder: "세계관",
    content: "기록은 과거의 사건만을 보여준다. 방문자가 직접 선택하기 전에는 이야기가 진행되지 않는다.",
    tags: ["세계관", "기본 규칙"], keywords: [], enabled: true, activation: "always", match: "any",
    priority: "필수", scanDepth: 9, searchTarget: "all", partialMatch: true, caseSensitive: false,
    tokenBudget: 400, order: 100, placement: "before", exclusiveGroup: "",
  },
  {
    id: "moon-courtyard", title: "달빛 정원", category: "장소", folder: "장소와 배경",
    content: "도서관 뒤편의 정원에는 밤에만 피는 하얀 꽃이 있다. 사서는 이곳에서 잠시 쉬곤 한다.",
    tags: ["장소", "야외"], keywords: ["정원", "꽃"], enabled: true, activation: "keyword", match: "any",
    priority: "보통", scanDepth: 5, searchTarget: "all", partialMatch: true, caseSensitive: false,
    tokenBudget: 500, order: 200, placement: "before", exclusiveGroup: "",
  },
  {
    id: "missing-record", title: "사라진 기록", category: "사건", folder: "사건과 비밀",
    content: "세 번째 서가에는 제목이 지워진 기록이 숨겨져 있다. 관련 사건을 겪기 전에는 위치를 알려주지 않는다.",
    tags: ["비밀", "후반부"], keywords: ["세 번째 서가", "사라진 기록"], enabled: false, activation: "keyword", match: "any",
    priority: "높음", scanDepth: 9, searchTarget: "user", partialMatch: true, caseSensitive: false,
    tokenBudget: 600, order: 300, placement: "after", exclusiveGroup: "",
  },
];

export function createLoreEntry(): LoreEntry {
  return { ...SAMPLE_LORE[0], id: crypto.randomUUID(), title: "새 로어", content: "", tags: [], keywords: [], exclusiveGroup: "" };
}

// Stored drafts are untrusted input; accept only the complete local schema.
export function readLoreDraft(raw: string | null): LoreEntry[] | null {
  if (!raw) return null;
  try {
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data) || data.length === 0) return null;
    const ids = new Set<string>();
    for (const item of data) {
      if (!item || typeof item !== "object") return null;
      const entry = item as Record<string, unknown>;
      for (const key of ["id", "title", "folder", "content", "exclusiveGroup"]) if (typeof entry[key] !== "string") return null;
      if (!entry.id || ids.has(entry.id as string)) return null;
      if (entry.sourceId !== undefined && (typeof entry.sourceId !== "string" || !entry.sourceId)) return null;
      ids.add(entry.id as string);
      for (const key of ["tags", "keywords"]) if (!Array.isArray(entry[key]) || !(entry[key] as unknown[]).every(value => typeof value === "string")) return null;
      for (const key of ["enabled", "partialMatch", "caseSensitive"]) if (typeof entry[key] !== "boolean") return null;
      for (const key of ["scanDepth", "tokenBudget", "order"]) if (typeof entry[key] !== "number" || !Number.isInteger(entry[key]) || (entry[key] as number) < 0) return null;
      if ((entry.scanDepth as number) < 1 || (entry.scanDepth as number) > 100 || (entry.tokenBudget as number) < 1 || (entry.tokenBudget as number) > 32000 || (entry.order as number) > 100000) return null;
      for (const [key, choices] of Object.entries({ category: ["장소", "세계관", "인물", "사건"], activation: ["keyword", "always", "manual"], match: ["any", "all"], priority: ["필수", "높음", "보통", "낮음"], searchTarget: ["all", "user"], placement: ["before", "after"] })) {
        if (!choices.includes(entry[key] as string)) return null;
      }
    }
    return data as LoreEntry[];
  } catch { return null; }
}
