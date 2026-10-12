"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import styles from "./discovery.module.css";

export function StorySearch() {
  const [query, setQuery] = useState("");
  return <form className={styles.search} action="/explore" role="search">
    <Search size={20} aria-hidden="true" />
    <input type="search" name="q" value={query} onChange={event => setQuery(event.target.value)} placeholder="제목, 분위기, 키워드 검색" aria-label="작품 검색" />
    <button type="submit" aria-label="검색"><ArrowRight size={18} /></button>
  </form>;
}

export function GenreFilters({ value, onChange }: { value: string; onChange: (genre: string) => void }) {
  return <div className={styles.genres} role="group" aria-label="샘플 작품 장르 필터">
    {["전체", "로맨스", "판타지", "미스터리", "SF", "일상", "힐링"].map(genre => <button key={genre} type="button" aria-pressed={value === genre} onClick={() => onChange(genre)}>{genre}</button>)}
  </div>;
}

export function StoryLink({ href, children, primary = false, className = "" }: { href: string; children: React.ReactNode; primary?: boolean; className?: string }) {
  return <Link href={href} className={`${styles.button} ${primary ? styles.primary : ""} ${className}`}>{children}<ArrowRight size={16} aria-hidden="true" /></Link>;
}
