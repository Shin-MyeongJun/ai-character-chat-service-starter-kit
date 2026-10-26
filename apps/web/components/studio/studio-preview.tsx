"use client";

import { Check, Minus, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { previewLore, type PreviewMessage, type LorePreviewResult } from "@/lib/studio-preview";
import type { LoreEntry } from "@/lib/studio-data";
import type { StudioCharacter, StudioScene } from "@/lib/studio-project";
import { ChoiceChips, StudioButton, StudioField } from "./studio-controls";
import styles from "./studio.module.css";

/** Show server selector diagnostics for unsaved content; stale checks never replace current results. */
export function StudioPreview({ entries, scene, character, running, onRun, onSelect, onClose }: { entries: LoreEntry[]; scene: StudioScene; character?: StudioCharacter; running: boolean; onRun: () => void; onSelect: (id: string) => void; onClose?: () => void }) {
  const intro: PreviewMessage = { role: "character", text: scene.opening };
  const [narrative, ...dialogue] = scene.opening.split(/\n\s*\n/);
  const [tab, setTab] = useState<"chat" | "lore">("chat");
  const [input, setInput] = useState("도서관에서 오래된 기록을 찾고 싶어요.");
  const [messages, setMessages] = useState<PreviewMessage[]>([intro]);
  const [tested, setTested] = useState(false);
  const [results, setResults] = useState<LorePreviewResult[]>([]);
  const [diagnosticError, setDiagnosticError] = useState("");
  const [checking, setChecking] = useState(false);
  const [manualIds, setManualIds] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    setChecking(true); setResults([]); setDiagnosticError("");
    const timer = setTimeout(() => {
      void previewLore(entries, tested ? messages : [{role: "character", text: scene.opening}, {role: "user", text: input}], manualIds).then(value => { if (active) setResults(value); }).catch(() => { if (active) setDiagnosticError("서버 진단을 실행하지 못했어요. 로그인과 입력 내용을 확인해 주세요."); }).finally(() => { if (active) setChecking(false); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [entries, tested, messages, scene.opening, input, manualIds]);
  /** Add a test input to the transient history without calling an AI provider. */
  function run() {
    if (!input.trim()) return;
    setMessages(current => [...current, { role: "user", text: input.trim() }]);
    setInput(""); setTested(true); setTab("lore");
  }
  return <>
    <div className={styles.previewHead}><h2>{running ? "키워드 테스트" : "미리보기"}</h2><Search size={15} />{onClose && <button type="button" className={`${styles.iconButton} ${styles.previewClose}`} aria-label="미리보기 닫기" onClick={onClose}><X size={18} /></button>}</div>
    <ChoiceChips label="미리보기 종류" value={tab} onChange={setTab} options={[{ value: "chat", label: "대화" }, { value: "lore", label: "적용 로어" }]} />
    {tab === "chat" ? <>
      <div className={styles.chips}><span className={styles.chip}>{scene.title || "이름 없는 장면"}</span><span className={styles.chip}>{scene.language}</span></div>
      <div className={styles.bubble}><strong>{scene.title || "이름 없는 장면"}</strong><p className={styles.preserveLines}>{narrative || "도입 대사를 작성해 주세요."}</p></div>
      <strong>{character?.name || "내레이션"}</strong>{dialogue.length > 0 && <div className={`${styles.bubble} ${styles.preserveLines}`}>{dialogue.join("\n\n")}</div>}
      {messages.slice(1).map((message, index) => <div key={index} className={styles.userBubble}>{message.text}</div>)}
      {!running && <p className={styles.help}>선택한 설정이 어떻게 보이는지<br />테스트로 확인해 보세요.</p>}
    </> : <>
      <strong>{tested ? "최근 테스트 입력에 적용된 설정" : "예시 입력에 적용되는 설정"}</strong>
      {!tested && <p className={styles.help}>예시: 도서관에서 오래된 기록을 찾고 싶어요.</p>}
      {checking && <p role="status">서버 판정 확인 중…</p>}{diagnosticError && <p role="alert">{diagnosticError}</p>}
      {entries.filter(entry => entry.activation === "manual").map(entry => <label key={entry.id}><input type="checkbox" checked={manualIds.includes(entry.id)} onChange={event => setManualIds(ids => event.target.checked ? [...ids, entry.id] : ids.filter(id => id !== entry.id))} />수동 적용: {entry.title}</label>)}
      <div className={styles.diagnostics}>{results.map(result => <button type="button" key={result.entry.id} className={styles.diagnostic} onClick={() => onSelect(result.entry.id)}>
        {result.included ? <Check className={styles.positive} size={17} /> : <Minus size={17} />}<span><strong>{result.entry.title || "이름 없는 로어"}</strong><small>{result.reason}{result.included && result.order != null ? ` · 순서 ${result.order + 1}` : ""}</small></span>
      </button>)}</div>
      <p className={styles.help}>대화와 같은 서버 로어 판정으로 검색 범위·순서·그룹·항목 예산을 확인해요. 예산은 UTF-8 바이트 상한 추정이며 실제 공급자 토큰 수와 달라요.</p>
    </>}
    {running && <form className={styles.testForm} onSubmit={event => { event.preventDefault(); run(); }}><StudioField label="테스트 메시지"><textarea rows={3} placeholder="로어가 적용될 문장을 입력하세요." value={input} onChange={event => setInput(event.target.value)} /></StudioField><StudioButton primary type="submit" disabled={!input.trim()}>키워드 확인</StudioButton><StudioButton onClick={() => { setMessages([intro]); setInput("도서관에서 오래된 기록을 찾고 싶어요."); setTested(false); }}>테스트 초기화</StudioButton></form>}
    <div className={styles.previewFooter}><small className={styles.help}>서버 기준 초안 진단 · 실제 AI 호출 없음.{running && " AI 응답이나 비용은 발생하지 않습니다."}</small>{!running && <StudioButton onClick={onRun}>테스트 열기</StudioButton>}</div>
  </>;
}
