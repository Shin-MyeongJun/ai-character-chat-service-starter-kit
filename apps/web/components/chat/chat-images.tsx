"use client";

import { Lock } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { findConversationProduct, getProductAlbum, type ChatImage, type ProductAlbum } from "@/lib/api";
import styles from "./chat.module.css";

export function useConversationAlbum(id: string, ownerId: string | null, settingsOpen: boolean) {
  const [result, setResult] = useState<{ id: string; ownerId: string; album: ProductAlbum } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const product = useRef<{ id: string; ownerId: string; productId: string } | null>(null);
  const refreshAlbum = useCallback(() => setRefresh(value => value + 1), []);

  useEffect(() => {
    if (!ownerId || !settingsOpen) return;
    const controller = new AbortController();
    const { signal } = controller;
    async function load(owner: string) {
      const cached = product.current;
      const productId = cached?.id === id && cached.ownerId === owner
        ? cached.productId : await findConversationProduct(id, signal);
      if (!productId || signal.aborted) return;
      product.current = { id, ownerId: owner, productId };
      const album = await getProductAlbum(productId, signal);
      if (!signal.aborted) setResult({ id, ownerId: owner, album });
    }
    void load(ownerId).catch(() => {});
    return () => controller.abort();
  }, [id, ownerId, settingsOpen, refresh]);

  const album = result?.id === id && result.ownerId === ownerId ? result.album : null;
  return { album, refreshAlbum };
}

export function ChatImageFrame({ image, onError }: { image: ChatImage; onError?: () => void }) {
  const [failed, setFailed] = useState(false);
  return <figure className={styles.imageFrame}>
    {failed ? <span className={styles.imageFallback}>{image.alt || "이미지를 불러오지 못했어요."}</span> :
      // The authenticated rewrite serves the exact stored occurrence without image optimization.
      // eslint-disable-next-line @next/next/no-img-element
      <img src={`/backend${image.content_url}`} alt={image.alt} loading="lazy" onError={() => {
        setFailed(true);
        onError?.();
      }} />}
  </figure>;
}

export function ChatAlbum({ album, onRefresh }: { album: ProductAlbum | null; onRefresh: () => void }) {
  const [unlockedOnly, setUnlockedOnly] = useState(false);
  const failedUrls = useRef(new Set<string>());
  const items = album?.items ?? [];
  const unlocked = items.filter(item => item.status === "unlocked");
  const visible = unlockedOnly ? unlocked : items;

  return <section className={styles.album} aria-label="작품 앨범 목록">
    <p>해금 {unlocked.length}/{items.length}</p>
    <div className={styles.choiceGroup} role="group" aria-label="앨범 필터">
      <button type="button" className={styles.button} aria-pressed={!unlockedOnly} onClick={() => setUnlockedOnly(false)}>전체</button>
      <button type="button" className={styles.button} aria-pressed={unlockedOnly} onClick={() => setUnlockedOnly(true)}>해금한 이미지</button>
    </div>
    {visible.length === 0 && <p>{items.length ? "해금한 이미지가 없어요." : "수집할 이미지가 없어요."}</p>}
    <ul className={styles.albumGrid}>
      {visible.map(item => <li key={item.image_item_id}>
        {item.status === "locked" ? <div className={styles.imageFrame}><span className={styles.imageFallback}><Lock size={16} aria-hidden="true" />잠김</span></div>
          : <ChatImageFrame key={item.content_url} image={item} onError={() => {
            if (failedUrls.current.has(item.content_url)) return;
            failedUrls.current.add(item.content_url);
            onRefresh();
          }} />}
      </li>)}
    </ul>
  </section>;
}
