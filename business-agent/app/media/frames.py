"""Работа с кадрами: извлечение из видео/GIF через ffmpeg и конвертация изображений."""
from __future__ import annotations

import asyncio
import io
import tempfile
from pathlib import Path

from PIL import Image


class FrameExtractionError(Exception):
    pass


async def extract_frames(
    data: bytes, *, suffix: str, max_frames: int, duration: float | None, ffmpeg: str = "ffmpeg", timeout: float = 60
) -> list[bytes]:
    """Равномерно извлекает до max_frames JPEG-кадров (ширина ≤ 768)."""
    fps = max_frames / duration if duration and duration > 0 else 1.0
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(data)
        cmd = [
            ffmpeg, "-v", "error", "-i", str(src),
            "-vf", f"fps={fps:.4f},scale='min(768,iw)':-2",
            "-frames:v", str(max_frames), str(Path(tmp) / "f_%03d.jpg"),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError as exc:
            raise FrameExtractionError("ffmpeg не установлен") from exc
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise FrameExtractionError("ffmpeg не уложился в таймаут") from exc
        if proc.returncode != 0:
            raise FrameExtractionError(f"ffmpeg: {stderr.decode(errors='replace')[:300]}")
        frames = [p.read_bytes() for p in sorted(Path(tmp).glob("f_*.jpg"))]
    if not frames:
        raise FrameExtractionError("не удалось извлечь ни одного кадра")
    return frames


async def has_audio_stream(data: bytes, *, suffix: str, ffmpeg: str = "ffmpeg") -> bool:
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(data)
        try:
            proc = await asyncio.create_subprocess_exec(
                ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(src),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return False
        out, _ = await proc.communicate()
    return bool(out.strip())


def to_png(data: bytes) -> bytes:
    """WEBP/любой формат Pillow → PNG (для статичных стикеров)."""
    with Image.open(io.BytesIO(data)) as img:
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, format="PNG")
        return buf.getvalue()


def sniff_image_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "application/octet-stream"
