import re


ALLOWED_ENTITY_TYPES = {
    "Person", "Project", "Skill", "Organization", "Publication",
    "Technology", "Role", "Achievement", "Event", "Institution",
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


def is_valid_entity(entity_type: str, name: str) -> bool:
    cleaned = re.sub(r"\s+", " ", name).strip()
    if not entity_type or not cleaned:
        return False
    if entity_type not in ALLOWED_ENTITY_TYPES:
        return False
    if entity_type != "Person":
        return True
    return is_valid_person_name(cleaned)


def is_valid_person_name(name: str) -> bool:
    lowered = name.lower().strip(" .,:;()[]{}")
    if len(lowered) <= 1 or lowered in INVALID_PERSON_EXACT:
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
