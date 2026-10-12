"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { WorkCard } from "@/components/work-card";
import { demoWorks } from "@/lib/works";
import { listCatalog, type CatalogItem } from "@/lib/api";

const genres = ["전체", "로맨스", "판타지", "미스터리", "SF", "일상", "힐링"];

export default function Explore() {
  const [query, setQuery] = useState("");
  const [genre, setGenre] = useState("전체");
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [cursor, setCursor] = useState<{ createdAt: string; id: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    listCatalog().then(page => {
      if (!active) return;
      setCatalog(page.items);
      setCursor(page.next_cursor_id && page.next_cursor_created_at ? { createdAt: page.next_cursor_created_at, id: page.next_cursor_id } : null);
    }).catch(() => { if (active) setError("공개 작품 목록을 불러오지 못했어요."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function more() {
    if (!cursor || loading) return;
    setLoading(true); setError("");
    try {
      const page = await listCatalog(cursor);
      setCatalog(current => [...current, ...page.items.filter(item => !current.some(row => row.id === item.id))]);
      setCursor(page.next_cursor_id && page.next_cursor_created_at ? { createdAt: page.next_cursor_created_at, id: page.next_cursor_id } : null);
    } catch { setError("다음 작품 목록을 불러오지 못했어요."); }
    finally { setLoading(false); }
  }
  const published = catalog.filter(item => `${item.title} ${item.description ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  const matches = useMemo(() => demoWorks.filter((work) => (genre === "전체" || work.genre === genre) && `${work.title} ${work.subtitle} ${work.tags.join(" ")}`.toLowerCase().includes(query.toLowerCase())), [query, genre]);
  return <><SiteHeader /><main className="page-container explore-page"><div className="page-intro"><span className="section-kicker">DISCOVER YOUR STORY</span><h1>당신을 기다리는<br />이야기를 찾아보세요.</h1><p>끌리는 제목 하나에서 새로운 장면이 시작됩니다.</p></div><label className="search-box"><Search size={22} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="제목, 분위기, 키워드 검색" aria-label="작품 검색" /></label><div className="results-heading"><h2>공개 작품 <span>{published.length}</span></h2><p>서버에서 승인된 공개 작품입니다</p></div>{error && <p className="inline-notice" role="alert">{error}</p>}{loading && !catalog.length && <p>공개 작품을 불러오는 중...</p>}{published.length ? <div className="live-list">{published.map(item => <Link key={item.id} href={`/works/${item.id}`}><span><strong>{item.title}</strong><small>{item.description}</small></span><span>열기 →</span></Link>)}</div> : !loading && !error && <p>현재 공개된 작품이 없어요.</p>}{cursor && <button type="button" className="button button-primary" disabled={loading} onClick={more}>{loading ? "불러오는 중..." : "공개 작품 더 보기"}</button>}<div className="filter-chips" role="group" aria-label="장르 필터">{genres.map((item) => <button type="button" key={item} onClick={() => setGenre(item)} className={genre === item ? "active" : ""}>{item}</button>)}</div><div className="results-heading"><h2>샘플 작품 <span>{matches.length}</span></h2><p>현재 화면 구성 시연용 작품입니다</p></div>{matches.length ? <div className="work-grid">{matches.map((work) => <WorkCard key={work.id} work={work} />)}</div> : <div className="empty-state"><span>✳</span><h2>찾는 이야기가 없어요</h2><p>다른 키워드나 장르로 찾아보세요.</p></div>}</main></>;
}
