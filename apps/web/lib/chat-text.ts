export type ChatTextPart = { text: string; narration: boolean };

/** Asterisks are story notation, not HTML or general Markdown. */
export function readChatText(value: string, character = false): ChatTextPart[][] {
  const paragraphs: ChatTextPart[][] = [[]];
  const markers = [...value.matchAll(/(?<!\*)\*\*(?!\*)/gu)];
  function append(text: string, narration: boolean) {
    text.split(/\r?\n[ \t]*\r?\n/).forEach((line, index) => {
      if (index > 0) paragraphs.push([]);
      if (line) paragraphs[paragraphs.length - 1].push({ text: line, narration });
    });
  }
  let cursor = 0;
  for (let i = 0; i + 1 < markers.length; i += 2) {
    const start = markers[i].index;
    const end = markers[i + 1].index;
    append(value.slice(cursor, start), false);
    append(value.slice(start + 2, end), true);
    cursor = end + 2;
  }
  append(value.slice(cursor), false);
  return paragraphs.filter(parts => parts.length).map(parts => {
    if (!character || parts.some(part => part.narration) || /^\s*["“‘「『]/u.test(parts[0].text)) return parts;
    return parts.map(part => ({ ...part, narration: true }));
  });
}

export function wrapChatNarration(value: string, start: number, end: number) {
  const selection = value.slice(start, end);
  return {
    value: value.slice(0, start) + "**" + selection + "**" + value.slice(end),
    selectionStart: start + 2,
    selectionEnd: end + 2,
  };
}

export function shouldSendOnEnter(event: { key: string; shiftKey: boolean; isComposing: boolean; keyCode: number }, composing: boolean, mobile: boolean) {
  return event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229 && !composing && !mobile;
}
