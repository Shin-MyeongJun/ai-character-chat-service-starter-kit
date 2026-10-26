import type { ReactNode } from "react";
import styles from "./work-tile.module.css";
export function WorkTile({ title, description, index, status, tags = [], children }: { title: string; description: string; index: number; status: string; tags?: string[]; children: ReactNode }) {
  return <article className={styles.tile}><div className={styles.cover}><small>STORY / {String(index + 1).padStart(2, "0")}</small><h2>{title || "이름 없는 작품"}</h2></div><div className={styles.body}>{tags.length > 0 && <div className={styles.tags}>{tags.map(tag => <span key={tag}>{tag}</span>)}</div>}<p>{description || "새로운 이야기를 기다리고 있어요."}</p><small>{status}</small><div className={styles.actions}>{children}</div></div></article>;
}
