import re
MODEL_NAME = "cointegrated/rubert-tiny-toxicity"

# Модель грузится один раз (при первом вызове), чтобы не тормозить импорт
_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model
    if _model is None:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


# ---------- Словарь стоп-слов (корни, ищем по началу слова) ----------
# Дополняйте списки своими словами — это самая простая часть для улучшения.
STOP_WORDS = {
    "наркотики": [
        "закладк", "кладмен", "мефедрон",
        "гашиш", "гаш", "шишк", "бошк", "спайс", "амфетамин", "амф",
        "кокаин", "героин", "экстази", "мдма", "лсд",
        "насвай", "альфа-pvp", "a-pvp",
    ],
    "оружие": [
        "пистолет", "травмат", "калаш",
        "патрон", "глок", "glock", "взрывчатк", "граната", "оружи",
    ],
    "казино_и_ставки": [
        "казино", "casino", "1xbet", "1хбет", "мелбет", "пинап", "pin-up",
        "pinup", "слоты", "букмекер",
        "промокод на депозит", "фриспин", "бонус за регистрацию", "занос",
    ],
    "мошенничество": [
        "быстрый заработок", "заработок без вложений", "пассивный доход",
        "переведи на карту", "скинь код", "код из смс", "дроп", "обнал",
        "инвестиции под",
    ],
    "угрозы_и_буллинг": [
        "убью", "убить", "зарежу", "прибью", "закопаю", "найду тебя",
        "иди сдохни", "сдохни", "выпились", "урод", "чмо", "лох",
        "дебил", "даун", "тупая", "тупой", "жирная", "жирный",
    ],
    "мат": [
        "хуй", "хуе", "хуя", "пизд", "ебат", "ебан", "ебал", "ебу", "ёб",
        "бля", "сука", "суки", "мудак", "мудил", "гандон", "пидор", "шлюх",
    ],
}


def find_danger_words(text: str) -> dict:
    """Ищет стоп-слова. Возвращает {категория: [найденные слова]}."""
    low = " " + text.lower().replace("ё", "е") + " "
    found = {}
    for category, words in STOP_WORDS.items():
        hits = []
        for w in words:
            w_norm = w.lower().replace("ё", "е")
            # слово должно начинаться с начала слова (чтобы "соль" не ловилось в "консоль")
            if re.search(r"(?<![а-яa-z0-9])" + re.escape(w_norm), low):
                hits.append(w.strip())
        if hits:
            found[category] = sorted(set(hits))
    return found


def _model_scores(text: str) -> dict:
    """Прогоняет текст через модель. Возвращает вероятности по классам."""
    import torch

    tokenizer, model = _load_model()
    with torch.no_grad():
        inputs = tokenizer(text, return_tensors="pt", truncation=True,
                           max_length=512, padding=True)
        proba = torch.sigmoid(model(**inputs).logits).cpu().numpy()[0]
    labels = model.config.id2label  # non-toxic, insult, obscenity, threat, dangerous
    scores = {labels[i]: float(proba[i]) for i in range(len(proba))}
    # Формула из описания модели: общая "опасность" текста
    if "non-toxic" not in scores or "dangerous" not in scores:
        raise RuntimeError("Модель вернула неизвестные названия классов")
    scores["toxicity"] = 1 - scores["non-toxic"] * (1 - scores["dangerous"])
    return scores


def _split_text(text: str, size: int = 1000) -> list:
    """Длинный текст (например, расшифровку видео) режем на куски."""
    text = text.strip()
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def check_text(text) -> dict:
    """
    ГЛАВНАЯ ФУНКЦИЯ.
    text — строка или список строк (комментарии).

    Возвращает:
    {
        "toxicity_percent": 87.5,          # максимальная токсичность, %
        "verdict": "Опасно",               # Безопасно / Подозрительно / Опасно
        "labels": {"insult": 91.2, ...},   # проценты по типам
        "danger_words": ["закладк", ...],  # все найденные стоп-слова
        "danger_categories": {"наркотики": [...], ...},
        "worst_fragment": "текст самого токсичного куска",
    }
    """
    if isinstance(text, (list, tuple)):
        pieces = [
            fragment
            for item in text if str(item).strip()
            for fragment in _split_text(str(item))
        ]
        full_text = "\n".join(pieces)
    else:
        full_text = str(text or "")
        pieces = _split_text(full_text)

    if not full_text.strip():
        return {
            "score": None, "is_danger": False, "status": "skipped",
            "toxicity_percent": None, "verdict": "Нет текста", "labels": {},
            "danger_words": [], "danger_categories": {}, "worst_fragment": "",
            "reasons": ["Нет текста для анализа"], "error": None,
        }

    # 1) Модель: берём самый токсичный кусок/комментарий
    worst_scores, worst_piece = None, ""
    model_error = None
    try:
        for piece in pieces:
            s = _model_scores(piece)
            if worst_scores is None or s["toxicity"] > worst_scores["toxicity"]:
                worst_scores, worst_piece = s, piece
    except Exception as exc:
        # Не выдаём словарь правил за работающую нейросеть.
        model_error = f"Модель NLP не запустилась: {exc}"

    # 2) Стоп-слова по всему тексту
    categories = find_danger_words(full_text)
    all_words = sorted({w for ws in categories.values() for w in ws})

    toxicity = round(worst_scores["toxicity"] * 100, 1) if worst_scores else None

    # 3) Итоговый вердикт
    illegal = any(c in categories for c in
                  ("наркотики", "оружие", "казино_и_ставки", "мошенничество"))
    # Ручные баллы — индекс риска, а не статистическая вероятность.
    keyword_risk = (
        75 if illegal else
        70 if "угрозы_и_буллинг" in categories else
        45 if "мат" in categories else 0
    )
    score = round(max(toxicity or 0, keyword_risk), 1)
    if score >= 70:
        verdict = "Опасно"
    elif score >= 40:
        verdict = "Подозрительно"
    else:
        verdict = "Безопасно"

    reasons = []
    if toxicity is not None:
        reasons.append(f"Оценка токсичности NLP: {toxicity}%")
    for category, hits in categories.items():
        reasons.append(f"{category.replace('_', ' ')}: {', '.join(hits)}")
    if not reasons:
        reasons.append("Опасные признаки не найдены")
    if model_error:
        reasons.append("Анализ по модели недоступен; использованы только правила")
        if score < 40:
            verdict = "Недостаточно данных для вывода"
        else:
            verdict += " (неполная проверка)"

    return {
        "score": score,
        "is_danger": score >= 70,
        "status": "partial" if model_error else "ok",
        "reasons": reasons,
        "error": model_error,
        "toxicity_percent": toxicity,
        "verdict": verdict,
        "labels": {k: round(v * 100, 1) for k, v in (worst_scores or {}).items()
                   if k not in ("toxicity",)},
        "danger_words": all_words,
        "danger_categories": categories,
        "worst_fragment": worst_piece[:300],
    }


# ---------- Быстрая проверка: python text_check.py ----------
if __name__ == "__main__":
    examples = [
        "Отличное видео, спасибо автору!",
        "Ты тупой урод, я тебя найду",
        "Пиши в лс, закладки меф по городу, быстро и надёжно",
        ["Крутой ролик", "Заходи в казино по промокоду, фриспины за регистрацию"],
    ]
    for ex in examples:
        print(ex)
        print(check_text(ex))
        print("-" * 60)
