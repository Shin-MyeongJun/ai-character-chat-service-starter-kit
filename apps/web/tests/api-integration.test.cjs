const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

function setup(t) {
  const cache = new Map();
  function load(name) {
    const file = path.resolve(__dirname, "../lib", name);
    if (cache.has(file)) return cache.get(file);
    const code = ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    const module = { exports: {} };
    cache.set(file, module.exports);
    new Function("exports", "require", "module", code)(module.exports, name => name.startsWith("./") ? load(`${name.slice(2)}.ts`) : require(name), module);
    return module.exports;
  }
  const data = new Map();
  let queue = Promise.resolve();
  const originals = new Map();
  for (const [key, value] of Object.entries({
    localStorage: { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, String(value)), removeItem: key => data.delete(key) },
    window: new EventTarget(),
    navigator: { locks: { request: (_name, callback) => { const result = queue.then(callback); queue = result.catch(() => {}); return result; } } },
  })) {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
    Object.defineProperty(globalThis, key, { configurable: true, value });
  }
  t.after(() => { for (const [key, descriptor] of originals) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  return { api: load("api.ts"), recent: load("recent-chats.ts"), studio: load("studio-server.ts"), workspace: load("studio-workspace.ts"), project: load("studio-project.ts"), data, newClient: () => { cache.clear(); return load("api.ts"); } };
}
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const expired = () => json({ error: { code: "invalid_token" } }, 401);

test("ascending message pages include messages beyond 100 and the newest answer", async t => {
  const { api } = setup(t);
  const calls = [];
  t.mock.method(globalThis, "fetch", async url => {
    calls.push(url);
    const cursor = new URL(url, "https://test").searchParams.get("cursor");
    const from = cursor ? Number(cursor) : 0;
    const end = Math.min(from + 100, 205);
    return json({ items: Array.from({ length: end - from }, (_, i) => ({ id: String(from + i + 1), position: from + i + 1, content: "message" })), next_cursor: end < 205 ? String(end) : null });
  });
  const items = await api.listConversationMessages("conversation");
  assert.equal(items.length, 205);
  assert.equal(items.at(-1).position, 205);
  assert.equal(calls.length, 3);
  assert.match(calls[2], /cursor=200/);
});

test("repeated message cursor fails instead of looping forever", async t => {
  const { api } = setup(t);
  t.mock.method(globalThis, "fetch", async () => json({ items: [], next_cursor: "same" }));
  await assert.rejects(api.listConversationMessages("conversation"), /did not advance/);
});

test("CSRF expiry is recovered once with exactly the same mutation body and request key", async t => {
  const { api } = setup(t);
  let issued = 0;
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/auth/csrf")) return json({ csrf_token: `csrf-${++issued}` });
    requests.push(options);
    if (requests.length === 1) return json({ error: { code: "csrf_failed" } }, 403);
    return json({ id: "saved" });
  });
  assert.equal((await api.createMessage("c", "hello", "original-key")).id, "saved");
  assert.equal(requests.length, 2);
  assert.equal(requests[0].body, requests[1].body);
  assert.equal(requests[1].headers.get("X-CSRF-Token"), "csrf-2");
});

test("persistent CSRF failure stops after one recovery", async t => {
  const { api } = setup(t);
  let posts = 0;
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/auth/csrf")) return json({ csrf_token: "csrf" });
    posts++;
    return json({ error: { code: "csrf_failed" } }, 403);
  });
  await assert.rejects(api.createMessage("c", "hello", "key"), { code: "csrf_failed" });
  assert.equal(posts, 2);
});

test("parallel expired requests share one refresh and retry their original requests", async t => {
  const { api } = setup(t);
  let valid = false, refreshes = 0;
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/auth/csrf")) return json({ csrf_token: "csrf" });
    if (url.endsWith("/auth/refresh")) { refreshes++; valid = true; return json({ id: "owner" }); }
    return valid ? json({ id: "owner" }) : expired();
  });
  const values = await Promise.all([api.getMe(), api.request("/products/p"), api.request("/conversations/c/start")]);
  assert.equal(values.length, 3);
  assert.ok(values.every(value => value.id === "owner"));
  assert.equal(refreshes, 1);
});

test("independent tab clients serialize refresh and recheck access under the lock", async t => {
  const first = setup(t);
  const second = first.newClient();
  let valid = false, refreshes = 0;
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/auth/csrf")) return json({ csrf_token: "csrf" });
    if (url.endsWith("/auth/refresh")) { refreshes++; valid = true; return json({ id: "owner" }); }
    return valid ? json({ id: "owner" }) : expired();
  });
  await Promise.all([first.api.getMe(), second.getMe()]);
  assert.equal(refreshes, 1);
});

test("lost refresh response is not replayed and a new login restores recovery", async t => {
  const { api } = setup(t);
  let refreshes = 0;
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/auth/csrf")) return json({ csrf_token: "csrf" });
    if (url.endsWith("/auth/login")) return json({ id: "new-owner" });
    if (url.endsWith("/auth/refresh")) { refreshes++; throw new TypeError("response lost"); }
    return expired();
  });
  await assert.rejects(api.getMe(), /response lost/);
  await assert.rejects(api.getMe(), { code: "refresh_uncertain" });
  assert.equal(refreshes, 1);
  await api.login("user@example.com", "password");
  await assert.rejects(api.getMe(), /response lost/);
  assert.equal(refreshes, 2);
});

test("bad login credentials never trigger session refresh", async t => {
  const { api } = setup(t);
  const paths = [];
  t.mock.method(globalThis, "fetch", async url => {
    paths.push(url);
    return url.endsWith("/auth/csrf") ? json({ csrf_token: "csrf" }) : json({ error: { code: "invalid_credentials" } }, 401);
  });
  await assert.rejects(api.login("user@example.com", "wrong"), { code: "invalid_credentials" });
  assert.ok(!paths.some(url => url.endsWith("/refresh")));
});

test("recent conversation previews stay within their owner and legacy real rows are never adopted", t => {
  const { recent, data } = setup(t);
  data.set(recent.RECENT_CHATS_KEY, JSON.stringify([{ id: "old-real", title: "private old title", lastMessage: "secret" }, { id: "demo-archive", title: "demo" }]));
  recent.setRecentChatOwner("a");
  recent.upsertRecentChat({ id: "real-a", title: "A", lastMessage: "A secret" });
  recent.setRecentChatOwner("b");
  recent.upsertRecentChat({ id: "real-b", title: "B", lastMessage: "B secret" });
  assert.deepEqual(recent.readRecentChats().map(row => row.id).sort(), ["demo-archive", "real-b"]);
  recent.setRecentChatOwner(null);
  assert.deepEqual(recent.readRecentChats().map(row => row.id), ["demo-archive"]);
  recent.setRecentChatOwner("a");
  assert.equal(recent.readRecentChats().find(row => row.id === "real-a").lastMessage, "A secret");
  assert.ok(!recent.readRecentChats().some(row => row.id === "old-real"));
});

test("lost studio save response resumes by reading the same server document", async t => {
  const { studio, workspace } = setup(t);
  const work = { id: "local-work", project: workspace.blankProject() };
  let stored = null, puts = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/auth/me")) return json({ id: "owner" });
    if (url.endsWith("/auth/csrf")) return json({ csrf_token: "csrf" });
    if (url.endsWith("/studio-draft") && (options.method ?? "GET") === "GET") return stored ? json(stored) : json({ detail: "missing" }, 404);
    if (url.endsWith("/studio-draft") && options.method === "PUT") {
      puts++;
      stored = { product_id: url.split("/").at(-2), revision: 1, document: JSON.parse(options.body).document, updated_at: new Date().toISOString() };
      if (puts === 1) throw new TypeError("response lost");
      return json(stored);
    }
    throw new Error(`Unexpected ${url}`);
  });
  await assert.rejects(studio.saveServerWork(work), /response lost/);
  assert.deepEqual(await studio.saveServerWork(work), { productId: stored.product_id, revision: 1 });
  assert.equal(puts, 1);
});

test("studio save refuses to overwrite a different device's edits", async t => {
  const { studio, workspace } = setup(t);
  const work = { id: "local-work", project: workspace.blankProject() };
  let stored = null, puts = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/auth/me")) return json({ id: "owner" });
    if (url.endsWith("/auth/csrf")) return json({ csrf_token: "csrf" });
    if (url.endsWith("/studio-draft") && (options.method ?? "GET") === "GET") return stored ? json(stored) : json({ detail: "missing" }, 404);
    if (url.endsWith("/studio-draft") && options.method === "PUT") {
      puts++;
      stored = { product_id: url.split("/").at(-2), revision: puts, document: JSON.parse(options.body).document, updated_at: new Date().toISOString() };
      return json(stored);
    }
    throw new Error(`Unexpected ${url}`);
  });
  await studio.saveServerWork(work);
  stored.document.work.title = "Edited elsewhere";
  stored.revision = 2;
  await assert.rejects(studio.saveServerWork({ ...work, project: { ...work.project, work: { ...work.project.work, title: "Local edit" } } }), /다른 기기/);
  assert.equal(puts, 1);
});

test("restored studio copy detaches browser-only source links and saves without duplicating", async t => {
  const { studio, project } = setup(t);
  const remoteProject = project.sampleProject();
  remoteProject.characters[0].sourceId = "browser-only-character";
  remoteProject.lorebooks[0].sourceId = "browser-only-lore";
  const productId = crypto.randomUUID();
  let puts = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/auth/me")) return json({ id: "owner" });
    if (url.endsWith("/products/mine?offset=0&limit=100")) return json([{ id: productId }]);
    if (url.endsWith("/studio-draft") && (options.method ?? "GET") === "GET") return json({
      product_id: productId, revision: 3, document: { ...remoteProject, clientWorkId: "original-work" }, updated_at: new Date().toISOString(),
    });
    if (options.method === "PUT") { puts++; throw new Error("Unexpected write"); }
    throw new Error(`Unexpected ${url}`);
  });
  const [restored] = await studio.loadServerWorks([]);
  assert.equal(restored.id, "original-work");
  assert.equal(restored.project.characters[0].sourceId, undefined);
  assert.equal(restored.project.lorebooks[0].sourceId, undefined);
  assert.deepEqual(await studio.saveServerWork(restored), { productId, revision: 3 });
  assert.equal(puts, 0);
});
