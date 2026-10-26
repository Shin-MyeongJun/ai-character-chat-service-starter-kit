"use client";
import { useMemo, useState } from "react";
import type { Prompt } from "@/lib/contracts";
import { copyOriginal, parseMessages } from "@/lib/prompt";
import { Button } from "../ui";
const roleLabels: Record<string, string> = { system: "시스템", user: "사용자", assistant: "어시스턴트" };
export function PromptViewer({ prompt }: { prompt: Prompt | null }) {
  const messages = useMemo(() => prompt ? parseMessages(prompt.request_json, prompt.format_version) : null, [prompt]);
  const [view, setView] = useState<"roles" | "raw">("roles"); const [wrap, setWrap] = useState(true);
  const [copy, setCopy] = useState<"idle" | "busy" | "success" | "failure">("idle");
  const raw = view === "raw" || !messages;
  async function copyAll() {
    if (!prompt) return;
    setCopy("busy");
    try { await copyOriginal(prompt.request_json, navigator.clipboard); setCopy("success"); }
    catch { setCopy("failure"); }
  }
  return <section className="prompt-section" aria-labelledby="prompt-heading">
    <div className="prompt-toolbar"><h2 id="prompt-heading">프롬프트 원문</h2><div className="prompt-actions" role="group" aria-label="원문 표시와 복사">
      <Button disabled={!messages} aria-pressed={!raw} variant={!raw ? "primary" : "secondary"} onClick={() => setView("roles")}>역할별 보기</Button>
      <Button disabled={!prompt} aria-pressed={raw} variant={raw ? "primary" : "secondary"} onClick={() => setView("raw")}>원본 JSON 문자열</Button>
      <Button disabled={!prompt || copy === "busy"} onClick={copyAll}>{copy === "success" ? "복사 완료" : copy === "busy" ? "복사 중…" : "원문 복사"}</Button>
    </div></div>
    <p className="fine-print">저장된 원문은 공급자 어댑터 변환 전 JSON입니다. 저장 사실은 공급자 전송 또는 생성 성공을 뜻하지 않습니다.</p>
    {copy === "success" && <p className="copy-feedback" role="status">원문 전체를 복사했습니다.</p>}
    {copy === "failure" && <p className="error-text" role="alert">복사하지 못했습니다. 브라우저의 클립보드 권한과 보안 연결을 확인한 뒤 다시 시도해 주세요.</p>}
    {!prompt ? <div className="query-state"><h2>기록된 프롬프트 원문이 없습니다.</h2><p>생성 기록은 존재하지만 저장된 원문이 없습니다. 미기록 이유나 전송 여부는 확인할 수 없습니다.</p></div> : <>
      {!messages && <p className="notice" role="status">역할별로 해석할 수 없는 형식입니다. 원본 문자열은 그대로 확인하고 복사할 수 있습니다.</p>}
      <div className="viewer-options"><label><input type="checkbox" checked={wrap} onChange={event => setWrap(event.target.checked)} />긴 줄 줄바꿈</label>{raw && <span>원본 문자열 · 재정렬 없음</span>}</div>
      <div className={`prompt-viewer ${wrap ? "wrap" : "nowrap"}`} tabIndex={0} role="region" aria-label={raw ? "원본 JSON 문자열" : "역할별 프롬프트"}>
        {raw ? <pre>{prompt.request_json}</pre> : messages!.map((message, index) => <article className={`prompt-message ${message.role === "user" ? "user-message" : ""}`} key={index}><h3>{message.role}{roleLabels[message.role] ? ` · ${roleLabels[message.role]}` : ""}</h3><pre>{message.content}</pre></article>)}
      </div>
    </>}
  </section>;
}
