// Route UUIDs can use a different textual form from the canonical API value.
export function conversationKey(id: string): string {
  return id.toLowerCase().replace(/^urn:uuid:/, "").replace(/[{}-]/g, "");
}
