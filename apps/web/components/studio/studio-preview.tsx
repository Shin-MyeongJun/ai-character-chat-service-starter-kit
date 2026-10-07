"use client";

import { Check, Minus, Search, X } from "lucide-react";
import { useState } from "react";
import { previewLore, type PreviewMessage } from "@/lib/studio-preview";
import type { LoreEntry } from "@/lib/studio-data";
import type { StudioCharacter, StudioScene } from "@/lib/studio-project";
import { ChoiceChips, StudioButton, StudioField } from "./studio-controls";
import styles from "./studio.module.css";

export function StudioPreview({ entries, scene, character, running, onRun, onSelect, onClose }: { entries: LoreEntry[]; scene: StudioScene; character?: StudioCharacter; running: boolean; onRun: () => void; onSelect: (id: string) => void; onClose?: () => void }) {
  const intro: PreviewMessage = { role: "character", text: scene.opening };
  const [narrative, ...dialogue] = scene.opening.split(/\n\s*\n/);
  const [tab, setTab] = useState<"chat" | "lore">("chat");
  const [input, setInput] = useState("도서관에서 오래된 기록을 찾고 싶어요.");
  const [messages, setMessages] = useState<PreviewMessage[]>([intro]);
  const [tested, setTested] = useState(false);
  const results = previewLore(entries, tested ? messages : [intro, { role: "user", text: input }]);
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
      <div className={styles.diagnostics}>{results.map(result => <button type="button" key={result.entry.id} className={styles.diagnostic} onClick={() => onSelect(result.entry.id)}>
        {result.included ? <Check className={styles.positive} size={17} /> : <Minus size={17} />}<span><strong>{result.entry.title || "이름 없는 로어"}</strong><small>{result.reason}</small></span>
      </button>)}</div>
      <p className={styles.help}>키워드·검색 범위·우선도·동시 적용 제한을 확인해요. 토큰 예산과 삽입 위치는 저장만 하며 실제 적용은 서버 연결 후 확인할 수 있어요.</p>
    </>}
    {running && <form className={styles.testForm} onSubmit={event => { event.preventDefault(); run(); }}><StudioField label="테스트 메시지"><textarea rows={3} placeholder="로어가 적용될 문장을 입력하세요." value={input} onChange={event => setInput(event.target.value)} /></StudioField><StudioButton primary type="submit" disabled={!input.trim()}>키워드 확인</StudioButton><StudioButton onClick={() => { setMessages([intro]); setInput("도서관에서 오래된 기록을 찾고 싶어요."); setTested(false); }}>테스트 초기화</StudioButton></form>}
    <div className={styles.previewFooter}><small className={styles.help}>임시 데이터로 동작하는 화면입니다.{running && " AI 응답이나 비용은 발생하지 않습니다."}</small>{!running && <StudioButton onClick={onRun}>테스트 열기</StudioButton>}</div>
  </>;
}
