import { request } from "./api";
import { readImage } from "./studio-assets";
import type { ChatImageUpload, StudioProject } from "./studio-project";

type ProductImageVersion = {
  product_id: string;
  file_version_id: string;
  state: string;
  content_url: string | null;
};

export function studioImagePreviewUrl(productId: string, fileVersionId: string) {
  return `/backend/products/${encodeURIComponent(productId)}/media/${encodeURIComponent(fileVersionId)}/content`;
}

export function studioDocument(project: StudioProject): StudioProject {
  const { chatImageUploads: _localUploads, ...document } = project;
  return document;
}

async function uploadStudioImage(productId: string, upload: ChatImageUpload) {
  const path = `/products/${encodeURIComponent(productId)}/media`;
  const headers = new Headers({ "Idempotency-Key": upload.requestId });
  if (upload.kind === "import") {
    return request<ProductImageVersion>(`${path}/imports`, {
      method: "POST", headers, body: JSON.stringify({ media_id: upload.mediaId }),
    });
  }
  const file = await readImage(upload.requestId);
  if (!file) throw new Error(`${upload.filename}: 이 브라우저에 이미지 원본이 없어요. 다시 선택해 주세요.`);
  headers.set("Content-Type", file.type);
  headers.set("X-Filename", encodeURIComponent(upload.filename));
  return request<ProductImageVersion>(`${path}/uploads`, { method: "POST", headers, body: file });
}

export async function resolveStudioImageUploads(ownerId: string, productId: string, project: StudioProject): Promise<StudioProject> {
  const document = studioDocument(project);
  if (!project.chatImageUploads?.length) return document;
  const uploads = new Map(project.chatImageUploads.map(upload => [upload.itemId, upload]));
  const items = [];
  for (const item of document.chatImageItems ?? []) {
    const upload = uploads.get(item.imageItemId);
    if (!upload) { items.push(item); continue; }
    const receiptKey = `chat-kit-studio-image-upload:${ownerId}:${productId}:${upload.requestId}`;
    let fileVersionId = localStorage.getItem(receiptKey);
    if (!fileVersionId) {
      const result = await uploadStudioImage(productId, upload);
      if (result.product_id !== productId || result.state !== "ready" || !result.file_version_id || !result.content_url) {
        throw new Error("사용 가능한 작품 이미지 버전을 받지 못했어요. 파일을 다시 선택해 주세요.");
      }
      fileVersionId = result.file_version_id;
      localStorage.setItem(receiptKey, fileVersionId);
    }
    items.push({ ...item, fileVersionId });
  }
  return { ...document, chatImageItems: items };
}
