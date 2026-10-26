const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function client(fetchImpl = async () => { throw new Error("unexpected_fetch"); }, shared = {}) {
  const cache = new Map();
  const storage = shared.storage ?? new Map();
  let queue = Promise.resolve();
  const locks = shared.locks ?? { request: (_name, callback) => { const pending = queue.then(callback); queue = pending.catch(() => {}); return pending; } };
  const context = vm.createContext({ URL, URLSearchParams, Intl, Date, Headers, Response, fetch: fetchImpl,
    navigator: { locks }, localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    BroadcastChannel: class { postMessage() {} close() {} },
  });
  function load(name) {
    const file = path.resolve(__dirname, "../lib", name);
    if (cache.has(file)) return cache.get(file);
    const output = ts.transpileModule(fs.readFileSync(file, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
    const module = { exports: {} }; cache.set(file, module.exports);
    const evaluate = vm.runInContext(`(function(exports, require, module) { ${output}\n})`, context);
    evaluate(module.exports, child => load(`${child.replace(/^\.\//, "")}.ts`), module);
    return module.exports;
  }
  return { api: load("api.ts"), filters: load("filters.ts"), prompt: load("prompt.ts"), storage, locks };
}
const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
const expired = () => json({ error: { code: "invalid_token" } }, 401);

test("Seoul dates cross UTC month/year boundaries and include seven days", () => {
  const { filters } = client();
  const result = filters.defaults(new Date("2026-12-31T15:30:00Z"));
  assert.equal(result.date_to, "2027-01-01"); assert.equal(result.date_from, "2026-12-26");
  assert.equal(filters.seoulTime("2026-10-22T05:32:08Z"), "2026-10-22 14:32:08");
});
test("filters and paging survive detail and safe login return links", () => {
  const { filters } = client();
  const input = { ...filters.defaults(), status: "failed", page: 4, page_size: 20, conversation_id: "80d4cbe2-6338-40f8-a734-6a29b685f723" };
  const query = filters.serializeFilters(input);
  assert.equal(JSON.stringify(filters.readFilters(new URLSearchParams(query))), JSON.stringify(input));
  const back = `/generation-prompts?${query}`;
  assert.equal(filters.safeReturnPath(back), back);
  for (const bad of ["https://evil.test", "//evil.test", "/login", "/\\evil.test", "/generation-prompts\nLocation:evil"]) assert.equal(filters.safeReturnPath(bad), "/generation-prompts");
});
test("731 inclusive days, UUIDs, impossible dates and unknown statuses are checked", () => {
  const { filters } = client(); const base = filters.defaults();
  assert.equal(filters.validateFilters({ ...base, date_from: "2024-01-01", date_to: "2025-12-31" }), null);
  assert.ok(filters.validateFilters({ ...base, date_from: "2024-01-01", date_to: "2026-01-01" }));
  for (const invalid of [{ date_from: "2026-02-30" }, { conversation_id: "invalid" }, { status: "__proto__" }, { date_to: "2000-01-01" }]) assert.ok(filters.validateFilters({ ...base, ...invalid }));
  const result = filters.readFilters(new URLSearchParams("page=-3&page_size=101")); assert.equal(result.page, 1); assert.equal(result.page_size, 50);
});
test("role parsing keeps message order, content and original whitespace; copy waits for success", async () => {
  const { prompt } = client();
  const raw = '{\n "chat_message_format": 1, "messages": [{"role":"user","content":"한글 <script>literal</script>\\n끝"}] }\n';
  assert.equal(prompt.parseMessages(raw, 1)[0].content, "한글 <script>literal</script>\n끝");
  for (const [body, version] of [[raw, 2], ["broken", 1], ['{"chat_message_format":1,"messages":[{"role":"user","content":4}]}', 1]]) assert.equal(prompt.parseMessages(body, version), null);
  let copied; let finish; let complete = false;
  const pending = prompt.copyOriginal(raw, { writeText: value => { copied = value; return new Promise(resolve => { finish = resolve; }); } }).then(() => { complete = true; });
  assert.equal(copied, raw); assert.equal(complete, false); finish(); await pending; assert.equal(complete, true);
  await assert.rejects(prompt.copyOriginal(raw, { writeText: async () => { throw new Error("denied"); } }));
  await assert.rejects(prompt.copyOriginal(raw, undefined));
});
test("CSRF retry preserves credentials and body, and stops after one recovery", async () => {
  let tokens = 0; const calls = [];
  const { api } = client(async (url, options) => {
    assert.equal(options.cache, "no-store"); assert.equal(options.credentials, "include");
    if (url.endsWith("/csrf")) return json({ csrf_token: `csrf-${++tokens}` });
    calls.push(options); return calls.length === 1 ? json({ error: { code: "csrf_failed" } }, 403) : json({ id: "admin" });
  });
  await api.login("admin@example.test", "fixture-password");
  assert.equal(calls.length, 2); assert.equal(calls[0].body, calls[1].body); assert.equal(calls[1].headers.get("X-CSRF-Token"), "csrf-2");
  let posts = 0;
  const again = client(async url => url.endsWith("/csrf") ? json({ csrf_token: "csrf" }) : (posts++, json({ error: { code: "csrf_failed" } }, 403)));
  await assert.rejects(again.api.login("a", "b"), { code: "csrf_failed" }); assert.equal(posts, 2);
});
test("401 session failures, 403 authorization and origin configuration are distinct", async () => {
  const { api } = client();
  assert.match(api.authDestination(new api.ApiError(401, "invalid_session"), "/generation-prompts?page=2"), /^\/login\?reason=expired&returnTo=/);
  assert.equal(api.authDestination(new api.ApiError(403, "forbidden"), "/"), "/forbidden");
  assert.equal(api.authDestination(new api.ApiError(403, "origin_forbidden"), "/"), null);
  assert.equal(api.authDestination(new api.ApiError(404, "not_found"), "/"), null);
});
test("simultaneous tabs rotate once and recheck /auth/me after the shared lock", async () => {
  let valid = false; let rotations = 0;
  const fetchImpl = async url => {
    if (url.endsWith("/csrf")) return json({ csrf_token: "csrf" });
    if (url.endsWith("/refresh")) { rotations++; valid = true; return json({ id: "admin" }); }
    return valid ? json({ id: "admin" }) : expired();
  };
  const first = client(fetchImpl); const second = client(fetchImpl, first);
  await Promise.all([first.api.request("/admin/reporting/generation-prompts"), second.api.request("/auth/me")]);
  assert.equal(rotations, 1); assert.equal(first.storage.size, 0);
});
test("lost refresh response never replays after reload; explicit login recovers", async () => {
  let rotations = 0;
  const fetchImpl = async url => {
    if (url.endsWith("/csrf")) return json({ csrf_token: "csrf" });
    if (url.endsWith("/refresh")) { rotations++; throw new TypeError("lost_response"); }
    if (url.endsWith("/login")) return json({ id: "admin" });
    return expired();
  };
  const first = client(fetchImpl);
  await assert.rejects(first.api.request("/auth/me"), { code: "refresh_uncertain", status: 401 });
  const reloaded = client(fetchImpl, first);
  await assert.rejects(reloaded.api.request("/auth/me"), { code: "refresh_uncertain" });
  assert.equal(rotations, 1); assert.deepEqual([...first.storage.values()], ["1"]);
  await reloaded.api.login("admin@example.test", "fixture-password"); assert.equal(first.storage.size, 0);
});
test("revoked sessions and wrong credentials are never refreshed", async () => {
  const paths = []; const { api } = client(async url => { paths.push(url); return json({ error: { code: url.endsWith("/login") ? "invalid_credentials" : "invalid_session" } }, 401); });
  await assert.rejects(api.request("/auth/me"), { code: "invalid_session" }); assert.equal(paths.length, 1);
});

module.exports = { client };
