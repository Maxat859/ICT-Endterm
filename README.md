Роль №3 — перевод видео в текст

Модуль video_to_text.py распознаёт речь и надписи на пяти кадрах.
Нужен Python 3.10–3.12.

Установка:
python -m pip install faster-whisper easyocr opencv-python-headless

Запуск:
python video_to_text.py demo.mp4

При первом запуске нужен интернет для скачивания моделей.
Тестовое видео demo.mp4 проверяет только распознавание надписей.

Подключение к app.py:
from video_to_text import video_to_text
text = video_to_text("путь_к_видео.mp4")