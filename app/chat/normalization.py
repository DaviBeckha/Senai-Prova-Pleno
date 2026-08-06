import re

from app.core.text import normalize_text
# Negacao ANTEPOSTA, ancorada no fim da janela: so vale se o marcador estiver
# colado ao termo ("nao e correia"), nunca solto no inicio da frase.
_NEGATION = re.compile(r"(?:\bnao\s+e(?:\s+a|\s+o)?|\bnao|\bdescartad[ao])\s*$")
# Negacao POSPOSTA, como o operador costuma escrever: "correia descartada".
_DISMISSAL = re.compile(r"descartad[ao]|eliminad[ao]|excluid[ao]")
# Quantas palavras apos o termo ainda contam como qualificando ELE. Duas cobrem
# "correia descartada" e "correia foi descartada" sem atravessar a familia
# seguinte em "correia e polia descartada".
_DISMISSAL_WINDOW = 2


def find_phrase_spans(
    text: str,
    aliases: tuple[str, ...],
) -> tuple[tuple[int, int, str], ...]:
    candidates: list[tuple[int, int, str]] = []
    for alias in sorted({normalize_text(item) for item in aliases}, key=len, reverse=True):
        pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(alias)}(?![a-z0-9_])")
        candidates.extend((match.start(), match.end(), alias) for match in pattern.finditer(text))

    selected: list[tuple[int, int, str]] = []
    for candidate in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        start, end, _ = candidate
        if any(not (end <= current[0] or start >= current[1]) for current in selected):
            continue
        selected.append(candidate)
    return tuple(sorted(selected))


def is_negated(text: str, start: int, end: int | None = None) -> bool:
    """A familia mencionada em `start` foi descartada pelo operador?

    `end` e o fim do alias casado. Quando omitido, assume-se que o termo vai
    ate o proximo espaco — suficiente para aliases de uma palavra, que sao o
    caso do chamador de dois argumentos.
    """
    if _NEGATION.search(text[max(0, start - 28):start]):
        return True
    if end is None:
        space = text.find(" ", start)
        end = len(text) if space == -1 else space
    following = text[end:].split()[:_DISMISSAL_WINDOW]
    return any(_DISMISSAL.fullmatch(word) for word in following)
