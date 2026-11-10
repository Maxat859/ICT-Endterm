"""Streamlit demo for the team's existing modules.

Role 6 owns the final UI; this is an integration draft for team review.
Run: streamlit run app.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from parser import parse_url

st.set_page_config(page_title="Content Shield · ICT Endterm", page_icon="🛡️", layout="wide")
st.title("🛡️ Content Shield")
st.caption("Учебный прототип · сбор данных → обработка → анализ доступными модулями")
st.info(
    "Демо работает с публичными ссылками YouTube, TikTok и Instagram Reels, "
    "а также с загруженным видео. Некоторые платформы могут ограничивать доступ."
)

with st.form("scan"):
    source = st.text_input("Ссылка на публикацию", placeholder="https://www.youtube.com/watch?v=...")
    upload = st.file_uploader("Или загрузи своё видео", type=["mp4", "webm", "mov", "mkv", "m4v"])
    c1, c2 = st.columns(2)
    with c1:
        comments_count = st.slider("Комментарии YouTube", min_value=0, max_value=20, value=0)
    with c2:
        download_video = st.checkbox("Скачать видео по ссылке", value=False)
    transcribe = st.checkbox("Распознать речь и надписи (Whisper + OCR)", value=False)
    submitted = st.form_submit_button("🔎 Проверить", type="primary", use_container_width=True)

if submitted:
    if upload is None and not source.strip():
        st.error("Вставь ссылку или загрузи видео.")
        st.stop()
    if upload is not None and source.strip():
        st.warning("При загрузке файла ссылка игнорируется.")

    data = None
    try:
        if upload is not None:
            with tempfile.TemporaryDirectory(prefix="ict_endterm_") as temp_dir:
                upload_path = Path(temp_dir) / Path(upload.name).name
                upload_path.write_bytes(upload.getvalue())
                with st.spinner("Читаю видео..."):
                    data = parse_url(str(upload_path))
                    if transcribe:
                        from video_to_text import video_to_text
                        with st.spinner("Распознаю речь и надписи..."):
                            data["transcribed_text"] = video_to_text(data["video_path"])
                # File is deleted after this block; never expose a broken local path.
                data["video_path"] = None
        else:
            with st.spinner("Получаю данные публикации..."):
                data = parse_url(
                    source.strip(),
                    download_video=download_video or transcribe,
                    max_comments=comments_count,
                )
            if transcribe and data.get("video_path"):
                from video_to_text import video_to_text
                with st.spinner("Распознаю речь и надписи..."):
                    data["transcribed_text"] = video_to_text(data["video_path"])
    except Exception as error:
        st.error(f"Не удалось завершить обработку: {error}")
        st.stop()

    st.success("Обработка завершена")
    details = data.get("metadata") or {}
    k1, k2, k3 = st.columns(3)
    k1.metric("Платформа", str(data.get("source", "?")))
    k2.metric("Комментарии", len(data.get("comments") or []))
    k3.metric("Длительность, сек", details.get("duration") or "—")
    st.subheader(data.get("title") or "Видео без названия")
    if details.get("channel"):
        st.caption(f"Автор/канал: {details['channel']}")

    st.subheader("📝 Извлечённый текст")
    extracted = data.get("text") or ""
    transcript = data.get("transcribed_text") or ""
    st.text_area("Название, описание и комментарии", value=extracted, height=180)
    if transcript:
        st.text_area("Речь и текст с экрана", value=transcript, height=180)

    # Real antifraud integration; avoid inventing bot scores for unknown profiles.
    try:
        from antifraud import check_links, check_account_bot
        report = check_links("\n".join([extracted, transcript]))
        st.subheader("🔗 Антифрод: ссылки")
        st.json(report)
        profile = data.get("profile_data") or {}
        if profile.get("has_avatar") is not None and profile.get("account_age_days") is not None:
            st.subheader("👤 Антифрод: аккаунт")
            st.json(check_account_bot(profile))
        else:
            st.caption("Скоринг аккаунта пропущен: платформа не предоставила возраст и аватар. Неизвестное ≠ подозрительное.")
    except ImportError:
        st.warning("Модуль antifraud.py пока не найден.")

    st.subheader("🤖 ML-анализ")
    if transcript:
        st.success("Модуль Whisper/EasyOCR запущен и вернул текст. Это ещё не классификация нарушений.")
    elif transcribe:
        st.warning("Распознанный текст отсутствует: проверь звук и надписи.")
    else:
        st.info("Включи распознавание речи и надписей, чтобы протестировать предобученные модели.")
    st.caption("Модули text_check.py / vision_check.py подключаются командой отдельно. Метрики и итоговый риск пока не рассчитываются.")

    for warning in data.get("warnings") or []:
        st.warning(warning)
    with st.expander("Полный JSON для интеграции"):
        st.json(data)
    st.download_button(
        "⬇️ Скачать результат JSON",
        data=json.dumps(data, ensure_ascii=False, indent=2),
        file_name="content_shield_result.json", mime="application/json",
    )
