"use client";

import { useId, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { X } from "lucide-react";
import styles from "./studio.module.css";

export function StudioButton({ primary, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return <button type="button" className={`${styles.button} ${primary ? styles.primary : ""} ${className}`} {...props}>{children}</button>;
}

export function StudioField({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return <label className={styles.field}><span>{label}</span>{children}{help && <small className={styles.help}>{help}</small>}</label>;
}

export function ChipEditor({ label, values, onChange, help }: { label: string; values: string[]; onChange: (values: string[]) => void; help?: string }) {
  const id = useId();
  const [input, setInput] = useState("");
  function add() {
    const next = input.split(/[,，\n]/).map(value => value.trim()).filter(Boolean);
    if (next.length) onChange([...new Set([...values, ...next])]);
    setInput("");
  }
  return <div className={styles.field}>
    <label htmlFor={id}>{label}</label>
    <div className={styles.chips}>
      {values.map(value => <span className={styles.chip} key={value}>{value}<button type="button" aria-label={`${label} ${value} 삭제`} onClick={() => onChange(values.filter(item => item !== value))}><X size={13} /></button></span>)}
      <div className={styles.chipInput}>
        <input id={id} value={input} placeholder="+ 추가" aria-label={`${label} 추가`} onChange={event => setInput(event.target.value)} onBlur={add} onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); add(); } }} />
        {input.trim() && <button type="button" onClick={add}>추가</button>}
      </div>
    </div>
    {help && <small className={styles.help}>{help}</small>}
  </div>;
}

export function ChoiceChips<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return <div className={styles.chips} role="group" aria-label={label}>{options.map(option => <button key={option.value} type="button" className={`${styles.choice} ${value === option.value ? styles.selected : ""}`} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}
