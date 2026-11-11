import type { ChatImageDraft, ChatImageItem, OpeningImagePlacement } from "./studio-chat-images";

export const a1ImageItems: ChatImageItem[] = [
  {
    imageItemId: "20000000-0000-4000-8000-000000000001",
    fileVersionId: "30000000-0000-4000-8000-000000000002",
    target: { kind: "character", id: "repairer" },
    kind: "expression",
    tags: ["미소"],
    alt: "수리공이 미소 짓는다",
  },
  {
    imageItemId: "20000000-0000-4000-8000-000000000002",
    fileVersionId: "30000000-0000-4000-8000-000000000003",
    target: { kind: "lore_entry", id: "workshop" },
    kind: "situation",
    tags: ["수리점"],
    alt: "등불이 켜진 수리점",
  },
];

export const a1Arrival = {
  id: "arrival",
  opening: "수리점 문이 열렸다.",
  openingImagePlacements: [{ imageItemId: a1ImageItems[1].imageItemId, afterParagraph: 1 }] satisfies OpeningImagePlacement[],
};

export const a1ImageDraft = {
  characters: [{ id: "repairer" }],
  lorebooks: [{ id: "workshop" }],
  chatImageItems: a1ImageItems,
  scenes: [a1Arrival],
} satisfies ChatImageDraft;
