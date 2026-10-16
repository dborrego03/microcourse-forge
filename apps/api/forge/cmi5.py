"""Package a lesson as a cmi5 course: one assignable unit (AU) that reports to an LRS with xAPI.

Same page as the SCORM package, different runtime. The LMS launches index.html with
endpoint, fetch, actor, registration and activityId in the query string; the AU
gets its token from `fetch`, reads LMS.LaunchData, then sends the cmi5-defined
statements: initialized, passed or failed, completed and terminated.
"""

from html import escape
from pathlib import Path

from forge.scorm import MASTERY_SCORE, audio_files, license_text, render_html, zip_files

IRI = "https://github.com/dborrego03/microcourse-forge"

COURSE_STRUCTURE = """<?xml version="1.0" encoding="utf-8"?>
<courseStructure xmlns="https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd">
  <course id="{id}">
    <title><langstring lang="en-US">{title}</langstring></title>
    <description><langstring lang="en-US">{description}</langstring></description>
  </course>
{aus}</courseStructure>
"""

AU = """  <au id="{id}" moveOn="CompletedAndPassed" masteryScore="{mastery}" launchMethod="AnyWindow">
    <title><langstring lang="en-US">{title}</langstring></title>
    <description><langstring lang="en-US">{description}</langstring></description>
    <url>{url}</url>
  </au>
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

// Statements go out one at a time, in the order they were queued, so "terminated" can't
// overtake the result of the attempt.
var queue = Promise.resolve();
function enqueue(verb, result, moveOn) {
  queue = queue.then(function () { return send(verb, result, moveOn); }).catch(function () {});
  return queue;
}

var launched = (async function () {
  var q = new URLSearchParams(location.search);
  if (!q.get("endpoint") || !q.get("fetch")) {
    document.getElementById("standalone").hidden = false;
    return;
  }
  // The fetch URL can only be used once; keep the token so reloading the page still reports.
  var key = "cmi5-token:" + q.get("registration"), token = null;
  try { token = sessionStorage.getItem(key); } catch (e) {}
  if (!token) {
    token = (await (await fetch(q.get("fetch"), { method: "POST" })).json())["auth-token"];
    try { sessionStorage.setItem(key, token); } catch (e) {}
  }
  lrs = {
    endpoint: q.get("endpoint").replace(/\\/?$/, "/"),
    token: token,
    actor: JSON.parse(q.get("actor")),
    registration: q.get("registration"),
    activityId: q.get("activityId"),
    context: {},
    masteryScore: null,
    launchMode: "Normal",
  };
  var state = new URLSearchParams({
    stateId: "LMS.LaunchData", activityId: lrs.activityId,
    agent: JSON.stringify(lrs.actor), registration: lrs.registration,
  });
  var res = await fetch(lrs.endpoint + "activities/state?" + state, { headers: headers() });
  var launchData = await res.json();
  lrs.context = launchData.contextTemplate || {};
  lrs.launchMode = launchData.launchMode || "Normal";
  // The LMS's mastery score wins over the one in the course structure.
  if (typeof launchData.masteryScore === "number") {
    lrs.masteryScore = launchData.masteryScore;
    MASTERY = Math.round(launchData.masteryScore * 100);
  }
  await enqueue("initialized");
})();

// shortcut: a relaunch in the same registration reports the new attempt again; storing a
// flag with the State API would stop that, once a real LMS shows it matters.
function report(score) {
  launched.then(function () {
    // Browse and Review launches look at the content; only Normal ones record results.
    if (!lrs || lrs.launchMode !== "Normal") return;
    var passed = score >= MASTERY;
    enqueue(passed ? "passed" : "failed",
      { score: { scaled: score / 100 }, success: passed, duration: duration() }, true);
    enqueue("completed", { completion: true, duration: duration() }, true);
  });
}

window.addEventListener("pagehide", function () {
  if (lrs) enqueue("terminated", { duration: duration() });
});
"""


def au(au_id: str, lesson: dict, url: str) -> str:
    return AU.format(
        id=au_id,
        title=escape(lesson["lesson"]["title"]),
        description=escape(lesson["lesson"]["summary"]),
        mastery=MASTERY_SCORE / 100,
        url=url,
    )


def build_cmi5(lesson: dict, media_dir: Path | None = None) -> bytes:
    """`lesson` is a ready row from forge.lessons.get_lesson; media_dir holds its narration, if any."""
    course_id = f"{IRI}/lessons/{lesson['id']}"
    license_txt = license_text(lesson)  # first, so a lesson without sources fails clearly
    audio = audio_files(lesson, media_dir)
    structure = COURSE_STRUCTURE.format(
        id=course_id,
        title=escape(lesson["lesson"]["title"]),
        description=escape(lesson["lesson"]["summary"]),
        aus=au(f"{course_id}/au", lesson, "index.html"),
    )
    return zip_files(
        {
            "cmi5.xml": structure,
            "index.html": render_html(lesson, narrated=bool(audio), runtime=CMI5_JS),
            "LICENSE.txt": license_txt,
            **audio,
        }
    )


def build_cmi5_course(title: str, description: str, lessons: list[dict], media_root: Path) -> bytes:
    """Several lessons as one cmi5 course, one AU per lesson in its own folder."""
    course_id = f"{IRI}/courses/" + "-".join(str(lesson["id"]) for lesson in lessons)
    for lesson in lessons:
        license_text(lesson)  # every lesson needs its sources before anything is built
    files: dict[str, str | bytes] = {"LICENSE.txt": license_text(lessons[0])}
    aus = []
    for lesson in lessons:
        folder = f"lesson-{lesson['id']}"
        audio = audio_files(lesson, media_root / folder)
        files[f"{folder}/index.html"] = render_html(lesson, narrated=bool(audio), runtime=CMI5_JS)
        files.update({f"{folder}/{name}": data for name, data in audio.items()})
        aus.append(au(f"{IRI}/lessons/{lesson['id']}/au", lesson, f"{folder}/index.html"))
    structure = COURSE_STRUCTURE.format(
        id=course_id, title=escape(title), description=escape(description), aus="".join(aus)
    )
    return zip_files({"cmi5.xml": structure, **files})
