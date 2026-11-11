"use client";

import { ArrowUp, ChevronDown, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import type { ManualLore } from "@/lib/api";
import { shouldSendOnEnter, wrapChatNarration } from "@/lib/chat-text";
import { previewModels, previewShortcuts, type PreviewModel, type PreviewShortcut } from "./chat-preview-data";
import styles from "./chat.module.css";

type ComposerProps = {
  draft: string;
  onDraft: (draft: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  disabled: boolean;
  loading: boolean;
  placeholder: string;
  manualLore: readonly ManualLore[];
  manualEntryIds: readonly string[];
  onManualLore: (id: string) => void;
  preview: boolean;
  shortcuts: readonly PreviewShortcut[];
  onShortcut: (id: PreviewShortcut) => void;
  model: PreviewModel;
  onModel: (id: PreviewModel) => void;
};

export function ChatComposer(props: ComposerProps) {
  const input = useRef<HTMLTextAreaElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const menuPanel = useRef<HTMLElement>(null);
  const menuTrigger = useRef<HTMLButtonElement | null>(null);
  const composing = useRef(false);
  const selection = useRef<{ selectionStart: number; selectionEnd: number } | null>(null);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const canSend = !props.disabled && (Boolean(props.draft.trim()) || props.preview && previewShortcuts.some(item => item.standalone && props.shortcuts.includes(item.id)));
  const hasMenu = props.preview || props.manualLore.length > 0;
  const menuLabel = props.preview ? "단축어" : "수동 로어";
  const openMenu = shortcutsOpen && hasMenu && !props.disabled;

  useLayoutEffect(() => {
    const node = input.current;
    if (!node) return;
    node.style.height = "0px";
    node.style.height = `${node.scrollHeight}px`;
    if (selection.current) {
      const { selectionStart, selectionEnd } = selection.current;
      selection.current = null;
      node.focus({ preventScroll: true });
      node.setSelectionRange(selectionStart, selectionEnd);
    }
  }, [props.draft]);

  useEffect(() => {
    if (!openMenu) return;
    menuPanel.current?.querySelector("button")?.focus({ preventScroll: true });
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !form.current?.contains(event.target)) setShortcutsOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [openMenu]);

  function closeMenu(restoreFocus: boolean) {
    setShortcutsOpen(false);
    if (restoreFocus) menuTrigger.current?.focus({ preventScroll: true });
  }

  return <form ref={form} className={styles.composer} onSubmit={event => {
    if (!canSend || composing.current) { event.preventDefault(); return; }
    closeMenu(false);
    props.onSubmit(event);
  }} onKeyDown={event => {
    if (openMenu && event.key === "Escape" && !composing.current) { event.stopPropagation(); closeMenu(true); }
  }}>
    {openMenu && <section ref={menuPanel} className={styles.toolMenu} aria-label={menuLabel}>
      <div className={styles.menuHeading}>
        <h2>{menuLabel}</h2>
        <button className={styles.iconButton} type="button" aria-label="목록 닫기" onClick={() => closeMenu(true)}><X size={16} /></button>
      </div>
      <p className={styles.caption}>선택한 항목을 다음 답변에 추가해요.</p>
      {props.manualLore.map(item => <button className={styles.menuRow} key={item.id} type="button"
        aria-pressed={props.manualEntryIds.includes(item.id)}
        disabled={props.manualEntryIds.length >= 100 && !props.manualEntryIds.includes(item.id)} onClick={() => props.onManualLore(item.id)}>
        <strong>{item.title}</strong><span>{props.manualEntryIds.includes(item.id) ? "선택됨" : "추가 ＋"}</span>
      </button>)}
      {props.preview && previewShortcuts.map(item => {
        const selected = props.shortcuts.includes(item.id);
        return <button className={styles.menuRow} key={item.id} type="button" onClick={() => {
          if (!selected) props.onShortcut(item.id);
          closeMenu(true);
        }}>
          <span><strong>{item.name}</strong><small>{item.description}</small></span>
          <span>{selected ? "선택됨" : "추가 ＋"}</span>
        </button>;
      })}
    </section>}
    {props.preview && props.shortcuts.length > 0 && <div className={styles.chips} aria-label="이번 답변에 적용할 항목">
      {props.preview && previewShortcuts.filter(item => props.shortcuts.includes(item.id)).map(item => <button type="button" className={styles.chip} disabled={props.disabled} key={item.id} aria-label={`${item.name} 제거`} onClick={() => props.onShortcut(item.id)}>{item.name}<X size={13} /></button>)}
    </div>}
    {props.manualEntryIds.length > 0 && <div className={styles.chips} aria-label="이번 답변에 적용할 수동 로어">
      {props.manualLore.filter(item => props.manualEntryIds.includes(item.id)).map(item =>
        <button type="button" className={styles.chip} disabled={props.disabled} key={item.id} aria-label={`${item.title} 제거`}
          onClick={() => props.onManualLore(item.id)}>{item.title}<X size={13} /></button>
      )}
    </div>}
    <textarea ref={input} aria-label="메시지 입력" rows={1} value={props.draft} disabled={props.disabled} placeholder={props.loading ? "대화를 불러오는 중…" : props.placeholder}
      onChange={event => props.onDraft(event.target.value)}
      onCompositionStart={() => { composing.current = true; }}
      onCompositionEnd={() => { composing.current = false; }}
      onKeyDown={event => {
        if (event.defaultPrevented || openMenu || !shouldSendOnEnter(event.nativeEvent, composing.current, matchMedia("(max-width: 700px), (pointer: coarse)").matches)) return;
        event.preventDefault();
        if (canSend) event.currentTarget.form?.requestSubmit();
      }} />
    <div className={styles.tools}>
      <button type="button" className={styles.toolButton} aria-label="묘사 넣기" title="묘사 넣기" disabled={props.disabled}
        onPointerDown={event => { if (document.activeElement === input.current) event.preventDefault(); }}
        onClick={() => {
          const node = input.current;
          if (!node || composing.current) return;
          closeMenu(false);
          const wrapped = wrapChatNarration(props.draft, node.selectionStart, node.selectionEnd);
          selection.current = wrapped;
          props.onDraft(wrapped.value);
        }}>**</button>
      {hasMenu && <button type="button" className={styles.toolButton} aria-label={menuLabel} title={menuLabel} disabled={props.disabled} aria-expanded={openMenu} onClick={event => {
        menuTrigger.current = event.currentTarget;
        setShortcutsOpen(!openMenu);
      }}>/</button>}
      <div className={styles.sendControls}>
        {props.preview && <div className={styles.modelPicker}>
          <select aria-label="시연 모델 선택" value={props.model} disabled={props.disabled} onChange={event => {
            const model = previewModels.find(item => item.id === event.currentTarget.value);
            if (model) props.onModel(model.id);
          }}>
            {previewModels.map(model => <option key={model.id} value={model.id}>{model.label}</option>)}
          </select>
          <ChevronDown size={13} aria-hidden="true" />
        </div>}
        <button type="submit" className={styles.send} aria-label="메시지 보내기" disabled={!canSend}><ArrowUp size={16} /></button>
      </div>
    </div>
  </form>;
}
