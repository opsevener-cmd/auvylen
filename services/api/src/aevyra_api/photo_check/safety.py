"""Last line of defence for model-written text (AGENTS.md, owner decision 2026-11-25).

The prompt already forbids these topics; this filter drops any line that still touches them,
so a slip is never shown. Appearance lines may praise features but never mention flaws,
procedures, medical or diet topics, weight, race, ethnicity or age. Roast lines are
stricter: they may joke only about the photo and situation, never the body or identity, and
never compare anyone to a real person. A dropped roast line simply means no joke.
"""

import re

# English: "stem*" matches the stem plus any ending; other terms match whole words only, so
# "many", "spotlight", "bold" or "agenda" are never caught by "man", "spot", "old" or "age".
_EN_APPEARANCE = [
    "flaw*",
    "defect*",
    "imperfect*",
    "ugl*",
    "unattractive",
    "homely",
    "surg*",
    "botox",
    "filler*",
    "inject*",
    "rhinoplast*",
    "cosmetic procedure*",
    "medic*",
    "doctor*",
    "dermatolog*",
    "prescri*",
    "treatment*",
    "clinic*",
    "diet*",
    "calori*",
    "weight*",
    "overweight",
    "underweight",
    "fat",
    "fatter",
    "chubby",
    "skinny",
    "obes*",
    "body size",
    "race",
    "races",
    "racial*",
    "ethnic*",
    "skin colou?r",
    "skin tone*",
    "age",
    "aged",
    "ageing",
    "aging",
    "old",
    "older",
    "young",
    "younger",
    "youthful",
    "years? old",
    "teen*",
]
_ZH_APPEARANCE = [
    "瑕疵",
    "缺陷",
    "缺点",
    "丑",
    "难看",
    "整容",
    "整形",
    "手术",
    "医美",
    "玻尿酸",
    "填充",
    "肉毒",
    "打针",
    "注射",
    "医生",
    "医院",
    "药",
    "治疗",
    "皮肤科",
    "节食",
    "减肥",
    "体重",
    "卡路里",
    "胖",
    "瘦",
    "种族",
    "民族",
    "人种",
    "肤色",
    "年龄",
    "岁",
    "显老",
    "苍老",
    "老了",
    "显年轻",
    "年轻",
]
# Roast lines: everything above, plus the body, health, identity and look-alikes.
_EN_ROAST = _EN_APPEARANCE + [
    "skin*",
    "acne",
    "pimple*",
    "spots?",
    "blemish*",
    "wrinkl*",
    "scar*",
    "pore*",
    "nose*",
    "chin*",
    "jaw*",
    "teeth",
    "tooth*",
    "forehead*",
    "ears?",
    "eyebrow*",
    "face shape*",
    "facial*",
    "hairline*",
    "bald*",
    "receding",
    "height*",
    "short",
    "shorter",
    "tall",
    "taller",
    "body",
    "bodies",
    "belly",
    "gut",
    "gender*",
    "man",
    "men",
    "woman",
    "women",
    "boy*",
    "girl*",
    "male*",
    "female*",
    "disab*",
    "ill",
    "sick*",
    "health*",
    "disease*",
    "looks? like",
    "look-?alike*",
    "twin*",
    "doppelg*",
    "celebrit*",
    "famous",
    "actor*",
    "actress*",
    "singer*",
    "idol*",
]
_ZH_ROAST = _ZH_APPEARANCE + [
    "皮肤",
    "痘",
    "斑",
    "皱纹",
    "疤",
    "毛孔",
    "鼻",
    "下巴",
    "下颌",
    "牙",
    "额头",
    "耳朵",
    "眉毛",
    "脸型",
    "五官",
    "发际线",
    "秃",
    "身高",
    "矮",
    "高个",
    "身材",
    "肚子",
    "性别",
    "男人",
    "女人",
    "男生",
    "女生",
    "残疾",
    "病",
    "健康",
    "长得像",
    "撞脸",
    "翻版",
    "明星",
    "演员",
    "歌手",
    "爱豆",
    "名人",
]


def _english(term: str) -> str:
    if term.endswith("*"):
        return rf"\b{term[:-1]}\w*"
    return rf"\b{term}\b"


def _pattern(english: list[str], chinese: list[str]) -> re.Pattern[str]:
    words = "|".join(map(_english, english))
    return re.compile(f"(?:{words})|(?:{'|'.join(map(re.escape, chinese))})", re.IGNORECASE)


APPEARANCE_BLOCK = _pattern(_EN_APPEARANCE, _ZH_APPEARANCE)
ROAST_BLOCK = _pattern(_EN_ROAST, _ZH_ROAST)
MAX_CHARS = 140


def _clean(lines: list[str], block: re.Pattern[str], limit: int) -> list[str]:
    kept = []
    for line in lines:
        text = " ".join(line.split())
        if not text or len(text) > MAX_CHARS or block.search(text):
            continue  # Dropped, never shown or logged.
        kept.append(text)
    return kept[:limit]


def appearance_lines(lines: list[str], limit: int = 3) -> list[str]:
    return _clean(lines, APPEARANCE_BLOCK, limit)


def roast_lines(lines: list[str], limit: int = 2) -> list[str]:
    return _clean(lines, ROAST_BLOCK, limit)
