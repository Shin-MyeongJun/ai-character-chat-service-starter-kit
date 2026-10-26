"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import styles from "./studio.module.css";

export function StudioDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => { dialog?.close(); if (opener?.isConnected) opener.focus({ preventScroll: true }); };
  }, []);
  return <dialog ref={ref} className={styles.dialog} aria-labelledby={id} onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className={styles.dialogHead}><h2 id={id}>{title}</h2><button type="button" className={styles.iconButton} aria-label="닫기" onClick={onClose}><X size={20} /></button></div>
    <div className={styles.dialogBody}>{children}</div>
  </dialog>;
}
