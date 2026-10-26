"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, request, authDestination, errorMessage } from "@/lib/api";
import { promptEndpoint, type PromptDetail as Detail } from "@/lib/contracts";
import { safeReturnPath, seoulTime, listPath, uuidPattern } from "@/lib/filters";
import { Badge } from "../ui";
import { QueryState } from "../query-state";
import { PromptViewer } from "./prompt-viewer";
export function PromptDetail({ id }: { id: string }) {
  const router = useRouter(); const query = useSearchParams().toString();
  const returnTo = safeReturnPath(new URLSearchParams(query).get("returnTo"));
  const [state, setState] = useState<{ id: string; data?: Detail; missing?: boolean; error?: string } | null>(null);
  const [attempt, retry] = useState(0);
  useEffect(() => {
    if (!uuidPattern.test(id)) { setState({ id, missing: true }); return; }
    let active = true; const controller = new AbortController(); setState(null);
    request<Detail>(`${promptEndpoint}/${encodeURIComponent(id)}`, { signal: controller.signal }).then(data => { if (active) setState({ id, data }); }).catch(cause => {
      if (!active) return;
      const destination = authDestination(cause, `${listPath}/${id}${query ? `?${query}` : ""}`);
      if (destination) { setState(null); router.replace(destination); }
      else if (cause instanceof ApiError && cause.status === 404) setState({ id, missing: true });
      else setState({ id, error: errorMessage(cause) });
    });
    return () => { active = false; controller.abort(); };
  }, [id, attempt, query, router]);
  const current = state?.id === id ? state : null; const data = current?.data; const generation = data?.generation;
  return <><Link prefetch={false} href={returnTo} className="button back-link">‹ 목록으로</Link>
    <div className="page-heading detail-heading"><h1>생성 프롬프트 상세</h1><p>생성 당시의 메타데이터와 저장된 원문을 조회합니다.</p></div>
    {!current ? <QueryState title="생성 기록을 불러오는 중입니다." loading /> : current.missing ? <QueryState title="생성 기록을 찾을 수 없습니다." description="존재하지 않거나 삭제된 생성 기록입니다. 목록에서 다른 기록을 선택해 주세요. (404)" /> : current.error ? <QueryState title="상세를 조회하지 못했습니다." description={current.error} retry={() => retry(x => x + 1)} /> : generation && data ? <>
      <section className="metadata" aria-label="생성 메타데이터"><dl className="metadata-grid">
        <div className="metadata-wide"><dt>생성 ID</dt><dd>{generation.generation_id}</dd></div><div className="metadata-wide"><dt>대화 ID</dt><dd>{generation.conversation_id}</dd></div>
        <div><dt>당시 모델</dt><dd>{generation.model_name}</dd></div><div><dt>Reasoning effort</dt><dd>{generation.reasoning_effort}</dd></div><div><dt>생성 시각 · 서울</dt><dd>{seoulTime(generation.created_at)}</dd></div><div><dt>완료 시각 · 서울</dt><dd>{seoulTime(generation.finished_at)}</dd></div>
      </dl><div className="metadata-status"><span>생성 상태 <Badge status={generation.status} /></span><span>원문 기록 <Badge recorded={generation.prompt_recorded} /></span><span className="invalidation">이력 무효화 시각 · 서울&nbsp; {seoulTime(generation.history_invalidated_at)}</span></div></section>
      <PromptViewer key={id + ":" + attempt} prompt={data.prompt} />
      <footer className="prompt-provenance">{data.prompt && <p>원문 기록 시각 · 서울&nbsp; {seoulTime(data.prompt.created_at)} <span>/</span> 공급자&nbsp; {data.prompt.provider} <span>/</span> 형식 버전&nbsp; {data.prompt.format_version} <span>/</span> 최대 출력 토큰&nbsp; {data.prompt.max_output_tokens}</p>}<p>모델 ID&nbsp; {generation.model_id}</p>{data.prompt && <p>SHA-256&nbsp; {data.prompt.digest}</p>}</footer>
    </> : null}
  </>;
}
