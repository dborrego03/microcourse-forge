"""Narrate a lesson with OpenAI's text-to-speech, one audio file per section.

Each section gets an MP3 and a WebVTT subtitle file. The subtitles come from the
script itself, with each sentence's timing estimated from its share of the
characters; that is close enough for short sections and costs nothing extra
(word-level timing would need a speech-to-text pass).

Audio is cached by (model, voice, text), so narrating the same lesson twice, or
two lessons that share a section, doesn't pay twice. The voice is synthetic and
the UI says so.
"""

import asyncio
import hashlib
import io
import os
import re
import time
from pathlib import Path

import httpx
import psycopg
from tinytag import TinyTag

from forge import API_DIR, REPO_ROOT

TTS_MODEL = os.environ.get("FORGE_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.environ.get("FORGE_TTS_VOICE", "alloy")
API_URL = "https://api.openai.com/v1/audio/speech"
CACHE_DIR = API_DIR / ".cache" / "tts"
MEDIA_DIR = Path(os.environ.get("FORGE_MEDIA_DIR", REPO_ROOT / "data" / "media"))
MAX_ATTEMPTS = 3


class TTSError(Exception):
    pass


def section_scripts(lesson: dict) -> list[str]:
    """What gets read aloud: each section (heading, body, example), then the summary."""
    scripts = []
    for s in lesson["sections"]:
        parts = [s["heading"] + ".", s["body"]]
        if s.get("example"):
            parts.append("For example: " + s["example"])
        scripts.append(" ".join(parts))
    scripts.append("In summary. " + lesson["summary"])
    return scripts


def synthesize(text: str, client: httpx.Client | None = None) -> bytes:
    key = hashlib.sha256(f"{TTS_MODEL}|{TTS_VOICE}|{text}".encode()).hexdigest()
    path = CACHE_DIR / f"{key}.mp3"
    if path.exists():
        return path.read_bytes()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise TTSError("OPENAI_API_KEY is not set, so narration is turned off")
    client = client or httpx.Client(timeout=60)
    body = {
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "input": text,
        "response_format": "mp3",
        "instructions": "A calm, clear teacher explaining a topic to adult learners.",
    }
    for attempt in range(1, MAX_ATTEMPTS + 1):
        res = client.post(API_URL, json=body, headers={"Authorization": f"Bearer {api_key}"})
        if res.status_code == 200:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(res.content)
            return res.content
        if res.status_code not in (429, 500, 502, 503) or attempt == MAX_ATTEMPTS:
            raise TTSError(f"TTS request failed with {res.status_code}: {res.text[:200]}")
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def duration_s(mp3: bytes) -> float:
    return TinyTag.get(file_obj=io.BytesIO(mp3)).duration or 0.0


def timestamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def to_vtt(text: str, seconds: float) -> str:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    total = sum(len(s) for s in sentences) or 1
    cues, start = ["WEBVTT", ""], 0.0
    for sentence in sentences:
        end = start + seconds * len(sentence) / total
        cues += [f"{timestamp(start)} --> {timestamp(end)}", sentence, ""]
        start = end
    return "\n".join(cues)


async def narrate(conn: psycopg.AsyncConnection, lesson: dict) -> list[dict]:
    """`lesson` is a ready row from forge.lessons.get_lesson. Writes files and audio_assets rows."""
    folder = MEDIA_DIR / f"lesson-{lesson['id']}"
    folder.mkdir(parents=True, exist_ok=True)
    per_minute = os.environ.get("FORGE_TTS_USD_PER_MINUTE")  # no default: prices change, so it's configured
    await conn.execute("DELETE FROM audio_assets WHERE lesson_id = %s", [lesson["id"]])
    for part, script in enumerate(section_scripts(lesson["lesson"]), 1):
        audio = await asyncio.to_thread(synthesize, script)
        seconds = duration_s(audio)
        (folder / f"part-{part}.mp3").write_bytes(audio)
        (folder / f"part-{part}.vtt").write_text(to_vtt(script, seconds), encoding="utf-8")
        await conn.execute(
            """INSERT INTO audio_assets (lesson_id, part, provider, model, voice, characters, duration_s,
                                         cost_usd, cache_key)
               VALUES (%s, %s, 'openai', %s, %s, %s, %s, %s, %s)""",
            [
                lesson["id"], part, TTS_MODEL, TTS_VOICE, len(script), round(seconds, 2),
                round(seconds / 60 * float(per_minute), 6) if per_minute else None,
                hashlib.sha256(f"{TTS_MODEL}|{TTS_VOICE}|{script}".encode()).hexdigest(),
            ],
        )  # fmt: skip
    await conn.commit()
    cur = await conn.execute("SELECT * FROM audio_assets WHERE lesson_id = %s ORDER BY part", [lesson["id"]])
    return await cur.fetchall()
