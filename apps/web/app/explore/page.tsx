"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { WorkCard } from "@/components/work-card";
import { demoWorks } from "@/lib/works";

const genres = ["전체", "로맨스", "판타지", "미스터리", "SF", "일상", "힐링"];

export default function Explore() {
  const [query, setQuery] = useState("");
  const [genre, setGenre] = useState("전체");
  const matches = useMemo(() => demoWorks.filter((work) => (genre === "전체" || work.genre === genre) && `${work.title} ${work.subtitle} ${work.tags.join(" ")}`.toLowerCase().includes(query.toLowerCase())), [query, genre]);
  return <><SiteHeader /><main className="page-container explore-page"><div className="page-intro"><span className="section-kicker">DISCOVER YOUR STORY</span><h1>당신을 기다리는<br />이야기를 찾아보세요.</h1><p>끌리는 제목 하나에서 새로운 장면이 시작됩니다.</p></div><label className="search-box"><Search size={22} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="제목, 분위기, 키워드 검색" aria-label="작품 검색" /></label><div className="filter-chips" role="group" aria-label="장르 필터">{genres.map((item) => <button type="button" key={item} onClick={() => setGenre(item)} className={genre === item ? "active" : ""}>{item}</button>)}</div><div className="results-heading"><h2>샘플 작품 <span>{matches.length}</span></h2><p>현재 화면 구성 시연용 작품입니다</p></div>{matches.length ? <div className="work-grid">{matches.map((work) => <WorkCard key={work.id} work={work} />)}</div> : <div className="empty-state"><span>✳</span><h2>찾는 이야기가 없어요</h2><p>다른 키워드나 장르로 찾아보세요.</p></div>}</main></>;
}
