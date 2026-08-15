import { expect, test } from "@playwright/test";

const silentWav = (seconds = 1, sampleRate = 8000) => {
  const samples = Math.round(seconds * sampleRate);
  const buffer = Buffer.alloc(44 + samples * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + samples * 2, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(samples * 2, 40);
  return buffer;
};

const baselineStems = Object.fromEntries(
  ["vocals", "drums", "bass", "other"].map(name => [name, `/stems/e2e-baseline/${name}.wav`]),
);
const baselineSession = {
  id: "e2e-baseline",
  title: "E2E Baseline",
  bpm: 120,
  date: "2026-08-16",
  assets: { stems: baselineStems },
};
const baselineResult = {
  ...baselineSession,
  total_bars: 1,
  duration: 1,
  sections: [{ label: "verse", start_bar: 1, end_bar: 1, bar_count: 1, start_time: 0, end_time: 1, start_time_str: "00:00" }],
  beats: [0],
  downbeats: [0],
  assets: { stems: baselineStems },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/cloud/status", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ configured: true, bucket: "e2e-bucket" }),
  }));
  await page.route("**/results/manifest.json", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify([baselineSession]),
  }));
  await page.route("**/results/e2e-baseline.json", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(baselineResult),
  }));
  await page.route("**/audio/e2e-baseline.mp3", route => route.abort());
  await page.route("**/stems/e2e-baseline/*.wav", route => route.fulfill({
    contentType: "audio/wav",
    body: silentWav(),
  }));
});

test("主要画面をネットワークCDNなしで開ける", async ({ page }) => {
  const dependencyRequests = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (["unpkg.com", "fonts.googleapis.com", "fonts.gstatic.com"].includes(url.hostname)) {
      dependencyRequests.push(url.href);
    }
  });

  await page.goto("/");
  await expect(page).toHaveTitle("PracticeLab");
  await expect(page.locator("#analyze-btn")).toBeAttached();
  await expect(page.getByRole("button", { name: "楽譜抽出", exact: true })).toBeVisible();
  await expect(page.locator("#btn-audio-file svg")).toBeAttached();
  expect(dependencyRequests).toEqual([]);
});

test("可視操作を小さく潰さず文字を切らない", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/");
  const issues = await page.locator("button").evaluateAll(buttons => buttons
    .filter(button => {
      const style = getComputedStyle(button);
      const rect = button.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    })
    .map(button => {
      const rect = button.getBoundingClientRect();
      return {
        id: button.id,
        width: rect.width,
        height: rect.height,
        clipped: button.scrollWidth > button.clientWidth + 1 || button.scrollHeight > button.clientHeight + 1,
        outside: rect.left < -1 || rect.right > innerWidth + 1,
      };
    })
    .filter(button => button.width < 30 || button.height < 30 || button.clipped || button.outside));
  expect(issues).toEqual([]);
});

test("同期ラベルをボタン中央に配置する", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#btn-cloud-sync")).toBeVisible();
  await expect(page.locator("#btn-cloud-sync .topbar-sync-content svg")).toBeVisible();
  const centers = await page.locator("#btn-cloud-sync").evaluate(button => {
    const content = button.querySelector(".topbar-sync-content");
    const icon = content.querySelector("svg");
    const buttonBox = button.getBoundingClientRect();
    const contentBox = content.getBoundingClientRect();
    const iconBox = icon.getBoundingClientRect();
    return {
      button: buttonBox.left + buttonBox.width / 2,
      content: contentBox.left + contentBox.width / 2,
      iconWidth: iconBox.width,
      iconVisible: getComputedStyle(icon).display !== "none" && getComputedStyle(icon).opacity === "1",
    };
  });
  expect(Math.abs(centers.button - centers.content)).toBeLessThanOrEqual(1);
  expect(centers.iconWidth).toBeGreaterThanOrEqual(13);
  expect(centers.iconVisible).toBe(true);
});

test("曲構成と楽譜抽出を切り替えられる", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "楽譜抽出", exact: true }).click();
  await expect(page.locator("#score-panel")).toBeVisible();
  await page.getByRole("button", { name: "曲構成", exact: true }).click();
  await expect(page.locator("#structure-panel")).toBeVisible();
});

test("パート書き出し操作を右パネル内に収める", async ({ page }) => {
  await page.goto("/");
  const panel = page.locator("#stem-panel");
  const scope = page.locator("#stem-export-scope");
  const exportButton = page.locator("#btn-export-stem-mix");
  await expect(panel).toBeVisible();
  await expect(scope).toBeVisible();
  await expect(exportButton).toBeVisible();
  const panelBox = await panel.boundingBox();
  const scopeBox = await scope.boundingBox();
  const exportBox = await exportButton.boundingBox();
  expect(scopeBox.width).toBeGreaterThanOrEqual(88);
  expect(exportBox.x + exportBox.width).toBeLessThanOrEqual(panelBox.x + panelBox.width);
});

test("入力ポップアップをアプリ内の画面として表示する", async ({ page }) => {
  const browserDialogs = [];
  page.on("dialog", dialog => browserDialogs.push(dialog.type()));

  await page.goto("/");
  await page.getByRole("button", { name: "新しいフォルダー" }).click();
  const dialog = page.getByRole("dialog", { name: "フォルダーを追加" });
  await expect(dialog).toBeVisible();
  const closeButton = dialog.getByRole("button", { name: "閉じる" });
  await expect(closeButton).toHaveCSS("width", "34px");
  await expect(closeButton).toHaveCSS("height", "34px");
  await expect(closeButton).not.toHaveCSS("background-color", "rgb(255, 255, 255)");
  const box = await dialog.boundingBox();
  const viewport = page.viewportSize();
  expect(Math.abs((box.x + box.width / 2) - viewport.width / 2)).toBeLessThan(3);
  expect(Math.abs((box.y + box.height / 2) - viewport.height / 2)).toBeLessThan(3);
  await expect(dialog.getByRole("textbox", { name: "フォルダー名" })).toHaveValue("新しいフォルダー");
  await dialog.getByRole("button", { name: "キャンセル" }).click();
  await expect(dialog).toBeHidden();
  expect(browserDialogs).toEqual([]);
});

test("新しい解析と再解析をプレイヤーを押し下げないモーダルで開く", async ({ page }) => {
  const session = { id: "analysis-modal", title: "Modal Test", bpm: 120, date: "2026-08-16" };
  const result = {
    ...session,
    sourceVideoId: "D8AZyKMBVVY",
    total_bars: 1,
    duration: 4,
    sections: [{ label: "verse", start_bar: 1, end_bar: 1, bar_count: 1, start_time: 0, end_time: 4, start_time_str: "00:00" }],
    beats: [],
    downbeats: [0],
  };
  await page.route("**/results/manifest.json", route => route.fulfill({ contentType: "application/json", body: JSON.stringify([session]) }));
  await page.route("**/results/analysis-modal.json", route => route.fulfill({ contentType: "application/json", body: JSON.stringify(result) }));
  await page.route("**/audio/analysis-modal.mp3", route => route.abort());

  await page.goto("/");
  await expect(page.locator("#player-card")).toBeVisible();
  await expect(page.getByRole("button", { name: "この曲を再解析" })).toBeVisible();
  const playerBefore = await page.locator("#player-card").boundingBox();
  await page.getByRole("button", { name: "新しい解析", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "練習したい曲を追加" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "解析画面を閉じる" })).toBeVisible();
  const playerWhileOpen = await page.locator("#player-card").boundingBox();
  expect(playerWhileOpen.y).toBe(playerBefore.y);
  await dialog.getByRole("button", { name: "解析画面を閉じる" }).click();

  await page.getByRole("button", { name: "この曲を再解析" }).click();
  await expect(page.getByRole("dialog", { name: "この曲を再解析" })).toBeVisible();
  await expect(page.locator("#url-input")).toHaveValue("https://www.youtube.com/watch?v=D8AZyKMBVVY");
  await expect(page.locator("#analyze-btn")).toHaveText("再解析を開始");
});

test("再起動で中断したジョブを利用者が再開できる", async ({ page }) => {
  await page.route("**/jobs?recoverable=true", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify([{
      id: "recovery-test",
      stage: "interrupted",
      message: "Application restarted; resume when ready",
      description: "Queued analysis",
      kind: "analysis",
      done: true,
      interrupted: true,
      resumable: true,
      started_at: Date.now() / 1000,
    }]),
  }));
  await page.route("**/jobs/recovery-test/resume", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ jobId: "recovery-test", stage: "queued", message: "Queued analysis" }),
  }));

  await page.goto("/");
  const resume = page.getByRole("button", { name: "再開", exact: true });
  await expect(resume).toBeVisible();
  await resume.click();
  await expect(resume).toBeHidden();
});

test("曲名とタグでライブラリを検索できる", async ({ page }) => {
  const session = {
    id: "library-test",
    title: "Midnight Practice",
    bpm: 120,
    date: "2026-08-10",
    tags: ["ライブ"],
  };
  await page.route("**/results/manifest.json", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify([session]),
  }));
  await page.route("**/results/library-test.json", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ ...session, total_bars: 0, duration: 0, sections: [], beats: [], downbeats: [] }),
  }));
  await page.route("**/audio/library-test.mp3", route => route.abort());

  await page.goto("/");
  const search = page.getByRole("searchbox", { name: "曲名・タグを検索" });
  await expect(page.locator("#sidebar-list").getByText("Midnight Practice", { exact: true })).toBeVisible();
  await search.fill("ライブ");
  await expect(page.locator("#sidebar-list").getByText("Midnight Practice", { exact: true })).toBeVisible();
  await search.fill("存在しない曲");
  await expect(page.getByText("条件に一致する曲がありません", { exact: true })).toBeVisible();
});

test("セクションを分割して保存できる", async ({ page }) => {
  const session = { id: "section-test", title: "Section Test", bpm: 120, date: "2026-08-10" };
  const result = {
    ...session,
    total_bars: 4,
    duration: 4,
    sections: [{ label: "verse", start_bar: 1, end_bar: 4, bar_count: 4, start_time: 0, end_time: 4, start_time_str: "00:00" }],
    beats: [],
    downbeats: [0, 1, 2, 3],
  };
  let saved = null;
  await page.route("**/results/manifest.json", route => route.fulfill({ contentType: "application/json", body: JSON.stringify([session]) }));
  await page.route("**/results/section-test.json", route => route.fulfill({ contentType: "application/json", body: JSON.stringify(result) }));
  await page.route("**/audio/section-test.mp3", route => route.fulfill({ contentType: "audio/wav", body: silentWav() }));
  await page.route("**/results/section-test/sections", async route => {
    if (route.request().method() !== "PUT") return route.continue();
    saved = route.request().postDataJSON();
    const sections = saved.sections.map(section => ({
      label: section.label,
      start_bar: section.startBar,
      end_bar: section.endBar,
      bar_count: section.endBar - section.startBar + 1,
      start_time: section.startBar - 1,
      end_time: section.endBar,
      start_time_str: `00:0${section.startBar - 1}`,
    }));
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...result, sections, automaticSections: result.sections }) });
  });

  await page.goto("/");
  await page.locator("#btn-edit-sections").click();
  await expect(page.getByText("区間を選択", { exact: true })).toBeVisible();
  await expect(page.getByLabel("曲をプレビュー")).toBeVisible();
  await expect(page.getByRole("slider", { name: "曲の再生位置" })).toBeVisible();
  await expect(page.getByRole("slider", { name: "再生インジケーター" })).toBeVisible();
  await expect(page.locator("#section-editor-waveform")).toBeVisible();
  await expect(page.locator(".section-editor-stage #section-editor-waveform")).toHaveCount(1);
  await expect(page.locator(".section-editor-grid-minor")).toHaveCount(1);
  await expect(page.locator(".section-editor-grid-major")).toHaveCount(1);
  await expect(page.locator(".section-editor-wave-texture, .section-editor-wave-base")).toHaveCount(0);
  const playhead = page.getByRole("slider", { name: "再生インジケーター" });
  await expect.poll(async () => Number(await playhead.getAttribute("aria-valuemax"))).toBeGreaterThan(0);
  const playheadBox = await playhead.boundingBox();
  const stageBox = await page.locator(".section-editor-stage").boundingBox();
  expect(playheadBox).not.toBeNull();
  expect(stageBox).not.toBeNull();
  await page.mouse.move(playheadBox.x + playheadBox.width / 2, playheadBox.y + 18);
  await page.mouse.down();
  await page.mouse.move(stageBox.x + stageBox.width * .7, playheadBox.y + 18, { steps: 6 });
  await page.mouse.up();
  await expect.poll(async () => Number(await playhead.getAttribute("aria-valuenow"))).toBeGreaterThan(.5);
  await expect(page.getByLabel("選択中のセクション名")).toHaveValue("Aメロ");
  await page.getByRole("button", { name: "中央で分割", exact: true }).click();
  await expect(page.locator(".section-editor-segment")).toHaveCount(2);
  await expect(page.getByLabel("選択中のセクション名")).toHaveValue("Aメロ");
  await page.locator("#btn-save-sections").click();
  await expect.poll(() => saved?.sections?.length).toBe(2);
  expect(saved.sections.map(section => [section.startBar, section.endBar])).toEqual([[1, 2], [3, 4]]);
  expect(saved.sections.map(section => section.label)).toEqual(["Aメロ", "Aメロ"]);
});

test("容量を確認して再生成可能なキャッシュだけを整理できる", async ({ page }) => {
  let cleanupRequest = null;
  const report = {
    totalBytes: 3072,
    categories: [
      { key: "work", label: "作業キャッシュ", bytes: 1024, files: 2, cleanup: true },
      { key: "source-audio", label: "元音声", bytes: 2048, files: 1, cleanup: false },
    ],
  };
  await page.route("**/storage", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(report),
  }));
  await page.route("**/storage/cleanup", async route => {
    cleanupRequest = route.request().postDataJSON();
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ removedBytes: 1024, removedFiles: 2, report: { ...report, totalBytes: 2048, categories: report.categories.map(category => category.key === "work" ? { ...category, bytes: 0, files: 0 } : category) } }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "容量とキャッシュ" }).click();
  await expect(page.getByText("作業キャッシュ", { exact: true })).toBeVisible();
  await expect(page.getByText("元音声", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "整理", exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: "整理", exact: true }).click();
  const confirmDialog = page.getByRole("dialog", { name: "キャッシュを整理" });
  await expect(confirmDialog).toBeVisible();
  await confirmDialog.getByRole("button", { name: "整理する" }).click();
  await expect.poll(() => cleanupRequest).toEqual({ categories: ["work"] });
  await expect(page.locator("#storage-total")).toContainText("1.00 KB削除");
});

test("デスクトップ設定で利用者ごとのクラウド連携を編集できる", async ({ page }) => {
  await page.addInitScript(() => {
    window.practiceLabDesktop = {
      getSettings: async () => ({
        autoUpdate: true,
        dataPath: "C:\\Users\\tester\\AppData\\Local\\PracticeLab",
        version: "1.0.0",
        cloud: { enabled: false, prefix: "sessions", hasSecret: false },
      }),
      saveSettings: async settings => settings,
      openDataFolder: async () => "",
      checkForUpdates: async () => true,
      getToken: async () => "test-token",
      onUpdateStatus: () => () => {},
      onCommand: () => () => {},
    };
  });
  await page.goto("/");
  const topSettings = page.locator("#btn-top-settings");
  await expect(topSettings).toBeVisible();
  await expect(topSettings).toHaveCSS("height", "38px");
  await topSettings.click();
  const settings = page.locator("#settings-dialog");
  await expect(settings).toBeVisible();
  const settingsBox = await settings.boundingBox();
  const viewport = page.viewportSize();
  expect(settingsBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(Math.abs(settingsBox.x + settingsBox.width / 2 - viewport.width / 2)).toBeLessThanOrEqual(1);
  expect(Math.abs(settingsBox.y + settingsBox.height / 2 - viewport.height / 2)).toBeLessThanOrEqual(1);
  await settings.getByRole("button", { name: "クラウド連携" }).click();
  await expect(settings.getByText("自分のCloudflare R2と連携")).toBeVisible();
  await settings.getByRole("checkbox", { name: /クラウド連携を有効/ }).check();
  await expect(settings.getByLabel("R2 バケット名")).toBeEnabled();
});

test("デスクトップの再生設定を固定保存先から復元して変更を保存する", async ({ page }) => {
  await page.addInitScript(() => {
    window.__savedPlayerSettings = null;
    window.practiceLabDesktop = {
      getPlayerSettings: () => ({ volMusic: 37, volMetro: 64, playbackRate: 0.8 }),
      savePlayerSettings: settings => {
        window.__savedPlayerSettings = structuredClone(settings);
        return { ok: true, settings };
      },
      getSettings: async () => ({ autoUpdate: true, version: "1.0.0", cloud: { enabled: false } }),
      getToken: async () => "test-token",
      onUpdateStatus: () => () => {},
      onCommand: () => () => {},
    };
  });
  await page.goto("/");
  await expect(page.locator("#vol-music")).toHaveValue("37");
  await expect(page.locator("#vol-metro")).toHaveValue("64");
  await expect(page.locator("#playback-rate")).toHaveValue("0.8");

  await page.locator("#vol-music").evaluate(element => {
    element.value = "52";
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect.poll(() => page.evaluate(() => window.__savedPlayerSettings?.volMusic)).toBe(52);
});

test("アップデート確認の結果を設定画面へ表示する", async ({ page }) => {
  await page.addInitScript(() => {
    let updateListener = () => {};
    window.practiceLabDesktop = {
      getPlayerSettings: () => ({}),
      savePlayerSettings: settings => ({ ok: true, settings }),
      getSettings: async () => ({ autoUpdate: true, version: "1.0.0", cloud: { enabled: false } }),
      getToken: async () => "test-token",
      checkForUpdates: async () => {
        updateListener({ state: "current" });
        return { state: "started" };
      },
      installUpdate: async () => false,
      onUpdateStatus: callback => {
        updateListener = callback;
        return () => {};
      },
      onCommand: () => () => {},
    };
  });
  await page.goto("/");
  await page.locator("#btn-top-settings").click();
  await page.getByRole("button", { name: "アップデート", exact: true }).click();
  await page.getByRole("button", { name: "アップデートを確認" }).click();
  await expect(page.locator("#settings-update-status")).toHaveText("現在のバージョンが最新です。");
});
