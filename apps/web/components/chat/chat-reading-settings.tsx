"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useUserTheme } from "@/components/user-theme";
import { ChatAlbum } from "./chat-images";
import type { CreditBalance, ProductAlbum } from "@/lib/api";
import styles from "./chat.module.css";

export const defaultReading = { size: 16, spacing: 29, showImages: true };
export type ReadingOptions = typeof defaultReading;
const storageKey = "moseori_chat_reading_v1";
const fontSizes = [14, 16, 18, 20];
const lineSpacings = [26, 29, 32];

export function useReadingOptions() {
  const [options, setOptions] = useState(defaultReading);
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null");
      if (saved && fontSizes.includes(saved.size) && lineSpacings.includes(saved.spacing)) setOptions({ size: saved.size, spacing: saved.spacing, showImages: saved.showImages !== false });
    } catch { /* Use the default when preferences are unavailable. */ }
  }, []);
  return [options, (next: ReadingOptions) => {
    setOptions(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Session preferences still work. */ }
  }] as const;
}

function Choices<T extends string | number>({ label, values, value, onChange, format = String }: {
  label: string;
  values: readonly T[];
  value: T;
  onChange: (value: T) => void;
  format?: (value: T) => string;
}) {
  return <div className={styles.choiceGroup} role="group" aria-label={label}>
    {values.map(option => <button key={option} type="button" className={styles.button} aria-pressed={option === value} onClick={() => onChange(option)}>{format(option)}</button>)}
  </div>;
}

const headings = { main: "대화 설정", album: "작품 앨범", note: "유저 노트", output: "답변 길이", memory: "요약 메모리", reading: "글자 크기 · 행간", theme: "테마" };

export function ChatReadingSettings({ title, character, description, preview, onClose, options, onOptions, balance, balanceUnavailable, answerPrice, album, onAlbumRefresh }: {
  album: ProductAlbum | null;
  onAlbumRefresh: () => void;
  title: string;
  character: string;
  description?: string;
  preview: boolean;
  onClose: () => void;
  options: ReadingOptions;
  onOptions: (value: ReadingOptions) => void;
  balance: CreditBalance | null;
  balanceUnavailable: boolean;
  answerPrice: number | null;
}) {
  const headingId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const [view, setView] = useState<keyof typeof headings>("main");
  const [note, setNote] = useState("에린은 손님에게 존댓말을 쓴다.\n기록실 문은 비가 내릴 때만 열린다.");
  const [length, setLength] = useState("기본");
  const [thinking, setThinking] = useState("기본");
  const { preference, setTheme, theme } = useUserTheme();

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const sheet = matchMedia("(max-width: 700px)");
    const sync = () => {
      if (node.open) node.close();
      if (sheet.matches) node.showModal();
      else node.show();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented && !event.isComposing && !sheet.matches) close.current();
    };
    sync();
    sheet.addEventListener("change", sync);
    node.addEventListener("keydown", escape);
    return () => {
      sheet.removeEventListener("change", sync);
      node.removeEventListener("keydown", escape);
      node.close();
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  function open(next: keyof typeof headings) {
    setView(next);
    heading.current?.focus({ preventScroll: true });
    dialog.current?.scrollTo(0, 0);
  }

  const row = (key: keyof typeof headings, detail?: string, value?: string) => <button type="button" className={styles.settingRow} onClick={() => open(key)}>
    <span><strong>{headings[key]}</strong>{detail && <small>{detail}</small>}</span>
    {value ? <small>{value}</small> : <ChevronRight size={15} aria-hidden="true" />}
  </button>;

  return <dialog className={styles.settings} ref={dialog} aria-labelledby={headingId} onCancel={event => {
    event.preventDefault();
    onClose();
  }} onClick={event => {
    if (event.target !== event.currentTarget) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientY < bounds.top) onClose();
  }}>
    <div className={styles.sheetHandle} aria-hidden="true" />
    <header className={styles.settingsHeader}>
      {view !== "main" && <button className={styles.iconButton} type="button" aria-label="설정 목록으로" onClick={() => open("main")}><ChevronLeft size={18} /></button>}
      <h2 id={headingId} ref={heading} tabIndex={-1}>{headings[view]}</h2>
      <button className={styles.iconButton} type="button" aria-label="설정 닫기" onClick={onClose}><X size={17} /></button>
    </header>
    {view === "main" && <>
      <div className={styles.roomInfo}><strong>{title}</strong><small>{character}{description ? ` · ${description}` : ""}</small></div>
      {preview && <div>
        {row("note", "에린이 기억할 내용을 정해요.")}
        {row("output", "한 번의 답변 길이와 생각 깊이를 정해요.")}
        {row("memory", "지금까지 쌓인 이야기를 확인해요.")}
      </div>}
      {album?.available && album.items.length > 0 &&
        row("album", undefined, `${album.items.filter(item => item.status === "unlocked").length}/${album.items.length}`)}
      <section aria-label="읽기 설정">
        <p className={styles.caption}>읽기</p>
        {row("reading", undefined, `${options.size}px · ${options.spacing === 29 ? "보통" : options.spacing < 29 ? "좁게" : "넓게"}`)}
        <label className={styles.settingRow}>본문 이미지 표시
          <input type="checkbox" checked={options.showImages} onChange={event => onOptions({ ...options, showImages: event.target.checked })} />
        </label>
        {row("theme", undefined, theme === "dark" ? "다크" : "라이트")}
      </section>
      {!preview && <section className={styles.wallet}>
        <p className={styles.caption}>답변과 크레딧</p>
        <p>{balance ? `사용 가능 ${balance.available_credit.toLocaleString("ko-KR")} 크레딧` : balanceUnavailable ? "크레딧 잔액 확인 불가" : "크레딧 잔액 확인 중"}</p>
        <small>{answerPrice === null ? "답변 가격은 요청 시 서버에서 계산합니다." : `최근 답변 예약 가격 ${answerPrice.toLocaleString("ko-KR")} 크레딧`}</small>
        <Link href="/account/wallet" className={styles.button}>내 크레딧 지갑</Link>
      </section>}
    </>}
    {view === "album" && <ChatAlbum album={album} onRefresh={onAlbumRefresh} />}
    {view === "reading" && <>
      <p>글자 크기</p>
      <Choices label="글자 크기" values={fontSizes} value={options.size} format={value => `${value}px`} onChange={size => onOptions({ ...options, size })} />
      <p>행간</p>
      <Choices label="행간" values={lineSpacings} value={options.spacing} format={value => value < 29 ? "좁게" : value > 29 ? "넓게" : "보통"} onChange={spacing => onOptions({ ...options, spacing })} />
    </>}
    {view === "theme" && <Choices label="테마" values={["light", "dark", "system"] as const} value={preference} format={value => value === "light" ? "라이트" : value === "dark" ? "다크" : "기기 설정"} onChange={setTheme} />}
    {preview && view === "note" && <>
      <p className={styles.caption}>시연용 노트 · 실제 대화에는 적용되지 않아요.</p>
      <textarea className={styles.noteField} aria-label="유저 노트" rows={4} value={note} onChange={event => setNote(event.target.value)} />
    </>}
    {preview && view === "output" && <>
      <p className={styles.caption}>시연용 설정 · 실제 생성과 과금은 없어요.</p>
      <p>최대 답변 길이</p><Choices label="최대 답변 길이" values={["짧게", "기본", "길게"]} value={length} onChange={setLength} />
      <p>생각 깊이</p><Choices label="생각 깊이" values={["기본", "깊게"]} value={thinking} onChange={setThinking} />
    </>}
    {preview && view === "memory" && <>
      <p className={styles.caption}>기록실 대화에서 사용하는 시연용 메모리예요.</p>
      <div className={styles.roomInfo}><strong>최근 요약</strong><p>에린이 은색 열쇠를 건넸다. 맞은편 문을 열기 전에 편지를 읽을지 정하려 한다.</p></div>
      <div className={styles.roomInfo}><strong>장기 기억</strong><p>에린은 기록실의 안내인이다. 손님은 잊어버린 이야기를 찾으러 왔다.</p></div>
    </>}
  </dialog>;
}
