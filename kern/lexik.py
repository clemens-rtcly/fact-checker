"""
Lexikalische Bausteine: Zeichen-n-Gramme, TF-IDF, Inhaltswörter.

Stufenübergreifend, weil dieselben Bausteine an drei Stellen tragen:
Stufe 1 baut daraus die Abdeckungs- und Ähnlichkeitsmatrix, Stufe 1.5
misst Restbeiträge damit, und die Evidenz-Spannen (stufe1/spannen.py)
prüfen einzelne Tokens gegen die Claim-Gramme.

Konstruktion von TF-IDF-Objekten läuft ausschließlich über
`erzeuge_tfidf` — dort greift der Varianten-Hook `tfidf_klasse`
(konfig.VARIANTE), der das frühere Monkeypatching von `pipeline.TfIdf`
ersetzt.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import konfig
from stufe0.zahlen import normalize_numbers

# ---------------------------------------------------------------- n-Gramme

_WS = re.compile(r"\s+")


def _prep(text: str) -> str:
    t = normalize_numbers(text).lower()
    t = re.sub(r"[^\wäöüß ]", " ", t)
    return " " + _WS.sub(" ", t).strip() + " "


def _ngrams(text: str, ns=(3, 4)) -> Counter:
    c: Counter = Counter()
    for n in ns:
        for i in range(len(text) - n + 1):
            c[text[i:i + n]] += 1
    return c


class TfIdf:
    def __init__(self, docs: list[str]):
        self.tfs = [_ngrams(_prep(d)) for d in docs]
        df: Counter = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n_docs = max(len(docs), 1)
        self.idf = {g: math.log((1 + n_docs) / (1 + d)) + 1 for g, d in df.items()}

    def vec(self, text: str) -> dict[str, float]:
        tf = _ngrams(_prep(text))
        v = {g: (1 + math.log(c)) * self.idf.get(g, self.idf_default())
             for g, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norm for g, x in v.items()}

    def idf_default(self) -> float:
        return max(self.idf.values()) if self.idf else 1.0


def erzeuge_tfidf(docs: list[str]) -> TfIdf:
    """Fabrik statt direkter Konstruktion — hier greift der Hook.

    `konfig.VARIANTE["tfidf_klasse"]` wird zur Laufzeit gelesen, damit
    eine Variante die Gewichtung für die Dauer eines Laufs ersetzen kann
    (etwa `tfidf_mit_boden` in varianten.py). Standard: die Klasse oben.
    """
    kls = konfig.VARIANTE.get("tfidf_klasse") or TfIdf
    return kls(docs)


def _cos_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if len(b) < len(a):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


def _cos_dense(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


# ------------------------------------------------------------ Inhaltswörter

# Quantifizierende und abtönende Adverbien. Geschlossene Klasse, praktisch
# ohne Informationsgehalt — sie tauchen in beliebigen Sätzen auf und
# stiften deshalb Scheinbelege. „Insgesamt" allein trug in einem Fall
# 13,1 % Restbeitrag und löste damit eine falsche Verdichtung aus.
_HEDGE_WORDS = set("""insgesamt rund etwa circa cirka ungefähr knapp jeweils
bereits zunächst derzeit aktuell überdies ebenfalls zudem außerdem ferner
vorerst weiterhin erneut wiederum allerdings womöglich offenbar angeblich
möglicherweise voraussichtlich schließlich nunmehr immerhin durchaus
ohnehin lediglich nämlich vielmehr indes hingegen zumal obendrein
sogar selbst nochmals abermals demnach mithin folglich""".split())

_FUNC_WORDS = set("""der die das den dem des ein eine einen einem einer eines
und oder in an auf zu von mit für bei nach vor aus seit über unter um durch
gegen ist sind war waren sein wird werden wurde wurden hat haben habe hatte
hätte sich als auch noch nur schon dann dass wenn dort hier man es er sie ihr
ihm ihn mehr sehr viel etwa rund dabei damit diese dieser dieses jenes solche
soll sollen sollte kann können könnte muss müssen sei seien wäre werde
im am beim zum zur vom ins dessen deren welche welcher welches
so wie daher also zwar eben gar ja doch denn""".split()) | _HEDGE_WORDS


def _content_tokens(text: str) -> list[tuple[str, int]]:
    """Inhaltstragende Tokens mit Position. Zahlen bleiben immer erhalten —
    sie sind kurz, aber die härtesten Anker."""
    out = []
    for i, m in enumerate(re.finditer(r"[\wäöüß]+", normalize_numbers(text))):
        w = m.group(0).lower()
        if w.isdigit() or (w not in _FUNC_WORDS and len(w) > 2):
            out.append((w, i))
    return out


def _content_grams(toks: list[tuple[str, int]]) -> set[str]:
    return set(_ngrams(_prep(" ".join(w for w, _ in toks)))) if toks else set()


def _covered_weight(claim_vec: dict[str, float], grams: set[str],
                    exclude: set[str] = frozenset()) -> float:
    """Anteil des Claim-Gewichts, den `grams` abdeckt (ohne `exclude`)."""
    total = sum(claim_vec.values()) or 1.0
    return sum(w for g, w in claim_vec.items()
               if g not in exclude and g in grams) / total


def _pmean(values: list[float], p: float) -> float:
    """Potenzmittel: p=1 Mittelwert, p→∞ Maximum.

    Bei p≈3 bleiben zwei mittelmäßige Signale mittelmäßig, ein einzelnes
    starkes Signal zieht aber spürbar hoch. Der Mittelwert würde ein
    starkes Signal herunterziehen, ein logisches Oder zwei mittelmäßige
    fälschlich in den sicheren Bereich heben.
    """
    vals = [max(0.0, min(1.0, v)) for v in values if v is not None]
    if not vals:
        return 0.0
    return (sum(v ** p for v in vals) / len(vals)) ** (1.0 / p)
