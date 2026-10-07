"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import styles from "./studio.module.css";

export function StudioDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className={styles.dialog} aria-labelledby={id} onCancel={onClose}>
    <div className={styles.dialogHead}><h2 id={id}>{title}</h2><button type="button" className={styles.iconButton} aria-label="닫기" onClick={onClose}><X size={20} /></button></div>
    <div className={styles.dialogBody}>{children}</div>
  </dialog>;
}
