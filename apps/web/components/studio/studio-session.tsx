"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { authEpoch, recoverInterruptedAuth, subscribeAuthChange } from "@/lib/auth-boundary";
import { resolveStudioScope, StudioScope } from "@/lib/studio-scope";

export const StudioScopeContext = createContext<StudioScope | null>(null);
export const useStudioScope = () => useContext(StudioScopeContext);
export function useAuthEpoch() {
  const epoch = useSyncExternalStore(subscribeAuthChange, authEpoch, () => "");
  useEffect(() => { recoverInterruptedAuth(epoch); }, [epoch]);
  return epoch;
}

export function StudioSession({ children }: { children: (scope: StudioScope) => ReactNode }) {
  const epoch = useAuthEpoch();
  const [scope, setScope] = useState<StudioScope>();
  const [failed, setFailed] = useState(false);
  const [attempt, retry] = useState(0);
  useEffect(() => {
    let active = true;
    setScope(undefined);
    setFailed(false);
    if (!epoch.startsWith("pending:")) {
      void resolveStudioScope(epoch).then(result => { if (active) setScope(result); })
        .catch(() => { if (active) setFailed(true); });
    }
    return () => { active = false; };
  }, [epoch, attempt]);
  if (!scope || scope.epoch !== epoch) {
    if (epoch === "storage-unavailable") return <p role="status">브라우저 저장소 접근을 허용한 뒤 작업실을 다시 열어 주세요.</p>;
    if (failed && !epoch.startsWith("pending:")) return <div role="status">
      <p>계정을 확인하지 못했어요. 익명 작업실은 이 브라우저의 다른 사용자도 열 수 있어요.</p>
      <button onClick={() => retry(n => n + 1)}>다시 확인</button>
      <button onClick={() => setScope(new StudioScope(null, epoch))}>익명 작업실 열기</button>
    </div>;
    return <p role="status">작업실 계정을 확인하고 있어요.</p>;
  }
  return <StudioScopeContext.Provider key={epoch} value={scope}>{children(scope)}</StudioScopeContext.Provider>;
}
