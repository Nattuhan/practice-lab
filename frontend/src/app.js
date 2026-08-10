import { RegionsPlugin, WaveSurfer, renderIcons } from "./vendor.js";
import { filterLibraryItems, sortLibraryItems } from "./library.js";
import { mutateSectionDraft } from "./section-editor.js";
import { formatBytes } from "./storage.js";

const lucide = { createIcons: renderIcons };

const COLORS = {
  intro: "#94a3b8",
  verse: "#60a5fa",
  "pre-chorus": "#a78bfa",
  chorus: "#f97316",
  bridge: "#34d399",
  outro: "#94a3b8",
};

const LEGACY_SETTINGS_KEY = "music_structure_v1";
const SETTINGS_KEY = "practice_lab_v1";
const SCORE_HISTORY_KEY = "practice_lab_score_history_v1";
const APP_CONFIG = window.PRACTICE_LAB_CONFIG || {};
const DEFAULT_LIBRARY_BASE_URL = "sessions";
const LIBRARY_BASE_URL = (APP_CONFIG.libraryBaseUrl || DEFAULT_LIBRARY_BASE_URL).replace(/\/$/, "");
const STATIC_MANIFEST_URL = APP_CONFIG.manifestUrl || (LIBRARY_BASE_URL ? `${LIBRARY_BASE_URL}/manifest.json` : "");
const STATIC_FOLDERS_URL = APP_CONFIG.foldersUrl || (LIBRARY_BASE_URL ? `${LIBRARY_BASE_URL}/folders.json` : "");
const VIDEO_ASSET_VERSION = "20260517-h264";
const STEM_NAMES = ["vocals", "drums", "bass", "other"];
const DEFAULT_STEM_MIX = { vocals: 100, drums: 100, bass: 100, other: 100 };
const SELECTORS = {
  sidebar: document.getElementById("sidebar"),
  sidebarScrim: document.getElementById("sidebar-scrim"),
  btnMobileLibrary: document.getElementById("btn-mobile-library"),
  sessionPanel: document.getElementById("session-panel"),
  sidebarList: document.getElementById("sidebar-list"),
  sessionSearch: document.getElementById("session-search"),
  sessionFilter: document.getElementById("session-filter"),
  sessionSort: document.getElementById("session-sort"),
  scoreHistoryPanel: document.getElementById("score-history-panel"),
  scoreHistoryList: document.getElementById("score-history-list"),
  contextMenu: document.getElementById("context-menu"),
  queueDock: document.getElementById("queue-dock"),
  queueList: document.getElementById("queue-list"),
  queueCount: document.getElementById("queue-count"),
  btnAddFolder: document.getElementById("btn-add-folder"),
  btnStorage: document.getElementById("btn-storage"),
  storageDialog: document.getElementById("storage-dialog"),
  storageTotal: document.getElementById("storage-total"),
  storageList: document.getElementById("storage-list"),
  sidebarSelectionCount: document.getElementById("sidebar-selection-count"),
  btnDeleteSessionSelection: document.getElementById("btn-delete-session-selection"),
  btnClearSessionSelection: document.getElementById("btn-clear-session-selection"),
  inputCard: document.getElementById("input-card"),
  structureWorkspace: document.getElementById("structure-workspace"),
  playerCard: document.getElementById("player-card"),
  stemPanel: document.getElementById("stem-panel"),
  btnGenerateStems: document.getElementById("btn-generate-stems"),
  btnResetStemMix: document.getElementById("btn-reset-stem-mix"),
  stemExportActions: document.getElementById("stem-export-actions"),
  stemExportScope: document.getElementById("stem-export-scope"),
  stemExportClick: document.getElementById("stem-export-click"),
  btnExportStemMix: document.getElementById("btn-export-stem-mix"),
  stemStatus: document.getElementById("stem-status"),
  stemMixer: document.getElementById("stem-mixer"),
  topbarSong: document.getElementById("topbar-song"),
  topbarActions: document.querySelector(".topbar-actions"),
  offlineBadge: document.getElementById("offline-badge"),
  analyzeBtn: document.getElementById("analyze-btn"),
  btnAudioFile: document.getElementById("btn-audio-file"),
  audioFileInput: document.getElementById("audio-file-input"),
  audioDropHint: document.getElementById("audio-drop-hint"),
  analysisTimeMode: document.getElementById("analysis-time-mode"),
  analysisTimeRange: document.getElementById("analysis-time-range"),
  analysisStartTime: document.getElementById("analysis-start-time"),
  analysisEndTime: document.getElementById("analysis-end-time"),
  status: document.getElementById("status"),
  jobCard: document.getElementById("job-card"),
  jobStage: document.getElementById("job-stage"),
  jobElapsed: document.getElementById("job-elapsed"),
  jobMessage: document.getElementById("job-message"),
  urlInput: document.getElementById("url-input"),
  waveformWrap: document.querySelector(".waveform-wrap"),
  videoPlayer: document.getElementById("video-player"),
  btnVideoFullscreen: document.getElementById("btn-video-fullscreen"),
  btnVideoExit: document.getElementById("btn-video-exit"),
  btnFsPlay: document.getElementById("btn-fs-play"),
  btnFsRestart: document.getElementById("btn-fs-restart"),
  btnFsLoop: document.getElementById("btn-fs-loop"),
  btnFsAutoNext: document.getElementById("btn-fs-auto-next"),
  btnFsMetro: document.getElementById("btn-fs-metro"),
  videoNote: document.getElementById("video-note"),
  btnReanalyze: document.getElementById("btn-reanalyze"),
  btnNewUrl: document.getElementById("btn-new-url"),
  btnAutoNext: document.getElementById("btn-auto-next"),
  btnYouTube: document.getElementById("btn-yt"),
  btnScoreExtractor: document.getElementById("btn-score-extractor"),
  btnCloudSync: document.getElementById("btn-cloud-sync"),
  btnLoop: document.getElementById("btn-loop"),
  btnMetro: document.getElementById("btn-metro"),
  btnBpmHalf: document.getElementById("btn-bpm-half"),
  btnBpmDouble: document.getElementById("btn-bpm-double"),
  btnBpmReset: document.getElementById("btn-bpm-reset"),
  btnBpmSave: document.getElementById("btn-bpm-save"),
  btnClickOffset: document.getElementById("btn-click-offset"),
  btnPlay: document.getElementById("btn-play"),
  btnRestart: document.getElementById("btn-restart"),
  sections: document.getElementById("sections"),
  btnEditSections: document.getElementById("btn-edit-sections"),
  sectionEditor: document.getElementById("section-editor"),
  sectionEditorRows: document.getElementById("section-editor-rows"),
  sectionEditorError: document.getElementById("section-editor-error"),
  btnSaveSections: document.getElementById("btn-save-sections"),
  btnRestoreSections: document.getElementById("btn-restore-sections"),
  metaBpm: document.getElementById("meta-bpm"),
  metaBars: document.getElementById("meta-bars"),
  loopInfo: document.getElementById("loop-info"),
  btnClearRange: document.getElementById("btn-clear-range"),
  timeCur: document.getElementById("time-cur"),
  timeTot: document.getElementById("time-tot"),
  waveform: document.getElementById("waveform"),
  waveformLoading: document.getElementById("waveform-loading"),
  volMusic: document.getElementById("vol-music"),
  volMusicVal: document.getElementById("vol-music-val"),
  volMetro: document.getElementById("vol-metro"),
  volMetroVal: document.getElementById("vol-metro-val"),
  playbackRate: document.getElementById("playback-rate"),
  playbackRateVal: document.getElementById("playback-rate-val"),
  btnSpeedReset: document.getElementById("btn-speed-reset"),
  stemControls: {
    vocals: {
      enabled: document.getElementById("stem-vocals-enabled"),
      solo: document.getElementById("stem-vocals-solo"),
      focus: document.getElementById("stem-vocals-focus"),
      volume: document.getElementById("stem-vocals-volume"),
      value: document.getElementById("stem-vocals-value"),
    },
    drums: {
      enabled: document.getElementById("stem-drums-enabled"),
      solo: document.getElementById("stem-drums-solo"),
      focus: document.getElementById("stem-drums-focus"),
      volume: document.getElementById("stem-drums-volume"),
      value: document.getElementById("stem-drums-value"),
    },
    bass: {
      enabled: document.getElementById("stem-bass-enabled"),
      solo: document.getElementById("stem-bass-solo"),
      focus: document.getElementById("stem-bass-focus"),
      volume: document.getElementById("stem-bass-volume"),
      value: document.getElementById("stem-bass-value"),
    },
    other: {
      enabled: document.getElementById("stem-other-enabled"),
      solo: document.getElementById("stem-other-solo"),
      focus: document.getElementById("stem-other-focus"),
      volume: document.getElementById("stem-other-volume"),
      value: document.getElementById("stem-other-value"),
    },
  },
  audioNote: document.getElementById("audio-note"),
  tabStructure: document.getElementById("tab-structure"),
  tabScore: document.getElementById("tab-score"),
  structurePanel: document.getElementById("structure-panel"),
  scorePanel: document.getElementById("score-panel"),
  scoreFormKicker: document.getElementById("score-form-kicker"),
  scoreFormTitle: document.getElementById("score-form-title"),
  scoreUrlInput: document.getElementById("score-url-input"),
  scoreTitleInput: document.getElementById("score-title-input"),
  scoreRegionPreset: document.getElementById("score-region-preset"),
  scoreRegionPercent: document.getElementById("score-region-percent"),
  scoreTimeMode: document.getElementById("score-time-mode"),
  scoreTimeRange: document.getElementById("score-time-range"),
  scoreStartTime: document.getElementById("score-start-time"),
  scoreEndTime: document.getElementById("score-end-time"),
  scoreTrimStart: document.getElementById("score-trim-start"),
  scoreTrimEnd: document.getElementById("score-trim-end"),
  scoreLayout: document.getElementById("score-layout"),
  scoreProcessingMode: document.getElementById("score-processing-mode"),
  scoreContent: document.getElementById("score-content"),
  scoreVerticalScrollMode: document.getElementById("score-vertical-scroll-mode"),
  scoreHorizontalScrollMode: document.getElementById("score-horizontal-scroll-mode"),
  scoreMeasuresPerRow: document.getElementById("score-measures-per-row"),
  scoreMeasureNumbers: document.getElementById("score-measure-numbers"),
  scoreChordSymbols: document.getElementById("score-chord-symbols"),
  scoreKeyEstimate: document.getElementById("score-key-estimate"),
  scoreBpm: document.getElementById("score-bpm"),
  scorePreviewBtn: document.getElementById("score-preview-btn"),
  scoreExtractBtn: document.getElementById("score-extract-btn"),
  scoreStatus: document.getElementById("score-status"),
  scorePreview: document.getElementById("score-preview"),
  scorePreviewStage: document.getElementById("score-preview-stage"),
  scorePreviewImg: document.getElementById("score-preview-img"),
  scoreRegionBox: document.getElementById("score-region-box"),
  scorePreviewMeta: document.getElementById("score-preview-meta"),
  scoreResultSection: document.getElementById("score-result-section"),
  scoreResultTitleInput: document.getElementById("score-result-title-input"),
  scoreResultStatus: document.getElementById("score-result-status"),
  scoreEditSettingsBtn: document.getElementById("score-edit-settings-btn"),
  scoreRegenerateBtn: document.getElementById("score-regenerate-btn"),
  scoreResult: document.getElementById("score-result"),
};

const setScoreFeatureVisible = visible => {
  SELECTORS.tabScore.hidden = !visible;
  SELECTORS.scorePanel.hidden = true;
};

let ws = null;
let hasServer = false;
let staticLibraryMode = APP_CONFIG.mode === "static";
let currentData = null;
let currentId = null;
let currentSidebarItems = [];
const practicedThisPage = new Set();
let currentPlaybackGroup = null;
let currentJobId = null;
let currentJobStartedAt = null;
let jobPollTimer = null;
let queuePollTimer = null;
const trackedJobs = new Map();
let selectedIdxs = new Set();
let loopOn = false;
let metroOn = false;
let autoNextOn = false;
let bpmFactor = 1;
let clickOffsetHalfBeat = false;
let playingIdx = -1;
let audioAvailable = true;
let audioReady = false;
let videoAvailable = true;
let playbackRate = 1;
let audioCtx = null;
let metroRafId = 0;
let metroGeneration = 0;
let nextBeatIndex = 0;
let metroResumeAtMs = 0;
let lastMetroTime = 0;
let customLoopRange = null;
let waveformSelectionEl = null;
let waveformSectionSelectionEls = [];
let waveformBarGridEls = [];
let waveformDrag = null;
let currentFeature = "structure";
let sidebarItemsCount = 0;
let sharedFolders = null;
let scorePreviewData = null;
let scoreRegion = null;
let scoreRegionDrag = null;
let currentScoreResult = null;
let editingScoreResult = null;
let lastVideoSyncAt = 0;
let videoClickTimer = 0;
let stemPlayers = {};
let stemGainNodes = {};
let stemSourceNodes = {};
let stemReady = false;
let stemsAudible = false;
let lastStemHardSyncAt = 0;
let stemExportInProgress = false;
let selectedSessionIds = new Set();
let lastSelectedSessionId = null;
let sidebarSessionDrag = null;
let suppressSidebarClickUntil = 0;

const isMobileViewport = () => window.matchMedia("(max-width: 680px), (pointer: coarse)").matches;
const closeMobileSidebar = () => {
  document.body.classList.remove("sidebar-open");
  SELECTORS.sidebarScrim.hidden = true;
};
const openMobileSidebar = () => {
  document.body.classList.add("sidebar-open");
  SELECTORS.sidebarScrim.hidden = false;
};

const cfg = () => {
  try {
    const current = JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
    if (Object.keys(current).length > 0) return current;
    const legacy = JSON.parse(localStorage.getItem(LEGACY_SETTINGS_KEY)) || {};
    if (Object.keys(legacy).length > 0) {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(legacy));
      return legacy;
    }
    return {};
  } catch {
    return {};
  }
};

const saveCfg = (key, value) => {
  const valueMap = cfg();
  valueMap[key] = value;
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(valueMap));
};

const bpmCorrectionKey = id => `bpmFactor:${id}`;
const clickOffsetKey = id => `clickOffsetHalfBeat:${id}`;
const foldersKey = "sidebarFolders";
const folderCollapsedKey = "sidebarFolderCollapsed";
const rootOrderKey = "sidebarRootOrder";
const autoNextKey = "autoNext";
const lastStructureSessionKey = "lastStructureSessionId";
const getStoredBpmFactor = id => Number(cfg()[bpmCorrectionKey(id)] ?? 1) || 1;
const getStoredClickOffset = id => !!cfg()[clickOffsetKey(id)];
const getDisplayBpm = item => {
  const value = Number(item?.bpm || 0) * getStoredBpmFactor(item?.id);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
};
const localizeEstimatedKey = value => String(value || "")
  .replace(/ Natural Minor$/u, "マイナー")
  .replace(/ Major$/u, "メジャー")
  .replace(/ Minor$/u, "マイナー");
const scoreOptionEnabled = (data, key) => data?.[key] ?? data?.showMusicalAnalysis ?? true;

const getStoredFolderCollapsed = () => {
  const value = cfg()[folderCollapsedKey];
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
};

const applyStoredFolderCollapsed = folders => {
  const collapsedById = getStoredFolderCollapsed();
  return folders.map(folder => Object.prototype.hasOwnProperty.call(collapsedById, folder.id)
    ? { ...folder, collapsed: !!collapsedById[folder.id] }
    : folder);
};

const saveFolderCollapsed = (folderId, collapsed) => {
  saveCfg(folderCollapsedKey, { ...getStoredFolderCollapsed(), [folderId]: !!collapsed });
};

const forgetFolderCollapsed = folderId => {
  const collapsedById = { ...getStoredFolderCollapsed() };
  delete collapsedById[folderId];
  saveCfg(folderCollapsedKey, collapsedById);
};

const getFolders = () => {
  if (sharedFolders) return applyStoredFolderCollapsed(sharedFolders);
  const value = cfg()[foldersKey];
  return applyStoredFolderCollapsed(Array.isArray(value) ? value : []);
};

const saveFoldersRemote = folders => {
  if (!hasServer || staticLibraryMode) return;
  fetch("/library/folders", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(folders),
  }).catch(() => {});
};

const saveFolders = (folders, { remote = true } = {}) => {
  sharedFolders = folders;
  saveCfg(foldersKey, folders);
  if (remote) saveFoldersRemote(folders);
};
const makeFolderId = () => `folder:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 7)}`;

const cleanFolders = (folders, items) => {
  const validIds = new Set(items.map(item => item.id));
  const used = new Set();
  return folders.map(folder => {
    const sessionIds = (folder.sessionIds || []).filter(id => {
      if (!validIds.has(id) || used.has(id)) return false;
      used.add(id);
      return true;
    });
    return { ...folder, sessionIds };
  });
};

const loadSharedFolders = async () => {
  const localFolders = (() => {
    const value = cfg()[foldersKey];
    return Array.isArray(value) ? value : [];
  })();
  if (!cfg()[folderCollapsedKey] && localFolders.length > 0) {
    saveCfg(folderCollapsedKey, Object.fromEntries(localFolders.map(folder => [folder.id, !!folder.collapsed])));
  }
  const urls = [];
  if (staticLibraryMode) urls.push(STATIC_FOLDERS_URL);
  if (hasServer) urls.push("/library/folders");
  for (const url of urls) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) continue;
      const data = await response.json();
      if (Array.isArray(data)) {
        if (hasServer && data.length === 0 && localFolders.length > 0) {
          sharedFolders = localFolders;
          saveFoldersRemote(localFolders);
        } else {
          sharedFolders = applyStoredFolderCollapsed(data);
          saveCfg(foldersKey, sharedFolders);
        }
        return;
      }
    } catch {}
  }
  sharedFolders = null;
};

const moveSessionToFolder = (sessionId, folderId, items) => {
  const folders = cleanFolders(getFolders(), items).map(folder => ({
    ...folder,
    sessionIds: (folder.sessionIds || []).filter(id => id !== sessionId),
  }));
  const target = folders.find(folder => folder.id === folderId);
  if (target) target.sessionIds.unshift(sessionId);
  saveFolders(folders);
  renderSidebar(items);
};

const getRootOrder = (items, folderedIds) => {
  const looseIds = items.map(item => item.id).filter(id => !folderedIds.has(id));
  const looseSet = new Set(looseIds);
  const saved = Array.isArray(cfg()[rootOrderKey]) ? cfg()[rootOrderKey] : [];
  const ordered = saved.filter(id => looseSet.has(id));
  for (const id of looseIds) {
    if (!ordered.includes(id)) ordered.push(id);
  }
  return ordered;
};

const getSidebarOrderedSessionIds = items => {
  const folders = cleanFolders(getFolders(), items);
  const folderedIds = new Set(folders.flatMap(folder => folder.sessionIds || []));
  return [
    ...folders.flatMap(folder => folder.sessionIds || []),
    ...getRootOrder(items, folderedIds),
  ];
};

const updateSidebarSelectionUI = () => {
  document.querySelectorAll(".si").forEach(row => {
    const selected = selectedSessionIds.has(row.dataset.id);
    row.classList.toggle("selected", selected);
    row.setAttribute("aria-selected", String(selected));
  });
  const count = selectedSessionIds.size;
  SELECTORS.sidebarSelectionCount.hidden = count === 0;
  SELECTORS.sidebarSelectionCount.textContent = `${count}件選択中`;
  SELECTORS.btnDeleteSessionSelection.hidden = count === 0 || !hasServer;
  SELECTORS.btnClearSessionSelection.hidden = count === 0;
};

const toggleSessionSelection = (sessionId, items, { range = false } = {}) => {
  if (range && lastSelectedSessionId) {
    const order = getSidebarOrderedSessionIds(items);
    const anchorIndex = order.indexOf(lastSelectedSessionId);
    const targetIndex = order.indexOf(sessionId);
    if (anchorIndex >= 0 && targetIndex >= 0) {
      const start = Math.min(anchorIndex, targetIndex);
      const end = Math.max(anchorIndex, targetIndex);
      for (const id of order.slice(start, end + 1)) selectedSessionIds.add(id);
    }
  } else if (selectedSessionIds.has(sessionId)) {
    selectedSessionIds.delete(sessionId);
  } else {
    selectedSessionIds.add(sessionId);
  }
  lastSelectedSessionId = sessionId;
  updateSidebarSelectionUI();
};

const clearSidebarDropMarkers = () => {
  document.querySelectorAll(".si.drop-before, .si.drop-after, .si.dragging").forEach(row => {
    row.classList.remove("drop-before", "drop-after", "dragging");
  });
  document.querySelectorAll(".sf.drop, .sf.drop-before, .sf.drop-after, .sf.dragging").forEach(group => {
    group.classList.remove("drop", "drop-before", "drop-after", "dragging");
  });
};

const hasDragType = (event, type) => Array.from(event.dataTransfer?.types || []).includes(type);

const reorderSessions = (sessionIds, targetId, containerId, items, { after = false } = {}) => {
  const movingSet = new Set(sessionIds || []);
  const moving = getSidebarOrderedSessionIds(items).filter(id => movingSet.has(id));
  if (!moving.length || movingSet.has(targetId)) return;
  const originalFolders = cleanFolders(getFolders(), items);
  const originalFolderedIds = new Set(originalFolders.flatMap(folder => folder.sessionIds || []));
  const originalRootOrder = getRootOrder(items, originalFolderedIds);
  const folders = originalFolders.map(folder => ({
    ...folder,
    sessionIds: (folder.sessionIds || []).filter(id => !movingSet.has(id)),
  }));

  if (containerId === "root") {
    const order = originalRootOrder.filter(id => !movingSet.has(id));
    const targetIndex = targetId ? order.indexOf(targetId) : -1;
    const insertAt = targetIndex >= 0 ? targetIndex + (after ? 1 : 0) : order.length;
    order.splice(insertAt, 0, ...moving);
    saveCfg(rootOrderKey, order);
  } else {
    const target = folders.find(folder => folder.id === containerId);
    if (!target) return;
    const ids = target.sessionIds || [];
    const targetIndex = targetId ? ids.indexOf(targetId) : -1;
    const insertAt = targetIndex >= 0 ? targetIndex + (after ? 1 : 0) : ids.length;
    ids.splice(insertAt, 0, ...moving);
    target.sessionIds = ids;
    saveCfg(rootOrderKey, originalRootOrder.filter(id => !movingSet.has(id)));
  }

  saveFolders(folders);
  renderSidebar(items);
};

const getDraggedSessionIds = event => {
  try {
    const value = JSON.parse(event.dataTransfer.getData("application/x-practice-lab-sessions") || "[]");
    if (Array.isArray(value) && value.length) return value;
  } catch {}
  const sessionId = event.dataTransfer.getData("application/x-practice-lab-session") || event.dataTransfer.getData("text/plain");
  return sessionId ? [sessionId] : [];
};

const updatePointerSessionDropTarget = (clientX, clientY) => {
  if (!sidebarSessionDrag?.active) return;
  document.querySelectorAll(".si.drop-before, .si.drop-after").forEach(row => {
    row.classList.remove("drop-before", "drop-after");
  });
  document.querySelectorAll(".sf.drop").forEach(group => group.classList.remove("drop"));
  const element = document.elementFromPoint(clientX, clientY);
  const row = element?.closest?.(".si");
  if (row && !sidebarSessionDrag.sessionIds.includes(row.dataset.id)) {
    const rect = row.getBoundingClientRect();
    const after = clientY > rect.top + rect.height / 2;
    row.classList.toggle("drop-before", !after);
    row.classList.toggle("drop-after", after);
    sidebarSessionDrag.target = {
      targetId: row.dataset.id,
      containerId: row.dataset.containerId || "root",
      after,
    };
    return;
  }
  const group = element?.closest?.(".sf");
  if (group) {
    group.classList.add("drop");
    sidebarSessionDrag.target = {
      targetId: null,
      containerId: group.classList.contains("sf-root") ? "root" : group.dataset.folderId,
      after: false,
    };
    return;
  }
  sidebarSessionDrag.target = null;
};

const finishSidebarSessionDrag = pointerId => {
  const drag = sidebarSessionDrag;
  if (!drag || drag.pointerId !== pointerId) return;
  if (drag.active && drag.target) {
    reorderSessions(drag.sessionIds, drag.target.targetId, drag.target.containerId, drag.items, {
      after: drag.target.after,
    });
  }
  if (drag.active) suppressSidebarClickUntil = performance.now() + 300;
  sidebarSessionDrag = null;
  clearSidebarDropMarkers();
};

const finishPointerSessionDrag = event => {
  if (sidebarSessionDrag?.active) updatePointerSessionDropTarget(event.clientX, event.clientY);
  finishSidebarSessionDrag(event.pointerId);
};
document.addEventListener("pointerup", finishPointerSessionDrag);
document.addEventListener("pointercancel", finishPointerSessionDrag);
document.addEventListener("mouseup", event => {
  if (sidebarSessionDrag?.active) {
    updatePointerSessionDropTarget(event.clientX, event.clientY);
    finishSidebarSessionDrag(sidebarSessionDrag.pointerId);
  }
});

const reorderFolder = (folderId, targetId, items, { after = false } = {}) => {
  if (!folderId || folderId === targetId) return;
  const folders = cleanFolders(getFolders(), items);
  const moving = folders.find(folder => folder.id === folderId);
  if (!moving) return;
  const next = folders.filter(folder => folder.id !== folderId);
  const targetIndex = targetId ? next.findIndex(folder => folder.id === targetId) : -1;
  const insertAt = targetIndex >= 0 ? targetIndex + (after ? 1 : 0) : next.length;
  next.splice(insertAt, 0, moving);
  saveFolders(next);
  renderSidebar(items);
};

const buildPlaybackGroups = items => {
  const folders = cleanFolders(getFolders(), items);
  const itemById = new Map(items.map(item => [item.id, item]));
  const folderedIds = new Set(folders.flatMap(folder => folder.sessionIds || []));
  const groups = [];
  for (const folder of folders) {
    const orderedItems = (folder.sessionIds || []).map(id => itemById.get(id)).filter(Boolean);
    if (orderedItems.length) groups.push({ id: folder.id, name: folder.name, items: orderedItems });
  }
  const rootItems = getRootOrder(items, folderedIds).map(id => itemById.get(id)).filter(Boolean);
  if (rootItems.length) groups.push({ id: "root", name: "未分類", items: rootItems });
  return groups;
};

const findPlaybackGroupForSession = (sessionId, items = currentSidebarItems) =>
  buildPlaybackGroups(items).find(group => group.items.some(item => item.id === sessionId)) || null;

const playNextInGroup = async () => {
  if (!autoNextOn || loopOn || !currentId) return false;
  const group = findPlaybackGroupForSession(currentId, currentSidebarItems);
  if (!group) return false;
  const index = group.items.findIndex(item => item.id === currentId);
  const next = index >= 0 ? group.items[index + 1] : null;
  if (!next) return false;
  await loadResult(next, { autoplay: true });
  return true;
};

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[char]));

const hideContextMenu = () => {
  if (!SELECTORS.contextMenu) return;
  SELECTORS.contextMenu.hidden = true;
  SELECTORS.contextMenu.innerHTML = "";
};

const showContextMenu = (event, actions) => {
  if (!SELECTORS.contextMenu || actions.length === 0) return;
  event.preventDefault();
  event.stopPropagation();
  SELECTORS.contextMenu.innerHTML = "";
  for (const action of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.className = action.danger ? "danger" : "";
    button.onclick = () => {
      hideContextMenu();
      action.run();
    };
    SELECTORS.contextMenu.appendChild(button);
  }
  SELECTORS.contextMenu.hidden = false;
  const menuRect = SELECTORS.contextMenu.getBoundingClientRect();
  const left = Math.min(event.clientX, window.innerWidth - menuRect.width - 8);
  const top = Math.min(event.clientY, window.innerHeight - menuRect.height - 8);
  SELECTORS.contextMenu.style.left = `${Math.max(8, left)}px`;
  SELECTORS.contextMenu.style.top = `${Math.max(8, top)}px`;
};

const mergeLibraryMetadata = (sessionId, updated) => {
  const metadata = {
    tags: Array.isArray(updated.tags) ? updated.tags : [],
    lastPracticedAt: updated.lastPracticedAt || null,
    practiceCount: Number(updated.practiceCount || 0),
  };
  currentSidebarItems = currentSidebarItems.map(item => item.id === sessionId ? { ...item, ...metadata } : item);
  if (currentData?.id === sessionId) currentData = { ...currentData, ...metadata };
  renderSidebar(currentSidebarItems);
};

const saveLibraryMetadata = async (sessionId, payload) => {
  const response = await fetch(`/results/${encodeURIComponent(sessionId)}/library`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const updated = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(updated.detail || "ライブラリ情報を保存できませんでした");
  mergeLibraryMetadata(sessionId, updated);
  return updated;
};

const editSessionTags = async item => {
  const value = prompt("タグをカンマ区切りで入力", (item.tags || []).join(", "));
  if (value === null) return;
  const tags = value.split(/[,、]/).map(tag => tag.trim()).filter(Boolean);
  try {
    await saveLibraryMetadata(item.id, { tags });
  } catch (error) {
    alert(error.message);
  }
};

const markCurrentSessionPracticed = () => {
  if (!hasServer || staticLibraryMode || !currentId || practicedThisPage.has(currentId)) return;
  practicedThisPage.add(currentId);
  saveLibraryMetadata(currentId, { played: true }).catch(() => practicedThisPage.delete(currentId));
};

const createSessionRow = (item, items, containerId = "root") => {
  const row = document.createElement("div");
  row.className = "si";
  row.dataset.id = item.id;
  row.dataset.date = item.date || "";
  row.dataset.containerId = containerId;
  row.draggable = false;
  const tags = Array.isArray(item.tags) ? item.tags : [];
  const practiced = item.lastPracticedAt ? "練習済み" : "未練習";
  row.innerHTML = `<div class="si-body"><div class="si-title">${escapeHtml(item.title)}</div><div class="si-meta">♩${escapeHtml(getDisplayBpm(item))} · ${escapeHtml(item.date)} · ${practiced}${tags.length ? ` · <span class="si-tags">${escapeHtml(tags.join(" / "))}</span>` : ""}</div></div>`;
  row.addEventListener("pointerdown", event => {
    if (!hasServer || event.button !== 0 || event.pointerType === "touch" || event.ctrlKey || event.metaKey || event.shiftKey) return;
    sidebarSessionDrag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      active: false,
      target: null,
      items,
      itemId: item.id,
      sessionIds: [],
    };
    row.setPointerCapture?.(event.pointerId);
  });
  row.addEventListener("pointermove", event => {
    const drag = sidebarSessionDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (!drag.active && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) >= 6) {
      if (!selectedSessionIds.has(drag.itemId)) {
        selectedSessionIds = new Set([drag.itemId]);
        lastSelectedSessionId = drag.itemId;
        updateSidebarSelectionUI();
      }
      drag.sessionIds = getSidebarOrderedSessionIds(items).filter(id => selectedSessionIds.has(id));
      drag.active = true;
      document.querySelectorAll(".si").forEach(element => {
        if (selectedSessionIds.has(element.dataset.id)) element.classList.add("dragging");
      });
    }
    if (!drag.active) return;
    event.preventDefault();
    updatePointerSessionDropTarget(event.clientX, event.clientY);
  });
  row.addEventListener("pointerup", finishPointerSessionDrag);
  row.addEventListener("pointercancel", finishPointerSessionDrag);
  row.onclick = event => {
    if (performance.now() < suppressSidebarClickUntil) return;
    if (event.ctrlKey || event.metaKey || event.shiftKey) {
      if (!selectedSessionIds.size && currentId && currentId !== item.id && items.some(entry => entry.id === currentId)) {
        selectedSessionIds.add(currentId);
        lastSelectedSessionId = currentId;
      }
      toggleSessionSelection(item.id, items, { range: event.shiftKey });
      return;
    }
    if (selectedSessionIds.size) {
      selectedSessionIds.clear();
      lastSelectedSessionId = null;
      updateSidebarSelectionUI();
    }
    loadResult(item, { autoplay: true });
    closeMobileSidebar();
  };
  if (hasServer) {
    row.addEventListener("contextmenu", event => {
      showContextMenu(event, [
        { label: "名前を変更", run: () => renameSession(item, items) },
        { label: "タグを編集", run: () => editSessionTags(item) },
        { label: "削除", danger: true, run: () => deleteResult(item.id, items) },
      ]);
    });
  }
  return row;
};

const fmt = seconds =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

const staticAssetUrl = (sessionId, filename) =>
  LIBRARY_BASE_URL ? `${LIBRARY_BASE_URL}/${sessionId}/${filename}` : "";

const versionedVideoUrl = url => {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${VIDEO_ASSET_VERSION}`;
};

const sessionAssets = session => {
  const hasExplicitVideo = !!session?.assets && Object.prototype.hasOwnProperty.call(session.assets, "video");
  if (!staticLibraryMode) {
    return {
      result: `results/${session.id}.json`,
      audio: `audio/${session.id}.mp3`,
      video: hasExplicitVideo
        ? (session.assets.video ? versionedVideoUrl(session.assets.video) : "")
        : versionedVideoUrl(`video/${session.id}.mp4`),
      stems: session?.assets?.stems || null,
    };
  }
  const staticVideo = hasExplicitVideo
    ? session.assets.video
    : staticAssetUrl(session.id, "video.mp4");
  return {
    result: session?.assets?.result || staticAssetUrl(session.id, "session.json"),
    audio: session?.assets?.audio || staticAssetUrl(session.id, "audio.mp3"),
    video: staticVideo ? versionedVideoUrl(staticVideo) : "",
    stems: session?.assets?.stems || null,
  };
};

const MIN_PLAYBACK_RATE = 0.25;
const MAX_PLAYBACK_RATE = 1.25;
const PLAYBACK_RATE_STEP = 0.05;
const DEFAULT_PLAYBACK_RATE = 1;
const clampPlaybackRate = value => Math.min(MAX_PLAYBACK_RATE, Math.max(MIN_PLAYBACK_RATE, Number(value) || DEFAULT_PLAYBACK_RATE));
const formatPlaybackRate = value => `${clampPlaybackRate(value).toFixed(2)}x`;
const getStemMix = () => ({ ...DEFAULT_STEM_MIX, ...(cfg().stemMix || {}) });
const saveStemMix = mix => saveCfg("stemMix", mix);
const getStemLastVolumes = () => ({ ...DEFAULT_STEM_MIX, ...(cfg().stemLastVolume || {}) });
const saveStemLastVolumes = volumes => saveCfg("stemLastVolume", volumes);
const getStemMixMode = () => {
  const mode = cfg().stemMixMode;
  return STEM_NAMES.includes(mode?.stem) && ["solo", "focus"].includes(mode?.type) ? mode : null;
};
const clearStemMixMode = () => {
  saveCfg("stemMixMode", null);
  saveCfg("stemMixRestore", null);
};
const setStemMixMode = (stem, type) => {
  const currentMode = getStemMixMode();
  if (currentMode?.stem === stem && currentMode.type === type) {
    saveStemMix({ ...DEFAULT_STEM_MIX, ...(cfg().stemMixRestore || {}) });
    clearStemMixMode();
    applyStemMix();
    return;
  }
  if (!currentMode) saveCfg("stemMixRestore", getStemMix());
  saveCfg("stemMixMode", { stem, type });
  saveStemMix(Object.fromEntries(STEM_NAMES.map(name => [name, name === stem ? 100 : (type === "focus" ? 20 : 0)])));
  applyStemMix();
};
const hasStemAssets = assets =>
  !!assets?.stems && STEM_NAMES.every(stem => typeof assets.stems[stem] === "string" && assets.stems[stem]);
const STEM_SYNC_DRIFT_SECONDS = 0.45;
const STEM_SYNC_COOLDOWN_MS = 1200;

const destroyStemPlayers = () => {
  for (const player of Object.values(stemPlayers)) {
    player.pause();
    player.removeAttribute("src");
    player.load();
  }
  for (const node of Object.values(stemGainNodes)) node.disconnect();
  for (const node of Object.values(stemSourceNodes)) node.disconnect();
  stemPlayers = {};
  stemGainNodes = {};
  stemSourceNodes = {};
  stemReady = false;
  stemsAudible = false;
};

const applyStemMix = () => {
  const mix = getStemMix();
  const mode = getStemMixMode();
  const effectiveMusicValue = isMobileViewport() ? 100 : SELECTORS.volMusic.value;
  const masterVolume = Math.min(1, Math.max(0, (Number(effectiveMusicValue) || 0) / 100));
  for (const stem of STEM_NAMES) {
    const value = Math.min(100, Math.max(0, Number(mix[stem] ?? DEFAULT_STEM_MIX[stem])));
    const controls = SELECTORS.stemControls[stem];
    if (controls) {
      controls.volume.value = String(value);
      controls.enabled.classList.toggle("active", value === 0);
      controls.enabled.setAttribute("aria-pressed", String(value === 0));
      const stemLabel = { vocals: "ボーカル", drums: "ドラム", bass: "ベース", other: "その他" }[stem] || stem;
      controls.enabled.title = value === 0 ? `${stemLabel}のミュートを解除` : `${stemLabel}をミュート`;
      controls.enabled.setAttribute("aria-label", controls.enabled.title);
      const soloActive = mode?.type === "solo" && mode.stem === stem;
      const focusActive = mode?.type === "focus" && mode.stem === stem;
      controls.solo.classList.toggle("active", soloActive);
      controls.solo.setAttribute("aria-pressed", String(soloActive));
      controls.focus.classList.toggle("active", focusActive);
      controls.focus.setAttribute("aria-pressed", String(focusActive));
      controls.value.textContent = `${value}%`;
    }
    const gain = stemGainNodes[stem];
    if (gain) gain.gain.value = masterVolume * (value / 100);
    const player = stemPlayers[stem];
    if (player) player.volume = masterVolume * (value / 100);
  }
};

const updateStemExportScopeAvailability = () => {
  if (!SELECTORS.stemExportScope) return;
  const selectionOption = SELECTORS.stemExportScope.querySelector('option[value="selection"]');
  const hasSelection = !!getLoopRange();
  if (selectionOption) selectionOption.disabled = !hasSelection;
  if (!hasSelection && SELECTORS.stemExportScope.value === "selection") {
    SELECTORS.stemExportScope.value = "full";
  }
};

const safeDownloadName = value => String(value || "practice")
  .replace(/[\\/:*?"<>|]+/g, " ")
  .replace(/\s+/g, " ")
  .trim()
  .slice(0, 80) || "practice";

const stemMixFilename = (title, stemVolumes, { selection = false, click = false } = {}) => {
  const base = safeDownloadName(title);
  const enabled = STEM_NAMES.filter(stem => Number(stemVolumes[stem]) > 0);
  const disabled = STEM_NAMES.filter(stem => !enabled.includes(stem));
  let stemSuffix = "";
  if (enabled.length === 1) stemSuffix = `_only_${enabled[0]}`;
  else if (enabled.length === 2) stemSuffix = `_${enabled.join("_")}`;
  else if (disabled.length === 1) stemSuffix = `_no_${disabled[0]}`;
  const rangeSuffix = selection ? "_selection" : "";
  const clickSuffix = click ? "_click" : "";
  return `${base}${stemSuffix}${rangeSuffix}${clickSuffix}.mp3`;
};

const exportStemMix = async () => {
  if (!currentId || !hasServer || stemExportInProgress) return;
  const stemVolumes = getStemMix();
  if (!STEM_NAMES.some(stem => Number(stemVolumes[stem]) > 0)) {
    SELECTORS.stemStatus.className = "stem-status err";
    SELECTORS.stemStatus.textContent = "少なくとも1つのパートを有効にしてください";
    return;
  }
  const range = SELECTORS.stemExportScope.value === "selection" ? getLoopRange() : null;
  if (SELECTORS.stemExportScope.value === "selection" && !range) {
    SELECTORS.stemStatus.className = "stem-status err";
    SELECTORS.stemStatus.textContent = "先に範囲を選択してください";
    return;
  }
  const includeClick = SELECTORS.stemExportClick.checked;
  const rangeStart = range?.start ?? 0;
  const rangeEnd = range?.end ?? Infinity;
  const clickTimes = includeClick
    ? getAdjustedBeats()
      .filter(time => time >= rangeStart && time <= rangeEnd)
      .map(time => time - rangeStart)
    : [];
  const downloadName = stemMixFilename(currentData?.title || currentId, stemVolumes, {
    selection: !!range,
    click: includeClick,
  });

  stemExportInProgress = true;
  SELECTORS.btnExportStemMix.disabled = true;
  SELECTORS.stemStatus.className = "stem-status";
  SELECTORS.stemStatus.innerHTML = `<span class="spin"></span>書き出しを処理一覧へ追加中`;
  try {
    const response = await fetch(`/results/${encodeURIComponent(currentId)}/stems/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        stemVolumes,
        startSec: range?.start ?? null,
        endSec: range?.end ?? null,
        clickTimes,
        clickVolume: includeClick ? Number(SELECTORS.volMetro.value) : 0,
        outputFilename: downloadName,
      }),
    });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `書き出しに失敗しました (${response.status})`);
    trackQueuedJob(submitted.jobId, {
      label: `パート書き出し · ${currentData?.title || currentId}`,
      kind: "stem-export",
      retainDone: true,
      onError: error => {
        SELECTORS.stemStatus.className = "stem-status err";
        SELECTORS.stemStatus.textContent = error.message;
      },
    });
    SELECTORS.stemStatus.className = "stem-status ok";
    SELECTORS.stemStatus.textContent = "書き出しを追加しました。完了後に処理一覧からダウンロードできます";
  } catch (error) {
    SELECTORS.stemStatus.className = "stem-status err";
    SELECTORS.stemStatus.textContent = error.message;
  } finally {
    stemExportInProgress = false;
    SELECTORS.btnExportStemMix.disabled = false;
  }
};

const syncStemPlayers = (time = ws?.getCurrentTime?.() ?? 0, { force = false } = {}) => {
  if (!stemReady) return;
  const now = performance.now();
  for (const player of Object.values(stemPlayers)) {
    if (Math.abs(player.playbackRate - playbackRate) > 0.001) player.playbackRate = playbackRate;
    const drift = Math.abs(player.currentTime - time);
    if (force || (drift > STEM_SYNC_DRIFT_SECONDS && now - lastStemHardSyncAt > STEM_SYNC_COOLDOWN_MS)) {
      player.currentTime = time;
      lastStemHardSyncAt = now;
    }
  }
};

const playStems = () => {
  if (!stemReady) return Promise.resolve(false);
  lastStemHardSyncAt = 0;
  syncStemPlayers(ws?.getCurrentTime?.() ?? 0, { force: true });
  return Promise.allSettled(Object.values(stemPlayers).map(player => player.play()))
    .then(results => {
      stemsAudible = results.some(result => result.status === "fulfilled");
      applyMusicVolume(SELECTORS.volMusic.value);
      if (!stemsAudible) {
        SELECTORS.stemStatus.className = "stem-status err";
        const rejected = results.find(result => result.status === "rejected");
        SELECTORS.stemStatus.textContent = rejected?.reason?.message || "パート再生がブロックされました";
      } else {
        SELECTORS.stemStatus.className = "stem-status ok";
        SELECTORS.stemStatus.textContent = "準備完了";
      }
      return stemsAudible;
    });
};

const pauseStems = () => {
  for (const player of Object.values(stemPlayers)) player.pause();
  stemsAudible = false;
};

const applyMusicVolume = value => {
  const effectiveValue = isMobileViewport() ? 100 : value;
  const volume = Math.min(1, Math.max(0, (Number(effectiveValue) || 0) / 100));
  ws?.setVolume(stemReady ? 0 : volume);
  SELECTORS.videoPlayer.volume = volume;
  applyStemMix();
};

const preserveMediaPitch = media => {
  if (!media) return;
  media.preservesPitch = true;
  media.mozPreservesPitch = true;
  media.webkitPreservesPitch = true;
};

const applyPlaybackRate = value => {
  playbackRate = clampPlaybackRate(value);
  SELECTORS.playbackRate.value = playbackRate.toFixed(2);
  SELECTORS.playbackRateVal.textContent = formatPlaybackRate(playbackRate);
  saveCfg("playbackRate", playbackRate);
  ws?.setPlaybackRate?.(playbackRate, true);
  preserveMediaPitch(ws?.getMediaElement?.());
  preserveMediaPitch(SELECTORS.videoPlayer);
  SELECTORS.videoPlayer.playbackRate = playbackRate;
  syncStemPlayers(ws?.getCurrentTime?.() ?? 0);
};

const nudgePlaybackRate = delta => {
  const next = Math.round((playbackRate + delta) / PLAYBACK_RATE_STEP) * PLAYBACK_RATE_STEP;
  applyPlaybackRate(next);
};

const applyCurrentPlaybackRate = () => {
  ws?.setPlaybackRate?.(playbackRate, true);
  preserveMediaPitch(ws?.getMediaElement?.());
  preserveMediaPitch(SELECTORS.videoPlayer);
  SELECTORS.videoPlayer.playbackRate = playbackRate;
  syncStemPlayers(ws?.getCurrentTime?.() ?? 0);
};

const syncVideoToAudio = (time, { force = false } = {}) => {
  if (!videoAvailable || !SELECTORS.videoPlayer.src) return;
  const video = SELECTORS.videoPlayer;
  if (video.readyState < 1) return;
  const now = performance.now();
  const minInterval = isMobileViewport() ? 900 : 450;
  if (!force && now - lastVideoSyncAt < minInterval) return;
  lastVideoSyncAt = now;
  const drift = Math.abs(video.currentTime - time);
  const threshold = isMobileViewport() ? 0.42 : 0.22;
  if (force || drift > threshold) video.currentTime = time;
};

const playVideo = () => {
  if (!videoAvailable || !SELECTORS.videoPlayer.src) return;
  SELECTORS.videoPlayer.play().catch(() => {});
};

const pauseVideo = () => {
  if (!SELECTORS.videoPlayer.src) return;
  SELECTORS.videoPlayer.pause();
};

const setVideoFullscreen = enabled => {
  if (enabled && (!videoAvailable || !SELECTORS.videoPlayer.src)) return;
  document.body.classList.toggle("video-fullscreen-mode", enabled);
};

const toggleVideoFullscreen = () => {
  setVideoFullscreen(!document.body.classList.contains("video-fullscreen-mode"));
};

const setActiveTab = tab => {
  if (staticLibraryMode && tab === "score") tab = "structure";
  const scoreActive = tab === "score";
  currentFeature = scoreActive ? "score" : "structure";
  if (scoreActive && ws?.isPlaying()) ws.pause();
  SELECTORS.tabStructure.classList.toggle("active", !scoreActive);
  SELECTORS.tabScore.classList.toggle("active", scoreActive);
  SELECTORS.structurePanel.hidden = scoreActive;
  SELECTORS.scorePanel.hidden = !scoreActive;
  SELECTORS.sessionPanel.hidden = scoreActive || sidebarItemsCount === 0;
  SELECTORS.scoreHistoryPanel.hidden = !scoreActive;
  SELECTORS.topbarSong.hidden = scoreActive || !currentId;
  SELECTORS.topbarActions.hidden = scoreActive || !currentId;
};

const getScoreHistory = () => {
  try {
    const history = JSON.parse(localStorage.getItem(SCORE_HISTORY_KEY) || "[]");
    return Array.isArray(history) ? history : [];
  } catch {
    return [];
  }
};

const renderScoreHistory = () => {
  if (!SELECTORS.scoreHistoryList) return;
  const history = getScoreHistory();
  if (!history.length) {
    SELECTORS.scoreHistoryList.innerHTML = `<div class="score-history-empty">抽出が完了した楽譜がここに表示されます。</div>`;
    return;
  }
  SELECTORS.scoreHistoryList.innerHTML = history.map(item => {
    const result = item.result || {};
    const title = result.title || result.videoId || "抽出済み楽譜";
    const previewOutputs = Array.isArray(result.pageOutputs) && result.pageOutputs.length
      ? result.pageOutputs
      : result.outputs;
    const pages = Array.isArray(previewOutputs) ? previewOutputs.length : 0;
    const sheets = result.layout === "a3_2up" && Array.isArray(result.outputs)
      ? result.outputs.length
      : 0;
    const measures = Number(result.labeledMeasures || 0);
    const musical = result.musicalAnalysis || {};
    const date = item.completedAt ? new Date(item.completedAt).toLocaleString() : "";
    return `<div class="score-history-item" data-score-history-id="${escapeHtml(item.id)}" tabindex="0" role="button">
      <div class="score-history-actions">
        <button class="score-history-action score-history-edit" type="button" data-score-history-edit="${escapeHtml(item.id)}" aria-label="設定を変えて再生成" title="設定を変えて再生成"><i data-lucide="settings-2"></i></button>
        <button class="score-history-action score-history-regenerate" type="button" data-score-history-regenerate="${escapeHtml(item.id)}" aria-label="同じ設定で再生成" title="同じ設定で再生成"><i data-lucide="refresh-cw"></i></button>
        <button class="score-history-action score-history-remove" type="button" data-score-history-remove="${escapeHtml(item.id)}" aria-label="履歴から削除" title="履歴から削除">×</button>
      </div>
      <div class="score-history-title" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
      <div class="score-history-meta">${measures ? `${measures}小節 · ` : ""}${pages}ページ${sheets ? ` · A3 ${sheets}枚` : ""}${scoreOptionEnabled(result, "showBpm") && musical.bpm ? ` · BPM ${escapeHtml(musical.bpm)}` : ""}${scoreOptionEnabled(result, "showKeyEstimate") && musical.key ? ` · 推定キー ${escapeHtml(localizeEstimatedKey(musical.key))}` : ""}</div>
      <div class="score-history-date">${escapeHtml(date)}</div>
    </div>`;
  }).join("");
  window.lucide?.createIcons();
};

const saveScoreHistory = result => {
  if (!result?.videoId || !Array.isArray(result.outputs)) return;
  const history = getScoreHistory().filter(item => item.result?.videoId !== result.videoId);
  history.unshift({
    id: `${result.videoId}-${Date.now()}`,
    completedAt: Date.now(),
    result,
  });
  localStorage.setItem(SCORE_HISTORY_KEY, JSON.stringify(history.slice(0, 30)));
  renderScoreHistory();
};

const removeScoreHistory = id => {
  const history = getScoreHistory().filter(item => item.id !== id);
  localStorage.setItem(SCORE_HISTORY_KEY, JSON.stringify(history));
  renderScoreHistory();
};

const updateScoreHistoryResult = (id, result) => {
  const history = getScoreHistory();
  const index = history.findIndex(item => item.id === id);
  if (index < 0) return;
  history[index] = { ...history[index], result };
  localStorage.setItem(SCORE_HISTORY_KEY, JSON.stringify(history));
};

const fetchLatestScoreResult = async result => {
  if (!result?.videoId) return result;
  try {
    const response = await fetch(`/score/${encodeURIComponent(result.videoId)}/metadata.json?t=${Date.now()}`, {
      cache: "no-store",
    });
    if (!response.ok) return result;
    const latest = await response.json();
    return Array.isArray(latest?.outputs) ? latest : result;
  } catch {
    return result;
  }
};

const scoreRegenerationPayload = data => ({
  url: `https://www.youtube.com/watch?v=${data.videoId}`,
  title: data.title || null,
  startSec: data.startSec ?? null,
  endSec: data.endSec ?? null,
  region: data.region,
  trimStartFrames: Number(data.trimStartFrames || 0),
  trimEndFrames: Number(data.trimEndFrames || 0),
  layout: data.layout || "a3_2up",
  processingMode: data.processingMode || "auto",
  scoreContent: data.scoreContent || "tab",
  verticalScrollMode: data.verticalScrollMode || "auto",
  horizontalScrollMode: data.horizontalScrollMode || "auto",
  measuresPerRow: Number(data.measuresPerRow || 4),
  showMeasureNumbers: !!data.showMeasureNumbers,
  showChordSymbols: scoreOptionEnabled(data, "showChordSymbols"),
  showKeyEstimate: scoreOptionEnabled(data, "showKeyEstimate"),
  showBpm: scoreOptionEnabled(data, "showBpm"),
});

const regenerateScore = async (data = currentScoreResult) => {
  if (!data?.videoId || !data?.region) return;
  const editedTitle = SELECTORS.scoreResultTitleInput.value.trim();
  const regenerationData = { ...data, title: editedTitle || data.title };
  currentScoreResult = regenerationData;
  SELECTORS.scoreResultSection.hidden = false;
  SELECTORS.scoreResultTitleInput.value = regenerationData.title || data.videoId || "";
  SELECTORS.scoreRegenerateBtn.disabled = true;
  SELECTORS.scoreResultStatus.className = "score-status score-result-status";
  SELECTORS.scoreResultStatus.innerHTML = `<span class="spin"></span>同じ設定で再生成を追加しています...`;
  try {
    const response = await fetch("/score/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scoreRegenerationPayload(regenerationData)),
    });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `サーバーエラー (${response.status})`);
    trackQueuedJob(submitted.jobId, {
      label: `楽譜を再生成 · ${data.videoId}`,
      kind: "score-extract",
      retainDone: true,
      onDone: result => {
        saveScoreHistory(result);
        if (currentScoreResult?.videoId === result.videoId) renderScoreOutputs(result);
      },
    });
    SELECTORS.scoreResultStatus.className = "score-status score-result-status ok";
    SELECTORS.scoreResultStatus.textContent = "再生成を処理一覧へ追加しました。完了後にこの楽譜を更新します。";
  } catch (error) {
    SELECTORS.scoreResultStatus.className = "score-status score-result-status err";
    SELECTORS.scoreResultStatus.textContent = error.message;
  } finally {
    SELECTORS.scoreRegenerateBtn.disabled = false;
  }
};

const renderScoreOutputs = data => {
  currentScoreResult = data;
  const region = data.region || { x: 0, y: 0, width: 0, height: 0 };
  const previewOutputs = Array.isArray(data.outputs) && data.outputs.length
    ? data.outputs
    : data.pageOutputs;
  const outputUnit = data.layout === "a3_2up" ? "枚" : "ページ";
  const outputFormat = data.layout === "a3_2up" ? "A3" : data.layout === "a4" ? "A4" : "縦長";
  const download = data.zipUrl
    ? `<a class="btn-analyze" href="${data.zipUrl}" download>PNGをまとめてダウンロード</a>`
    : "";
  const actions = download ? `<div class="score-download">${download}</div>` : "";
  const badges = [
    `${outputFormat}出力`,
    scoreOptionEnabled(data, "showBpm") && data.musicalAnalysis?.bpm
      ? `BPM ${data.musicalAnalysis.bpm}` : null,
    scoreOptionEnabled(data, "showKeyEstimate") && data.musicalAnalysis?.key
      ? `推定キー ${localizeEstimatedKey(data.musicalAnalysis.key)}` : null,
    scoreOptionEnabled(data, "showChordSymbols")
      && Number(data.musicalAnalysis?.analyzedMeasures || 0) > 0
      ? `TAB画像コード ${data.musicalAnalysis.analyzedMeasures}小節`
      : null,
    data.processingMode === "simple" ? "元の段組みを維持" : "自動再構成済み",
    data.scoreContent === "paired" ? "五線譜＋TAB" : data.scoreContent === "tab" ? "TABのみ" : null,
    Number(data.verticalScrollSystems || 0) > 0 ? "縦スクロールを検出" : null,
    data.horizontalScrollMode === "off" ? "横スクロール補正なし" : null,
    Number(data.measuresPerRow || 0) > 0 ? `1行${data.measuresPerRow}小節` : null,
  ].filter(Boolean);
  const summary = badges.length
    ? `<div class="score-result-summary">${badges.map(label => `<span>${escapeHtml(label)}</span>`).join("")}</div>`
    : "";
  SELECTORS.scoreResultSection.hidden = false;
  SELECTORS.scoreResultTitleInput.value = data.title || data.videoId || "";
  SELECTORS.scoreResult.innerHTML = `${summary}${actions}${previewOutputs.map((url, index) => `
    <div class="score-output">
      <div class="score-output-head">
        <span>${index + 1}/${previewOutputs.length}${outputUnit} · ${outputFormat} · 採用 ${data.keptFrames} · 除外 ${data.skippedFrames}</span>
        <a href="${url}" target="_blank">PNGを開く</a>
      </div>
      <img src="${url}?t=${Date.now()}" alt="抽出済み楽譜 ${index + 1}ページ目">
    </div>
  `).join("")}`;
  SELECTORS.scoreResultStatus.className = "score-status score-result-status ok";
  SELECTORS.scoreResultStatus.textContent = `完了 · 範囲 ${region.x},${region.y},${region.width}x${region.height}`;
  window.lucide?.createIcons();
};

const editScoreSettings = async (data = currentScoreResult) => {
  if (!data?.videoId || !data?.region) return;
  const editedTitle = SELECTORS.scoreResultTitleInput.value.trim();
  editingScoreResult = { ...data, title: editedTitle || data.title };
  scorePreviewData = null;
  scoreRegion = null;
  SELECTORS.scorePreview.hidden = true;
  SELECTORS.scoreUrlInput.value = `https://www.youtube.com/watch?v=${data.videoId}`;
  SELECTORS.scoreTitleInput.value = editingScoreResult.title || "";
  const duration = Number(data.videoDurationSec || 0);
  const start = Number(data.startSec || 0);
  const end = Number(data.endSec || duration || 0);
  const usesRange = start > 0 || (duration > 0 && end < duration - 0.5);
  SELECTORS.scoreTimeMode.value = usesRange ? "range" : "full";
  SELECTORS.scoreTimeRange.hidden = !usesRange;
  SELECTORS.scoreStartTime.value = usesRange ? fmt(start) : "";
  SELECTORS.scoreEndTime.value = usesRange ? fmt(end) : "";
  SELECTORS.scoreTrimStart.value = Number(data.trimStartFrames || 0);
  SELECTORS.scoreTrimEnd.value = Number(data.trimEndFrames || 0);
  SELECTORS.scoreLayout.value = data.layout || "a3_2up";
  SELECTORS.scoreProcessingMode.value = data.processingMode || "auto";
  SELECTORS.scoreContent.value = data.scoreContent || "tab";
  SELECTORS.scoreVerticalScrollMode.value = data.verticalScrollMode || "auto";
  SELECTORS.scoreHorizontalScrollMode.value = data.horizontalScrollMode || "auto";
  SELECTORS.scoreMeasuresPerRow.value = Number(data.measuresPerRow || 4);
  SELECTORS.scoreMeasureNumbers.checked = !!data.showMeasureNumbers;
  SELECTORS.scoreChordSymbols.checked = scoreOptionEnabled(data, "showChordSymbols");
  SELECTORS.scoreKeyEstimate.checked = scoreOptionEnabled(data, "showKeyEstimate");
  SELECTORS.scoreBpm.checked = scoreOptionEnabled(data, "showBpm");
  syncScoreOptionAvailability();
  SELECTORS.scoreFormKicker.textContent = "再生成設定";
  SELECTORS.scoreFormTitle.textContent = "設定を変更して再生成";
  SELECTORS.scoreExtractBtn.textContent = "再生成開始";
  SELECTORS.scoreEditSettingsBtn.disabled = true;
  SELECTORS.scoreStatus.className = "score-status";
  SELECTORS.scoreStatus.textContent = "保存済み設定とプレビューを読み込んでいます...";
  SELECTORS.scorePanel.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    await loadScorePreview();
    if (!scorePreviewData) return;
    scoreRegion = clampScoreRegion(data.region);
    const video = scorePreviewData.video;
    SELECTORS.scoreRegionPercent.value = Math.max(
      5, Math.min(90, Math.round((scoreRegion.height / video.height) * 100))
    );
    SELECTORS.scoreRegionPreset.value = scoreRegion.y + scoreRegion.height / 2 < video.height / 2
      ? "top" : "bottom";
    renderScoreRegion();
    SELECTORS.scoreStatus.className = "score-status ok";
    SELECTORS.scoreStatus.textContent = "設定を読み込みました。変更後に「再生成開始」を押してください。";
  } finally {
    SELECTORS.scoreEditSettingsBtn.disabled = false;
  }
};

const resetScoreWorkspace = () => {
  editingScoreResult = null;
  scorePreviewData = null;
  scoreRegion = null;
  SELECTORS.scoreUrlInput.value = "";
  SELECTORS.scoreTitleInput.value = "";
  SELECTORS.scoreTimeMode.value = "full";
  SELECTORS.scoreTimeRange.hidden = true;
  SELECTORS.scoreStartTime.value = "";
  SELECTORS.scoreEndTime.value = "";
  SELECTORS.scorePreview.hidden = true;
  SELECTORS.scorePreviewImg.removeAttribute("src");
  SELECTORS.scorePreviewMeta.textContent = "";
  SELECTORS.scoreFormKicker.textContent = "新規作成";
  SELECTORS.scoreFormTitle.textContent = "新しい楽譜を抽出";
  SELECTORS.scoreExtractBtn.textContent = "抽出開始";
  SELECTORS.scoreStatus.className = "score-status";
  SELECTORS.scoreStatus.textContent = "次の楽譜動画URLを貼り付けてください。";
  SELECTORS.scoreUrlInput.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => SELECTORS.scoreUrlInput.focus(), 250);
};

const clampScoreRegion = region => {
  if (!scorePreviewData?.video) return region;
  const video = scorePreviewData.video;
  const minSize = 8;
  const x = Math.max(0, Math.min(video.width - minSize, Math.round(region.x)));
  const y = Math.max(0, Math.min(video.height - minSize, Math.round(region.y)));
  const width = Math.max(minSize, Math.min(video.width - x, Math.round(region.width)));
  const height = Math.max(minSize, Math.min(video.height - y, Math.round(region.height)));
  return { x, y, width, height };
};

const regionFromEdges = edges => {
  if (!scorePreviewData?.video) return scoreRegion;
  const video = scorePreviewData.video;
  const minSize = 8;
  let left = Math.max(0, Math.min(video.width - minSize, edges.left));
  let top = Math.max(0, Math.min(video.height - minSize, edges.top));
  let right = Math.max(minSize, Math.min(video.width, edges.right));
  let bottom = Math.max(minSize, Math.min(video.height, edges.bottom));

  if (right - left < minSize) {
    if (edges.anchorX === "left") right = Math.min(video.width, left + minSize);
    else left = Math.max(0, right - minSize);
  }
  if (bottom - top < minSize) {
    if (edges.anchorY === "top") bottom = Math.min(video.height, top + minSize);
    else top = Math.max(0, bottom - minSize);
  }

  return clampScoreRegion({
    x: left,
    y: top,
    width: right - left,
    height: bottom - top,
  });
};

const renderScoreRegion = () => {
  if (!scorePreviewData?.video || !scoreRegion) return;
  const video = scorePreviewData.video;
  const box = SELECTORS.scoreRegionBox;
  box.style.left = `${(scoreRegion.x / video.width) * 100}%`;
  box.style.top = `${(scoreRegion.y / video.height) * 100}%`;
  box.style.width = `${(scoreRegion.width / video.width) * 100}%`;
  box.style.height = `${(scoreRegion.height / video.height) * 100}%`;
  const selectedTime = scorePreviewData.startSec > 0 || scorePreviewData.endSec < video.durationSec
    ? ` · 抽出 ${fmt(scorePreviewData.startSec)}–${fmt(scorePreviewData.endSec)}`
    : ` · 全体 ${fmt(video.durationSec)}`;
  SELECTORS.scorePreviewMeta.textContent =
    `範囲 ${scoreRegion.x},${scoreRegion.y},${scoreRegion.width}x${scoreRegion.height} · 動画 ${video.width}x${video.height}${selectedTime}`;
};

const parseScoreTime = (value, label) => {
  const text = value.trim();
  if (!text) return null;
  const parts = text.split(":");
  if (parts.length > 3 || parts.some(part => part === "" || !/^\d+(?:\.\d+)?$/.test(part))) {
    throw new Error(`${label}は「分:秒」または秒数で入力してください。`);
  }
  const values = parts.map(Number);
  if (values.some(value => !Number.isFinite(value) || value < 0)) {
    throw new Error(`${label}には0以上の時間を入力してください。`);
  }
  if (parts.length > 1 && values.slice(1).some(value => value >= 60)) {
    throw new Error(`${label}の分・秒は60未満にしてください。`);
  }
  return values.reduce((total, value) => total * 60 + value, 0);
};

const getScoreTimePayload = () => {
  if (SELECTORS.scoreTimeMode.value !== "range") return { startSec: null, endSec: null };
  const startSec = parseScoreTime(SELECTORS.scoreStartTime.value, "開始時間");
  const endSec = parseScoreTime(SELECTORS.scoreEndTime.value, "終了時間");
  if (startSec !== null && endSec !== null && endSec <= startSec) {
    throw new Error("終了時間は開始時間より後にしてください。");
  }
  return { startSec, endSec };
};

const getAnalysisTimePayload = () => {
  if (SELECTORS.analysisTimeMode.value !== "range") return { startSec: null, endSec: null };
  const startSec = parseScoreTime(SELECTORS.analysisStartTime.value, "開始時間");
  const endSec = parseScoreTime(SELECTORS.analysisEndTime.value, "終了時間");
  if (startSec !== null && endSec !== null && endSec <= startSec) {
    throw new Error("終了時間は開始時間より後にしてください。");
  }
  return { startSec, endSec };
};

const getScorePreviewPoint = event => {
  const rect = SELECTORS.scorePreviewImg.getBoundingClientRect();
  const video = scorePreviewData.video;
  return {
    x: Math.max(0, Math.min(video.width, ((event.clientX - rect.left) / rect.width) * video.width)),
    y: Math.max(0, Math.min(video.height, ((event.clientY - rect.top) / rect.height) * video.height)),
  };
};

const loadScorePreview = async () => {
  const url = SELECTORS.scoreUrlInput.value.trim();
  SELECTORS.scorePreviewBtn.disabled = true;
  SELECTORS.scoreExtractBtn.disabled = true;
  SELECTORS.scoreStatus.className = "score-status";
  SELECTORS.scoreStatus.innerHTML = `<span class="spin"></span>プレビュー画像を読み込み中...`;
  try {
    const timeRange = getScoreTimePayload();
    const response = await fetch("/score/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        title: SELECTORS.scoreTitleInput.value.trim() || null,
        regionPreset: SELECTORS.scoreRegionPreset.value,
        regionPercent: Number(SELECTORS.scoreRegionPercent.value),
        ...timeRange,
      }),
    });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `サーバーエラー (${response.status})`);
    trackQueuedJob(submitted.jobId, { label: "楽譜プレビュー" });
    const data = await waitForJobResult(submitted.jobId);
    scorePreviewData = data;
    scoreRegion = clampScoreRegion(data.region);
    SELECTORS.scorePreview.hidden = false;
    SELECTORS.scorePreviewImg.src = `${data.previewFrameUrl}?t=${Date.now()}`;
    SELECTORS.scoreStatus.className = "score-status ok";
    SELECTORS.scoreStatus.textContent = "プレビューを読み込みました。オレンジの枠を動かして楽譜範囲を選択してください。";
    SELECTORS.scorePreviewImg.onload = renderScoreRegion;
    renderScoreRegion();
  } catch (error) {
    SELECTORS.scoreStatus.className = "score-status err";
    SELECTORS.scoreStatus.textContent = error.message;
  } finally {
    SELECTORS.scorePreviewBtn.disabled = false;
    SELECTORS.scoreExtractBtn.disabled = false;
  }
};

const extractScore = async () => {
  const url = SELECTORS.scoreUrlInput.value.trim();
  const regeneratingWithChanges = !!editingScoreResult;
  if (!scoreRegion) {
    await loadScorePreview();
    if (!scoreRegion) return;
  }
  SELECTORS.scoreExtractBtn.disabled = true;
  SELECTORS.scoreStatus.className = "score-status";
  SELECTORS.scoreStatus.innerHTML = `<span class="spin"></span>抽出を処理一覧へ追加中...`;
  try {
    const timeRange = getScoreTimePayload();
    const response = await fetch("/score/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        title: SELECTORS.scoreTitleInput.value.trim() || null,
        regionPreset: SELECTORS.scoreRegionPreset.value,
        regionPercent: Number(SELECTORS.scoreRegionPercent.value),
        ...timeRange,
        trimStartFrames: Number(SELECTORS.scoreTrimStart.value),
        trimEndFrames: Number(SELECTORS.scoreTrimEnd.value),
        layout: SELECTORS.scoreLayout.value,
        processingMode: SELECTORS.scoreProcessingMode.value,
        scoreContent: SELECTORS.scoreContent.value,
        verticalScrollMode: SELECTORS.scoreVerticalScrollMode.value,
        horizontalScrollMode: SELECTORS.scoreHorizontalScrollMode.value,
        measuresPerRow: Number(SELECTORS.scoreMeasuresPerRow.value),
        showMeasureNumbers: SELECTORS.scoreMeasureNumbers.checked,
        showChordSymbols: SELECTORS.scoreChordSymbols.checked,
        showKeyEstimate: SELECTORS.scoreKeyEstimate.checked,
        showBpm: SELECTORS.scoreBpm.checked,
        region: scoreRegion,
      }),
    });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `サーバーエラー (${response.status})`);
    const videoId = extractVideoId(url);
    trackQueuedJob(submitted.jobId, {
      label: regeneratingWithChanges
        ? `楽譜を再生成 · ${videoId || "設定変更"}`
        : videoId ? `楽譜抽出 · ${videoId}` : "楽譜抽出",
      kind: "score-extract",
      retainDone: true,
      onDone: saveScoreHistory,
    });
    resetScoreWorkspace();
    SELECTORS.scoreStatus.className = "score-status ok";
    SELECTORS.scoreStatus.textContent = regeneratingWithChanges
      ? "変更した設定で再生成を追加しました。"
      : "抽出を追加しました。続けて次の楽譜動画URLを貼り付けられます。";
  } catch (error) {
    SELECTORS.scoreStatus.className = "score-status err";
    SELECTORS.scoreStatus.textContent = error.message;
  } finally {
    SELECTORS.scoreExtractBtn.disabled = false;
  }
};

const syncScoreOptionAvailability = () => {
  const automatic = SELECTORS.scoreProcessingMode.value === "auto";
  [
    SELECTORS.scoreContent,
    SELECTORS.scoreVerticalScrollMode,
    SELECTORS.scoreHorizontalScrollMode,
    SELECTORS.scoreMeasuresPerRow,
  ].forEach(control => {
    control.disabled = !automatic;
  });
};

const extractVideoId = url => {
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "youtu.be") return parsed.pathname.replace(/^\//, "").split("?")[0] || null;
    if (["www.youtube.com", "youtube.com", "m.youtube.com"].includes(parsed.hostname)) {
      return parsed.searchParams.get("v");
    }
  } catch {
    return null;
  }
  return null;
};

const secColor = label => COLORS[Object.keys(COLORS).find(key => label.toLowerCase().includes(key))] ?? "#94a3b8";
const localizeSectionLabel = label => {
  const raw = String(label || "");
  const normalized = raw.toLowerCase();
  const labels = [
    ["pre-chorus", "プレコーラス"],
    ["post-chorus", "ポストコーラス"],
    ["intro", "イントロ"],
    ["verse", "ヴァース"],
    ["chorus", "コーラス"],
    ["bridge", "ブリッジ"],
    ["interlude", "間奏"],
    ["instrumental", "間奏"],
    ["solo", "ソロ"],
    ["start", "開始"],
    ["outro", "アウトロ"],
    ["ending", "エンディング"],
  ];
  const match = labels.find(([key]) => normalized.includes(key));
  return match ? raw.replace(new RegExp(match[0], "i"), match[1]) : raw;
};
const rgba = (hex, alpha) => {
  const [r, g, b] = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16));
  return `rgba(${r},${g},${b},${alpha})`;
};

const getCtx = () => {
  if (!audioCtx) audioCtx = new AudioContext();
  if (audioCtx.state === "suspended") audioCtx.resume();
  return audioCtx;
};

const initStemPlayers = stemAssets => {
  destroyStemPlayers();
  if (!hasStemAssets({ stems: stemAssets })) return false;
  for (const stem of STEM_NAMES) {
    const player = new Audio(stemAssets[stem]);
    player.preload = "auto";
    preserveMediaPitch(player);
    player.playbackRate = playbackRate;
    stemPlayers[stem] = player;
  }
  stemReady = true;
  applyStemMix();
  ws?.setVolume(0);
  return true;
};

const clickTone = time => {
  const ctx = getCtx();
  const startTime = Math.max(ctx.currentTime + 0.002, time);
  const volume = parseInt(SELECTORS.volMetro.value, 10) / 100;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const filter = ctx.createBiquadFilter();
  osc.connect(filter);
  filter.connect(gain);
  gain.connect(ctx.destination);
  osc.type = "square";
  osc.frequency.value = 1800;
  filter.type = "highpass";
  filter.frequency.value = 700;
  gain.gain.setValueAtTime(0.0001, startTime);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, volume * 0.9), startTime + 0.003);
  gain.gain.exponentialRampToValueAtTime(0.0001, startTime + 0.045);
  osc.start(startTime);
  osc.stop(startTime + 0.055);
  osc.onended = () => {
    gain.disconnect();
    filter.disconnect();
    osc.disconnect();
  };
};

const alignMetronomeToTime = time => {
  const beats = getAdjustedBeats();
  nextBeatIndex = beats.findIndex(beat => beat >= time - 0.02);
  if (nextBeatIndex < 0) nextBeatIndex = beats.length;
};

const syncMetronome = () => {
  alignMetronomeToTime(ws?.getCurrentTime() ?? 0);
};

const seekAudio = (targetTime, { respectLoopRange = true } = {}) => {
  if (!ws) return;
  const duration = ws.getDuration();
  if (!(duration > 0)) return;
  let clampedTime = Math.min(duration, Math.max(0, targetTime));
  if (respectLoopRange && loopOn) {
    const loopRange = getLoopRange();
    if (loopRange && clampedTime < loopRange.start) clampedTime = loopRange.start;
  }
  metroResumeAtMs = performance.now() + 120;
  alignMetronomeToTime(clampedTime);
  lastMetroTime = clampedTime;
  syncVideoToAudio(clampedTime, { force: true });
  ws.seekTo(clampedTime / duration);
  syncStemPlayers(clampedTime, { force: true });
};

const tickMetronome = generation => {
  if (generation !== metroGeneration) return;
  const beats = getAdjustedBeats();
  if (!ws || !audioAvailable || !metroOn || !ws.isPlaying() || !beats.length) return;
  if (performance.now() < metroResumeAtMs) {
    metroRafId = requestAnimationFrame(() => tickMetronome(generation));
    return;
  }
  const currentTime = ws.getCurrentTime();
  if (Math.abs(currentTime - lastMetroTime) > 0.25) alignMetronomeToTime(currentTime);
  lastMetroTime = currentTime;
  const ctx = getCtx();
  const lookAhead = isMobileViewport() ? 0.09 : 0.055;

  while (nextBeatIndex < beats.length && beats[nextBeatIndex] <= currentTime + lookAhead) {
    clickTone(ctx.currentTime + Math.max(0, beats[nextBeatIndex] - currentTime));
    nextBeatIndex += 1;
  }

  metroRafId = requestAnimationFrame(() => tickMetronome(generation));
};

const startMetro = () => {
  if (metroRafId) cancelAnimationFrame(metroRafId);
  metroGeneration += 1;
  syncMetronome();
  lastMetroTime = ws?.getCurrentTime() ?? 0;
  metroRafId = requestAnimationFrame(() => tickMetronome(metroGeneration));
};

const stopMetro = () => {
  if (metroRafId) cancelAnimationFrame(metroRafId);
  metroRafId = 0;
  metroGeneration += 1;
  metroResumeAtMs = 0;
};

const medianNumber = values => {
  const sorted = values.filter(value => Number.isFinite(value) && value > 0).sort((left, right) => left - right);
  if (!sorted.length) return 0;
  return sorted[Math.floor(sorted.length / 2)];
};

const applyClickOffset = beats => {
  if (!clickOffsetHalfBeat || beats.length < 2) return beats;
  const interval = medianNumber(beats.slice(1).map((beat, index) => beat - beats[index]));
  if (!(interval > 0)) return beats;
  const offset = -interval / 2;
  return beats.map(beat => Math.max(0, beat + offset));
};

const getAdjustedBeats = () => {
  const beats = currentData?.beats ?? [];
  if (!beats.length) return [];
  if (bpmFactor === 1) return applyClickOffset(beats);

  let adjusted = [...beats];
  let factor = bpmFactor;

  while (factor > 1) {
    const expanded = [];
    for (let i = 0; i < adjusted.length; i += 1) {
      const beat = adjusted[i];
      expanded.push(beat);
      const next = adjusted[i + 1];
      if (next != null) expanded.push((beat + next) / 2);
    }
    adjusted = expanded;
    factor /= 2;
  }

  while (factor < 1) {
    adjusted = adjusted.filter((_, index) => index % 2 === 0);
    factor *= 2;
  }

  return applyClickOffset(adjusted);
};

const getLoopRange = () => {
  if (customLoopRange) return customLoopRange;
  if (!selectedIdxs.size || !currentData) return null;
  const indexes = [...selectedIdxs].sort((left, right) => left - right);
  return {
    start: currentData.sections[indexes[0]].start_time,
    end: currentData.sections[indexes.at(-1)].end_time,
    labels: indexes.map(index => localizeSectionLabel(currentData.sections[index].label)),
  };
};

const updateSelectionUI = () => {
  document.querySelectorAll(".sec-row").forEach((row, index) => {
    const selected = selectedIdxs.has(index);
    row.classList.toggle("selected", selected && loopOn);
    row.classList.toggle("preview-selected", selected && !loopOn);
  });
  SELECTORS.btnClearRange.hidden = !customLoopRange;
  renderCustomLoopRange();
  renderSectionSelectionRanges();
  updateStemExportScopeAvailability();

  if (!loopOn) {
    SELECTORS.loopInfo.textContent = "";
    return;
  }

  const loopRange = getLoopRange();
  if (!loopRange) {
    SELECTORS.loopInfo.textContent = "↻ 曲全体";
    return;
  }

  if (loopRange.kind === "custom") {
    if (loopRange.labels?.length) {
      const label = loopRange.labels.length === 1
        ? loopRange.labels[0]
        : `${loopRange.labels[0]} → ${loopRange.labels.at(-1)}`;
      SELECTORS.loopInfo.textContent = `↻ ${label} ${fmt(loopRange.start)}-${fmt(loopRange.end)}`;
      return;
    }
    SELECTORS.loopInfo.textContent = `↻ 範囲 ${fmt(loopRange.start)}-${fmt(loopRange.end)}`;
    return;
  }

  const label = loopRange.labels.length === 1
    ? loopRange.labels[0]
    : `${loopRange.labels[0]} → ${loopRange.labels.at(-1)}`;
  SELECTORS.loopInfo.textContent = `↻ ${label} ${fmt(loopRange.start)}-${fmt(loopRange.end)}`;
};

const updatePlayButton = () => {
  const isPlaying = !!ws?.isPlaying();
  for (const button of [SELECTORS.btnPlay, SELECTORS.btnFsPlay]) {
    button.classList.toggle("is-playing", isPlaying);
    button.setAttribute("aria-label", isPlaying ? "一時停止" : "再生");
  }
};

const updatePlaybackModeButtons = () => {
  for (const button of [SELECTORS.btnLoop, SELECTORS.btnFsLoop]) {
    button.classList.toggle("active", loopOn);
    button.setAttribute("aria-pressed", String(loopOn));
  }
  for (const button of [SELECTORS.btnAutoNext, SELECTORS.btnFsAutoNext]) {
    button.classList.toggle("active", autoNextOn);
    button.setAttribute("aria-pressed", String(autoNextOn));
    button.title = loopOn
      ? "ループ中は自動で次への機能を停止します"
      : "曲が終わると次の曲を再生します";
  }
  for (const button of [SELECTORS.btnMetro, SELECTORS.btnFsMetro]) {
    button.classList.toggle("active", metroOn);
    button.setAttribute("aria-pressed", String(metroOn));
  }
};

const canPlayAudio = () => !!ws && audioAvailable && audioReady;

const togglePlayback = () => {
  if (!ws || (!ws.isPlaying() && !canPlayAudio())) return;
  getCtx();
  if (ws.isPlaying()) {
    ws.pause();
    return;
  }
  playStems();
  ws.play();
};

const playFromTime = time => {
  if (!canPlayAudio()) return;
  getCtx();
  seekAudio(time);
  playStems();
  ws.play();
};

const playFromBeginning = () => playFromTime(0);

const seekVideoByClickSide = event => {
  if (!ws) return;
  const rect = SELECTORS.videoPlayer.getBoundingClientRect();
  const fullscreenPortrait =
    document.body.classList.contains("video-fullscreen-mode") &&
    window.matchMedia("(max-width: 680px) and (orientation: portrait)").matches;
  const position = fullscreenPortrait
    ? (event.clientY - rect.top) / rect.height
    : (event.clientX - rect.left) / rect.width;
  const delta = position < 0.5 ? -5 : 5;
  seekAudio(ws.getCurrentTime() + delta);
};

const handleVideoClick = event => {
  event.preventDefault();
  if (videoClickTimer) {
    clearTimeout(videoClickTimer);
    videoClickTimer = 0;
    seekVideoByClickSide(event);
    return;
  }
  videoClickTimer = window.setTimeout(() => {
    videoClickTimer = 0;
    togglePlayback();
  }, 240);
};

const adjustBarValue = value => Math.max(1, Math.round(value * bpmFactor));
const adjustBarRange = (startBar, endBar) => {
  const start = Math.max(1, Math.round((startBar - 1) * bpmFactor) + 1);
  const end = Math.max(start, Math.round(endBar * bpmFactor));
  return { start, end, count: end - start + 1 };
};

const applyBpmDisplay = () => {
  if (!currentData) return;
  const value = Number(currentData.bpm || 0) * bpmFactor;
  SELECTORS.metaBpm.textContent = Number.isInteger(value) ? String(value) : value.toFixed(1);
  SELECTORS.metaBars.textContent = adjustBarValue(currentData.total_bars || 0);
  document.querySelectorAll(".sec-row").forEach((row, index) => {
    const section = currentData.sections[index];
    if (!section) return;
    const { count: barCount } = adjustBarRange(section.start_bar, section.end_bar);
    const bars = row.querySelector(".sec-bars");
    if (bars) {
      bars.innerHTML = `<span class="subtle">${barCount}小節</span>`;
    }
  });
  document.querySelectorAll(".si").forEach(row => {
    if (row.dataset.id !== currentId) return;
    const meta = row.querySelector(".si-meta");
    if (meta) {
      const date = row.dataset.date || "";
      meta.textContent = `♩${SELECTORS.metaBpm.textContent}${date ? ` · ${date}` : ""}`;
    }
  });
  renderFourBarGrid();
};

const stopJobPolling = () => {
  if (jobPollTimer) {
    clearInterval(jobPollTimer);
    jobPollTimer = null;
  }
};

const renderJobStatus = job => {
  if (!job) return;
  SELECTORS.jobCard.hidden = true;
  SELECTORS.jobStage.textContent = localizeJobStage(job.stage);
  const startedAt = job.started_at ?? currentJobStartedAt ?? Date.now() / 1000;
  currentJobStartedAt = startedAt;
  const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
  SELECTORS.jobElapsed.textContent = `${elapsed}秒`;
  SELECTORS.jobMessage.textContent = job.error || localizeJobMessage(job.message);
};

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const fetchJobStatus = async jobId => {
  const response = await fetch(`/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`ジョブ状態を取得できません (${response.status})`);
  return response.json();
};

const queueItemClass = job => {
  if (job?.canceled || job?.stage === "canceled") return "canceled";
  if (job?.error) return "error";
  if (job?.done) return "done";
  if (job?.stage === "queued") return "queued";
  return "running";
};

const localizeJobStage = stage => ({
  queued: "待機中",
  running: "処理中",
  processing: "処理中",
  downloading: "素材準備",
  inferencing: "曲構成を解析中",
  saving: "保存中",
  stems: "パート分離中",
  exporting: "書き出し中",
  uploading: "同期中",
  canceling: "キャンセル中",
  canceled: "キャンセル済み",
  interrupted: "再開待ち",
  done: "完了",
  error: "エラー",
}[String(stage || "").toLowerCase()] || stage || "待機中");

const localizeJobMessage = message => {
  const raw = String(message || "");
  const exact = {
    "Complete": "完了しました",
    "Canceled": "キャンセルしました",
    "Cancel requested": "キャンセルを要求しました",
    "Application restarted; resume when ready": "前回の終了時に中断されました。準備ができたら再開してください",
    "Queued": "処理一覧に追加しました",
    "Queued analysis": "解析を処理一覧に追加しました",
    "Queued local audio analysis": "音声ファイルの解析を処理一覧に追加しました",
    "Queued stem separation": "パート分離を処理一覧に追加しました",
    "Queued stem mix export": "パート書き出しを処理一覧に追加しました",
    "Queued cloud sync": "クラウド同期を処理一覧に追加しました",
    "Queued score preview": "楽譜プレビューを処理一覧に追加しました",
    "Queued score extraction": "楽譜抽出を処理一覧に追加しました",
    "Rendering stem mix": "パートのミックスを書き出しています",
    "Analysis timed out": "解析がタイムアウトしました",
    "Separating stems": "パートを分離しています",
    "Loaded from cache": "保存済みの解析結果を読み込みました",
    "Fetching title": "動画タイトルを取得しています",
    "Downloading audio": "音声をダウンロードしています",
    "Using cached audio": "保存済みの音声を使用します",
    "Downloading video": "動画をダウンロードしています",
    "Using cached video": "保存済みの動画を使用します",
    "Preparing playback mp3": "再生用の音声を準備しています",
    "Preparing uploaded audio": "音声ファイルを変換しています",
    "Preparing playback video": "再生用の動画を準備しています",
    "Saving results": "解析結果を保存しています",
    "Analysis complete": "解析が完了しました",
    "Preparing cloud asset URLs": "クラウド用URLを準備しています",
    "Uploading session assets to R2": "楽曲データをクラウドへ送信しています",
    "Stems ready": "パートの準備ができました",
    "Exporting static assets": "公開用データを書き出しています",
    "Updating R2 CORS": "クラウドの接続設定を更新しています",
    "Uploading manifest": "楽曲一覧をクラウドへ送信しています",
    "Uploading folders": "フォルダー情報をクラウドへ送信しています",
    "Uploading static app": "アプリをクラウドへ送信しています",
  };
  if (exact[raw]) return exact[raw];
  if (/^Starting WSL analyzer on /i.test(raw)) return "曲構成の解析を開始しています";
  if (/^Analyzer still running; no output for (\d+)s$/i.test(raw)) {
    return `曲構成を解析中です（${raw.match(/(\d+)s$/)?.[1] || 0}秒間、新しい進捗なし）`;
  }
  if (/^Encoding /i.test(raw)) {
    const stem = raw.replace(/^Encoding /i, "").toLowerCase();
    return `${({ vocals: "ボーカル", drums: "ドラム", bass: "ベース", other: "その他" })[stem] || stem}を変換しています`;
  }
  if (/^Uploading /i.test(raw)) return `${raw.replace(/^Uploading /i, "")}をクラウドへ送信しています`;
  return raw;
};

const renderQueueDock = () => {
  if (!SELECTORS.queueDock || !SELECTORS.queueList || !SELECTORS.queueCount) return;
  const jobs = [...trackedJobs.values()].sort((a, b) => b.createdAt - a.createdAt);
  SELECTORS.queueDock.hidden = jobs.length === 0;
  SELECTORS.queueCount.textContent = String(jobs.filter(item => !item.status?.done || item.status?.resumable).length);
  SELECTORS.queueList.innerHTML = jobs.map(item => {
    const status = item.status || { stage: "queued", message: "サーバーを待っています" };
    const startedAt = status.started_at || item.createdAt / 1000;
    const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
    return `
      <div class="queue-item ${queueItemClass(status)}">
        <div class="queue-title" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</div>
        <div class="queue-stage">${escapeHtml(localizeJobStage(status.stage))} · ${elapsed}秒</div>
        <div class="queue-message">${escapeHtml(status.error || localizeJobMessage(status.message))}</div>
        ${status.resumable
          ? `<button class="queue-cancel queue-resume" type="button" data-job-id="${escapeHtml(item.id)}" data-job-action="resume">再開</button>`
          : item.kind === "stem-export" && status.done && status.result?.downloadUrl
          ? `<a class="queue-cancel queue-download" href="${escapeHtml(status.result.downloadUrl)}" download="${escapeHtml(status.result.filename || "stem-mix.mp3")}">ダウンロード</a>`
          : item.kind === "score-extract" && status.done && status.result
            ? `<button class="queue-cancel queue-view-result" type="button" data-job-id="${escapeHtml(item.id)}" data-job-action="view-score">結果を見る</button>`
            : `<button class="queue-cancel" type="button" data-job-id="${escapeHtml(item.id)}" data-job-action="cancel" ${status.done || status.cancel_requested ? "disabled" : ""}>キャンセル</button>`}
      </div>
    `;
  }).join("");
};

const stopQueuePollingIfIdle = () => {
  if ([...trackedJobs.values()].some(item => !item.status?.done)) return;
  if (queuePollTimer) {
    clearInterval(queuePollTimer);
    queuePollTimer = null;
  }
};

const pollTrackedJobs = async () => {
  const now = Date.now();
  for (const [jobId, item] of trackedJobs.entries()) {
    if (item.status?.done) {
      if (!item.retainDone && (item.doneAt || now) + 9000 < now) trackedJobs.delete(jobId);
      continue;
    }
    try {
      const status = await fetchJobStatus(jobId);
      item.status = status;
      if (status.done) {
        item.doneAt = now;
        if (status.canceled) {}
        else if (status.error) item.onError?.(new Error(status.error));
        else item.onDone?.(status.result);
      }
    } catch (error) {
      item.status = { stage: "error", message: error.message, done: true, error: error.message };
      item.doneAt = now;
      item.onError?.(error);
    }
  }
  renderQueueDock();
  stopQueuePollingIfIdle();
};

const trackQueuedJob = (jobId, options = {}) => {
  if (!jobId) return;
  trackedJobs.set(jobId, {
    id: jobId,
    label: options.label || jobId,
    onDone: options.onDone,
    onError: options.onError,
    kind: options.kind,
    retainDone: Boolean(options.retainDone),
    createdAt: Date.now(),
    status: { stage: "queued", message: "処理一覧に追加しました", done: false },
  });
  renderQueueDock();
  if (!queuePollTimer) queuePollTimer = setInterval(pollTrackedJobs, 1000);
  pollTrackedJobs();
};

const cancelQueuedJob = async jobId => {
  if (!jobId || !trackedJobs.has(jobId)) return;
  const item = trackedJobs.get(jobId);
  item.status = { ...(item.status || {}), stage: "canceling", message: "キャンセルを要求しました", cancel_requested: true, done: false };
  renderQueueDock();
  try {
    const response = await fetch(`/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
    const status = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(status.detail || "キャンセルに失敗しました");
    item.status = status;
    if (status.done) item.doneAt = Date.now();
  } catch (error) {
    item.status = { stage: "error", message: error.message, done: true, error: error.message };
    item.doneAt = Date.now();
  }
  renderQueueDock();
  if (!queuePollTimer) queuePollTimer = setInterval(pollTrackedJobs, 1000);
};

const resumeQueuedJob = async jobId => {
  const item = trackedJobs.get(jobId);
  if (!item) return;
  try {
    const response = await fetch(`/jobs/${encodeURIComponent(jobId)}/resume`, { method: "POST" });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || "ジョブを再開できませんでした");
    item.status = { stage: submitted.stage, message: submitted.message, done: false, resumable: false };
    item.doneAt = null;
    item.retainDone = true;
    renderQueueDock();
    if (!queuePollTimer) queuePollTimer = setInterval(pollTrackedJobs, 1000);
    pollTrackedJobs();
  } catch (error) {
    item.status = { ...(item.status || {}), error: error.message };
    renderQueueDock();
  }
};

const restoreInterruptedJobs = async () => {
  if (!hasServer || staticLibraryMode) return;
  try {
    const response = await fetch("/jobs?recoverable=true", { cache: "no-store" });
    if (!response.ok) return;
    const jobs = await response.json();
    for (const status of jobs) {
      trackedJobs.set(status.id, {
        id: status.id,
        label: localizeJobMessage(status.description) || status.id,
        kind: status.kind,
        retainDone: true,
        createdAt: (status.started_at || status.updated_at || Date.now() / 1000) * 1000,
        status,
      });
    }
    renderQueueDock();
  } catch {}
};

const syncCloudLibrary = async () => {
  if (!hasServer || staticLibraryMode) return;
  SELECTORS.btnCloudSync.disabled = true;
  try {
    const response = await fetch("/cloud/sync", { method: "POST" });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `同期に失敗しました (${response.status})`);
    trackQueuedJob(submitted.jobId, { label: "クラウド同期" });
  } catch (error) {
    alert(error.message);
  } finally {
    SELECTORS.btnCloudSync.disabled = false;
  }
};

const pollJobStatus = async jobId => {
  if (!jobId || !hasServer) return;
  currentJobId = jobId;
  currentJobStartedAt = Date.now() / 1000;
  stopJobPolling();
  const refresh = async () => {
    try {
      const job = await fetchJobStatus(jobId);
      renderJobStatus(job);
      if (job.done) stopJobPolling();
    } catch {}
  };
  await refresh();
  jobPollTimer = setInterval(refresh, 1000);
};

const waitForJobResult = async jobId => {
  if (!jobId) throw new Error("ジョブIDがありません");
  currentJobId = jobId;
  currentJobStartedAt = Date.now() / 1000;
  stopJobPolling();
  while (true) {
    const job = await fetchJobStatus(jobId);
    renderJobStatus(job);
    if (job.done) {
      if (job.canceled) throw new Error("キャンセルされました");
      if (job.error) throw new Error(job.error);
      return job.result;
    }
    await sleep(1000);
  }
};

const updatePlayingRow = time => {
  if (!currentData) return;
  let index = -1;
  for (let i = 0; i < currentData.sections.length; i += 1) {
    const section = currentData.sections[i];
    if (time >= section.start_time && time < section.end_time) {
      index = i;
      break;
    }
  }
  if (index === playingIdx) return;
  playingIdx = index;
  document.querySelectorAll(".sec-row").forEach((row, rowIndex) => {
    row.classList.toggle("playing", rowIndex === index);
  });
};

const ensureWaveformSelectionEl = () => {
  if (waveformSelectionEl?.isConnected) return waveformSelectionEl;
  waveformSelectionEl = document.createElement("div");
  waveformSelectionEl.className = "loop-selection";
  waveformSelectionEl.hidden = true;
  for (const side of ["start", "end"]) {
    const handle = document.createElement("span");
    handle.className = `loop-selection-handle ${side}`;
    handle.dataset.loopHandle = side;
    handle.title = side === "start" ? "ループ開始位置を調整" : "ループ終了位置を調整";
    waveformSelectionEl.appendChild(handle);
  }
  SELECTORS.waveform.appendChild(waveformSelectionEl);
  return waveformSelectionEl;
};

const clearSectionSelectionRanges = () => {
  waveformSectionSelectionEls.forEach(element => element.remove());
  waveformSectionSelectionEls = [];
};

const clearFourBarGrid = () => {
  waveformBarGridEls.forEach(element => element.remove());
  waveformBarGridEls = [];
};

const renderFourBarGrid = () => {
  clearFourBarGrid();
  if (!SELECTORS.waveform || !currentData?.sections?.length) return;
  const duration = ws?.getDuration() ?? currentData.duration ?? 0;
  if (!(duration > 0)) return;

  for (const section of currentData.sections) {
    const start = Math.max(0, Math.min(duration, section.start_time));
    const end = Math.max(start, Math.min(duration, section.end_time));
    const { count: barCount } = adjustBarRange(section.start_bar, section.end_bar);
    if (!(end > start) || barCount < 1) continue;

    // Every section begins a new four-bar count: 0, 4, 8... within that section only.
    for (let barOffset = 0; barOffset < barCount; barOffset += 4) {
      const time = start + ((end - start) * barOffset / barCount);
      const element = document.createElement("span");
      element.className = "four-bar-grid-line";
      element.style.left = `${(time / duration) * 100}%`;
      SELECTORS.waveform.appendChild(element);
      waveformBarGridEls.push(element);
    }
  }
};

const renderSectionSelectionRanges = () => {
  clearSectionSelectionRanges();
  if (!SELECTORS.waveform || loopOn || customLoopRange || !selectedIdxs.size || !currentData?.sections?.length) return;
  const duration = ws?.getDuration() ?? currentData.duration ?? 0;
  if (!(duration > 0)) return;

  [...selectedIdxs].sort((left, right) => left - right).forEach(index => {
    const section = currentData.sections[index];
    if (!section) return;
    const start = Math.max(0, Math.min(duration, section.start_time));
    const end = Math.max(start, Math.min(duration, section.end_time));
    if (end - start < 0.05) return;

    const element = document.createElement("div");
    element.className = "section-selection preview";
    element.style.left = `${(start / duration) * 100}%`;
    element.style.width = `${Math.max(0.2, ((end - start) / duration) * 100)}%`;
    SELECTORS.waveform.appendChild(element);
    waveformSectionSelectionEls.push(element);
  });
};

const renderCustomLoopRange = previewRange => {
  const selection = ensureWaveformSelectionEl();
  const duration = ws?.getDuration() ?? currentData?.duration ?? 0;
  const range = previewRange ?? (loopOn ? getLoopRange() : customLoopRange);
  if (!(duration > 0) || !range || range.end - range.start < 0.05) {
    selection.hidden = true;
    selection.style.left = "0%";
    selection.style.width = "0%";
    return;
  }
  const start = Math.max(0, Math.min(duration, range.start));
  const end = Math.max(start, Math.min(duration, range.end));
  selection.hidden = false;
  selection.style.left = `${(start / duration) * 100}%`;
  selection.style.width = `${Math.max(0.2, ((end - start) / duration) * 100)}%`;
};

const getWaveformTimeFromClientX = clientX => {
  if (!ws) return 0;
  const rect = SELECTORS.waveform.getBoundingClientRect();
  if (rect.width <= 0) return 0;
  const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  return (ws.getDuration() || 0) * ratio;
};

const getMovedLoopRange = (drag, clientX) => {
  const duration = ws?.getDuration() ?? 0;
  const rangeDuration = drag.rangeEnd - drag.rangeStart;
  const delta = getWaveformTimeFromClientX(clientX) - drag.startTime;
  const start = Math.min(Math.max(0, drag.rangeStart + delta), Math.max(0, duration - rangeDuration));
  return { start, end: start + rangeDuration, kind: "custom" };
};

const clearCustomLoopRange = ({ clearSelection = false } = {}) => {
  customLoopRange = null;
  if (clearSelection) selectedIdxs.clear();
  renderCustomLoopRange();
  updateSelectionUI();
};

const applySectionLoopRange = indexes => {
  if (!currentData || !indexes.length) return;
  const sorted = [...indexes].sort((left, right) => left - right);
  const startIndex = sorted[0];
  const endIndex = sorted.at(-1);
  const startSection = currentData.sections[startIndex];
  const endSection = currentData.sections[endIndex];
  if (!startSection || !endSection) return;
  selectedIdxs = new Set(sorted);
  customLoopRange = {
    start: startSection.start_time,
    end: endSection.end_time,
    kind: "custom",
    labels: sorted.map(sectionIndex => currentData.sections[sectionIndex].label),
  };
  renderCustomLoopRange();
  updateSelectionUI();
};

const applyCustomLoopRange = (start, end) => {
  const duration = ws?.getDuration() ?? 0;
  if (!(duration > 0)) return;
  const clampedStart = Math.min(duration, Math.max(0, start));
  const clampedEnd = Math.min(duration, Math.max(clampedStart, end));
  if (clampedEnd - clampedStart < 0.1) {
    clearCustomLoopRange();
    return;
  }
  selectedIdxs = new Set();
  customLoopRange = { start: clampedStart, end: clampedEnd, kind: "custom" };
  renderCustomLoopRange();
  updateSelectionUI();
  playFromTime(clampedStart);
};

const renderStemPanel = assets => {
  const available = hasStemAssets(assets);
  SELECTORS.stemPanel.classList.toggle("missing", !available);
  SELECTORS.btnGenerateStems.textContent = available ? "再生成" : "生成";
  SELECTORS.btnGenerateStems.hidden = !hasServer || staticLibraryMode;
  SELECTORS.btnGenerateStems.disabled = !currentId || !hasServer;
  SELECTORS.stemExportActions.hidden = !available || !hasServer;
  SELECTORS.stemExportClick.disabled = !currentData?.beats?.length;
  if (SELECTORS.stemExportClick.disabled) SELECTORS.stemExportClick.checked = false;
  SELECTORS.btnExportStemMix.disabled = !available || stemExportInProgress;
  SELECTORS.stemStatus.className = available ? "stem-status ok" : "stem-status";
  SELECTORS.stemStatus.textContent = available
    ? "準備完了"
    : (hasServer ? "パート生成までは元音源を再生します" : "元音源");
  applyStemMix();
  updateStemExportScopeAvailability();
};

const initVideoPlayer = videoUrl => {
  const video = SELECTORS.videoPlayer;
  video.pause();
  if (videoClickTimer) {
    clearTimeout(videoClickTimer);
    videoClickTimer = 0;
  }
  video.onclick = handleVideoClick;
  video.ondblclick = event => event.preventDefault();
  video.removeAttribute("src");
  video.load();
  videoAvailable = !!videoUrl;
  lastVideoSyncAt = 0;
  SELECTORS.videoNote.hidden = !!videoUrl;
  SELECTORS.btnVideoFullscreen.hidden = !videoUrl;
  if (!videoUrl) return;
  video.src = videoUrl;
  preserveMediaPitch(video);
  video.playbackRate = playbackRate;
  video.onerror = () => {
    videoAvailable = false;
    setVideoFullscreen(false);
    video.removeAttribute("src");
    video.load();
    SELECTORS.videoNote.hidden = false;
    SELECTORS.btnVideoFullscreen.hidden = true;
  };
};

const initWaveSurfer = (audioUrl, videoUrl, stemAssets = null) => {
  if (ws) {
    stopMetro();
    ws.destroy();
    ws = null;
  }
  destroyStemPlayers();

  initVideoPlayer(videoUrl);

  waveformDrag = null;
  SELECTORS.timeCur.textContent = "00:00";
  playingIdx = -1;
  document.querySelectorAll(".sec-row").forEach(row => row.classList.remove("playing"));
  updatePlayButton();
  updateSelectionUI();

  ws = WaveSurfer.create({
    container: "#waveform",
    waveColor: "#2e2e2e",
    progressColor: "#f97316",
    url: audioUrl,
    height: isMobileViewport() ? 44 : 64,
    barWidth: 2,
    barGap: 1,
    barRadius: 2,
    plugins: [RegionsPlugin.create()],
  });

  initStemPlayers(stemAssets);
  applyMusicVolume(SELECTORS.volMusic.value);
  ws.setPlaybackRate?.(playbackRate, true);
  preserveMediaPitch(ws.getMediaElement?.());
  let handlingFinish = false;
  const handlePlaybackFinished = async () => {
    if (handlingFinish) return;
    handlingFinish = true;
    try {
      if (loopOn) {
        const loopRange = getLoopRange();
        if (loopRange) {
          seekAudio(loopRange.start);
          ws.play();
          return;
        }
        seekAudio(0);
        ws.play();
        return;
      }
      if (await playNextInGroup()) return;
      pauseVideo();
      pauseStems();
      stopMetro();
      updatePlayButton();
    } finally {
      handlingFinish = false;
    }
  };
  ws.getMediaElement?.()?.addEventListener("ended", handlePlaybackFinished);
  const getRegions = () => ws.getActivePlugins()[0];
  const disableTransport = disabled => {
    for (const button of [SELECTORS.btnPlay, SELECTORS.btnRestart, SELECTORS.btnLoop, SELECTORS.btnAutoNext, SELECTORS.btnMetro, SELECTORS.btnFsPlay, SELECTORS.btnFsRestart, SELECTORS.btnFsLoop, SELECTORS.btnFsAutoNext, SELECTORS.btnFsMetro]) {
      button.disabled = disabled;
    }
  };

  audioAvailable = true;
  audioReady = false;
  SELECTORS.audioNote.hidden = true;
  SELECTORS.waveformLoading.hidden = false;
  disableTransport(true);
  ensureWaveformSelectionEl();
  renderCustomLoopRange();
  SELECTORS.waveformWrap.onpointerdown = event => {
    if (!ws || event.button !== 0) return;
    const rect = SELECTORS.waveform.getBoundingClientRect();
    if (rect.width <= 0) return;
    const handle = event.target.closest?.(".loop-selection-handle");
    const selection = event.target.closest?.(".loop-selection");
    if (handle && customLoopRange) {
      event.preventDefault();
      const mode = handle.dataset.loopHandle === "start" ? "resize-start" : "resize-end";
      waveformDrag = {
        pointerId: event.pointerId,
        mode,
        anchorTime: mode === "resize-start" ? customLoopRange.end : customLoopRange.start,
        startX: event.clientX,
        currentX: event.clientX,
        moved: true,
      };
      SELECTORS.waveformWrap.setPointerCapture?.(event.pointerId);
      SELECTORS.waveformWrap.classList.add("resizing-loop");
      return;
    }
    if (selection && customLoopRange) {
      event.preventDefault();
      waveformDrag = {
        pointerId: event.pointerId,
        mode: "move",
        startX: event.clientX,
        currentX: event.clientX,
        startTime: getWaveformTimeFromClientX(event.clientX),
        rangeStart: customLoopRange.start,
        rangeEnd: customLoopRange.end,
        moved: false,
      };
      SELECTORS.waveformWrap.setPointerCapture?.(event.pointerId);
      SELECTORS.waveformWrap.classList.add("moving-loop");
      return;
    }
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) return;
    event.preventDefault();
    waveformDrag = {
      pointerId: event.pointerId,
      mode: "create",
      startX: event.clientX,
      currentX: event.clientX,
      moved: false,
    };
    SELECTORS.waveformWrap.setPointerCapture?.(event.pointerId);
  };
  SELECTORS.waveformWrap.onpointermove = event => {
    if (!waveformDrag || waveformDrag.pointerId !== event.pointerId) return;
    waveformDrag.currentX = event.clientX;
    if (waveformDrag.mode === "resize-start" || waveformDrag.mode === "resize-end") {
      const edge = getWaveformTimeFromClientX(waveformDrag.currentX);
      const start = Math.min(waveformDrag.anchorTime, edge);
      const end = Math.max(waveformDrag.anchorTime, edge);
      renderCustomLoopRange({
        start,
        end,
        kind: "custom",
      });
      if (waveformDrag.mode === "resize-start") seekAudio(start, { respectLoopRange: false });
      return;
    }
    if (waveformDrag.mode === "move") {
      if (Math.abs(waveformDrag.currentX - waveformDrag.startX) >= 4) waveformDrag.moved = true;
      if (waveformDrag.moved) renderCustomLoopRange(getMovedLoopRange(waveformDrag, waveformDrag.currentX));
      return;
    }
    if (Math.abs(waveformDrag.currentX - waveformDrag.startX) >= 12) waveformDrag.moved = true;
    if (!waveformDrag.moved) return;
    const start = getWaveformTimeFromClientX(Math.min(waveformDrag.startX, waveformDrag.currentX));
    const end = getWaveformTimeFromClientX(Math.max(waveformDrag.startX, waveformDrag.currentX));
    renderCustomLoopRange({ start, end, kind: "custom" });
  };
  SELECTORS.waveformWrap.onpointerup = event => {
    if (!waveformDrag || waveformDrag.pointerId !== event.pointerId) return;
    const drag = waveformDrag;
    const startX = waveformDrag.startX;
    const endX = waveformDrag.currentX;
    const moved = waveformDrag.moved;
    waveformDrag = null;
    SELECTORS.waveformWrap.releasePointerCapture?.(event.pointerId);
    SELECTORS.waveformWrap.classList.remove("resizing-loop");
    SELECTORS.waveformWrap.classList.remove("moving-loop");
    if (drag.mode === "resize-start" || drag.mode === "resize-end") {
      const edge = getWaveformTimeFromClientX(endX);
      applyCustomLoopRange(
        Math.min(drag.anchorTime, edge),
        Math.max(drag.anchorTime, edge),
      );
      return;
    }
    if (drag.mode === "move") {
      if (!moved) {
        renderCustomLoopRange();
        seekAudio(getWaveformTimeFromClientX(event.clientX));
        return;
      }
      const range = getMovedLoopRange(drag, endX);
      applyCustomLoopRange(range.start, range.end);
      return;
    }
    if (!moved) {
      renderCustomLoopRange();
      seekAudio(getWaveformTimeFromClientX(event.clientX));
      return;
    }
    applyCustomLoopRange(
      getWaveformTimeFromClientX(Math.min(startX, endX)),
      getWaveformTimeFromClientX(Math.max(startX, endX)),
    );
    seekAudio(getWaveformTimeFromClientX(Math.min(startX, endX)));
  };
  SELECTORS.waveformWrap.onpointercancel = event => {
    if (!waveformDrag || waveformDrag.pointerId !== event.pointerId) return;
    waveformDrag = null;
    SELECTORS.waveformWrap.releasePointerCapture?.(event.pointerId);
    SELECTORS.waveformWrap.classList.remove("resizing-loop");
    SELECTORS.waveformWrap.classList.remove("moving-loop");
    renderCustomLoopRange();
  };

  ws.on("decode", () => {
    audioReady = true;
    SELECTORS.waveformLoading.hidden = true;
    disableTransport(false);
    applyCurrentPlaybackRate();
    const duration = ws.getDuration();
    SELECTORS.timeTot.textContent = fmt(duration);
    for (const section of currentData.sections) {
      const color = secColor(section.label);
      getRegions().addRegion({
        start: section.start_time,
        end: Math.min(section.end_time, duration),
        content: localizeSectionLabel(section.label),
        color: rgba(color, 0.15),
        drag: false,
        resize: false,
      });
    }
    renderFourBarGrid();
  });

  ws.on("timeupdate", time => {
    SELECTORS.timeCur.textContent = fmt(time);
    updatePlayingRow(time);
    syncVideoToAudio(time);
    syncStemPlayers(time);
    if (loopOn && ws.isPlaying()) {
      const loopRange = getLoopRange();
      if (loopRange && (time < loopRange.start || time >= loopRange.end)) {
        seekAudio(loopRange.start);
      }
    }
  });

  ws.on("play", () => {
    markCurrentSessionPracticed();
    applyCurrentPlaybackRate();
    syncVideoToAudio(ws.getCurrentTime(), { force: true });
    playVideo();
    playStems();
    if (metroOn) startMetro();
    updatePlayButton();
  });

  ws.on("pause", () => {
    pauseVideo();
    pauseStems();
    stopMetro();
    updatePlayButton();
  });

  ws.on("seeking", () => {
    lastMetroTime = ws.getCurrentTime();
    syncVideoToAudio(lastMetroTime, { force: true });
    syncStemPlayers(lastMetroTime, { force: true });
  });

  ws.on("finish", handlePlaybackFinished);

  ws.on("error", () => {
    audioAvailable = false;
    audioReady = false;
    SELECTORS.waveformLoading.hidden = true;
    pauseVideo();
    pauseStems();
    stopMetro();
    disableTransport(true);
    SELECTORS.audioNote.hidden = false;
    updatePlayButton();
  });

};

const setupControls = () => {
  SELECTORS.btnPlay.onclick = togglePlayback;
  SELECTORS.btnFsPlay.onclick = togglePlayback;
  SELECTORS.btnRestart.onclick = playFromBeginning;
  SELECTORS.btnFsRestart.onclick = playFromBeginning;
  SELECTORS.btnVideoFullscreen.onclick = toggleVideoFullscreen;
  SELECTORS.btnVideoExit.onclick = () => setVideoFullscreen(false);
  SELECTORS.btnLoop.onclick = () => {
    loopOn = !loopOn;
    saveCfg("loop", loopOn);
    if (loopOn && autoNextOn) {
      autoNextOn = false;
      saveCfg(autoNextKey, false);
    }
    updatePlaybackModeButtons();
    if (!loopOn) {
      clearCustomLoopRange();
      return;
    }
    if (selectedIdxs.size) {
      applySectionLoopRange([...selectedIdxs]);
      return;
    }
    updateSelectionUI();
  };
  SELECTORS.btnFsLoop.onclick = SELECTORS.btnLoop.onclick;
  SELECTORS.btnClearRange.onclick = () => clearCustomLoopRange({ clearSelection: true });
  SELECTORS.btnMetro.onclick = () => {
    metroOn = !metroOn;
    saveCfg("metro", metroOn);
    updatePlaybackModeButtons();
    if (metroOn && ws?.isPlaying()) startMetro();
    else stopMetro();
  };
  SELECTORS.btnFsMetro.onclick = SELECTORS.btnMetro.onclick;
  SELECTORS.btnReanalyze.onclick = async () => {
    const sourceVideoId = currentData?.sourceVideoId || currentId;
    if (sourceVideoId && hasServer) await doAnalyze(
      `https://www.youtube.com/watch?v=${sourceVideoId}`,
      true,
      {
        startSec: currentData?.analysisStartSec ?? null,
        endSec: currentData?.analysisEndSec ?? null,
      },
    );
  };
  SELECTORS.btnNewUrl.onclick = () => {
    SELECTORS.inputCard.hidden = !SELECTORS.inputCard.hidden;
    if (!SELECTORS.inputCard.hidden) SELECTORS.urlInput.focus();
  };
  SELECTORS.btnAutoNext.onclick = () => {
    autoNextOn = !autoNextOn;
    saveCfg(autoNextKey, autoNextOn);
    if (autoNextOn && loopOn) {
      loopOn = false;
      saveCfg("loop", false);
      clearCustomLoopRange();
    }
    updatePlaybackModeButtons();
  };
  SELECTORS.btnFsAutoNext.onclick = SELECTORS.btnAutoNext.onclick;
  SELECTORS.btnGenerateStems.onclick = () => generateStems();
  SELECTORS.btnExportStemMix.onclick = () => exportStemMix();
  SELECTORS.btnBpmHalf.onclick = () => {
    if (!currentId) return;
    bpmFactor /= 2;
    saveCfg(bpmCorrectionKey(currentId), bpmFactor);
    applyBpmDisplay();
  };
  SELECTORS.btnBpmDouble.onclick = () => {
    if (!currentId) return;
    bpmFactor *= 2;
    saveCfg(bpmCorrectionKey(currentId), bpmFactor);
    applyBpmDisplay();
  };
  SELECTORS.btnBpmReset.onclick = () => {
    if (!currentId) return;
    bpmFactor = 1;
    saveCfg(bpmCorrectionKey(currentId), bpmFactor);
    applyBpmDisplay();
  };
  SELECTORS.btnClickOffset.onclick = () => {
    if (!currentId) return;
    clickOffsetHalfBeat = !clickOffsetHalfBeat;
    saveCfg(clickOffsetKey(currentId), clickOffsetHalfBeat);
    SELECTORS.btnClickOffset.classList.toggle("active", clickOffsetHalfBeat);
    syncMetronome();
  };
  SELECTORS.btnBpmSave.onclick = async () => {
    if (!currentId || !hasServer) return;
    try {
      SELECTORS.btnBpmSave.disabled = true;
      const response = await fetch(`/results/${currentId}/bpm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ factor: bpmFactor }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `サーバーエラー (${response.status})`);
      saveCfg(bpmCorrectionKey(currentId), 1);
      showResult(data, data.id);
      SELECTORS.status.className = "status ok";
      SELECTORS.status.textContent = "✓ BPM補正を保存しました";
      await loadHistory();
    } catch (error) {
      SELECTORS.status.className = "status err";
      SELECTORS.status.textContent = error.message;
    } finally {
      SELECTORS.btnBpmSave.disabled = false;
    }
  };
  SELECTORS.btnYouTube.onclick = () => {
    const sourceVideoId = currentData?.sourceVideoId || currentId;
    if (sourceVideoId) window.open(`https://www.youtube.com/watch?v=${sourceVideoId}`, "_blank");
  };
  SELECTORS.btnScoreExtractor.onclick = () => {
    const sourceVideoId = currentData?.sourceVideoId || currentId;
    if (!sourceVideoId) return;
    SELECTORS.scoreUrlInput.value = `https://www.youtube.com/watch?v=${sourceVideoId}`;
    setActiveTab("score");
    SELECTORS.scoreUrlInput.focus();
  };

  const setVol = (slider, label, configKey, apply) => {
    const saved = cfg()[configKey] ?? parseInt(slider.value, 10);
    slider.value = saved;
    label.textContent = `${saved}%`;
    apply(saved);
    slider.oninput = () => {
      const value = parseInt(slider.value, 10);
      label.textContent = `${value}%`;
      saveCfg(configKey, value);
      apply(value);
    };
  };

  setVol(SELECTORS.volMusic, SELECTORS.volMusicVal, "volMusic", applyMusicVolume);
  setVol(SELECTORS.volMetro, SELECTORS.volMetroVal, "volMetro", () => {});
  SELECTORS.playbackRate.oninput = () => applyPlaybackRate(SELECTORS.playbackRate.value);
  SELECTORS.btnSpeedReset.onclick = () => applyPlaybackRate(DEFAULT_PLAYBACK_RATE);

  for (const stem of STEM_NAMES) {
    const controls = SELECTORS.stemControls[stem];
    controls.enabled.onclick = () => {
      clearStemMixMode();
      const mix = getStemMix();
      const lastVolumes = getStemLastVolumes();
      const current = Number(mix[stem] ?? DEFAULT_STEM_MIX[stem]) || 0;
      if (current > 0) {
        lastVolumes[stem] = current;
        mix[stem] = 0;
      } else {
        mix[stem] = Math.max(1, Number(lastVolumes[stem]) || DEFAULT_STEM_MIX[stem]);
      }
      saveStemLastVolumes(lastVolumes);
      saveStemMix(mix);
      applyStemMix();
    };
    controls.volume.oninput = () => {
      clearStemMixMode();
      const mix = getStemMix();
      const value = Number(controls.volume.value) || 0;
      mix[stem] = value;
      if (value > 0) {
        const lastVolumes = getStemLastVolumes();
        lastVolumes[stem] = value;
        saveStemLastVolumes(lastVolumes);
      }
      saveStemMix(mix);
      applyStemMix();
    };
    controls.solo.onclick = () => setStemMixMode(stem, "solo");
    controls.focus.onclick = () => setStemMixMode(stem, "focus");
  }
  SELECTORS.btnResetStemMix.onclick = () => {
    clearStemMixMode();
    saveStemMix({ ...DEFAULT_STEM_MIX });
    saveStemLastVolumes({ ...DEFAULT_STEM_MIX });
    applyStemMix();
  };
};

const showResult = (data, id, { autoplay = false } = {}) => {
  currentData = data;
  currentId = id;
  SELECTORS.btnEditSections.hidden = !hasServer || staticLibraryMode;
  SELECTORS.btnEditSections.disabled = !data.sections?.length || !data.total_bars;
  saveCfg(lastStructureSessionKey, id);
  currentPlaybackGroup = findPlaybackGroupForSession(id);
  const assets = sessionAssets(data);
  const isLocalAudio = data.sourceType === "local_audio";
  selectedIdxs = new Set();
  customLoopRange = null;
  playingIdx = -1;
  audioAvailable = true;
  audioReady = false;
  videoAvailable = true;
  loopOn = cfg().loop ?? false;
  metroOn = cfg().metro ?? false;
  autoNextOn = cfg()[autoNextKey] ?? false;
  bpmFactor = getStoredBpmFactor(id);
  clickOffsetHalfBeat = getStoredClickOffset(id);
  playbackRate = clampPlaybackRate(cfg().playbackRate ?? 1);

  SELECTORS.structureWorkspace.hidden = false;
  SELECTORS.playerCard.hidden = false;
  SELECTORS.inputCard.hidden = true;
  SELECTORS.topbarSong.hidden = false;
  SELECTORS.topbarActions.hidden = false;
  SELECTORS.topbarSong.textContent = data.title || "";
  SELECTORS.timeCur.textContent = "00:00";
  SELECTORS.timeTot.textContent = fmt(data.duration || 0);
  updatePlaybackModeButtons();
  SELECTORS.loopInfo.textContent = "";
  SELECTORS.btnNewUrl.hidden = !hasServer;
  SELECTORS.btnAutoNext.hidden = false;
  SELECTORS.btnYouTube.hidden = !hasServer || isLocalAudio;
  SELECTORS.btnScoreExtractor.hidden = !hasServer || isLocalAudio;
  SELECTORS.btnCloudSync.hidden = !hasServer || staticLibraryMode;
  SELECTORS.btnReanalyze.hidden = !hasServer || isLocalAudio;
  SELECTORS.btnClearRange.hidden = true;
  SELECTORS.btnBpmSave.hidden = !hasServer;
  SELECTORS.btnClickOffset.classList.toggle("active", clickOffsetHalfBeat);

  applyPlaybackRate(playbackRate);
  renderStemPanel(assets);
  initWaveSurfer(assets.audio, assets.video, assets.stems);
  setupControls();

  const maxBars = Math.max(...data.sections.map(section => section.bar_count));
  SELECTORS.sections.innerHTML = "";
  data.sections.forEach((section, index) => {
    const color = secColor(section.label);
    const row = document.createElement("div");
    row.className = "sec-row";
    row.innerHTML = `
      <span class="sec-num">${String(index + 1).padStart(2, "0")}</span>
      <span class="sec-dot" style="background:${color}"></span>
      <span class="sec-label">${localizeSectionLabel(section.label)}</span>
      <span class="sec-bars"><span class="subtle">${section.bar_count}小節</span></span>
      <div class="sec-vis"><div class="sec-vis-fill" style="width:${Math.round(section.bar_count / maxBars * 100)}%;background:${color}"></div></div>
      <span class="sec-time">${section.start_time_str}</span>
    `;
    row.onclick = event => {
      if (event.shiftKey && selectedIdxs.size > 0) {
        const indexes = [...selectedIdxs, index];
        const min = Math.min(...indexes);
        const max = Math.max(...indexes);
        const nextIndexes = [];
        for (let i = min; i <= max; i += 1) nextIndexes.push(i);
        if (loopOn) {
          applySectionLoopRange(nextIndexes);
        } else {
          clearCustomLoopRange();
          selectedIdxs = new Set(nextIndexes);
          updateSelectionUI();
        }
      } else {
        if (loopOn) {
          applySectionLoopRange([index]);
        } else {
          clearCustomLoopRange();
          selectedIdxs = new Set([index]);
          updateSelectionUI();
        }
        if (canPlayAudio()) {
          const wasPlaying = ws.isPlaying();
          seekAudio(section.start_time);
          if (!wasPlaying) ws.play();
        }
      }
    };
    SELECTORS.sections.appendChild(row);
  });

  applyBpmDisplay();

  document.querySelectorAll(".si").forEach(element => {
    element.classList.toggle("active", element.dataset.id === id);
  });

  if (autoplay) {
    const startWhenReady = () => {
      if (!canPlayAudio()) return;
      playStems();
      ws.play();
    };
    if (audioReady) startWhenReady();
    else ws?.once?.("decode", startWhenReady);
  }
};

let sectionEditorDraft = [];

const readSectionEditorDraft = () => {
  sectionEditorDraft = [...SELECTORS.sectionEditorRows.querySelectorAll(".section-edit-row")].map(row => ({
    label: row.querySelector("[data-section-field='label']").value.trim(),
    startBar: Number(row.querySelector("[data-section-field='start']").value),
    endBar: Number(row.querySelector("[data-section-field='end']").value),
  }));
};

const renderSectionEditor = () => {
  SELECTORS.sectionEditorRows.innerHTML = sectionEditorDraft.map((section, index) => `
    <div class="section-edit-row" data-section-index="${index}">
      <input data-section-field="label" value="${escapeHtml(section.label)}" aria-label="セクション名 ${index + 1}">
      <input data-section-field="start" type="number" min="1" value="${section.startBar}" aria-label="開始小節 ${index + 1}">
      <input data-section-field="end" type="number" min="1" value="${section.endBar}" aria-label="終了小節 ${index + 1}">
      <div class="section-edit-tools">
        <button type="button" data-section-action="split" title="中央で分割" ${section.startBar >= section.endBar ? "disabled" : ""}>分割</button>
        <button type="button" data-section-action="merge" title="次と結合" ${index === sectionEditorDraft.length - 1 ? "disabled" : ""}>結合</button>
        <button type="button" data-section-action="delete" title="削除" ${sectionEditorDraft.length === 1 ? "disabled" : ""}>削除</button>
      </div>
    </div>
  `).join("");
};

const openSectionEditor = () => {
  if (!hasServer || !currentData?.sections?.length) return;
  sectionEditorDraft = currentData.sections.map(section => ({
    label: section.label,
    startBar: section.start_bar,
    endBar: section.end_bar,
  }));
  SELECTORS.sectionEditorError.textContent = "";
  SELECTORS.btnRestoreSections.disabled = !currentData.automaticSections?.length;
  renderSectionEditor();
  SELECTORS.sectionEditor.showModal();
  lucide.createIcons();
};

const applySectionDraftAction = (index, action) => {
  readSectionEditorDraft();
  sectionEditorDraft = mutateSectionDraft(sectionEditorDraft, index, action);
  renderSectionEditor();
};

const saveSectionEditor = async () => {
  readSectionEditorDraft();
  SELECTORS.sectionEditorError.textContent = "";
  SELECTORS.btnSaveSections.disabled = true;
  try {
    const response = await fetch(`/results/${encodeURIComponent(currentId)}/sections`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sections: sectionEditorDraft }),
    });
    const updated = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(updated.detail || "セクションを保存できませんでした");
    SELECTORS.sectionEditor.close();
    showResult(updated, currentId);
  } catch (error) {
    SELECTORS.sectionEditorError.textContent = error.message;
  } finally {
    SELECTORS.btnSaveSections.disabled = false;
  }
};

const restoreAutomaticSections = async () => {
  if (!confirm("編集内容を破棄して自動解析結果へ戻しますか？")) return;
  SELECTORS.sectionEditorError.textContent = "";
  try {
    const response = await fetch(`/results/${encodeURIComponent(currentId)}/sections`, { method: "DELETE" });
    const updated = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(updated.detail || "自動解析結果へ戻せませんでした");
    SELECTORS.sectionEditor.close();
    showResult(updated, currentId);
  } catch (error) {
    SELECTORS.sectionEditorError.textContent = error.message;
  }
};

const renderStorageReport = report => {
  SELECTORS.storageTotal.textContent = `合計 ${formatBytes(report.totalBytes)}`;
  SELECTORS.storageList.innerHTML = (report.categories || []).map(category => `
    <div class="storage-row">
      <span>${escapeHtml(category.label)}</span>
      <span class="storage-size">${formatBytes(category.bytes)} · ${Number(category.files || 0)}件</span>
      ${category.cleanup
        ? `<button class="storage-clean" type="button" data-storage-clean="${escapeHtml(category.key)}">整理</button>`
        : "<span></span>"}
    </div>
  `).join("");
};

const openStorageDialog = async () => {
  if (!hasServer || staticLibraryMode) return;
  SELECTORS.storageTotal.textContent = "計算中...";
  SELECTORS.storageList.innerHTML = "";
  SELECTORS.storageDialog.showModal();
  lucide.createIcons();
  try {
    const response = await fetch("/storage", { cache: "no-store" });
    const report = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(report.detail || "容量を取得できませんでした");
    renderStorageReport(report);
  } catch (error) {
    SELECTORS.storageTotal.textContent = error.message;
  }
};

const cleanStorageCategory = async key => {
  if (!confirm("再生成可能なキャッシュを削除しますか？")) return;
  const button = SELECTORS.storageList.querySelector(`[data-storage-clean="${CSS.escape(key)}"]`);
  if (button) button.disabled = true;
  try {
    const response = await fetch("/storage/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ categories: [key] }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "キャッシュを整理できませんでした");
    renderStorageReport(result.report);
    SELECTORS.storageTotal.textContent += `（${formatBytes(result.removedBytes)}削除）`;
  } catch (error) {
    alert(error.message);
  } finally {
    if (button) button.disabled = false;
  }
};

const renderSidebar = items => {
  currentSidebarItems = items;
  SELECTORS.sidebarList.innerHTML = "";
  const visibleItems = filterLibraryItems(items, {
    query: SELECTORS.sessionSearch?.value || "",
    filter: SELECTORS.sessionFilter?.value || "all",
  });
  sidebarItemsCount = visibleItems.length;
  const validIds = new Set(items.map(item => item.id));
  selectedSessionIds = new Set([...selectedSessionIds].filter(id => validIds.has(id)));
  if (!selectedSessionIds.has(lastSelectedSessionId)) lastSelectedSessionId = null;
  SELECTORS.sessionPanel.hidden = currentFeature === "score" || items.length === 0;
  if (items.length === 0) return;
  if (visibleItems.length === 0) {
    SELECTORS.sidebarList.innerHTML = `<div class="library-empty">条件に一致する曲がありません</div>`;
    return;
  }

  const folders = cleanFolders(getFolders(), items);
  saveFolders(folders, { remote: false });
  const itemById = new Map(visibleItems.map(item => [item.id, item]));
  const folderedIds = new Set(folders.flatMap(folder => folder.sessionIds || []));
  const toggleFolder = folderId => {
    const next = folders.map(item => item.id === folderId ? { ...item, collapsed: !item.collapsed } : item);
    const toggled = next.find(item => item.id === folderId);
    if (toggled) saveFolderCollapsed(folderId, toggled.collapsed);
    saveFolders(next);
    renderSidebar(items);
  };
  const deleteFolder = folder => {
    if (!confirm(`フォルダー「${folder.name}」を削除しますか？\nセッションは未分類へ移動します。`)) return;
    const next = folders.filter(item => item.id !== folder.id);
    forgetFolderCollapsed(folder.id);
    saveFolders(next);
    renderSidebar(items);
  };
  const renameFolder = folder => {
    const name = prompt("フォルダー名", folder.name)?.trim();
    if (!name || name === folder.name) return;
    const next = folders.map(item => item.id === folder.id ? { ...item, name } : item);
    saveFolders(next);
    renderSidebar(items);
  };

  folders.forEach(folder => {
    const group = document.createElement("div");
    group.className = "sf";
    group.dataset.folderId = folder.id;
    const folderName = escapeHtml(folder.name);
    group.innerHTML = `
      <div class="sf-head">
        <button class="sf-toggle" title="${folder.collapsed ? "展開" : "折りたたむ"}">${folder.collapsed ? "▸" : "▾"}</button>
        <button class="sf-name" title="${folder.collapsed ? "フォルダーを展開" : "フォルダーを折りたたむ"}">${folderName}</button>
      </div>
      <div class="sf-items"></div>
    `;
    const folderItems = group.querySelector(".sf-items");
    const folderHead = group.querySelector(".sf-head");
    folderItems.hidden = !!folder.collapsed;
    const folderVisibleItems = sortLibraryItems((folder.sessionIds || []).map(id => itemById.get(id)).filter(Boolean), SELECTORS.sessionSort?.value || "manual");
    for (const item of folderVisibleItems) {
      folderItems.appendChild(createSessionRow(item, items, folder.id));
    }
    if (hasServer) {
      folderHead.draggable = true;
      folderHead.addEventListener("dragstart", event => {
        event.dataTransfer.setData("application/x-practice-lab-folder", folder.id);
        event.dataTransfer.effectAllowed = "move";
        group.classList.add("dragging");
      });
      folderHead.addEventListener("dragend", clearSidebarDropMarkers);
      group.addEventListener("dragover", event => {
        event.preventDefault();
        if (hasDragType(event, "application/x-practice-lab-folder")) {
          const rect = group.getBoundingClientRect();
          const after = event.clientY > rect.top + rect.height / 2;
          group.classList.toggle("drop-before", !after);
          group.classList.toggle("drop-after", after);
          group.classList.remove("drop");
          return;
        }
        group.classList.add("drop");
      });
      group.addEventListener("dragleave", () => group.classList.remove("drop", "drop-before", "drop-after"));
      group.addEventListener("drop", event => {
        event.preventDefault();
        group.classList.remove("drop", "drop-before", "drop-after");
        const draggedFolderId = event.dataTransfer.getData("application/x-practice-lab-folder");
        if (draggedFolderId) {
          const rect = group.getBoundingClientRect();
          reorderFolder(draggedFolderId, folder.id, items, { after: event.clientY > rect.top + rect.height / 2 });
          clearSidebarDropMarkers();
          return;
        }
        const sessionIds = getDraggedSessionIds(event);
        if (sessionIds.length) reorderSessions(sessionIds, null, folder.id, items);
        clearSidebarDropMarkers();
      });
    }
    group.querySelector(".sf-toggle").onclick = () => toggleFolder(folder.id);
    group.querySelector(".sf-name").onclick = () => toggleFolder(folder.id);
    if (hasServer) {
      folderHead.addEventListener("contextmenu", event => {
        const actions = [
          { label: "名前を変更", run: () => renameFolder(folder) },
          { label: "削除", danger: true, run: () => deleteFolder(folder) },
        ];
        if (selectedSessionIds.size) {
          actions.unshift({
            label: `選択中の${selectedSessionIds.size}件をここへ移動`,
            run: () => reorderSessions([...selectedSessionIds], null, folder.id, items),
          });
        }
        showContextMenu(event, actions);
      });
    }
    SELECTORS.sidebarList.appendChild(group);
  });

  const looseOrder = getRootOrder(items, folderedIds);
  const looseItems = sortLibraryItems(looseOrder.map(id => itemById.get(id)).filter(Boolean), SELECTORS.sessionSort?.value || "manual");
  const loose = document.createElement("div");
  loose.className = "sf sf-root";
  loose.innerHTML = `<div class="sf-head"><span class="sf-root-name">未分類</span></div><div class="sf-items"></div>`;
  const looseList = loose.querySelector(".sf-items");
  if (hasServer) {
    loose.addEventListener("dragover", event => {
      event.preventDefault();
      if (hasDragType(event, "application/x-practice-lab-folder")) {
        loose.classList.add("drop-before");
        loose.classList.remove("drop");
        return;
      }
      loose.classList.add("drop");
    });
    loose.addEventListener("dragleave", () => loose.classList.remove("drop", "drop-before"));
    loose.addEventListener("drop", event => {
      event.preventDefault();
      loose.classList.remove("drop", "drop-before");
      const draggedFolderId = event.dataTransfer.getData("application/x-practice-lab-folder");
      if (draggedFolderId) {
        reorderFolder(draggedFolderId, null, items);
        clearSidebarDropMarkers();
        return;
      }
      const sessionIds = getDraggedSessionIds(event);
      if (!sessionIds.length) return;
      reorderSessions(sessionIds, null, "root", items);
      clearSidebarDropMarkers();
    });
  }
  looseItems.forEach(item => looseList.appendChild(createSessionRow(item, items, "root")));
  SELECTORS.sidebarList.appendChild(loose);
  updateSidebarSelectionUI();
};

const addFolder = async () => {
  const name = prompt("フォルダー名", "新しいフォルダー")?.trim();
  if (!name) return;
  const folders = getFolders();
  folders.push({ id: makeFolderId(), name, collapsed: false, sessionIds: [] });
  saveFolders(folders);
  await loadHistory();
};

if (SELECTORS.btnAddFolder) {
  SELECTORS.btnAddFolder.onclick = addFolder;
}
SELECTORS.btnDeleteSessionSelection.onclick = () => deleteSelectedResults(currentSidebarItems);
SELECTORS.btnClearSessionSelection.onclick = () => {
  selectedSessionIds.clear();
  lastSelectedSessionId = null;
  updateSidebarSelectionUI();
};
SELECTORS.btnMobileLibrary.onclick = openMobileSidebar;
SELECTORS.sidebarScrim.onclick = closeMobileSidebar;

SELECTORS.tabStructure.onclick = () => setActiveTab("structure");
if (!staticLibraryMode) {
  SELECTORS.tabScore.onclick = () => setActiveTab("score");
  SELECTORS.scorePreviewBtn.onclick = loadScorePreview;
  SELECTORS.scoreExtractBtn.onclick = extractScore;
  SELECTORS.scoreUrlInput.addEventListener("keydown", event => {
    if (event.key === "Enter") loadScorePreview();
  });
  SELECTORS.scoreRegionPreset.onchange = () => {
    if (scorePreviewData) loadScorePreview();
  };
  SELECTORS.scoreRegionPercent.onchange = () => {
    if (scorePreviewData) loadScorePreview();
  };
  SELECTORS.scoreTimeMode.onchange = () => {
    SELECTORS.scoreTimeRange.hidden = SELECTORS.scoreTimeMode.value !== "range";
    if (scorePreviewData) loadScorePreview();
  };
  SELECTORS.scoreRegionBox.onpointerdown = event => {
    if (!scorePreviewData || !scoreRegion) return;
    event.preventDefault();
    event.stopPropagation();
    const point = getScorePreviewPoint(event);
    const handle = event.target.dataset.handle || "";
    scoreRegionDrag = {
      pointerId: event.pointerId,
      mode: handle ? "resize" : "move",
      handle,
      startPoint: point,
      startRegion: { ...scoreRegion },
    };
    SELECTORS.scoreRegionBox.classList.toggle("resizing", !!handle);
    SELECTORS.scoreRegionBox.classList.toggle("dragging", !handle);
    SELECTORS.scoreRegionBox.setPointerCapture?.(event.pointerId);
  };
  SELECTORS.scoreRegionBox.onpointermove = event => {
    if (!scoreRegionDrag || scoreRegionDrag.pointerId !== event.pointerId) return;
    const point = getScorePreviewPoint(event);
    const dx = point.x - scoreRegionDrag.startPoint.x;
    const dy = point.y - scoreRegionDrag.startPoint.y;
    const start = scoreRegionDrag.startRegion;
    if (scoreRegionDrag.mode === "resize") {
      const handle = scoreRegionDrag.handle;
      const startLeft = start.x;
      const startTop = start.y;
      const startRight = start.x + start.width;
      const startBottom = start.y + start.height;
      scoreRegion = regionFromEdges({
        left: handle.includes("w") ? startLeft + dx : startLeft,
        top: handle.includes("n") ? startTop + dy : startTop,
        right: handle.includes("e") ? startRight + dx : startRight,
        bottom: handle.includes("s") ? startBottom + dy : startBottom,
        anchorX: handle.includes("e") ? "left" : "right",
        anchorY: handle.includes("s") ? "top" : "bottom",
      });
    } else {
      scoreRegion = clampScoreRegion({
        ...start,
        x: start.x + dx,
        y: start.y + dy,
      });
    }
    renderScoreRegion();
  };
  SELECTORS.scoreRegionBox.onpointerup = event => {
    if (!scoreRegionDrag || scoreRegionDrag.pointerId !== event.pointerId) return;
    scoreRegionDrag = null;
    SELECTORS.scoreRegionBox.classList.remove("dragging", "resizing");
    SELECTORS.scoreRegionBox.releasePointerCapture?.(event.pointerId);
  };
  SELECTORS.scoreRegionBox.onpointercancel = event => {
    if (!scoreRegionDrag || scoreRegionDrag.pointerId !== event.pointerId) return;
    scoreRegionDrag = null;
    SELECTORS.scoreRegionBox.classList.remove("dragging", "resizing");
    SELECTORS.scoreRegionBox.releasePointerCapture?.(event.pointerId);
  };
}

const loadHistory = async () => {
  try {
    const manifestUrl = staticLibraryMode ? STATIC_MANIFEST_URL : "results/manifest.json";
    const response = await fetch(manifestUrl, { cache: "no-store" });
    if (!response.ok) return;
    const items = await response.json();
    renderSidebar(items);
    return items;
  } catch {
    renderSidebar([]);
  }
  return [];
};

const restoreLastStructureSession = async items => {
  if (!Array.isArray(items) || items.length === 0 || currentId) return;
  setActiveTab("structure");
  const lastId = cfg()[lastStructureSessionKey];
  const session = items.find(item => item.id === lastId) || items[0];
  await loadResult(session);
};

const loadResult = async (session, { autoplay = false } = {}) => {
  const id = typeof session === "string" ? session : session.id;
  const assets = sessionAssets(typeof session === "string" ? { id } : session);
  const response = await fetch(assets.result, { cache: "no-store" });
  if (!response.ok) {
    if (hasServer && confirm("解析データが見つかりません。再解析しますか？")) {
      await doAnalyze(`https://www.youtube.com/watch?v=${id}`, true);
    }
    return;
  }
  showResult(await response.json(), id, { autoplay });
};

const deleteResult = async (id, currentList) => {
  if (!hasServer) {
    alert("サーバー接続が必要です");
    return;
  }
  if (!confirm("このセッションと音声ファイルを削除しますか？")) return;
  try {
    const response = await fetch(`/results/${encodeURIComponent(id)}`, { method: "DELETE" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `サーバーエラー (${response.status})`);
    selectedSessionIds.delete(id);
    renderSidebar(currentList.filter(item => item.id !== id));
  } catch (error) {
    alert(`削除に失敗しました: ${error.message}`);
  }
};

const deleteSelectedResults = async currentList => {
  if (!hasServer) {
    alert("サーバー接続が必要です");
    return;
  }
  const ids = getSidebarOrderedSessionIds(currentList).filter(id => selectedSessionIds.has(id));
  if (!ids.length) return;
  if (!confirm(`選択した${ids.length}件のセッションと音声ファイルを削除しますか？`)) return;

  SELECTORS.btnDeleteSessionSelection.disabled = true;
  try {
    const response = await fetch("/results", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `サーバーエラー (${response.status})`);
    const deletedIds = new Set(payload.deleted || ids);
    selectedSessionIds = new Set([...selectedSessionIds].filter(id => !deletedIds.has(id)));
    lastSelectedSessionId = null;
    renderSidebar(currentList.filter(item => !deletedIds.has(item.id)));
  } catch (error) {
    alert(`一括削除に失敗しました: ${error.message}`);
  } finally {
    SELECTORS.btnDeleteSessionSelection.disabled = false;
  }
};

const renameSession = async (item, currentList) => {
  if (!hasServer) {
    alert("サーバー接続が必要です");
    return;
  }
  const title = prompt("セッション名", item.title)?.trim();
  if (!title || title === item.title) return;
  const nextList = currentList.map(entry => entry.id === item.id ? { ...entry, title } : entry);
  renderSidebar(nextList);
  const previousData = currentId === item.id ? currentData : null;
  if (currentId === item.id) {
    currentData = { ...currentData, title };
    SELECTORS.topbarSong.textContent = title;
  }
  try {
    const response = await fetch(`/results/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "名前の変更に失敗しました");
    if (currentId === item.id) currentData = data;
  } catch (error) {
    renderSidebar(currentList);
    if (currentId === item.id && previousData) {
      currentData = previousData;
      SELECTORS.topbarSong.textContent = previousData.title || item.title;
    }
    alert(error.message);
  }
};

const queueStemGeneration = async (sessionId, { title = "", silent = false, refreshCurrent = false } = {}) => {
  if (!sessionId || !hasServer || staticLibraryMode) return null;
  if (refreshCurrent) {
    SELECTORS.btnGenerateStems.disabled = true;
    SELECTORS.stemStatus.className = "stem-status";
    SELECTORS.stemStatus.innerHTML = `<span class="spin"></span>生成中`;
  }
  SELECTORS.status.className = "status";
  if (!silent) SELECTORS.status.innerHTML = `<span class="spin"></span>パートを生成中...`;
  try {
    const response = await fetch(`/results/${sessionId}/stems`, { method: "POST" });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `サーバーエラー (${response.status})`);
    trackQueuedJob(submitted.jobId, { label: `パート生成 · ${title || sessionId}` });
    const data = await waitForJobResult(submitted.jobId);
    if (refreshCurrent || currentId === data.id) showResult(data, data.id);
    SELECTORS.status.className = "status ok";
    SELECTORS.status.textContent = "✓ パートの準備ができました";
    SELECTORS.jobCard.hidden = false;
    SELECTORS.jobStage.textContent = "完了";
    SELECTORS.jobMessage.textContent = "パートの準備ができました";
    await loadHistory();
    return data;
  } catch (error) {
    stopJobPolling();
    SELECTORS.status.className = "status err";
    SELECTORS.status.textContent = error.message;
    if (refreshCurrent || currentId === sessionId) {
      SELECTORS.stemStatus.className = "stem-status err";
      SELECTORS.stemStatus.textContent = error.message;
    }
    SELECTORS.jobCard.hidden = false;
    SELECTORS.jobStage.textContent = "エラー";
    SELECTORS.jobMessage.textContent = error.message;
    return null;
  } finally {
    if (refreshCurrent) SELECTORS.btnGenerateStems.disabled = false;
  }
};

const generateStems = async ({ silent = false } = {}) =>
  queueStemGeneration(currentId, { title: currentData?.title || currentId, silent, refreshCurrent: true });

const doAnalyze = async (url, force = false, rangeOverride = null) => {
  if (!url) return;
  const videoId = extractVideoId(url);
  let range;
  try {
    range = rangeOverride || getAnalysisTimePayload();
  } catch (error) {
    SELECTORS.status.className = "status err";
    SELECTORS.status.textContent = error.message;
    return;
  }
  SELECTORS.inputCard.hidden = false;
  SELECTORS.analyzeBtn.disabled = true;
  SELECTORS.status.className = "status";
  SELECTORS.status.innerHTML = `<span class="spin"></span>${force ? "再解析を処理一覧へ追加中..." : "解析を処理一覧へ追加中..."} `;
  try {
    const response = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, force, ...range }),
    });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `サーバーエラー (${response.status})`);
    SELECTORS.status.className = "status ok";
    SELECTORS.status.textContent = `✓ ${force ? "再解析" : "解析"}を追加しました`;
    trackQueuedJob(submitted.jobId, {
      label: `${force ? "再解析" : "解析"} · ${videoId || submitted.jobId}${range.startSec !== null || range.endSec !== null ? ` · ${range.startSec ?? 0}秒–${range.endSec ?? "末尾"}` : ""}`,
      onDone: async data => {
        if (!data) return;
        showResult(data, data.id);
        SELECTORS.status.className = data.cached ? "status ok" : "status";
        SELECTORS.status.textContent = data.cached ? "✓ 保存済みの解析結果を読み込みました" : "✓ 解析が完了しました";
        await loadHistory();
        if (force || !hasStemAssets(data.assets)) {
          await queueStemGeneration(data.id, { title: data.title || data.id, silent: true });
        }
      },
      onError: error => {
        SELECTORS.status.className = "status err";
        SELECTORS.status.textContent = error.message;
      },
    });
  } catch (error) {
    SELECTORS.status.className = "status err";
    SELECTORS.status.textContent = error.message;
  } finally {
    SELECTORS.analyzeBtn.disabled = false;
  }
};

const doAnalyzeFile = async file => {
  if (!file) return;
  if (!/\.(wav|m4a|mp3|flac|aac|ogg)$/i.test(file.name)) {
    SELECTORS.status.className = "status err";
    SELECTORS.status.textContent = "WAV、M4A、MP3、FLAC、AAC、OGGに対応しています";
    return;
  }
  if (file.size > 500 * 1024 * 1024) {
    SELECTORS.status.className = "status err";
    SELECTORS.status.textContent = "音声ファイルは500MB以下にしてください";
    return;
  }

  SELECTORS.inputCard.hidden = false;
  SELECTORS.analyzeBtn.disabled = true;
  SELECTORS.btnAudioFile.disabled = true;
  SELECTORS.status.className = "status";
  SELECTORS.status.innerHTML = `<span class="spin"></span>「${escapeHtml(file.name)}」をアップロードしています...`;
  try {
    const body = new FormData();
    body.append("file", file, file.name);
    const response = await fetch("/analyze-file", { method: "POST", body });
    const submitted = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(submitted.detail || `サーバーエラー (${response.status})`);
    SELECTORS.status.className = "status ok";
    SELECTORS.status.textContent = "✓ 音声ファイルの解析を追加しました";
    trackQueuedJob(submitted.jobId, {
      label: `音声解析 · ${file.name}`,
      onDone: async data => {
        if (!data) return;
        showResult(data, data.id);
        SELECTORS.status.className = "status ok";
        SELECTORS.status.textContent = "✓ 音声ファイルの解析が完了しました";
        await loadHistory();
        if (!hasStemAssets(data.assets)) {
          await queueStemGeneration(data.id, { title: data.title || data.id, silent: true });
        }
      },
      onError: error => {
        SELECTORS.status.className = "status err";
        SELECTORS.status.textContent = error.message;
      },
    });
  } catch (error) {
    SELECTORS.status.className = "status err";
    SELECTORS.status.textContent = error.message;
  } finally {
    SELECTORS.analyzeBtn.disabled = false;
    SELECTORS.btnAudioFile.disabled = false;
    SELECTORS.audioFileInput.value = "";
  }
};

const detectServer = async () => {
  if (APP_CONFIG.mode === "static") {
    hasServer = false;
    staticLibraryMode = true;
  } else {
    try {
      const response = await fetch("/healthz", { signal: AbortSignal.timeout(2000) });
      hasServer = response.ok;
      staticLibraryMode = !hasServer && !!STATIC_MANIFEST_URL;
    } catch {
      hasServer = false;
      staticLibraryMode = !!STATIC_MANIFEST_URL;
    }
  }

  if (staticLibraryMode) {
    setActiveTab("structure");
    SELECTORS.inputCard.hidden = true;
    SELECTORS.offlineBadge.hidden = false;
    SELECTORS.offlineBadge.textContent = "ライブラリ";
    SELECTORS.btnReanalyze.hidden = true;
    SELECTORS.btnCloudSync.hidden = true;
    SELECTORS.btnBpmSave.hidden = true;
    SELECTORS.btnAddFolder.hidden = true;
    SELECTORS.btnStorage.hidden = true;
    setScoreFeatureVisible(false);
    SELECTORS.status.className = "status ok";
    SELECTORS.status.textContent = "静的ライブラリモード";
    return;
  }

  if (!hasServer) {
    SELECTORS.inputCard.hidden = true;
    SELECTORS.offlineBadge.hidden = false;
    SELECTORS.btnReanalyze.hidden = true;
    SELECTORS.btnCloudSync.hidden = true;
    SELECTORS.btnStorage.hidden = true;
    return;
  }

  SELECTORS.btnCloudSync.hidden = false;
  SELECTORS.btnStorage.hidden = false;
};

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    hideContextMenu();
    setVideoFullscreen(false);
    closeMobileSidebar();
  }
  if (event.key === "Escape" && customLoopRange) {
    clearCustomLoopRange();
    return;
  }
  if (event.code === "Space" && event.target.tagName !== "INPUT") {
    event.preventDefault();
    if (currentFeature !== "structure") return;
    togglePlayback();
  }
  if (event.shiftKey && event.target.tagName !== "INPUT" && (event.key === ">" || event.code === "Period")) {
    event.preventDefault();
    nudgePlaybackRate(PLAYBACK_RATE_STEP);
    return;
  }
  if (event.shiftKey && event.target.tagName !== "INPUT" && (event.key === "<" || event.code === "Comma")) {
    event.preventDefault();
    nudgePlaybackRate(-PLAYBACK_RATE_STEP);
    return;
  }
  if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && event.target.tagName !== "INPUT") {
    if (currentFeature !== "structure" || !ws) return;
    event.preventDefault();
    seekAudio(ws.getCurrentTime() + (event.key === "ArrowRight" ? 5 : -5));
  }
});
document.addEventListener("click", hideContextMenu);
SELECTORS.contextMenu?.addEventListener("click", event => event.stopPropagation());

SELECTORS.analyzeBtn.addEventListener("click", () => doAnalyze(SELECTORS.urlInput.value.trim()));
SELECTORS.analysisTimeMode.addEventListener("change", () => {
  SELECTORS.analysisTimeRange.hidden = SELECTORS.analysisTimeMode.value !== "range";
});
SELECTORS.btnAudioFile.addEventListener("click", () => SELECTORS.audioFileInput.click());
SELECTORS.audioFileInput.addEventListener("change", () => doAnalyzeFile(SELECTORS.audioFileInput.files?.[0]));
let audioDragDepth = 0;
SELECTORS.inputCard.addEventListener("dragenter", event => {
  if (!event.dataTransfer?.types?.includes("Files")) return;
  event.preventDefault();
  audioDragDepth += 1;
  SELECTORS.inputCard.classList.add("audio-drag");
});
SELECTORS.inputCard.addEventListener("dragover", event => {
  if (!event.dataTransfer?.types?.includes("Files")) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
});
SELECTORS.inputCard.addEventListener("dragleave", () => {
  audioDragDepth = Math.max(0, audioDragDepth - 1);
  if (!audioDragDepth) SELECTORS.inputCard.classList.remove("audio-drag");
});
SELECTORS.inputCard.addEventListener("drop", event => {
  event.preventDefault();
  audioDragDepth = 0;
  SELECTORS.inputCard.classList.remove("audio-drag");
  doAnalyzeFile(event.dataTransfer?.files?.[0]);
});
SELECTORS.scoreProcessingMode?.addEventListener("change", syncScoreOptionAvailability);
SELECTORS.btnCloudSync?.addEventListener("click", syncCloudLibrary);
SELECTORS.btnStorage?.addEventListener("click", openStorageDialog);
SELECTORS.storageList?.addEventListener("click", event => {
  const button = event.target.closest("[data-storage-clean]");
  if (button) cleanStorageCategory(button.dataset.storageClean);
});
SELECTORS.btnEditSections?.addEventListener("click", openSectionEditor);
SELECTORS.btnSaveSections?.addEventListener("click", saveSectionEditor);
SELECTORS.btnRestoreSections?.addEventListener("click", restoreAutomaticSections);
SELECTORS.sectionEditorRows?.addEventListener("click", event => {
  const button = event.target.closest("[data-section-action]");
  const row = button?.closest("[data-section-index]");
  if (!button || !row) return;
  applySectionDraftAction(Number(row.dataset.sectionIndex), button.dataset.sectionAction);
});
SELECTORS.sessionSearch?.addEventListener("input", () => renderSidebar(currentSidebarItems));
SELECTORS.sessionFilter?.addEventListener("change", () => renderSidebar(currentSidebarItems));
SELECTORS.sessionSort?.addEventListener("change", () => renderSidebar(currentSidebarItems));
SELECTORS.queueList?.addEventListener("click", event => {
  const button = event.target.closest("[data-job-id]");
  if (!button) return;
  if (button.dataset.jobAction === "view-score") {
    const item = trackedJobs.get(button.dataset.jobId);
    const result = item?.status?.result;
    if (!result) return;
    renderScoreOutputs(result);
    SELECTORS.scoreResult.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (button.dataset.jobAction === "resume") {
    resumeQueuedJob(button.dataset.jobId);
    return;
  }
  cancelQueuedJob(button.dataset.jobId);
});
SELECTORS.scoreRegenerateBtn?.addEventListener("click", () => regenerateScore());
SELECTORS.scoreEditSettingsBtn?.addEventListener("click", () => editScoreSettings());
SELECTORS.scoreHistoryList?.addEventListener("click", async event => {
  const remove = event.target.closest("[data-score-history-remove]");
  if (remove) {
    event.stopPropagation();
    removeScoreHistory(remove.dataset.scoreHistoryRemove);
    return;
  }
  const edit = event.target.closest("[data-score-history-edit]");
  if (edit) {
    event.stopPropagation();
    const item = getScoreHistory().find(entry => entry.id === edit.dataset.scoreHistoryEdit);
    if (!item?.result) return;
    const result = await fetchLatestScoreResult(item.result);
    if (result !== item.result) updateScoreHistoryResult(item.id, result);
    renderScoreOutputs(result);
    closeMobileSidebar();
    await editScoreSettings(result);
    return;
  }
  const regenerate = event.target.closest("[data-score-history-regenerate]");
  if (regenerate) {
    event.stopPropagation();
    const item = getScoreHistory().find(entry => entry.id === regenerate.dataset.scoreHistoryRegenerate);
    if (!item?.result) return;
    const result = await fetchLatestScoreResult(item.result);
    if (result !== item.result) updateScoreHistoryResult(item.id, result);
    renderScoreOutputs(result);
    closeMobileSidebar();
    await regenerateScore(result);
    return;
  }
  const row = event.target.closest("[data-score-history-id]");
  if (!row) return;
  const item = getScoreHistory().find(entry => entry.id === row.dataset.scoreHistoryId);
  if (!item?.result) return;
  const result = await fetchLatestScoreResult(item.result);
  if (result !== item.result) updateScoreHistoryResult(item.id, result);
  renderScoreOutputs(result);
  SELECTORS.scoreResult.scrollIntoView({ behavior: "smooth", block: "start" });
  closeMobileSidebar();
});
SELECTORS.scoreHistoryList?.addEventListener("keydown", event => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("[data-score-history-id]");
  if (!row) return;
  event.preventDefault();
  row.click();
});
SELECTORS.urlInput.addEventListener("keydown", event => {
  if (event.key === "Enter") doAnalyze(SELECTORS.urlInput.value.trim());
});

lucide.createIcons();
syncScoreOptionAvailability();
renderScoreHistory();
await detectServer();
await restoreInterruptedJobs();
await loadSharedFolders();
await restoreLastStructureSession(await loadHistory());
