import type { ChatImageItem, ChatImageTarget, OpeningImagePlacement } from "./studio-chat-images";
import { chatImageItem, chatImageUpload, openingPlacement, type ChatImageUpload, type StudioProject } from "./studio-project";

type Indexed<T> = { index: number; value: T };
export type TrashedImages = {
  items: Indexed<ChatImageItem>[];
  uploads: Indexed<ChatImageUpload>[];
  scenes: { sceneId: string; placements: Indexed<OpeningImagePlacement>[] }[];
};

function capture<T>(rows: T[] | undefined, matches: (row: T) => boolean): Indexed<T>[] {
  return (rows ?? []).flatMap((value, index) => matches(value) ? [{ index, value }] : []);
}

export function captureTrashedImages(project: StudioProject, target: ChatImageTarget): TrashedImages | undefined {
  const items = capture(project.chatImageItems, item => item.target.kind === target.kind && item.target.id === target.id);
  if (!items.length) return undefined;
  const ids = new Set(items.map(({ value }) => value.imageItemId));
  return {
    items,
    uploads: capture(project.chatImageUploads, upload => ids.has(upload.itemId)),
    scenes: project.scenes.flatMap(scene => {
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

export function restoreTrashedImages(project: StudioProject, images: TrashedImages, retired: ReadonlySet<string>): StudioProject {
  const existing = new Set(project.chatImageItems?.map(item => item.imageItemId));
  const items = images.items.filter(({ value }) => !retired.has(value.imageItemId.toLowerCase()) && !existing.has(value.imageItemId));
  if (!items.length) return project;
  const ids = new Set(items.map(({ value }) => value.imageItemId));
  const scenes = new Map(images.scenes.map(scene => [scene.sceneId, scene.placements]));
  return {
    ...project,
    chatImageItems: reinsert(project.chatImageItems, images.items, item => ids.has(item.imageItemId)),
    ...(images.uploads.length > 0 && { chatImageUploads: reinsert(project.chatImageUploads, images.uploads, upload => ids.has(upload.itemId)) }),
    scenes: project.scenes.map(scene => {
      const placements = scenes.get(scene.id);
      return placements ? { ...scene, openingImagePlacements: reinsert(scene.openingImagePlacements, placements, p => ids.has(p.imageItemId)) } : scene;
    }),
  };
}
