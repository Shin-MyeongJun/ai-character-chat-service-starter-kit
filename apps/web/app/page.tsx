"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, ChevronRight, MessageCircle, RotateCcw, Search } from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { WorkCard } from "@/components/work-card";
import { GenreFilters, StoryLink } from "@/components/discovery-controls";
import { ConversationAvatar, useConversationDirectory } from "@/components/recent-conversations";
import { ApiError, getPublishedWork, listCatalog } from "@/lib/api";
import { demoWorks } from "@/lib/works";
import styles from "./discovery.module.css";

const featuredIds = (process.env.NEXT_PUBLIC_FEATURED_PRODUCT_IDS ?? "").split(",").map(id => id.trim()).filter(Boolean);
type LiveWork = { id: string; title: string; description: string | null };

export default function Home() {
  const [liveWorks, setLiveWorks] = useState<LiveWork[]>([]);
  const [liveError, setLiveError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [genre, setGenre] = useState("전체");
  const directory = useConversationDirectory();
  const lastChat = directory.recent[0];

  useEffect(() => {
    let active = true;
    setLoading(true); setLiveError("");
    void Promise.allSettled([listCatalog(), ...featuredIds.map(getPublishedWork)]).then(results => {
      if (!active) return;
      const rows = new Map<string, LiveWork>();
      for (const result of results) {
        if (result.status !== "fulfilled") continue;
        if ("items" in result.value) for (const work of result.value.items) rows.set(work.id, { id: work.id, title: work.title, description: work.description });
        else { const work = result.value; rows.set(work.product_id, { id: work.product_id, title: work.title, description: work.description }); }
      }
      // Configured featured works keep their original priority over the catalog.
      const featured = featuredIds.map(id => rows.get(id)).filter((work): work is LiveWork => !!work);
      setLiveWorks([...new Map([...featured, ...rows.values()].map(work => [work.id, work])).values()]);
      const failed = results.find((result): result is PromiseRejectedResult => result.status === "rejected");
      if (failed) setLiveError(failed.reason instanceof ApiError && failed.reason.status === 401 ? "로그인하면 연결된 작품을 볼 수 있어요." : rows.size ? "일부 공개 작품을 불러오지 못했어요." : "공개 작품을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
      setLoading(false);
    });
    return () => { active = false; };
  }, [retry]);

  const lead = demoWorks[0];
  const samples = genre === "전체" ? demoWorks.slice(0, 4) : demoWorks.filter(work => work.genre === genre);
  return <><SiteHeader /><main className={styles.main} id="user-content" tabIndex={-1}>
    <h1 className={styles.srOnly}>이야기 발견</h1>
    <GenreFilters value={genre} onChange={setGenre} />
    <section className={styles.hero} aria-labelledby="featured-story-title">
      <div className={styles.heroCopy}><p className={styles.eyebrow}>이번 주의 이야기</p><h2 id="featured-story-title">밤의 기록<br />보관소</h2><p className={styles.heroDescription}>당신이 잊은 기억을, 누군가는 기다리고 있다.</p><StoryLink href={`/works/${lead.id}`} className={styles.heroButton}>이야기 살펴보기</StoryLink></div>
      <div className={styles.heroArt}><Image src={lead.coverImage!} alt="" fill loading="eager" sizes="(max-width: 370px) 104px, (max-width: 700px) 126px, (max-width: 1100px) 220px, 348px" style={{ objectFit: "cover", objectPosition: "center top" }} /></div>
    </section>

    <section aria-labelledby="discovery-title">
      <div className={styles.sectionHeading}><div><h2 id="discovery-title">오늘의 발견</h2><p>마음이 가는 캐릭터, 빠져들고 싶은 세계</p></div><Link href="/explore">전체 보기 <ChevronRight size={14} /></Link></div>
      {samples.length ? <div className={styles.grid}>{samples.map(work => <WorkCard key={work.id} work={work} />)}</div> : <div className={styles.empty}><Search size={28} /><h3>아직 찾는 이야기가 없어요</h3><p>다른 장르로 다시 찾아보세요.</p><button type="button" onClick={() => setGenre("전체")}>필터 초기화</button></div>}
      <p className={styles.sampleNote}>샘플 작품 · 대화 화면을 체험할 수 있어요. 실제 AI 답변은 생성되지 않습니다.</p>
    </section>

    <section className={styles.continue} aria-label="최근 대화">
      {directory.loading && !lastChat ? <p role="status">이어갈 이야기를 확인하는 중…</p> : lastChat ? <>
        <ConversationAvatar chat={lastChat} /><div className={styles.continueCopy}><h2>지난 이야기를 이어볼까요?</h2><p>{lastChat.title}{lastChat.lastMessage ? ` · ${lastChat.lastMessage}` : " · 다음 장면이 기다려요"}</p></div><StoryLink href={`/chats/${lastChat.id}`}>내 대화 열기</StoryLink>
      </> : <><MessageCircle size={28} className={styles.continueIcon} /><div className={styles.continueCopy}><h2>{directory.error ? "이어갈 이야기를 확인하지 못했어요" : "아직 시작한 이야기가 없어요"}</h2><p>{directory.error ? "잠시 후 내 대화에서 다시 확인해 주세요." : "마음에 드는 작품에서 첫 장면을 열어보세요."}</p></div><StoryLink href={directory.error ? "/chats" : "/explore"}>{directory.error ? "내 대화 확인" : "작품 둘러보기"}</StoryLink></>}
      {directory.error && lastChat && <p className={styles.directoryError} role="status">{directory.error} <Link href="/chats">내 대화 확인</Link></p>}
    </section>

    <section className={styles.published} aria-labelledby="published-title" aria-busy={loading}>
      <div className={styles.sectionHeading}><div><h2 id="published-title">공개된 이야기</h2><p>새로운 세계와 캐릭터를 만나보세요</p></div><Link href="/explore">전체 보기 <ChevronRight size={14} /></Link></div>
      {liveError && <div className={styles.error} role="alert"><p>{liveError}</p><button type="button" disabled={loading} onClick={() => setRetry(value => value + 1)}><RotateCcw size={16} />다시 시도</button></div>}
      {loading && !liveWorks.length ? <div className={styles.liveGrid} role="status" aria-label="공개 작품을 불러오는 중">{[0, 1, 2, 3].map(index => <div key={index} className={styles.skeleton}><span /><i /><i /></div>)}</div>
        : liveWorks.length ? <div className={styles.liveGrid}>{liveWorks.map(work => <Link key={work.id} href={`/works/${work.id}`} className={styles.liveCard}><div className={styles.missingCover}><MessageCircle size={28} aria-hidden="true" /><span>새로운 이야기</span></div><h3>{work.title}</h3>{work.description && <p>{work.description}</p>}<span className={styles.liveMore}>이야기 살펴보기 <ArrowRight size={16} /></span></Link>)}</div>
        : !liveError && <div className={styles.empty}><MessageCircle size={28} /><h3>새로운 이야기를 기다리고 있어요</h3><p>현재 공개된 작품이 없어요. 샘플 작품을 먼저 둘러보세요.</p></div>}
    </section>
    <footer className={styles.footer}>모서리 <span>이야기가 시작되는 곳</span></footer>
  </main></>;
}
