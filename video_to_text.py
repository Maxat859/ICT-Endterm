from functools import lru_cache
from pathlib import Path

import av
import cv2
import easyocr
from faster_whisper import WhisperModel


@lru_cache(maxsize=1)
def _speech_model(model_size):
    # Use model several times.
    return WhisperModel(
        model_size, device="cpu", compute_type="int8"
    )


@lru_cache(maxsize=1)
def _ocr_reader():
    return easyocr.Reader(["ru", "en"], gpu=False)


def video_to_text(
    video_path: str,
    *,
    model_size: str = "base",
    language: str | None = "ru",
    num_frames: int = 5,
) -> str:
    """NLP."""
    path = Path(video_path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Видео не найдено: {path}")

    if type(num_frames) is not int or not 1 <= num_frames <= 5:
        raise ValueError("num_frames должен быть от 1 до 5")

    # Check if there is a audio road.
    with av.open(str(path)) as container:
        has_audio = bool(container.streams.audio)

    speech = ""
    if has_audio:
        segments, _ = _speech_model(model_size).transcribe(
            str(path),
            language=language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        speech = " ".join(
            s.text.strip() for s in segments if s.text.strip()
        )

    # Take frames
    capture = cv2.VideoCapture(str(path))
    screen_lines = []
    seen = set()

    try:
        if not capture.isOpened():
            raise ValueError("Can not open the video")

        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            raise ValueError("Can not count the frames")

        count = min(num_frames, total)
        indices = (
            [total // 2]
            if count == 1
            else [
                round(i * (total - 1) / (count - 1))
                for i in range(count)
            ]
        )

        reader = _ocr_reader()

        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()

            if not ok:
                raise ValueError(f"Не удалось прочитать кадр {index}")

            for _, text, confidence in reader.readtext(frame):
                text = " ".join(text.split())
                key = text.casefold()

                # Remove errors
                if confidence >= 0.4 and text and key not in seen:
                    screen_lines.append(text)
                    seen.add(key)
    finally:
        capture.release()

    sections = []
    if speech:
        sections.append("[Речь]\n" + speech)
    if screen_lines:
        sections.append(
            "[Текст на экране]\n" + "\n".join(screen_lines)
        )

    return "\n\n".join(sections)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Путь к видеофайлу")
    args = parser.parse_args()

    print(video_to_text(args.video))