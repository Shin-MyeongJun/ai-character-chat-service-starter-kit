const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

const AUTH_CHANGED_KEY = "moseori_auth_changed";
const RECENT_CHATS_EVENT = "moseori:recent-chats-updated";
const createdAt = "2026-10-30T00:00:00Z";
const row = id => ({ id, title: id, created_at: createdAt });
const page = (ids, cursor = null) => ({
  items: ids.map(row), next_cursor_id: cursor, next_cursor_created_at: cursor ? createdAt : null,
});
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

// Execute the production hook with controlled promises and an explicit render
// cycle. This models hook state/effect lifetime; it is not a browser/React E2E.
function setup(t) {
  const slots = [], effects = [], auth = [], pages = [];
  const window = new EventTarget();
  let index = 0, mounted = false, writes = 0, local = [];
  const react = {
    useState(initial) {
      const slot = index++;
      if (!(slot in slots)) slots[slot] = typeof initial === "function" ? initial() : initial;
      return [slots[slot], value => {
        writes++;
        slots[slot] = typeof value === "function" ? value(slots[slot]) : value;
      }];
    },
    useRef(initial) {
      const slot = index++;
      if (!(slot in slots)) slots[slot] = { current: initial };
      return slots[slot];
    },
    useEffect(effect) { if (!mounted) effects.push({ effect, cleanup: null }); },
  };
  const dependencies = {
    react,
    "react/jsx-runtime": {},
    "next/link": {},
    "lucide-react": {},
    "@/lib/works": {},
    "@/lib/recent-chats": {
      AUTH_CHANGED_KEY, RECENT_CHATS_EVENT,
      readRecentChats: () => local,
    },
    "@/lib/api": {
      getMe() { const call = deferred(); auth.push(call); return call.promise; },
      listOwnedConversations(cursor) {
        const call = { ...deferred(), cursor };
        pages.push(call);
        return call.promise;
      },
    },
  };
  const file = path.resolve(__dirname, "../components/recent-conversations.tsx");
  const code = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const module = { exports: {} };
  new Function("exports", "require", "module", "window", code)(module.exports, name => {
    assert.ok(name in dependencies, `unexpected import: ${name}`);
    return dependencies[name];
  }, module, window);
  function render() {
    index = 0;
    const value = module.exports.useConversationDirectory();
    if (!mounted) {
      mounted = true;
      for (const entry of effects) entry.cleanup = entry.effect();
    }
    return value;
  }
  function cleanup() {
    for (const entry of effects) { entry.cleanup?.(); entry.cleanup = null; }
  }
  t.after(cleanup);
  render();
  return {
    auth, pages, render, cleanup, writes: () => writes,
    dispatch(type, key) {
      const event = new Event(type);
      if (type === "storage") Object.defineProperty(event, "key", { value: key });
      window.dispatchEvent(event);
    },
    replayEffects() { cleanup(); for (const entry of effects) entry.cleanup = entry.effect(); },
    setLocal(value) { local = value; },
  };
}

async function finishFirst(harness, ids, cursor = null) {
  const auth = harness.auth.at(-1);
  auth.resolve({ id: "owner" });
  await flush();
  const first = harness.pages.at(-1);
  assert.equal(first.cursor, undefined);
  first.resolve(page(ids, cursor));
  await flush();
  return harness.render();
}
const ids = directory => directory.recent.map(item => item.id);
const state = directory => ({ ids: ids(directory), loading: directory.loading, error: directory.error, hasMore: directory.hasMore });

for (const outcome of ["success", "failure"]) {
  for (const order of ["before new first page", "after new first page", "during new additional page"]) {
    test(`old account additional-page ${outcome} is ignored ${order}`, async t => {
      const h = setup(t);
      const oldDirectory = await finishFirst(h, ["A-first"], "A-cursor");
      const oldRequest = oldDirectory.loadMore();
      const oldPage = h.pages.at(-1);
      h.dispatch(AUTH_CHANGED_KEY);
      assert.deepEqual(state(h.render()), { ids: [], loading: true, error: "", hasMore: false });
      let currentRequest;
      if (order !== "before new first page") {
        const current = await finishFirst(h, ["B-first"], "B-cursor");
        if (order === "during new additional page") currentRequest = current.loadMore();
      }
      const before = state(h.render());
      const writes = h.writes();
      if (outcome === "success") oldPage.resolve(page(["A-old-page"], "A-next"));
      else oldPage.reject(new Error("old account unavailable"));
      await oldRequest;
      assert.equal(h.writes(), writes, "stale success/catch/finally must not write state");
      assert.deepEqual(state(h.render()), before);
      if (order === "before new first page") await finishFirst(h, ["B-first"], "B-cursor");
      if (currentRequest) {
        const count = h.pages.length;
        await oldDirectory.loadMore();
        assert.equal(h.pages.length, count, "stale finally must not unlock the current request");
        h.pages.at(-1).resolve(page(["B-next"]));
        await currentRequest;
        assert.deepEqual(ids(h.render()), ["B-first", "B-next"]);
      } else {
        // Even a callback retained from A must use B's current cursor.
        const next = oldDirectory.loadMore();
        assert.deepEqual(h.pages.at(-1).cursor, { createdAt, id: "B-cursor" });
        h.pages.at(-1).resolve(page(["B-next"]));
        await next;
        assert.deepEqual(ids(h.render()), ["B-first", "B-next"]);
      }
      assert.deepEqual(state(h.render()), { ids: ["B-first", "B-next"], loading: false, error: "", hasMore: false });
    });
  }
}

for (const [trigger, key] of [["focus"], ["storage", AUTH_CHANGED_KEY], ["storage", null]]) {
  test(`${trigger} ${key ?? ""} invalidates an outstanding additional page`, async t => {
    const h = setup(t);
    const directory = await finishFirst(h, ["before"], "old-cursor");
    const oldRequest = directory.loadMore();
    const oldPage = h.pages.at(-1);
    h.dispatch(trigger, key);
    await finishFirst(h, ["refreshed"], "fresh-cursor");
    oldPage.resolve(page(["outdated"], "outdated-cursor"));
    await oldRequest;
    assert.deepEqual(ids(h.render()), ["refreshed"]);
    const next = h.render().loadMore();
    assert.equal(h.pages.at(-1).cursor.id, "fresh-cursor");
    h.pages.at(-1).resolve(page(["next"]));
    await next;
    assert.deepEqual(ids(h.render()), ["refreshed", "next"]);
  });
}

for (const outcome of ["success", "failure"]) {
  test(`logout ignores old additional-page ${outcome} and retains browser demos`, async t => {
    const h = setup(t);
    h.setLocal([{ id: "demo-local", title: "demo" }]);
    const directory = await finishFirst(h, ["A-first"], "A-cursor");
    const pending = directory.loadMore();
    const oldPage = h.pages.at(-1);
    h.dispatch(AUTH_CHANGED_KEY);
    h.auth.at(-1).reject(Object.assign(new Error("logged out"), { status: 401 }));
    await flush();
    const expected = { ids: ["demo-local"], loading: false, error: "", hasMore: false };
    assert.deepEqual(state(h.render()), expected);
    if (outcome === "success") oldPage.resolve(page(["A-private"], "private-cursor"));
    else oldPage.reject(new Error("late failure"));
    await pending;
    assert.deepEqual(state(h.render()), expected);
    const count = h.pages.length;
    await directory.loadMore();
    assert.equal(h.pages.length, count);
  });

  test(`additional-page ${outcome} after unmount performs no state updates`, async t => {
    const h = setup(t);
    const directory = await finishFirst(h, ["first"], "cursor");
    const pending = directory.loadMore();
    h.cleanup();
    const writes = h.writes();
    if (outcome === "success") h.pages.at(-1).resolve(page(["late"], "next"));
    else h.pages.at(-1).reject(new Error("late failure"));
    await pending;
    assert.equal(h.writes(), writes);
    const calls = h.pages.length;
    await directory.loadMore();
    h.dispatch("focus"); h.dispatch(AUTH_CHANGED_KEY); h.dispatch("storage", null); h.dispatch(RECENT_CHATS_EVENT);
    assert.equal(h.pages.length, calls);
    assert.equal(h.auth.length, 1, "unmount removes verification listeners");
    assert.equal(h.writes(), writes, "unmount removes local refresh listeners");
  });
}

test("additional pages serialize immediate duplicate calls, advance cursors and deduplicate rows", async t => {
  const h = setup(t);
  const directory = await finishFirst(h, ["first"], "cursor-1");
  const first = directory.loadMore();
  const duplicate = directory.loadMore();
  const rerenderDuplicate = h.render().loadMore();
  assert.equal(h.pages.length, 2, "both same-render and later-render duplicates are blocked");
  h.pages.at(-1).resolve(page(["first", "second"], "cursor-2"));
  await Promise.all([first, duplicate, rerenderDuplicate]);
  assert.deepEqual(ids(h.render()), ["first", "second"]);
  const second = directory.loadMore();
  assert.deepEqual(h.pages.at(-1).cursor, { createdAt, id: "cursor-2" });
  h.pages.at(-1).resolve(page(["third"]));
  await second;
  assert.deepEqual(state(h.render()), { ids: ["first", "second", "third"], loading: false, error: "", hasMore: false });
  await directory.loadMore();
  assert.equal(h.pages.length, 3);
});

test("current additional-page failure releases the lock and retries the same cursor", async t => {
  const h = setup(t);
  const directory = await finishFirst(h, ["first"], "retry-cursor");
  const pending = directory.loadMore();
  h.pages.at(-1).reject(new Error("temporary failure"));
  await pending;
  assert.deepEqual(state(h.render()), { ids: ["first"], loading: false, error: "다음 대화 목록을 불러오지 못했어요.", hasMore: true });
  const retry = h.render().loadMore();
  assert.equal(h.render().error, "");
  assert.equal(h.pages.at(-1).cursor.id, "retry-cursor");
  h.pages.at(-1).resolve(page(["retried"]));
  await retry;
  assert.deepEqual(ids(h.render()), ["first", "retried"]);
});

for (const outcome of ["success", "failure"]) {
  test(`outdated first-page ${outcome} cannot overwrite a newer refresh`, async t => {
    const h = setup(t);
    h.auth[0].resolve({ id: "A" });
    await flush();
    const oldPage = h.pages[0];
    h.dispatch(AUTH_CHANGED_KEY);
    await finishFirst(h, ["B-first"], "B-cursor");
    const before = state(h.render()), writes = h.writes();
    if (outcome === "success") oldPage.resolve(page(["A-first"], "A-cursor"));
    else oldPage.reject(new Error("A failed"));
    await flush();
    assert.deepEqual(state(h.render()), before);
    assert.equal(h.writes(), writes);
  });
}

test("a stale authentication result never starts a list request", async t => {
  const h = setup(t);
  h.dispatch(AUTH_CHANGED_KEY);
  await finishFirst(h, ["B-first"]);
  const writes = h.writes();
  h.auth[0].resolve({ id: "A" });
  await flush();
  assert.equal(h.pages.length, 1);
  assert.equal(h.writes(), writes);
  assert.deepEqual(ids(h.render()), ["B-first"]);
});

test("effect cleanup invalidates auth work during Strict Mode setup replay", async t => {
  const h = setup(t);
  h.replayEffects();
  h.auth[0].resolve({ id: "stale" });
  await flush();
  assert.equal(h.pages.length, 0);
  await finishFirst(h, ["current"], "current-cursor");
  const pending = h.render().loadMore();
  h.pages.at(-1).resolve(page(["next"]));
  await pending;
  assert.deepEqual(ids(h.render()), ["current", "next"]);
});

test("unmount during authentication prevents list requests and state updates", async t => {
  const h = setup(t);
  h.cleanup();
  const writes = h.writes();
  h.auth[0].resolve({ id: "late" });
  await flush();
  assert.equal(h.pages.length, 0);
  assert.equal(h.writes(), writes);
});

test("current first-page failure reports the error and focus can retry", async t => {
  const h = setup(t);
  h.auth[0].resolve({ id: "owner" });
  await flush();
  h.pages[0].reject(new Error("unavailable"));
  await flush();
  assert.deepEqual(state(h.render()), { ids: [], loading: false, error: "대화 목록을 불러오지 못했어요.", hasMore: false });
  h.dispatch("focus");
  await finishFirst(h, ["retried"]);
  assert.deepEqual(state(h.render()), { ids: ["retried"], loading: false, error: "", hasMore: false });
});

test("local and unrelated storage events preserve an active server page request", async t => {
  const h = setup(t);
  const directory = await finishFirst(h, ["first"], "cursor");
  const pending = directory.loadMore();
  h.setLocal([{ id: "demo-new", title: "demo" }]);
  h.dispatch(RECENT_CHATS_EVENT);
  h.dispatch("storage", "unrelated-key");
  assert.equal(h.auth.length, 1);
  assert.deepEqual(ids(h.render()), ["first", "demo-new"]);
  h.pages.at(-1).resolve(page(["second"]));
  await pending;
  assert.deepEqual(ids(h.render()), ["first", "second", "demo-new"]);
});
