"use client";

import { useEffect, useId, useRef, useState } from "react";
import {
  CHAT_IMAGE_TYPES, splitOpeningParagraphs, validateOpeningPlacement,
  type ChatImageItem, type ChatImageKind, type OpeningImagePlacement,
} from "@/lib/studio-chat-images";
import { readImage } from "@/lib/studio-assets";
import { ChipEditor, StudioButton, StudioField } from "./studio-controls";
import styles from "./studio.module.css";

export type StudioImage = {
  item: ChatImageItem;
  previewUrl?: string;
  previewBlobId?: string;
  pending?: boolean;
};

export type StudioImageGroupProps = {
  category: ChatImageKind;
  images: readonly StudioImage[];
  onAdd: (file: File) => void;
  onReplace: (imageItemId: string, file: File) => void;
  onMetadataChange: (imageItemId: string, patch: Pick<ChatImageItem, "tags"> | Pick<ChatImageItem, "alt">) => void;
  onRemove: (imageItemId: string) => void;
  importOptions?: readonly { id: string; label: string }[];
  onImport?: (mediaId: string) => void;
  busy?: boolean;
  error?: string;
};

function imageLabel({ item }: StudioImage) {
  return item.tags.join(", ") || item.alt.trim() || "이름 없는 이미지";
}

function ImageFileButton({ label, imageLabel, disabled, onFile }: {
  label: string;
  imageLabel?: string;
  disabled?: boolean;
  onFile: (file: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return <>
    <StudioButton
      disabled={disabled}
      aria-label={imageLabel ? `${label} · ${imageLabel}` : undefined}
      onClick={() => input.current?.click()}
    >{label}</StudioButton>
    <input
      ref={input}
      type="file"
      accept={CHAT_IMAGE_TYPES.join(",")}
      hidden
      disabled={disabled}
      onChange={event => {
        const file = event.currentTarget.files?.[0];
        event.currentTarget.value = "";
        if (file) onFile(file);
      }}
    />
  </>;
}

export function ImageThumbnail({ image }: { image: StudioImage }) {
  const [local, setLocal] = useState<{ id: string; url: string }>();
  const [failed, setFailed] = useState<string>();
  const id = image.previewBlobId;
  useEffect(() => {
    if (!id) return;
    let active = true;
    let url: string | undefined;
    void readImage(id).then(blob => {
      if (!active || !blob) return;
      url = URL.createObjectURL(blob);
      setLocal({ id, url });
    }).catch(() => { /* The server thumbnail or alt remains available. */ });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [id]);
  const src = local && local.id === id ? local.url : image.previewUrl;
  return src && failed !== src
    ? <img className={styles.assetImage} src={src} alt={image.item.alt} onError={() => setFailed(src)} />
    : <p className={styles.help}>{image.item.alt || "미리보기 이미지 없음"}</p>;
}

export function StudioImageGroup({
  category, images, onAdd, onReplace, onMetadataChange, onRemove, importOptions = [], onImport, busy, error,
}: StudioImageGroupProps) {
  const headingId = useId();
  const [importId, setImportId] = useState("");
  const label = category === "expression" ? "표정" : "상황";
  return <section aria-labelledby={headingId} aria-busy={busy} className={styles.editorFields}>
    <h2 id={headingId}>{label} 이미지</h2>
    {images.length === 0 && <p className={styles.help}>등록된 이미지가 없어요.</p>}
    <fieldset className={styles.editorFieldset} disabled={busy}>
      {images.length > 0 && <div className={styles.assetGrid}>
        {images.map((image, index) => {
          const { imageItemId, fileVersionId, tags, alt } = image.item;
          const name = (index + 1) + ". " + imageLabel(image);
          return <div key={imageItemId} className={styles.assetCard}>
            <strong>{name}</strong>
            <ImageThumbnail image={image} />
            {(image.pending || !fileVersionId) && <p className={styles.help}>업로드 대기</p>}
            <ChipEditor label={label + " 태그"} values={tags} onChange={value => onMetadataChange(imageItemId, { tags: value })} />
            <StudioField label="대체 텍스트">
              <input value={alt} onChange={event => onMetadataChange(imageItemId, { alt: event.target.value })} />
            </StudioField>
            <div className={styles.inline}>
              <ImageFileButton label="이미지 교체" imageLabel={name} onFile={file => onReplace(imageItemId, file)} />
              <StudioButton aria-label={"이미지 삭제 · " + name} onClick={() => onRemove(imageItemId)}>삭제</StudioButton>
            </div>
          </div>;
        })}
      </div>}
    </fieldset>
    <div className={styles.inline}><ImageFileButton label="새 이미지 추가" disabled={busy} onFile={onAdd} /></div>
    {onImport && importOptions.length > 0 && <div className={styles.inline}>
      <StudioField label="기존 이미지 가져오기">
        <select disabled={busy} value={importId} onChange={event => setImportId(event.target.value)}>
          <option value="">이미지 선택</option>
          {importOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
        </select>
      </StudioField>
      <StudioButton disabled={busy || !importOptions.some(option => option.id === importId)} onClick={() => {
        onImport(importId);
        setImportId("");
      }}>선택한 이미지 추가</StudioButton>
    </div>}
    {error && <p className={styles.error} role="alert">{error}</p>}
  </section>;
}

export function StudioOpeningImage({ images, opening, placements, onChange }: {
  images: readonly StudioImage[];
  opening: string;
  placements: readonly OpeningImagePlacement[];
  onChange: (placements: OpeningImagePlacement[]) => void;
}) {
  const headingId = useId();
  const paragraphs = splitOpeningParagraphs(opening);
  const imagesById = new Map(images.map(image => [image.item.imageItemId, image]));
  const imageIds = new Set(imagesById.keys());

  function updatePlacement(index: number, patch: Partial<OpeningImagePlacement>) {
    onChange(placements.map((placement, position) => position === index ? { ...placement, ...patch } : placement));
  }

  return <section aria-labelledby={headingId} className={styles.editorFields}>
    <h2 id={headingId}>첫 장면 이미지 배치</h2>
    {images.length === 0 && <p className={styles.help}>캐릭터 또는 로어북에서 이미지를 먼저 추가해 주세요.</p>}
    {placements.map((placement, index) => {
      const { missingImage, invalidPosition } = validateOpeningPlacement(placement, imageIds, paragraphs.length);
      const image = imagesById.get(placement.imageItemId);
      return <fieldset key={index} className={styles.assetCard}>
        <legend>이미지 배치 {index + 1}</legend>
        <div className={styles.fieldRow}>
          <StudioField label="기존 이미지">
            <select aria-invalid={missingImage} value={placement.imageItemId} onChange={event => updatePlacement(index, { imageItemId: event.target.value })}>
              {missingImage && <option value={placement.imageItemId} disabled>삭제됐거나 찾을 수 없는 이미지</option>}
              {images.map((option, position) => <option key={option.item.imageItemId} value={option.item.imageItemId}>
                {position + 1}. {imageLabel(option)}
              </option>)}
            </select>
          </StudioField>
          <StudioField label="삽입 위치">
            <select aria-invalid={invalidPosition} value={String(placement.afterParagraph)} onChange={event => updatePlacement(index, { afterParagraph: Number(event.target.value) })}>
              {invalidPosition && <option value={String(placement.afterParagraph)} disabled>유효하지 않은 문단 위치</option>}
              <option value="0">본문 앞</option>
              {paragraphs.map((paragraph, position) => <option key={position} value={position + 1}>
                {position + 1}번 문단 뒤 · {paragraph.trim().slice(0, 32)}
              </option>)}
            </select>
          </StudioField>
        </div>
        {missingImage && <p className={styles.error} role="alert">다른 이미지를 선택하거나 이 배치를 삭제해 주세요.</p>}
        {invalidPosition && <p className={styles.error} role="alert">문단 위치를 다시 선택해 주세요.</p>}
        {image && <ImageThumbnail image={image} />}
        <div className={styles.inline}>
          <StudioButton onClick={() => onChange(placements.filter((_, position) => position !== index))}>배치 삭제</StudioButton>
        </div>
      </fieldset>;
    })}
    <div className={styles.inline}>
      <StudioButton disabled={!images.length} onClick={() => {
        const first = images[0];
        if (first) onChange([...placements, { imageItemId: first.item.imageItemId, afterParagraph: 0 }]);
      }}>이미지 배치 추가</StudioButton>
    </div>
  </section>;
}

export type StudioAlbumItem = { image: StudioImage; sourceLabel: string };

export function StudioAlbumPreview({ items }: { items: readonly StudioAlbumItem[] }) {
  const headingId = useId();
  return <section aria-labelledby={headingId} className={styles.editorFields}>
    <h3 id={headingId}>앨범에 포함될 이미지 ({items.length})</h3>
    {items.length === 0 ? <p className={styles.help}>앨범에 포함될 이미지가 없어요.</p> :
      <div className={styles.assetGrid} role="list">
        {items.map(({ image, sourceLabel }) => <div key={image.item.imageItemId} className={styles.assetCard} role="listitem">
          <ImageThumbnail image={image} />
          <strong className={styles.assetName}>{imageLabel(image)}</strong>
          <small className={styles.help}>{sourceLabel}</small>
        </div>)}
      </div>}
  </section>;
}
