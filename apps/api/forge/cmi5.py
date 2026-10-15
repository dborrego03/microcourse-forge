"""Package a lesson as a cmi5 course: one assignable unit (AU) that reports to an LRS with xAPI.

Same page as the SCORM package, different runtime. The LMS launches index.html with
endpoint, fetch, actor, registration and activityId in the query string; the AU
gets its token from `fetch`, reads LMS.LaunchData, then sends the cmi5-defined
statements: initialized, passed or failed, completed and terminated.
"""

from html import escape
from pathlib import Path

from forge.scorm import MASTERY_SCORE, audio_files, license_text, render_html, zip_files

COURSE_IRI = "https://github.com/dborrego03/microcourse-forge/lessons/{id}"

COURSE_STRUCTURE = """<?xml version="1.0" encoding="utf-8"?>
<courseStructure xmlns="https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd">
  <course id="{course}">
    <title><langstring lang="en-US">{title}</langstring></title>
    <description><langstring lang="en-US">{description}</langstring></description>
  </course>
  <au id="{course}/au" moveOn="CompletedAndPassed" masteryScore="{mastery}" launchMethod="AnyWindow">
    <title><langstring lang="en-US">{title}</langstring></title>
    <description><langstring lang="en-US">{description}</langstring></description>
    <url>index.html</url>
  </au>
</courseStructure>
"""

CMI5_JS = """
var lrs = null, started = Date.now();
var VERB = "http://adlnet.gov/expapi/verbs/";
var CMI5 = "https://w3id.org/xapi/cmi5/context/categories/cmi5";
var MOVE_ON = "https://w3id.org/xapi/cmi5/context/categories/moveon";
var MASTERY_EXT = "https://w3id.org/xapi/cmi5/context/extensions/masteryscore";

function uuid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  // crypto.randomUUID needs a secure context; LMS previews over http don't always have one.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 3) | 8).toString(16);
  });
}

function headers() {
  return {
    "Authorization": "Basic " + lrs.token,
    "X-Experience-API-Version": "1.0.3",
    "Content-Type": "application/json",
  };
}

function send(verb, result, moveOn) {
  var context = JSON.parse(JSON.stringify(lrs.context));
  context.registration = lrs.registration;
  context.contextActivities = context.contextActivities || {};
  var category = (context.contextActivities.category || []).concat([{ id: CMI5 }]);
  if (moveOn) category.push({ id: MOVE_ON });
  context.contextActivities.category = category;
  if (lrs.masteryScore !== null && (verb === "passed" || verb === "failed")) {
    context.extensions = context.extensions || {};
    context.extensions[MASTERY_EXT] = lrs.masteryScore;
  }
  var statement = {
    id: uuid(),
    actor: lrs.actor,
    verb: { id: VERB + verb, display: { "en-US": verb } },
    object: { id: lrs.activityId, objectType: "Activity" },
    context: context,
    timestamp: new Date().toISOString(),
  };
  if (result) statement.result = result;
  return fetch(lrs.endpoint + "statements", {
    method: "POST", headers: headers(), body: JSON.stringify(statement), keepalive: true,
  });
}

function duration() {
  return "PT" + Math.round((Date.now() - started) / 1000) + "S";
}

var launched = (async function () {
  var q = new URLSearchParams(location.search);
  if (!q.get("endpoint") || !q.get("fetch")) {
    document.getElementById("standalone").hidden = false;
    return;
  }
  var auth = await (await fetch(q.get("fetch"), { method: "POST" })).json();
  lrs = {
    endpoint: q.get("endpoint").replace(/\\/?$/, "/"),
    token: auth["auth-token"],
    actor: JSON.parse(q.get("actor")),
    registration: q.get("registration"),
    activityId: q.get("activityId"),
    context: {},
    masteryScore: null,
  };
  var state = new URLSearchParams({
    stateId: "LMS.LaunchData", activityId: lrs.activityId,
    agent: JSON.stringify(lrs.actor), registration: lrs.registration,
  });
  var res = await fetch(lrs.endpoint + "activities/state?" + state, { headers: headers() });
  var launchData = await res.json();
  lrs.context = launchData.contextTemplate || {};
  // The LMS's mastery score wins over the one in the course structure.
  if (typeof launchData.masteryScore === "number") {
    lrs.masteryScore = launchData.masteryScore;
    MASTERY = Math.round(launchData.masteryScore * 100);
  }
  await send("initialized");
})();

function report(score) {
  launched.then(async function () {
    if (!lrs) return;
    var passed = score >= MASTERY;
    await send(passed ? "passed" : "failed",
      { score: { scaled: score / 100 }, success: passed, duration: duration() }, true);
    await send("completed", { completion: true, duration: duration() }, true);
  });
}

window.addEventListener("pagehide", function () {
  if (lrs) send("terminated", { duration: duration() });
});
"""


def build_cmi5(lesson: dict, media_dir: Path | None = None) -> bytes:
    """`lesson` is a ready row from forge.lessons.get_lesson; media_dir holds its narration, if any."""
    audio = audio_files(lesson, media_dir)
    structure = COURSE_STRUCTURE.format(
        course=COURSE_IRI.format(id=lesson["id"]),
        title=escape(lesson["lesson"]["title"]),
        description=escape(lesson["lesson"]["summary"]),
        mastery=MASTERY_SCORE / 100,
    )
    return zip_files(
        {
            "cmi5.xml": structure,
            "index.html": render_html(lesson, narrated=bool(audio), runtime=CMI5_JS),
            "LICENSE.txt": license_text(lesson),
            **audio,
        }
    )
