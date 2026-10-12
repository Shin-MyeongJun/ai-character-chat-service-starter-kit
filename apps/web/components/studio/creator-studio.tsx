"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BookOpen, Check, ChevronDown, ChevronLeft, FolderOpen, Moon, Plus, Search, Sun } from "lucide-react";
import { createLoreEntry, type LoreEntry } from "@/lib/studio-data";
import { createCharacter, createScene, duplicateScene, type StudioCharacter, type StudioProject } from "@/lib/studio-project";
import { createWork, linkSource, restoreTrash, trashEntity, updateProject, type TrashItem } from "@/lib/studio-workspace";
import { listAvailableModels, loadServerWorks, publishServerWork, sameStudioProject, saveServerWork, type AvailableModel } from "@/lib/studio-server";
import { ApiError } from "@/lib/api";
import { readImage } from "@/lib/studio-assets";
import { CharacterEditor } from "./character-editor";
import { WorkEditor, SceneEditor, type SceneTab } from "./project-editors";
import { LoreEditor, type LoreTab } from "./lore-editor";
import { StudioButton } from "./studio-controls";
import { StudioDialog } from "./studio-dialog";
import { StudioPreview } from "./studio-preview";
import { useStudioDraft } from "./use-studio-draft";
import styles from "./studio.module.css";

type Library = "works" | "characters" | "lore" | "trash";
type Kind = "character" | "lore" | "scene";
type Route = { kind: "library" } | { kind: "source"; type: "character" | "lore"; id: string } | { kind: "work"; workId: string; type: "overview" | Kind; id?: string };
type DeleteTarget = { kind: TrashItem["kind"]; id: string; label: string; workId?: string };
const titles: Record<Library, string> = { works: "작품", characters: "캐릭터", lore: "로어북", trash: "휴지통" };
const matches = (q: string, values: string[]) => values.join(" ").toLocaleLowerCase().includes(q.trim().toLocaleLowerCase());
const serverError = (cause: unknown) => cause instanceof ApiError && cause.status === 401 ? "로그인한 뒤 다시 시도해 주세요." : cause instanceof ApiError && cause.status === 409 ? cause.message.includes("Published studio") || cause.message.includes("updates") ? "이미 발행한 작품의 후속 버전은 현재 스튜디오에서 저장·발행할 수 없어요." : "서버 초안이 바뀌었어요. 서버 초안을 확인한 뒤 다시 시도해 주세요." : cause instanceof Error ? cause.message : "서버 요청에 실패했어요. 다시 시도해 주세요.";

export function CreatorStudio() {
  const draft = useStudioDraft(); const { workspace, ready, status, storageWarning, commit } = draft;
  const [route, setRoute] = useState<Route>({ kind: "library" });
  const [library, setLibrary] = useState<Library>("works");
  const [queries, setQueries] = useState<Record<Library, string>>({ works: "", characters: "", lore: "", trash: "" });
  const [treeQuery, setTreeQuery] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [pane, setPane] = useState<"editor" | "resources" | "preview">("editor");
  const [tab, setTab] = useState<LoreTab>("content"); const [sceneTab, setSceneTab] = useState<SceneTab>("content");
  const [running, setRunning] = useState(false); const [previewId, setPreviewId] = useState<string | null>(null);
  const [modal, setModal] = useState<"add" | "connect" | "publish" | null>(null);
  const [connectQuery, setConnectQuery] = useState("");
  const [deleting, setDeleting] = useState<DeleteTarget | null>(null);
  const [notice, setNotice] = useState("");
  const [serverBusy, setServerBusy] = useState(false);
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedEffort, setSelectedEffort] = useState("");
  const [releaseSummary, setReleaseSummary] = useState("첫 발행");
  const [releaseBody, setReleaseBody] = useState("스튜디오에서 만든 첫 작품입니다.");
  const [publishedId, setPublishedId] = useState<string | null>(null);
  const activeWork = route.kind === "work" ? workspace.works.find(w => w.id === route.workId) : undefined;
  const project = activeWork?.project; const isWork = !!project;
  const character = route.kind === "source" && route.type === "character" ? workspace.characters.find(c => c.id === route.id) : route.kind === "work" && route.type === "character" ? project?.characters.find(c => c.id === route.id) : undefined;
  const lore = route.kind === "source" && route.type === "lore" ? workspace.lorebooks.find(l => l.id === route.id) : route.kind === "work" && route.type === "lore" ? project?.lorebooks.find(l => l.id === route.id) : undefined;
  const scene = route.kind === "work" && route.type === "scene" ? project?.scenes.find(s => s.id === route.id) : undefined;
  const previewScene = project?.scenes.find(s => s.id === (previewId ?? project.work.defaultSceneId)) ?? project?.scenes[0];
  const wide = !!character;
  useEffect(() => {
    if (!ready) return;
    if (route.kind === "work" && !activeWork) { setRoute({ kind: "library" }); setLibrary("works"); setPane("editor"); }
    else if (route.kind === "source" && !(route.type === "character" ? character : lore)) { setLibrary(route.type === "character" ? "characters" : "lore"); setRoute({ kind: "library" }); setPane("editor"); }
    else if (route.kind === "work" && route.type !== "overview" && !(route.type === "character" ? character : route.type === "lore" ? lore : scene)) { setRoute({ kind: "work", workId: route.workId, type: "overview" }); setPane("editor"); }
  }, [ready, route, activeWork, character, lore, scene]);
  useEffect(() => { try { if (localStorage.getItem("chat-kit-studio-theme") === "dark") setTheme("dark"); } catch { /* Optional theme persistence. */ } }, []);
  useEffect(() => { window.scrollTo({ top: 0, behavior: "instant" }); }, [route, pane]);
  useEffect(() => {
    if (modal !== "publish") return;
    let active = true;
    void listAvailableModels().then(rows => {
      if (!active) return;
      setModels(rows);
      setSelectedModel(rows[0]?.id ?? "");
      setSelectedEffort(rows[0]?.reasoning_efforts[0] ?? "");
    }).catch(() => { if (active) setNotice("사용 가능한 모델을 불러오지 못했어요."); });
    return () => { active = false; };
  }, [modal]);
  function themeToggle() { const next = theme === "light" ? "dark" : "light"; setTheme(next); try { localStorage.setItem("chat-kit-studio-theme", next); } catch { setNotice("테마는 현재 화면에만 적용됩니다."); } }
  function home(nextLibrary = library) { setLibrary(nextLibrary); setRoute({ kind: "library" }); setPane("editor"); setModal(null); setRunning(false); setPreviewId(null); }
  function openWork(workId: string) { setRoute({ kind: "work", workId, type: "overview" }); setTreeQuery(""); setPane("editor"); setRunning(false); setPreviewId(null); }
  function select(type: "overview" | Kind, id?: string) { if (!activeWork) return; setRoute({ kind: "work", workId: activeWork.id, type, id }); setTab("content"); setSceneTab("content"); setPane("editor"); if (type === "scene") { setPreviewId(id ?? null); setRunning(false); } else if (type === "overview") { setPreviewId(null); setRunning(false); } }
  function openSource(type: "character" | "lore", id: string) { setRoute({ kind: "source", type, id }); setPane("editor"); setTab("content"); setRunning(false); }
  function changeProject(change: (p: StudioProject) => StudioProject) { if (activeWork) { setPublishedId(null); commit(w => updateProject(w, activeWork.id, change)); } }
  function editCharacter(patch: Partial<StudioCharacter>) {
    if (!character) return;
    if (route.kind === "source") commit(w => ({ ...w, characters: w.characters.map(c => c.id === character.id ? { ...c, ...patch } : c) }));
    else changeProject(p => ({ ...p, characters: p.characters.map(c => c.id === character.id ? { ...c, ...patch } : c) }));
  }
  function editLore(patch: Partial<LoreEntry>) {
    if (!lore) return;
    if (route.kind === "source") commit(w => ({ ...w, lorebooks: w.lorebooks.map(l => l.id === lore.id ? { ...l, ...patch } : l) }));
    else changeProject(p => ({ ...p, lorebooks: p.lorebooks.map(l => l.id === lore.id ? { ...l, ...patch } : l) }));
  }
  function newWork() { const work = createWork(); commit(w => ({ ...w, works: [...w.works, work] })); openWork(work.id); }
  function add(type: Kind) {
    if (type === "character") {
      const c = createCharacter();
      if (isWork) { changeProject(p => ({ ...p, characters: [...p.characters, c] })); select(type, c.id); }
      else { commit(w => ({ ...w, characters: [...w.characters, c] })); openSource(type, c.id); }
    } else if (type === "lore") {
      const l = createLoreEntry();
      if (isWork) { changeProject(p => ({ ...p, lorebooks: [...p.lorebooks, l] })); select(type, l.id); }
      else { commit(w => ({ ...w, lorebooks: [...w.lorebooks, l] })); openSource(type, l.id); }
    } else if (project) {
      const s = createScene("", ""); changeProject(p => ({ ...p, scenes: [...p.scenes, s], work: { ...p.work, defaultSceneId: p.work.defaultSceneId || s.id } })); select(type, s.id);
    }
    setModal(null);
  }
  function connect(type: "character" | "lore", id: string) {
    if (!activeWork) return;
    commit(w => linkSource(w, activeWork.id, type, id)); setModal(null); setNotice("원본을 작품 전용 복사본으로 연결했어요. 원본 수정은 이 복사본에 자동 반영되지 않아요.");
  }
  function remove() {
    if (!deleting) return;
    const target = deleting; commit(w => trashEntity(w, target.kind, target.id, target.workId)); setDeleting(null);
    if (target.kind === "work") home("works");
    else if (target.kind === "character") home("characters");
    else if (target.kind === "lore") home("lore");
    else select("overview");
    setNotice("휴지통으로 이동했어요. 내 작업실 → 휴지통에서 복구할 수 있어요.");
  }
  function restore(id: string) { commit(w => restoreTrash(w, id)); setNotice("복구했어요. 원본 삭제로 해제된 연결은 자동으로 다시 연결하지 않습니다."); }
  function exportData(value: unknown, name: string) { const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" })); const a = document.createElement("a"); a.href = url; a.download = name; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); setNotice("JSON 내보내기를 요청했어요. 이미지 파일은 별도로 보관해 주세요."); }
  function test() { if (previewScene) { setRunning(true); setPane("preview"); } }
  async function saveServer() {
    if (!activeWork || serverBusy) return;
    setServerBusy(true); setNotice("");
    try {
      await saveServerWork(activeWork);
      setNotice(activeWork.project.characters.some(row => row.assets.length)
        ? "작품 문서를 서버에 저장했어요. 이미지 원본은 이 기기에만 있어 다른 기기에서 복원되지 않습니다."
        : "서버에 저장했어요. 다른 기기에서 내 작업실의 서버 초안 가져오기로 복원할 수 있어요.");
    }
    catch (cause) { setNotice(serverError(cause)); }
    finally { setServerBusy(false); }
  }
  async function restoreServer() {
    if (serverBusy) return;
    setServerBusy(true); setNotice("");
    try {
      const incoming = await loadServerWorks(workspace.works);
      const additions = incoming.filter(row => !workspace.works.some(local => local.id === row.id));
      const conflicts = incoming.filter(row => workspace.works.some(local => local.id === row.id && !sameStudioProject(local.project, row.project)));
      if (additions.length) commit(current => ({ ...current, works: [...current.works, ...additions.filter(row => !current.works.some(existing => existing.id === row.id))] }));
      const assetIds = [...new Set(incoming.flatMap(row => row.project.characters.flatMap(character => character.assets.map(asset => asset.id))))];
      const missingImages = (await Promise.all(assetIds.map(async id => (await readImage(id).catch(() => null)) ? 0 : 1))).reduce<number>((sum, missing) => sum + missing, 0);
      setNotice(`${additions.length}개 작품을 가져왔어요.${conflicts.length ? ` 다른 기기와 내용이 다른 ${conflicts.length}개 작품은 이 브라우저의 초안을 유지했어요.` : ""}${missingImages ? ` 이미지 원본 ${missingImages}개는 이 기기에 없어 표시·발행할 수 없습니다.` : ""}`);
    } catch (cause) { setNotice(serverError(cause)); }
    finally { setServerBusy(false); }
  }
  async function publishWork() {
    if (!activeWork || serverBusy) return;
    setServerBusy(true); setNotice("");
    try {
      const result = await publishServerWork(activeWork, selectedModel, selectedEffort, releaseSummary, releaseBody);
      setPublishedId(result.productId);
      setNotice(`버전 ${result.release.version}을 발행했어요. 작품 상세에서 대화를 시작할 수 있어요.`);
    } catch (cause) { setNotice(serverError(cause)); }
    finally { setServerBusy(false); }
  }
  const q = queries[library];
  const filteredLore = project?.lorebooks.filter(l => matches(treeQuery, [l.title, l.folder, l.category, ...l.tags, ...l.keywords])) ?? [];
  const filteredCharacters = project?.characters.filter(c => matches(treeQuery, [c.name, c.role, ...c.tags])) ?? [];
  const filteredScenes = project?.scenes.filter(s => matches(treeQuery, [s.title, s.language])) ?? [];
  const folders = [...new Set(filteredLore.map(l => l.folder))];
  const current = (type: Kind, id: string) => route.kind === "work" && route.type === type && route.id === id;
  const deletionImpact = deleting?.kind === "work" ? "이 작품과 작품 전용 자료를 휴지통에 보관합니다. 독립 원본은 유지됩니다." : deleting?.kind === "character" || deleting?.kind === "lore" ? `독립 원본을 휴지통으로 이동합니다. 연결된 작품 ${workspace.works.filter(w => (deleting.kind === "character" ? w.project.characters : w.project.lorebooks).some(row => row.sourceId === deleting.id)).length}개의 복사본은 현재 내용을 유지하고 작품 전용으로 전환됩니다.` : deleting?.kind === "scene" ? "시작 장면을 휴지통으로 이동합니다. 기본 장면이면 남은 첫 장면으로 변경하며, 마지막 장면이면 선택을 비웁니다." : `이 작품에서만 연결을 해제합니다. 원본과 다른 작품은 유지됩니다. 참조하는 장면 ${project?.scenes.filter(s => deleting?.kind === "work-character" ? s.characterId === deleting.id : s.placeId === deleting?.id).length ?? 0}개의 인물·장소 선택은 비워집니다.`;
  const publishReady = !!project && !!project.scenes.length && !!project.characters.length && !!project.work.defaultSceneId &&
    project.characters.every(c => !!c.name.trim() && !!c.persona.trim() && !c.assets.length) &&
    project.scenes.every(s => !!s.title.trim() && !!s.opening.trim() && !!s.characterId) &&
    project.lorebooks.every(l => !!l.title.trim() && !!l.content.trim() && (!l.enabled || l.activation !== "keyword" || !!l.keywords.length)) &&
    !!selectedModel && !!selectedEffort && !!releaseSummary.trim() && !!releaseBody.trim();
  const resultsCount = library === "works" ? workspace.works.filter(w => matches(q, [w.project.work.title, ...w.project.work.tags])).length : library === "characters" ? workspace.characters.filter(c => matches(q, [c.name, c.role, ...c.tags])).length : library === "lore" ? workspace.lorebooks.filter(l => matches(q, [l.title, l.folder, ...l.tags])).length : workspace.trash.filter(t => matches(q, [t.label])).length;
  return <div className={styles.studio} data-theme={theme} data-pane={pane} data-context={isWork ? "work" : "library"}>
    <a className={styles.skipLink} href="#studio-editor">편집 영역으로 이동</a>
    <header className={styles.topbar}>
      <button type="button" className={styles.brand} aria-label="내 작업실 열기" onClick={() => home()}><span>S</span><strong>STUDIO</strong></button>
      <span className={styles.breadcrumb}>{isWork ? `내 작품 / ${project.work.title || "이름 없는 작품"}` : route.kind === "source" ? "내 작업실 / 원본 편집" : "내 작업실"}</span>
      <div className={styles.topActions}><span className={styles.saveStatus} role="status">{ready && !status.includes("실패") && <Check size={14} />}{status}</span><StudioButton onClick={themeToggle} aria-label={theme === "light" ? "다크 모드" : "라이트 모드"}>{theme === "light" ? <Moon size={17} /> : <Sun size={17} />}<span>{theme === "light" ? "다크 모드" : "라이트 모드"}</span></StudioButton>{isWork && <><StudioButton disabled={serverBusy} onClick={() => void saveServer()}>{serverBusy ? "서버 작업 중…" : "서버에 저장"}</StudioButton><StudioButton disabled={!previewScene} onClick={test}>테스트</StudioButton><StudioButton onClick={() => setModal("publish")}>발행</StudioButton></>}</div>
    </header>
    {isWork && <div className={styles.mobileToolbar}><button onClick={() => setPane(pane === "resources" ? "editor" : "resources")}><FolderOpen size={17} />{pane === "resources" ? "편집으로" : "자료 탐색"}</button><span>{status}</span><button onClick={() => setPane(pane === "preview" ? "editor" : "preview")}>{pane === "preview" ? "편집으로" : "미리보기"}</button></div>}
    <div className={styles.workspace} data-wide={wide}>
      {project && <aside className={styles.explorer} aria-label="작품 자료 탐색기">
        <StudioButton onClick={() => home("works")}><ChevronLeft size={15} /> 내 작업실</StudioButton><h2>{project.work.title || "이름 없는 작품"}</h2><small className={styles.help}>캐릭터 {project.characters.length} · 로어 {project.lorebooks.length} · 시작 장면 {project.scenes.length}</small>
        <label className={styles.search}><Search size={16} /><input aria-label="작품 자료 검색" placeholder="자료·태그 검색" value={treeQuery} onChange={e => setTreeQuery(e.target.value)} />{treeQuery && <button aria-label="작품 자료 검색 초기화" onClick={() => setTreeQuery("")}>×</button>}</label>
        <nav className={styles.tree} aria-label="작품 구성"><button className={styles.treeRow} aria-current={route.kind === "work" && route.type === "overview" ? "page" : undefined} onClick={() => select("overview")}>작품 개요</button>
          {!!filteredCharacters.length && <details open key={`characters-${treeQuery}`}><summary><ChevronDown size={12} />등장인물</summary>{filteredCharacters.map(c => <button className={`${styles.treeRow} ${styles.indent}`} key={c.id} aria-current={current("character", c.id) ? "page" : undefined} onClick={() => select("character", c.id)}>{c.name || "이름 없는 인물"}</button>)}</details>}
          {!!filteredLore.length && <details open key={`lore-${treeQuery}`}><summary><ChevronDown size={12} />로어북</summary>{folders.map(folder => <details open key={folder} className={styles.treeFolder}><summary>{folder}</summary>{filteredLore.filter(l => l.folder === folder).map(l => <button className={`${styles.treeRow} ${styles.loreRow}`} key={l.id} aria-current={current("lore", l.id) ? "page" : undefined} onClick={() => select("lore", l.id)}>{l.title || "이름 없는 로어"}{!l.enabled && <span className={styles.disabledDot} aria-label="비활성" />}</button>)}</details>)}</details>}
          {!!filteredScenes.length && <details open key={`scenes-${treeQuery}`}><summary><ChevronDown size={12} />시작 장면</summary>{filteredScenes.map(s => <button className={`${styles.treeRow} ${styles.indent}`} key={s.id} aria-current={current("scene", s.id) ? "page" : undefined} onClick={() => select("scene", s.id)}>{s.title || "이름 없는 장면"}</button>)}</details>}
          {!treeQuery && previewScene && <button className={styles.treeRow} onClick={() => { select("scene", previewScene.id); setSceneTab("options"); }}>플레이 옵션</button>}
          {treeQuery && !filteredCharacters.length && !filteredLore.length && !filteredScenes.length && <p className={styles.emptySmall}>검색 결과가 없어요.</p>}
        </nav><div className={styles.explorerFooter}><StudioButton disabled={!ready} onClick={() => setModal("add")}><Plus size={15} />자료 추가</StudioButton><StudioButton onClick={() => { setConnectQuery(""); setModal("connect"); }}>보관함 원본 연결</StudioButton><Link href="/" className={styles.siteLink}>서비스 홈으로</Link></div>
      </aside>}
      <main className={styles.editor} id="studio-editor" tabIndex={-1}>
        {(storageWarning || notice) && <div className={styles.notice} role="status">{notice || storageWarning}{notice && <button aria-label="알림 닫기" onClick={() => setNotice("")}>×</button>}</div>}
        <fieldset disabled={!ready} className={styles.editorFieldset}>
          {route.kind === "library" && <>
            <div className={styles.editorTitle}><h1>내 작업실</h1><p>작품과 독립 원본 자료를 관리해요.</p></div>
            <div className={styles.libraryTabs} role="group" aria-label="보관함 선택">{(Object.keys(titles) as Library[]).map(key => <StudioButton key={key} primary={library === key} aria-pressed={library === key} onClick={() => setLibrary(key)}>{titles[key]}{key === "trash" && ` ${workspace.trash.length}`}</StudioButton>)}</div>
              <div className={styles.libraryActions}><label className={styles.search}><Search size={16} /><input aria-label={`${titles[library]} 보관함 검색`} placeholder="이름·제목·태그 검색" value={q} onChange={e => setQueries(prev => ({ ...prev, [library]: e.target.value }))} />{q && <button aria-label={`${titles[library]} 검색 초기화`} onClick={() => setQueries(prev => ({ ...prev, [library]: "" }))}>×</button>}</label>{library === "works" ? <><StudioButton primary onClick={newWork}>새 작품</StudioButton><StudioButton disabled={serverBusy} onClick={() => void restoreServer()}>서버 초안 가져오기</StudioButton></> : library === "characters" ? <StudioButton primary onClick={() => add("character")}>새 캐릭터</StudioButton> : library === "lore" ? <StudioButton primary onClick={() => add("lore")}>새 로어북</StudioButton> : null}<StudioButton onClick={() => exportData(workspace, "studio-workspace.json")}>작업실 내보내기</StudioButton></div>
            {library !== "trash" && <div className={styles.chips} aria-label={`${titles[library]} 태그로 검색`}>{[...new Set(library === "works" ? workspace.works.flatMap(w => w.project.work.tags) : library === "characters" ? workspace.characters.flatMap(c => c.tags) : workspace.lorebooks.flatMap(l => l.tags))].map(tag => <button key={tag} className={styles.choice} aria-pressed={q === tag} onClick={() => setQueries(prev => ({ ...prev, [library]: q === tag ? "" : tag }))}>{tag}</button>)}</div>}
            <p className={styles.help}>{library === "characters" || library === "lore" ? "독립 원본 보관함입니다. 기존 작품 전용 자료는 해당 작품에서 편집하세요." : library === "trash" ? "영구 삭제 없이 보관합니다. 작품 내부 자료는 소속 작품을 먼저 복구하세요." : "작품을 선택하면 작품 내부 편집이 열립니다."}</p>
            <div className={styles.libraryList}>
              {library === "works" && workspace.works.filter(w => matches(q, [w.project.work.title, ...w.project.work.tags])).map(w => <div className={styles.libraryItem} key={w.id}><button className={styles.libraryCard} onClick={() => openWork(w.id)}><span className={styles.chip}>초안</span><strong>{w.project.work.title || "이름 없는 작품"}</strong><p>{w.project.work.introduction}</p><small>캐릭터 {w.project.characters.length} · 로어 {w.project.lorebooks.length} · 장면 {w.project.scenes.length}</small></button><StudioButton className={styles.dangerButton} aria-label={`${w.project.work.title} 작품 삭제`} onClick={() => setDeleting({ kind: "work", id: w.id, label: w.project.work.title })}>작품 삭제</StudioButton></div>)}
              {library === "characters" && workspace.characters.filter(c => matches(q, [c.name, c.role, ...c.tags])).map(c => <div className={styles.libraryItem} key={c.id}><button className={styles.libraryCard} onClick={() => openSource("character", c.id)}><span className={styles.chip}>독립 원본</span><strong>{c.name || "이름 없는 인물"}</strong><p>{c.introduction}</p><small>{c.tags.join(" · ")}</small></button><StudioButton className={styles.dangerButton} aria-label={`${c.name} 원본 삭제`} onClick={() => setDeleting({ kind: "character", id: c.id, label: c.name })}>원본 삭제</StudioButton></div>)}
              {library === "lore" && workspace.lorebooks.filter(l => matches(q, [l.title, l.folder, ...l.tags])).map(l => <div className={styles.libraryItem} key={l.id}><button className={styles.libraryCard} onClick={() => openSource("lore", l.id)}><span className={styles.chip}>독립 원본</span><strong>{l.title || "이름 없는 로어"}</strong><p>{l.content}</p><small>{l.tags.join(" · ")}</small></button><StudioButton className={styles.dangerButton} aria-label={`${l.title} 원본 삭제`} onClick={() => setDeleting({ kind: "lore", id: l.id, label: l.title })}>원본 삭제</StudioButton></div>)}
              {library === "trash" && workspace.trash.filter(t => matches(q, [t.label])).map(t => <div className={styles.libraryCard} key={t.id}><strong>{t.label || "이름 없는 자료"}</strong><small>{t.kind === "work" ? "작품" : t.kind === "character" || t.kind === "lore" ? "독립 원본" : "작품 내부 자료"} · {new Date(t.deletedAt).toLocaleString("ko-KR")}</small><StudioButton aria-label={`${t.label} 복구`} disabled={"workId" in t && !workspace.works.some(w => w.id === t.workId)} onClick={() => restore(t.id)}>복구</StudioButton>{"workId" in t && !workspace.works.some(w => w.id === t.workId) && <p className={styles.help}>소속 작품을 먼저 복구하세요.</p>}</div>)}
            </div>{resultsCount === 0 && <div className={styles.emptySmall}>{q ? "검색 결과가 없어요." : library === "trash" ? "휴지통이 비어 있어요." : "아직 등록한 자료가 없어요. 위의 추가 버튼으로 시작하세요."}</div>}
          </>}
          {route.kind === "source" && <div className={styles.editActions}><StudioButton onClick={() => home(route.type === "character" ? "characters" : "lore")}><ChevronLeft size={15} />보관함으로</StudioButton><StudioButton className={styles.dangerButton} onClick={() => setDeleting({ kind: route.type, id: route.id, label: character?.name || lore?.title || "자료" })}>원본 삭제</StudioButton></div>}
          {project && route.kind === "work" && <div className={styles.editActions}><span className={styles.help}>{route.type === "overview" ? "작품 전용 초안" : "이 작품에서만 적용"}</span><StudioButton className={styles.dangerButton} onClick={() => setDeleting(route.type === "overview" ? { kind: "work", id: activeWork.id, label: project.work.title } : { kind: route.type === "character" ? "work-character" : route.type === "lore" ? "work-lore" : "scene", id: route.id!, label: character?.name || lore?.title || scene?.title || "자료", workId: activeWork.id })}>{route.type === "overview" ? "작품 삭제" : route.type === "scene" ? "시작 장면 삭제" : "작품에서 연결 해제"}</StudioButton></div>}
          {project && route.kind === "work" && route.type === "overview" && <WorkEditor key={activeWork.id} project={project} update={patch => { if (patch.defaultSceneId !== undefined) setPreviewId(null); changeProject(p => ({ ...p, work: { ...p.work, ...patch } })); }} onCharacter={id => select("character", id)} onLore={id => select("lore", id)} onScene={id => select("scene", id)} onOptions={() => { if (previewScene) { select("scene", previewScene.id); setSceneTab("options"); } }} />}
          {character && <CharacterEditor key={`${route.kind}-${activeWork?.id}-${character.id}`} character={character} scope={route.kind === "source" ? "source" : "work"} update={editCharacter} />}
          {lore && <>{route.kind === "source" && <div className={styles.callout}><strong>원본 편집</strong><p className={styles.help}>보관함 원본을 저장해요. 기존 작품의 복사본은 바뀌지 않아요.</p></div>}<LoreEditor key={`${route.kind}-${activeWork?.id}-${lore.id}`} entry={lore} canTest={isWork && !!previewScene} tab={tab} setTab={setTab} update={editLore} onTest={isWork ? test : () => setNotice("원본을 작품에 연결하고 시작 장면을 만든 뒤 테스트해 주세요.")} /></>}
          {scene && project && <SceneEditor key={scene.id} scene={scene} project={project} tab={sceneTab} setTab={setSceneTab} update={patch => changeProject(p => ({ ...p, scenes: p.scenes.map(s => s.id === scene.id ? { ...s, ...patch } : s) }))} onDuplicate={() => { const copy = duplicateScene(scene); changeProject(p => ({ ...p, scenes: [...p.scenes, copy] })); select("scene", copy.id); }} onTest={test} />}
        </fieldset>
      </main>
      {project && <aside className={styles.preview} aria-label="작품 미리보기">{previewScene ? <StudioPreview key={`${activeWork.id}-${previewScene.id}-${previewScene.opening}-${previewScene.characterId}`} entries={project.lorebooks} scene={previewScene} character={project.characters.find(c => c.id === previewScene.characterId)} running={running} onRun={test} onSelect={id => select("lore", id)} onClose={() => setPane("editor")} /> : <><h2>미리보기</h2><p className={styles.help}>아직 시작 장면이 없어요. 자료 추가에서 첫 장면을 만들어 주세요.</p><StudioButton onClick={() => add("scene")}>시작 장면 추가</StudioButton></>}</aside>}
    </div>
    {isWork && <nav className={styles.mobileNav} aria-label="스튜디오 화면 전환">{([{ id: "resources", label: "자료" }, { id: "editor", label: "편집" }, { id: "preview", label: "미리보기" }] as const).map(item => <button key={item.id} className={pane === item.id ? styles.mobileActive : ""} aria-current={pane === item.id ? "page" : undefined} onClick={() => setPane(item.id)}><BookOpen size={19} />{item.label}</button>)}</nav>}
    {modal === "add" && project && <StudioDialog title="작품 자료 추가" onClose={() => setModal(null)}><p className={styles.help}>새 자료는 이 작품에만 저장됩니다. 독립 원본은 보관함에서 만들어 연결하세요.</p><StudioButton onClick={() => add("character")}>작품 전용 캐릭터 추가</StudioButton><StudioButton onClick={() => add("lore")}>작품 전용 로어 추가</StudioButton><StudioButton onClick={() => add("scene")}>시작 장면 추가</StudioButton><StudioButton onClick={() => { setConnectQuery(""); setModal("connect"); }}>보관함 원본 연결</StudioButton></StudioDialog>}
    {modal === "connect" && project && <StudioDialog title="보관함 원본 연결" onClose={() => setModal(null)}><p className={styles.help}>원본의 현재 설정을 작품 전용 복사본으로 연결해요. 연결 후 각 작품과 원본은 따로 편집됩니다.</p><label className={styles.search}><Search size={16} /><input aria-label="연결할 원본 검색" placeholder="이름·제목·태그 검색" value={connectQuery} onChange={e => setConnectQuery(e.target.value)} /></label><h3>캐릭터</h3>{workspace.characters.filter(c => matches(connectQuery, [c.name, ...c.tags])).map(c => <StudioButton key={c.id} disabled={project.characters.some(row => row.sourceId === c.id)} onClick={() => connect("character", c.id)}>{c.name}{project.characters.some(row => row.sourceId === c.id) ? " · 연결됨" : " 연결"}</StudioButton>)}<h3>로어북</h3>{workspace.lorebooks.filter(l => matches(connectQuery, [l.title, ...l.tags])).map(l => <StudioButton key={l.id} disabled={project.lorebooks.some(row => row.sourceId === l.id)} onClick={() => connect("lore", l.id)}>{l.title}{project.lorebooks.some(row => row.sourceId === l.id) ? " · 연결됨" : " 연결"}</StudioButton>)}{!workspace.characters.length && !workspace.lorebooks.length && <p className={styles.help}>독립 원본이 없어요. 내 작업실의 캐릭터·로어북 보관함에서 먼저 만들어 주세요.</p>}</StudioDialog>}
    {deleting && <StudioDialog title={deleting.kind.startsWith("work-") ? "작품에서 연결 해제" : "삭제 확인"} onClose={() => setDeleting(null)}><strong>{deleting.label}</strong><p>{deletionImpact}</p><p className={styles.help}>휴지통에서 복구할 수 있습니다. 원본을 복구해도 이미 해제된 작품 연결은 자동으로 복원하지 않습니다.</p><StudioButton onClick={() => setDeleting(null)}>취소</StudioButton><StudioButton className={styles.dangerButton} onClick={remove}>휴지통으로 이동</StudioButton></StudioDialog>}
    {modal === "publish" && project && <StudioDialog title="초안 검토 및 발행" onClose={() => setModal(null)}>
      <strong>{project.work.title || "이름 없는 작품"}</strong><p>캐릭터 {project.characters.length} · 로어 {project.lorebooks.length} · 시작 장면 {project.scenes.length}</p>
      {!project.scenes.length && <p className={styles.error}>시작 장면을 추가해 주세요.</p>}
      {project.characters.filter(c => !c.name.trim() || !c.persona.trim()).map(c => <StudioButton key={c.id} onClick={() => { select("character", c.id); setModal(null); }}>{c.name}: 이름과 성격 확인</StudioButton>)}
      {project.characters.some(c => c.assets.length) && <p className={styles.error}>이미지가 있는 캐릭터는 현재 발행할 수 없어요. 이미지 원본 업로드 연결이 필요합니다.</p>}
      {project.scenes.filter(s => !s.title.trim() || !s.opening.trim() || !s.characterId).map(s => <StudioButton key={s.id} onClick={() => { select("scene", s.id); setModal(null); }}>{s.title}: 제목·도입·캐릭터 확인</StudioButton>)}
      {project.lorebooks.filter(l => !l.title.trim() || !l.content.trim() || (l.enabled && l.activation === "keyword" && !l.keywords.length)).map(l => <StudioButton key={l.id} onClick={() => { select("lore", l.id); setModal(null); }}>{l.title}: 제목·내용·키워드 확인</StudioButton>)}
      <label>실행 모델 <select value={selectedModel} onChange={event => { const id = event.target.value; setSelectedModel(id); setSelectedEffort(models.find(row => row.id === id)?.reasoning_efforts[0] ?? ""); }}><option value="">모델 선택</option>{models.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
      <label>추론 수준 <select value={selectedEffort} onChange={event => setSelectedEffort(event.target.value)}><option value="">수준 선택</option>{models.find(model => model.id === selectedModel)?.reasoning_efforts.map(effort => <option key={effort} value={effort}>{effort}</option>)}</select></label>
      <label>발행 요약 <input value={releaseSummary} maxLength={300} onChange={event => setReleaseSummary(event.target.value)} /></label>
      <label>발행 안내 <textarea value={releaseBody} maxLength={20000} onChange={event => setReleaseBody(event.target.value)} /></label>
      {notice && <p role="status">{notice}</p>}
      {publishedId && <Link href={`/works/${publishedId}`}>발행된 작품 상세 보기</Link>}
      <p className={styles.help}>서버 저장 후 발행합니다. 공개 목록 노출은 관리자 승인과 전체 공개 설정이 필요합니다.</p>
      <StudioButton onClick={() => exportData(project, "studio-draft.json")}>초안 JSON 내보내기</StudioButton>
      <StudioButton disabled={!publishReady || serverBusy} onClick={() => void publishWork()}>{serverBusy ? "발행 중…" : "서버에 발행"}</StudioButton>
    </StudioDialog>}
  </div>;
}
