import { ApiError, getMe, request } from "./api";
import { authEpoch } from "./auth-boundary";
import { WORKSPACE_STORAGE_KEY } from "./studio-workspace";

/** Capture once for the lifetime of an editor, including every asynchronous continuation. */
export class StudioScope {
  readonly namespace: string;
  readonly workspaceKey: string;

  constructor(readonly owner: string | null, readonly epoch: string) {
    this.namespace = owner === null ? "guest" : "user:" + encodeURIComponent(owner);
    this.workspaceKey = WORKSPACE_STORAGE_KEY + ":" + this.namespace;
  }

  current() {
    return this.epoch !== "storage-unavailable" && !this.epoch.startsWith("pending:") && this.epoch === authEpoch();
  }

  check() {
    if (!this.current()) throw new Error("계정이 변경됐어요. 작업실을 다시 열어 주세요.");
  }

  async confirmOwner() {
    this.check();
    if (!this.owner) throw new Error("로그인한 뒤 다시 시도해 주세요.");
    const user = await getMe();
    this.check();
    if (user.id !== this.owner) throw new Error("작업실 계정이 변경됐어요.");
    return user;
  }

  async request<T>(path: string, options?: RequestInit): Promise<T> {
    this.check();
    if (!this.owner) throw new Error("로그인한 뒤 다시 시도해 주세요.");
    const result = await request<T>(path, options, () => this.check());
    this.check();
    return result;
  }
}

export async function resolveStudioScope(epoch: string) {
  let owner = null;
  try {
    owner = (await getMe()).id;
    if (typeof owner !== "string" || !owner) throw new Error("계정을 확인하지 못했어요.");
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error;
  }
  const scope = new StudioScope(owner, epoch);
  scope.check();
  return scope;
}
