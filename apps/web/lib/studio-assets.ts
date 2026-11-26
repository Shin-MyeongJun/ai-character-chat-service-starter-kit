import type { StudioScope } from "./studio-scope";

const DATABASE = "chat-kit-studio-assets";
const STORE = "images";
function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Image storage is blocked"));
  });
}
export async function saveImages(scope: StudioScope, images: { id: string; file: File }[]) {
  scope.check();
  const database = await openDatabase();
  try {
    scope.check();
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE, "readwrite");
      for (const image of images) transaction.objectStore(STORE).put(image.file, [scope.namespace, image.id]);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
    scope.check();
  } finally { database.close(); }
}
export async function readImage(scope: StudioScope, id: string): Promise<Blob | null> {
  scope.check();
  const database = await openDatabase();
  try {
    scope.check();
    const blob = await new Promise<Blob | null>((resolve, reject) => {
      const request = database.transaction(STORE, "readonly").objectStore(STORE).get([scope.namespace, id]);
      request.onsuccess = () => resolve(request.result instanceof Blob ? request.result : null);
      request.onerror = () => reject(request.error);
    });
    scope.check();
    return blob;
  } finally { database.close(); }
}
