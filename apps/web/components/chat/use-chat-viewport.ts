"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

/** Keep the fixed chat inside the visible viewport while a mobile keyboard is up. */
export function useChatViewport(root: RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const node = root.current;
    const viewport = window.visualViewport;
    if (!node || !viewport) return;
    const resize = () => {
      const editing = node.contains(document.activeElement) && document.activeElement?.matches("textarea, input:not([type=checkbox]), [contenteditable=true]");
      const keyboard = editing && viewport.scale === 1 && window.innerHeight - viewport.height > 100;
      node.toggleAttribute("data-keyboard", Boolean(keyboard));
      if (keyboard) {
        node.style.setProperty("--chat-visible-height", `${viewport.height}px`);
        node.style.setProperty("--chat-visible-top", `${viewport.offsetTop}px`);
        node.style.setProperty("--chat-visible-bottom", `${Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)}px`);
      } else {
        for (const key of ["height", "top", "bottom"]) node.style.removeProperty(`--chat-visible-${key}`);
      }
    };
    viewport.addEventListener("resize", resize);
    viewport.addEventListener("scroll", resize);
    window.addEventListener("resize", resize);
    node.addEventListener("focusin", resize);
    node.addEventListener("focusout", resize);
    resize();
    return () => {
      viewport.removeEventListener("resize", resize);
      viewport.removeEventListener("scroll", resize);
      window.removeEventListener("resize", resize);
      node.removeEventListener("focusin", resize);
      node.removeEventListener("focusout", resize);
    };
  }, [root]);
}

export function useChatScroll(
  room: string,
  ready: boolean,
  messages: readonly { id: string; sender_type: string }[],
  startAtTop: boolean,
) {
  const scrollRef = useRef<HTMLElement>(null);
  const columnRef = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const previous = useRef<{ room: string; latestId?: string } | null>(null);
  const [away, setAway] = useState(false);
  const [newAnswer, setNewAnswer] = useState(false);

  const onScroll = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    following.current = node.scrollHeight - node.clientHeight - node.scrollTop <= 48;
    setAway(!following.current);
    if (following.current) setNewAnswer(false);
  }, []);

  useLayoutEffect(() => {
    const node = scrollRef.current;
    if (!ready || !node) { previous.current = null; return; }
    const latest = messages.at(-1);
    if (previous.current?.room !== room) {
      node.scrollTop = startAtTop ? 0 : node.scrollHeight;
      setNewAnswer(false);
      onScroll();
    } else if (following.current) {
      node.scrollTop = node.scrollHeight;
    } else if (latest && latest.id !== previous.current.latestId && latest.sender_type === "character") {
      setNewAnswer(true);
    }
    previous.current = { room, latestId: latest?.id };
  }, [room, ready, messages, startAtTop, onScroll]);

  useEffect(() => {
    const viewport = scrollRef.current;
    const column = columnRef.current;
    if (!ready || !viewport || !column) return;
    const observer = new ResizeObserver(() => {
      if (following.current) viewport.scrollTop = viewport.scrollHeight;
      onScroll();
    });
    observer.observe(viewport);
    observer.observe(column);
    return () => observer.disconnect();
  }, [ready, onScroll]);

  function jumpToLatest() {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
    onScroll();
    node.focus({ preventScroll: true });
  }

  return { scrollRef, columnRef, onScroll, jumpToLatest, away, newAnswer };
}
