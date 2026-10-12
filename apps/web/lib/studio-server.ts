import { ApiError, getMe, request } from "./api";
import { readStudioProject, type StudioProject } from "./studio-project";
import type { WorkspaceWork } from "./studio-workspace";

type StudioDraft = { product_id: string; revision: number; document: StudioProject & { clientWorkId?: string }; updated_at: string };
type Product = { id: string };
export type AvailableModel = { id: string; name: string; reasoning_efforts: string[] };
export type StudioRelease = { snapshot_id: string; version: number; summary: string };
type Link = { productId: string; revision: number | null; base: string | null };
const key = (ownerId: string, workId: string) => `chat-kit-studio-server-v1:${ownerId}:${workId}`;
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).filter(([, field]) => field !== undefined).sort(([a], [b]) => a.localeCompare(b)).map(([key, field]) => `${JSON.stringify(key)}:${canonical(field)}`).join(",")}}`;
  return JSON.stringify(value) ?? "null";
}
const serialized = (project: StudioProject) => canonical({
  ...project,
  characters: project.characters.map(({ sourceId: _sourceId, ...character }) => character),
  lorebooks: project.lorebooks.map(({ sourceId: _sourceId, ...lore }) => lore),
});
export const sameStudioProject = (a: StudioProject, b: StudioProject) => serialized(a) === serialized(b);

function readLink(ownerId: string, workId: string): Link | null {
  const raw = localStorage.getItem(key(ownerId, workId));
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Link;
    return typeof value.productId === "string" && typeof value.revision !== "undefined" ? value : null;
  } catch { return null; }
}

export async function saveServerWork(work: WorkspaceWork): Promise<{ productId: string; revision: number }> {
  const owner = await getMe();
  let link = readLink(owner.id, work.id);
  if (!link) {
    link = { productId: crypto.randomUUID(), revision: null, base: null };
    // Save the server ID before the network request. A lost response can be retried safely.
    localStorage.setItem(key(owner.id, work.id), JSON.stringify(link));
  }
  try {
    const remote = await request<StudioDraft>(`/products/${link.productId}/studio-draft`);
    const remoteProject = readStudioProject(JSON.stringify(remote.document));
    if (!remoteProject) throw new Error("서버 초안의 형식을 읽을 수 없어요.");
    const current = serialized(remoteProject);
    if (current === serialized(work.project)) {
      localStorage.setItem(key(owner.id, work.id), JSON.stringify({ productId: link.productId, revision: remote.revision, base: current }));
      return { productId: link.productId, revision: remote.revision };
    }
    if (link.base !== current) throw new Error("서버 초안이 다른 기기에서 변경됐어요. 서버 초안을 확인한 뒤 다시 저장해 주세요.");
    link = { ...link, revision: remote.revision };
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 404 && link.revision === null)) throw cause;
  }
  const result = await request<StudioDraft>(`/products/${link.productId}/studio-draft`, {
    method: "PUT",
    body: JSON.stringify({ expected_revision: link.revision, document: { ...work.project, clientWorkId: work.id } }),
  });
  localStorage.setItem(key(owner.id, work.id), JSON.stringify({ productId: link.productId, revision: result.revision, base: serialized(work.project) }));
  return { productId: link.productId, revision: result.revision };
}

export async function loadServerWorks(localWorks: WorkspaceWork[]): Promise<WorkspaceWork[]> {
  const owner = await getMe();
  const works: WorkspaceWork[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await request<Product[]>(`/products/mine?offset=${offset}&limit=100`);
    for (const item of page) {
      let draft: StudioDraft;
      try { draft = await request<StudioDraft>(`/products/${item.id}/studio-draft`); }
      catch (cause) { if (cause instanceof ApiError && cause.status === 404) continue; throw cause; }
      const project = readStudioProject(JSON.stringify(draft.document));
      if (!project) continue;
      // Independent source rows are browser-only; server copies are self-contained.
      const detached: StudioProject = { ...project,
        characters: project.characters.map(({ sourceId: _sourceId, ...character }) => character),
        lorebooks: project.lorebooks.map(({ sourceId: _sourceId, ...lore }) => lore),
      };
      const originalId = draft.document.clientWorkId || item.id;
      const workId = works.some(row => row.id === originalId) ? item.id : originalId;
      const local = localWorks.find(row => row.id === workId);
      if (!local || serialized(local.project) === serialized(detached)) {
        localStorage.setItem(key(owner.id, workId), JSON.stringify({ productId: item.id, revision: draft.revision, base: serialized(detached) }));
      }
      works.push({ id: workId, project: detached });
    }
    if (page.length < 100) break;
  }
  return works;
}

export const listAvailableModels = () => request<AvailableModel[]>("/models/available");

export async function publishServerWork(
  work: WorkspaceWork, modelId: string, reasoningEffort: string, summary: string, body: string,
): Promise<{ productId: string; release: StudioRelease }> {
  const saved = await saveServerWork(work);
  const release = await request<StudioRelease>(`/products/${saved.productId}/studio-publication`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: saved.revision, model_id: modelId, reasoning_effort: reasoningEffort, summary, body }),
  });
  return { productId: saved.productId, release };
}
