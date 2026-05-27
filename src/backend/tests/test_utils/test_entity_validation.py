from app.utils.entity_validation import is_valid_entity, normalize_entity_type


def test_technology_aliases_to_skill():
    assert normalize_entity_type("Technology") == "Skill"
    assert normalize_entity_type(None) == ""
    assert is_valid_entity("Technology", "LLM")


def test_rejects_generic_person_and_role_labels():
    assert not is_valid_entity("Person", "교수님")
    assert not is_valid_entity("Role", "사회자")
    assert not is_valid_entity("Role", "패널")
    assert not is_valid_entity("Role", "B.S. in Artificial Intelligence")


def test_rejects_common_noise_entities():
    assert not is_valid_entity("Achievement", "약 1년간 근무")
    assert not is_valid_entity("Project", "GPT")
    assert not is_valid_entity("Organization", "기업")
    assert not is_valid_entity("Role", "4학년")
    assert not is_valid_entity("Role", "LLM팀 근무")
    assert not is_valid_entity("Role", "연구자")
    assert not is_valid_entity("Skill", "긍정적인 에너지 전달")
    assert not is_valid_entity("Skill", "사회자 언급 분석")
    assert not is_valid_entity("Event", "panelists")
    assert not is_valid_entity("Institution", "Jeju")


def test_keeps_valid_entities():
    assert is_valid_entity("Skill", "Python")
    assert is_valid_entity("Project", "LLM-based Lecture Video Chatbot")
    assert is_valid_entity("Role", "Research Engineer")
    assert is_valid_entity("Achievement", "2021 Smart Tourism Big Data Hackathon Encouragement Award")
