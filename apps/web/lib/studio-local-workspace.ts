import { legacyServerCopy } from "./studio-server";
import type { StudioScope } from "./studio-scope";
import { emptyWorkspace, readWorkspace, WORKSPACE_STORAGE_KEY } from "./studio-workspace";

export function readLocalWorkspace(scope: StudioScope) {
  scope.check();
  const raw = localStorage.getItem(scope.workspaceKey);
  if (raw !== null) return { raw, workspace: readWorkspace(raw) };
  const workspace = emptyWorkspace();
  const owner = scope.owner;
  if (owner) {
    const legacy = localStorage.getItem(WORKSPACE_STORAGE_KEY);
    for (const work of (legacy && readWorkspace(legacy)?.works) || []) {
      const owned = legacyServerCopy(owner, work);
      if (owned) workspace.works.push(owned);
    }
  }
  return { raw, workspace };
}
