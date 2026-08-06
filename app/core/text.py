import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9_]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    without_punctuation = _NON_WORD.sub(" ", without_marks.replace("-", " "))
    return _WHITESPACE.sub(" ", without_punctuation).strip()
