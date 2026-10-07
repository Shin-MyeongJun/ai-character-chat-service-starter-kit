import { SAMPLE_LORE, readLoreDraft, type LoreEntry } from "./studio-data";

export const PROJECT_STORAGE_KEY = "chat-kit-studio-draft-v2";
export type StudioCharacter = { id: string; sourceId?: string; name: string; role: string; introduction: string; persona: string; dialogue: string; tags: string[]; relationships: string; assets: CharacterAsset[] };
export type CharacterAsset = { id: string; name: string; usage: "portrait" | "expression" | "scene" };
export type StudioScene = {
  id: string; title: string; background: string; opening: string; characterId: string; placeId: string;
  initialNotes: string; language: "한국어" | "English" | "日本語"; storyTime: string;
  perspective: "2인칭" | "1인칭" | "3인칭"; variants: string;
};
export type StudioWork = { title: string; introduction: string; tags: string[]; worldRules: string; visibility: "비공개" | "링크 공개" | "전체 공개"; defaultSceneId: string };
export type StudioProject = { version: 2; work: StudioWork; characters: StudioCharacter[]; scenes: StudioScene[]; lorebooks: LoreEntry[] };
export function createCharacter(): StudioCharacter {
  return { id: crypto.randomUUID(), name: "새 캐릭터", role: "", introduction: "", persona: "", dialogue: "", tags: [], relationships: "", assets: [] };
}
export function createScene(characterId: string, placeId: string): StudioScene {
  return { id: crypto.randomUUID(), title: "새 시작 장면", background: "", opening: "", characterId, placeId, initialNotes: "", language: "한국어", storyTime: "", perspective: "2인칭", variants: "" };
}
export function duplicateScene(scene: StudioScene): StudioScene {
  return { ...scene, id: crypto.randomUUID(), title: `${scene.title || "시작 장면"} (복사)` };
}
export function sampleProject(lorebooks: LoreEntry[] = SAMPLE_LORE): StudioProject {
  const placeId = lorebooks.find(entry => entry.category === "장소")?.id ?? "";
  return {
    version: 2,
    work: { title: "별빛 기록실", introduction: "달빛 아래 열리는 기록실에서\n잊힌 이야기와 새로운 인연을 만나보세요.", tags: ["판타지", "미스터리", "학교"], worldRules: "달이 뜨면 기록실의 문이 열린다. 기록은 과거만을 보여준다.\n독자의 선택을 기다리고, 독자의 행동이나 감정을 대신 결정하지 않는다.", visibility: "비공개", defaultSceneId: "first-door" },
    characters: [
      { id: "erin", name: "에린", role: "기록실의 사서", introduction: "밤의 기록실을 지키는 사서. 낯선 손님에게도 작은 친절을 건넨다.", persona: "차분하고 관찰력이 좋다. 처음에는 존댓말을 사용한다.\n상대의 선택을 기다리며, 질문은 한 번에 하나씩 한다.\n찾는 기록을 함께 살피되 사용자의 행동을 대신 정하지 않는다.", dialogue: "“급할 것 없어요. 이야기는 도망가지 않으니까요.”", tags: ["사서", "차분함", "주인공"], relationships: "레온은 기록실을 자주 찾는 손님이다. 아델과는 기록을 함께 연구한다.", assets: [] },
      { id: "leon", name: "레온", role: "기록을 찾는 여행자", introduction: "사라진 약속의 흔적을 찾아 기록실을 방문한 여행자.", persona: "솔직하고 행동이 빠르다. 중요한 기억을 말할 때는 잠시 머뭇거린다.", dialogue: "“그 기록을 찾으면, 이번에는 약속을 지킬 수 있을까요?”", tags: ["여행자"], relationships: "에린의 도움으로 오래된 기록을 찾고 있다.", assets: [] },
      { id: "adel", name: "아델", role: "도서관의 연구자", introduction: "밤마다 달의 움직임과 도서관의 변화를 관찰하는 연구자.", persona: "호기심이 많으며 관찰한 사실을 꼼꼼히 기록한다.", dialogue: "“오늘의 달빛은 어제와 조금 다르네요.”", tags: ["연구자"], relationships: "에린과 기록실의 변화를 연구한다.", assets: [] },
    ],
    scenes: [
      { id: "first-door", title: "처음 열린 문", background: "달빛이 닿아 기록실의 문이 열리는 밤.\n독자는 처음 방문한 손님이며 에린과 아직 아는 사이가 아니다.", opening: "문이 조용히 열리고, 사서가 고개를 들었다.\n\n“이 시간에 손님이라니. 혹시 찾고 있는 기록이 있나요?”", characterId: "erin", placeId, initialNotes: "독자는 찾고 싶은 기록을 자유롭게 선택한다.", language: "한국어", storyTime: "달빛이 비치는 밤", perspective: "2인칭", variants: "" },
      { id: "night-room", title: "야간 열람실", background: "밤이 깊어지고 기록실의 마지막 등불이 켜진다.", opening: "마지막 등불 아래, 여행자가 오래된 책을 내려놓았다.\n\n“이 기록을 함께 살펴봐 주실래요?”", characterId: "leon", placeId, initialNotes: "", language: "한국어", storyTime: "늦은 밤", perspective: "2인칭", variants: "" },
    ], lorebooks,
  };
}
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === "object" && !Array.isArray(value); }
function strings(value: unknown): value is string[] { return Array.isArray(value) && value.every(item => typeof item === "string"); }
function fields(value: Record<string, unknown>, names: string[]) { return names.every(name => typeof value[name] === "string"); }
function uniqueRows(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every(item => record(item) && typeof item.id === "string" && !!item.id) && new Set(value.map(item => item.id)).size === value.length;
}
export function readStudioProject(raw: string | null): StudioProject | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!record(value) || value.version !== 2 || !record(value.work) || !uniqueRows(value.characters) || !uniqueRows(value.scenes)) return null;
    const work = value.work;
    if (!fields(work, ["title", "introduction", "worldRules", "defaultSceneId"]) || !strings(work.tags) || !["비공개", "링크 공개", "전체 공개"].includes(work.visibility as string)) return null;
    const lore = Array.isArray(value.lorebooks) && value.lorebooks.length === 0 ? [] : readLoreDraft(JSON.stringify(value.lorebooks));
    if (!lore || (work.defaultSceneId !== "" && !value.scenes.some(scene => scene.id === work.defaultSceneId))) return null;
    for (const character of value.characters) {
      if (!fields(character, ["name", "role", "introduction", "persona", "dialogue", "relationships"]) || !strings(character.tags) || !Array.isArray(character.assets)) return null;
      if (character.sourceId !== undefined && (typeof character.sourceId !== "string" || !character.sourceId)) return null;
      const assets = character.assets;
      if (!assets.every(asset => record(asset) && fields(asset, ["id", "name"]) && !!asset.id && ["portrait", "expression", "scene"].includes(asset.usage as string)) || new Set(assets.map(asset => asset.id)).size !== assets.length || assets.filter(asset => asset.usage === "portrait").length > 1) return null;
    }
    for (const scene of value.scenes) {
      if (!fields(scene, ["title", "background", "opening", "characterId", "placeId", "initialNotes", "storyTime", "variants"]) || !["한국어", "English", "日本語"].includes(scene.language as string) || !["2인칭", "1인칭", "3인칭"].includes(scene.perspective as string)) return null;
      if ((scene.characterId !== "" && !value.characters.some(character => character.id === scene.characterId)) || (scene.placeId !== "" && !lore.some(entry => entry.id === scene.placeId && entry.category === "장소"))) return null;
    }
    return { version: 2, work: work as StudioWork, characters: value.characters as StudioCharacter[], scenes: value.scenes as StudioScene[], lorebooks: lore };
  } catch { return null; }
}
// Leave the old key intact, preserving existing lore and adding the new editable sample data.
export function restoreStudioProject(current: string | null, legacy: string | null): StudioProject | null {
  if (current !== null) return readStudioProject(current);
  const lore = readLoreDraft(legacy);
  return lore ? sampleProject(lore) : null;
}
