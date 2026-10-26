const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
function loadLibrary(name, overrides = {}) {
  const cache = new Map();
  function load(name) {
    if (overrides[name]) return overrides[name];
    if (cache.has(name)) return cache.get(name);
    const file = path.resolve(__dirname, "../lib", name);
    const code = ts.transpileModule(fs.readFileSync(file, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
    const module = { exports: {} }; cache.set(name, module.exports);
    new Function("exports", "require", "module", code)(module.exports, name => name.startsWith("./") ? load(`${name.slice(2)}.ts`) : require(name), module);
    return module.exports;
  }
  return load(name);
}
const pending = { id: "MC-20261019-001", amount: 10000, credits: 10000, createdAt: "2026-10-19T06:20:00Z", status: "pending" };
test("rechecking pending, failed and uncertain orders never creates a success or alters purchase identity", () => {
  const api = loadLibrary("account.ts");
  for (const status of ["pending", "failed", "uncertain"]) {
    const order = { ...pending, status, amount: status === "failed" ? 5000 : 10000, credits: status === "failed" ? 5000 : 10000 };
    assert.deepEqual(api.recheckPreviewOrder(order), { ...order, status: "uncertain" });
    assert.equal(order.status, status);
  }
  assert.deepEqual(api.recheckPreviewOrder({ ...pending, status: "succeeded" }), { ...pending, status: "succeeded" });
});
test("order filtering combines status and date without mixing unknown with paid", () => {
  const api = loadLibrary("account.ts");
  const orders = [pending, { ...pending, id: "paid", status: "succeeded" }, { ...pending, id: "old", status: "uncertain", createdAt: "2026-09-01T00:00:00Z" }];
  assert.deepEqual(api.filterOrders(orders, "확인 중", 7, Date.parse("2026-10-20T00:00:00Z")).map(o => o.id), [pending.id]);
  assert.deepEqual(api.filterOrders(orders, "완료", 0).map(o => o.id), ["paid"]);
});
test("account overview retains successful resources when credit lookup fails", async () => {
  const user = { id: "owner", email: "owner@example.test", email_verified: true };
  const api = loadLibrary("account.ts", { "api.ts": { getMe: async () => user, getCreditBalance: async () => { throw new Error("unavailable"); }, listOwnedConversations: async () => ({ items: [{ id: "conversation" }] }), request: async () => [{ id: "product" }] } });
  const value = await api.readAccountOverview();
  assert.equal(value.user.id, "owner"); assert.equal(value.balance.status, "rejected");
  assert.equal(value.conversations.value.items[0].id, "conversation"); assert.equal(value.products.value[0].id, "product");
});
test("unauthenticated overview does not query private credit, conversation or product resources", async () => {
  const api = loadLibrary("account.ts", { "api.ts": { getMe: async () => { throw new Error("unauthenticated"); }, getCreditBalance: () => assert.fail(), listOwnedConversations: () => assert.fail(), request: () => assert.fail() } });
  await assert.rejects(api.readAccountOverview(), /unauthenticated/);
});
test("owned product listing paginates the actual owner endpoint", async () => {
  const calls = [];
  const api = loadLibrary("account.ts", { "api.ts": { request: async path => { calls.push(path); return calls.length === 1 ? Array.from({ length: 100 }, (_, i) => ({ id: String(i) })) : [{ id: "last" }]; } } });
  assert.equal((await api.listOwnedProducts()).length, 101);
  assert.deepEqual(calls, ["/products/mine?offset=0&limit=100", "/products/mine?offset=100&limit=100"]);
});
test("credit history keeps the period and both cursor values in owner-only requests", async () => {
  const calls = [];
  const api = loadLibrary("account.ts", { "api.ts": { request: async path => { calls.push(path); return { items: [], next_cursor_id: null, next_cursor_created_at: null }; } } });
  await api.listCreditHistory("2026-10-01T00:00:00Z", { createdAt: "2026-10-19T06:20:00Z", id: "ledger-row" });
  const query = new URL(calls[0], "https://local.test").searchParams;
  assert.equal(query.get("start"), "2026-10-01T00:00:00Z");
  assert.equal(query.get("cursor_created_at"), "2026-10-19T06:20:00Z");
  assert.equal(query.get("cursor_id"), "ledger-row");
  assert.equal(query.get("user_id"), null);
});
test("development chat and arbitrary status routes are excluded from production account routing", () => {
  const api = loadLibrary("account.ts");
  assert.equal(api.validAccountSection(["chat"]), false);
  assert.equal(api.validAccountSection(["chat"], true), true);
  assert.equal(api.validAccountSection(["purchases", pending.id, "recheck"]), true);
  assert.equal(api.validAccountSection(["purchases", pending.id, "success"]), false);
});
test("server work entry reads the selected product and detaches browser-only source rows", async t => {
  const data = new Map();
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: k => data.get(k) ?? null, setItem: (k,v) => data.set(k,v) } });
  t.after(() => original ? Object.defineProperty(globalThis, "localStorage", original) : delete globalThis.localStorage);
  const project = loadLibrary("studio-project.ts").sampleProject();
  project.characters[0].sourceId = "private-browser-source";
  const calls = [];
  const studio = loadLibrary("studio-server.ts", { "api.ts": { getMe: async () => ({ id: "owner" }), request: async path => { calls.push(path); return { product_id: "target", revision: 4, document: project }; } } });
  const work = await studio.loadServerWork("target");
  assert.deepEqual(calls, ["/products/target/studio-draft"]);
  assert.equal(work.id, "server:target"); assert.equal(work.project.characters[0].sourceId, undefined);
  assert.equal(project.characters[0].sourceId, "private-browser-source");
  assert.equal(JSON.parse([...data.values()][0]).revision, 4);
  const linkKey = [...data.keys()][0];
  const previous = { productId: "target", revision: 2, base: "earlier-server-base" };
  data.set(linkKey, JSON.stringify(previous));
  await studio.loadServerWork("target");
  assert.deepEqual(JSON.parse(data.get(linkKey)), previous, "opening a link must preserve the conflict-detection baseline");
});
