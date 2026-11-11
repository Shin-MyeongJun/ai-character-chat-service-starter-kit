"use client";

import { useEffect, useRef, useState } from "react";
import { sampleProject } from "@/lib/studio-project";
import { a1Arrival, a1ImageDraft, a1ImageItems } from "@/lib/studio-chat-image-example";
import {
  addChatImageItem, buildOpeningImagePreview, normalizeChatImageTags,
  replaceChatImageFile, validateChatImageDraft, validChatImageFile,
  type ChatImageKind, type ChatImageTarget,
} from "@/lib/studio-chat-images";
import { CharacterEditor } from "./character-editor";
import { LoreEditor, type LoreTab } from "./lore-editor";
import { SceneEditor, type SceneTab } from "./project-editors";
import { ChoiceChips, StudioButton } from "./studio-controls";
import { StudioDialog } from "./studio-dialog";
import { ImageThumbnail, StudioAlbumPreview, StudioImageGroup, StudioOpeningImage } from "./studio-image-editor";
import styles from "./studio.module.css";

type Editor = "character" | "lore" | "opening";
type ImageGroup = "expression" | "characterSituation" | "loreSituation";

const sample = sampleProject();
const characterExample = { ...sample.characters[0], id: a1ImageDraft.characters[0].id, name: "수리공", role: "수리점 주인" };
const loreExample = { ...sample.lorebooks[0], id: a1ImageDraft.lorebooks[0].id, title: "수리점", content: "등불을 켜면 수리점 문이 열린다." };
const sceneExample = {
  ...sample.scenes[0], ...a1Arrival, title: "수리점 도착", background: "등불이 켜진 수리점.",
  characterId: characterExample.id, placeId: loreExample.id,
};
const initialPreviews = new Map([
  [a1ImageItems[0].imageItemId, "/images/stories/radio.png"],
  [a1ImageItems[1].imageItemId, "/images/stories/archive.png"],
]);

export function StudioImageExample() {
  const [editor, setEditor] = useState<Editor>("character");
  const [character, setCharacter] = useState(characterExample);
  const [lore, setLore] = useState(loreExample);
  const [scene, setScene] = useState(sceneExample);
  const [loreTab, setLoreTab] = useState<LoreTab>("content");
  const [sceneTab, setSceneTab] = useState<SceneTab>("content");
  const [items, setItems] = useState(a1ImageItems);
  const [errors, setErrors] = useState<Partial<Record<ImageGroup, string>>>({});
  const [preview, setPreview] = useState<"album" | "opening" | null>(null);
  const urls = useRef(new Map<string, string>());

  useEffect(() => {
    const objectUrls = urls.current;
    return () => {
      objectUrls.forEach(url => URL.revokeObjectURL(url));
      objectUrls.clear();
    };
  }, []);

  function clearLocalPreview(imageItemId: string) {
    const url = urls.current.get(imageItemId);
    if (url) URL.revokeObjectURL(url);
    urls.current.delete(imageItemId);
  }

  function selectFile(group: ImageGroup, target: ChatImageTarget, kind: ChatImageKind, file: File, imageItemId?: string) {
    if (!validChatImageFile(file)) {
      setErrors(current => ({ ...current, [group]: "32 MiB 이하의 PNG·JPEG·WebP·GIF 이미지를 선택해 주세요." }));
      return;
    }

    // The demo has local bytes only. An a2 ready response supplies the real fileVersionId.
    const added = imageItemId ? null : addChatImageItem(target, kind);
    const id = imageItemId ?? added!.imageItemId;
    const previewUrl = URL.createObjectURL(file);
    clearLocalPreview(id);
    urls.current.set(id, previewUrl);
    setItems(current => added ? [...current, added] : replaceChatImageFile(current, id, null));
    setErrors(current => ({ ...current, [group]: undefined }));
  }

  const images = items.map(item => ({
    item,
    previewUrl: urls.current.get(item.imageItemId) ?? initialPreviews.get(item.imageItemId),
  }));

  function imageGroup(group: ImageGroup, target: ChatImageTarget, kind: ChatImageKind) {
    return <StudioImageGroup
      category={kind}
      images={images.filter(({ item }) => item.kind === kind && item.target.kind === target.kind && item.target.id === target.id)}
      error={errors[group]}
      onAdd={file => selectFile(group, target, kind, file)}
      onReplace={(id, file) => selectFile(group, target, kind, file, id)}
      onMetadataChange={(id, patch) => setItems(current => current.map(item => {
        if (item.imageItemId !== id) return item;
        return "tags" in patch ? { ...item, tags: normalizeChatImageTags(patch.tags) } : { ...item, alt: patch.alt };
      }))}
      onRemove={id => {
        clearLocalPreview(id);
        // Keep affected placements visible so the author can replace or remove them explicitly.
        setItems(current => current.filter(item => item.imageItemId !== id));
      }}
    />;
  }

  const characterTarget = { kind: "character", id: character.id } as const;
  const loreTarget = { kind: "lore_entry", id: lore.id } as const;
  const project = { ...sample, characters: [character], lorebooks: [lore], scenes: [scene] };
  const validationErrors = validateChatImageDraft({ ...project, chatImageItems: items });
  const imagesById = new Map(images.map(image => [image.item.imageItemId, image]));
  const openingBlocks = buildOpeningImagePreview(scene.opening, scene.openingImagePlacements, new Set(imagesById.keys()));
  const albumItems = images.filter(({ item }) => item.fileVersionId !== null).map(image => ({
    image, sourceLabel: image.item.target.kind === "character" ? character.name : lore.title,
  }));

  return <div className={styles.studio}>
    <main className={`${styles.editor} ${styles.imageExample}`}>
      <header className={styles.editorTitle}>
        <h1>스튜디오 이미지 편집</h1>
        <p>수리점 · a1 예시 데이터</p>
      </header>
      <div className={styles.imageExampleNav}>
        <ChoiceChips label="편집 대상" value={editor} onChange={setEditor} options={[
          { value: "character", label: "캐릭터" },
          { value: "lore", label: "로어북" },
          { value: "opening", label: "첫 장면" },
        ]} />
        <StudioButton primary onClick={() => setPreview("album")}>발행 미리보기</StudioButton>
      </div>
      {editor === "character" && <CharacterEditor
        character={character}
        update={patch => setCharacter(current => ({ ...current, ...patch }))}
        imageSection={<div className={styles.editorFields}>
          {imageGroup("expression", characterTarget, "expression")}
          {imageGroup("characterSituation", characterTarget, "situation")}
        </div>}
      />}
      {editor === "lore" && <LoreEditor
        entry={lore} tab={loreTab} setTab={setLoreTab} canTest={false} onTest={() => {}}
        update={patch => setLore(current => ({ ...current, ...patch }))}
        imageSection={imageGroup("loreSituation", loreTarget, "situation")}
      />}
      {editor === "opening" && <SceneEditor
        scene={scene} project={project} tab={sceneTab} setTab={setSceneTab}
        update={patch => setScene(current => ({ ...current, ...patch }))}
        onTest={() => setPreview("opening")} testLabel="첫 장면 미리보기"
        imageSection={<StudioOpeningImage
          images={images} opening={scene.opening} placements={scene.openingImagePlacements}
          onChange={openingImagePlacements => setScene(current => ({ ...current, openingImagePlacements }))}
        />}
      />}
    </main>
    {preview === "album" && <StudioDialog title="발행 미리보기" onClose={() => setPreview(null)}>
      {validationErrors.length > 0 && <div role="status">
        <strong>발행 전 확인할 항목</strong>
        <ul>{validationErrors.map(error => <li key={error} className={styles.error}>{error}</li>)}</ul>
      </div>}
      <StudioAlbumPreview items={albumItems} />
    </StudioDialog>}
    {preview === "opening" && <StudioDialog title="첫 장면 미리보기" onClose={() => setPreview(null)}>
      {openingBlocks.map((block, index) => block.type === "text"
        ? <p key={index} className={styles.preserveLines}>{block.text}</p>
        : <ImageThumbnail key={index} image={imagesById.get(block.imageItemId)!} />)}
    </StudioDialog>}
  </div>;
}
