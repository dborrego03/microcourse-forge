import io
import json
import zipfile

import httpx
import pytest

from forge import tts
from forge.scorm import build_scorm12
from forge.tts import TTSError, duration_s, section_scripts, synthesize, to_vtt
from tests.test_scorm import LESSON

# 100 silent MPEG-1 Layer III frames (128 kbps, 44.1 kHz): 100 * 1152 / 44100 s.
SILENT_MP3 = (bytes([0xFF, 0xFB, 0x90, 0x64]) + bytes(413)) * 100


def test_scripts_cover_every_section_and_the_summary():
    scripts = section_scripts(LESSON["lesson"])
    assert scripts == ["Dogs. Bells and food. For example: A bell.", "In summary. That's it."]


def test_vtt_cues_split_the_duration_by_sentence_length():
    vtt = to_vtt("Short one. A much longer second sentence here.", 10.0)
    lines = vtt.splitlines()
    assert lines[0] == "WEBVTT"
    assert lines[2] == "00:00:00.000 --> 00:00:02.222"  # 10 of 45 characters
    assert lines[-1] == "A much longer second sentence here."
    assert "--> 00:00:10.000" in vtt


def test_duration_comes_from_the_mp3_frames():
    assert duration_s(SILENT_MP3) == pytest.approx(100 * 1152 / 44100)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_synthesize_retries_rate_limits_and_caches(isolated):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, content=SILENT_MP3)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert synthesize("Hello there.", client) == SILENT_MP3
    assert synthesize("Hello there.", client) == SILENT_MP3  # second time from the cache
    assert len(calls) == 2
    assert calls[0]["input"] == "Hello there." and calls[0]["response_format"] == "mp3"


def test_synthesize_gives_up_on_client_errors(isolated):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad voice")))
    with pytest.raises(TTSError, match="400"):
        synthesize("Hello.", client)


def test_synthesize_needs_a_key(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(TTSError, match="OPENAI_API_KEY"):
        synthesize("Hello.")


def test_scorm_package_includes_narration(tmp_path):
    for part in (1, 2):
        (tmp_path / f"part-{part}.mp3").write_bytes(SILENT_MP3)
        (tmp_path / f"part-{part}.vtt").write_text("WEBVTT\n")
    lesson = {**LESSON, "audio": [{"part": 1}, {"part": 2}]}

    zf = zipfile.ZipFile(io.BytesIO(build_scorm12(lesson, tmp_path)))

    assert "audio/part-2.mp3" in zf.namelist()
    assert '<file href="audio/part-1.vtt"/>' in zf.read("imsmanifest.xml").decode()
    assert 'src="audio/part-1.mp3"' in zf.read("index.html").decode()


def test_network_errors_become_tts_errors(isolated):
    def handler(request):
        raise httpx.ConnectTimeout("too slow")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(TTSError, match="can't reach"):
        synthesize("Hello.", client)


async def test_narrating_twice_reuses_the_audio(conn, isolated, monkeypatch, tmp_path):
    calls = []

    def fake_synthesize(text):
        calls.append(text)
        return SILENT_MP3

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    monkeypatch.setattr(tts, "MEDIA_DIR", tmp_path)
    cur = await conn.execute("INSERT INTO lessons (request, status) VALUES ('{}', 'ready') RETURNING id")
    lesson = {"id": (await cur.fetchone())["id"], "lesson": LESSON["lesson"]}
    # narrate() commits, so clean up by hand afterwards.
    try:
        first = await tts.narrate(conn, lesson)
        again = await tts.narrate(conn, lesson)
    finally:
        await conn.execute("DELETE FROM lessons WHERE id = %s", [lesson["id"]])
        await conn.commit()

    assert len(first) == 2 and [a["id"] for a in again] == [a["id"] for a in first]
    assert len(calls) == 2  # two parts, synthesized once
