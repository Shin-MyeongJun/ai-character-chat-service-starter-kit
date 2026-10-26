"use client";
import { useEffect, useRef, useState } from "react";
import { request } from "@/lib/api";
import type { OwnedProduct } from "@/lib/account";

/** Page a server-searched owner scope; epochs prevent mixed responses after edits. */
export function useOwnedProducts(owner: string | null, enabled: boolean, search: string) {
  const [items, setItems] = useState<OwnedProduct[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const epoch = useRef(0);
  const running = useRef(false);
  const size = 24;
  useEffect(() => {
    const current = ++epoch.current;
    setItems([]); setTotal(null); setStatus("loading"); setError(""); running.current = false; setBusy(false);
    if (!owner || !enabled) return;
    const timer = setTimeout(() => {
      void Promise.all([request<OwnedProduct[]>(`/products/mine?limit=${size}&search=${encodeURIComponent(search)}`), request<{total: number}>(`/products/mine/count?search=${encodeURIComponent(search)}`)]).then(([page, count]) => {
        if (current === epoch.current) { setItems(page); setTotal(count.total); setStatus("ready"); }
      }).catch(() => { if (current === epoch.current) { setStatus("error"); setError("작품을 불러오지 못했어요."); } });
    }, 200);
    return () => { clearTimeout(timer); epoch.current++; };
  }, [owner, enabled, search, version]);
  /** Append only to the captured search scope; live offset pages are deduplicated by ID. */
  async function more() {
    if (running.current || total === null || items.length >= total) return;
    const current = epoch.current;
    running.current = true; setBusy(true); setError("");
    try {
      const page = await request<OwnedProduct[]>(`/products/mine?offset=${items.length}&limit=${size}&search=${encodeURIComponent(search)}`);
      if (current === epoch.current) { setItems(prior => [...new Map([...prior, ...page].map(row => [row.id, row])).values()]); if (!page.length) setTotal(items.length); }
    } catch { if (current === epoch.current) setError("다음 작품을 불러오지 못했어요."); }
    finally { if (current === epoch.current) { running.current = false; setBusy(false); } }
  }
  return {items, total, status, error, busy, more, retry: () => setVersion(value => value + 1)};
}
