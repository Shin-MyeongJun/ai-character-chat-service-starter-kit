"use client";
import { useEffect, useRef, useState } from "react";
import { listCreditHistory, type CreditHistory } from "@/lib/account";
const empty = (): CreditHistory => ({ items: [], next_cursor_created_at: null, next_cursor_id: null });
/** Reset both cursor and request epoch when server filters change; stale pages are ignored. */
export function useCreditHistory(ownerId: string | null, enabled: boolean, start?: string, direction?: "usage" | "acquisition") {
  const [data, setData] = useState<CreditHistory>(empty);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [moreBusy, setMoreBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const epoch = useRef(0);
  const running = useRef(false);
  useEffect(() => {
    const current = ++epoch.current;
    running.current = false; setMoreBusy(false); setData(empty()); setError(""); setStatus("loading");
    if (!ownerId || !enabled) return;
    void listCreditHistory(start, undefined, direction).then(value => {
      if (current === epoch.current) { setData(value); setStatus("ready"); }
    }).catch(() => { if (current === epoch.current) { setStatus("error"); setError("이용 내역을 불러오지 못했어요. 다시 시도해 주세요."); } });
    return () => { epoch.current++; };
  }, [ownerId, enabled, start, direction, version]);
  async function loadMore() {
    // Capture the filter epoch before appending an asynchronously returned page.
    if (running.current || !data.next_cursor_id || !data.next_cursor_created_at) return;
    const current = epoch.current;
    running.current = true; setMoreBusy(true); setError("");
    try {
      const page = await listCreditHistory(start, { id: data.next_cursor_id, createdAt: data.next_cursor_created_at }, direction);
      if (current !== epoch.current) return;
      if (page.next_cursor_id === data.next_cursor_id && page.next_cursor_created_at === data.next_cursor_created_at) throw new Error("Cursor did not advance.");
      setData(previous => ({ ...page, items: [...new Map([...previous.items, ...page.items].map(item => [item.id, item])).values()] }));
    } catch { if (current === epoch.current) setError("다음 내역을 불러오지 못했어요. 다시 시도해 주세요."); }
    finally { if (current === epoch.current) { running.current = false; setMoreBusy(false); } }
  }
  return { data, status, error, moreBusy, loadMore, retry: () => setVersion(value => value + 1) };
}
