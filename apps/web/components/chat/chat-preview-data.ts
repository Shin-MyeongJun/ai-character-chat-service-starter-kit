import paragraphs from "../../../../docs/design/moseori-chat-v1/content.json";

export const designTitle = "비가 그치면, 기록실에서";
export const designCharacter = "에린";
export const designOpening = "낯선 골목 끝, 불이 켜진 기록실. 에린이 장부를 덮으며 고개를 들었다. “어떤 이야기를 찾고 계신가요?”";
export const designReply = paragraphs.map(({ type, text }) => type === "narration" ? `**${text}**` : text).join("\n\n");
export const designMessages = [
  { id: "design-user", sender_type: "user", content: "잊어버린 이야기를 찾으러 왔어요.\n어디서부터 시작하면 될까요?", position: 1, revision: 1 },
  { id: "design-answer", sender_type: "character", content: designReply, position: 2, revision: 1 },
];

// Preview data contains display labels and sample output only.
export const previewShortcuts = [
  { id: "diary", name: "/일기", description: "지금까지의 이야기를 일기로 정리", standalone: true },
  { id: "detail", name: "/묘사 강화", description: "다음 장면을 더 자세하게 묘사", standalone: false },
] as const;
export type PreviewShortcut = typeof previewShortcuts[number]["id"];

export const previewModels = [
  { id: "default", label: "기본 모델" },
  { id: "fast", label: "빠른 모델" },
  { id: "detailed", label: "상세 모델" },
] as const;
export type PreviewModel = typeof previewModels[number]["id"];

export function previewReply(shortcuts: readonly PreviewShortcut[], model: PreviewModel) {
  if (shortcuts.includes("diary")) return "**기록실 일기**\n\n비가 그치기 전에 손님이 왔다. 잃어버린 이야기를 찾는다기에 은색 열쇠를 건넸다. 내일은 그 편지부터 함께 읽기로 했다.";
  if (shortcuts.includes("detail")) return "**에린이 커튼을 젖히자 잿빛 빗줄기 사이로 노란 불빛이 번졌다. 창틀에 떨어진 물방울이 책상 위의 은색 열쇠에 작은 점을 남겼다.**\n\n“편지를 먼저 읽어 볼까요?”";
  if (model === "fast") return "**에린이 편지를 책상 위에 펼쳤다.**\n\n“여기, 이 문장부터 읽어 보세요.”";
  if (model === "detailed") return "**에린이 편지를 펼치자 봉투에 붙어 있던 마른 은행잎이 책상 위로 떨어졌다. 빗소리 사이로 종이가 펴지는 소리가 들렸다.**\n\n“이 필체가 낯익나요?”\n\n${designReply}";
  return designReply;
}
