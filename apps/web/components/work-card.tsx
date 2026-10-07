import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { Work } from "@/lib/works";

export function WorkCover({ work, large = false }: { work: Work; large?: boolean }) {
  return <div className={`work-cover ${large ? "work-cover-large" : ""}`} style={{ "--cover-base": work.color, "--cover-accent": work.accent } as React.CSSProperties}>
    <span className="cover-orbit cover-orbit-one" /><span className="cover-orbit cover-orbit-two" />
    <span className="cover-glow" />
    <span className="cover-symbol" aria-hidden="true">{work.symbol}</span>
    <span className="cover-caption">M O S E O R I &nbsp; / &nbsp; S T O R Y</span>
    <span className="cover-title">{work.title}</span>
  </div>;
}

export function WorkCard({ work, index }: { work: Work; index?: number }) {
  return <Link className="work-card" href={`/works/${work.id}`}>
    <div className="card-art"><WorkCover work={work} />{work.badge && <span className="card-badge">{work.badge}</span>}</div>
    <div className="card-meta"><span>{work.genre}</span><span>✦ {work.popularity}</span></div>
    <div className="card-title-row"><h3>{work.title}</h3><ArrowUpRight size={17} /></div>
    <p>{work.subtitle}</p>
    {index !== undefined && <span className="card-rank">{String(index + 1).padStart(2, "0")}</span>}
  </Link>;
}
