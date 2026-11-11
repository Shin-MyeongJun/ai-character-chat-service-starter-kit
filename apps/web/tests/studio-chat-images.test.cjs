const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const ts = require("typescript");

function load(name) {
  const filename = resolve(__dirname, "../lib", name);
  const source = readFileSync(filename, "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  new Function("exports", "module", code)(module.exports, module);
  return module.exports;
}

const {
  addChatImageItem, replaceChatImageFile, normalizeChatImageTags, validChatImageFile,
  validateChatImageDraft, buildOpeningImagePreview, splitOpeningParagraphs,
} = load("studio-chat-images.ts");
const { a1ImageItems, a1Arrival, a1ImageDraft } = load("studio-chat-image-example.ts");
const [smile, workshop] = a1ImageItems;
const ids = new Set(a1ImageItems.map(item => item.imageItemId));

test("a1 fixture validates and places the workshop image after its first paragraph", () => {
  assert.deepEqual(validateChatImageDraft(a1ImageDraft), []);
  assert.deepEqual(buildOpeningImagePreview(a1Arrival.opening, a1Arrival.openingImagePlacements, ids), [
    { type: "text", text: a1Arrival.opening },
    { type: "image", imageItemId: workshop.imageItemId },
  ]);
  assert.deepEqual(validateChatImageDraft({
    characters: [], lorebooks: [], scenes: [{ id: "legacy", opening: "본문" }],
  }), []);
});

test("add allocates a fresh ID per item even for the same tags and after deletion", () => {
  const first = { ...addChatImageItem(smile.target, smile.kind), tags: ["미소"], fileVersionId: smile.fileVersionId };
  const second = { ...addChatImageItem(smile.target, smile.kind), tags: ["미소"], fileVersionId: smile.fileVersionId };
  assert.equal(new Set([smile.imageItemId, first.imageItemId, second.imageItemId]).size, 3);
  assert.match(first.imageItemId, /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/);
  assert.deepEqual(validateChatImageDraft({ ...a1ImageDraft, chatImageItems: [...a1ImageItems, first, second] }), []);
  const afterDeletion = addChatImageItem(first.target, first.kind);
  assert.notEqual(afterDeletion.imageItemId, first.imageItemId);
  assert.equal(afterDeletion.fileVersionId, null);
  assert.throws(() => addChatImageItem(workshop.target, "expression"));
});

test("replace changes only the selected file version and existing placement keeps its reference", () => {
  const fileVersionId = "30000000-0000-4000-8000-000000000004";
  const replaced = replaceChatImageFile(a1ImageItems, workshop.imageItemId, fileVersionId);
  assert.equal(replaced[0], smile);
  assert.deepEqual(replaced[1], { ...workshop, fileVersionId });
  assert.deepEqual(validateChatImageDraft({ ...a1ImageDraft, chatImageItems: replaced }), []);
  assert.equal(a1Arrival.openingImagePlacements[0].imageItemId, replaced[1].imageItemId);
});

test("validation flags deleted references and invalid paragraph positions independently", () => {
  const scene = {
    ...a1Arrival,
    openingImagePlacements: [{ imageItemId: workshop.imageItemId, afterParagraph: 2 }],
  };
  const errors = validateChatImageDraft({ ...a1ImageDraft, chatImageItems: [smile], scenes: [scene] });
  assert.equal(errors.length, 2);
  assert.match(errors[0], /삭제/);
  assert.match(errors[1], /문단/);
  assert.deepEqual(buildOpeningImagePreview(scene.opening, scene.openingImagePlacements, new Set([smile.imageItemId])), [
    { type: "text", text: scene.opening },
  ]);
  for (const afterParagraph of [-1, 0.5, 2, NaN]) {
    const badScene = { ...scene, openingImagePlacements: [{ imageItemId: smile.imageItemId, afterParagraph }] };
    assert.match(validateChatImageDraft({ ...a1ImageDraft, scenes: [badScene] })[0], /문단/);
  }
});

test("paragraph preview preserves CRLF, blank separators, same-position order and repeats", () => {
  const opening = "\r\n\r\n첫 문단\r\n \r\n  둘째 문단\r\n\r\n";
  const paragraphs = splitOpeningParagraphs(opening);
  assert.equal(paragraphs.length, 2);
  assert.equal(paragraphs.join(""), opening);
  const blocks = buildOpeningImagePreview(opening, [
    { imageItemId: workshop.imageItemId, afterParagraph: 1 },
    { imageItemId: smile.imageItemId, afterParagraph: 0 },
    { imageItemId: smile.imageItemId, afterParagraph: 1 },
    { imageItemId: workshop.imageItemId, afterParagraph: 1 },
  ], ids);
  assert.deepEqual(blocks.map(block => block.type === "text" ? block.text : block.imageItemId), [
    smile.imageItemId, paragraphs[0], workshop.imageItemId, smile.imageItemId, workshop.imageItemId, paragraphs[1],
  ]);
  assert.deepEqual(splitOpeningParagraphs(" \n\n "), []);
  assert.deepEqual(buildOpeningImagePreview("", [{ imageItemId: smile.imageItemId, afterParagraph: 0 }], ids), [
    { type: "image", imageItemId: smile.imageItemId },
  ]);
});

test("validation catches missing targets, lore expressions, blank tags, and pending files", () => {
  assert.deepEqual(normalizeChatImageTags([" 미소 ", "미소", " 놀람 "]), ["미소", "놀람"]);
  const errors = validateChatImageDraft({
    ...a1ImageDraft,
    lorebooks: [],
    chatImageItems: [smile, { ...workshop, kind: "expression", fileVersionId: null, tags: [" "] }],
  });
  assert.equal(errors.length, 4);
  for (const term of ["찾을 수 없어요", "상황 이미지", "태그", "업로드"]) {
    assert.ok(errors.some(error => error.includes(term)));
  }
});

test("local file preflight uses a2 MIME and byte bounds", () => {
  for (const type of ["image/png", "image/jpeg", "image/webp", "image/gif"]) {
    assert.equal(validChatImageFile({ type, size: 32 * 1024 * 1024 }), true);
  }
  assert.equal(validChatImageFile({ type: "image/png", size: 32 * 1024 * 1024 + 1 }), false);
  assert.equal(validChatImageFile({ type: "image/png", size: 0 }), false);
  assert.equal(validChatImageFile({ type: "image/svg+xml", size: 1 }), false);
});
