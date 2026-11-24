const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const { createElement } = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const ts = require("typescript");

function load(path, imports = {}) {
  const source = readFileSync(resolve(__dirname, "..", path), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  });
  const exports = {};
  new Function("exports", "require", outputText)(exports, name => imports[name] ?? require(name));
  return exports;
}

const styles = { prose: "prose", narration: "narration", speech: "speech", speechLine: "speechLine", imageFrame: "imageFrame" };
const { ChatBlocks } = load("components/chat/chat-blocks.tsx", {
  "@/lib/chat-text": load("lib/chat-text.ts"),
  "./chat-images": load("components/chat/chat-images.tsx", { "@/lib/api": {}, "./chat.module.css": styles }),
  "./chat.module.css": styles,
});

const image = {
  type: "image", image_item_id: "scene", file_version_id: "image-version",
  alt: "열린 문", content_url: "/conversations/example/messages/answer/blocks/1/image",
};
const text = value => ({ type: "text", text: value });
const render = props => renderToStaticMarkup(createElement(ChatBlocks, { character: true, showImages: true, ...props }));
const spans = html => Array.from(html.matchAll(/<span class="(narration|speech)">(.*?)<\/span>/gs), match => match.slice(1));

test("narration crosses an image without changing text styles when the image is hidden", () => {
  for (const separator of ["", "\r\n\r\n"]) {
    const first = `**문이 열렸다.${separator}`;
    const last = "그가 들어왔다.** “기다렸어.”";
    const props = { content: first + last, blocks: [text(first), image, text(last)] };
    const visible = render(props);
    const hidden = render({ ...props, showImages: false });
    const expected = [["narration", "문이 열렸다."], ["narration", "그가 들어왔다."], ["speech", " “기다렸어.”"]];

    assert.deepEqual(spans(visible), expected);
    assert.match(visible, /문이 열렸다\.<\/span><\/p><\/div><figure.*?<\/figure><div class="prose"><p><span class="narration">그가 들어왔다\./s);
    assert.equal((visible.match(/<img\b/g) ?? []).length, 1);
    assert.ok(visible.includes(`src="/backend${image.content_url}"`));
    assert.equal(visible.replace(/<figure.*?<\/figure>/s, ""), hidden);
    const legacySpans = separator ? expected : [["narration", "문이 열렸다.그가 들어왔다."], expected[2]];
    assert.deepEqual(spans(render({ content: props.content, blocks: null })), legacySpans);
  }
});

test("inner thoughts and actions use narration while inline dialogue uses the default color", () => {
  const blocks = [text("**괜히 왔나"), image, text(" 싶었다.** “저기요.” "), text("**그가 고개를 들었다.**")];
  const content = blocks.filter(block => block.type === "text").map(block => block.text).join("");
  const expected = [["speech", " “저기요.” "], ["narration", "그가 고개를 들었다."]];

  assert.deepEqual(spans(render({ content, blocks })), [["narration", "괜히 왔나"], ["narration", " 싶었다."], ...expected]);
  assert.deepEqual(spans(render({ content })), [["narration", "괜히 왔나 싶었다."], ...expected]);
});

test("a closing marker restores default text color even at the start of a paragraph", () => {
  const first = "**그는 잠시 생각했다.\n\n";
  const last = "** 기다렸어.";
  const props = { content: first + last, blocks: [text(first), image, text(last)] };
  const expected = [["narration", "그는 잠시 생각했다."], ["speech", " 기다렸어."]];

  assert.deepEqual(spans(render(props)), expected);
  assert.deepEqual(spans(render({ content: props.content })), expected);
});

test("unpaired markers stay literal and unmarked paragraphs keep their existing styles", () => {
  const first = "그가 문을 바라봤다.";
  const last = "“잠깐만.” **<img src=x>";
  const expected = [["narration", "그가 문을 바라봤다."], ["speech", "“잠깐만.” **&lt;img src=x&gt;"]];

  for (const separator of ["", "\n\n"]) {
    assert.deepEqual(spans(render({ content: first + separator + last, blocks: [text(first + separator), image, text(last)] })), expected);
  }
  assert.deepEqual(spans(render({ content: `${first}\n\n${last}` })), expected);
  assert.deepEqual(spans(render({ content: "“잠깐만.”" })), [["speech", "“잠깐만.”"]]);
  assert.deepEqual(spans(render({ content: "그가 문을 바라봤다." })), [["narration", "그가 문을 바라봤다."]]);
});
