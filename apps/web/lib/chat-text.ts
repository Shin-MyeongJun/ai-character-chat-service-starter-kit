export type ChatTextPart = { text: string; narration: boolean };

export function readChatText(value: string, character = false): ChatTextPart[][] {
  return readChatTextBlocks([value], character)[0];
}

/** Match story notation across the reply, then return paragraphs at each original block position. */
export function readChatTextBlocks(blocks: readonly string[], character = false): ChatTextPart[][][] {
  const value = blocks.join("");
  const markers = [...value.matchAll(/(?<!\*)\*\*(?!\*)/gu)];
  if (markers.length % 2 !== 0) markers.pop();

  const paragraphs = value.split(/(\r?\n[ \t]*\r?\n)/);
  const blockParagraphs: ChatTextPart[][][] = blocks.map(() => []);
  let markerIndex = 0;
  let blockIndex = 0;
  let blockEnd = blocks[0]?.length ?? 0;
  let cursor = 0;

  for (let i = 0; i < paragraphs.length; i += 2) {
    const paragraph = paragraphs[i];
    const paragraphEnd = cursor + paragraph.length;
    // A closing marker still sets the style boundary when it starts a paragraph.
    const hasNotation = markerIndex % 2 !== 0 || (markers[markerIndex]?.index ?? Infinity) < paragraphEnd;
    let renderedParagraph: ChatTextPart[] | undefined;

    while (cursor < paragraphEnd) {
      const nextMarker = markers[markerIndex]?.index ?? Infinity;
      if (cursor === nextMarker) {
        cursor += 2;
        markerIndex++;
        continue;
      }
      if (cursor >= blockEnd) {
        blockIndex++;
        blockEnd += blocks[blockIndex].length;
        renderedParagraph = undefined;
        continue;
      }
      if (!renderedParagraph) {
        renderedParagraph = [];
        blockParagraphs[blockIndex].push(renderedParagraph);
      }
      const partEnd = Math.min(paragraphEnd, blockEnd, nextMarker);
      const text = value.slice(cursor, partEnd);
      const legacyNarration = character && !hasNotation && !/^\s*["“‘「『]/u.test(text);
      renderedParagraph.push({ text, narration: legacyNarration || markerIndex % 2 !== 0 });
      cursor = partEnd;
    }
    cursor = paragraphEnd + (paragraphs[i + 1]?.length ?? 0);
  }

  return blockParagraphs;
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
