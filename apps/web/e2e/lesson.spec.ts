import { expect, test } from "@playwright/test";

// Same request as the one used while developing, so the model's answer
// usually comes from the API's cache instead of a new call.
const TOPIC = "Classical conditioning";
const OBJECTIVE = "Explain how a neutral stimulus becomes a conditioned stimulus";

test("create a micro-course, read it and take the quiz", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "New micro-course" })).toBeVisible();

  await page.getByLabel("Topic").fill(TOPIC);
  await page.getByLabel(/Learning objectives/).fill(OBJECTIVE);
  await page.getByRole("button", { name: "Create micro-course" }).click();

  await page.waitForURL(/\/lessons\/\d+$/, { timeout: 110_000 });
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  await expect(page.getByText("CC BY-NC-SA 4.0").last()).toBeVisible();

  // Citations jump to their source.
  const citation = page.locator("article p a[href^='#source-']").first();
  await expect(citation).toBeVisible();

  const quiz = page.getByRole("region", { name: "Check yourself" });
  for (const group of await quiz.locator("fieldset").all()) {
    const radio = group.getByRole("radio").first();
    if (await radio.count()) await radio.check();
  }
  await quiz.getByRole("button", { name: "Check answers" }).click();
  await expect(quiz.getByRole("status")).toContainText(/\d+ of \d+ correct/);
});

test("the home page lists recent lessons", async ({ page }) => {
  await page.goto("/");
  const recent = page.getByRole("heading", { name: "Recent lessons" }).locator("..");
  await expect(recent.getByRole("link").first()).toBeVisible();
});

test("the quality page shows evals and pipeline steps", async ({ page }) => {
  await page.goto("/quality");
  await expect(page.getByRole("heading", { name: "Evaluations" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /^rerank/ })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "lesson", exact: true })).toBeVisible();
});
