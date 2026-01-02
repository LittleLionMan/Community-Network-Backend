CONDITION_TRANSLATIONS = {
    "new": "Neu",
    "like_new": "Wie neu",
    "very_good": "Sehr gut",
    "good": "Gut",
    "acceptable": "Akzeptabel",
}


def translate_condition(condition: str | None) -> str | None:
    if not condition:
        return None
    return CONDITION_TRANSLATIONS.get(condition, condition)
