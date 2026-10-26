"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { request, authDestination, errorMessage } from "@/lib/api";
import { promptEndpoint, statuses, type PromptPage } from "@/lib/contracts";
import { defaults, readFilters, serializeFilters, validateFilters, seoulTime, listPath, type Filters } from "@/lib/filters";
import { Badge, Button, Input, Select } from "../ui";
import { QueryState } from "../query-state";

function ShortId({ value }: { value: string }) { return <span className="short-id" title={value}><span className="sr-only">{value}</span><span aria-hidden="true">{value.slice(0, 8)}<br />…{value.slice(-4)}</span></span>; }
export function PromptList() {
  const router = useRouter(); const query = useSearchParams().toString();
  const filters = readFilters(new URLSearchParams(query)); const canonical = serializeFilters(filters);
  const [draft, setDraft] = useState<Filters>(filters); const [inputError, setInputError] = useState("");
  const [result, setResult] = useState<{ key: string; data?: PromptPage; error?: string } | null>(null);
  const [attempt, retry] = useState(0);
  useEffect(() => { setDraft(readFilters(new URLSearchParams(query))); setInputError(""); }, [query]);
  useEffect(() => {
    const current = readFilters(new URLSearchParams(canonical));
    const invalid = validateFilters(current);
    if (invalid) { setResult({ key: canonical, error: invalid }); return; }
    let active = true; const controller = new AbortController();
    setResult(null);
    request<PromptPage>(`${promptEndpoint}?${canonical}`, { signal: controller.signal }).then(data => {
      if (active) setResult({ key: canonical, data });
    }).catch(cause => {
      if (!active) return;
      const destination = authDestination(cause, `${listPath}?${canonical}`);
      if (destination) { setResult(null); router.replace(destination); }
      else setResult({ key: canonical, error: errorMessage(cause) });
    });
    return () => { active = false; controller.abort(); };
  }, [canonical, attempt, router]);
  const visible = result?.key === canonical ? result : null;
  const data = visible?.data;
  const currentPath = `${listPath}?${canonical}`;
  function navigate(next: Filters) { router.push(`${listPath}?${serializeFilters(next)}`, { scroll: false }); }
  function search(event: FormEvent) {
    event.preventDefault(); const invalid = validateFilters(draft); setInputError(invalid ?? "");
    if (invalid) return;
    const next = { ...draft, page: 1 };
    if (serializeFilters(next) === canonical) retry(x => x + 1); else navigate(next);
  }
  const update = (key: keyof Filters, value: string) => setDraft(previous => ({ ...previous, [key]: value }));
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const first = data?.items.length ? (data.page - 1) * data.page_size + 1 : 0;
  const last = data?.items.length ? first + data.items.length - 1 : 0;
  const pageNumbers = [...new Set([1, Math.max(1, filters.page - 1), filters.page, Math.min(totalPages, filters.page + 1), totalPages])].filter(page => page <= totalPages).sort((a, b) => a - b);
  return <>
    <div className="page-heading"><h1>생성 프롬프트</h1><p>생성 당시의 모델 정보와 기록된 프롬프트를 확인합니다.</p></div>
    <form className="filters" onSubmit={search}>
      <div className="filter-fields">
        <label>시작일 · 서울<Input type="date" required value={draft.date_from} onChange={event => update("date_from", event.target.value)} /></label>
        <label>종료일 · 서울<Input type="date" required value={draft.date_to} onChange={event => update("date_to", event.target.value)} /></label>
        <label className="conversation-filter">대화 ID<Input placeholder="UUID 전체 입력" value={draft.conversation_id} onChange={event => update("conversation_id", event.target.value)} spellCheck={false} /></label>
        <label>생성 상태<Select value={draft.status} onChange={event => update("status", event.target.value)}><option value="">전체</option>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></label>
        <Button variant="primary" type="submit">검색</Button><Button type="button" onClick={() => { const base = defaults(); setDraft(base); setInputError(""); if (serializeFilters(base) === canonical) retry(x => x + 1); else navigate(base); }}>초기화</Button>
      </div>
      <p className="fine-print">서울 날짜 기준 · 시작일과 종료일 포함 · 최대 731일</p>
      {inputError && <p className="error-text" role="alert">{inputError}</p>}
    </form>
    <div className="results-toolbar"><p aria-live="polite">{data ? <>검색 결과 <strong>{data.total.toLocaleString("ko-KR")}건</strong></> : visible?.error ? "검색 결과 확인 불가" : "검색 결과 조회 중…"}</p>
      <label className="page-size">페이지당<Select value={filters.page_size} onChange={event => navigate({ ...filters, page_size: Number(event.target.value), page: 1 })}>{[...new Set([20, 50, 100, filters.page_size])].sort((a, b) => a - b).map(size => <option key={size} value={size}>{size}개</option>)}</Select></label>
    </div>
    {!visible ? <QueryState title="생성 프롬프트를 불러오는 중입니다." description="조건에 맞는 생성 기록을 조회하고 있습니다." loading /> : visible.error ? <QueryState title="조회하지 못했습니다." description={visible.error} retry={() => retry(x => x + 1)} /> : !data?.items.length ? <QueryState title={data?.total ? "현재 페이지에 결과가 없습니다." : "검색 결과가 없습니다."} description={data?.total ? "조회 중 결과 개수가 변경되었을 수 있습니다. 이전 페이지로 이동하거나 다시 검색해 주세요." : "날짜 범위나 검색 조건을 변경해 다시 검색해 주세요."} /> :
      <div className="table-scroll" tabIndex={0} role="region" aria-label="생성 프롬프트 조회 결과. 표 안에서 가로 및 세로 스크롤 가능">
        <table className="prompt-table"><colgroup><col className="id-col" /><col className="id-col" /><col className="model-col" /><col className="effort-col" /><col className="status-col" /><col className="time-col" /><col className="record-col" /><col className="link-col" /></colgroup>
          <thead><tr><th scope="col">생성 ID</th><th scope="col">대화 ID</th><th scope="col">당시 모델</th><th scope="col">Effort</th><th scope="col">상태</th><th scope="col">생성 시각 · 서울</th><th scope="col">원문 기록</th><th scope="col"><span className="sr-only">상세 보기</span></th></tr></thead>
          <tbody>{data.items.map(item => <tr key={item.generation_id}>
            <td><ShortId value={item.generation_id} /></td><td><ShortId value={item.conversation_id} /></td>
            <td><span className="model-name" title={item.model_name}>{item.model_name}</span></td><td><span className="breakable">{item.reasoning_effort}</span></td>
            <td><Badge status={item.status} /></td><td className="time-cell">{seoulTime(item.created_at).split(" ").map((part, index) => <span key={index}>{part}</span>)}</td><td><Badge recorded={item.prompt_recorded} /></td>
            <td><Link prefetch={false} className="detail-link" aria-label={`${item.generation_id} 상세 보기`} href={`${listPath}/${encodeURIComponent(item.generation_id)}?returnTo=${encodeURIComponent(currentPath)}`}>상세 보기</Link></td>
          </tr>)}</tbody>
        </table>
      </div>}
    {data && <div className="pagination"><p>{first}–{last} / {data.total.toLocaleString("ko-KR")}건</p><nav aria-label="검색 결과 페이지"><Button disabled={filters.page <= 1} onClick={() => navigate({ ...filters, page: filters.page - 1 })}>이전</Button>
      {pageNumbers.map((page, index) => <span className="page-number" key={page}>{index > 0 && page - pageNumbers[index - 1] > 1 && <span className="ellipsis">…</span>}<Button aria-label={`${page}페이지`} aria-current={page === filters.page ? "page" : undefined} variant={page === filters.page ? "primary" : "secondary"} onClick={() => navigate({ ...filters, page })}>{page}</Button></span>)}
      <Button disabled={filters.page >= totalPages} onClick={() => navigate({ ...filters, page: filters.page + 1 })}>다음</Button></nav></div>}
    <p className="fine-print list-note">원문 기록 여부는 저장 사실만 표시하며 생성 성공과 별개입니다. <span title="생성 버전 변경 또는 실행 유효성 만료로 결과가 반영되지 않은 상태">만료(stale)</span>는 세션 만료와 다릅니다.</p>
  </>;
}
