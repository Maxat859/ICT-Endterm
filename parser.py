"""Role 1: collect public YouTube metadata or prepare a local video for analysis.

Install: python -m pip install yt-dlp
"""

import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def clean_text(value):
    """Remove HTML tags, entities and extra whitespace."""
    if not isinstance(value, str):
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_url(source, download_video=False, output_dir="downloads", max_comments=0):
    """Return a common dictionary for text, video and antifraud modules.

    source: public YouTube URL or path to an existing local video.
    download_video: download video for video_to_text.py and vision_check.py.
    max_comments: request up to 20 public YouTube comments (may be unavailable).
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Укажи ссылку на YouTube или путь к видео")
    if not isinstance(max_comments, int) or not 0 <= max_comments <= 20:
        raise ValueError("max_comments должен быть от 0 до 20")

    source = source.strip()
    local_file = Path(source).expanduser()
    if local_file.is_file():
        if local_file.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
            raise ValueError("Поддерживаются локальные видео: MP4, MOV, MKV, WEBM")
        return {
            "source": "local", "source_url": None,
            "title": local_file.stem, "description": "", "text": "",
            "comments": [], "video_path": str(local_file.resolve()),
            "profile_data": {"username": None, "has_avatar": None,
                             "account_age_days": None, "bio": ""},
            "metadata": {"id": local_file.stem, "duration": None, "view_count": None},
            "warnings": ["Локальное видео: текст и профиль не получены из соцсети"],
        }

    parsed = urlsplit(source)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"https", "http"} or host not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"
    }:
        raise ValueError("Пока поддерживаются ссылки YouTube и локальные видео")

    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
    except ImportError as error:
        raise RuntimeError("Установи библиотеку: python -m pip install yt-dlp") from error

    folder = Path(output_dir)
    if download_video:
        folder.mkdir(parents=True, exist_ok=True)

    options = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "skip_download": not download_video,
        "outtmpl": str(folder / "%(id)s.%(ext)s"),
        "format": "bv*+ba/bv*/ba",
        "getcomments": max_comments > 0,
    }
    if max_comments:
        options["extractor_args"] = {
            "youtube": {"max_comments": [f"{max_comments},all,all,all"]}
        }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(source, download=download_video)
            if not isinstance(info, dict):
                raise ValueError("YouTube не вернул данные о видео")
            guessed_video_path = Path(ydl.prepare_filename(info))
    except DownloadError as error:
        raise RuntimeError(f"Не удалось получить видео: {error}") from error

    comments = [
        {"author": clean_text(item.get("author")),
         "text": clean_text(item.get("text"))}
        for item in (info.get("comments") or [])[:max_comments]
        if isinstance(item, dict) and clean_text(item.get("text"))
    ]
    title = clean_text(info.get("title"))
    description = clean_text(info.get("description"))
    text_parts = [title, description] + [comment["text"] for comment in comments]

    video_path = None
    if download_video and guessed_video_path.is_file():
        video_path = str(guessed_video_path.resolve())

    warnings = []
    if max_comments and not comments:
        warnings.append("Комментарии отсутствуют или недоступны")
    if download_video and video_path is None:
        warnings.append("Путь к скачанному видео не обнаружен")

    return {
        "source": "youtube", "source_url": source,
        "title": title, "description": description,
        "text": "\n".join(part for part in text_parts if part),
        "comments": comments, "video_path": video_path,
        "profile_data": {
            "username": info.get("uploader_id") or info.get("channel_id"),
            "has_avatar": None, "account_age_days": None, "bio": "",
        },
        "metadata": {
            "id": info.get("id"), "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "channel": clean_text(info.get("channel")),
            "upload_date": info.get("upload_date"),
        },
        "warnings": warnings,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Парсер видео и метаданных YouTube")
    cli.add_argument("source", help="Ссылка YouTube или локальный видеофайл")
    cli.add_argument("--download", action="store_true", help="Скачать видео")
    cli.add_argument("--comments", type=int, default=0, help="До 20 комментариев")
    args = cli.parse_args()
    data = parse_url(args.source, download_video=args.download, max_comments=args.comments)
    print(json.dumps(data, ensure_ascii=False, indent=2))
