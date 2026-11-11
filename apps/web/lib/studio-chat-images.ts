export type ChatImageTarget = { kind: "character" | "lore_entry"; id: string };
export type ChatImageKind = "expression" | "situation";

export type ChatImageItem = {
  imageItemId: string;
  fileVersionId: string | null;
  target: ChatImageTarget;
  kind: ChatImageKind;
  tags: string[];
  alt: string;
};

export type OpeningImagePlacement = { imageItemId: string; afterParagraph: number };

export type ChatImageDraft = {
  characters: readonly { id: string }[];
  lorebooks: readonly { id: string }[];
  chatImageItems?: readonly ChatImageItem[];
  scenes: readonly { id: string; opening: string; openingImagePlacements?: readonly OpeningImagePlacement[] }[];
};

export const CHAT_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const MAX_CHAT_IMAGE_BYTES = 32 * 1024 * 1024;

export function validChatImageFile(file: Pick<File, "size" | "type">) {
  return CHAT_IMAGE_TYPES.includes(file.type) && file.size > 0 && file.size <= MAX_CHAT_IMAGE_BYTES;
}

export function normalizeChatImageTags(tags: readonly string[]) {
  return [...new Set(tags.map(tag => tag.trim()))];
}

export function addChatImageItem(target: ChatImageTarget, kind: ChatImageKind): ChatImageItem {
  if (target.kind === "lore_entry" && kind === "expression") {
    throw new Error("Lore entries only support situation images.");
  }
  return { imageItemId: crypto.randomUUID(), fileVersionId: null, target, kind, tags: [], alt: "" };
}

export function replaceChatImageFile(
  items: readonly ChatImageItem[], imageItemId: string, fileVersionId: string | null,
): ChatImageItem[] {
  return items.map(item => item.imageItemId === imageItemId ? { ...item, fileVersionId } : item);
}

export function splitOpeningParagraphs(opening: string) {
  const paragraphs: string[] = [];
  let offset = 0;
  let prefix = "";
  for (const separator of opening.matchAll(/\r?\n(?:[ \t]*\r?\n)+/g)) {
    const end = separator.index + separator[0].length;
    const paragraph = opening.slice(offset, separator.index);
    if (paragraph.trim()) {
      paragraphs.push(prefix + opening.slice(offset, end));
      prefix = "";
    } else {
      prefix += opening.slice(offset, end);
    }
    offset = end;
  }
  const tail = prefix + opening.slice(offset);
  if (tail.trim()) paragraphs.push(tail);
  else if (paragraphs.length) paragraphs[paragraphs.length - 1] += tail;
  return paragraphs;
}

export function validOpeningPosition(afterParagraph: number, paragraphCount: number) {
  return Number.isInteger(afterParagraph) && afterParagraph >= 0 && afterParagraph <= paragraphCount;
}

export type PlacementErrors = { missingImage: boolean; invalidPosition: boolean };

export function validateOpeningPlacement(
  placement: OpeningImagePlacement, imageIds: ReadonlySet<string>, paragraphCount: number,
): PlacementErrors {
  return {
    missingImage: !imageIds.has(placement.imageItemId),
    invalidPosition: !validOpeningPosition(placement.afterParagraph, paragraphCount),
  };
}

export function validateChatImageDraft(draft: ChatImageDraft): string[] {
  const errors: string[] = [];
  const imageIds = new Set<string>();
  const characterIds = new Set(draft.characters.map(({ id }) => id));
  const loreIds = new Set(draft.lorebooks.map(({ id }) => id));

  for (const [index, item] of (draft.chatImageItems ?? []).entries()) {
    const label = `이미지 항목 ${index + 1}`;
    if (imageIds.has(item.imageItemId)) errors.push(`${label}: 수집 항목 ID가 중복됐어요.`);
    imageIds.add(item.imageItemId);
    const targetIds = item.target.kind === "character" ? characterIds : loreIds;
    if (!targetIds.has(item.target.id)) errors.push(`${label}: 연결된 캐릭터 또는 로어북 항목을 찾을 수 없어요.`);
    if (item.target.kind === "lore_entry" && item.kind !== "situation") {
      errors.push(`${label}: 로어북에는 상황 이미지만 등록할 수 있어요.`);
    }
    if (normalizeChatImageTags(item.tags).includes("")) errors.push(`${label}: 비어 있는 태그가 있어요.`);
    if (!item.fileVersionId) errors.push(`${label}: 업로드가 완료된 파일이 필요해요.`);
  }

  for (const scene of draft.scenes) {
    const count = splitOpeningParagraphs(scene.opening).length;
    for (const [index, placement] of (scene.openingImagePlacements ?? []).entries()) {
      const label = `${scene.id} · 이미지 배치 ${index + 1}`;
      const { missingImage, invalidPosition } = validateOpeningPlacement(placement, imageIds, count);
      if (missingImage) errors.push(`${label}: 삭제됐거나 찾을 수 없는 이미지예요.`);
      if (invalidPosition) errors.push(`${label}: 문단 위치를 다시 선택해 주세요.`);
    }
  }
  return errors;
}

export type OpeningPreviewBlock =
  | { type: "text"; text: string }
  | { type: "image"; imageItemId: string };

export function buildOpeningImagePreview(
  opening: string, placements: readonly OpeningImagePlacement[], imageIds: ReadonlySet<string>,
): OpeningPreviewBlock[] {
  const paragraphs = splitOpeningParagraphs(opening);
  const placementsByPosition = new Map<number, OpeningPreviewBlock[]>();
  for (const placement of placements) {
    const { missingImage, invalidPosition } = validateOpeningPlacement(placement, imageIds, paragraphs.length);
    if (missingImage || invalidPosition) continue;
    const position = placement.afterParagraph;
    const blocks = placementsByPosition.get(position) ?? [];
    blocks.push({ type: "image", imageItemId: placement.imageItemId });
    placementsByPosition.set(position, blocks);
  }
  const blocks = [...(placementsByPosition.get(0) ?? [])];
  for (const [index, paragraph] of paragraphs.entries()) {
    blocks.push({ type: "text", text: paragraph }, ...(placementsByPosition.get(index + 1) ?? []));
  }
  if (!paragraphs.length && opening) blocks.push({ type: "text", text: opening });
  return blocks;
}
