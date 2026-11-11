"""Анализ выборки кадров через Gemini (требуется GEMINI_API_KEY)."""

from __future__ import annotations

import json
import os


def extract_frames(video_path: str, num_frames: int = 8):
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(video_path)
    frames = []
    try:
        if not cap.isOpened():
            raise ValueError("Видео не открывается")
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            raise ValueError("Не удалось определить количество кадров")
        count = min(max(1, num_frames), total)
        positions = (
            [total // 2] if count == 1
            else [round(i * (total - 1) / (count - 1)) for i in range(count)]
        )
        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok:
                continue
            height, width = frame.shape[:2]
            if max(width, height) > 1280:
                scale = 1280 / max(width, height)
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb))
    finally:
        cap.release()
    return frames


def check_video_safety(video_path: str) -> dict:
    """Возвращает тот же контракт score/status/reasons, что и другие модули."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Не задан GEMINI_API_KEY. См. README.md")

    frames = extract_frames(video_path)
    if not frames:
        raise ValueError("Из видео не удалось извлечь кадры")

    from google import genai

    prompt = (
        "Проверь кадры публичного видео для задачи модерации. "
        "Есть ли явные сцены физического насилия, оружия, продажи запрещённых "
        "веществ или сексуального контента? Отличай учебные/новостные "
        "сюжеты от призывов к нарушению. Верни СТРОГО JSON-объект "
        'с полями {"unsafe": boolean, "risk_score": число от 0 до 100, '
        '"reasons": массив коротких строк на русском}. '
        "Это приблизительный индекс подозрительности, а не вероятность."
    )
    client = genai.Client(api_key=key)
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=[prompt, *frames],
            config={"response_mime_type": "application/json"},
        )
        if not response.text:
            raise RuntimeError("Модель не вернула ответа")
        data = json.loads(response.text)
        if not isinstance(data, dict) or not isinstance(data.get("unsafe"), bool):
            raise ValueError("Ответ Gemini имеет неверный формат")
        score = float(data["risk_score"])
        if not 0 <= score <= 100:
            raise ValueError("Неверный индекс риска в ответе Gemini")
        # Обнаруженная опасность не должна отображаться как зелёный сигнал.
        if data["unsafe"]:
            score = max(score, 70)
        raw_reasons = data.get("reasons")
        reasons = [str(x) for x in raw_reasons] if isinstance(raw_reasons, list) else []
        return {
            "score": round(score, 1),
            "is_danger": bool(data["unsafe"]) or score >= 70,
            "status": "ok",
            "reasons": reasons or ["Явных визуальных признаков опасности не выявлено"],
            "frames_checked": len(frames),
            "error": None,
        }
    finally:
        if hasattr(client, "close"):
            client.close()


# Совместимость с прежним названием функции.
check_video_frames = check_video_safety
