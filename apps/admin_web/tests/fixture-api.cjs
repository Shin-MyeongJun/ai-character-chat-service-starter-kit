// Explicit, standalone synthetic backend. Never imported by the Next application.
const http = require("node:http");
const crypto = require("node:crypto");
if (process.env.ADMIN_FIXTURE !== "1" || process.env.NODE_ENV === "production") throw new Error("Set ADMIN_FIXTURE=1 in a development/test shell only.");
const port = Number(process.env.ADMIN_FIXTURE_PORT ?? 8100);
const id = n => `d274c6a0-a613-4d20-972f-${String(n).padStart(12, "0")}`;
const conversation = "80d4cbe2-6338-40f8-a734-6a29b685f723";
const user = { id: id(900), email: "admin@example.test", email_verified: true };
const sessions = new Map(); let controls = {};
const raw = '{\n  "chat_message_format": 1,\n  "messages": [\n    {"role":"system","content":"당신은 가상의 별빛 기록실 안내자입니다. 주어진 설정과 대화의 맥락을 따르고 한국어로 답변합니다."},\n    {"role":"user","content":"{\\"reference_data\\":{\\"setting\\":\\"별빛 기록실\\",\\"characters\\":[{\\"name\\":\\"에린\\",\\"role\\":\\"기록실 안내자\\"}],\\"active_lore\\":[],\\"memories\\":[]}}"},\n    {"role":"assistant","content":"에린이 오래된 장부를 덮으며 고개를 들었다. ‘기록실에 오신 것을 환영해요. 어떤 이야기를 찾고 계신가요?’"},\n    {"role":"user","content":"마지막으로 관측된 별의 기록을 찾고 있어요.\\n<literal>원문 문자열 보존 확인</literal>"}\n  ]\n}\n';
const longRaw = JSON.stringify({ chat_message_format: 1, messages: [{ role: "system", content: "긴 원문과 줄바꿈 검증\n".repeat(300) + "very-long-line-".repeat(160) }] });
function items() {
  const now = new Date(); const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  return Array.from({ length: 128 }, (_, index) => ({ generation_id: id(index + 1), conversation_id: index % 3 ? id(800 + index) : conversation,
    model_id: id(600), model_name: index === 1 ? "Claude Sonnet 4.5 20250929 very-long-model-name-without-spaces-".repeat(3) : ["GPT-4.1", "Claude Sonnet 4.5 20250929", "Gemini 2.5 Pro"][index % 3],
    reasoning_effort: ["medium", "none", "high", "low"][index % 4], status: ["succeeded", "failed", "pending", "cancelled", "stale"][index % 5],
    created_at: `${day}T${String(5 - Math.floor(index / 60)).padStart(2, "0")}:${String(59 - index % 60).padStart(2, "0")}:08Z`, finished_at: index % 5 === 2 ? null : `${day}T06:00:00Z`,
    history_invalidated_at: null, prompt_recorded: index !== 5, prompt_created_at: index === 5 ? null : `${day}T05:32:08Z`, provider: index === 5 ? null : "openai" }));
}
async function body(request) { let value = ""; for await (const chunk of request) value += chunk; return value ? JSON.parse(value) : {}; }
http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${port}`);
  const cookies = Object.fromEntries((request.headers.cookie ?? "").split(";").filter(Boolean).map(pair => pair.trim().split("=")));
  const send = (status, data, cookie) => { response.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store", ...(cookie ? { "Set-Cookie": cookie } : {}) }); response.end(status === 204 ? undefined : JSON.stringify(data)); };
  try {
    if (url.pathname === "/__fixture/control" && request.method === "POST") { controls = await body(request); send(200, { fixture: true }); return; }
    if (url.pathname === "/auth/csrf") { send(200, { csrf_token: "fixture-csrf" }, "chatkit_csrf=fixture-csrf; Path=/; HttpOnly; SameSite=Lax"); return; }
    if (request.method === "POST" && (!request.headers.origin || request.headers["x-csrf-token"] !== "fixture-csrf" || cookies.chatkit_csrf !== "fixture-csrf")) { send(403, { error: { code: "csrf_failed" } }); return; }
    if (url.pathname === "/auth/login") {
      const input = await body(request);
      if (controls.loginDelay) await new Promise(resolve => setTimeout(resolve, controls.loginDelay));
      if (input.password !== "fixture-password" || !["admin@example.test", "user@example.test"].includes(input.email)) { send(401, { error: { code: "invalid_credentials" } }); return; }
      const token = crypto.randomUUID(); sessions.set(token, input.email);
      send(200, { ...user, email: input.email }, `chatkit_access=${token}; Path=/; HttpOnly; SameSite=Lax`); return;
    }
    if (url.pathname === "/auth/logout") { sessions.delete(cookies.chatkit_access); send(204, null, "chatkit_access=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"); return; }
    const email = sessions.get(cookies.chatkit_access);
    if (!email || controls.expired) { send(401, { error: { code: "invalid_session" } }); return; }
    if (url.pathname === "/auth/me") { send(200, { ...user, email }); return; }
    if (!url.pathname.startsWith("/admin/reporting/generation-prompts")) { send(404, { detail: "not_found" }); return; }
    if (email !== user.email || controls.forbidden) { send(403, { detail: "forbidden" }); return; }
    const list = url.pathname === "/admin/reporting/generation-prompts";
    const pageSize = Number(url.searchParams.get("page_size") ?? 50);
    if ((list && pageSize !== 1 && controls.listError) || (!list && controls.detailError)) { send(503, { detail: "unavailable" }); return; }
    if (controls.delay && (!list || pageSize !== 1)) await new Promise(resolve => setTimeout(resolve, controls.delay));
    if (list) {
      let result = items();
      for (const key of ["status", "conversation_id"]) if (url.searchParams.get(key)) result = result.filter(item => item[key] === url.searchParams.get(key));
      result = result.filter(item => { const date = new Date(Date.parse(item.created_at) + 9 * 3600000).toISOString().slice(0, 10); return date >= url.searchParams.get("date_from") && date <= url.searchParams.get("date_to"); });
      if (controls.empty && pageSize !== 1) result = [];
      const page = Number(url.searchParams.get("page") ?? 1);
      send(200, { items: result.slice((page - 1) * pageSize, page * pageSize), total: result.length, page, page_size: pageSize }); return;
    }
    const item = items().find(item => item.generation_id === url.pathname.split("/").at(-1));
    if (!item || controls.missing) { send(404, { detail: "not_found" }); return; }
    const text = controls.malformed ? "not-valid-json\n  원본 문자열 그대로  \n" : controls.long ? longRaw : raw;
    send(200, { generation: item, prompt: item.prompt_recorded ? { request_json: text, digest: crypto.createHash("sha256").update(text).digest("hex"), format_version: 1, created_at: item.created_at, provider: "openai", max_output_tokens: 2048 } : null });
  } catch { send(500, { detail: "fixture_error" }); }
}).listen(port, "127.0.0.1", () => console.log(`Development fixture API: http://127.0.0.1:${port} (synthetic data only)`));
