"""Offline unit tests: no social-network requests and no large ML downloads."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parser


class FakeYoutubeDL:
    info = {}
    options = None

    def __init__(self, options):
        FakeYoutubeDL.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return dict(FakeYoutubeDL.info)

    def prepare_filename(self, info):
        return self.options["outtmpl"].replace("%(id)s", str(info["id"])).replace("%(ext)s", "webm")


class ParserTests(unittest.TestCase):
    def fake_yt_dlp(self, data):
        FakeYoutubeDL.info = data
        package = types.ModuleType("yt_dlp")
        utils = types.ModuleType("yt_dlp.utils")
        package.YoutubeDL = FakeYoutubeDL
        utils.DownloadError = type("DownloadError", (Exception,), {})
        return patch.dict(sys.modules, {"yt_dlp": package, "yt_dlp.utils": utils})

    def test_local_video(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "demo.mp4"
            path.write_bytes(b"demo-placeholder")
            got = parser.parse_url(str(path))
            self.assertEqual(got["source"], "local")
            self.assertEqual(got["video_path"], str(path.resolve()))
            self.assertIsNone(got["profile_data"]["account_age_days"])

    def test_youtube_comments_and_text(self):
        info = {"id": "vid123", "title": "Hey <b>guys</b>", "description": "A   demo",
                "comments": [{"author": "Ada", "text": "Buy  now"}]}
        with self.fake_yt_dlp(info):
            got = parser.parse_url("https://www.youtube.com/watch?v=vid123", max_comments=2)
        self.assertEqual(got["source"], "youtube")
        self.assertEqual(got["comments"][0]["text"], "Buy now")
        self.assertIn("Hey guys", got["text"])
        self.assertTrue(FakeYoutubeDL.options["getcomments"])

    def test_tiktok_metadata_uses_same_contract(self):
        info = {"id": "777", "title": "Clip", "description": "Hello", "uploader": "user7"}
        with self.fake_yt_dlp(info):
            got = parser.parse_url("https://www.tiktok.com/@user7/video/777", max_comments=5)
        self.assertEqual(got["source"], "tiktok")
        self.assertEqual(got["profile_data"]["username"], "user7")
        self.assertEqual(got["comments"], [])
        self.assertFalse(FakeYoutubeDL.options["getcomments"])
        self.assertTrue(any("пока" in x for x in got["warnings"]))

    def test_instagram_reels_metadata(self):
        info = {"id": "abc", "title": "Reel", "description": "Original audio"}
        with self.fake_yt_dlp(info):
            got = parser.parse_url("https://www.instagram.com/reel/abc/")
        self.assertEqual(got["source"], "instagram")
        self.assertIn("Original audio", got["text"])

    def test_disallow_unknown_host(self):
        with self.assertRaises(ValueError):
            parser.parse_url("https://youtube.com.evil.example/video")

    def test_download_and_mp4_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "v001.webm"
            path.write_bytes(b"synthetic-webm")
            info = {"id": "v001", "title": "Clip"}

            def fake_ffmpeg(args, **kwargs):
                Path(args[-1]).write_bytes(b"synthetic-mp4")

            with self.fake_yt_dlp(info), patch.object(parser.shutil, "which", return_value="ffmpeg"), \
                 patch.object(parser.subprocess, "run", side_effect=fake_ffmpeg):
                got = parser.parse_url("https://www.youtube.com/watch?v=v001", True, folder)
            self.assertTrue(got["video_path"].endswith(".mp4"))
            self.assertTrue(Path(got["video_path"]).exists())


if __name__ == "__main__":
    unittest.main()
