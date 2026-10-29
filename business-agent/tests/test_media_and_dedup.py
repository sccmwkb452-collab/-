import io
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.core.dedup import claim_update
from app.media.analyzer import MediaAnalyzer, MediaRef
from tests.conftest import FakeLLM

ANALYSIS = {"summary": "плюшевая лягушка", "objects": ["лягушка"], "visible_text": None, "item_attributes": [],
            "events": [], "tone": "радость", "matches_discussed_item": "not_applicable", "match_explanation": None,
            "reference_matches": [], "confidence": "high"}


def webp_bytes():
    buf = io.BytesIO()
    Image.new("RGBA", (64, 64), (0, 200, 0, 255)).save(buf, format="WEBP")
    return buf.getvalue()


async def test_static_sticker_converted_and_analyzed():
    llm = FakeLLM(ANALYSIS)
    data = webp_bytes()

    async def dl(fid):
        return data

    an = MediaAnalyzer(llm, dl)
    res = await an.analyze(MediaRef("sticker", "f", "u", 100, suffix=".webp", meta={"format": "static", "emoji": "🐸"}))
    assert res.ok and res.summary == "плюшевая лягушка"
    image_block = llm.calls[0]["content"][0]
    assert image_block["source"]["media_type"] == "image/png"


async def test_download_failure_is_reported_not_faked():
    async def dl(fid):
        raise RuntimeError("file is too big")

    res = await MediaAnalyzer(FakeLLM(), dl).analyze(MediaRef("photo", "f", "u", 10, suffix=".jpg"))
    assert not res.ok and "не удалось получить файл" in res.error


async def test_oversized_file_rejected_before_download():
    async def dl(fid):
        raise AssertionError("не должен скачивать")

    res = await MediaAnalyzer(FakeLLM(), dl, max_bytes=10).analyze(MediaRef("video", "f", "u", 100, suffix=".mp4"))
    assert not res.ok and "лимита Bot API" in res.error


async def test_tgs_without_thumbnail_is_not_claimed_as_analyzed():
    async def dl(fid):
        return b"\x1f\x8b fake tgs"

    res = await MediaAnalyzer(FakeLLM(), dl).analyze(
        MediaRef("sticker", "f", "u", 10, suffix=".tgs", meta={"format": "animated", "emoji": "😂"}))
    assert not res.ok and "TGS" in res.error


@pytest.mark.skipif(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0, reason="нет ffmpeg")
async def test_video_frames_extracted(tmp_path: Path):
    out = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    data = out.read_bytes()

    async def dl(fid):
        return data

    llm = FakeLLM(ANALYSIS | {"events": ["кадры тестовой таблицы"]})
    res = await MediaAnalyzer(llm, dl, max_frames=4).analyze(MediaRef("animation", "f", "u", len(data), 2, suffix=".mp4"))
    assert res.ok
    images = [b for b in llm.calls[0]["content"] if b["type"] == "image"]
    assert 1 <= len(images) <= 4
    assert res.details["audio"] == "у GIF-анимаций нет звука"


async def test_update_dedup(sessions):
    assert await claim_update(sessions, "bot:1")
    assert not await claim_update(sessions, "bot:1")
    assert await claim_update(sessions, "bot:2")
