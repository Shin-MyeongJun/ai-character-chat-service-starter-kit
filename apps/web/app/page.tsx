"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, ChevronRight, Sparkles } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { WorkCard, WorkCover } from "@/components/work-card";
import { ApiError, getPublishedWork, listCatalog, type PublishedWork } from "@/lib/api";
import { demoWorks } from "@/lib/works";

const featuredIds = (process.env.NEXT_PUBLIC_FEATURED_PRODUCT_IDS ?? "").split(",").map((id) => id.trim()).filter(Boolean);

export default function Home() {
  const [liveWorks, setLiveWorks] = useState<{ id: string; title: string }[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void listCatalog().then(page => {
      if (active) setLiveWorks(current => [...new Map([...current, ...page.items].map(item => [item.id, { id: item.id, title: item.title }])).values()]);
    }).catch(() => { if (active) setLiveError("공개 작품을 불러오지 못했어요."); });
    if (!featuredIds.length) return () => { active = false; };
    void Promise.allSettled(featuredIds.map(getPublishedWork)).then((results) => {
      if (!active) return;
      const found = results.filter((item): item is PromiseFulfilledResult<PublishedWork> => item.status === "fulfilled").map((item) => ({ id: item.value.product_id, title: item.value.title }));
      setLiveWorks(current => [...new Map([...found, ...current].map(item => [item.id, item])).values()]);
      if (results.some((item) => item.status === "rejected")) {
        const first = results.find((item): item is PromiseRejectedResult => item.status === "rejected");
        setLiveError(first?.reason instanceof ApiError && first.reason.status === 401 ? "로그인하면 연결된 작품을 볼 수 있어요." : "일부 연결된 작품을 불러오지 못했어요.");
      }
    });
    return () => { active = false; };
  }, []);

  const lead = demoWorks[0];
  return <><SiteHeader /><main>
    <section className="hero page-container">
      <div className="hero-copy">
        <p className="eyebrow"><Sparkles size={15} /> A PLACE FOR YOUR NEXT STORY</p>
        <h1>다음 장면은<br /><em>당신이</em> 완성해요.</h1>
        <p className="hero-description">어떤 세계에 들어가고 싶나요? 마음을 끄는 이야기를 발견하고, 당신만의 대화를 시작하세요.</p>
        <div className="hero-actions"><Link className="button button-primary" href="/explore">작품 둘러보기 <ArrowRight size={18} /></Link><Link className="text-link" href={`/works/${lead.id}`}>추천 이야기 보기 <ChevronRight size={17} /></Link></div>
        <div className="hero-footnote"><span className="hero-line" />하나의 선택에서 시작되는 무한한 이야기</div>
      </div>
      <Link href={`/works/${lead.id}`} className="hero-feature" aria-label={`${lead.title} 자세히 보기`}>
        <div className="hero-cover"><WorkCover work={lead} large /></div>
        <div className="hero-feature-label"><span>이번 주의 이야기</span><strong>{lead.title}</strong><ArrowRight size={18} /></div>
      </Link>
      <span className="hero-deco" aria-hidden="true">✳</span>
    </section>
    <section className="page-container featured-section">
      <div className="section-heading"><div><span className="section-kicker">CURATED FOR YOU</span><h2>오늘의 발견</h2><p>잠깐 머물러도 오래 기억에 남을 이야기들</p></div><Link href="/explore" className="section-more">전체 보기 <ArrowRight size={17} /></Link></div>
      <div className="work-grid">{demoWorks.slice(0, 4).map((work) => <WorkCard key={work.id} work={work} />)}</div>
      <p className="demo-note">위 작품들은 화면을 체험하기 위한 샘플입니다. 실제 AI 답변이 생성되지는 않습니다.</p>
    </section>
    <section className="quote-band"><div className="page-container quote-inner"><span className="quote-icon">✳</span><p>새로운 세계의 문은<br /><strong>언제나 첫 문장부터</strong> 열립니다.</p><Link href="/explore">이야기 찾아보기 <ArrowRight size={18} /></Link></div></section>
    <section className="page-container discovery-section"><div className="section-heading"><div><span className="section-kicker">MORE TO EXPLORE</span><h2>이런 이야기는 어때요?</h2></div></div><div className="work-grid compact-grid">{demoWorks.slice(2).map((work) => <WorkCard key={work.id} work={work} />)}</div></section>
    {(liveWorks.length > 0 || liveError) && <section className="page-container live-section"><div className="section-heading"><div><span className="section-kicker">CONNECTED TO YOUR API</span><h2>연결된 작품</h2></div></div>{liveError && <p className="inline-notice">{liveError} <Link href="/explore">작품 둘러보기</Link></p>}<div className="live-list">{liveWorks.map((work) => <Link key={work.id} href={`/works/${work.id}`}><span>{work.title}</span><ArrowRight size={18} /></Link>)}</div></section>}
  </main><footer className="site-footer"><div className="page-container"><span>✳ 모서리</span><p>이야기가 시작되는 곳 · 프런트 프로토타입</p></div></footer></>;
}
