export type PromptMessage = { role: string; content: string };
export function parseMessages(raw: string, version: number): PromptMessage[] | null {
  if (version !== 1) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.chat_message_format !== 1 || !Array.isArray(parsed.messages) || !parsed.messages.length) return null;
    if (!parsed.messages.every((item: unknown) => item && typeof item === "object" && "role" in item && typeof item.role === "string" && "content" in item && typeof item.content === "string")) return null;
    return parsed.messages.map((item: PromptMessage) => ({ role: item.role, content: item.content }));
  } catch { return null; }
}
export async function copyOriginal(raw: string, clipboard: Pick<Clipboard, "writeText"> | undefined): Promise<void> {
  if (!clipboard) throw new Error("clipboard_unavailable");
  await clipboard.writeText(raw);
}
