"use client";

import { useEffect, useRef, useState } from "react";
import type { StudioScope } from "@/lib/studio-scope";
import { readLocalWorkspace } from "@/lib/studio-local-workspace";
import { emptyWorkspace, readWorkspace, type StudioWorkspace } from "@/lib/studio-workspace";

export function useStudioDraft(scope: StudioScope) {
  const key = scope.workspaceKey;
  const [workspace, setWorkspace] = useState<StudioWorkspace>(emptyWorkspace);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState("불러오는 중");
  const [dirty, setDirty] = useState(false);
  const [storageWarning, setStorageWarning] = useState("");
  const latest = useRef(workspace);
  const unsaved = useRef(false);
  const unreadable = useRef<string | null>(null);
  const lastStored = useRef<string | null>(null);
  function save() {
    if (!scope.current()) return;
    // Do not overwrite newer work from another tab with a stale snapshot.
    if (localStorage.getItem(key) !== lastStored.current) throw new Error("다른 탭에서 작업실이 변경됐어요. 현재 작업을 내보낸 뒤 새로고침해 주세요.");
    if (unreadable.current !== null) {
      localStorage.setItem(`${key}-unreadable-backup-${Date.now()}`, unreadable.current);
      unreadable.current = null;
    }
    const raw = JSON.stringify(latest.current);
    localStorage.setItem(key, raw); lastStored.current = raw;
    unsaved.current = false;
  }
  useEffect(() => {
    try {
      const { raw, workspace: restored } = readLocalWorkspace(scope);
      lastStored.current = raw;
      if (restored) { setWorkspace(restored); latest.current = restored; }
      if (!restored) {
        unreadable.current = raw;
        setStorageWarning("저장된 데이터를 읽지 못했어요. 기존 내용을 이 작업실에 백업한 뒤 새 편집을 저장합니다.");
      }
      if (restored?.works.length && raw === null) {
        unsaved.current = true; setDirty(true);
        setStorageWarning("이 계정의 이전 서버 저장본을 복원했어요.");
      }
      setStatus(restored?.works.length || raw ? "이 브라우저에 저장됨" : "빈 작업실 · 편집 시 자동 저장");
    } catch {
      setStorageWarning("브라우저 저장소를 사용할 수 없어요. 작업실 JSON 내보내기로 보관하세요.");
      setStatus("저장소 사용 불가");
    }
    setReady(true);
    const flush = () => { if (unsaved.current) { try { save(); } catch { /* Keep unload guard. */ } } };
    const guard = (event: BeforeUnloadEvent) => { if (unsaved.current) { event.preventDefault(); event.returnValue = ""; } };
    const sync = (event: StorageEvent) => {
      if (!scope.current() || event.key !== key) return;
      if (unsaved.current) { setStorageWarning("다른 탭에서 작업실이 변경됐어요. 현재 작업을 내보낸 뒤 새로고침해 주세요."); return; }
      const next = event.newValue ? readWorkspace(event.newValue) : null;
      if (!next) { setStorageWarning("다른 탭의 저장 데이터를 읽지 못했어요. 현재 작업을 내보낸 뒤 새로고침해 주세요."); return; }
      lastStored.current = event.newValue; latest.current = next; setWorkspace(next); setStatus("이 브라우저에 저장됨");
    };
    window.addEventListener("pagehide", flush); window.addEventListener("beforeunload", guard);
    window.addEventListener("storage", sync);
    return () => { flush(); window.removeEventListener("pagehide", flush); window.removeEventListener("beforeunload", guard); window.removeEventListener("storage", sync); };
  }, [scope, key]);
  useEffect(() => {
    if (!ready || !dirty) return;
    const timer = window.setTimeout(() => {
      try { save(); setDirty(false); setStatus("이 브라우저에 저장됨"); }
      catch (error) { setStatus("저장 실패 · 내보내기 필요"); setStorageWarning(error instanceof Error && error.message.includes("다른 탭") ? error.message : "저장 공간이 부족하거나 저장이 차단됐어요. 작업실을 내보내 주세요."); }
    }, 450);
    return () => window.clearTimeout(timer);
  }, [workspace, ready, dirty]);
  function commit(change: (current: StudioWorkspace) => StudioWorkspace) {
    if (!scope.current()) return;
    const next = change(latest.current);
    if (next === latest.current) return;
    latest.current = next; unsaved.current = true; setWorkspace(next); setDirty(true); setStatus("저장 중…");
  }
  return { workspace, commit, ready, status, storageWarning };
}
