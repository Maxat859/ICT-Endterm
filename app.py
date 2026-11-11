"""Независимые тесты основных правил и единого контракта модулей."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from antifraud import check_account_bot, check_links, run_antifraud
from parser import detect_platform, parse_url
from text_check import check_text, find_danger_words
from vision_check import check_video_safety


class AntiFraudTests(unittest.TestCase):
    def test_legitimate_steam_is_not_phishing(self):
        result = check_links("https://store.steampowered.com/app/123")
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["is_phishing"])

    def test_suspicious_link(self):
        result = check_links("http://free-prize.xyz/bonus")
        self.assertGreaterEqual(result["score"], 70)

    def test_missing_profile_values_do_not_add_points(self):
        report = check_account_bot({"has_avatar": None, "account_age_days": None})
        self.assertEqual(report["bot_score_percent"], 0)
        self.assertEqual(len(report["unknown_fields"]), 2)

    def test_young_account(self):
        result = run_antifraud("", {
            "username": "user123456", "account_age_days": 2,
            "has_avatar": False, "bio": "https://example.com",
        })
        self.assertTrue(result["is_danger"])
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["score"], 70)


class TextTests(unittest.TestCase):
    def test_soup_is_not_a_drug_hit(self):
        self.assertNotIn("наркотики", find_danger_words("Добавь соль в суп"))

    def test_known_toxicity_model_result(self):
        fake_scores = {
            "non-toxic": 0.2, "dangerous": 0.1, "insult": 0.8,
            "toxicity": 0.82,
        }
        with patch("text_check._model_scores", return_value=fake_scores):
            result = check_text("Неприятное сообщение")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["score"], 82.0)
        self.assertTrue(result["is_danger"])

    def test_missing_model_does_not_claim_success(self):
        with patch("text_check._model_scores", side_effect=RuntimeError("offline")):
            result = check_text("Обычное сообщение")
        self.assertEqual(result["status"], "partial")
        self.assertIn("Недостаточно", result["verdict"])
        self.assertIsNotNone(result["error"])

    def test_bullying_rules_work_without_model(self):
        with patch("text_check._model_scores", side_effect=RuntimeError("offline")):
            result = check_text("Ты тупой урод")
        self.assertGreaterEqual(result["score"], 70)
        self.assertEqual(result["status"], "partial")


class ParserAndVisionTests(unittest.TestCase):
    def test_whitelisted_video_url(self):
        self.assertEqual(
            detect_platform("https://www.youtube.com/watch?v=abc"), "youtube"
        )

    def test_telegram_not_promised(self):
        with self.assertRaises(ValueError):
            detect_platform("https://t.me/example/12")

    def test_local_video_returns_profile_data(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "example.mp4"
            video.write_bytes(b"fake-video-for-parser-test")
            result = parse_url(str(video))
        self.assertIn("profile_data", result)
        self.assertIsNone(result["profile_data"]["account_age_days"])

    def test_gemini_key_required(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                check_video_safety("unavailable.mp4")


if __name__ == "__main__":
    unittest.main()
