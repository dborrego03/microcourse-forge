"""Package a lesson as a SCORM 1.2 zip: one SCO with the lesson, the quiz and a small runtime.

SCORM 1.2 because it is the version every LMS still imports. The page reports
cmi.core.lesson_status and cmi.core.score.raw when the learner checks the quiz,
and works on its own (without an LMS) for previews.
"""

import io
import json
import re
import zipfile
from html import escape
from pathlib import Path

MASTERY_SCORE = 70  # percent of graded questions needed to pass

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="microcourse-forge-lesson-{id}" version="1.0"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                              http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="org-1">
    <organization identifier="org-1">
      <title>{title}</title>
      <item identifier="item-1" identifierref="sco-1">
        <title>{title}</title>
        <adlcp:masteryscore>{mastery}</adlcp:masteryscore>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="sco-1" type="webcontent" adlcp:scormtype="sco" href="index.html">
{files}
    </resource>
  </resources>
</manifest>
"""

# Finds the LMS API the way the SCORM 1.2 run-time spec describes: walk up the
# parent frames, then try the opener window.
RUNTIME = """
var api = null;
function findAPI(win) {
  for (var i = 0; win && i < 10; i++) {
    if (win.API) return win.API;
    if (win.parent === win) break;
    win = win.parent;
  }
  return null;
}
api = findAPI(window) || (window.opener ? findAPI(window.opener) : null);
if (api) {
  api.LMSInitialize("");
  if (api.LMSGetValue("cmi.core.lesson_status") === "not attempted") {
    api.LMSSetValue("cmi.core.lesson_status", "incomplete");
    api.LMSCommit("");
  }
} else {
  document.getElementById("standalone").hidden = false;
}
window.addEventListener("beforeunload", function () { if (api) api.LMSFinish(""); });

document.getElementById("check").addEventListener("click", function () {
  var graded = 0, correct = 0;
  QUIZ.forEach(function (q, i) {
    var box = document.getElementById("feedback-" + i);
    if (q.type === "short_answer") {
      box.textContent = "Model answer: " + q.answer + " " + q.feedback;
    } else {
      graded++;
      var picked = document.querySelector('input[name="q' + i + '"]:checked');
      var ok = picked && picked.value === q.answer;
      if (ok) correct++;
      box.textContent = (ok ? "Correct. " : "Answer: " + q.answer + ". ") + q.feedback;
      box.className = ok ? "feedback ok" : "feedback wrong";
    }
    box.hidden = false;
  });
  var score = graded ? Math.round((100 * correct) / graded) : 100;
  document.getElementById("score").textContent = correct + " of " + graded + " correct (" + score + "%)";
  if (api) {
    api.LMSSetValue("cmi.core.score.min", "0");
    api.LMSSetValue("cmi.core.score.max", "100");
    api.LMSSetValue("cmi.core.score.raw", String(score));
    api.LMSSetValue("cmi.core.lesson_status", score >= MASTERY ? "passed" : "failed");
    api.LMSCommit("");
  }
});
"""

STYLE = """
body { font-family: system-ui, sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem;
       line-height: 1.6; color: #1c1917; background: #fafaf9; }
h1 { line-height: 1.2; } .example { border-left: 4px solid #0f766e; background: #fff; padding: .5rem 1rem; }
sup a { color: #115e59; } fieldset { border: 0; padding: 0; margin: 1.5rem 0 0; } legend { font-weight: 600; }
label { display: block; padding: .2rem 0; } .feedback { font-size: .9rem; } .ok { color: #166534; }
.wrong { color: #991b1b; } button { background: #115e59; color: #fff; border: 0; border-radius: 6px;
       padding: .6rem 1rem; font-size: 1rem; cursor: pointer; } button:focus { outline: 3px solid #0f766e; }
.sources li { margin-bottom: .5rem; } small { color: #57534e; }
"""


def audio_tag(part: int) -> str:
    return (
        f'<audio controls preload="none" src="audio/part-{part}.mp3">'
        f'<track kind="captions" srclang="en" label="English" src="audio/part-{part}.vtt" default></audio>'
        "<br><small>Synthetic voice.</small>"
    )


def render_html(lesson: dict, narrated: bool = False) -> str:
    body, quiz, sources = lesson["lesson"], lesson["quiz"]["questions"], lesson["sources"]
    number = {s["id"]: i for i, s in enumerate(sources, 1)}

    def cite(ids):
        links = (
            f'<a href="#source-{i}">[{number[i]}]</a>' for i in sorted(ids, key=number.get) if i in number
        )
        return f"<sup>{''.join(links)}</sup>"

    parts = [
        f"<h1>{escape(body['title'])}</h1>",
        '<p id="standalone" hidden><small>Preview mode: no LMS found, so results are not saved.</small></p>',
        "<h2>By the end you should be able to</h2><ol>",
        *(f"<li>{escape(o)}</li>" for o in body["objectives"]),
        "</ol>",
    ]
    for n, section in enumerate(body["sections"], 1):
        if narrated:
            parts.append(audio_tag(n))
        parts.append(
            f"<h2>{escape(section['heading'])}</h2><p>{escape(section['body'])}{cite(section['sources'])}</p>"
        )
        if section.get("example"):
            parts.append(f'<p class="example"><strong>Example:</strong> {escape(section["example"])}</p>')
    summary_audio = audio_tag(len(body["sections"]) + 1) if narrated else ""
    parts.append(f"<h2>Summary</h2>{summary_audio}<p>{escape(body['summary'])}</p><h2>Check yourself</h2>")
    for i, q in enumerate(quiz):
        parts.append(f"<fieldset><legend>{i + 1}. {escape(q['question'])}</legend>")
        if q["type"] == "short_answer":
            parts.append(f'<textarea aria-label="Answer to question {i + 1}" rows="2" cols="60"></textarea>')
        for option in q["options"]:
            value = escape(option, quote=True)
            parts.append(f'<label><input type="radio" name="q{i}" value="{value}"> {escape(option)}</label>')
        parts.append(f'<p id="feedback-{i}" class="feedback" hidden></p></fieldset>')
    parts.append('<p><button id="check" type="button">Check answers</button>')
    parts.append('<span id="score" role="status"></span></p>')
    parts.append('<h2>Sources</h2><ol class="sources">')
    for s in sources:
        parts.append(f'<li id="source-{s["id"]}">{escape(s["section"])}, PDF pages {escape(s["pages"])}</li>')
    first = sources[0] if sources else {}
    url, title = escape(first.get("source_url", ""), quote=True), escape(first.get("title", ""))
    license_, attribution = escape(first.get("license", "")), escape(first.get("attribution", ""))
    parts.append(
        f'</ol><p><small>Adapted from <a href="{url}">{title}</a> by OpenStax, licensed {license_}. '
        f"{attribution}. Written by an AI model ({escape(lesson.get('model') or '')}) and shared under "
        "the same license. It can contain mistakes: check the cited passages.</small></p>"
    )

    # Escape "</" so lesson text can't close the script tag early.
    quiz_json = json.dumps(quiz).replace("</", "<\\/")
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(body['title'])}</title><style>{STYLE}</style></head><body>"
        + "\n".join(parts)
        + f"<script>var QUIZ = {quiz_json}; var MASTERY = {MASTERY_SCORE};{RUNTIME}</script></body></html>\n"
    )


def license_text(lesson: dict) -> str:
    s = lesson["sources"][0]
    return (
        f"This package is adapted from {s['title']} (OpenStax), {s['source_url']}\n"
        f"License: {s['license']} {s['license_url']}\n"
        f"{s['attribution']}.\n\n"
        "The lesson and quiz were generated by an AI model from passages of that book and are shared\n"
        "under the same license. Changes: passages were selected, summarised and rewritten as a lesson.\n"
    )


def package_name(lesson: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", lesson["lesson"]["title"].lower()).strip("-")[:60]
    return f"lesson-{lesson['id']}-{slug}-scorm12.zip"


def build_scorm12(lesson: dict, media_dir: Path | None = None) -> bytes:
    """`lesson` is a ready row from forge.lessons.get_lesson; media_dir holds its narration, if any."""
    audio = {}
    if media_dir and lesson.get("audio"):
        for a in lesson["audio"]:
            for ext in ("mp3", "vtt"):
                audio[f"audio/part-{a['part']}.{ext}"] = (media_dir / f"part-{a['part']}.{ext}").read_bytes()

    files = {
        "index.html": render_html(lesson, narrated=bool(audio)).encode(),
        "LICENSE.txt": license_text(lesson).encode(),
        **audio,
    }
    title = escape(lesson["lesson"]["title"])
    file_list = "\n".join(f'      <file href="{name}"/>' for name in files)
    manifest = MANIFEST.format(id=lesson["id"], title=title, mastery=MASTERY_SCORE, files=file_list)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # The manifest has to sit at the root of the zip.
        zf.writestr("imsmanifest.xml", manifest)
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()
