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
const { sampleProject, createCharacter, createScene, readStudioProject } = load("studio-project.ts");
const { emptyWorkspace, blankProject, createWork, migrateWorkspace, readWorkspace, linkSource, updateProject, trashEntity, restoreTrash } = load("studio-workspace.ts");
const roundtrip = w => assert.deepEqual(readWorkspace(JSON.stringify(w)), w);
function setup() {
  const c = createCharacter(); c.name = "원본"; c.persona = "원본 성격"; c.assets = [{ id: "existing-image", name: "image.webp", usage: "portrait" }];
  const l = structuredClone(SAMPLE_LORE[0]);
  let w = { ...emptyWorkspace(), works: [createWork(), createWork()], characters: [c], lorebooks: [l] };
  for (const work of w.works) { w = linkSource(w, work.id, "character", c.id); w = linkSource(w, work.id, "lore", l.id); }
  const workId = w.works[0].id; const p = w.works[0].project;
  const s = createScene(p.characters[0].id, p.lorebooks[0].id); s.opening = "도입";
  w = updateProject(w, workId, p => ({ ...p, scenes: [s], work: { ...p.work, defaultSceneId: s.id } }));
  return { w, workId, c, l, s };
}
test("migration preserves all private content, assets and scene references without inventing originals", () => {
  const p = sampleProject(); p.work.title = "CHARX 초안"; p.characters[0].assets = [{ id: "saved-image", name: "portrait", usage: "portrait" }];
  const old = JSON.stringify(p); const w = migrateWorkspace(null, old, null);
  assert.equal(w.works.length, 1); assert.deepEqual(w.works[0].project, p); assert.deepEqual(w.characters, []); assert.deepEqual(w.lorebooks, []); roundtrip(w);
  assert.equal(migrateWorkspace("bad v3", old, null), null); assert.equal(migrateWorkspace(null, "bad v2", JSON.stringify(SAMPLE_LORE)), null);
  assert.deepEqual(migrateWorkspace(null, null, null), emptyWorkspace());
  assert.equal(migrateWorkspace(JSON.stringify(w), "bad old value", null).works[0].project.work.title, "CHARX 초안");
});
test("empty works survive reload and edits stay isolated from sources and another work", () => {
  assert.deepEqual(readStudioProject(JSON.stringify(blankProject())), blankProject());
  const { w, workId, c } = setup();
  const changed = updateProject(w, workId, p => ({ ...p, work: { ...p.work, title: "첫 작품" }, characters: p.characters.map(row => ({ ...row, persona: "작품 변경", tags: ["전용"] })) }));
  assert.equal(changed.characters[0].persona, c.persona); assert.equal(changed.works[1].project.characters[0].persona, c.persona); assert.deepEqual(changed.characters[0].tags, []);
  const sourceEdit = { ...changed, characters: changed.characters.map(row => ({ ...row, persona: "원본 변경" })) };
  assert.equal(sourceEdit.works[0].project.characters[0].persona, "작품 변경"); assert.equal(sourceEdit.works[1].project.characters[0].persona, c.persona); roundtrip(sourceEdit);
  const loreEdit = updateProject(sourceEdit, workId, p => ({ ...p, lorebooks: p.lorebooks.map(row => ({ ...row, content: "작품 로어 수정", keywords: ["전용 단어"] })) }));
  assert.equal(loreEdit.lorebooks[0].content, SAMPLE_LORE[0].content); assert.equal(loreEdit.works[1].project.lorebooks[0].content, SAMPLE_LORE[0].content);
  assert.notDeepEqual(loreEdit.works[0].project.lorebooks[0].keywords, loreEdit.lorebooks[0].keywords); roundtrip(loreEdit);
});
test("unlink clears only affected references and restore preserves subsequent scene edits", () => {
  let { w, workId, s } = setup(); const p = w.works[0].project; const cid = p.characters[0].id; const lid = p.lorebooks[0].id;
  w = trashEntity(w, "work-character", cid, workId); assert.equal(w.works[0].project.scenes[0].characterId, ""); assert.equal(w.characters.length, 1); assert.equal(w.works[1].project.characters.length, 1); roundtrip(w);
  const trashId = w.trash[0].id;
  w = updateProject(w, workId, p => ({ ...p, scenes: p.scenes.map(row => ({ ...row, opening: "후속 수정" })) }));
  w = restoreTrash(w, trashId); assert.equal(w.works[0].project.scenes[0].characterId, cid); assert.equal(w.works[0].project.scenes[0].opening, "후속 수정");
  w = trashEntity(w, "work-lore", lid, workId); assert.equal(w.works[0].project.scenes[0].placeId, ""); roundtrip(w);
  w = restoreTrash(w, w.trash[0].id); assert.equal(w.works[0].project.scenes[0].placeId, lid);
  w = updateProject(w, workId, p => ({ ...p, lorebooks: p.lorebooks.map(row => ({ ...row, category: "세계관" })) })); assert.equal(w.works[0].project.scenes[0].placeId, ""); roundtrip(w);
});
test("deleting an original keeps work copies and deleting parent requires parent restore first", () => {
  let { w, workId, c } = setup(); const cid = w.works[0].project.characters[0].id;
  w = trashEntity(w, "work-character", cid, workId); const child = w.trash[0].id;
  w = trashEntity(w, "work", workId); const parent = w.trash[1].id;
  assert.equal(restoreTrash(w, child), w);
  w = trashEntity(w, "character", c.id); assert.equal(w.characters.length, 0); assert.equal(w.works[0].project.characters[0].sourceId, undefined); roundtrip(w);
  w = restoreTrash(w, parent); w = restoreTrash(w, child);
  const p = w.works.find(row => row.id === workId).project;
  assert.equal(p.characters[0].assets[0].id, "existing-image"); assert.equal(p.characters[0].sourceId, undefined); assert.equal(p.scenes[0].characterId, cid); roundtrip(w);
  w = restoreTrash(w, w.trash[0].id); assert.equal(w.characters[0].id, c.id); assert.equal(w.works[0].project.characters[0].sourceId, undefined); roundtrip(w);
});
test("last scene removal, restoration and deleted referenced entities never leave dangling IDs", () => {
  let { w, workId, s } = setup(); w = trashEntity(w, "scene", s.id, workId);
  assert.equal(w.works[0].project.work.defaultSceneId, ""); assert.equal(w.works[0].project.scenes.length, 0); roundtrip(w);
  const sceneTrash = w.trash[0].id; w = trashEntity(w, "work-character", w.works[0].project.characters[0].id, workId);
  w = restoreTrash(w, sceneTrash); assert.equal(w.works[0].project.scenes[0].characterId, ""); assert.equal(w.works[0].project.work.defaultSceneId, s.id); roundtrip(w);
});
for (const kind of ["work-character", "work-lore"]) {
  test(`${kind}: scene and linked images can be trashed and restored independently`, () => {
    const { w, workId, s } = setup();
    const target = kind === "work-character" ? { kind: "character", id: s.characterId } : { kind: "lore_entry", id: s.placeId };
    const item = { imageItemId: crypto.randomUUID(), fileVersionId: crypto.randomUUID(), target,
      kind: kind === "work-character" ? "expression" : "situation", alt: "", tags: [] };
    const placement = { imageItemId: item.imageItemId, afterParagraph: 1 };
    const original = { ...s, opening: "편집한 본문", openingImagePlacements: [placement, placement] };
    const initial = updateProject(w, workId, p => ({ ...p, scenes: [original], chatImageItems: [item] }));
    for (const sceneDeletedFirst of [false, true]) {
      for (const sceneRestoredFirst of [false, true]) {
        const removeScene = w => trashEntity(w, "scene", s.id, workId);
        const unlink = w => trashEntity(w, kind, target.id, workId);
        let state = sceneDeletedFirst ? unlink(removeScene(initial)) : removeScene(unlink(initial));
        const restore = kind => {
          state = readWorkspace(JSON.stringify(restoreTrash(state, state.trash.find(t => t.kind === kind).id)));
          assert.ok(state);
        };
        restore(sceneRestoredFirst ? "scene" : kind);
        if (sceneRestoredFirst) assert.deepEqual(state.works[0].project.scenes[0].openingImagePlacements, []);
        else assert.deepEqual(state.works[0].project.scenes, []);
        restore(sceneRestoredFirst ? kind : "scene");
        assert.deepEqual(state.works[0].project.chatImageItems, [item]);
        assert.deepEqual(state.works[0].project.scenes, [original]);
      }
    }
  });
  test(`${kind}: reload restores file, pending request and ordered placements into the edited scenes`, () => {
    let { w, workId, s } = setup();
    const character = kind === "work-character";
    const target = character ? { kind: "character", id: s.characterId } : { kind: "lore_entry", id: s.placeId };
    const item = { imageItemId: crypto.randomUUID(), fileVersionId: crypto.randomUUID(), target,
      kind: character ? "expression" : "situation", alt: "설명", tags: ["장면"] };
    const otherCharacter = createCharacter();
    const other = { ...item, imageItemId: crypto.randomUUID(), target: { kind: "character", id: otherCharacter.id } };
    const upload = { requestId: crypto.randomUUID(), itemId: item.imageItemId,
      ...(character ? { kind: "upload", filename: "smile.png" } : { kind: "import", mediaId: crypto.randomUUID() }) };
    const a = { imageItemId: item.imageItemId, afterParagraph: 0 };
    const b = { imageItemId: other.imageItemId, afterParagraph: 0 };
    const placements = [a, b, a, a, { ...a, afterParagraph: 1 }];
    const otherScene = { ...createScene(otherCharacter.id, ""), opening: "다른 장면", openingImagePlacements: [a] };
    w = updateProject(w, workId, p => ({ ...p, characters: [...p.characters, otherCharacter],
      chatImageItems: [item, other], chatImageUploads: [upload],
      scenes: [{ ...s, openingImagePlacements: placements }, otherScene] }));
    const unlinked = readWorkspace(JSON.stringify(trashEntity(w, kind, target.id, workId)));
    assert.deepEqual(unlinked.works[0].project.chatImageItems, [other]);
    assert.deepEqual(unlinked.works[0].project.chatImageUploads, []);
    assert.deepEqual(unlinked.works[0].project.scenes.map(scene => scene.openingImagePlacements), [[b], []]);
    const newer = { ...other, imageItemId: crypto.randomUUID() };
    const added = { imageItemId: newer.imageItemId, afterParagraph: 1 };
    const edited = updateProject(unlinked, workId, p => ({ ...p,
      characters: p.characters.map(c => c.id === otherCharacter.id ? { ...c, persona: "편집한 설정" } : c),
      chatImageItems: [...p.chatImageItems, newer],
      scenes: p.scenes.map(scene => ({ ...scene, opening: "새 본문", openingImagePlacements: [...scene.openingImagePlacements, added] })),
    }));
    const restored = readWorkspace(JSON.stringify(restoreTrash(edited, edited.trash[0].id)));
    assert.deepEqual(restored.trash, []);
    const result = restored.works[0].project;
    assert.deepEqual(result.chatImageItems, [item, other, newer]);
    assert.deepEqual(result.chatImageUploads, [upload]);
    assert.deepEqual(result.scenes.map(scene => scene.openingImagePlacements), [[...placements, added], [a, added]]);
    assert.deepEqual(result.scenes.map(scene => scene.opening), ["새 본문", "새 본문"]);
    assert.equal(result.characters.find(c => c.id === otherCharacter.id).persona, "편집한 설정");
    assert.equal(character ? result.scenes[0].characterId : result.scenes[0].placeId, target.id);
    assert.deepEqual(restored.works[1], w.works[1]);

    const legacy = structuredClone(unlinked);
    delete legacy.trash[0].images;
    const fromLegacy = restoreTrash(readWorkspace(JSON.stringify(legacy)), legacy.trash[0].id);
    assert.ok(readWorkspace(JSON.stringify(fromLegacy)));
    assert.equal((character ? fromLegacy.works[0].project.characters : fromLegacy.works[0].project.lorebooks).some(row => row.id === target.id), true);
    assert.deepEqual(fromLegacy.works[0].project.chatImageItems, [other]);

    for (const corrupt of [
      images => { images.items[0].value.target.id = "unrelated"; },
      images => { images.uploads[0].value.itemId = other.imageItemId; },
      images => { images.scenes[0].placements[0].index = -1; },
    ]) {
      const invalid = structuredClone(unlinked);
      corrupt(invalid.trash[0].images);
      assert.equal(readWorkspace(JSON.stringify(invalid)), null);
    }
  });
}
test("stored schemas reject malformed trash, duplicate works and orphan source references", () => {
  const { w } = setup();
  for (const mutate of [
    v => { v.works.push(v.works[0]); },
    v => { v.works[0].project.characters[0].sourceId = "missing"; },
    v => { v.trash = [{ id: "x", label: "x", kind: "unknown", deletedAt: "today", data: {} }]; },
    v => { v.characters[0].assets[0].usage = "bad"; },
  ]) { const copy = structuredClone(w); mutate(copy); assert.equal(readWorkspace(JSON.stringify(copy)), null); }
});
