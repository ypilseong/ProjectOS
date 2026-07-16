from app.services.citation_validator import validate_citations


def test_allows_only_provided_labels():
    result = validate_citations(
        "ProjectOS는 로컬 지식 그래프를 사용합니다 [readme.md]. "
        "검색 chunk도 인용할 수 있습니다 [cv.pdf#id1 p.1 char:0].",
        ["[readme.md]", "[cv.pdf#id1 p.1 char:0]"],
    )

    assert result["valid"] is True
    assert result["used_labels"] == ["[readme.md]", "[cv.pdf#id1 p.1 char:0]"]
    assert result["unknown_labels"] == []
    assert result["missing_citation_sentences"] == []
    assert result["unsupported_count"] == 0


def test_reports_unknown_labels():
    result = validate_citations(
        "ProjectOS는 citation을 검사합니다 [unknown.pdf].",
        ["[readme.md]"],
    )

    assert result["valid"] is False
    assert result["used_labels"] == []
    assert result["unknown_labels"] == ["[unknown.pdf]"]
    assert result["missing_citation_sentences"] == []


def test_reports_missing_citation_sentences():
    result = validate_citations(
        "# 답변\n\n"
        "ProjectOS는 그래프 기반 컨텍스트를 사용합니다.\n"
        "무슨 의미인가요?\n"
        "-\n"
        "- 이 문장은 인용이 있습니다 [readme.md].",
        ["[readme.md]"],
    )

    assert result["valid"] is False
    assert result["missing_citation_sentences"] == [
        "ProjectOS는 그래프 기반 컨텍스트를 사용합니다."
    ]


def test_unsupported_marker_is_allowed_without_known_label():
    result = validate_citations(
        "이 내용은 제공된 컨텍스트에서 확인되지 않습니다 [출처 불명]. "
        "추가 세부 사항은 출처 불명입니다.",
        ["[readme.md]"],
    )

    assert result["valid"] is True
    assert result["used_labels"] == []
    assert result["unknown_labels"] == []
    assert result["missing_citation_sentences"] == []
    assert result["unsupported_count"] == 2


def test_validation_is_deterministic():
    answer = (
        "첫 문장은 허용 라벨을 씁니다 [readme.md]. "
        "둘째 문장은 알 수 없는 라벨을 씁니다 [missing.md]."
    )
    allowed = ["[readme.md]"]

    assert validate_citations(answer, allowed) == validate_citations(answer, allowed)


def test_empty_answer_is_valid_and_has_empty_fields():
    result = validate_citations("", ["[readme.md]"])

    assert result["valid"] is True
    assert result["used_labels"] == []
    assert result["unknown_labels"] == []
    assert result["missing_citation_sentences"] == []
    assert result["unsupported_count"] == 0


def test_require_citation_can_be_disabled():
    result = validate_citations(
        "인용 없는 문장입니다.",
        ["[readme.md]"],
        require_citation=False,
    )

    assert result["valid"] is True
    assert result["missing_citation_sentences"] == []
