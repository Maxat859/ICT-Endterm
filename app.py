"""Интерфейс проекта AI-модерации. Запуск: streamlit run app.py"""

from __future__ import annotations

import importlib
import json
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="AI Модератор", page_icon="🛡️", layout="wide")

MODULES = [
    ("Парсер", "parser", "parse_url"),
    ("Анализ текста", "text_check", "check_text"),
    ("Видео → текст", "video_to_text", "video_to_text"),
    ("Кадры Gemini", "vision_check", "check_video_safety"),
    ("Антифрод", "antifraud", "run_antifraud"),
]
MAX_UPLOAD_BYTES = 150 * 1024 * 1024


def load_function(module_name: str, function_name: str):
    module = importlib.import_module(module_name)
    function = getattr(module, function_name)
    if not callable(function):
        raise TypeError(f"{module_name}.{function_name} не является функцией")
    return function


def skipped(reason: str) -> dict:
    return {
        "score": None, "is_danger": False, "status": "skipped",
        "reasons": [reason], "error": None,
    }


def failed(error: Exception | str) -> dict:
    message = str(error)
    return {
        "score": None, "is_danger": None, "status": "error",
        "reasons": [f"Не удалось выполнить модуль: {message}"],
        "error": message,
    }


def run_module(module: str, name: str, *args) -> dict:
    try:
        result = load_function(module, name)(*args)
        if not isinstance(result, dict):
            raise TypeError(f"{module}.{name} должен возвращать словарь")
        if result.get("status") not in {"ok", "partial", "skipped"}:
            raise ValueError(f"{module}.{name}: неверный статус")
        score = result.get("score")
        if score is not None and (
            isinstance(score, bool) or not isinstance(score, (int, float))
            or not 0 <= score <= 100
        ):
            raise ValueError(f"{module}.{name}: индекс риска должен быть 0–100")
        return result
    except Exception as exc:
        return failed(exc)


def fmt_score(result: dict) -> str:
    value = result.get("score")
    return "—" if value is None else f"{value:g}/100"


def build_verdict(results: dict, extra_errors: list[str]) -> tuple[str, float | None, bool]:
    scores = [
        data["score"] for data in results.values()
        if data.get("score") is not None
    ]
    max_score = max(scores) if scores else None
    incomplete = bool(extra_errors) or any(
        data.get("status") in {"partial", "error"} for data in results.values()
    )
    if max_score is None:
        return "НЕТ ДОСТАТОЧНЫХ ДАННЫХ", None, True
    if max_score >= 70:
        verdict = "ВЫСОКИЙ РИСК — нужна проверка модератором"
    elif max_score >= 40:
        verdict = "ПОДОЗРИТЕЛЬНО — нужна ручная проверка"
    else:
        verdict = "ПРИЗНАКОВ НАРУШЕНИЙ НЕ НАЙДЕНО"
    if incomplete:
        verdict += " (анализ неполный)"
    return verdict, max_score, incomplete


if "history" not in st.session_state:
    st.session_state.history = []
if "last_report" not in st.session_state:
    st.session_state.last_report = None


with st.sidebar:
    st.header("📊 Статистика")
    st.metric("Проверок за сессию", len(st.session_state.history))
    st.metric(
        "Высокий риск",
        sum(
            1 for row in st.session_state.history
            if row["Индекс риска"] is not None and row["Индекс риска"] >= 70
        ),
    )
    st.divider()
    st.subheader("Модули проекта")
    for title, module, function in MODULES:
        try:
            load_function(module, function)
            st.success(f"✅ {title}")
        except Exception as exc:
            st.warning(f"⚠️ {title}: {type(exc).__name__}")
    st.caption("Зелёная отметка означает, что модуль импортируется. Модель и API проверяются при запуске анализа.")


st.title("🛡️ AI-модератор социальных сетей")
st.caption("Текст • видео • речь • ссылки • признаки подозрительных аккаунтов")
st.info(
    "Оценка 0–100 — это **индекс риска**, а не доказанная вероятность нарушения. "
    "Решение о блокировке должен принимать человек."
)

mode = st.radio(
    "Способ ввода",
    ["🔗 Публичная ссылка", "🛠️ Ручной ввод / видео"],
    horizontal=True,
)

source_url = ""
text_input = ""
uploaded_video = None
download_video = False
max_comments = 0
profile_data = {}

if mode == "🔗 Публичная ссылка":
    source_url = st.text_input(
        "Ссылка на YouTube, TikTok или Instagram",
        placeholder="https://www.youtube.com/watch?v=...",
    )
    download_video = st.checkbox(
        "Скачать видео для анализа речи и кадров",
        value=True,
        help="Загрузка зависит от доступности публичного ролика и может занять время.",
    )
    max_comments = st.slider("Комментарии YouTube (если доступны)", 0, 20, 5)
    st.caption("Telegram сейчас не поддерживается. Закрытые посты и аккаунты не обходятся.")
else:
    left, right = st.columns(2)
    with left:
        text_input = st.text_area(
            "Комментарий или описание",
            placeholder="Вставьте сюда текст для анализа...",
            height=130,
        )
        uploaded_video = st.file_uploader(
            "Загрузить видео (до 150 МБ)",
            type=["mp4", "mov", "mkv", "webm", "m4v"],
        )
    with right:
        st.markdown("**Данные аккаунта (если известны):**")
        username = st.text_input("Имя аккаунта", value="test_user")
        account_age = st.number_input("Возраст аккаунта в днях", min_value=0, value=30)
        has_avatar = st.checkbox("У аккаунта есть аватар", value=True)
        profile_data = {
            "username": username,
            "account_age_days": int(account_age),
            "has_avatar": has_avatar,
            "bio": "",
        }

use_gemini = st.checkbox(
    "Разрешить анализ кадров через Gemini (кадры отправляются во внешний AI-сервис)",
    value=False,
)
if use_gemini:
    st.caption("Для анализа кадров необходим GEMINI_API_KEY. Не загружайте чужие частные видео без разрешения.")


if st.button("🚀 Запустить анализ", type="primary"):
    if mode == "🔗 Публичная ссылка" and not source_url.strip():
        st.error("Сначала вставьте ссылку.")
        st.stop()
    if mode != "🔗 Публичная ссылка" and not text_input.strip() and uploaded_video is None:
        st.error("Введите текст или загрузите видео.")
        st.stop()
    if uploaded_video is not None and uploaded_video.size > MAX_UPLOAD_BYTES:
        st.error("Размер видео превышает 150 МБ.")
        st.stop()

    with st.spinner("Проверка выполняется. Первый запуск моделей может быть долгим..."):
        errors = []
        source_label = source_url if mode == "🔗 Публичная ссылка" else "Ручной ввод"
        video_text = ""
        raw_data = {}
        with tempfile.TemporaryDirectory(prefix="ai_moderation_") as workdir:
            if mode == "🔗 Публичная ссылка":
                try:
                    parse_url = load_function("parser", "parse_url")
                    raw_data = parse_url(
                        source_url.strip(),
                        download_video=download_video,
                        output_dir=workdir,
                        max_comments=max_comments,
                    )
                except Exception as exc:
                    st.error(f"Не удалось обработать ссылку: {exc}")
                    st.stop()
            else:
                video_path = None
                if uploaded_video is not None:
                    suffix = Path(uploaded_video.name).suffix.lower()
                    video_path = str(Path(workdir) / ("uploaded" + suffix))
                    with open(video_path, "wb") as target:
                        target.write(uploaded_video.getvalue())
                raw_data = {
                    "source": "manual", "text": text_input,
                    "video_path": video_path, "profile_data": profile_data,
                    "warnings": [],
                }

            full_text = str(raw_data.get("text") or "")
            path = raw_data.get("video_path")
            video_available = bool(path and Path(path).is_file())
            warnings = [str(w) for w in (raw_data.get("warnings") or [])]

            if video_available:
                try:
                    converter = load_function("video_to_text", "video_to_text")
                    video_text = converter(str(path))
                    if video_text:
                        full_text = "\n".join(filter(None, [full_text, video_text]))
                except Exception as exc:
                    errors.append(f"Видео → текст: {exc}")
            elif mode == "🔗 Публичная ссылка" and download_video:
                warnings.append("Видео недоступно: проверены только доступные метаданные и текст")

            result_text = (
                run_module("text_check", "check_text", full_text)
                if full_text.strip() else skipped("Нет текста для проверки")
            )
            result_fraud = run_module(
                "antifraud", "run_antifraud",
                full_text, raw_data.get("profile_data", {}),
            )
            if video_available and use_gemini:
                result_vision = run_module("vision_check", "check_video_safety", str(path))
            else:
                result_vision = skipped(
                    "Gemini не включён" if video_available else "Видео отсутствует"
                )

            results = {
                "Текст": result_text,
                "Видео (кадры)": result_vision,
                "Антифрод": result_fraud,
            }
            verdict, max_score, incomplete = build_verdict(results, errors)

            safe_raw = dict(raw_data)
            # Временное видео удаляется после анализа; не храним нерабочую ссылку на него.
            safe_raw["video_path"] = (
                Path(path).name if video_available else None
            )
            report = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": source_label,
                "verdict": verdict,
                "total_risk_index": max_score,
                "incomplete": incomplete,
                "modules": results,
                "extracted_video_text": video_text,
                "warnings": warnings,
                "errors": errors,
                "raw_input_data": safe_raw,
            }

        st.session_state.last_report = report
        st.session_state.history.insert(0, {
            "Время": report["timestamp"],
            "Источник": source_label[:55],
            "Вердикт": verdict,
            "Индекс риска": max_score,
            "Текст": result_text.get("score"),
            "Видео": result_vision.get("score"),
            "Антифрод": result_fraud.get("score"),
        })
        st.rerun()


if st.session_state.last_report:
    report = st.session_state.last_report
    score = report["total_risk_index"]
    st.divider()
    if score is None:
        st.error(report["verdict"])
    elif score >= 70:
        st.error(f"🚨 {report['verdict']} — индекс {score:g}/100")
    elif report["incomplete"]:
        st.warning(f"⚠️ {report['verdict']} — индекс {score:g}/100")
    elif score >= 40:
        st.warning(f"⚠️ {report['verdict']} — индекс {score:g}/100")
    else:
        st.success(f"✅ {report['verdict']} — индекс {score:g}/100")

    for warning in report["warnings"]:
        st.info(warning)
    for error in report["errors"]:
        st.warning(error)
    if report["incomplete"]:
        st.warning("Проверка неполная: низкий индекс нельзя считать гарантией безопасности.")

    import plotly.graph_objects as go

    c1, c2 = st.columns([1, 2])
    with c1:
        if score is not None:
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=score,
                title={"text": "Максимальный индекс риска"},
                gauge={"axis": {"range": [0, 100]}},
            ))
            fig.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        plotted = [
            (title, result["score"])
            for title, result in report["modules"].items()
            if result.get("score") is not None
        ]
        if plotted:
            fig = go.Figure(go.Bar(
                x=[value for _, value in plotted],
                y=[title for title, _ in plotted],
                orientation="h",
                text=[f"{value:g}/100" for _, value in plotted],
                textposition="auto",
            ))
            fig.update_layout(
                title="Индекс по каждому модулю", xaxis_range=[0, 100],
                height=280, margin=dict(l=25, r=25, t=50, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

    columns = st.columns(3)
    for column, (title, result) in zip(columns, report["modules"].items()):
        with column:
            st.subheader(title)
            st.metric("Индекс риска", fmt_score(result))
            if result.get("status") == "partial":
                st.warning("Частичный анализ")
            elif result.get("status") == "error":
                st.error("Ошибка модуля")
            elif result.get("status") == "skipped":
                st.info("Не проверялось")
            for reason in result.get("reasons", []):
                st.write("• " + str(reason))

    if report["extracted_video_text"]:
        with st.expander("📝 Текст, распознанный в видео"):
            st.text(report["extracted_video_text"])

    st.subheader("📥 Скачать отчёт")
    a, b = st.columns(2)
    with a:
        st.download_button(
            "Скачать JSON",
            data=json.dumps(report, ensure_ascii=False, indent=2, default=str),
            file_name="moderation_report.json",
            mime="application/json",
            use_container_width=True,
        )
    lines = [
        "ОТЧЁТ AI-МОДЕРАЦИИ",
        f"Дата: {report['timestamp']}",
        f"Источник: {report['source']}",
        f"Вердикт: {report['verdict']}",
        f"Индекс: {score if score is not None else 'нет данных'}/100",
    ]
    for title, result in report["modules"].items():
        lines.append(f"\n{title}: {fmt_score(result)} ({result.get('status')})")
        lines.extend("• " + str(x) for x in result.get("reasons", []))
    with b:
        st.download_button(
            "Скачать TXT",
            data="\n".join(lines),
            file_name="moderation_report.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with st.expander("Исходные данные"):
        st.json(report["raw_input_data"])

st.divider()
st.subheader("🕓 История за сессию")
if st.session_state.history:
    import pandas as pd

    history = pd.DataFrame(st.session_state.history)
    st.dataframe(history, use_container_width=True, hide_index=True)
    a, b = st.columns(2)
    with a:
        st.download_button(
            "Скачать историю CSV",
            history.to_csv(index=False).encode("utf-8-sig"),
            "moderation_history.csv",
            mime="text/csv",
        )
    with b:
        if st.button("Очистить историю"):
            st.session_state.history = []
            st.session_state.last_report = None
            st.rerun()
else:
    st.caption("История пока пуста.")
