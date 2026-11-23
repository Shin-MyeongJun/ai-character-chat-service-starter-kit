import { ApiError, getMe, request } from "./api";
import { readStudioProject, type StudioProject } from "./studio-project";
import type { WorkspaceWork } from "./studio-workspace";
import { readImage } from "./studio-assets";
import { resolveStudioImageUploads, studioDocument } from "./studio-product-images";

export type SavedStudioWork = { productId: string; revision: number; project: StudioProject };
type OnDraftSaved = (work: WorkspaceWork, saved: SavedStudioWork) => void;
type StudioDraft = { product_id: string; revision: number; document: StudioProject & { clientWorkId?: string }; updated_at: string };
type Product = { id: string };
export type AvailableModel = { id: string; name: string; reasoning_efforts: string[] };
export type StudioRelease = { snapshot_id: string; version: number; summary: string };
type Link = { productId: string; revision: number | null; base: string | null };
const linkPrefix = "chat-kit-studio-server-v1:";
const key = (ownerId: string, workId: string) => `${linkPrefix}${ownerId}:${workId}`;
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).filter(([, field]) => field !== undefined).sort(([a], [b]) => a.localeCompare(b)).map(([key, field]) => `${JSON.stringify(key)}:${canonical(field)}`).join(",")}}`;
  return JSON.stringify(value) ?? "null";
}
const serialized = (project: StudioProject) => canonical({
  ...studioDocument(project),
  characters: project.characters.map(({ sourceId: _sourceId, ...character }) => ({...character, assets: character.assets.map(({mediaId: _mediaId, ...asset}) => asset)})),
  lorebooks: project.lorebooks.map(({ sourceId: _sourceId, ...lore }) => lore),
});
export const sameStudioProject = (a: StudioProject, b: StudioProject) => !a.chatImageUploads?.length && !b.chatImageUploads?.length && serialized(a) === serialized(b);

export function serverError(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 401) return "로그인한 뒤 다시 시도해 주세요.";
  if (cause instanceof ApiError && cause.status === 409) {
    return cause.message.includes("Published studio") || cause.message.includes("updates")
      ? "이미 발행한 작품의 후속 버전은 현재 스튜디오에서 저장·발행할 수 없어요."
      : "서버 초안이 바뀌었어요. 서버 초안을 확인한 뒤 다시 시도해 주세요.";
  }
  return cause instanceof Error ? cause.message : "서버 요청에 실패했어요. 다시 시도해 주세요.";
}

function readLink(ownerId: string, workId: string): Link | null {
  const raw = localStorage.getItem(key(ownerId, workId));
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Link;
    return typeof value.productId === "string" && typeof value.revision !== "undefined" ? value : null;
  } catch { return null; }
}

export async function getStudioProductId(workId: string): Promise<string | null> {
  const owner = await getMe();
  return readLink(owner.id, workId)?.productId ?? null;
}

export async function getRetiredStudioImageIds(work: WorkspaceWork): Promise<Set<string>> {
  const workId = work.id;
  // Local-only works support offline undo. A link is written before the first draft PUT,
  // so a missing acknowledgement (including revision: null) still needs a server check.
  const serverId = workId.startsWith("server:") ? workId.slice("server:".length) : undefined;
  let linked = false;
  for (let index = 0; index < localStorage.length; index++) {
    const name = localStorage.key(index);
    if (name?.startsWith(linkPrefix) && name.slice(name.indexOf(":", linkPrefix.length) + 1) === workId) {
      linked = true;
      break;
    }
  }
  if (!serverId && !linked) return new Set();
  const owner = await getMe();
  const link = readLink(owner.id, workId);
  const productId = link?.productId ?? serverId;
  if (!productId) throw new Error("이 작품을 저장한 계정으로 로그인해 이미지 복구 여부를 확인해 주세요.");
  const path = `/products/${encodeURIComponent(productId)}/studio-draft`;
  try {
    const result = await request<{ revision: number; retired_image_item_ids: string[] }>(`${path}/image-retirements`);
    if (link && result.revision !== link.revision) {
      // A lost PUT response can leave the link behind the already-saved deletion.
      // Advance the base only for the exact pre-restore document, as on draft import.
      const draft = await request<StudioDraft>(path);
      if (draft.revision !== result.revision) throw new Error("확인 중에 서버 초안이 바뀌었어요. 다시 복구해 주세요.");
      const project = readStudioProject(JSON.stringify(draft.document));
      if (project && sameStudioProject(work.project, project)) {
        localStorage.setItem(key(owner.id, workId), JSON.stringify({ productId, revision: draft.revision, base: serialized(project) }));
      }
    }
    return new Set(result.retired_image_item_ids.map(id => id.toLowerCase()));
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 404 && link?.revision === null) {
      // A reserved product ID may never have reached the server.
      try { await request<StudioDraft>(path); }
      catch (error) { if (error instanceof ApiError && error.status === 404) return new Set(); throw error; }
    }
    throw cause;
  }
}

async function saveDocument(work: WorkspaceWork): Promise<SavedStudioWork> {
  const owner = await getMe();
  const linkKey = key(owner.id, work.id);
  let link = readLink(owner.id, work.id);
  if (!link) {
    link = { productId: crypto.randomUUID(), revision: null, base: null };
    localStorage.setItem(linkKey, JSON.stringify(link));
  }
  const productId = link.productId;
  const path = "/products/" + productId + "/studio-draft";

  async function put(project: StudioProject, revision: number | null): Promise<StudioDraft> {
    return request<StudioDraft>(path, {
      method: "PUT",
      body: JSON.stringify({ expected_revision: revision, document: { ...project, clientWorkId: work.id } }),
    });
  }

  function acknowledge(draft: StudioDraft, project: StudioProject): SavedStudioWork {
    const saved = readStudioProject(JSON.stringify(draft.document));
    if (!saved) throw new Error("서버 초안의 형식을 읽을 수 없어요.");
    localStorage.setItem(linkKey, JSON.stringify({ productId, revision: draft.revision, base: serialized(saved) }));
    return { productId, revision: draft.revision, project };
  }

  let remote: StudioDraft | null;
  try { remote = await request<StudioDraft>(path); }
  catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 404 && link.revision === null)) throw cause;
    remote = null;
  }

  if (work.project.chatImageUploads?.length && link.revision === null) {
    // A new product needs a server ID before a2 can accept bytes. The same
    // bootstrap document also lets us recover a lost creation response.
    const { chatImageItems: _items, ...bootstrap } = studioDocument(work.project);
    bootstrap.scenes = bootstrap.scenes.map(({ openingImagePlacements: _placements, ...scene }) => scene);
    if (!remote) remote = await put(bootstrap, null);
    const createdProject = readStudioProject(JSON.stringify(remote.document));
    if (createdProject && serialized(createdProject) === serialized(bootstrap)) {
      acknowledge(remote, bootstrap);
      link = { productId, revision: remote.revision, base: serialized(bootstrap) };
    }
  }

  const project = await resolveStudioImageUploads(owner.id, productId, work.project);
  if (remote) {
    const remoteProject = readStudioProject(JSON.stringify(remote.document));
    if (!remoteProject) throw new Error("서버 초안의 형식을 읽을 수 없어요.");
    const current = serialized(remoteProject);
    if (current === serialized(project)) return acknowledge(remote, project);
    if (link.base !== current) throw new Error("서버 초안이 다른 기기에서 변경됐어요. 서버 초안을 확인한 뒤 다시 저장해 주세요.");
  }
  return acknowledge(await put(project, remote?.revision ?? null), project);
}

type MediaLink = { requestId: string; mediaId?: string };

/** Save → prepare server copies → upload → CAS-save references, with resumable partial success.
 * Upload receipts are owner/product/character/asset/usage scoped and stored before I/O.
 * Failed final saves leave confirmed uploads reusable; existing snapshots never change.
 */
export async function saveServerWork(work: WorkspaceWork, onSaved?: OnDraftSaved): Promise<SavedStudioWork> {
  const saved = await saveDocument(work);
  onSaved?.(work, saved);
  if (!work.project.characters.some(row => row.assets.length)) return saved;
  const owner = await getMe();
  const remote = await request<StudioDraft>(`/products/${saved.productId}/studio-draft`);
  const prepared = await request<{characters: Record<string, string>}>(`/products/${saved.productId}/studio-components`, {method: "POST", body: JSON.stringify({expected_revision: saved.revision})});
  const project: StudioProject = structuredClone(saved.project);
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
    const linked = { productId: saved.productId, revision: result.revision, project };
    onSaved?.(work, linked);
    return linked;
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
  onSaved: OnDraftSaved,
): Promise<{ productId: string; release: StudioRelease }> {
  const saved = await saveServerWork(work, onSaved);
  try {
    const release = await request<StudioRelease>(`/products/${saved.productId}/studio-publication`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: saved.revision, model_id: modelId, reasoning_effort: reasoningEffort, summary, body }),
    });
    return { productId: saved.productId, release };
  } catch (cause) {
    if (cause instanceof ApiError && ![408, 502, 503, 504].includes(cause.status)) {
      throw new Error(`초안을 서버에 저장했지만 발행에 실패했어요. ${serverError(cause)}`, { cause });
    }
    throw new Error("초안을 서버에 저장했어요. 발행 결과를 확인할 수 없어요. 같은 내용과 설정으로 다시 발행하면 결과를 확인할 수 있어요.", { cause });
  }
}
