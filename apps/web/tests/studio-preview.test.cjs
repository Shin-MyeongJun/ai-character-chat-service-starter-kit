const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

// UI delegates every decision to the server; only transport and mapping are tested here.
function load(name, overrides = {}) {
  const filename = path.resolve(__dirname, "../lib", name);
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  new Function("exports", "require", "module", code)(module.exports, name => overrides[name] ?? require(name), module);
  return module.exports;
}
const { SAMPLE_LORE, readLoreDraft } = load("studio-data.ts");
test("unsaved diagnostics send history and manual choices, and preserve server ordering and reasons", async () => {
  let called;
  const {previewLore} = load("studio-preview.ts", {"./api": {request: async (path, options) => {
    called = {path, body: JSON.parse(options.body)};
    return {items: [{id: SAMPLE_LORE[0].id, included: false, reason: "entry_budget_exceeded", order: null}], ai_called: false};
  }}});
  const messages = [{role: "user", text: "도서관"}];
  const results = await previewLore([SAMPLE_LORE[0]], messages, [SAMPLE_LORE[0].id]);
  assert.equal(called.path, "/products/studio/lore-diagnostics");
  assert.deepEqual(called.body.messages, messages);
  assert.deepEqual(called.body.manual_entry_ids, [SAMPLE_LORE[0].id]);
  assert.equal(results[0].included, false);
  assert.match(results[0].reason, /예산 초과/);
});
test("diagnostic failures propagate instead of falling back to browser matching", async () => {
  const {previewLore} = load("studio-preview.ts", {"./api": {request: async () => {throw new Error("offline");}}});
  await assert.rejects(previewLore(SAMPLE_LORE, []), /offline/);
});
test("draft restoration rejects malformed, duplicate, fractional and out-of-range values", () => {
  assert.deepEqual(readLoreDraft(JSON.stringify(SAMPLE_LORE)), SAMPLE_LORE);
  for (const raw of ["{", "null", "[]", JSON.stringify([{ ...SAMPLE_LORE[0], keywords: [4] }]), JSON.stringify([SAMPLE_LORE[0], SAMPLE_LORE[0]]), JSON.stringify([{ ...SAMPLE_LORE[0], scanDepth: 1.5 }]), JSON.stringify([{ ...SAMPLE_LORE[0], tokenBudget: 0 }])]) assert.equal(readLoreDraft(raw), null);
});
