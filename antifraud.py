"""Проверка ссылок и профиля по объяснимым правилам (не обученная ML-модель)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\[\]()]+", re.I)
SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "t.co", "clck.ru"}
UNUSUAL_TLDS = {".xyz", ".top", ".click", ".cam"}
LURE_WORDS = {"free", "prize", "bonus", "gift", "reward", "airdrop", "verify-account"}


def check_links(text: Any) -> dict:
    """Даёт индекс подозрительности URL. Не утверждает, что ссылка точно фишинговая."""
    content = text if isinstance(text, str) else str(text or "")
    urls = []
    flagged = []
    reasons = []
    max_risk = 0

    for match in URL_RE.finditer(content):
        url = match.group(0).rstrip(".,!?:;")
        normalized = url if url.lower().startswith(("http://", "https://")) else "https://" + url
        parsed = urlsplit(normalized)
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            continue
        urls.append(url)
        signals = []
        score = 0
        if any(host.endswith(tld) for tld in UNUSUAL_TLDS):
            score += 40
            signals.append("Необычная доменная зона")
        if host in SHORTENERS:
            score += 25
            signals.append("Сокращённая ссылка скрывает настоящий адрес")
        # Проверяем слова именно в адресе, не в произвольном тексте сообщения.
        tokens = set(re.split(r"[^a-z0-9]+", (host + parsed.path).lower()))
        if tokens & LURE_WORDS:
            score += 30
            signals.append("Обещания подарков/бонусов в адресе")
        if parsed.scheme == "http":
            score += 10
            signals.append("Соединение без HTTPS")
        if "xn--" in host:
            score += 20
            signals.append("Домен с кодированными символами")
        score = min(score, 100)
        max_risk = max(max_risk, score)
        if score:
            reasons.extend(f"{url}: {signal}" for signal in signals)
        if score >= 40:
            flagged.append(url)

    return {
        "urls": urls,
        "score": max_risk,
        "is_phishing": max_risk >= 70,
        "is_suspicious": max_risk >= 40,
        "details": flagged,
        "reasons": reasons,
    }


def check_account_bot(profile: Any) -> dict:
    """Не штрафуем пользователя за данные, которых у нас нет."""
    profile = profile if isinstance(profile, dict) else {}
    score = 0
    reasons = []
    unknown_fields = []

    avatar = profile.get("has_avatar")
    if avatar is None:
        unknown_fields.append("аватар")
    elif avatar is False or str(avatar).strip().lower() in {"false", "0", "no"}:
        score += 15
        reasons.append("Нет аватара (+15)")

    username = str(profile.get("username") or "")
    if sum(ch.isdigit() for ch in username) >= 5:
        score += 15
        reasons.append("Много цифр в имени аккаунта (+15)")

    raw_age = profile.get("account_age_days")
    if raw_age is None or raw_age == "":
        unknown_fields.append("возраст аккаунта")
    else:
        try:
            age = int(raw_age)
            if age < 0:
                raise ValueError("отрицательный возраст")
            if age < 7:
                score += 40
                reasons.append("Аккаунт создан менее 7 дней назад (+40)")
        except (ValueError, TypeError):
            unknown_fields.append("возраст аккаунта")

    bio = str(profile.get("bio") or "")
    if URL_RE.search(bio):
        score += 20
        reasons.append("Ссылка в описании аккаунта (+20)")

    return {
        "bot_score_percent": min(score, 100),
        "is_suspicious": score >= 70,
        "reasons": reasons,
        "unknown_fields": unknown_fields,
    }


def run_antifraud(text: Any, profile_data: Any) -> dict:
    links = check_links(text)
    account = check_account_bot(profile_data)
    score = max(links["score"], account["bot_score_percent"])
    status = "partial" if account["unknown_fields"] else "ok"
    reasons = links["reasons"] + account["reasons"]
    if account["unknown_fields"]:
        reasons.append("Нет данных: " + ", ".join(account["unknown_fields"]))
    return {
        "module_name": "Антифрод и фишинг",
        "score": score,
        "is_danger": score >= 70,
        "status": status,
        "reasons": reasons,
        "links_report": links,
        "account_report": account,
        "error": None,
    }


if __name__ == "__main__":
    print(run_antifraud("Приз: http://free-prize.xyz", {"has_avatar": False, "account_age_days": 2}))
