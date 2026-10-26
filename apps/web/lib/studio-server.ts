import { ApiError, getMe, request } from "./api";
import { readStudioProject, type StudioProject } from "./studio-project";
import type { WorkspaceWork } from "./studio-workspace";
import { readImage } from "./studio-assets";

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
  characters: project.characters.map(({ sourceId: _sourceId, ...character }) => ({...character, assets: character.assets.map(({mediaId: _mediaId, ...asset}) => asset)})),
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

/** CAS-save a document; callers retain browser originals if any later upload/save fails. */
async function saveDocument(work: WorkspaceWork): Promise<{ productId: string; revision: number }> {
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

type MediaLink = { requestId: string; mediaId?: string };

/** Save → prepare server copies → upload → CAS-save references, with resumable partial success.
 * Upload receipts are owner/product/character/asset/usage scoped and stored before I/O.
 * Failed final saves leave confirmed uploads reusable; existing snapshots never change.
 */
export async function saveServerWork(work: WorkspaceWork): Promise<{ productId: string; revision: number }> {
  const saved = await saveDocument(work);
  if (!work.project.characters.some(row => row.assets.length)) return saved;
  const owner = await getMe();
  const remote = await request<StudioDraft>(`/products/${saved.productId}/studio-draft`);
  const prepared = await request<{characters: Record<string, string>}>(`/products/${saved.productId}/studio-components`, {method: "POST", body: JSON.stringify({expected_revision: saved.revision})});
  const project: StudioProject = structuredClone(work.project);
  let uploaded = 0;
  try {
    for (const character of project.characters) {
      for (const asset of character.assets) {
        const existing = remote.document.characters.find(row => row.id === character.id)?.assets.find(row => row.id === asset.id && row.usage === asset.usage);
        if (existing?.mediaId) { asset.mediaId = existing.mediaId; continue; }
        const characterId = prepared.characters[character.id];
        if (!characterId) throw new Error("이미지 대상 캐릭터를 확인하지 못했어요.");
        const storageKey = `chat-kit-studio-media-v1:${owner.id}:${saved.productId}:${characterId}:${asset.id}:${asset.usage}`;
        const link: MediaLink = JSON.parse(localStorage.getItem(storageKey) ?? "null") ?? {requestId: crypto.randomUUID()};
        localStorage.setItem(storageKey, JSON.stringify(link));
        if (!link.mediaId) {
          const file = await readImage(asset.id);
          if (!file) throw new Error(`${asset.name}: 이 브라우저에 이미지 원본이 없어요. 다시 등록해 주세요.`);
          const result = await request<{media_id: string}>(`/characters/${characterId}/media/uploads`, {method: "POST", body: file, headers: {"Content-Type": file.type, "Idempotency-Key": link.requestId, "X-Filename": encodeURIComponent(asset.name), "X-Media-Purpose": `studio:${asset.id}:${asset.usage}`}});
          link.mediaId = result.media_id;
          localStorage.setItem(storageKey, JSON.stringify(link));
          uploaded++;
        }
        asset.mediaId = link.mediaId;
      }
    }
    // Use the captured revision, not an automatic merge with another device's edit.
    const result = await request<StudioDraft>(`/products/${saved.productId}/studio-draft`, {method: "PUT", body: JSON.stringify({expected_revision: saved.revision, document: {...project, clientWorkId: work.id}})});
    localStorage.setItem(key(owner.id, work.id), JSON.stringify({productId: saved.productId, revision: result.revision, base: serialized(project)}));
    return {productId: saved.productId, revision: result.revision};
  } catch (cause) {
    throw new Error(`이미지 연결을 완료하지 못했어요${uploaded ? ` (이번 업로드 ${uploaded}개 완료)` : ""}. 완료된 업로드는 재시도에 재사용돼요. ${cause instanceof Error ? cause.message : "다시 시도해 주세요."}`);
  }
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

export async function loadServerWork(productId: string): Promise<WorkspaceWork> {
  const owner = await getMe();
  const draft = await request<StudioDraft>(`/products/${encodeURIComponent(productId)}/studio-draft`);
  const project = readStudioProject(JSON.stringify(draft.document));
  if (!project) throw new Error("이 작품의 스튜디오 초안 형식을 읽을 수 없어요.");
  // A dedicated server ID avoids replacing a browser draft with a coincident clientWorkId.
  const workId = `server:${productId}`;
  const detached = { ...project, characters: project.characters.map(({ sourceId: _sourceId, ...row }) => row), lorebooks: project.lorebooks.map(({ sourceId: _sourceId, ...row }) => row) };
  if (!readLink(owner.id, workId)) localStorage.setItem(key(owner.id, workId), JSON.stringify({ productId, revision: draft.revision, base: serialized(detached) }));
  return { id: workId, project: detached };
}

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
