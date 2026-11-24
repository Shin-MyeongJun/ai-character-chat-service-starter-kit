import type { ContentBlock } from "@/lib/api";
import { readChatText, readChatTextBlocks, type ChatTextPart } from "@/lib/chat-text";
import { ChatImageFrame } from "./chat-images";
import styles from "./chat.module.css";

function ChatProse({ paragraphs, character }: { paragraphs: ChatTextPart[][]; character: boolean }) {
  return <div className={styles.prose}>{paragraphs.map((paragraph, index) =>
    <p key={index} className={character && paragraph.every(part => !part.narration) ? styles.speechLine : undefined}>
      {paragraph.map((part, partIndex) => <span key={partIndex} className={part.narration ? styles.narration : styles.speech}>{part.text}</span>)}
    </p>,
  )}</div>;
}

export function ChatBlocks({ blocks, content, showImages, opening = false, character = false }: {
  blocks?: ContentBlock[] | null;
  content: string;
  showImages: boolean;
  opening?: boolean;
  character?: boolean;
}) {
  if (blocks == null) return opening ? <p>{content}</p>
    : <ChatProse paragraphs={readChatText(content, character)} character={character} />;

  const paragraphs = opening ? null : readChatTextBlocks(blocks.map(block => block.type === "text" ? block.text : ""), character);
  return blocks.map((block, index) => {
    if (block.type === "image") return showImages && <ChatImageFrame key={index} image={block} />;
    if (!paragraphs) return <p key={index}>{block.text}</p>;
    return <ChatProse key={index} paragraphs={paragraphs[index]} character={character} />;
  });
}
