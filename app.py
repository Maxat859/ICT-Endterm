import streamlit as st
import os
import json
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go


try:
    from parser import parse_url
except ImportError:
    def parse_url(url: str) -> dict:
        return {
            "text": "Слышь, ты лох! Переходи по ссылке http://free-steam-prize.xyz и покупай запрещенный товар!",
            "video_path": None,
            "account_info": {"username": "user_9938123", "account_age_days": 2, "has_avatar": False}
        }

try:
    from text_check import check_text
except ImportError:
    def check_text(text: str) -> dict:
        return {
            "is_danger": True,
            "score": 82,
            "reasons": ["[Заглушка] Найдены оскорбления (буллинг)", "[Заглушка] Подозрение на нелегал"]
        }

try:
    from video_to_text import extract_text_from_video
except Exception as e:
    def extract_text_from_video(video_path: str) -> str:
        return f"[Заглушка] Модуль видео временно отключен из-за системной ошибки: {e}"
try:
    from vision_check import check_video_frames
except ImportError:
    def check_video_frames(video_path: str) -> dict:
        return {
            "is_danger": False,
            "score": 25,
            "reasons": ["[Заглушка] Подозрительная активность в кадре, но без прямых угроз"]
        }

try:
    from antifraud import check_antifraud
except ImportError:
    def check_antifraud(text: str, account_info: dict) -> dict:
        return {
            "is_danger": True,
            "score": 90,
            "reasons": ["[Заглушка] Фишинговая доменная зона .xyz", "[Заглушка] Аккаунт-однодневка без аватарки"]
        }



if "history" not in st.session_state:
    st.session_state.history = []

if "last_report" not in st.session_state:
    st.session_state.last_report = None



st.set_page_config(page_title="AI Модератор Соцсетей Pro", page_icon="🛡️", layout="wide")

with st.sidebar:
    st.header("📊 Статистика сессии")
    total_checks = len(st.session_state.history)
    high_risk_count = sum(1 for item in st.session_state.history if item["Итоговый риск (%)"] >= 70)
    
    st.metric("Всего проверок", total_checks)
    st.metric("Выявлено угроз (≥70%)", high_risk_count)
    
    st.divider()
    st.caption("Статус подключения модулей команды:")
    for mod_name, filename in [
        ("Парсер", "parser.py"),
        ("Текст (NLP)", "text_check.py"),
        ("Видео в текст", "video_to_text.py"),
        ("Видео (CV)", "vision_check.py"),
        ("Антифрод", "antifraud.py")
    ]:
        if os.path.exists(filename):
            st.success(f"✅ {mod_name} ({filename}) подключен")
        else:
            st.warning(f"⏳ {mod_name} — работает заглушка")

st.title("🛡️ AI-система детекции буллинга, фишинга и нелегального контента")
st.caption("Мультимодальный анализ комментариев, видеороликов и профилей пользователей")

mode = st.radio(
    "Выберите режим проверки:",
    ["🔗 По ссылке из соцсети", "🛠️ Ручной ввод (для теста отдельных модулей)"],
    horizontal=True
)

url_input = ""
manual_text = ""
uploaded_video = None
acc_age = 5
has_ava = False

if mode == "🔗 По ссылке из соцсети":
    url_input = st.text_input("Вставьте ссылку на пост, видео или профиль:", placeholder="https://t.me/... или https://youtube.com/...")
else:
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        manual_text = st.text_area("Текст комментария или описания:", "Привет! Забирай бесплатный приз тут: http://scam-link.xyz")
        uploaded_video = st.file_uploader("Загрузите видеоролик (необязательно):", type=["mp4", "mov", "avi"])
    with col_in2:
        st.markdown("**Параметры аккаунта (для теста антифрода):**")
        acc_age = st.number_input("Возраст аккаунта (в днях):", min_value=0, value=2)
        has_ava = st.checkbox("Есть аватарка", value=False)

if st.button("🚀 Запустить полный анализ", type="primary"):
    with st.spinner("Модели анализируют контент..."):

        if mode == "🔗 По ссылке из соцсети":
            source_label = url_input if url_input.strip() else "Тестовый URL (заглушка)"
            try:
                raw_data = parse_url(url_input)
            except Exception as e:
                st.error(f"Ошибка в модуле parser.py: {e}")
                raw_data = {"text": "", "video_path": None, "account_info": {}}
        else:
            source_label = "Ручной ввод"
            video_path = None
            if uploaded_video:
                video_path = "temp_video.mp4"
                with open(video_path, "wb") as f:
                    f.write(uploaded_video.read())
            raw_data = {
                "text": manual_text,
                "video_path": video_path,
                "account_info": {"username": "test_user", "account_age_days": acc_age, "has_avatar": has_ava}
            }

        full_text = raw_data.get("text", "")
        video_path = raw_data.get("video_path")
        account_info = raw_data.get("account_info", {})

        video_extracted_text = ""
        if video_path and os.path.exists(video_path):
            try:
                video_extracted_text = extract_text_from_video(video_path)
                full_text = f"{full_text}\n{video_extracted_text}"
            except Exception as e:
                video_extracted_text = f"Ошибка модуля video_to_text.py: {e}"

        try:
            res_text = check_text(full_text)
        except Exception as e:
            res_text = {"is_danger": False, "score": 0, "reasons": [f"Ошибка в text_check.py: {e}"]}

        try:
            if video_path and os.path.exists(video_path):
                res_vision = check_video_frames(video_path)
            else:
                res_vision = {"is_danger": False, "score": 0, "reasons": ["Видео не прикреплено"]}
        except Exception as e:
            res_vision = {"is_danger": False, "score": 0, "reasons": [f"Ошибка в vision_check.py: {e}"]}

        try:
            res_fraud = check_antifraud(full_text, account_info)
        except Exception as e:
            res_fraud = {"is_danger": False, "score": 0, "reasons": [f"Ошибка в antifraud.py: {e}"]}

        s_text = res_text.get("score", 0)
        s_vision = res_vision.get("score", 0)
        s_fraud = res_fraud.get("score", 0)
        max_score = max(s_text, s_vision, s_fraud)

        if max_score >= 70:
            verdict = "БЛОКИРОВКА (Высокий риск)"
        elif max_score >= 40:
            verdict = "РУЧНАЯ ПРОВЕРКА (Подозрительно)"
        else:
            verdict = "БЕЗОПАСНО"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report_data = {
            "timestamp": timestamp,
            "source": source_label,
            "verdict": verdict,
            "total_risk_score": max_score,
            "modules": {
                "text_analysis": res_text,
                "vision_analysis": res_vision,
                "antifraud_analysis": res_fraud
            },
            "extracted_video_text": video_extracted_text,
            "raw_input_data": raw_data
        }
        st.session_state.last_report = report_data

        st.session_state.history.insert(0, {
            "Время": timestamp,
            "Источник": source_label[:45] + ("..." if len(source_label) > 45 else ""),
            "Вердикт": verdict,
            "Итоговый риск (%)": max_score,
            "Текст (%)": s_text,
            "Видео (%)": s_vision,
            "Антифрод (%)": s_fraud
        })
        st.rerun()



if st.session_state.last_report:
    rep = st.session_state.last_report
    max_score = rep["total_risk_score"]
    res_text = rep["modules"]["text_analysis"]
    res_vision = rep["modules"]["vision_analysis"]
    res_fraud = rep["modules"]["antifraud_analysis"]

    st.divider()
    if max_score >= 70:
        st.error(f"🚨 ВЫСОКИЙ УРОВЕНЬ УГРОЗЫ! Итоговый риск: {max_score}% — Рекомендуется блокировка")
    elif max_score >= 40:
        st.warning(f"⚠️ ПОДОЗРИТЕЛЬНЫЙ КОНТЕНТ! Итоговый риск: {max_score}% — Требуется ручная проверка")
    else:
        st.success(f"✅ БЕЗОПАСНО! Итоговый риск: {max_score}% — Нарушений не выявлено")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=max_score,
            title={"text": "Итоговый индекс угрозы (%)"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#ff4b4b" if max_score >= 70 else ("#ffa726" if max_score >= 40 else "#2ecc71")},
                "steps": [
                    {"range": [0, 40], "color": "rgba(46, 204, 113, 0.2)"},
                    {"range": [40, 70], "color": "rgba(255, 167, 38, 0.2)"},
                    {"range": [70, 100], "color": "rgba(255, 75, 75, 0.2)"}
                ]
            }
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with chart_col2:
        s_t = res_text.get("score", 0)
        s_v = res_vision.get("score", 0)
        s_f = res_fraud.get("score", 0)
        # Если все нули, подставляем 1 для корректной отрисовки круга
        values = [s_t, s_v, s_f] if (s_t + s_v + s_f) > 0 else [1, 1, 1]

        fig_pie = go.Figure(data=[go.Pie(
            labels=["Буллинг и Нелегал (Текст)", "Опасный визуал (Видео)", "Фишинг и Боты (Антифрод)"],
            values=values,
            hole=0.45,
            marker_colors=["#ff6b6b", "#4dabf7", "#ffd43b"]
        )])
        fig_pie.update_layout(
            title_text="Распределение рисков по модулям",
            height=300,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # Детальные карточки по 3 направлениям
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("💬 Текст и Буллинг")
        st.metric("Риск текста", f"{res_text.get('score', 0)}%")
        for r in res_text.get("reasons", []):
            st.write(f"• {r}")

    with col2:
        st.subheader("🎬 Видео и Визуал")
        st.metric("Риск видео", f"{res_vision.get('score', 0)}%")
        for r in res_vision.get("reasons", []):
            st.write(f"• {r}")
        if rep["extracted_video_text"]:
            st.info(f"**Распознано из видео:** {rep['extracted_video_text']}")

    with col3:
        st.subheader("🕵️ Фишинг и Аккаунт")
        st.metric("Риск профиля/ссылок", f"{res_fraud.get('score', 0)}%")
        for r in res_fraud.get("reasons", []):
            st.write(f"• {r}")

    # Кнопки скачивания отчета для модератора
    st.subheader("📥 Выгрузка отчета для модератора")
    dl_col1, dl_col2, _ = st.columns([1, 1, 2])

    json_report = json.dumps(rep, ensure_ascii=False, indent=2)
    with dl_col1:
        st.download_button(
            label="📥 Скачать полный отчет (JSON)",
            data=json_report,
            file_name=f"moderation_report_{datetime.now().strftime('%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )

    txt_report = (
        f"=== АКТ МОДЕРАЦИИ КОНТЕНТА ===\n"
        f"Время проверки: {rep['timestamp']}\n"
        f"Источник: {rep['source']}\n"
        f"ИТОГОВЫЙ ВЕРДИКТ: {rep['verdict']} (Риск: {max_score}%)\n\n"
        f"1. Анализ текста ({res_text.get('score', 0)}%): {', '.join(res_text.get('reasons', []))}\n"
        f"2. Анализ видео ({res_vision.get('score', 0)}%): {', '.join(res_vision.get('reasons', []))}\n"
        f"3. Антифрод и профиль ({res_fraud.get('score', 0)}%): {', '.join(res_fraud.get('reasons', []))}\n"
    )
    with dl_col2:
        st.download_button(
            label="📄 Скачать акт проверки (TXT)",
            data=txt_report,
            file_name=f"moderation_act_{datetime.now().strftime('%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True
        )

    with st.expander("🔍 Посмотреть сырые данные от парсера (JSON)"):
        st.json(rep["raw_input_data"])



st.divider()
st.subheader("🕓 История проверок за сессию")

if st.session_state.history:
    df_history = pd.DataFrame(st.session_state.history)
    st.dataframe(df_history, use_container_width=True, hide_index=True)

    hist_col1, hist_col2, _ = st.columns([1, 1, 2])
    with hist_col1:
        csv_data = df_history.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📊 Выгрузить всю историю (CSV для Excel)",
            data=csv_data,
            file_name="moderation_history.csv",
            mime="text/csv",
            use_container_width=True
        )
    with hist_col2:
        if st.button("🗑️ Очистить историю", use_container_width=True):
            st.session_state.history = []
            st.session_state.last_report = None
            st.rerun()
else:
    st.info("История пока пуста. Запустите первый анализ выше, чтобы запись появилась в таблице.")