import { readLoreDraft, type LoreEntry } from "./studio-data";
import { readStudioProject, restoreStudioProject, type StudioCharacter, type StudioProject, type StudioScene } from "./studio-project";
import { captureTrashedImages, restoreTrashedImages, validTrashedImages, type TrashedImages } from "./studio-trash-images";

export const WORKSPACE_STORAGE_KEY = "chat-kit-studio-workspace-v3";
export type WorkspaceWork = { id: string; project: StudioProject };
export type TrashItem = { id: string; label: string; deletedAt: string } & (
  | { kind: "work"; data: WorkspaceWork }
  | { kind: "character"; data: StudioCharacter }
  | { kind: "lore"; data: LoreEntry }
  | { kind: "work-character"; workId: string; data: StudioCharacter; sceneIds: string[]; images?: TrashedImages }
  | { kind: "work-lore"; workId: string; data: LoreEntry; sceneIds: string[]; images?: TrashedImages }
  | { kind: "scene"; workId: string; data: StudioScene; wasDefault: boolean });
export type StudioWorkspace = { version: 3; works: WorkspaceWork[]; characters: StudioCharacter[]; lorebooks: LoreEntry[]; trash: TrashItem[] };
export const emptyWorkspace = (): StudioWorkspace => ({ version: 3, works: [], characters: [], lorebooks: [], trash: [] });
export function blankProject(): StudioProject {
  return { version: 2, work: { title: "새 작품", introduction: "", tags: [], worldRules: "", visibility: "비공개", defaultSceneId: "" }, characters: [], lorebooks: [], scenes: [] };
}
export function createWork(): WorkspaceWork { return { id: crypto.randomUUID(), project: blankProject() }; }
export function migrateWorkspace(current: string | null, previous: string | null, legacy: string | null): StudioWorkspace | null {
  if (current !== null) return readWorkspace(current);
  if (previous === null && legacy === null) return emptyWorkspace();
  const project = restoreStudioProject(previous, legacy);
  if (!project) return null;
  // Unknown provenance stays private to the existing work; asset IDs and content survive unchanged.
  const copy = structuredClone(project);
  copy.characters.forEach(row => { delete row.sourceId; }); copy.lorebooks.forEach(row => { delete row.sourceId; });
  return { ...emptyWorkspace(), works: [{ id: "migrated-work", project: copy }] };
}
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const rows = (v: unknown): v is Record<string, unknown>[] => Array.isArray(v) && v.every(row => record(row) && typeof row.id === "string" && !!row.id) && new Set(v.map(row => row.id)).size === v.length;
const validCharacter = (v: unknown) => !!readStudioProject(JSON.stringify({ ...blankProject(), characters: [v] }));
const validLore = (v: unknown) => !!readLoreDraft(JSON.stringify([v]));
const validWork = (v: unknown) => record(v) && typeof v.id === "string" && !!v.id && !!readStudioProject(JSON.stringify(v.project));
const validScene = (v: unknown) => {
  if (!record(v) || typeof v.characterId !== "string" || typeof v.placeId !== "string") return false;
  return !!readStudioProject(JSON.stringify({ ...blankProject(), scenes: [{ ...v, characterId: "", placeId: "" }] }));
};
export function readWorkspace(raw: string): StudioWorkspace | null {
  try {
    const v: unknown = JSON.parse(raw);
    if (!record(v) || v.version !== 3 || !rows(v.works) || !rows(v.characters) || !rows(v.lorebooks) || !rows(v.trash)) return null;
    const sources = { characters: v.characters, lorebooks: v.lorebooks };
    if (!v.works.every(validWork) || !v.characters.every(row => validCharacter(row) && row.sourceId === undefined) || !v.lorebooks.every(row => validLore(row) && row.sourceId === undefined)) return null;
    for (const work of v.works) {
      const p = work.project as StudioProject;
      if (p.characters.some(row => row.sourceId && !sources.characters.some(source => source.id === row.sourceId)) || p.lorebooks.some(row => row.sourceId && !sources.lorebooks.some(source => source.id === row.sourceId))) return null;
    }
    for (const t of v.trash) {
      if (typeof t.label !== "string" || typeof t.deletedAt !== "string") return null;
      if (t.kind === "work") { if (!validWork(t.data)) return null; }
      else if (t.kind === "character" || t.kind === "lore") { if (!(t.kind === "character" ? validCharacter(t.data) : validLore(t.data))) return null; }
      else if (["work-character", "work-lore", "scene"].includes(t.kind as string)) {
        if (typeof t.workId !== "string" || !t.workId) return null;
        if (t.kind === "scene") { if (!validScene(t.data) || typeof t.wasDefault !== "boolean") return null; }
        else if (!(t.kind === "work-character" ? validCharacter(t.data) : validLore(t.data)) || !Array.isArray(t.sceneIds) || !t.sceneIds.every(id => typeof id === "string")) return null;
        else if (t.images !== undefined && !validTrashedImages(t.images, {
          kind: t.kind === "work-character" ? "character" : "lore_entry", id: (t.data as StudioCharacter | LoreEntry).id,
        })) return null;
      } else return null;
    }
    return v as StudioWorkspace;
  } catch { return null; }
}
export function repairProject(p: StudioProject): StudioProject {
  return { ...p, work: { ...p.work, defaultSceneId: p.work.defaultSceneId === "" || p.scenes.some(s => s.id === p.work.defaultSceneId) ? p.work.defaultSceneId : p.scenes[0]?.id ?? "" }, scenes: p.scenes.map(s => ({ ...s, characterId: p.characters.some(c => c.id === s.characterId) ? s.characterId : "", placeId: p.lorebooks.some(l => l.id === s.placeId && l.category === "장소") ? s.placeId : "" })) };
}
export function updateProject(w: StudioWorkspace, id: string, change: (p: StudioProject) => StudioProject): StudioWorkspace {
  return { ...w, works: w.works.map(work => work.id === id ? { ...work, project: repairProject(change(work.project)) } : work) };
}

function mergeSavedCharacterMedia(current: StudioCharacter[], submitted: StudioCharacter[], saved: StudioCharacter[]): StudioCharacter[] {
  if (submitted === saved) return current;
  return current.map(character => {
    const original = submitted.find(row => row.id === character.id);
    const confirmed = saved.find(row => row.id === character.id);
    if (!original || !confirmed || !character.assets.length) return character;
    const assets = character.assets.map(asset => {
      const before = original.assets.find(row => row.id === asset.id && row.usage === asset.usage);
      const after = confirmed.assets.find(row => row.id === asset.id && row.usage === asset.usage);
      return before && after?.mediaId && before.mediaId === asset.mediaId ? { ...asset, mediaId: after.mediaId } : asset;
    });
    return { ...character, assets };
  });
}

export function applySavedStudioWork(workspace: StudioWorkspace, submitted: WorkspaceWork, saved: StudioProject): StudioWorkspace {
  return updateProject(workspace, submitted.id, current => {
    if (current === submitted.project) return saved;

    // An item ID survives replacement. Only consume the request that produced this version.
    const requests = new Map(submitted.project.chatImageUploads?.map(upload => [upload.itemId, upload.requestId]));
    const versions = new Map(saved.chatImageItems?.map(item => [item.imageItemId, item.fileVersionId]));
    const completed = new Map<string, string>();
    const pending = current.chatImageUploads?.filter(upload => {
      const version = versions.get(upload.itemId);
      if (!version || requests.get(upload.itemId) !== upload.requestId) return true;
      completed.set(upload.itemId, version);
      return false;
    });
    return {
      ...current,
      chatImageItems: current.chatImageItems?.map(item => {
        const fileVersionId = completed.get(item.imageItemId);
        return fileVersionId ? { ...item, fileVersionId } : item;
      }),
      chatImageUploads: pending?.length ? pending : undefined,
      characters: mergeSavedCharacterMedia(current.characters, submitted.project.characters, saved.characters),
    };
  });
}
export function linkSource(w: StudioWorkspace, workId: string, kind: "character" | "lore", sourceId: string): StudioWorkspace {
  const source = (kind === "character" ? w.characters : w.lorebooks).find(row => row.id === sourceId);
  if (!source) return w;
  const copy = { ...structuredClone(source), id: crypto.randomUUID(), sourceId };
  return updateProject(w, workId, p => kind === "character" ? { ...p, characters: [...p.characters, copy as StudioCharacter] } : { ...p, lorebooks: [...p.lorebooks, copy as LoreEntry] });
}
export function trashEntity(w: StudioWorkspace, kind: TrashItem["kind"], id: string, workId?: string): StudioWorkspace {
  const work = w.works.find(row => row.id === workId); const p = work?.project;
  const data = kind === "work" ? w.works.find(row => row.id === id) : kind === "character" ? w.characters.find(row => row.id === id) : kind === "lore" ? w.lorebooks.find(row => row.id === id) : kind === "work-character" ? p?.characters.find(row => row.id === id) : kind === "work-lore" ? p?.lorebooks.find(row => row.id === id) : p?.scenes.find(row => row.id === id);
  if (!data) return w;
  const label = "project" in data ? data.project.work.title : "name" in data ? data.name : data.title;
  const base = { id: crypto.randomUUID(), label, deletedAt: new Date().toISOString(), kind, data: structuredClone(data) };
  const images = p && (kind === "work-character" || kind === "work-lore")
    ? captureTrashedImages(p, { kind: kind === "work-character" ? "character" : "lore_entry", id }) : undefined;
  const t = (kind === "scene" ? { ...base, workId, wasDefault: p?.work.defaultSceneId === id } : kind.startsWith("work-") ? {
    ...base, workId, ...(images && { images }), sceneIds: p?.scenes.filter(s => kind === "work-character" ? s.characterId === id : s.placeId === id).map(s => s.id) ?? [],
  } : base) as TrashItem;
  let next = { ...w, trash: [...w.trash, t] };
  if (kind === "work") return { ...next, works: next.works.filter(row => row.id !== id) };
  if (kind === "character" || kind === "lore") {
    next = { ...next, characters: kind === "character" ? next.characters.filter(row => row.id !== id) : next.characters, lorebooks: kind === "lore" ? next.lorebooks.filter(row => row.id !== id) : next.lorebooks };
    // Existing work copies retain all edits and become work-only, even in deleted works.
    const detach = (p: StudioProject): StudioProject => ({ ...p, characters: p.characters.map(row => kind === "character" && row.sourceId === id ? withoutSource(row) : row), lorebooks: p.lorebooks.map(row => kind === "lore" && row.sourceId === id ? withoutSource(row) : row) });
    return { ...next, works: next.works.map(row => ({ ...row, project: detach(row.project) })), trash: next.trash.map(row => row.kind === "work" ? { ...row, data: { ...row.data, project: detach(row.data.project) } } : row) };
  }
  return updateProject(next, workId!, p => {
    if (kind === "scene") return { ...p, scenes: p.scenes.filter(row => row.id !== id) };
    const project = {
      ...p,
      characters: kind === "work-character" ? p.characters.filter(row => row.id !== id) : p.characters,
      lorebooks: kind === "work-lore" ? p.lorebooks.filter(row => row.id !== id) : p.lorebooks,
    };
    if (!images) return project;
    const removed = new Set(images.items.map(({ value }) => value.imageItemId));
    return {
      ...project,
      chatImageItems: project.chatImageItems?.filter(item => !removed.has(item.imageItemId)),
      ...(project.chatImageUploads && { chatImageUploads: project.chatImageUploads.filter(upload => !removed.has(upload.itemId)) }),
      scenes: project.scenes.map(scene => scene.openingImagePlacements ? {
        ...scene, openingImagePlacements: scene.openingImagePlacements.filter(placement => !removed.has(placement.imageItemId)),
      } : scene),
    };
  });
}
function withoutSource<T extends { sourceId?: string }>(row: T): T { const copy = { ...row }; delete copy.sourceId; return copy; }
export function restoreTrash(w: StudioWorkspace, trashId: string, retiredImageIds: ReadonlySet<string> = new Set()): StudioWorkspace {
  const t = w.trash.find(row => row.id === trashId); if (!t) return w;
  if ("workId" in t && !w.works.some(row => row.id === t.workId)) return w;
  const next = { ...w, trash: w.trash.filter(row => row.id !== trashId) };
  const character = (row: StudioCharacter) => row.sourceId && !w.characters.some(c => c.id === row.sourceId) ? withoutSource(row) : row;
  const lore = (row: LoreEntry) => row.sourceId && !w.lorebooks.some(l => l.id === row.sourceId) ? withoutSource(row) : row;
  if (t.kind === "work") return { ...next, works: [...next.works, { ...t.data, project: repairProject({ ...t.data.project, characters: t.data.project.characters.map(character), lorebooks: t.data.project.lorebooks.map(lore) }) }] };
  if (t.kind === "character") return { ...next, characters: [...next.characters, withoutSource(t.data)] };
  if (t.kind === "lore") return { ...next, lorebooks: [...next.lorebooks, withoutSource(t.data)] };
  return updateProject(next, t.workId, p => {
    if (t.kind === "scene") return { ...p, scenes: [...p.scenes, t.data], work: { ...p.work, defaultSceneId: t.wasDefault && !p.work.defaultSceneId ? t.data.id : p.work.defaultSceneId } };
    const restored = t.images ? restoreTrashedImages(p, t.images, retiredImageIds) : p;
    const field = t.kind === "work-character" ? "characterId" : "placeId";
    const scenes = restored.scenes.map(s => t.sceneIds.includes(s.id) && !s[field] ? { ...s, [field]: t.data.id } : s);
    if (t.kind === "work-character") {
      const characters = p.characters.some(c => c.id === t.data.id) ? p.characters : [...p.characters, character(t.data)];
      return { ...restored, scenes, characters };
    }
    const lorebooks = p.lorebooks.some(l => l.id === t.data.id) ? p.lorebooks : [...p.lorebooks, lore(t.data)];
    return { ...restored, scenes, lorebooks };
  });
}
