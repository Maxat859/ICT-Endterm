"""Role 1 — public video metadata and local video preparation.

Supports public YouTube videos/Shorts, TikTok posts and Instagram posts/Reels
via yt-dlp. Does NOT bypass logins, privacy controls or rate limits.

External requirement: python -m pip install yt-dlp
For download/conversion: ffmpeg must be on PATH.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

TIKTOK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)

MEDIA_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
SUPPORTED_HOSTS = {
    "youtube": {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"},
    "tiktok": {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"},
    "instagram": {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am", "www.instagr.am"},
}


def clean_text(value: object) -> str:
    """Normalize publicly available text to a single clean line."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()


def detect_platform(source: str) -> str:
    """Detect the platform from a *validated* URL host (not substring matching)."""
    parsed = urlsplit(source)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Укажи полную публичную ссылку https://...")
    host = parsed.hostname.casefold().rstrip(".")
    if parsed.username is not None or parsed.password is not None or parsed.port not in (None, 80, 443):
        raise ValueError("Используй публичную ссылку без данных входа и нестандартного порта")
    for platform, hosts in SUPPORTED_HOSTS.items():
        if host in hosts:
            return platform
    raise ValueError("Поддерживаются YouTube, TikTok, Instagram и локальные видео")


def _profile(info: dict) -> dict:
    """Unknown account attributes are None, NEVER assumed suspicious."""
    return {
        "username": info.get("uploader_id") or info.get("uploader") or info.get("channel_id"),
        "has_avatar": None,
        "account_age_days": None,
        "bio": "",
    }


def _find_download(info: dict, folder: Path, guessed: Path) -> Path | None:
    """Locate the actual download; yt-dlp may change the extension after merging."""
    paths = []
    for item in info.get("requested_downloads") or []:
        if isinstance(item, dict):
            for key in ("filepath", "filename"):
                if item.get(key):
                    paths.append(Path(item[key]))
    if info.get("filepath"):
        paths.append(Path(info["filepath"]))
    paths.append(guessed)
    video_id = str(info.get("id") or "")
    if video_id:
        paths.extend(sorted(p for p in folder.glob("*") if p.stem == video_id))
    for path in paths:
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
            return path
    return None


def _to_mp4(source: Path) -> Path:
    """Make video friendlier for OpenCV/Whisper. Do not delete the source."""
    if source.suffix.lower() == ".mp4":
        with source.open("rb") as media:
            if media.read(512).lstrip().lower().startswith((b"<html", b"<!doctype", b"<head")):
                raise RuntimeError("Сервер вернул HTML-страницу вместо видео")
        return source
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg не найден: установи FFmpeg и проверь ffmpeg -version")
    target = source.with_suffix(".mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", str(source),
             "-c:v", "libx264", "-c:a", "aac", str(target)],
            check=True, timeout=300,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Не удалось преобразовать видео в MP4: {error}") from error
    if not target.is_file():
        raise RuntimeError("FFmpeg завершился, но MP4-файл не найден")
    return target


def _tiktok_embed(source: str) -> dict:
    """Read public embed metadata when the video extractor is unavailable."""
    endpoint = "https://www.tiktok.com/oembed?" + urlencode({"url": source})
    with urlopen(endpoint, timeout=15) as response:
        embed = json.load(response)
    if not isinstance(embed, dict) or not any(
        embed.get(key) for key in ("title", "author_name", "embed_product_id")
    ):
        raise ValueError("TikTok не вернул данные публикации")
    return {"id": embed.get("embed_product_id"), "title": embed.get("title"),
            "uploader": embed.get("author_name")}


def parse_url(
    source: str,
    download_video: bool = False,
    output_dir: str = "downloads",
    max_comments: int = 0,
) -> dict:
    """Return a shared dict for text/video/antifraud modules.

    max_comments works for YouTube only; TikTok/Instagram comments are not
    promised because yt-dlp extractors may not provide them.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Укажи ссылку или путь к локальному видео")
    if type(max_comments) is not int or not 0 <= max_comments <= 20:
        raise ValueError("max_comments должен быть целым числом от 0 до 20")
    source = source.strip()
    local_file = Path(source).expanduser()
    if not re.match(r"^https?://", source, re.I) and local_file.is_file():
        if local_file.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ValueError("Файл должен быть видео: MP4, MOV, MKV, WEBM или M4V")
        return {
            "source": "local", "source_url": None,
            "title": local_file.stem, "description": "", "text": "", "comments": [],
            "video_path": str(local_file.resolve()),
            "profile_data": _profile({}),
            "metadata": {"id": local_file.stem, "duration": None, "view_count": None,
                         "channel": "", "upload_date": None},
            "warnings": ["Локальный файл: данные профиля и описание отсутствуют"],
        }

    platform = detect_platform(source)
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
    except ImportError as error:
        raise RuntimeError("Установи yt-dlp: python -m pip install -U yt-dlp") from error

    folder = Path(output_dir).expanduser()
    if download_video:
        folder.mkdir(parents=True, exist_ok=True)
    options = {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": not download_video,
        "outtmpl": str(folder / "%(id)s.%(ext)s"),
        "format": "b[ext=mp4]/b/bv*+ba" if shutil.which("ffmpeg") else "best",
        "playlistend": 1,
        "getcomments": max_comments > 0 and platform == "youtube",
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
    }
    if platform == "tiktok":
        # Same as yt-dlp --user-agent; TikTok may reject the default request.
        options["http_headers"] = {"User-Agent": TIKTOK_USER_AGENT}
    if max_comments and platform == "youtube":
        options["extractor_args"] = {
            "youtube": {"max_comments": [f"{max_comments},all,all,all"]}
        }
    warnings = []
    guessed = None
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(source, download=download_video)
            if not isinstance(info, dict):
                raise RuntimeError("Не удалось извлечь данные публикации")
            # Instagram video carousels are returned as playlists. Use one post item.
            if "entries" in info:
                entry = next((item for item in info["entries"] or [] if isinstance(item, dict)), None)
                if entry is None:
                    raise RuntimeError("В публикации нет доступного видео")
                info = {**info, **entry}
            guessed = Path(ydl.prepare_filename(info)) if download_video else None
    except DownloadError as error:
        if platform != "tiktok" and (download_video or max_comments):
            # Retry metadata only so a blocked CDN/comment endpoint cannot erase the report.
            result = parse_url(source, output_dir=output_dir)
            result["warnings"].append(f"Получены только метаданные. Ошибка загрузки: {error}")
            return result
        if platform != "tiktok":
            raise RuntimeError(f"Платформа не предоставила данные: {error}") from error
        try:
            info = _tiktok_embed(source)
        except (OSError, ValueError) as embed_error:
            raise RuntimeError(f"TikTok: {error}. Ошибка oEmbed: {embed_error}") from embed_error
        warnings.append("TikTok предоставил только открытые метаданные через oEmbed.")

    comments = []
    if platform == "youtube":
        for item in (info.get("comments") or [])[:max_comments]:
            if isinstance(item, dict):
                body = clean_text(item.get("text"))
                if body:
                    comments.append({"author": clean_text(item.get("author")), "text": body})

    title = clean_text(info.get("title") or info.get("fulltitle"))
    description = clean_text(info.get("description"))
    text = "\n".join(filter(None, [title, description] + [c["text"] for c in comments]))
    if not text:
        warnings.append("У публикации нет доступного текста для анализа.")
    video_path = None
    if download_video and guessed is not None:
        found = _find_download(info, folder, guessed)
        if found is not None:
            try:
                video_path = str(_to_mp4(found).resolve())
            except RuntimeError as error:
                warnings.append(str(error))

    if max_comments and platform != "youtube":
        warnings.append("Комментарии TikTok/Instagram пока не поддерживаются")
    elif max_comments and not comments:
        warnings.append("Комментарии YouTube отсутствуют или недоступны")
    if download_video and not video_path:
        warnings.append("Скачанное видео не найдено")
    warnings.append("Возраст аккаунта и наличие аватара не проверены")

    return {
        "source": platform, "source_url": source,
        "title": title, "description": description, "text": text,
        "comments": comments, "video_path": video_path,
        "profile_data": _profile(info),
        "metadata": {
            "id": info.get("id"), "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "channel": clean_text(info.get("channel") or info.get("uploader")),
            "upload_date": info.get("upload_date"),
        },
        "warnings": warnings,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="YouTube/TikTok/Instagram video metadata parser")
    cli.add_argument("source", help="Публичная ссылка или путь к видео")
    cli.add_argument("--download", action="store_true", help="Скачать и подготовить MP4")
    cli.add_argument("--comments", type=int, default=0, help="Число комментариев YouTube: 0–20")
    args = cli.parse_args()
    print(json.dumps(
        parse_url(args.source, download_video=args.download, max_comments=args.comments),
        ensure_ascii=False, indent=2,
    ))
