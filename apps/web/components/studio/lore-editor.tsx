"use client";

import { useEffect, useState } from "react";
import { Check, ChevronRight } from "lucide-react";
import type { LoreEntry } from "@/lib/studio-data";
import { ChipEditor, ChoiceChips, StudioButton, StudioField } from "./studio-controls";
import styles from "./studio.module.css";

export type LoreTab = "content" | "conditions" | "advanced";

function NumberField({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (value: number) => void }) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const valid = draft !== "" && Number.isInteger(Number(draft)) && Number(draft) >= min && Number(draft) <= max;
  return <StudioField label={label}><input type="number" inputMode="numeric" min={min} max={max} value={draft} aria-invalid={!valid} onChange={event => { const next = event.target.value; setDraft(next); if (next && Number.isInteger(Number(next)) && Number(next) >= min && Number(next) <= max) onChange(Number(next)); }} onBlur={() => { if (!valid) setDraft(String(value)); }} />{!valid && <small className={styles.error}>{min}~{max} 사이의 정수를 입력해 주세요.</small>}</StudioField>;
}

export function LoreEditor({ entry, tab, setTab, update, onTest, canTest = true }: { entry: LoreEntry; tab: LoreTab; setTab: (tab: LoreTab) => void; update: (patch: Partial<LoreEntry>) => void; onTest: () => void; canTest?: boolean }) {
  const tabs = [{ id: "content", label: "내용" }, { id: "conditions", label: "적용 조건" }, { id: "advanced", label: "고급 설정" }] as const;
  return <>
    <div className={styles.editorTitle}><h1>{entry.title || "이름 없는 로어"}</h1><p>{tab === "advanced" ? "필요할 때만, 필요한 만큼 설정을 전달해요." : entry.category === "장소" ? "장소가 등장할 때 필요한 배경을 전달해요." : "이야기에 필요한 설정을 정리하고 전달해요."}</p></div>
    <div className={styles.tabs} role="tablist" aria-label="로어 편집 설정">{tabs.map((item, index) => <button type="button" key={item.id} id={`tab-${item.id}`} role="tab" aria-selected={tab === item.id} aria-controls="lore-panel" tabIndex={tab === item.id ? 0 : -1} className={`${styles.choice} ${tab === item.id ? styles.selected : ""}`} onClick={() => setTab(item.id)} onKeyDown={event => {
      let next = index;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault(); setTab(tabs[next].id); document.getElementById(`tab-${tabs[next].id}`)?.focus();
    }}>{item.label}</button>)}</div>
    <div role="tabpanel" id="lore-panel" aria-labelledby={`tab-${tab}`} className={`${styles.editorFields} ${tab === "content" ? styles.contentFields : ""}`}>
      {tab === "content" && <>
        <div className={`${styles.fieldRow} ${styles.titleRow}`}>
          <StudioField label="항목 제목"><input value={entry.title} maxLength={120} aria-invalid={!entry.title.trim()} onChange={event => update({ title: event.target.value })} />{!entry.title.trim() && <small className={styles.error}>항목 제목을 입력해 주세요.</small>}</StudioField>
          <StudioField label="분류"><select value={entry.category} onChange={event => update({ category: event.target.value as LoreEntry["category"] })}>{["장소", "세계관", "인물", "사건"].map(item => <option key={item}>{item}</option>)}</select></StudioField>
        </div>
        <StudioField label="설정 내용" help="이 내용은 AI에 전달되며 독자에게 그대로 공개되지 않습니다."><textarea rows={7} value={entry.content} placeholder="이 장소나 세계에 대해 AI가 알아야 할 내용을 적어 주세요." onChange={event => update({ content: event.target.value })} /></StudioField>
        <div className={styles.callout}>
          <div className={styles.inline}><strong>활성화 키워드 · 적용 조건</strong><StudioButton onClick={() => setTab("conditions")}>조건 편집</StudioButton></div>
          <div className={styles.chips}><span className={styles.chip}>{entry.activation === "keyword" ? "특정 단어가 나오면" : entry.activation === "always" ? "항상 적용" : "수동 적용"}</span></div>
          {entry.activation === "keyword" && <div className={styles.chips}>{entry.keywords.length ? entry.keywords.map(keyword => <span key={keyword} className={styles.chip}>{keyword}</span>) : <span className={styles.help}>키워드를 등록해 주세요.</span>}</div>}
          <small className={styles.help}>{entry.activation === "keyword" ? entry.match === "any" ? "대화에 등록한 문구가 등장하면 이 항목을 활성화해요. 분류 태그와 별개예요." : "대화에 등록한 문구가 모두 등장하면 이 항목을 활성화해요. 분류 태그와 별개예요." : entry.activation === "always" ? "매 대화에 이 설정을 포함해요." : "필요한 순간에 제작자가 선택해 적용하는 설정이에요."}</small>
        </div>
        <ChipEditor key={`${entry.id}-tags`} label="로어북 분류 태그 · 공개" reorderable values={entry.tags} onChange={tags => update({ tags })} help="로어북을 분류하는 공개 태그예요. 활성화 조건에는 영향을 주지 않아요." />
        <button type="button" className={styles.fold} onClick={() => setTab("advanced")}><span><strong>고급 설정</strong><small>포함 우선도 · 검색 범위 · 문맥 예산</small></span><ChevronRight size={18} /></button>
        <div className={styles.inline}><button type="button" className={`${styles.statusToggle} ${entry.enabled ? styles.positive : ""}`} aria-pressed={entry.enabled} onClick={() => update({ enabled: !entry.enabled })}>{entry.enabled && <Check size={15} />}{entry.enabled ? "활성화됨" : "비활성화됨"}</button>{canTest && <StudioButton primary onClick={onTest}>다음: 테스트하기</StudioButton>}</div>
      </>}
      {tab === "conditions" && <>
        <div className={styles.callout}><strong>설정이 필요한 순간을 정해요.</strong><small className={styles.help}>분류 태그를 바꿔도 적용 조건은 바뀌지 않아요.</small></div>
        <div className={styles.field}><span>언제 적용할까요?</span><ChoiceChips label="적용 방식" value={entry.activation} onChange={activation => update({ activation })} options={[{ value: "keyword", label: "특정 단어" }, { value: "always", label: "항상" }, { value: "manual", label: "수동" }]} /></div>
        {entry.activation === "keyword" ? <>
          <ChipEditor key={`${entry.id}-keywords`} label="활성화 키워드" values={entry.keywords} onChange={keywords => update({ keywords })} help="Enter 또는 쉼표로 추가해요. 한글 이름, 별칭, 다른 언어도 함께 등록할 수 있어요." />
          {!entry.keywords.length && <p className={styles.error}>키워드가 없으면 자동으로 적용되지 않아요.</p>}
          <StudioField label="키워드 일치 조건"><select value={entry.match} onChange={event => update({ match: event.target.value as LoreEntry["match"] })}><option value="any">키워드 중 하나 일치</option><option value="all">모든 키워드 일치</option></select></StudioField>
        </> : <p className={styles.help}>{entry.activation === "always" ? "키워드와 관계없이 매 대화에 포함하는 기본 설정에 적합해요." : "자동 키워드 검사에서는 제외돼요. 실제 수동 적용은 서버 연결 단계에서 지원할 예정이에요."}</p>}
        <StudioField label="폴더"><select value={entry.folder} onChange={event => update({ folder: event.target.value })}>{[...new Set([entry.folder, "세계관", "장소와 배경", "사건과 비밀"])].map(folder => <option key={folder}>{folder}</option>)}</select></StudioField>
        <label className={styles.checkbox}><input type="checkbox" checked={entry.enabled} onChange={event => update({ enabled: event.target.checked })} />이 항목 활성화</label>
        <div className={styles.inline}><StudioButton onClick={() => setTab("content")}>내용으로 돌아가기</StudioButton>{canTest && <StudioButton primary onClick={onTest}>키워드 확인</StudioButton>}</div>
      </>}
      {tab === "advanced" && <>
        <div className={styles.callout}><strong>기본값으로도 시작할 수 있어요.</strong><small className={styles.help}>설정이 많아지면 아래 옵션으로 포함 순서와 분량을 조절하세요.</small></div>
        <div className={styles.field}><span>포함 우선도</span><ChoiceChips label="포함 우선도" value={entry.priority} onChange={priority => update({ priority })} options={["필수", "높음", "보통", "낮음"].map(value => ({ value: value as LoreEntry["priority"], label: value }))} /><small className={styles.help}>문맥이 부족할 때, 높은 우선도의 항목부터 포함해요.</small></div>
        <div className={styles.fieldRow}>
          <NumberField label="검색 범위 · 최근 메시지 수" value={entry.scanDepth} min={1} max={100} onChange={scanDepth => update({ scanDepth })} />
          <StudioField label="검색 대상"><select value={entry.searchTarget} onChange={event => update({ searchTarget: event.target.value as LoreEntry["searchTarget"] })}><option value="all">사용자 + 캐릭터 대화</option><option value="user">사용자 대화만</option></select></StudioField>
        </div>
        <div className={styles.inline}><StudioButton aria-pressed={entry.partialMatch} onClick={() => update({ partialMatch: !entry.partialMatch })}>{entry.partialMatch && <Check size={15} />}{entry.partialMatch ? "부분 일치" : "단어 일치"}</StudioButton><StudioButton aria-pressed={entry.caseSensitive} onClick={() => update({ caseSensitive: !entry.caseSensitive })}>{entry.caseSensitive ? "대소문자 구분함" : "대소문자 구분 안 함"}</StudioButton></div>
        <div className={styles.fieldRow}><NumberField label="항목 토큰 예산" value={entry.tokenBudget} min={1} max={32000} onChange={tokenBudget => update({ tokenBudget })} /><NumberField label="배치 순서" value={entry.order} min={0} max={100000} onChange={order => update({ order })} /></div>
        <StudioField label="삽입 위치"><select value={entry.placement} onChange={event => update({ placement: event.target.value as LoreEntry["placement"] })}><option value="before">대화 이력 앞</option><option value="after">대화 이력 뒤</option></select></StudioField>
        <div className={styles.callout}><strong>동시 적용 제한</strong><span>같은 그룹의 설정 중 하나만 적용</span><StudioField label="그룹 이름"><input value={entry.exclusiveGroup} placeholder="예: 도서관 · 시간대" maxLength={80} onChange={event => update({ exclusiveGroup: event.target.value })} /></StudioField><small className={styles.help}>낮 / 밤 설정이 동시에 적용되지 않도록 해요. 비워두면 제한하지 않아요.</small></div>
        <div className={styles.inline}><StudioButton onClick={() => setTab("content")}>기본 설정으로</StudioButton>{canTest && <StudioButton primary onClick={onTest}>테스트로 확인</StudioButton>}</div>
      </>}
    </div>
  </>;
}
