const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const ts = require("typescript");

const exportsObject = {};
const source = readFileSync(resolve(__dirname, "../lib/chat-text.ts"), "utf8");
new Function("exports", ts.transpile(source, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }))(exportsObject);
const { readChatText, wrapChatNarration, shouldSendOnEnter } = exportsObject;

test("wrapping a selection preserves multiple paragraphs and surrounding dialogue", () => {
  const first = "문을 연다.\n\n열쇠를 놓는다.";
  const wrapped = wrapChatNarration(first + "\n읽어 볼까요?", 0, first.length);
  assert.equal(wrapped.value.slice(wrapped.selectionStart, wrapped.selectionEnd), first);
  assert.deepEqual(readChatText(wrapped.value), [
    [{ text: "문을 연다.", narration: true }],
    [{ text: "열쇠를 놓는다.", narration: true }, { text: "\n읽어 볼까요?", narration: false }],
  ]);
});

test("unpaired marks and HTML-like text stay literal", () => {
  assert.deepEqual(readChatText("말해요 **<img src=x>"), [[{ text: "말해요 **<img src=x>", narration: false }]]);
  assert.deepEqual(wrapChatNarration("안녕", 1, 1), { value: "안****녕", selectionStart: 3, selectionEnd: 3 });
});

test("only a plain desktop Enter sends; Korean composition and mobile Enter do not", () => {
  const event = { key: "Enter", shiftKey: false, isComposing: false, keyCode: 13 };
  assert.equal(shouldSendOnEnter(event, false, false), true);
  assert.equal(shouldSendOnEnter(event, true, false), false);
  assert.equal(shouldSendOnEnter({ ...event, isComposing: true }, false, false), false);
  assert.equal(shouldSendOnEnter({ ...event, keyCode: 229 }, false, false), false);
  assert.equal(shouldSendOnEnter({ ...event, shiftKey: true }, false, false), false);
  assert.equal(shouldSendOnEnter(event, false, true), false);
});
