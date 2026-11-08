#5 Start
import re
import logging
from typing import Any, Dict

logger = logging.getLogger("antifraud_module")

def check_links(text: Any) -> Dict[str, Any]:
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
        
    urls = re.findall(r'(https?://[^\s]+)', text)
    
    scam_markers = {
        'bit.ly', 'tinyurl.com', 'cutt.ly', 't.co', 'clck.ru', '.xyz', '.top', 
        '.click', '.cam', 'free', 'prize', 'steam', 'crypto', 'wallet', 'bonus'
    }
    
    phishing_flags = []
    for url in urls:
        url_lower = url.lower()
        if any(marker in url_lower for marker in scam_markers):
            phishing_flags.append(url)

    return {
        "urls": urls,
        "is_phishing": bool(phishing_flags),
        "details": phishing_flags
    }

def check_account_bot(profile: Any) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        logger.warning(f"Ожидался словарь profile_data, получено: {type(profile)}. Используем пустой.")
        profile = {}

    score = 0
    reasons = []
    
    has_avatar = profile.get("has_avatar")
    if has_avatar not in (True, "True", "true", 1): 
        score += 20
        reasons.append("Нет аватарки (+20)")
        
    username = str(profile.get("username", ""))
    digit_count = sum(c.isdigit() for c in username)
    if digit_count > 4: 
        score += 15
        reasons.append(f"Много цифр в имени ({digit_count}) (+15)")
        
    age_raw = profile.get("account_age_days", 999)
    try:
        age = int(age_raw)
    except (ValueError, TypeError):
        logger.warning(f"Некорректный возраст аккаунта: {age_raw}. Считаем как новый.")
        age = 0 
        
    if age < 7: 
        score += 40
        reasons.append(f"Новый/неизвестный аккаунт (возраст: {age} дн.) (+40)")
        
    bio = str(profile.get("bio", ""))
    if re.search(r'(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', bio): 
        score += 25
        reasons.append("Ссылка в био (+25)")

    is_suspicious = score > 60

    return {
        "bot_score_percent": min(score, 100),
        "is_suspicious": is_suspicious,
        "reasons": reasons
    }

def run_antifraud(text: Any, profile_data: Any) -> Dict[str, Any]:
    try:
        links = check_links(text)
        account = check_account_bot(profile_data)
        
        return {
            "module_name": "Антифрод и Фишинг",
            "overall_danger": links["is_phishing"] or account["is_suspicious"],
            "links_report": links,
            "account_report": account,
            "error": None
        }
    except Exception as e:
        logger.error(f"Критический сбой в antifraud: {str(e)}")
        
        return {
            "module_name": "Антифрод и Фишинг",
            "overall_danger": False,
            "links_report": {"urls": [], "is_phishing": False, "details": []},
            "account_report": {"bot_score_percent": 0, "is_suspicious": False, "reasons": []},
            "error": f"Сбой модуля антифрода: {str(e)}"
        }
#5 End