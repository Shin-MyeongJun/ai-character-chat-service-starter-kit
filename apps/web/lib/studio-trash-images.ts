import type { ChatImageItem, ChatImageTarget, OpeningImagePlacement } from "./studio-chat-images";
import { chatImageItem, chatImageUpload, openingPlacement, type ChatImageUpload, type StudioProject, type StudioScene } from "./studio-project";

type Indexed<T> = { index: number; value: T };
export type TrashedImages = {
  items: Indexed<ChatImageItem>[];
  uploads: Indexed<ChatImageUpload>[];
  scenes: { sceneId: string; placements: Indexed<OpeningImagePlacement>[] }[];
};

function capture<T>(rows: T[] | undefined, matches: (row: T) => boolean): Indexed<T>[] {
  return (rows ?? []).flatMap((value, index) => matches(value) ? [{ index, value }] : []);
}

export function captureTrashedImages(project: StudioProject, target: ChatImageTarget, scenes: StudioScene[]): TrashedImages | undefined {
  const items = capture(project.chatImageItems, item => item.target.kind === target.kind && item.target.id === target.id);
  if (!items.length) return undefined;
  const ids = new Set(items.map(({ value }) => value.imageItemId));
  return {
    items,
    uploads: capture(project.chatImageUploads, upload => ids.has(upload.itemId)),
    scenes: scenes.flatMap(scene => {
      const placements = capture(scene.openingImagePlacements, placement => ids.has(placement.imageItemId));
      return placements.length ? [{ sceneId: scene.id, placements }] : [];
    }),
  };
}

function indexedRows<T>(rows: unknown, valid: (row: unknown) => row is T): rows is Indexed<T>[] {
  return Array.isArray(rows) && rows.every((row, i) => row && Number.isSafeInteger(row.index)
    && row.index >= 0 && (!i || rows[i - 1].index < row.index) && valid(row.value));
}

export function validTrashedImages(images: unknown, target: ChatImageTarget): boolean {
  if (!images || typeof images !== "object"
    || !("items" in images) || !indexedRows(images.items, chatImageItem)
    || !("uploads" in images) || !indexedRows(images.uploads, chatImageUpload)
    || !("scenes" in images) || !Array.isArray(images.scenes)) return false;
  const ids = new Set(images.items.map(({ value }) => value.imageItemId));
  if (ids.size !== images.items.length || images.items.some(({ value }) => value.target.kind !== target.kind || value.target.id !== target.id)
    || images.uploads.some(({ value }) => !ids.has(value.itemId))) return false;
  const sceneIds = new Set<string>();
  for (const scene of images.scenes) {
    if (!scene || typeof scene.sceneId !== "string" || sceneIds.has(scene.sceneId)) return false;
    const placements: unknown = scene.placements;
    if (!indexedRows(placements, openingPlacement) || placements.some(({ value }) => !ids.has(value.imageItemId))) return false;
    sceneIds.add(scene.sceneId);
  }
  return true;
}

function reinsert<T>(current: T[] | undefined, removed: Indexed<T>[], include: (value: T) => boolean): T[] {
  const merged = [...(current ?? [])];
  let skipped = 0;
  for (const { index, value } of removed) {
    if (include(value)) merged.splice(index - skipped, 0, value);
    else skipped++;
  }
  return merged;
}

export function restoreTrashedImages(project: StudioProject, images: TrashedImages, retired: ReadonlySet<string>) {
  const existing = new Set(project.chatImageItems?.map(item => item.imageItemId));
  const retiredIds = new Set(images.items.map(({ value }) => value.imageItemId).filter(id => retired.has(id.toLowerCase())));
  const ids = new Set(images.items.map(({ value }) => value.imageItemId).filter(id => !retiredIds.has(id) && !existing.has(id)));
  const scenes = new Map(images.scenes.map(scene => [scene.sceneId, scene.placements]));
  return {
    project: ids.size ? {
      ...project,
      chatImageItems: reinsert(project.chatImageItems, images.items, item => ids.has(item.imageItemId)),
      ...(images.uploads.length > 0 && { chatImageUploads: reinsert(project.chatImageUploads, images.uploads, upload => ids.has(upload.itemId)) }),
    } : project,
    restorePlacements(scene: StudioScene): StudioScene {
      // Older scene trash entries can still contain placements for a now-retired item.
      let current = scene.openingImagePlacements;
      if (current?.some(p => retiredIds.has(p.imageItemId))) current = current.filter(p => !retiredIds.has(p.imageItemId));
      const placements = scenes.get(scene.id);
      if (ids.size && placements) current = reinsert(current, placements, p => ids.has(p.imageItemId));
      return current === scene.openingImagePlacements ? scene : { ...scene, openingImagePlacements: current };
    },
  };
}
