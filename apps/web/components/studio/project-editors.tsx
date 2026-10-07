"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";
import type { StudioProject, StudioScene, StudioWork } from "@/lib/studio-project";
import { ChipEditor, ChoiceChips, StudioButton, StudioField } from "./studio-controls";
import styles from "./studio.module.css";

export function EditorHeading({ title, description, spacious = false }: { title: string; description: string; spacious?: boolean }) {
  return <div className={`${styles.editorTitle} ${styles.projectHeading} ${spacious ? styles.workHeading : ""}`}><h1>{title}</h1><p>{description}</p></div>;
}
export function StudioFold({ title, description, onClick }: { title: string; description: string; onClick: () => void }) {
  return <button type="button" className={styles.fold} onClick={onClick}><span><strong>{title}</strong><small>{description}</small></span><ChevronRight size={17} /></button>;
}
export function WorkEditor({ project, update, onCharacter, onLore, onScene, onOptions }: {
  project: StudioProject; update: (patch: Partial<StudioWork>) => void;
  onCharacter: (id: string) => void; onLore: (id: string) => void; onScene: (id: string) => void; onOptions: () => void;
}) {
  const [tab, setTab] = useState<"basic" | "world" | "links">("basic");
  const { work, characters, lorebooks, scenes } = project;
  const defaultScene = scenes.find(scene => scene.id === work.defaultSceneId) ?? scenes[0];
  return <>
    <EditorHeading spacious title="작품 개요" description="이 작품의 소개와 이야기의 방향을 정해요." />
    <div className={styles.tabs}><ChoiceChips label="작품 편집 탭" value={tab} onChange={setTab} options={[{ value: "basic", label: "기본 정보" }, { value: "world", label: "세계관·규칙" }, { value: "links", label: "연결 자료" }]} /></div>
    <div className={`${styles.editorFields} ${styles.projectFields}`}>
      {tab === "basic" && <>
        <StudioField label="작품 제목"><input value={work.title} onChange={event => update({ title: event.target.value })} /></StudioField>
        <StudioField label="공개 소개" help="작품 상세 화면에 표시됩니다."><textarea className={styles.mediumText} value={work.introduction} onChange={event => update({ introduction: event.target.value })} /></StudioField>
        <ChipEditor label="정리 태그" values={work.tags} onChange={tags => update({ tags })} />
        <StudioFold title="세계관과 진행 규칙" description="AI에 전달할 비공개 설정을 편집해요." onClick={() => setTab("world")} />
        <StudioFold title="연결 자료" description={`캐릭터 ${characters.length}명 · 로어 폴더 ${new Set(lorebooks.map(entry => entry.folder)).size}개 · 로어 항목 ${lorebooks.length}개`} onClick={() => setTab("links")} />
        {defaultScene ? <StudioFold title="시작 장면과 플레이 옵션" description={`${defaultScene.title || "이름 없는 장면"}${scenes.length > 1 ? ` 외 ${scenes.length - 1}개` : ""} · 언어와 작중 시점`} onClick={onOptions} /> : <p className={styles.help}>자료 추가에서 첫 시작 장면을 만들어 주세요.</p>}
        <div className={`${styles.callout} ${styles.inlineCallout}`}><strong>현재 공개 범위: {work.visibility}</strong><span className={styles.help}>발행 전에 변경할 수 있어요.</span></div>
      </>}
      {tab === "world" && <>
        <div className={styles.callout}><strong>이야기 전체에 적용하는 설정</strong><p className={styles.help}>항상 필요한 세계관과 진행 규칙을 적어요. 특정 단어에 반응하는 설정은 로어북으로 관리하세요.</p></div>
        <StudioField label="세계관과 진행 규칙 · 비공개"><textarea rows={12} value={work.worldRules} onChange={event => update({ worldRules: event.target.value })} /></StudioField>
        <StudioField label="공개 범위" help="초안 설정만 저장하며, 실제 공개는 서버 발행 연결 후 적용됩니다."><select value={work.visibility} onChange={event => update({ visibility: event.target.value as StudioWork["visibility"] })}>{["비공개", "링크 공개", "전체 공개"].map(value => <option key={value}>{value}</option>)}</select></StudioField>
        <StudioButton onClick={() => setTab("basic")}>기본 정보로</StudioButton>
      </>}
      {tab === "links" && <>
        <StudioField label="기본 시작 장면"><select value={work.defaultSceneId} onChange={event => update({ defaultSceneId: event.target.value })}><option value="">선택 안 함</option>{scenes.map(scene => <option key={scene.id} value={scene.id}>{scene.title || "이름 없는 장면"}</option>)}</select></StudioField>
        <h2 className={styles.sectionHeading}>등장인물</h2><div className={styles.linkList}>{characters.map(character => <StudioFold key={character.id} title={character.name || "이름 없는 인물"} description={character.role || "역할을 작성해 주세요."} onClick={() => onCharacter(character.id)} />)}</div>
        <h2 className={styles.sectionHeading}>로어북</h2><div className={styles.linkList}>{lorebooks.map(entry => <StudioFold key={entry.id} title={entry.title || "이름 없는 로어"} description={`${entry.folder} · ${entry.enabled ? "활성" : "비활성"}`} onClick={() => onLore(entry.id)} />)}</div>
        <h2 className={styles.sectionHeading}>시작 장면</h2><div className={styles.linkList}>{scenes.map(scene => <StudioFold key={scene.id} title={scene.title || "이름 없는 장면"} description={`${scene.language}${scene.id === work.defaultSceneId ? " · 기본 장면" : ""}`} onClick={() => onScene(scene.id)} />)}</div>
      </>}
    </div>
  </>;
}
export type SceneTab = "content" | "initial" | "options";
export function SceneEditor({ scene, project, tab, setTab, update, onDuplicate, onTest }: {
  scene: StudioScene; project: StudioProject; tab: SceneTab; setTab: (tab: SceneTab) => void;
  update: (patch: Partial<StudioScene>) => void; onDuplicate: () => void; onTest: () => void;
}) {
  return <>
    <EditorHeading title={scene.title || "이름 없는 시작 장면"} description="독자가 처음 마주할 장면과 초기 설정을 정해요." />
    <div className={styles.tabs}><ChoiceChips label="시작 장면 편집 탭" value={tab} onChange={setTab} options={[{ value: "content", label: "장면 내용" }, { value: "initial", label: "초기 설정" }, { value: "options", label: "플레이 옵션" }]} /></div>
    <div className={`${styles.editorFields} ${styles.sceneFields}`}>
      {tab === "content" && <>
        <StudioField label="시작 장면 제목"><input value={scene.title} onChange={event => update({ title: event.target.value })} /></StudioField>
        <StudioField label="장면 배경 · 비공개"><textarea className={styles.mediumText} value={scene.background} onChange={event => update({ background: event.target.value })} /></StudioField>
        <StudioField label="도입 대사 · 독자에게 표시"><textarea className={styles.openingText} value={scene.opening} onChange={event => update({ opening: event.target.value })} /></StudioField>
        <div className={styles.fieldRow}>
          <StudioField label="처음 등장할 인물"><select value={scene.characterId} onChange={event => update({ characterId: event.target.value })}><option value="">내레이션 · 인물 선택 안 함</option>{project.characters.map(character => <option key={character.id} value={character.id}>{character.name || "이름 없는 인물"}</option>)}</select></StudioField>
          <StudioField label="시작 장소"><select value={scene.placeId} onChange={event => update({ placeId: event.target.value })}><option value="">선택 안 함</option>{project.lorebooks.filter(entry => entry.category === "장소").map(entry => <option key={entry.id} value={entry.id}>{entry.title || "이름 없는 장소"}</option>)}</select></StudioField>
        </div>
        <StudioFold title="초기 설정과 플레이 옵션" description="언어 · 작중 시점 · 인물 변형 선택" onClick={() => setTab("initial")} />
      </>}
      {tab === "initial" && <>
        <div className={styles.callout}><strong>장면이 시작될 때의 상태</strong><p className={styles.help}>관계, 이미 알고 있는 사실, 초기 목표를 적어요. 독자에게 그대로 표시되지 않는 설정입니다.</p></div>
        <StudioField label="초기 상태 · 비공개"><textarea rows={8} value={scene.initialNotes} onChange={event => update({ initialNotes: event.target.value })} /></StudioField>
        <StudioField label="인물 변형 · 비공개" help="이 장면에서 달라지는 말투나 관계를 적어요. 캐릭터의 기본 설정은 유지됩니다."><textarea className={styles.mediumText} value={scene.variants} onChange={event => update({ variants: event.target.value })} /></StudioField>
        <StudioFold title="플레이 옵션" description="언어와 작중 시점을 정해요." onClick={() => setTab("options")} />
      </>}
      {tab === "options" && <>
        <StudioField label="대화 언어"><select value={scene.language} onChange={event => update({ language: event.target.value as StudioScene["language"] })}>{["한국어", "English", "日本語"].map(value => <option key={value}>{value}</option>)}</select></StudioField>
        <StudioField label="작중 시점"><input placeholder="예: 달빛이 비치는 밤" value={scene.storyTime} onChange={event => update({ storyTime: event.target.value })} /></StudioField>
        <StudioField label="서술 시점"><select value={scene.perspective} onChange={event => update({ perspective: event.target.value as StudioScene["perspective"] })}>{["2인칭", "1인칭", "3인칭"].map(value => <option key={value}>{value}</option>)}</select></StudioField>
        <p className={styles.help}>옵션은 초안에 저장됩니다. AI 생성에 적용하는 기능은 서버 연결 후 지원합니다.</p>
      </>}
      <div className={styles.inline}><StudioButton onClick={onDuplicate}>장면 복제</StudioButton><StudioButton primary onClick={onTest}>이 장면으로 테스트</StudioButton></div>
    </div>
  </>;
}
