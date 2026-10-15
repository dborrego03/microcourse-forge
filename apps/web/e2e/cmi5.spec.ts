import { expect, test } from "@playwright/test";
import { strFromU8, unzipSync } from "fflate";

type Statement = {
  verb: { id: string };
  result?: { score?: { scaled: number }; success?: boolean; completion?: boolean };
  context: { registration: string; contextActivities: { category: { id: string }[] } };
};

// Plays both the LMS and the LRS: serves the AU, hands out a token and records statements.
test("the cmi5 package launches and sends the cmi5 statements", async ({ page, request }) => {
  const recent = await (await request.get("http://127.0.0.1:8000/lessons?limit=20")).json();
  const ready = recent.find((l: { status: string }) => l.status === "ready");
  test.skip(!ready, "needs at least one ready lesson");

  const res = await request.get(`/lessons/${ready.id}/cmi5`);
  expect(res.ok()).toBeTruthy();
  const files = unzipSync(new Uint8Array(await res.body()));
  expect(Object.keys(files).sort()).toEqual(["LICENSE.txt", "cmi5.xml", "index.html"]);

  const statements: Statement[] = [];
  await page.route("http://lms.test/au/index.html*", (route) =>
    route.fulfill({ contentType: "text/html", body: strFromU8(files["index.html"]) }),
  );
  await page.route("http://lms.test/token", (route) => route.fulfill({ json: { "auth-token": "dGVzdA==" } }));
  await page.route("http://lrs.test/xapi/activities/state*", (route) =>
    route.fulfill({ json: { contextTemplate: { extensions: { session: "s1" } }, masteryScore: 0.5 } }),
  );
  await page.route("http://lrs.test/xapi/statements", (route) => {
    expect(route.request().headers()["x-experience-api-version"]).toBe("1.0.3");
    statements.push(route.request().postDataJSON());
    return route.fulfill({ json: ["ok"] });
  });

  const launch = new URLSearchParams({
    endpoint: "http://lrs.test/xapi",
    fetch: "http://lms.test/token",
    actor: JSON.stringify({
      objectType: "Agent",
      account: { homePage: "http://lms.test", name: "learner-1" },
    }),
    registration: "11111111-2222-4333-8444-555555555555",
    activityId: "https://github.com/dborrego03/microcourse-forge/lessons/1/au",
  });
  await page.goto(`http://lms.test/au/index.html?${launch}`);
  await expect.poll(() => statements.length).toBe(1);
  await expect(page.getByText("Preview mode")).toBeHidden();

  for (const group of await page.locator("fieldset").all()) {
    const radio = group.getByRole("radio").first();
    if (await radio.count()) await radio.check();
  }
  await page.getByRole("button", { name: "Check answers" }).click();
  await expect.poll(() => statements.length).toBe(3);

  const verbs = statements.map((s) => s.verb.id.split("/").pop());
  expect(verbs[0]).toBe("initialized");
  expect(verbs[1]).toMatch(/^(passed|failed)$/);
  expect(verbs[2]).toBe("completed");
  expect(statements[1].result?.success).toBe(verbs[1] === "passed");
  expect(statements[2].result?.completion).toBe(true);
  for (const s of statements) {
    expect(s.context.registration).toBe("11111111-2222-4333-8444-555555555555");
    expect(s.context.contextActivities.category).toContainEqual({
      id: "https://w3id.org/xapi/cmi5/context/categories/cmi5",
    });
  }
});
