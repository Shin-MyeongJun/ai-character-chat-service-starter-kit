const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const ts = require("typescript");

function setup() {
  const storage = new Map();
  const uploads = [];
  const uploaded = new Map();
  const writes = [];
  const draftReads = [];
  const publications = [];
  const retiredIds = new Set();
  let remote;
  let failImport = false;
  let loseSaveResponse = false;
  let loseUploadResponse = false;
  class ApiError extends Error {
    constructor(status) { super(String(status)); this.status = status; }
  }
  const api = {
    ApiError, getMe: async () => ({ id: "owner" }),
    async request(path, options = {}) {
      const productId = path.split("/")[2];
      if (path.endsWith("/studio-draft/image-retirements")) {
        if (!remote) throw new ApiError(404);
        return { revision: remote.revision, retired_image_item_ids: [...retiredIds] };
      }
      if (path.endsWith("/studio-draft")) {
        if (!options.method) {
          draftReads.push(productId);
          if (!remote) throw new ApiError(404);
          return structuredClone(remote);
        }
        const payload = JSON.parse(options.body);
        assert.equal(payload.expected_revision, remote?.revision ?? null);
        assert.equal("chatImageUploads" in payload.document, false);
        const ids = new Set(payload.document.chatImageItems?.map(item => item.imageItemId));
        if ([...ids].some(id => retiredIds.has(id))) throw new ApiError(422);
        for (const item of remote?.document.chatImageItems ?? []) {
          if (!ids.has(item.imageItemId)) retiredIds.add(item.imageItemId);
        }
        remote = { product_id: productId, revision: (remote?.revision ?? 0) + 1, document: payload.document };
        writes.push(structuredClone(remote));
        if (loseSaveResponse) { loseSaveResponse = false; throw new Error("save response lost"); }
        return structuredClone(remote);
      }
      if (path.endsWith("/studio-publication")) {
        assert.equal(options.method, "POST");
        const payload = JSON.parse(options.body);
        assert.equal(payload.expected_revision, remote.revision);
        publications.push(payload);
        return api.publish(payload);
      }
      const key = options.headers.get("Idempotency-Key");
      uploads.push(key);
      if (path.endsWith("/imports")) {
        if (failImport) throw new Error("import interrupted");
        assert.equal(JSON.parse(options.body).media_id, "10000000-0000-4000-8000-000000000001");
      } else {
        assert.equal(options.headers.get("X-Filename"), "one.png");
        assert.equal(await options.body.text(), "test file");
      }
      if (!uploaded.has(key)) uploaded.set(key, crypto.randomUUID());
      if (loseUploadResponse) { loseUploadResponse = false; throw new Error("upload response lost"); }
      return { product_id: productId, file_version_id: uploaded.get(key), state: "ready", content_url: "/owner-preview" };
    },
    publish: () => ({ snapshot_id: "snapshot", version: 1, summary: "첫 발행" }),
  };
  function reopen() {
    const modules = new Map([
      ["api", api], ["studio-assets", { readImage: async () => new Blob(["test file"], { type: "image/png" }) }],
    ]);
    function load(name) {
      if (modules.has(name)) return modules.get(name);
      const path = resolve(__dirname, "../lib", name + ".ts");
      const code = ts.transpileModule(readFileSync(path, "utf8"), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      }).outputText;
      const module = { exports: {} };
      const localStorage = {
        get length() { return storage.size; }, key: index => [...storage.keys()][index] ?? null,
        getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value),
      };
      new Function("exports", "require", "module", "localStorage", code)(
        module.exports, specifier => load(specifier.slice(2)), module, localStorage,
      );
      modules.set(name, module.exports);
      return module.exports;
    }
    return { scope: new (load("studio-scope").StudioScope)("owner", ""), ...load("studio-server"), ...load("studio-project"), ...load("studio-chat-images"), ...load("studio-workspace") };
  }
  return {
    reopen, uploads, uploaded, writes, draftReads, publications, api,
    failImport: value => { failImport = value; },
    loseSaveResponse: () => { loseSaveResponse = true; },
    loseUploadResponse: () => { loseUploadResponse = true; },
    remoteEdit: () => {
      remote.revision++;
      remote.document.work.title = "Concurrent editor";
    },
  };
}

function pendingWork(client) {
  const project = client.sampleProject();
  const target = { kind: "character", id: project.characters[0].id };
  const first = { ...client.addChatImageItem(target, "expression"), tags: ["미소"] };
  const second = { ...client.addChatImageItem(target, "expression"), tags: ["미소"] };
  project.chatImageItems = [first, second];
  project.scenes[0].openingImagePlacements = [{ imageItemId: second.imageItemId, afterParagraph: 1 }];
  project.chatImageUploads = [
    { itemId: first.imageItemId, requestId: crypto.randomUUID(), kind: "upload", filename: "one.png" },
    { itemId: second.imageItemId, requestId: crypto.randomUUID(), kind: "import", mediaId: "10000000-0000-4000-8000-000000000001" },
  ];
  return { id: "work", project };
}

test("trash restore distinguishes committed retirements from local images, even after lost save response", async t => {
  const server = setup();
  const client = server.reopen();
  const work = pendingWork(client);
  let workspace = { ...client.emptyWorkspace(), works: [work] };
  const owner = t.mock.method(server.api, "getMe");
  assert.deepEqual(await client.getRetiredStudioImageIds(client.scope, work), new Set());
  assert.equal(owner.mock.callCount(), 0);

  const saved = await client.saveServerWork(client.scope, work);
  const local = client.addChatImageItem(saved.project.chatImageItems[0].target, "expression");
  const pending = { ...work.project.chatImageUploads[0], itemId: local.imageItemId, requestId: crypto.randomUUID() };
  const placement = { imageItemId: local.imageItemId, afterParagraph: 0 };
  workspace = client.updateProject(workspace, work.id, () => ({
    ...saved.project, chatImageItems: [...saved.project.chatImageItems, local], chatImageUploads: [pending],
    scenes: saved.project.scenes.map(scene => ({ ...scene, openingImagePlacements: [...(scene.openingImagePlacements ?? []), placement] })),
  }));
  const before = workspace.works[0].project;
  workspace = client.trashEntity(workspace, "work-character", local.target.id, work.id);
  const trash = workspace.trash[0].id;
  async function restore(client) {
    const ids = await client.getRetiredStudioImageIds(client.scope, workspace.works[0]);
    return client.readWorkspace(JSON.stringify(client.restoreTrash(workspace, trash, ids))).works[0].project;
  }
  const unsaved = await restore(client);
  assert.deepEqual(unsaved.chatImageItems, before.chatImageItems);
  assert.deepEqual(unsaved.scenes, before.scenes);
  assert.deepEqual(unsaved.chatImageUploads, [pending]);
  owner.mock.mockImplementationOnce(async () => { throw new Error("offline"); });
  await assert.rejects(restore(client), /offline/);
  assert.equal(workspace.trash[0].id, trash);

  server.loseSaveResponse();
  await assert.rejects(client.saveServerWork(client.scope, workspace.works[0]), /save response lost/);
  const reopened = server.reopen();
  const restored = await restore(reopened);
  assert.deepEqual(restored.chatImageItems, [local]);
  assert.deepEqual(restored.chatImageUploads, [pending]);
  assert.deepEqual(restored.scenes.map(scene => scene.openingImagePlacements), [[placement], [placement]]);
  assert.ok(restored.characters.some(row => row.id === local.target.id));
  assert.equal(server.writes.at(-1).document.chatImageItems.length, 0);
  // A second check against the acknowledged revision makes the same decision.
  const confirmed = await restore(reopened);
  assert.deepEqual(confirmed, restored);
  const resaved = await reopened.saveServerWork(reopened.scope, { ...work, project: confirmed });
  assert.deepEqual(resaved.project.chatImageItems.map(item => item.imageItemId), [local.imageItemId]);
  assert.ok(resaved.project.chatImageItems[0].fileVersionId);
});

test("restoring a deleted scene after a confirmed lore unlink keeps only unretired placements", async () => {
  const client = setup().reopen();
  const work = pendingWork(client);
  const lore = work.project.lorebooks[0];
  const target = { kind: "lore_entry", id: lore.id };
  work.project.chatImageItems = work.project.chatImageItems.map(item => ({ ...item, kind: "situation", target }));
  const saved = await client.saveServerWork(client.scope, work);
  const pending = client.addChatImageItem(target, "situation");
  const upload = { ...work.project.chatImageUploads[0], itemId: pending.imageItemId, requestId: crypto.randomUUID() };
  const placement = { imageItemId: pending.imageItemId, afterParagraph: 1 };
  const scene = saved.project.scenes[0];
  let state = { ...client.emptyWorkspace(), works: [{ ...work, project: {
    ...saved.project, chatImageItems: [...saved.project.chatImageItems, pending], chatImageUploads: [upload],
    scenes: [{ ...scene, openingImagePlacements: [...scene.openingImagePlacements, placement, placement] }],
  } }] };
  state = client.trashEntity(state, "scene", scene.id, work.id);
  state = client.trashEntity(state, "work-lore", lore.id, work.id);
  await client.saveServerWork(client.scope, state.works[0]);
  const retired = await client.getRetiredStudioImageIds(client.scope, state.works[0]);
  assert.deepEqual(retired, new Set(saved.project.chatImageItems.map(item => item.imageItemId)));
  const [deletedScene, unlinkedLore] = state.trash;
  // Older browsers left the scene's placements in its own trash record.
  const legacy = structuredClone(state);
  legacy.trash[0].data.openingImagePlacements = [...scene.openingImagePlacements, placement, placement];
  legacy.trash[1].images.scenes = [];
  const partial = client.restoreTrash(client.readWorkspace(JSON.stringify(legacy)), unlinkedLore.id, retired);
  assert.deepEqual(client.restoreTrash(partial, deletedScene.id).works[0].project.scenes[0].openingImagePlacements, [placement, placement]);
  state = client.restoreTrash(state, unlinkedLore.id, retired);
  state = client.readWorkspace(JSON.stringify(client.restoreTrash(state, deletedScene.id)));
  assert.deepEqual(state.works[0].project.chatImageItems, [pending]);
  assert.deepEqual(state.works[0].project.chatImageUploads, [upload]);
  assert.deepEqual(state.works[0].project.scenes[0].openingImagePlacements, [placement, placement]);
  const resaved = await client.saveServerWork(client.scope, state.works[0]);
  assert.deepEqual(resaved.project.chatImageItems.map(item => item.imageItemId), [pending.imageItemId]);
  assert.ok(resaved.project.chatImageItems[0].fileVersionId);
  assert.deepEqual(resaved.project.scenes[0].openingImagePlacements, [placement, placement]);
});

test("partial upload, lost CAS response and reconnect preserve ready results and the saved placement", async () => {
  const server = setup();
  let client = server.reopen();
  const work = pendingWork(client);
  const [upload, imported] = work.project.chatImageUploads;
  server.loseUploadResponse();
  await assert.rejects(client.saveServerWork(client.scope, work), /upload response lost/);
  assert.equal(server.writes.length, 1);
  assert.equal(server.uploaded.size, 1);

  client = server.reopen();
  server.failImport(true);
  await assert.rejects(client.saveServerWork(client.scope, { ...work, project: client.readStudioProject(JSON.stringify(work.project)) }), /import interrupted/);
  assert.equal(server.writes.length, 1);
  assert.deepEqual(server.uploads, [upload.requestId, upload.requestId, imported.requestId]);
  assert.equal(server.uploaded.size, 1);

  server.failImport(false);
  server.loseSaveResponse();
  await assert.rejects(client.saveServerWork(client.scope, work), /save response lost/);
  assert.equal(server.writes.length, 2);
  const committed = server.writes[1];
  client = server.reopen();
  const replay = await client.saveServerWork(client.scope, work);
  assert.equal(replay.revision, committed.revision);
  assert.deepEqual(server.uploads, [upload.requestId, upload.requestId, imported.requestId, imported.requestId]);
  assert.equal(server.writes.length, 2);
  const reopened = await client.loadServerWork(client.scope, committed.product_id);
  assert.deepEqual(reopened.project.chatImageItems.map(item => item.imageItemId), work.project.chatImageItems.map(item => item.imageItemId));
  assert.deepEqual(reopened.project.scenes[0].openingImagePlacements, work.project.scenes[0].openingImagePlacements);
  assert.equal(reopened.project.chatImageItems[0].fileVersionId, server.uploaded.get(upload.requestId));

  const previous = reopened.project.chatImageItems[0];
  const replacement = { ...upload, requestId: crypto.randomUUID() };
  reopened.project.chatImageUploads = [replacement];
  const replaced = await client.saveServerWork(client.scope, reopened);
  assert.equal(replaced.project.chatImageItems[0].imageItemId, previous.imageItemId);
  assert.notEqual(replaced.project.chatImageItems[0].fileVersionId, previous.fileVersionId);
});

test("a concurrent draft save preserves both the remote draft and the completed upload receipt", async () => {
  const server = setup();
  let client = server.reopen();
  const work = pendingWork(client);
  server.failImport(true);
  await assert.rejects(client.saveServerWork(client.scope, work), /import interrupted/);
  server.failImport(false);
  server.remoteEdit();
  await assert.rejects(client.saveServerWork(client.scope, work), /다른 기기/);
  assert.equal(server.writes.length, 1);
  assert.equal(server.uploaded.size, 2);
  client = server.reopen();
  await assert.rejects(client.saveServerWork(client.scope, work), /다른 기기/);
  assert.equal(server.uploads.length, 3);
  const reopened = await client.loadServerWork(client.scope, server.writes[0].product_id);
  assert.equal(reopened.project.work.title, "Concurrent editor");
  assert.equal(reopened.project.chatImageItems, undefined);
});

async function replacementWorkspace() {
  const server = setup();
  const client = server.reopen();
  const work = pendingWork(client);
  const [replacement, secondReplacement] = work.project.chatImageUploads;
  delete work.project.chatImageUploads;
  for (const item of work.project.chatImageItems) item.fileVersionId = crypto.randomUUID();
  const versionA = work.project.chatImageItems[0].fileVersionId;
  let workspace = { ...client.emptyWorkspace(), works: [work, client.createWork()] };
  function acknowledge(submitted, saved) {
    workspace = client.applySavedStudioWork(workspace, submitted, saved.project);
  }
  const { productId } = await client.saveServerWork(client.scope, work, acknowledge);
  function edit(change) { workspace = client.updateProject(workspace, work.id, change); }
  edit(project => ({ ...project, chatImageUploads: [replacement] }));
  return {
    server, client, productId, versionA, replacement, secondReplacement, edit,
    get workspace() { return workspace; },
    get project() { return workspace.works[0].project; },
    publish: () => client.publishServerWork(client.scope, workspace.works[0], "model", "low", "첫 발행", "안내", acknowledge),
  };
}

function assertReplacementSaved(project, itemId, versionB) {
  assert.ok(versionB);
  assert.equal(project.chatImageItems.find(item => item.imageItemId === itemId)?.fileVersionId, versionB);
  assert.deepEqual(project.chatImageUploads ?? [], []);
}

test("direct publication acknowledges the replacement in the workspace before posting the release", async t => {
  const tab = await replacementWorkspace();
  const { server, replacement, productId } = tab;
  const reads = server.draftReads.length;
  const publish = server.api.publish;
  t.mock.method(server.api, "publish", payload => {
    assertReplacementSaved(tab.project, replacement.itemId, server.uploaded.get(replacement.requestId));
    return publish(payload);
  });
  await tab.publish();
  const versionB = server.uploaded.get(replacement.requestId);
  assert.notEqual(versionB, tab.versionA);
  assert.equal(server.draftReads.length, reads + 1);
  assert.deepEqual(server.uploads, [replacement.requestId]);
  const reopened = server.reopen();
  assertReplacementSaved(reopened.readWorkspace(JSON.stringify(tab.workspace)).works[0].project, replacement.itemId, versionB);
  assertReplacementSaved((await reopened.loadServerWork(reopened.scope, productId)).project, replacement.itemId, versionB);
});

for (const lost of [false, true]) {
  test(`publication ${lost ? "response loss" : "rejection"} leaves the saved replacement ready for retry`, async t => {
    const tab = await replacementWorkspace();
    const { server, replacement } = tab;
    const release = server.api.publish();
    const publish = t.mock.method(server.api, "publish", () => release);
    publish.mock.mockImplementationOnce(() => {
      if (lost) throw new TypeError("connection closed");
      throw new server.api.ApiError(422);
    });
    await assert.rejects(tab.publish(), lost ? /초안을 서버에 저장.*발행 결과를 확인할 수 없/ : /초안을 서버에 저장.*발행에 실패/);
    const versionB = server.uploaded.get(replacement.requestId);
    assertReplacementSaved(tab.project, replacement.itemId, versionB);
    assertReplacementSaved((await tab.client.loadServerWork(tab.client.scope, tab.productId)).project, replacement.itemId, versionB);
    const writes = server.writes.length;
    assert.deepEqual((await tab.publish()).release, release);
    assert.equal(server.publications.length, 2);
    assert.deepEqual(server.publications[1], server.publications[0]);
    assert.equal(server.writes.length, writes);
    assert.deepEqual(server.uploads, [replacement.requestId]);
    assertReplacementSaved(tab.project, replacement.itemId, versionB);
  });
}

test("save acknowledgement merges into newer text, image metadata and replacement requests on the submitted work", async () => {
  const tab = await replacementWorkspace();
  const { server, replacement, secondReplacement } = tab;
  const otherWork = tab.workspace.works[1];
  tab.edit(project => ({ ...project, chatImageUploads: [replacement, secondReplacement] }));
  const publishing = tab.publish();
  const newer = { ...secondReplacement, requestId: crypto.randomUUID() };
  tab.edit(project => ({
    ...project, work: { ...project.work, title: "저장 중 수정" },
    chatImageItems: project.chatImageItems.map(item => ({ ...item, alt: "새 설명" })),
    chatImageUploads: [replacement, newer],
  }));
  await publishing;
  assert.equal(tab.project.work.title, "저장 중 수정");
  assert.equal(tab.project.chatImageItems[0].alt, "새 설명");
  assert.equal(tab.project.chatImageItems[0].fileVersionId, server.uploaded.get(replacement.requestId));
  assert.deepEqual(tab.project.chatImageUploads, [newer]);
  assert.equal(tab.workspace.works[1], otherWork);
  const remote = await tab.client.loadServerWork(tab.client.scope, tab.productId);
  assert.notEqual(remote.project.work.title, tab.project.work.title);
  assert.equal(remote.project.chatImageItems[1].fileVersionId, server.uploaded.get(secondReplacement.requestId));
});

test("a conflicting save keeps the browser replacement pending and never starts publication", async () => {
  const tab = await replacementWorkspace();
  tab.server.remoteEdit();
  await assert.rejects(tab.publish(), /다른 기기/);
  assert.equal(tab.project.chatImageItems[0].fileVersionId, tab.versionA);
  assert.deepEqual(tab.project.chatImageUploads, [tab.replacement]);
  assert.deepEqual(tab.server.publications, []);
});

test("an unacknowledged draft write keeps the replacement pending until a retry confirms it", async () => {
  const tab = await replacementWorkspace();
  const { server, replacement } = tab;
  server.loseSaveResponse();
  await assert.rejects(tab.publish(), /save response lost/);
  assert.deepEqual(server.publications, []);
  assert.equal(tab.project.chatImageItems[0].fileVersionId, tab.versionA);
  assert.deepEqual(tab.project.chatImageUploads, [replacement]);
  const writes = server.writes.length;
  await tab.publish();
  assertReplacementSaved(tab.project, replacement.itemId, server.uploaded.get(replacement.requestId));
  assert.equal(server.writes.length, writes);
  assert.deepEqual(server.uploads, [replacement.requestId]);
});

test("a confirmed replacement survives an interrupted character media link and its retry", async t => {
  const tab = await replacementWorkspace();
  const { server, replacement } = tab;
  const asset = { id: "portrait", name: "portrait.png", usage: "portrait" };
  tab.edit(project => ({
    ...project,
    characters: project.characters.map((row, i) => i ? row : { ...row, assets: [asset] }),
  }));
  const request = server.api.request;
  const mediaId = crypto.randomUUID();
  let interrupted = true;
  t.mock.method(server.api, "request", (path, options) => {
    if (path.endsWith("/studio-components")) {
      if (interrupted) throw new Error("prepare interrupted");
      return { characters: { erin: "server-character" } };
    }
    if (path === "/characters/server-character/media/uploads") {
      tab.edit(project => ({
        ...project,
        characters: project.characters.map((row, i) => i ? row : { ...row, name: "저장 중 바꾼 이름" }),
      }));
      return { media_id: mediaId };
    }
    return request(path, options);
  });
  await assert.rejects(tab.publish(), /prepare interrupted/);
  const versionB = server.uploaded.get(replacement.requestId);
  assertReplacementSaved(tab.project, replacement.itemId, versionB);
  assert.deepEqual(tab.project.characters[0].assets, [asset]);
  assert.deepEqual(server.publications, []);
  interrupted = false;
  await tab.publish();
  assertReplacementSaved(tab.project, replacement.itemId, versionB);
  assert.equal(tab.project.characters[0].assets[0].mediaId, mediaId);
  assert.equal(tab.project.characters[0].name, "저장 중 바꾼 이름");
  assert.deepEqual(server.uploads, [replacement.requestId]);
});
