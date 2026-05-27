import re


ALLOWED_ENTITY_TYPES = {
    "Person", "Project", "Skill", "Organization", "Publication",
    "Role", "Achievement", "Event", "Institution",
}

ENTITY_TYPE_ALIASES = {
    "Technology": "Skill",
}

INVALID_PERSON_EXACT = {
    "i",
    "me",
    "my",
    "mine",
    "author",
    "user",
    "individual",
    "unknown",
    "unknown person",
    "저",
    "나",
    "저는",
    "제가",
    "저자",
    "사용자",
    "개인",
    "미상",
}

INVALID_PERSON_TERMS = {
    "author",
    "user",
    "individual",
    "student",
    "panelist",
    "department",
    "unknown",
    "llm",
    "development",
    "researcher",
    "role",
    "responsibility",
    "저자",
    "사용자",
    "학부",
    "학과",
    "학생",
    "연구자",
    "개발",
}

INVALID_EXACT_BY_TYPE = {
    "Person": {
        "교수님",
        "교수",
        "선생님",
        "멘토",
    },
    "Role": {
        "4학년",
        "교수님",
        "교수",
        "발표자",
        "사회자",
        "패널",
        "참석자",
        "참여자",
        "학부 4학년",
        "학부생",
        "석사 과정",
        "석사",
        "대학원",
        "대학원생",
        "연구자",
        "리더",
        "llm팀 근무",
        "presenter",
        "moderator",
        "panelist",
        "participant",
        "student",
        "researcher",
        "leader",
    },
    "Project": {
        "gemini",
        "gpt",
        "chatgpt",
        "팀 프로젝트",
        "dual project",
    },
    "Organization": {
        "기업",
        "정책결정자",
        "지역 주민",
        "연구소",
    },
    "Institution": {
        "jeju",
        "대학원",
        "석사과정",
        "연구소",
        "undergraduate studies",
    },
    "Event": {
        "presenter",
        "panelists",
        "대학원",
        "석사 과정",
        "a hackathon",
    },
    "Skill": {
        "30% performance improvement",
        "긍정적인 에너지 전달",
        "사회자 언급 분석",
        "패널 정보 분석",
        "분석",
        "시스템 개발",
        "우선순위 설정",
    },
}

INVALID_SUBSTRINGS_BY_TYPE = {
    "Achievement": {
        "약 1년",
        "점점 나아지고",
        "희망 의사 전달",
    },
    "Role": {
        "학년",
        "학부 ",
        "b.s. in ",
        "bachelor",
        " 근무",
    },
    "Skill": {
        "performance improvement",
        "에너지 전달",
        "사회자",
        "패널 정보",
    },
}


def is_valid_entity(entity_type: str, name: str) -> bool:
    entity_type = normalize_entity_type(entity_type)
    cleaned = re.sub(r"\s+", " ", name).strip()
    if not entity_type or not cleaned:
        return False
    if entity_type not in ALLOWED_ENTITY_TYPES:
        return False
    if entity_type != "Person":
        return is_valid_non_person_entity(entity_type, cleaned)
    return is_valid_person_name(cleaned)


def normalize_entity_type(entity_type: str | None) -> str:
    cleaned = (entity_type or "").strip()
    return ENTITY_TYPE_ALIASES.get(cleaned, cleaned)


def is_valid_non_person_entity(entity_type: str, name: str) -> bool:
    lowered = name.lower().strip(" .,:;()[]{}")
    exact = INVALID_EXACT_BY_TYPE.get(entity_type, set())
    if lowered in exact or name.strip() in exact:
        return False

    if any(term in lowered for term in INVALID_SUBSTRINGS_BY_TYPE.get(entity_type, set())):
        return False

    # Long prose-like fragments make poor graph nodes. Keep concrete achievements
    # and project titles, but reject sentence-shaped labels.
    if entity_type in {"Project", "Role", "Skill", "Organization", "Institution", "Event"}:
        if len(name) > 80:
            return False
    if entity_type == "Achievement":
        if len(name) > 120:
            return False

    return True


def is_valid_person_name(name: str) -> bool:
    lowered = name.lower().strip(" .,:;()[]{}")
    if len(lowered) <= 1 or lowered in INVALID_PERSON_EXACT:
        return False
    if lowered in INVALID_EXACT_BY_TYPE["Person"] or name.strip() in INVALID_EXACT_BY_TYPE["Person"]:
        return False
    if "/" in name or "\\" in name:
        return False

    if any(term in lowered for term in INVALID_PERSON_TERMS):
        return False

    alpha_tokens = re.findall(r"[A-Za-z]+", name)
    capitalized_tokens = [t for t in alpha_tokens if t[:1].isupper()]
    if len(capitalized_tokens) >= 2:
        return True

    korean_tokens = re.findall(r"[가-힣]{2,4}", name)
    if korean_tokens and len(name.strip()) <= 12:
        return True

    if "," in name and len(alpha_tokens) >= 2:
        return True

    return False
