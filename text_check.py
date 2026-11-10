"""
Участник 2 — Аналитик текста: буллинг и нелегал (text_check.py)

Главная функция: check_text(text) -> dict
Принимает строку ИЛИ список строк (например, комментарии).
Возвращает процент токсичности и список найденных опасных слов.

Установка:  pip install transformers torch
"""

import re
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_NAME = "cointegrated/rubert-tiny-toxicity"

# Модель грузится один раз (при первом вызове), чтобы не тормозить импорт
_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


# ---------- Словарь стоп-слов (корни, ищем по началу слова) ----------
# Дополняйте списки своими словами — это самая простая часть для улучшения.
STOP_WORDS = {
    "наркотики": [
        "закладк", "кладмен", "клад ", "меф", "мефедрон", "соль", "соли",
        "гашиш", "гаш", "шишк", "бошк", "спайс", "амфетамин", "амф",
        "кокаин", "кокс", "героин", "экстази", "мдма", "лсд", "марки",
        "трава", "травк", "дурь", "план ", "насвай", "альфа-pvp", "a-pvp",
    ],
    "оружие": [
        "ствол", "пистолет", "травмат", "обрез", "автомат", "калаш",
        "патрон", "глок", "glock", "взрывчатк", "граната", "оружи",
    ],
    "казино_и_ставки": [
        "казино", "casino", "1xbet", "1хбет", "мелбет", "пинап", "pin-up",
        "pinup", "вулкан", "слоты", "слот", "ставки", "букмекер",
        "промокод на депозит", "фриспин", "бонус за регистрацию", "занос",
    ],
    "мошенничество": [
        "быстрый заработок", "заработок без вложений", "пассивный доход",
        "переведи на карту", "скинь код", "код из смс", "дроп", "обнал",
        "работа курьером", "закупка", "инвестиции под",
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
    tokenizer, model = _load_model()
    with torch.no_grad():
        inputs = tokenizer(text, return_tensors="pt", truncation=True,
                           max_length=512, padding=True)
        proba = torch.sigmoid(model(**inputs).logits).cpu().numpy()[0]
    labels = model.config.id2label  # non-toxic, insult, obscenity, threat, dangerous
    scores = {labels[i]: float(proba[i]) for i in range(len(proba))}
    # Формула из описания модели: общая "опасность" текста
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
        pieces = [str(t) for t in text if str(t).strip()]
        full_text = "\n".join(pieces)
    else:
        full_text = str(text or "")
        pieces = _split_text(full_text)

    if not full_text.strip():
        return {"toxicity_percent": 0.0, "verdict": "Безопасно", "labels": {},
                "danger_words": [], "danger_categories": {}, "worst_fragment": ""}

    # 1) Модель: берём самый токсичный кусок/комментарий
    worst_scores, worst_piece = None, ""
    for piece in pieces:
        s = _model_scores(piece)
        if worst_scores is None or s["toxicity"] > worst_scores["toxicity"]:
            worst_scores, worst_piece = s, piece

    # 2) Стоп-слова по всему тексту
    categories = find_danger_words(full_text)
    all_words = sorted({w for ws in categories.values() for w in ws})

    toxicity = round(worst_scores["toxicity"] * 100, 1)

    # 3) Итоговый вердикт
    illegal = any(c in categories for c in
                  ("наркотики", "оружие", "казино_и_ставки", "мошенничество"))
    if toxicity >= 70 or illegal or "угрозы_и_буллинг" in categories:
        verdict = "Опасно"
    elif toxicity >= 40 or categories:
        verdict = "Подозрительно"
    else:
        verdict = "Безопасно"

    return {
        "toxicity_percent": toxicity,
        "verdict": verdict,
        "labels": {k: round(v * 100, 1) for k, v in worst_scores.items()
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
