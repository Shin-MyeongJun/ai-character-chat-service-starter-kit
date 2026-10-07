"use client";

import { useEffect, useRef, useState } from "react";
import type { CharacterAsset, StudioCharacter } from "@/lib/studio-project";
import { readImage, saveImages } from "@/lib/studio-assets";
import { ChipEditor, ChoiceChips, StudioButton, StudioField } from "./studio-controls";
import { EditorHeading, StudioFold } from "./project-editors";
import styles from "./studio.module.css";

function AssetImage({ asset }: { asset: CharacterAsset }) {
  const [url, setUrl] = useState("");
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    let disposed = false;
    let objectUrl = "";
    readImage(asset.id).then(blob => {
      if (disposed) return;
      if (!blob) { setMissing(true); return; }
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
    }).catch(() => { if (!disposed) setMissing(true); });
    return () => { disposed = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [asset.id]);
  // Browser-local object URLs cannot use Next's remote image optimizer.
  return url ? <img className={styles.assetImage} src={url} alt={asset.name} /> : <span className={styles.help}>{missing ? "이미지를 다시 등록해 주세요." : "이미지 불러오는 중"}</span>;
}
export function CharacterEditor({ character, update, scope = "work" }: { character: StudioCharacter; update: (patch: Partial<StudioCharacter>) => void; scope?: "source" | "work" }) {
  const [tab, setTab] = useState<"basic" | "relations" | "assets">("basic");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const portraitInput = useRef<HTMLInputElement>(null);
  const imagesInput = useRef<HTMLInputElement>(null);
  const portrait = character.assets.find(asset => asset.usage === "portrait");
  const otherAssets = character.assets.filter(asset => asset.usage !== "portrait");
  async function upload(files: FileList | null, usage: CharacterAsset["usage"]) {
    if (!files?.length) return;
    const incoming = Array.from(files);
    if (incoming.length > 20 || incoming.some(file => !["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 8 * 1024 * 1024)) {
      setError("PNG·JPG·WebP를 한 번에 20개까지, 파일당 8MB 이하로 등록해 주세요."); return;
    }
    setBusy(true); setError("");
    try {
      const images = incoming.map(file => ({ id: crypto.randomUUID(), file }));
      await saveImages(images);
      update({ assets: [...character.assets.filter(asset => usage !== "portrait" || asset.usage !== "portrait"), ...images.map(image => ({ id: image.id, name: image.file.name, usage }))] });
    } catch { setError("이미지를 저장하지 못했어요. 브라우저 저장 공간과 권한을 확인해 주세요."); }
    finally { setBusy(false); }
  }
  return <>
    <EditorHeading title={character.name || "이름 없는 캐릭터"} description="말투와 성격, 장면에서 보여줄 모습을 정해요." />
    <div className={styles.tabs}><ChoiceChips label="캐릭터 편집 탭" value={tab} onChange={setTab} options={[{ value: "basic", label: "기본 설정" }, { value: "relations", label: "관계" }, { value: "assets", label: "이미지·에셋" }]} /></div>
    <div className={styles.characterGrid}>
      <div className={`${styles.editorFields} ${styles.characterFields}`}>
        <div className={`${styles.callout} ${styles.scopeCallout}`}><div><strong>{scope === "source" ? "원본 편집" : "이 작품에서만 적용"}</strong><p className={styles.help}>{scope === "source" ? "보관함 원본을 저장해요. 이미 작품에 연결한 복사본은 바뀌지 않아요." : character.sourceId ? "연결한 원본과 다른 작품의 복사본은 바뀌지 않아요." : "이 작품 전용 캐릭터예요. 보관함 원본은 연결되어 있지 않아요."}</p></div></div>
        {tab === "basic" && <>
          <StudioField label="캐릭터 이름"><input value={character.name} onChange={event => update({ name: event.target.value })} /></StudioField>
          <StudioField label="공개 소개"><textarea className={styles.characterIntro} value={character.introduction} onChange={event => update({ introduction: event.target.value })} /></StudioField>
          <StudioField label="성격과 말투 · 비공개"><textarea className={styles.characterPersona} value={character.persona} onChange={event => update({ persona: event.target.value })} /></StudioField>
          <StudioField label="대사 예시"><textarea className={styles.shortText} value={character.dialogue} onChange={event => update({ dialogue: event.target.value })} /></StudioField>
          <StudioFold title="관계와 장면별 변화" description="기본 성격에 조건부 설정을 더할 수 있어요." onClick={() => setTab("relations")} />
        </>}
        {tab === "relations" && <>
          <StudioField label={scope === "source" ? "캐릭터 역할" : "작품에서의 역할"}><input value={character.role} onChange={event => update({ role: event.target.value })} /></StudioField>
          <StudioField label="인물 관계 · 비공개" help="다른 인물을 부르는 호칭, 알고 있는 사실, 관계를 적어요."><textarea rows={10} value={character.relationships} onChange={event => update({ relationships: event.target.value })} /></StudioField>
          <div className={styles.callout}><strong>장면별 변화는 시작 장면에서</strong><p className={styles.help}>시작 장면 → 초기 설정 → 인물 변형에서 이 장면에만 적용할 설정을 작성할 수 있어요.</p></div>
        </>}
        {tab === "assets" && <>
          <div className={styles.callout}><strong>이미지 용도를 나누어 관리해요.</strong><p className={styles.help}>초상은 대표 이미지, 표정은 대화 중 모습, 장면 에셋은 배경과 소품에 사용해요. 파일은 이 브라우저에 보관됩니다.</p></div>
          <StudioButton disabled={busy} onClick={() => portraitInput.current?.click()}>초상 이미지 등록</StudioButton>
          <StudioButton disabled={busy} onClick={() => imagesInput.current?.click()}>표정·장면 이미지 일괄 등록</StudioButton>
          <p className={styles.help}>PNG·JPG·WebP · 파일당 8MB 이하 · 한 번에 20개까지</p>
        </>}
      </div>
      <aside className={styles.characterMedia} aria-label="캐릭터 이미지와 태그">
        <button type="button" className={styles.portrait} disabled={busy} aria-label="초상 이미지 등록" onClick={() => portraitInput.current?.click()}>{portrait ? <AssetImage key={portrait.id} asset={portrait} /> : <><span className={styles.portraitLetter}>{character.id === "erin" ? "E" : character.name.slice(0, 1) || "?"}</span><strong>{character.name || "새 캐릭터"} / {character.role || "역할 미설정"}</strong><small className={styles.help}>초상 이미지를 등록하세요.</small></>}</button>
        {portrait && <StudioButton disabled={busy} onClick={() => update({ assets: character.assets.filter(asset => asset.id !== portrait.id) })}>초상 연결 해제</StudioButton>}
        <ChipEditor label="정리 태그" values={character.tags} onChange={tags => update({ tags })} />
        <h2>표정 이미지</h2>
        <div className={styles.assetGrid}>{!otherAssets.length && <><div className={styles.assetPlaceholder}><span>—</span><small>기본 표정</small></div><div className={styles.assetPlaceholder}><span>◡</span><small>미소</small></div></>}{otherAssets.map(asset => <div className={styles.assetCard} key={asset.id}><AssetImage asset={asset} /><StudioField label={`${asset.name} 용도`}><select disabled={busy} value={asset.usage} onChange={event => update({ assets: character.assets.map(item => item.id === asset.id ? { ...item, usage: event.target.value as "expression" | "scene" } : item) })}><option value="expression">표정 이미지</option><option value="scene">장면 에셋</option></select></StudioField><small className={styles.assetName}>{asset.name}</small><button type="button" disabled={busy} className={styles.assetRemove} onClick={() => update({ assets: character.assets.filter(item => item.id !== asset.id) })}>연결 해제</button></div>)}</div>
        <StudioButton disabled={busy} onClick={() => imagesInput.current?.click()}>{busy ? "이미지 저장 중…" : "+ 이미지 일괄 등록"}</StudioButton>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <p className={styles.help}>표정 이미지와 장면 에셋은<br />용도를 나누어 관리할 수 있어요.</p>
        <input hidden type="file" ref={portraitInput} accept="image/png,image/jpeg,image/webp" onChange={event => { void upload(event.target.files, "portrait"); event.target.value = ""; }} />
        <input hidden type="file" ref={imagesInput} multiple accept="image/png,image/jpeg,image/webp" onChange={event => { void upload(event.target.files, "expression"); event.target.value = ""; }} />
      </aside>
    </div>
  </>;
}
