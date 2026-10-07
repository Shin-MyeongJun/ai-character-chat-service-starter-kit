const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

// The project has no test runner dependency. Transpile the pure TS modules in memory.
function load(name) {
  const filename = path.resolve(__dirname, "../lib", name);
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  new Function("exports", "require", "module", code)(module.exports, require, module);
  return module.exports;
}
const { previewLore } = load("studio-preview.ts");
const { SAMPLE_LORE, readLoreDraft } = load("studio-data.ts");
const entry = overrides => ({ ...SAMPLE_LORE[0], exclusiveGroup: "", ...overrides });
const result = (overrides, messages) => previewLore([entry(overrides)], messages)[0];

test("Korean word boundaries distinguish a word from a larger word; aliases ignore case by default", () => {
  assert.equal(result({ partialMatch: false, keywords: ["도서관"] }, [{ role: "user", text: "도서관장" }]).included, false);
  assert.equal(result({ partialMatch: false, keywords: ["도서관"] }, [{ role: "user", text: "도서관!" }]).included, true);
  assert.equal(result({ keywords: ["library"] }, [{ role: "user", text: "LIBRARY" }]).included, true);
  assert.equal(result({ keywords: ["library"], caseSensitive: true }, [{ role: "user", text: "LIBRARY" }]).included, false);
});
test("scan depth and speaker filters exclude old and character-only triggers", () => {
  const messages = [{ role: "user", text: "도서관" }, { role: "character", text: "도서관" }, { role: "user", text: "안녕" }];
  assert.equal(result({ scanDepth: 1 }, messages).included, false);
  assert.equal(result({ scanDepth: 2, searchTarget: "user" }, messages).included, false);
  assert.equal(result({ scanDepth: 2, searchTarget: "all" }, messages).included, true);
});
test("all keywords can match across recent messages; a disabled entry stays excluded", () => {
  const messages = [{ role: "user", text: "도서관" }, { role: "user", text: "기록실" }];
  assert.equal(result({ match: "all", keywords: ["도서관", "기록실"] }, messages).included, true);
  assert.equal(result({ match: "all", keywords: ["도서관", "기록실", "library"] }, messages).included, false);
  assert.equal(result({ activation: "always", enabled: false }, messages).included, false);
});
test("exclusive groups choose by priority, then placement order, even if source order differs", () => {
  const rows = [entry({ id: "low", activation: "always", priority: "낮음", exclusiveGroup: "밤" }), entry({ id: "later", activation: "always", priority: "높음", order: 200, exclusiveGroup: "밤" }), entry({ id: "first", activation: "always", priority: "높음", order: 100, exclusiveGroup: "밤" })];
  const results = previewLore(rows, []);
  assert.deepEqual(results.filter(item => item.included).map(item => item.entry.id), ["first"]);
  assert.match(results.find(item => item.entry.id === "later").reason, /같은 그룹/);
});
test("draft restoration rejects malformed, duplicate, fractional and out-of-range values", () => {
  assert.deepEqual(readLoreDraft(JSON.stringify(SAMPLE_LORE)), SAMPLE_LORE);
  for (const raw of ["{", "null", "[]", JSON.stringify([{ ...SAMPLE_LORE[0], keywords: [4] }]), JSON.stringify([SAMPLE_LORE[0], SAMPLE_LORE[0]]), JSON.stringify([{ ...SAMPLE_LORE[0], scanDepth: 1.5 }]), JSON.stringify([{ ...SAMPLE_LORE[0], tokenBudget: 0 }])]) assert.equal(readLoreDraft(raw), null);
});
