import { listMessages, type ChatMessage } from "./api";

export type ConversationHistory = {
  conversationId: string;
  messages: ChatMessage[];
  historyRevision: number | null;
  syncCursor: string | null;
};

class HistoryChanged extends Error {}

// Route UUIDs can use a different textual form from the canonical API value.
const conversationKey = (id: string) => id.toLowerCase().replace(/^urn:uuid:/, "").replace(/[{}-]/g, "");

function mergeMessages(previous: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const messages = new Map(previous.map(message => [message.id, message]));
  for (const message of incoming) {
    const saved = messages.get(message.id);
    if (!saved || saved.revision <= message.revision) messages.set(message.id, message);
  }
  return [...messages.values()].sort((a, b) => a.position - b.position);
}

async function readHistory(
  id: string, previous?: ConversationHistory, signal?: AbortSignal,
): Promise<ConversationHistory> {
  const incremental = previous !== undefined && conversationKey(previous.conversationId) === conversationKey(id) && previous.historyRevision !== null;
  const messages = new Map((incremental ? previous.messages : []).map(message => [message.id, message]));
  let cursor = incremental ? previous.syncCursor ?? undefined : undefined;
  let revision: number | null | undefined = incremental ? previous.historyRevision : undefined;
  let checkpoint: string | null = cursor ?? null;
  const seen = new Set(cursor ? [cursor] : []);
  do {
    const page = await listMessages(id, cursor, signal);
    const hasCheckpoint = Number.isSafeInteger(page.history_revision) && (page.history_revision ?? 0) > 0
      && (typeof page.sync_cursor === "string" || page.sync_cursor === null);
    const pageRevision = hasCheckpoint ? page.history_revision! : null;
    if (incremental && !hasCheckpoint || revision !== undefined && revision !== pageRevision) {
      throw new HistoryChanged("Message history changed while reading.");
    }
    revision = pageRevision;
    for (const message of page.items) {
      if (conversationKey(message.conversation_id) !== conversationKey(id)) throw new Error("Message belongs to another conversation.");
      const saved = incremental ? messages.get(message.id) : undefined;
      if (saved && (saved.revision !== message.revision || saved.content !== message.content || saved.position !== message.position)) {
        throw new HistoryChanged("Saved message changed; reload the history.");
      }
      const known = messages.get(message.id);
      if (!known || known.revision <= message.revision) messages.set(message.id, message);
    }
    if (hasCheckpoint) {
      checkpoint = page.sync_cursor!;
      if (page.items.length && !checkpoint) throw new HistoryChanged("Missing message checkpoint.");
    }
    cursor = page.next_cursor ?? undefined;
    if (cursor && seen.has(cursor)) throw new Error("Message cursor did not advance.");
    if (cursor) seen.add(cursor);
  } while (cursor);
  return { conversationId: id, messages: [...messages.values()].sort((a, b) => a.position - b.position), historyRevision: revision ?? null, syncCursor: revision ? checkpoint : null };
}

/** Restart once on an observed destructive change; publish no partial results. */
export async function readConversationHistory(
  id: string, previous?: ConversationHistory, signal?: AbortSignal,
): Promise<ConversationHistory> {
  try { return await readHistory(id, previous, signal); }
  catch (cause) {
    if (!(cause instanceof HistoryChanged)) throw cause;
    return readHistory(id, undefined, signal);
  }
}

/** One room/account's in-memory cache. Disposed or superseded reads cannot publish. */
export class ConversationHistorySession {
  private history: ConversationHistory | undefined;
  private version = 0;
  private disposed = false;
  private reads = new Set<AbortController>();

  constructor(readonly conversationId: string, readonly ownerId: string) {}

  private abortReads(): void { for (const controller of this.reads) controller.abort(); }

  dispose(): void { this.disposed = true; this.version++; this.abortReads(); }

  async sync(reset = false, signal?: AbortSignal): Promise<ConversationHistory | null> {
    if (this.disposed) return null;
    this.abortReads();
    const version = ++this.version;
    const controller = new AbortController();
    const abort = () => controller.abort(signal?.reason);
    if (signal?.aborted) abort(); else signal?.addEventListener("abort", abort, { once: true });
    this.reads.add(controller);
    try {
      const history = await readConversationHistory(this.conversationId, reset ? undefined : this.history, controller.signal);
      if (this.disposed || version !== this.version) return null;
      this.history = history;
      return history;
    } catch (cause) {
      if (this.disposed || version !== this.version) return null;
      throw cause;
    } finally {
      this.reads.delete(controller);
      signal?.removeEventListener("abort", abort);
    }
  }

  append(message: ChatMessage): ConversationHistory | null {
    if (this.disposed || !this.history || conversationKey(message.conversation_id) !== conversationKey(this.conversationId)) return null;
    const saved = this.history.messages.find(item => item.id === message.id);
    this.version++; // An older in-flight read cannot remove this confirmed save.
    this.abortReads();
    this.history = {
      ...this.history,
      messages: mergeMessages(this.history.messages, [message]),
      historyRevision: saved && saved.revision !== message.revision ? null : this.history.historyRevision,
    };
    // Keep the old cursor: messages from another tab may precede the returned save.
    return this.history;
  }
}
