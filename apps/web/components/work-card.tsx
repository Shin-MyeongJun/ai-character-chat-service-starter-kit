import Link from "next/link";
import Image from "next/image";
import type { Work } from "@/lib/works";
import styles from "./discovery.module.css";

export function WorkCover({ work, large = false }: { work: Work; large?: boolean }) {
  if (work.coverImage) return <div className={styles.coverImage}><Image src={work.coverImage} alt="" fill sizes={large ? "(max-width: 700px) 70vw, 420px" : "(max-width: 700px) 45vw, (max-width: 1100px) 35vw, 300px"} style={{ objectFit: "cover" }} /></div>;
  return <div className={`work-cover ${large ? "work-cover-large" : ""}`} style={{ "--cover-base": work.color, "--cover-accent": work.accent } as React.CSSProperties}>
    <span className="cover-orbit cover-orbit-one" /><span className="cover-orbit cover-orbit-two" />
    <span className="cover-glow" />
    <span className="cover-symbol" aria-hidden="true">{work.symbol}</span>
    <span className="cover-caption">M O S E O R I &nbsp; / &nbsp; S T O R Y</span>
    <span className="cover-title">{work.title}</span>
  </div>;
}

export function WorkCard({ work, index }: { work: Work; index?: number }) {
  return <Link className={styles.card} href={`/works/${work.id}`}>
    <div className={styles.cardArt}><WorkCover work={work} /></div>
    <div className={styles.cardMeta}><span>{work.genre}</span><span>{work.author}</span></div>
    <h3>{work.title}</h3>
    <p>{work.subtitle}</p>
    {index !== undefined && <span className={styles.rank}>{String(index + 1).padStart(2, "0")}</span>}
  </Link>;
}
