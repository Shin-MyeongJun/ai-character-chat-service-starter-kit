// Execute the actual hook through TypeScript transpilation and a minimal hook harness.
// No browser or network is used; this is not an E2E test.
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const webRequire = createRequire(path.join(root, 'apps/web/package.json'));
const ts = webRequire('typescript');
const source = fs.readFileSync(path.join(root, 'apps/web/components/recent-conversations.tsx'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020,
}}).outputText;
const state = [];
let slot = 0, mounted = false, effect, calls = 0, finishOldPage;
const events = new Map();
const row = id => ({ id, title: id, created_at: '2026-10-23T00:00:00Z', last_message: id });
const page = (id, more = false) => ({ items: [row(id)], next_cursor_id: more ? 'cursor-a' : null,
  next_cursor_created_at: more ? '2026-10-23T00:00:00Z' : null });
const api = {
  getMe: async () => ({}),
  listOwnedConversations: async () => {
    calls++;
    if (calls === 1) return page('A-first', true);
    if (calls === 2) return new Promise(resolve => { finishOldPage = resolve; });
    if (calls === 3) return page('B-first');
    throw new Error('Unexpected API request');
  },
};
const react = {
  useState(initial) {
    const index = slot++;
    if (!(index in state)) state[index] = initial;
    return [state[index], value => { state[index] = typeof value === 'function' ? value(state[index]) : value; }];
  },
  useEffect(fn) { if (!mounted) effect = fn; },
};
const windowStub = {
  addEventListener: (name, callback) => events.set(name, callback),
  removeEventListener: name => events.delete(name),
};
function requireStub(name) {
  if (name === 'react') return react;
  if (name === '@/lib/api') return api;
  if (name === '@/lib/recent-chats') return { AUTH_CHANGED_KEY: 'auth', RECENT_CHATS_EVENT: 'recent', readRecentChats: () => [] };
  if (name === '@/lib/works') return { demoWorkById: () => undefined };
  if (['react/jsx-runtime', 'next/link', 'lucide-react'].includes(name)) return {};
  throw new Error(`Unexpected import: ${name}`);
}
const mod = { exports: {} };
new Function('require', 'module', 'exports', 'window', compiled)(requireStub, mod, mod.exports, windowStub);
function render() {
  slot = 0;
  const hook = mod.exports.useConversationDirectory();
  if (!mounted) { mounted = true; effect(); }
  return hook;
}
async function drain() { for (let i = 0; i < 10; i++) await Promise.resolve(); }
(async () => {
  render(); await drain();
  let hook = render();
  assert.deepEqual(hook.recent.map(x => x.id), ['A-first']);
  const oldRequest = hook.loadMore();
  events.get('auth')(); await drain();
  hook = render();
  const before = hook.recent.map(x => x.id);
  assert.deepEqual(before, ['B-first']);
  finishOldPage(page('A-old-page'));
  await oldRequest; await drain();
  const after = render().recent.map(x => x.id);
  assert.deepEqual(after, ['B-first', 'A-old-page']);
  const result = { harness: 'actual hook with minimal useState/useEffect and deferred API doubles',
    before_old_response: before, after_old_response: after, api_requests: calls, browser_e2e: false };
  fs.writeFileSync(path.join(__dirname, 'frontend-verification.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
