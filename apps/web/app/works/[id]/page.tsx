"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, Compass, Sparkles } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { WorkCover } from "@/components/work-card";
import { ApiError, getMe, getPublishedWork, startConversation, type PublishedWork } from "@/lib/api";
import { demoWorkById, isDemoWork, type Work } from "@/lib/works";
import { upsertRecentChat } from "@/lib/recent-chats";

export default function WorkDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const demo = demoWorkById(id);
  const [live, setLive] = useState<PublishedWork | null>(null);
  const [loading, setLoading] = useState(!isDemoWork(id));
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (isDemoWork(id)) return;
    getPublishedWork(id).then((work) => { setLive(work); setSelected(work.start_options[0]?.id ?? null); }).catch((cause) => {
      setError(cause instanceof ApiError && cause.status === 401 ? "이 작품을 보려면 로그인이 필요해요." : "작품을 불러오지 못했어요. 연결 상태와 작품 ID를 확인해 주세요.");
    }).finally(() => setLoading(false));
  }, [id]);

  const work: Work | null = demo ?? (live ? {
    id: live.product_id, title: live.title, subtitle: live.description || "새로운 이야기가 당신을 기다립니다.",
    genre: "연결된 작품", tags: [], author: "", color: "#34304b", accent: "#d7aa80", symbol: "✦", popularity: "", opening: "",
    startOptions: live.start_options.map((option) => ({ ...option, preview: "" })),
  } : null);
  const options = work?.startOptions ?? [];
  const selectedOption = options.find((option) => option.id === (selected ?? options[0]?.id));

  async function begin() {
    if (!work || starting) return;
    if (demo) {
      upsertRecentChat({ id: work.id, title: work.title, lastMessage: work.opening, color: work.color, accent: work.accent, symbol: work.symbol });
      router.push(`/chats/${work.id}?start=${encodeURIComponent(selectedOption?.id ?? "")}`);
      return;
    }
    setStarting(true); setError(null);
    try {
      const user = await getMe();
      const conversation = await startConversation(work.id, selectedOption?.id ?? null);
      upsertRecentChat({ id: conversation.id, title: work.title, lastMessage: "대화를 시작했어요", color: work.color, accent: work.accent, symbol: work.symbol }, user.id);
      router.push(`/chats/${conversation.id}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        router.push(`/login?next=${encodeURIComponent(`/works/${id}`)}`);
      } else {
        setError("대화를 시작했는지 확인할 수 없어요. 내 대화 목록이 연결되기 전까지 다시 누르면 대화가 하나 더 만들어질 수 있습니다.");
      }
    } finally { setStarting(false); }
  }

  return <><SiteHeader /><main className="page-container detail-page">
    <Link className="back-link" href="/explore"><ArrowLeft size={17} /> 작품 둘러보기</Link>
    {loading && <div className="loading-panel">작품을 불러오는 중...</div>}
    {!loading && !work && <div className="empty-state"><span>✳</span><h1>작품을 찾을 수 없어요</h1><p>{error ?? "주소를 다시 확인해 주세요."}</p><Link className="button button-primary" href={error?.includes("로그인") ? `/login?next=${encodeURIComponent(`/works/${id}`)}` : "/explore"}>{error?.includes("로그인") ? "로그인하기" : "다른 작품 보기"}</Link></div>}
    {work && <>
      <section className="detail-top"><div className="detail-cover"><WorkCover work={work} large /></div><div className="detail-summary"><div className="detail-kicker"><Sparkles size={15} /> {demo ? "STORY PREVIEW" : "PUBLISHED STORY"}</div><h1>{work.title}</h1><p className="detail-subtitle">{work.subtitle}</p><div className="detail-tags">{[work.genre, ...work.tags].map((tag) => <span key={tag}>#{tag}</span>)}</div><div className="detail-author">{work.author && <span>by {work.author}</span>}<span>{demo ? "화면 시연용 작품" : `버전 ${live?.version ?? ""}`}</span></div><div className="detail-description"><BookOpen size={20} /><p>당신의 선택에 따라 펼쳐지는 이야기를 만나보세요. 마음에 드는 시작 장면을 고르고 첫 문장을 보내면 됩니다.</p></div></div></section>
      <section className="start-panel"><div className="section-heading"><div><span className="section-kicker">CHOOSE YOUR BEGINNING</span><h2>어디서 시작할까요?</h2><p>시작 장면을 선택하면 대화가 열립니다.</p></div></div><div className="start-options">{options.map((option, index) => <button key={option.id} type="button" onClick={() => setSelected(option.id)} className={(selected ?? options[0]?.id) === option.id ? "selected" : ""}><span className="option-num">{String(index + 1).padStart(2, "0")}</span><span><strong>{option.title}</strong>{option.preview && <small>{option.preview}</small>}</span><span className="option-check">✓</span></button>)}</div>{demo && <div className="prologue-preview"><span className="section-kicker">PROLOGUE PREVIEW</span><p>{work.opening}</p></div>}{!demo && <p className="demo-note">첫 장면 내용은 대화를 만든 뒤 표시됩니다.</p>}{error && <p className="inline-notice" role="alert">{error}</p>}<button type="button" disabled={starting || options.length === 0} className="button button-primary start-button" onClick={begin}>{starting ? "대화를 여는 중..." : demo ? "화면 시연 시작하기" : "대화 시작하기"}<ArrowRight size={19} /></button>{demo && <p className="start-disclaimer">이 작품의 대화는 UI 시연용으로, 실제 AI 응답이나 과금이 없습니다.</p>}</section>
      <div className="detail-next"><Compass size={20} /><div><strong>다른 세계도 궁금한가요?</strong><p>당신에게 맞는 새로운 이야기를 찾아보세요.</p></div><Link href="/explore">둘러보기 <ArrowRight size={16} /></Link></div>
    </>}
  </main></>;
}
