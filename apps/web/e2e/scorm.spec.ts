import { expect, test } from "@playwright/test";
import { strFromU8, unzipSync } from "fflate";

// A stand-in LMS: it exposes the SCORM 1.2 API object and records every call,
// then loads the package's index.html in a frame, the way an LMS would.
function harness(indexHtml: string) {
  return `<!DOCTYPE html><html><body>
    <script>
      window.calls = [];
      var data = { "cmi.core.lesson_status": "not attempted" };
      window.API = {
        LMSInitialize: function (a) { calls.push(["LMSInitialize"]); return "true"; },
        LMSGetValue: function (k) { calls.push(["LMSGetValue", k]); return data[k] || ""; },
        LMSSetValue: function (k, v) { calls.push(["LMSSetValue", k, v]); data[k] = v; return "true"; },
        LMSCommit: function () { calls.push(["LMSCommit"]); return "true"; },
        LMSFinish: function () { calls.push(["LMSFinish"]); return "true"; },
        LMSGetLastError: function () { return "0"; },
        LMSGetErrorString: function () { return ""; },
        LMSGetDiagnostic: function () { return ""; },
      };
    </script>
    <iframe title="sco" style="width:100%;height:90vh" srcdoc="${indexHtml.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}"></iframe>
  </body></html>`;
}

test("the SCORM package reports status and score to the LMS", async ({ page, request }) => {
  const recent = await (await request.get("http://127.0.0.1:8000/lessons?limit=20")).json();
  const ready = recent.find((l: { status: string }) => l.status === "ready");
  test.skip(!ready, "needs at least one ready lesson");

  const res = await request.get(`/lessons/${ready.id}/scorm`);
  expect(res.ok()).toBeTruthy();
  expect(res.headers()["content-disposition"]).toContain("scorm12.zip");
  const files = unzipSync(new Uint8Array(await res.body()));
  expect(Object.keys(files).sort()).toEqual(["LICENSE.txt", "imsmanifest.xml", "index.html"]);
  expect(strFromU8(files["imsmanifest.xml"])).toContain("<schemaversion>1.2</schemaversion>");

  await page.setContent(harness(strFromU8(files["index.html"])));
  const sco = page.frameLocator("iframe");
  await expect(sco.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(sco.getByText("Preview mode")).toBeHidden();

  for (const group of await sco.locator("fieldset").all()) {
    const radio = group.getByRole("radio").first();
    if (await radio.count()) await radio.check();
  }
  await sco.getByRole("button", { name: "Check answers" }).click();
  await expect(sco.getByRole("status")).toContainText(/\d+ of \d+ correct/);

  const calls: string[][] = await page.evaluate(() => (window as unknown as { calls: string[][] }).calls);
  expect(calls[0]).toEqual(["LMSInitialize"]);
  expect(calls).toContainEqual(["LMSSetValue", "cmi.core.lesson_status", "incomplete"]);
  const score = calls.find((c) => c[1] === "cmi.core.score.raw");
  expect(Number(score?.[2])).toBeGreaterThanOrEqual(0);
  const status = calls.filter((c) => c[1] === "cmi.core.lesson_status").at(-1);
  expect(status?.[2]).toMatch(/^(passed|failed)$/);
  expect(calls.at(-1)).toEqual(["LMSCommit"]);
});
