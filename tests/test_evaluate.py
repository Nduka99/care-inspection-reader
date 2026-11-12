from inspection_reader.evaluate import score
from inspection_reader.metrics import wilson


def test_wilson_matches_published_values() -> None:
    low, high = wilson(9, 10)
    assert (round(low, 3), round(high, 3)) == (0.596, 0.982)


def test_scores_count_sections_against_hand_worked_answers() -> None:
    reports = [
        {
            "location": "a",
            "sections": [
                {"statement": "Safeguarding", "score": 1},
                {"statement": "Medicines optimisation", "score": 2},
                {"statement": "Learning culture", "score": 3},
            ],
        },
        {"location": "b", "sections": [{"statement": "Safeguarding", "score": 1}]},
    ]
    runs = {
        "a": {
            "findings": [
                {"category": "Safeguarding", "section": 0},
                {"category": "Safeguarding", "section": 1},
                {"category": "Learning culture", "section": 2},
            ],
            "dropped": 1,
        },
        "b": {"findings": [], "dropped": 0, "error": "timeout"},
    }
    result = score(reports, runs)
    assert (result["recall_score_1"]["found"], result["recall_score_1"]["total"]) == (1, 2)
    assert result["recall_score_2_or_below"]["found"] == 2
    assert result["flag_rate_score_3"]["found"] == 1
    assert result["flag_rate_score_4"]["total"] == 0
    # Of the two flagged shortfalls, only the first has its own statement's category.
    assert (result["category_agreement"]["found"], result["category_agreement"]["total"]) == (1, 2)
    assert (result["quote_drops"]["found"], result["quote_drops"]["total"]) == (1, 4)
    assert result["errors"] == ["b"]
    assert result["missed_score_1"] == [{"location": "b", "statement": "Safeguarding"}]


CARRIED = (
    "We did not look at Medicines optimisation during this assessment. The score for this "
    "quality statement is based on the previous rating for Safe."
)


def test_a_carried_over_section_is_not_assessed() -> None:
    from inspection_reader.evaluate import assessed

    assert not assessed({"paragraphs": [CARRIED]})
    assert assessed({"paragraphs": ["Staff gave medicines safely. " + CARRIED]})
    assert assessed({"paragraphs": ["We did not look at the rota but staff were kind."]})


def test_a_carried_over_section_never_counts_as_caught() -> None:
    reports = [
        {
            "location": "a",
            "sections": [
                {"statement": "Safeguarding", "score": 1, "paragraphs": [CARRIED]},
                {"statement": "Safeguarding", "score": 1, "paragraphs": ["Abuse was missed."]},
            ],
        }
    ]
    runs = {"a": {"findings": [{"category": "Safeguarding", "section": 0}], "dropped": 0}}
    result = score(reports, runs)
    assert (result["recall_score_1"]["found"], result["recall_score_1"]["total"]) == (0, 1)
    assert result["not_assessed_left_out"] == 1
