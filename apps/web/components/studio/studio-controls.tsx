"use client";

import { useId, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { X } from "lucide-react";
import styles from "./studio.module.css";

export function StudioButton({ primary, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return <button type="button" className={`${styles.button} ${primary ? styles.primary : ""} ${className}`} {...props}>{children}</button>;
}

export function StudioField({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return <label className={styles.field}><span>{label}</span>{children}{help && <small className={styles.help}>{help}</small>}</label>;
}

export function ChipEditor({ label, values, onChange, help, reorderable = false }: { label: string; values: string[]; onChange: (values: string[]) => void; help?: string; reorderable?: boolean }) {
  const id = useId();
  const [input, setInput] = useState("");
  const [dragged, setDragged] = useState<string | null>(null);
  const [preview, setPreview] = useState<string[] | null>(null);
  const previewRef = useRef<string[] | null>(null);
  const lastMove = useRef<{ x: number; y: number; time: number } | null>(null);
  const displayed = preview ?? values;
  const chips = useRef(new Map<string, HTMLSpanElement>());
  const previousBounds = useRef(new Map<string, DOMRect>());
  useLayoutEffect(() => {
    const previous = previousBounds.current;
    previousBounds.current = new Map();
    if (!previous.size || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const animations: Animation[] = [];
    chips.current.forEach((node, value) => {
      const before = previous.get(value);
      if (!before) return;
      const after = node.getBoundingClientRect();
      const x = before.left - after.left, y = before.top - after.top;
      if (x || y) animations.push(node.animate([
        { transform: `translate(${x}px, ${y}px)` },
        { transform: "translate(0, 0)" },
      ], { duration: 220, easing: "cubic-bezier(.2,.8,.2,1)" }));
    });
    return () => animations.forEach(animation => animation.cancel());
  }, [displayed]);
  function finishDrag(save: boolean) {
    if (previewRef.current) {
      previousBounds.current = new Map([...chips.current].map(([key, node]) => [key, node.getBoundingClientRect()]));
      if (save && previewRef.current.some((value, index) => value !== values[index])) onChange(previewRef.current);
    }
    previewRef.current = null;
    lastMove.current = null;
    setPreview(null);
    setDragged(null);
  }
  function move(value: string, destination: string, after: boolean) {
    const current = previewRef.current ?? values;
    if (value === destination || !current.includes(value) || !current.includes(destination)) return;
    const next = current.filter(item => item !== value);
    next.splice(next.indexOf(destination) + (after ? 1 : 0), 0, value);
    if (next.some((item, index) => item !== current[index])) {
      previousBounds.current = new Map([...chips.current].map(([key, node]) => [key, node.getBoundingClientRect()]));
      if (previewRef.current) { previewRef.current = next; setPreview(next); }
      else onChange(next);
    }
  }
  function add() {
    const next = input.split(/[,，\n]/).map(value => value.trim()).filter(Boolean);
    if (next.length) onChange([...new Set([...values, ...next])]);
    setInput("");
  }
  return <div className={styles.field}>
    <label htmlFor={id}>{label}</label>
    <div className={styles.chips} onDragOver={event => {
      if (!dragged) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    }} onDrop={event => {
      if (!dragged) return;
      event.preventDefault();
      finishDrag(true);
    }}>
      {displayed.map((value, index) => <span
        className={`${styles.chip} ${reorderable ? styles.draggableChip : ""} ${dragged === value ? styles.draggingChip : ""}`}
        key={value}
        ref={node => { if (node) chips.current.set(value, node); else chips.current.delete(value); }}
        draggable={reorderable}
        tabIndex={reorderable ? 0 : undefined}
        aria-label={reorderable ? `${value} · Alt + 방향키로 순서 변경` : undefined}
        title={reorderable ? "드래그하거나 Alt + 방향키로 순서를 바꿔요." : undefined}
        onKeyDown={event => {
          if (event.target !== event.currentTarget || !reorderable || !event.altKey || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
          event.preventDefault();
          const destination = values[index + (event.key === "ArrowLeft" ? -1 : 1)];
          if (destination !== undefined) move(value, destination, event.key === "ArrowRight");
        }}
        onDragStart={event => {
          if (!reorderable || (event.target as HTMLElement).closest("button")) { event.preventDefault(); return; }
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", value);
          previewRef.current = [...values];
          setPreview(previewRef.current);
          lastMove.current = null;
          setDragged(value);
        }}
        onDragOver={event => {
          if (!dragged || dragged === value) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          const previous = lastMove.current;
          // Ignore the chip sliding underneath a stationary pointer after a swap.
          if (previous && (performance.now() - previous.time < 180 || Math.hypot(event.clientX - previous.x, event.clientY - previous.y) < 8)) return;
          const current = previewRef.current;
          if (!current) return;
          const after = current.indexOf(dragged) < current.indexOf(value);
          const bounds = event.currentTarget.getBoundingClientRect();
          const midpoint = bounds.left + bounds.width / 2;
          if (after ? event.clientX < midpoint + 6 : event.clientX > midpoint - 6) return;
          lastMove.current = { x: event.clientX, y: event.clientY, time: performance.now() };
          move(dragged, value, after);
        }}
        onDragEnd={() => finishDrag(false)}
      >{value}<button type="button" draggable={false} aria-label={`${label} ${value} 삭제`} onClick={() => onChange(values.filter(item => item !== value))}><X size={13} /></button></span>)}
      <div className={styles.chipInput}>
        <input id={id} value={input} placeholder="+ 추가" aria-label={`${label} 추가`} onChange={event => setInput(event.target.value)} onBlur={add} onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); add(); } }} />
        {input.trim() && <button type="button" onClick={add}>추가</button>}
      </div>
    </div>
    {help && <small className={styles.help}>{help}</small>}
    {reorderable && values.length > 1 && <small className={styles.help}>태그를 드래그해 순서를 바꿀 수 있어요.</small>}
  </div>;
}

export function ChoiceChips<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return <div className={styles.chips} role="group" aria-label={label}>{options.map(option => <button key={option.value} type="button" className={`${styles.choice} ${value === option.value ? styles.selected : ""}`} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}
