"use client";
import Link from "next/link";
import { useId, type ReactNode } from "react";
export { StudioButton as Button, StudioField as Field } from "@/components/studio/studio-controls";
export { StudioDialog as Dialog } from "@/components/studio/studio-dialog";
import styles from "./account.module.css";
export function ActionLink({ href, children, primary = false, full = false }: { href: string; children: ReactNode; primary?: boolean; full?: boolean }) {
  return <Link className={`${styles.link} ${primary ? styles.primary : ""} ${full ? styles.full : ""}`} href={href}>{children}</Link>;
}
export function Section({ title, children, help }: { title: string; children: ReactNode; help?: string }) {
  const id = useId();
  return <section className={styles.section} aria-labelledby={id}><h2 id={id}>{title}</h2>{children}{help && <small>{help}</small>}</section>;
}
export function StatusRow({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className={`${styles.status} ${error ? styles.error : ""}`} role={error ? "alert" : "status"}>{children}</div>;
}
export function Card({ children }: { children: ReactNode }) { return <div className={styles.card}>{children}</div>; }
export function ChoiceGroup({ label, values, value, onChange }: { label: string; values: string[]; value: string; onChange: (value: string) => void }) {
  return <div className={styles.choices} role="group" aria-label={label}>{values.map(item => <button key={item} type="button" aria-pressed={value === item} onClick={() => onChange(item)}>{item}</button>)}</div>;
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) { return <Card><strong>{title}</strong>{children && <p>{children}</p>}</Card>; }
