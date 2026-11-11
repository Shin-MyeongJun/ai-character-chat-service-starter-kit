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
      if (path.endsWith("/studio-draft")) {
        if (!options.method) {
          if (!remote) throw new ApiError(404);
          return structuredClone(remote);
        }
        const payload = JSON.parse(options.body);
        assert.equal(payload.expected_revision, remote?.revision ?? null);
        assert.equal("chatImageUploads" in payload.document, false);
        remote = { product_id: productId, revision: (remote?.revision ?? 0) + 1, document: payload.document };
        writes.push(structuredClone(remote));
        if (loseSaveResponse) { loseSaveResponse = false; throw new Error("save response lost"); }
        return structuredClone(remote);
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
        getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value),
      };
      new Function("exports", "require", "module", "localStorage", code)(
        module.exports, specifier => load(specifier.slice(2)), module, localStorage,
      );
      modules.set(name, module.exports);
      return module.exports;
    }
    return { ...load("studio-server"), ...load("studio-project"), ...load("studio-chat-images") };
  }
  return {
    reopen, uploads, uploaded, writes,
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

test("partial upload, lost CAS response and reconnect preserve ready results and the saved placement", async () => {
  const server = setup();
  let client = server.reopen();
  const work = pendingWork(client);
  const [upload, imported] = work.project.chatImageUploads;
  server.loseUploadResponse();
  await assert.rejects(client.saveServerWork(work), /upload response lost/);
  assert.equal(server.writes.length, 1);
  assert.equal(server.uploaded.size, 1);

  client = server.reopen();
  server.failImport(true);
  await assert.rejects(client.saveServerWork({ ...work, project: client.readStudioProject(JSON.stringify(work.project)) }), /import interrupted/);
  assert.equal(server.writes.length, 1);
  assert.deepEqual(server.uploads, [upload.requestId, upload.requestId, imported.requestId]);
  assert.equal(server.uploaded.size, 1);

  server.failImport(false);
  server.loseSaveResponse();
  await assert.rejects(client.saveServerWork(work), /save response lost/);
  assert.equal(server.writes.length, 2);
  const committed = server.writes[1];
  client = server.reopen();
  const replay = await client.saveServerWork(work);
  assert.equal(replay.revision, committed.revision);
  assert.deepEqual(server.uploads, [upload.requestId, upload.requestId, imported.requestId, imported.requestId]);
  assert.equal(server.writes.length, 2);
  const reopened = await client.loadServerWork(committed.product_id);
  assert.deepEqual(reopened.project.chatImageItems.map(item => item.imageItemId), work.project.chatImageItems.map(item => item.imageItemId));
  assert.deepEqual(reopened.project.scenes[0].openingImagePlacements, work.project.scenes[0].openingImagePlacements);
  assert.equal(reopened.project.chatImageItems[0].fileVersionId, server.uploaded.get(upload.requestId));

  const previous = reopened.project.chatImageItems[0];
  const replacement = { ...upload, requestId: crypto.randomUUID() };
  reopened.project.chatImageUploads = [replacement];
  const replaced = await client.saveServerWork(reopened);
  assert.equal(replaced.project.chatImageItems[0].imageItemId, previous.imageItemId);
  assert.notEqual(replaced.project.chatImageItems[0].fileVersionId, previous.fileVersionId);
});

test("a concurrent draft save preserves both the remote draft and the completed upload receipt", async () => {
  const server = setup();
  let client = server.reopen();
  const work = pendingWork(client);
  server.failImport(true);
  await assert.rejects(client.saveServerWork(work), /import interrupted/);
  server.failImport(false);
  server.remoteEdit();
  await assert.rejects(client.saveServerWork(work), /다른 기기/);
  assert.equal(server.writes.length, 1);
  assert.equal(server.uploaded.size, 2);
  client = server.reopen();
  await assert.rejects(client.saveServerWork(work), /다른 기기/);
  assert.equal(server.uploads.length, 3);
  const reopened = await client.loadServerWork(server.writes[0].product_id);
  assert.equal(reopened.project.work.title, "Concurrent editor");
  assert.equal(reopened.project.chatImageItems, undefined);
});
