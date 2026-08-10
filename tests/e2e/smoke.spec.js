import { expect, test } from "@playwright/test";

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

test("曲構成と楽譜抽出を切り替えられる", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "楽譜抽出", exact: true }).click();
  await expect(page.locator("#score-panel")).toBeVisible();
  await page.getByRole("button", { name: "曲構成", exact: true }).click();
  await expect(page.locator("#structure-panel")).toBeVisible();
});

test("入力ポップアップをアプリ内の画面として表示する", async ({ page }) => {
  const browserDialogs = [];
  page.on("dialog", dialog => browserDialogs.push(dialog.type()));

  await page.goto("/");
  await page.getByRole("button", { name: "新しいフォルダー" }).click();
  const dialog = page.getByRole("dialog", { name: "フォルダーを追加" });
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  const viewport = page.viewportSize();
  expect(Math.abs((box.x + box.width / 2) - viewport.width / 2)).toBeLessThan(3);
  expect(Math.abs((box.y + box.height / 2) - viewport.height / 2)).toBeLessThan(3);
  await expect(dialog.getByRole("textbox", { name: "フォルダー名" })).toHaveValue("新しいフォルダー");
  await dialog.getByRole("button", { name: "キャンセル" }).click();
  await expect(dialog).toBeHidden();
  expect(browserDialogs).toEqual([]);
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
  await page.route("**/audio/section-test.mp3", route => route.abort());
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
  await page.getByRole("button", { name: "分割", exact: true }).click();
  await expect(page.getByLabel("セクション名 2")).toBeVisible();
  await page.locator("#btn-save-sections").click();
  await expect.poll(() => saved?.sections?.length).toBe(2);
  expect(saved.sections.map(section => [section.startBar, section.endBar])).toEqual([[1, 2], [3, 4]]);
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
