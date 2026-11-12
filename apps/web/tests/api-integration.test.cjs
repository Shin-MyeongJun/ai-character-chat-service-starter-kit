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
  return { api: load("api.ts"), history: load("chat-history.ts"), recent: load("recent-chats.ts"), studio: load("studio-server.ts"), workspace: load("studio-workspace.ts"), project: load("studio-project.ts"), data, newClient: () => { cache.clear(); return load("api.ts"); } };
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
  assert.deepEqual(await studio.saveServerWork(work), { productId: stored.product_id, revision: 1, project: work.project });
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
  assert.deepEqual(await studio.saveServerWork(restored), { productId, revision: 3, project: restored.project });
  assert.equal(puts, 0);
});


const chatMessage = (position, fields = {}) => ({ id: `message-${position}`, conversation_id: "conversation", position, content: `message ${position}`, revision: 1, sender_type: "user", product_character_id: null, ...fields });
const messagePage = (items, revision = 1, next = null, checkpoint = items.at(-1)?.position) => ({ items, next_cursor: next, history_revision: revision, sync_cursor: checkpoint ? `v1:conversation:${checkpoint}` : null });
const cursorOf = url => new URL(url, "https://test").searchParams.get("cursor");
const afterOf = url => Number(cursorOf(url)?.split(":").at(-1) ?? 0);
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; };

test("205-message history appends a confirmed input without GET and reads only new answers", async t => {
  const { api, history } = setup(t);
  let total = 205;
  const reads = [], saves = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/auth/csrf")) return json({csrf_token: "csrf"});
    if (options.method === "POST") { saves.push(JSON.parse(options.body)); return json(chatMessage(206)); }
    reads.push(url);
    const after = afterOf(url), end = Math.min(after + 100, total);
    return json(messagePage(Array.from({length: Math.max(0, end - after)}, (_, i) => chatMessage(after + i + 1)), 1, end < total ? `v1:conversation:${end}` : null, end));
  });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  assert.equal((await scope.sync()).messages.length, 205);
  assert.equal(reads.length, 3);
  const saved = await api.createMessage("conversation", "hello", "same-message-key");
  assert.equal(scope.append(saved).messages.length, 206);
  assert.equal(scope.append(saved).messages.length, 206);
  assert.equal(reads.length, 3);
  total = 208;
  const updated = await scope.sync();
  assert.equal(updated.messages.length, 208);
  assert.equal(new Set(updated.messages.map(item => item.id)).size, 208);
  assert.equal(reads.length, 4);
  assert.equal(cursorOf(reads[3]), "v1:conversation:205");
  assert.equal(saves[0].request_key, "same-message-key");
});

test("empty incremental responses retain the checkpoint instead of restarting from page one", async t => {
  const {history} = setup(t);
  const cursors = [];
  let pass = 0;
  t.mock.method(globalThis, "fetch", async url => {
    cursors.push(cursorOf(url));
    return json(++pass === 1 ? messagePage([chatMessage(10)]) : messagePage([], 1, null, 10));
  });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); await scope.sync(); await scope.sync();
  assert.deepEqual(cursors, [null, "v1:conversation:10", "v1:conversation:10"]);
});

for (const change of ["edit", "rewind"]) test(`${change} revision discards stale cached history and reloads`, async t => {
  const {history} = setup(t);
  const paths = []; let pass = 0;
  t.mock.method(globalThis, "fetch", async url => {
    paths.push(cursorOf(url)); pass++;
    if (pass === 1) return json(messagePage([chatMessage(1), chatMessage(2)]));
    if (pass === 2) return json(messagePage([], 2, null, 2));
    return json(messagePage(change === "edit" ? [chatMessage(1, {revision: 2, content: "edited"}), chatMessage(2)] : [], 2));
  });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); const current = await scope.sync();
  assert.deepEqual(paths, [null, "v1:conversation:2", null]);
  assert.equal(current.historyRevision, 2);
  assert.deepEqual(current.messages.map(item => item.content), change === "edit" ? ["edited", "message 2"] : []);
});

test("a revision change across full pages restarts once and publishes only the stable read", async t => {
  const {history} = setup(t); let pass = 0;
  t.mock.method(globalThis, "fetch", async () => {
    pass++;
    if (pass === 1) return json(messagePage([chatMessage(1)], 1, "v1:conversation:1"));
    if (pass === 2) return json(messagePage([chatMessage(2)], 2));
    return json(messagePage([chatMessage(1, {content: "stable", revision: 3})], 3));
  });
  const current = await history.readConversationHistory("conversation");
  assert.equal(pass, 3); assert.deepEqual(current.messages.map(item => item.content), ["stable"]);
});

test("continuous revision changes stop after the one full-read recovery", async t => {
  const {history} = setup(t); let pass = 0;
  t.mock.method(globalThis, "fetch", async () => {
    pass++; return json(messagePage([chatMessage(pass)], pass, pass % 2 ? `v1:conversation:${pass}` : null));
  });
  await assert.rejects(history.readConversationHistory("conversation"), /history changed/);
  assert.equal(pass, 4);
});

test("a legacy response falls back to full reads while preserving cursor loop protection", async t => {
  const {history} = setup(t); const cursors = []; let pass = 0;
  t.mock.method(globalThis, "fetch", async url => {
    cursors.push(cursorOf(url)); pass++;
    if (pass === 1) return json(messagePage([chatMessage(1)]));
    return json({items: [chatMessage(1), chatMessage(2)], next_cursor: null});
  });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); assert.equal((await scope.sync()).messages.length, 2);
  await scope.sync();
  assert.deepEqual(cursors, [null, "v1:conversation:1", null, null]);
});

test("repeated incremental cursors fail without losing cached messages", async t => {
  const {history} = setup(t); let pass = 0;
  t.mock.method(globalThis, "fetch", async () => json(++pass === 1 ? messagePage([chatMessage(1)]) : messagePage([], 1, "v1:conversation:1", 1)));
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); await assert.rejects(scope.sync(), /did not advance/);
});

test("partial delta network failure leaves the old checkpoint for the next retry", async t => {
  const {history} = setup(t); const cursors = []; let pass = 0;
  t.mock.method(globalThis, "fetch", async url => {
    cursors.push(cursorOf(url)); pass++;
    if (pass === 1) return json(messagePage([chatMessage(1)]));
    if (pass === 2) return json(messagePage([chatMessage(2)], 1, "v1:conversation:2"));
    if (pass === 3) throw new TypeError("read lost");
    return json(messagePage([chatMessage(2), chatMessage(3)]));
  });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); await assert.rejects(scope.sync(), /read lost/);
  assert.deepEqual((await scope.sync()).messages.map(item => item.position), [1, 2, 3]);
  assert.deepEqual(cursors, [null, "v1:conversation:1", "v1:conversation:2", "v1:conversation:1"]);
});

test("same-ID revision conflicts force a full replacement and old save replays cannot downgrade", async t => {
  const {history} = setup(t); const cursors = [];
  t.mock.method(globalThis, "fetch", async url => { cursors.push(cursorOf(url)); return json(messagePage([chatMessage(1, {revision: 2, content: "edited"})], 2)); });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); assert.equal(scope.append(chatMessage(1)).messages[0].revision, 2);
  await scope.sync(); assert.deepEqual(cursors, [null, null]);
});

test("same-ID changed data in a delta triggers recovery even if metadata revision was unchanged", async t => {
  const {history} = setup(t); const cursors = []; let pass = 0;
  t.mock.method(globalThis, "fetch", async url => { cursors.push(cursorOf(url)); return json(messagePage([chatMessage(1, ++pass > 1 ? {revision: 2} : {})])); });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); assert.equal((await scope.sync()).messages[0].revision, 2);
  assert.deepEqual(cursors, [null, "v1:conversation:1", null]);
});

test("explicit reset reloads rather than merging messages from the old history", async t => {
  const {history} = setup(t); const cursors = []; let pass = 0;
  t.mock.method(globalThis, "fetch", async url => { cursors.push(cursorOf(url)); return json(messagePage(++pass === 1 ? [chatMessage(1)] : [])); });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); assert.deepEqual((await scope.sync(true)).messages, []);
  assert.deepEqual(cursors, [null, null]);
});

test("late old reads cannot overwrite newer reads or confirmed input saves", async t => {
  const {history} = setup(t); let pass = 0; const old = deferred(), pending = deferred();
  t.mock.method(globalThis, "fetch", async () => {
    pass++;
    if (pass === 2) return old.promise;
    if (pass === 4) return pending.promise;
    return json(messagePage([chatMessage(1)], 1));
  });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); const first = scope.sync(); const newer = await scope.sync();
  old.resolve(json(messagePage([], 1, null, 1))); assert.equal(await first, null);
  assert.equal(newer.messages.length, 1);
  const stale = scope.sync(); assert.equal(scope.append(chatMessage(2)).messages.length, 2);
  pending.resolve(json(messagePage([], 1, null, 1))); assert.equal(await stale, null);
});

for (const failed of [false, true]) test(`disposed account/room reads ignore late ${failed ? "errors" : "responses"}`, async t => {
  const {history} = setup(t); const late = deferred(); let calls = 0, signal;
  t.mock.method(globalThis, "fetch", async (_url, options) => { calls++; signal = options.signal; return late.promise; });
  const scope = new history.ConversationHistorySession("conversation", "owner-a");
  const pending = scope.sync(); scope.dispose();
  assert.ok(signal.aborted);
  if (failed) late.reject(new Error("old account response")); else late.resolve(json(messagePage([chatMessage(1)])));
  assert.equal(await pending, null); assert.equal(await scope.sync(), null);
  assert.equal(scope.append(chatMessage(2)), null); assert.equal(calls, 1);
});

test("another room's history or returned messages are never merged into this room", async t => {
  const {history} = setup(t); const cursors = [];
  t.mock.method(globalThis, "fetch", async url => { cursors.push(cursorOf(url)); return json(messagePage([chatMessage(1)])); });
  const old = {conversationId: "other", messages: [chatMessage(9, {conversation_id: "other"})], historyRevision: 1, syncCursor: "old-other-cursor"};
  const current = await history.readConversationHistory("conversation", old);
  assert.deepEqual(current.messages.map(item => item.position), [1]); assert.deepEqual(cursors, [null]);
  await assert.rejects(history.readConversationHistory("wrong"), /another conversation/);
});

test("aborted message sync keeps its saved checkpoint and forwards the signal", async t => {
  const {history} = setup(t); const controller = new AbortController(); let pass = 0;
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    if (++pass === 1) return json(messagePage([chatMessage(1)]));
    assert.ok(options.signal.aborted); throw new DOMException("cancelled", "AbortError");
  });
  const scope = new history.ConversationHistorySession("conversation", "owner");
  await scope.sync(); controller.abort();
  await assert.rejects(scope.sync(false, controller.signal), {name: "AbortError"});
});


test("UUID route aliases still accept canonical message IDs and checkpoints", async t => {
  const {history} = setup(t);
  const canonical = "abcdef12-3456-7890-abcd-ef1234567890";
  t.mock.method(globalThis, "fetch", async () => json(messagePage([chatMessage(1, {conversation_id: canonical})])));
  for (const id of [canonical.toUpperCase(), canonical.replaceAll("-", ""), `{${canonical}}`, `urn:uuid:${canonical}`]) {
    const scope = new history.ConversationHistorySession(id, "owner");
    assert.equal((await scope.sync()).messages.length, 1);
    assert.equal(scope.append(chatMessage(2, {conversation_id: canonical})).messages.length, 2);
  }
});

test("chat album resolves the authorized room across owned-conversation pages", async t => {
  const { api } = setup(t);
  const controller = new AbortController();
  const calls = [];
  t.mock.method(globalThis, "fetch", async (path, options) => {
    assert.equal(options.signal, controller.signal);
    const url = new URL(path, "https://test");
    calls.push(url);
    if (url.pathname.endsWith("/album")) {
      return json({ product_id: "work", product_snapshot_id: "latest", available: true,
        items: [{ image_item_id: "locked", status: "locked" }] });
    }
    return json(url.searchParams.has("cursor_id")
      ? { items: [{ id: "room", product_id: "work" }] }
      : { items: [{ id: "different", product_id: "other" }],
        next_cursor_created_at: "2026-11-01", next_cursor_id: "different" });
  });
  const productId = await api.findConversationProduct("room", controller.signal);
  const album = await api.getProductAlbum(productId, controller.signal);
  assert.equal(calls[1].searchParams.get("cursor_created_at"), "2026-11-01");
  assert.equal(calls[1].searchParams.get("cursor_id"), "different");
  assert.equal(calls[2].pathname, "/backend/products/work/album");
  assert.deepEqual(album.items, [{ image_item_id: "locked", status: "locked" }]);
});
