// Run against a local Next server with Playwright and Chrome installed.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const origin = new URL(process.env.STUDIO_TEST_ORIGIN ?? "http://127.0.0.1:34219").origin;
assert.ok(["localhost", "127.0.0.1"].includes(new URL(origin).hostname));
const prefix = "chat-kit-studio-workspace-v3";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVh0AAAAASUVORK5CYII=", "base64");
const deferred = () => Promise.withResolvers();
const button = (page, name) => page.getByRole("button", { name, exact: true });
const goto = (page, path) => page.goto(origin + path);
const raw = (page, key) => page.evaluate(k => localStorage.getItem(k), key);
const workspace = async (page, scope) => JSON.parse(await raw(page, prefix + ":" + scope));
const documentFor = (owner, assets = []) => ({
  version: 2, clientWorkId: "work-" + owner,
  work: { title: owner + "-private", introduction: "private introduction " + owner, worldRules: owner + "-secret", tags: [], defaultSceneId: "", visibility: "비공개" },
  characters: [{ id: "hero", name: owner + "-hero", role: "", introduction: "", persona: "", dialogue: "", tags: [], relationships: "", assets }],
  lorebooks: [], scenes: [],
});

async function exportJSON(page, label = "작업실 내보내기") {
  const download = page.waitForEvent("download");
  await button(page, label).click();
  const stream = await (await download).createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString());
}

async function bytes(page, key) {
  return page.evaluate(key => new Promise((resolve, reject) => {
    const open = indexedDB.open("chat-kit-studio-assets");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const read = db.transaction("images").objectStore("images").get(key);
      read.onsuccess = async () => {
        db.close();
        resolve(read.result ? Array.from(new Uint8Array(await read.result.arrayBuffer())) : null);
      };
    };
  }), key);
}

async function login(page, owner) {
  await goto(page, "/login?next=/account/settings");
  await page.getByLabel("이메일").fill(owner + "@example.test");
  await page.getByLabel("비밀번호", { exact: true }).fill("test-password");
  await button(page, "로그인").click();
  await button(page, "로그아웃").waitFor();
}

async function assertIsolated(page, account, scope, assetId) {
  await button(page, "작업실 내보내기").waitFor();
  assert.doesNotMatch(await page.locator("body").innerText(), /A-private|A-hero|A-trash/);
  assert.equal(await page.locator('img[src^="blob:"]').count(), 0);
  await button(page, "휴지통 0").click();
  assert.doesNotMatch(JSON.stringify(await exportJSON(page)), /A-secret|A-local|A-trash/);
  assert.equal(await bytes(page, [scope, assetId]), null);
  assert.doesNotMatch(JSON.stringify(await workspace(page, scope)), /A-secret|A-local|A-trash/);
  await goto(page, "/studio?work=work-A");
  await page.getByText(/해당 초안을 찾지 못했어요/).waitFor();
  await goto(page, "/studio?product=product-A");
  await page.getByText(/로그인한 뒤|편집 가능한 스튜디오 초안이 없어요/).waitFor();
  assert.doesNotMatch(JSON.stringify(await exportJSON(page)), /A-secret|A-local|A-trash/);
  await goto(account, "/account/works");
  await account.locator("#browser-works").waitFor();
  assert.doesNotMatch(await account.locator("#browser-works").innerText(), /A-private|A-trash/);
}

test("shared browser isolates drafts, trash, downloads, pending work and actual image bytes", { timeout: 150000 }, async t => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  t.after(() => browser.close());
  const context = await browser.newContext({ serviceWorkers: "block" });
  const pageErrors = [];
  context.on("page", tab => tab.on("pageerror", error => pageErrors.push(error.message)));
  let owner = "A", assetId, holdMe, holdDraft;
  const lateDraft = deferred();
  const doc = who => documentFor(who, who === "B" && assetId ? [{ id: assetId, name: "remote-only.png", usage: "portrait" }] : []);
  await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (!url.pathname.startsWith("/backend/")) return route.continue();
    const path = url.pathname.slice("/backend".length);
    const json = (value, status = 200) => route.fulfill({ status, json: value });
    const user = () => ({ id: owner, email: owner + "@example.test", email_verified: true });
    if (path === "/auth/csrf") return json({ csrf_token: "test" });
    if (path === "/auth/login") { owner = route.request().postDataJSON().email[0]; return json(user()); }
    if (path === "/auth/logout") { owner = null; return route.fulfill({ status: 204 }); }
    if (path === "/auth/me") {
      if (holdMe) await holdMe.promise;
      return owner ? json(user()) : json({ detail: "signed out" }, 401);
    }
    if (!owner) return json({}, 401);
    if (path === "/models/available") return json([]);
    if (path === "/products/mine") return json([{
      id: "product-" + owner, title: owner + "-server", description: null, status: "draft", visibility: "private",
      has_publication: false, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
    }]);
    if (path.endsWith("/studio-draft")) {
      const who = owner;
      if (path !== "/products/product-" + who + "/studio-draft") return json({}, 404);
      const result = { product_id: "product-" + who, revision: 1, document: doc(who) };
      if (holdDraft) {
        result.document.clientWorkId = "late-work";
        result.document.work.title = "A-late-import";
        lateDraft.resolve();
        await holdDraft.promise;
      }
      return json(result);
    }
    if (path === "/conversations/mine") return json({ items: [], next_cursor_id: null });
    return json({ total: 0, conversations: 0, products: 0, available_credit: 0, reserved_credit: 0, balance_credit: 0 });
  });

  const editor = await context.newPage();
  const account = await context.newPage();
  await goto(editor, "/studio");
  await button(editor, "서버 초안 가져오기").click();
  await editor.getByText("A-private", { exact: true }).waitFor();
  await button(editor, "편집하기").click();
  await button(editor, "A-hero").click();
  await editor.locator('input[type=file][accept="image/png,image/jpeg,image/webp"]:not([multiple])')
    .setInputFiles({ name: "A-local.png", mimeType: "image/png", buffer: png });
  const portrait = editor.getByAltText("A-local.png");
  await portrait.waitFor();
  await editor.waitForFunction(() => document.querySelector('img[alt="A-local.png"]')?.naturalWidth === 1);
  await editor.getByRole("button", { name: "내 작업실 열기" }).click();
  await button(editor, "새 작품").click();
  await editor.getByLabel("작품 제목").fill("A-trash");
  await button(editor, "작품 삭제").click();
  await button(editor, "휴지통으로 이동").click();
  await editor.getByRole("banner").getByText("이 브라우저에 저장됨", { exact: true }).waitFor();
  const owned = await exportJSON(editor);
  assert.equal(owned.trash[0].label, "A-trash");
  assetId = owned.works[0].project.characters[0].assets[0].id;
  assert.equal(owned.works[0].project.work.worldRules, "A-secret");
  assert.deepEqual(await workspace(editor, "user:A"), owned);
  assert.deepEqual(await bytes(editor, ["user:A", assetId]), [...png]);
  const inventory = await context.newPage();
  await goto(inventory, "/account/works");
  await inventory.locator("#browser-works").getByText("A-private").waitFor();
  await goto(account, "/account/settings");
  await button(account, "로그아웃").click();
  await account.waitForURL("**/login");
  await inventory.locator("#browser-works").getByText("이 브라우저에 저장된 초안이 없어요").waitFor();
  await assertIsolated(editor, account, "guest", assetId);

  await button(editor, "새 작품").click();
  await editor.getByLabel("작품 제목").fill("Guest-local");
  await editor.getByRole("banner").getByText("이 브라우저에 저장됨", { exact: true }).waitFor();
  await login(account, "B");
  await assertIsolated(editor, account, "user:B", assetId);
  await button(editor, "서버 초안 가져오기").click();
  await editor.getByText("B-private", { exact: true }).waitFor();
  await button(editor, "편집하기").click();
  await button(editor, "B-hero").click();
  await editor.getByText("이미지를 다시 등록해 주세요.").waitFor();
  assert.equal(await editor.locator('img[src^="blob:"]').count(), 0);
  await editor.getByRole("banner").getByText("이 브라우저에 저장됨", { exact: true }).waitFor();
  await inventory.locator("#browser-works").getByText("B-private").waitFor();
  assert.doesNotMatch(await inventory.locator("#browser-works").innerText(), /A-private/);
  const savedB = await workspace(editor, "user:B");
  assert.equal(savedB.works[0].project.work.title, "B-private");

  await goto(editor, "/studio");
  await login(account, "A");
  const importing = await context.newPage();
  await goto(importing, "/studio");
  await importing.getByText("A-private", { exact: true }).waitFor();
  await goto(editor, "/studio?work=work-A");
  await editor.getByLabel("작품 제목").waitFor();
  // Capture just the scheduled autosave, then deliberately invoke even after clearTimeout.
  await editor.evaluate(() => {
    const schedule = window.setTimeout.bind(window);
    window.setTimeout = (callback, delay, ...args) => {
      if (delay === 450) { window.oldSave = () => callback(...args); return -1; }
      return schedule(callback, delay, ...args);
    };
    const get = IDBObjectStore.prototype.get;
    IDBObjectStore.prototype.get = function(key) {
      const read = get.call(this, key);
      read.addEventListener("success", event => {
        event.stopImmediatePropagation();
        IDBObjectStore.prototype.get = get;
        window.oldImage = () => read.onsuccess(event);
      }, { once: true });
      return read;
    };
  });
  await editor.getByLabel("작품 제목").fill("A-late-edit");
  await editor.waitForFunction(() => typeof window.oldSave === "function");
  await button(editor, "A-hero").click();
  await editor.waitForFunction(() => typeof window.oldImage === "function");
  holdDraft = deferred();
  await button(importing, "서버 초안 가져오기").click();
  await lateDraft.promise;
  holdMe = deferred();
  const switching = login(account, "B");
  await editor.getByText("작업실 계정을 확인하고 있어요.").waitFor();
  assert.doesNotMatch(await editor.locator("body").innerText(), /A-late-edit|A-hero/);
  assert.equal(await editor.locator('img[src^="blob:"]').count(), 0);
  holdMe.resolve(); holdMe = null;
  await switching;
  await importing.getByText("B-private", { exact: true }).waitFor();
  const completed = importing.waitForResponse(response => response.url().endsWith("/product-A/studio-draft"));
  holdDraft.resolve(); holdDraft = null;
  await (await completed).finished();
  await editor.evaluate(() => { window.oldSave(); window.oldImage(); });
  await editor.getByText(/해당 초안을 찾지 못했어요/).waitFor();
  assert.deepEqual(await workspace(editor, "user:B"), savedB);
  assert.deepEqual(await workspace(editor, "user:A"), owned);
  assert.deepEqual(await exportJSON(importing), savedB);
  assert.equal(await raw(editor, "chat-kit-studio-server-v1:B:late-work"), null);
  assert.equal(await raw(editor, "chat-kit-studio-server-v1:A:late-work"), null);
  assert.equal(await bytes(importing, ["user:B", assetId]), null);
  assert.equal(await editor.locator('img[src^="blob:"]').count(), 0);
  await login(account, "A");
  await button(editor, "A-hero").click();
  await portrait.waitFor();
  assert.deepEqual(await bytes(importing, ["user:A", assetId]), [...png]);
  assert.deepEqual(await exportJSON(importing), owned);
  assert.equal((await workspace(editor, "guest")).works[0].project.work.title, "Guest-local");
  assert.deepEqual(await workspace(editor, "user:B"), savedB);
  await button(editor, "발행").click();
  const project = await exportJSON(editor, "초안 JSON 내보내기");
  assert.deepEqual(project, owned.works[0].project);
  await button(account, "로그아웃").click();
  await importing.getByText("Guest-local", { exact: true }).waitFor();
  assert.equal((await exportJSON(importing)).works[0].project.work.title, "Guest-local");
  assert.deepEqual(pageErrors, []);
});

test("unreadable and legacy data stay in place and bare image IDs cannot resolve through a server document", async t => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  const shared = documentFor("unknown");
  const remote = documentFor("A", [{ id: "old-file", name: "remote-reference.png", usage: "portrait" }]);
  let offline = false;
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (!url.pathname.startsWith("/backend/")) return route.continue();
    if (url.pathname.endsWith("/auth/me")) return route.fulfill({ status: offline ? 503 : 200, json: { id: "A" } });
    if (url.pathname.endsWith("/studio-draft")) return route.fulfill({ json: { product_id: "p", revision: 1, document: remote } });
    return route.fulfill({ status: 404, json: {} });
  });
  await goto(page, "/login");
  const sharedKey = prefix + "-unreadable-backup-100";
  await page.evaluate(async ({prefix, sharedKey, shared}) => {
    localStorage.setItem(prefix, JSON.stringify({ version: 3, works: [{ id: "unknown", project: shared }], characters: [], lorebooks: [], trash: [] }));
    localStorage.setItem("chat-kit-studio-draft-v2", JSON.stringify(shared));
    localStorage.setItem("chat-kit-studio-draft-v1", "unknown-v1");
    localStorage.setItem(sharedKey, "unknown-backup");
    localStorage.setItem(prefix + ":user:A", "unreadable-A");
    await new Promise((resolve, reject) => {
      const open = indexedDB.open("chat-kit-studio-assets", 1);
      open.onupgradeneeded = () => open.result.createObjectStore("images");
      open.onsuccess = () => {
        const db = open.result;
        const tx = db.transaction("images", "readwrite");
        tx.objectStore("images").put(new Blob(["unknown bytes"]), "old-file");
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onerror = () => reject(tx.error);
      };
    });
  }, {prefix, sharedKey, shared});
  const oldV3 = await raw(page, prefix);
  await goto(page, "/studio?product=p");
  await button(page, "A-hero").click();
  await page.getByText("이미지를 다시 등록해 주세요.").waitFor();
  assert.equal(await page.locator('img[src^="blob:"]').count(), 0);
  assert.equal(await bytes(page, ["user:A", "old-file"]), null);
  assert.deepEqual(await bytes(page, "old-file"), [...Buffer.from("unknown bytes")]);
  await page.getByRole("banner").getByText("이 브라우저에 저장됨", { exact: true }).waitFor();
  const backups = await page.evaluate(key => Object.keys(localStorage).filter(k => k.startsWith(key)).map(k => localStorage[k]), prefix + ":user:A-unreadable-backup-");
  assert.deepEqual(backups, ["unreadable-A"]);
  assert.equal(await raw(page, prefix), oldV3);
  assert.equal(await raw(page, sharedKey), "unknown-backup");
  assert.equal(await raw(page, "chat-kit-studio-draft-v2"), JSON.stringify(shared));
  assert.equal(await raw(page, "chat-kit-studio-draft-v1"), "unknown-v1");
  offline = true;
  await goto(page, "/studio");
  await button(page, "익명 작업실 열기").click();
  assert.deepEqual(await exportJSON(page), { version: 3, works: [], characters: [], lorebooks: [], trash: [] });
});
