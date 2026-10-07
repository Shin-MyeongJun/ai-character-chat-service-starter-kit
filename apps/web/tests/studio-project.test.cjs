const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
const cache = new Map();
function load(name) {
  const filename = path.resolve(__dirname, "../lib", name);
  if (cache.has(filename)) return cache.get(filename);
  const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  const localRequire = specifier => specifier.startsWith("./") ? load(`${specifier.slice(2)}.ts`) : require(specifier);
  new Function("exports", "require", "module", code)(module.exports, localRequire, module);
  cache.set(filename, module.exports); return module.exports;
}
const { SAMPLE_LORE } = load("studio-data.ts");
const { sampleProject, readStudioProject, restoreStudioProject, duplicateScene } = load("studio-project.ts");

test("legacy migration preserves edited lore, attaches new scene references and keeps v2 authoritative", () => {
  const old = [{ ...SAMPLE_LORE[0], id: "custom-place", title: "내 장소", content: "수정된 설정", tags: ["내 태그"], scanDepth: 12 }];
  const migrated = restoreStudioProject(null, JSON.stringify(old));
  assert.deepEqual(migrated.lorebooks, old);
  assert.equal(migrated.scenes[0].placeId, "custom-place");
  assert.deepEqual(readStudioProject(JSON.stringify(migrated)), migrated);
  migrated.work.title = "새 작품";
  assert.equal(restoreStudioProject(JSON.stringify(migrated), JSON.stringify(old)).work.title, "새 작품");
  assert.equal(restoreStudioProject("corrupt", JSON.stringify(old)), null);
});
test("full draft restoration rejects dangling references, malformed assets and duplicate entities", () => {
  assert.deepEqual(readStudioProject(JSON.stringify(sampleProject())), sampleProject());
  const invalid = [
    draft => { draft.work.defaultSceneId = "missing"; },
    draft => { draft.scenes[0].characterId = "missing"; },
    draft => { draft.scenes[0].placeId = "world-rules"; },
    draft => { draft.characters[0].assets = [{ id: "a", name: "image", usage: "unknown" }]; },
    draft => { draft.characters[0].assets = [{ id: "a", name: "image", usage: "portrait" }, { id: "b", name: "image", usage: "portrait" }]; },
    draft => { draft.scenes.push(draft.scenes[0]); },
    draft => { draft.characters[0].tags = [2]; },
    draft => { draft.scenes[0].language = "unknown"; },
  ];
  for (const change of invalid) { const draft = structuredClone(sampleProject()); change(draft); assert.equal(readStudioProject(JSON.stringify(draft)), null); }
});
test("scene duplication creates a separate editable record while preserving character and location links", () => {
  const source = sampleProject().scenes[0];
  const copied = duplicateScene(source);
  assert.notEqual(copied.id, source.id);
  assert.equal(copied.characterId, source.characterId);
  assert.equal(copied.placeId, source.placeId);
  assert.equal(copied.opening, source.opening);
  copied.opening = "복사본의 도입";
  assert.notEqual(source.opening, copied.opening);
});
