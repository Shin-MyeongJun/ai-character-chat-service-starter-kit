// Run against the explicitly configured standalone fixture, never a real API.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
if (process.env.ADMIN_FIXTURE !== "1") throw new Error("Browser suite requires ADMIN_FIXTURE=1 and the fixture API.");
const base = process.env.ADMIN_BROWSER_URL ?? "http://127.0.0.1:3100";
const fixture = process.env.ADMIN_FIXTURE_URL ?? "http://127.0.0.1:8100";
const out = path.resolve(__dirname, "../../..", "docs/assets/admin-web-implementation");
const id = n => `d274c6a0-a613-4d20-972f-${String(n).padStart(12, "0")}`;
const control = async value => { const response = await fetch(`${fixture}/__fixture/control`, { method: "POST", body: JSON.stringify(value) }); assert.equal(response.status, 200); };
let checks = 0;
const pass = label => { checks++; console.log(`PASS ${checks}: ${label}`); };
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: process.env.ADMIN_BROWSER_CHANNEL ?? "msedge" });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1120 }, permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage(); const errors = [];
  page.on("pageerror", error => errors.push(error.name));
  async function shot(name) {
    await page.evaluate(() => document.fonts.ready);
    const buffer = await page.screenshot({ fullPage: true });
    const target = path.join(out, `${name}.png`);
    // Desktop file indexers can briefly hold a previous screenshot open on Windows.
    for (let attempt = 0; ; attempt++) {
      try { fs.writeFileSync(target, buffer); return; }
      catch (error) { if (attempt >= 5) throw error; await new Promise(resolve => setTimeout(resolve, 200)); }
    }
  }
  async function login(email = "admin@example.test") {
    await page.goto(`${base}/login`); await page.getByLabel("이메일", { exact: true }).fill(email); await page.getByLabel("비밀번호", { exact: true }).fill("fixture-password"); await page.getByRole("button", { name: "로그인", exact: true }).click();
  }
  async function listReady() { await page.getByRole("table").waitFor(); }
  async function noOverflow() {
    const result = await page.evaluate(() => ({ viewport: innerWidth, height: innerHeight, body: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight, panels: [...document.querySelectorAll(".main, .metadata, .prompt-viewer, .filters")].map(el => ({ class: el.className, right: el.getBoundingClientRect().right })) }));
    assert.ok(result.body <= result.viewport, `Page overflow ${JSON.stringify(result)}`);
    assert.ok(result.panels.every(panel => panel.right <= result.viewport + 1));
    assert.ok(result.scrollHeight <= result.height + 1, `Internal scroll regions must not expand the page height: ${JSON.stringify(result)}`);
  }
  try {
    await control({});
    await page.goto(`${base}/generation-prompts`); await page.waitForURL(/\/login\?reason=expired/); pass("unauthenticated direct entry redirects with return URL");
    await page.getByLabel("이메일", { exact: true }).fill("admin@example.test"); await page.getByLabel("비밀번호", { exact: true }).fill("wrong-password"); await page.getByRole("button", { name: "로그인", exact: true }).click(); await page.getByText("이메일 또는 비밀번호를 확인해 주세요.").waitFor(); pass("login failure stays on login");
    await page.goto(`${base}/login`); await shot("login-1440");
    await control({ loginDelay: 500 }); await login(); await page.getByRole("button", { name: "로그인 중…" }).waitFor(); await listReady(); await control({}); pass("login progress then server-authorized list");
    const cookies = await context.cookies(); assert.ok(cookies.some(cookie => cookie.name === "chatkit_access" && cookie.httpOnly)); pass("proxy forwards HttpOnly cookie");
    await shot("list-1440"); await noOverflow();
    await page.setViewportSize({ width: 1280, height: 1120 }); await noOverflow(); await shot("list-1280"); pass("1440 and 1280 list layout has no page overflow with long model and UUID");
    await page.getByRole("combobox", { name: "생성 상태" }).selectOption("failed"); await page.getByRole("button", { name: "검색", exact: true }).click(); await page.waitForURL(/status=failed/); await listReady();
    await page.getByRole("combobox", { name: "페이지당" }).selectOption("20"); await page.waitForURL(/page_size=20/); await listReady();
    await page.getByRole("button", { name: "다음", exact: true }).click(); await page.waitForURL(/page=2/); await listReady(); const savedUrl = page.url();
    await page.getByRole("link", { name: /상세 보기$/ }).first().click(); await page.getByRole("heading", { name: "프롬프트 원문", exact: true }).waitFor(); await page.getByRole("link", { name: "‹ 목록으로" }).click(); await listReady(); assert.equal(page.url(), savedUrl); pass("filter, page size and page 2 survive detail and list return");
    await page.getByRole("button", { name: "초기화", exact: true }).click(); await page.waitForURL(url => !url.searchParams.has("status") && url.searchParams.get("page") === "1"); await listReady();
    await page.getByRole("link", { name: `${id(1)} 상세 보기`, exact: true }).click(); await page.getByRole("region", { name: "역할별 프롬프트", exact: true }).waitFor(); await noOverflow(); await shot("detail-1280");
    await page.setViewportSize({ width: 1440, height: 1120 }); await noOverflow(); await shot("detail-1440"); pass("role detail at both desktop widths");
    await page.getByRole("button", { name: "원본 JSON 문자열", exact: true }).click(); const original = await page.locator(".prompt-viewer pre").textContent();
    await page.evaluate(() => { const write = navigator.clipboard.writeText.bind(navigator.clipboard); navigator.clipboard.writeText = async text => { window.__copiedOriginal = text; return write(text); }; });
    await page.getByRole("button", { name: "원문 복사", exact: true }).click(); await page.getByText("원문 전체를 복사했습니다.").waitFor();
    assert.ok(await page.evaluate(() => window.__copiedOriginal) === original, "writeText receives the original unchanged string");
    const pasted = await page.evaluate(() => navigator.clipboard.readText());
    // Windows CF_UNICODETEXT converts LF into CRLF; the application passes its original unchanged.
    assert.ok(pasted.replace(/\r\n/g, "\n") === original.replace(/\r\n/g, "\n"), "native clipboard text matches (platform newline normalization only)");
    await shot("raw-1440"); pass("unchanged original passed to clipboard; native Windows line endings accounted for");
    await page.evaluate(() => { window.__clipboardWrite = navigator.clipboard.writeText.bind(navigator.clipboard); navigator.clipboard.writeText = async () => { throw new DOMException("denied", "NotAllowedError"); }; });
    await page.getByRole("button", { name: "복사 완료", exact: true }).click(); await page.getByText(/복사하지 못했습니다/).waitFor(); await page.evaluate(() => { navigator.clipboard.writeText = window.__clipboardWrite; }); pass("clipboard failure is visible and does not report success");
    const stored = await page.evaluate(() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)]); assert.equal(stored.length, 0); pass("no auth token or prompt content in browser storage");
    await control({ long: true }); await page.reload(); await page.getByRole("region", { name: "역할별 프롬프트", exact: true }).waitFor(); await noOverflow();
    await page.getByLabel("긴 줄 줄바꿈", { exact: true }).uncheck(); await noOverflow(); assert.ok(await page.locator(".prompt-viewer").evaluate(el => el.scrollWidth > el.clientWidth)); await shot("long-nowrap-1440"); pass("long text scrolls internally with wrap off");
    await control({ malformed: true }); await page.reload(); await page.getByText("역할별로 해석할 수 없는 형식입니다.", { exact: false }).waitFor(); assert.equal(await page.locator(".prompt-viewer pre").textContent(), "not-valid-json\n  원본 문자열 그대로  \n"); pass("malformed role JSON keeps original text available");
    await control({}); await page.goto(`${base}/generation-prompts/${id(6)}`); await page.getByRole("heading", { name: "기록된 프롬프트 원문이 없습니다." }).waitFor(); assert.ok(await page.getByRole("button", { name: "원문 복사", exact: true }).isDisabled()); await shot("unrecorded-1440"); pass("unrecorded 200 is distinct and copy is disabled");
    await page.goto(`${base}/generation-prompts/${id(9999)}`); await page.getByRole("heading", { name: "생성 기록을 찾을 수 없습니다." }).waitFor(); await shot("not-found-1440"); pass("missing generation is a separate 404 state");
    await control({ detailError: true }); await page.goto(`${base}/generation-prompts/${id(1)}`); await page.getByRole("heading", { name: "상세를 조회하지 못했습니다." }).waitFor(); await control({}); await page.getByRole("button", { name: "다시 시도" }).click(); await page.getByRole("region", { name: "역할별 프롬프트", exact: true }).waitFor(); pass("detail error retries successfully");
    await control({ empty: true }); await page.goto(`${base}/generation-prompts`); await page.getByRole("heading", { name: "검색 결과가 없습니다." }).waitFor(); await shot("empty-1440"); pass("empty results");
    await control({ listError: true }); await page.getByRole("button", { name: "검색", exact: true }).click(); await page.getByRole("heading", { name: "조회하지 못했습니다." }).waitFor(); await shot("error-1440"); await control({}); await page.getByRole("button", { name: "다시 시도" }).click(); await listReady(); pass("list error leaves count unknown and retries");
    await control({ delay: 900 }); await page.getByRole("button", { name: "검색", exact: true }).click(); await page.getByRole("heading", { name: "생성 프롬프트를 불러오는 중입니다." }).waitFor(); await shot("loading-1440"); await listReady(); await control({}); pass("loading does not display stale result count");
    let oldStarted; const began = new Promise(resolve => { oldStarted = resolve; });
    const delayed = async route => { const url = new URL(route.request().url()); if (url.searchParams.get("status") === "failed" && url.searchParams.get("page_size") !== "1") { const response = await route.fetch(); oldStarted(); await new Promise(resolve => setTimeout(resolve, 700)); try { await route.fulfill({ response }); } catch {} } else await route.continue(); };
    await page.route("**/backend/admin/reporting/generation-prompts?**", delayed);
    await page.getByRole("combobox", { name: "생성 상태" }).selectOption("failed"); await page.getByRole("button", { name: "검색", exact: true }).click(); await began;
    await page.getByRole("combobox", { name: "생성 상태" }).selectOption("succeeded"); await page.getByRole("button", { name: "검색", exact: true }).click(); await page.waitForURL(/status=succeeded/); await listReady(); await page.waitForTimeout(850);
    assert.equal(await page.getByRole("combobox", { name: "생성 상태" }).inputValue(), "succeeded"); assert.equal(await page.locator("tbody .badge.failed").count(), 0); await page.unroute("**/backend/admin/reporting/generation-prompts?**", delayed); pass("older delayed search cannot overwrite the newer query");
    await page.getByRole("textbox", { name: "대화 ID", exact: true }).fill("bad-uuid"); await page.getByRole("button", { name: "검색", exact: true }).click(); await page.getByText("대화 ID는 UUID 전체를 입력해 주세요.").waitFor(); pass("invalid filters are explained before request");
    await control({ forbidden: true }); await page.getByRole("button", { name: "초기화", exact: true }).click(); await page.waitForURL(/\/forbidden$/); await page.getByRole("heading", { name: "접근 권한이 없습니다." }).waitFor(); assert.equal(await page.locator("table, .prompt-viewer").count(), 0); await shot("forbidden-1440"); pass("server permission revocation hides data and shows access denied");
    await control({}); await page.getByRole("button", { name: "로그아웃 후 다시 로그인" }).click(); await page.waitForURL(/\/login$/); await login("user@example.test"); await page.waitForURL(/\/forbidden$/); pass("authenticated non-admin cannot enter list");
    await page.getByRole("button", { name: "로그아웃 후 다시 로그인" }).click(); await page.waitForURL(/\/login$/); await login(); await listReady();
    await control({ expired: true }); await page.getByRole("button", { name: "검색", exact: true }).click(); await page.waitForURL(/\/login\?reason=expired/); await page.getByText(/세션이 만료되었거나 유효하지 않습니다/).waitFor(); pass("expired session returns to login and preserves destination");
    await control({}); await login(); await listReady();
    const second = await context.newPage(); await second.goto(`${base}/generation-prompts`); await second.getByRole("table").waitFor();
    await page.getByRole("button", { name: "로그아웃", exact: true }).click(); await page.waitForURL(/\/login$/); await second.waitForURL(/\/login\?reason=expired/); pass("logout clears session and hides another tab through BroadcastChannel"); await second.close();
    await page.goto(`${base}/login`); await page.keyboard.press("Tab"); assert.equal(await page.evaluate(() => document.activeElement?.id), "email"); assert.ok(await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle !== "none")); pass("keyboard focus is visible");
    assert.deepEqual(errors, []); pass("no uncaught browser errors");
    fs.writeFileSync(path.join(out, "verification.json"), JSON.stringify({ kind: "development-fixture", checks, viewports: [1440, 1280], errors, screenshots: fs.readdirSync(out).filter(name => name.endsWith(".png")) }, null, 2) + "\n");
    console.log(`Browser verification: ${checks} passed. Synthetic fixture; not real API integration.`);
  } finally { await control({}); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
