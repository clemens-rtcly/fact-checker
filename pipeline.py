"""
Alignment-Pipeline, Stufen 0–2.

  Stufe 0    Zahl-Normalisierung & Anker (german_numbers) + Zahlkonflikt-Prüfung
  Stufe 0.5  Personen über NER (ner.py) + tokenbasierter Namensabgleich
  Stufe 1    Lexikalisches Alignment: Char-n-Gramm-TF-IDF, asymmetrische
             Claim-Abdeckung mit Wortfolgen-Bonus, Positionsprior
  Stufe 1.2  Teilaussagen: Sätze an Konnektoren zerlegen (claims.py)
  Stufe 1.5  Restabdeckung: weitere Quellen nach ihrem Zusatzbeitrag
  Stufe 2    Embeddings (SAIA oder lokal, optional) + Score-Fusion

Ausgabe: JSON exakt im Schema des Split-View-Prototyps
(article.sentences, transcript.claims mit relation/sources/confidence/
margin/entities/flags/note).

Keine externen Abhängigkeiten. Embeddings werden als Funktion injiziert.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from html import unescape

import claims
import ner
from german_numbers import Entity, extract_entities, normalize_numbers

# ------------------------------------------------------------- Konfiguration

CFG = {
    # Fusionsgewichte (werden ohne Embeddings automatisch renormalisiert)
    "w_emb": 0.40,
    "w_cov": 0.28,
    "w_lex": 0.20,
    "w_pos": 0.12,
    # Abdeckungsscore: A · B-Dämpfer + Wortfolgen-Bonus
    "cov_contig": 0.30,   # Gewicht der Ko-Lokalität im Abdeckungsscore
    "cov_b_floor": 0.75,  # stärkste Dämpfung bei sehr geringer Rückabdeckung
    "cov_b_ref": 0.30,    # ab dieser Rückabdeckung wird nicht mehr gedämpft
    # Confidence: Potenzmittel über Abdeckung und Embedding
    "conf_power": 3.0,    # 1 = Mittelwert, ∞ = Maximum
    "conf_margin_ref": 0.15,
    "dissens_delta": 0.45,  # ab hier gelten die Signale als uneinig
    # Anker-Boni (additiv, gedeckelt)
    "anchor_unique": 0.30,   # numerischer Anker, eindeutig im Artikel
    "anchor_multi": 0.12,    # numerischer Anker, 2–3 Fundstellen
    "anchor_name": 0.10,     # seltener Eigenname
    "anchor_cap": 0.38,
    # Entscheidungsschwellen auf dem fusionierten Score.
    # Kalibriert an zwei Textpaaren (25 Claims mit bekannter Quelle,
    # 3 ohne). Die Trennung lag dort zwischen 0,431 und 0,460 — das ist
    # eine sehr dünne Datenbasis, besonders auf der Negativseite.
    "t_direct": 0.60,
    "t_none": 0.44,
    # Aggregation über Restabdeckung (Stufe 1.5):
    # Ein weiterer Satz wird aufgenommen, wenn er einen Anteil des Claims
    # erklärt, den die bisherigen Fundstellen NICHT erklären.
    "residual_min": 0.13,        # Mindest-Zusatzbeitrag am Claim-Gewicht
    "residual_max_sources": 3,   # Obergrenze der Fundstellen je Claim
    "residual_min_carriers": 2,  # so viele Inhaltswörter müssen den
                                 # Zusatzbeitrag tragen (gegen Scheinbelege)
    "agg_min_claim_len": 55,     # sehr kurze Claims aggregieren nicht
    # Redundante Fundstellen
    "redundant_delta": 0.07,
    # Teilaussagen (Stufe 1.2): Transkriptsätze an Konnektoren zerlegen
    "split_claims": True,
    "split_min_lex": 0.16,   # darunter gilt ein Teil als "findet nichts";
                             # zurückgeführt wird er nur mit Rückverweis
}


# ------------------------------------------------------------- Segmentierung

_ABBREV = {
    "z.b", "bzw", "ca", "dr", "prof", "mio", "mrd", "nr", "u.a", "d.h",
    "o.ä", "o.a", "vgl", "ggf", "inkl", "evtl", "usw", "str", "abs", "art",
    "etc", "sog", "u.u", "v.a", "bspw", "geb", "st", "hr", "fr", "min",
    "max", "tel", "co", "jh", "jhd", "s", "vgl",
}

_SENT_END = re.compile(r"[.!?…]+[»«\"'\u201c\u201d\u201e)\]]*")


@dataclass
class Sent:
    id: str
    start: int
    end: int
    text: str
    paragraph: int
    block: str


def _split_sentences_in(text: str, p_start: int, p_end: int) -> list[tuple[int, int]]:
    """Satzgrenzen innerhalb eines Absatzes, als absolute Offsets."""
    out = []
    seg_start = p_start
    for m in _SENT_END.finditer(text, p_start, p_end):
        end = m.end()
        # Folgekontext prüfen: nach Satzende kommt Leerraum + Großbuchstabe/Ziffer/Anführung
        rest = text[end:p_end]
        nxt = rest.lstrip()
        if nxt and not re.match(r"[A-ZÄÖÜ0-9\u201e\u201c\"'«»(]", nxt):
            continue
        # Wort vor dem Punkt: Abkürzung oder kurze Ordnungszahl -> keine Grenze
        before = text[seg_start:m.start()]
        wm = re.search(r"([A-Za-zÄÖÜäöüß.]+|\d+)$", before)
        if wm:
            w = wm.group(1).lower().rstrip(".")
            if w in _ABBREV:
                continue
            if w.isdigit() and len(w) <= 2 and "." in m.group(0):
                continue  # "3. Platz", "2. Januar"
        out.append((seg_start, end))
        seg_start = end
        while seg_start < p_end and text[seg_start].isspace():
            seg_start += 1
    if seg_start < p_end and text[seg_start:p_end].strip():
        out.append((seg_start, p_end))
    # Whitespace an den Rändern abschneiden
    trimmed = []
    for s, e in out:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            trimmed.append((s, e))
    return trimmed


def segment(text: str, kind: str, id_prefix: str) -> list[Sent]:
    """Absätze + Sätze mit exakten Zeichen-Offsets. kind: 'article'|'transcript'."""
    sents: list[Sent] = []
    para_idx = 0
    counter = 1
    for pm in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]*)*", text):
        p_start, p_end = pm.start(), pm.end()
        for s, e in _split_sentences_in(text, p_start, p_end):
            if kind == "article":
                if para_idx == 0:
                    block = "headline"
                elif para_idx == 1:
                    block = "lead"
                else:
                    block = "body"
            else:
                block = "body"
            sents.append(Sent(f"{id_prefix}{counter}", s, e, text[s:e], para_idx, block))
            counter += 1
        para_idx += 1
    return sents


# ------------------------------------------- Stufe 1: Char-n-Gramm-TF-IDF

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


def _cos_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if len(b) < len(a):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


def _cos_dense(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


# ------------------------------------------------------------------ Pipeline

_BLOCK_TAGS = re.compile(
    r"</?(?:p|div|h[1-6]|br|li|ul|ol|tr|section|article|blockquote)\b[^>]*>",
    re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_HAS_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


_MD_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.M)


def strip_html(text: str) -> str:
    """Entfernt HTML- und Markdown-Auszeichnung, stellt Absatzgrenzen her.

    Aus Redaktionssystemen kopierte Artikel bringen oft `<p class="">`,
    `</p>` und `<h3>` mit, aus Markdown-Exporten kommen `###`-Zeilen.
    Unbehandelt landet das Markup mitten in den Sätzen: Die Überschrift
    verklebt mit dem ersten Fließtextsatz, und Zwischenüberschriften
    zählen als eigene Artikelsätze mitsamt ihren Rautezeichen.

    Blocktags werden zu Leerzeilen, damit die Absatzlogik (Überschrift =
    §0, Vorspann = §1) wieder greift. Zwischenüberschriften bleiben als
    Text erhalten — sie tragen Inhalt (etwa „19 Gelege von Bodenbrütern")
    und dürfen als Fundstelle dienen.
    """
    t = text
    if _HAS_TAG.search(t):
        t = _BLOCK_TAGS.sub("\n\n", t)
        t = _ANY_TAG.sub("", t)
        t = unescape(t)
    t = t.replace("\u00a0", " ")
    if _MD_HEADING.search(t):
        t = _MD_HEADING.sub("", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


_SPAN_FUZZ = 0.6      # Anteil gemeinsamer Zeichen-3-Gramme je Token
_SPAN_GAP = 4         # max. Abstand in Tokens innerhalb einer Region


def _evidence_spans(claim_grams: set[str], sent_text: str,
                    anchor_spans: list[tuple[int, int]]
                    ) -> list[tuple[int, int]]:
    """Regionen des Satzes, die den Claim tatsächlich stützen.

    Ersetzt die frühere Regel „Ankerregion, sonst ganzer Satz". Die war in
    beide Richtungen falsch: Eine Zahl im Satz schrumpfte die Anzeige auf
    die Ziffern zusammen, ein Satz ohne Zahl wurde vollständig markiert.

    Der Vergleich läuft über Zeichen-3-Gramme statt über Wortgleichheit,
    weil Transkripte Eigennamen phonetisch verformen („Pfass" für PFAS).
    Die Reihenfolge bleibt unberücksichtigt, denn Zusammenfassungen
    stellen um.

    Drei Token-Zustände, die streng auseinandergehalten werden:

      treffer        im Claim belegt
      abgelehnt      geprüft und nicht gefunden
      übersprungen   gar nicht geprüft (Funktionswort, sehr kurz)

    Zwei Trefferregionen werden **nur** über übersprungene Tokens
    verbunden. Ein einziges abgelehntes Wort dazwischen trennt sie — sonst
    verschmolz „Laut Feuerwehr konnte es zu einer Geruchsbelästigung" zu
    einer Region, obwohl „konnte" im Transkript gar nicht vorkommt.

    An den Rändern wächst eine Region über übersprungene Tokens hinaus,
    aber nur, wenn bis zur Satzgrenze nichts Abgelehntes mehr folgt. So
    bleibt „… nicht verfügbar waren." vollständig, während „… die
    Geschäfte, der erst zwei Jahre zuvor …" nach „Geschäfte" endet und das
    Relativpronomen nicht mehr einschließt.

    Offsets relativ zum Satzanfang, aufsteigend und überschneidungsfrei.
    """
    toks = [(m.group(0), m.start(), m.end())
            for m in re.finditer(r"[\wäöüß]+", sent_text)]
    zustand: list[str] = []
    for w, _a, _b in toks:
        wl = w.lower()
        if wl in _FUNC_WORDS or (len(wl) < 4 and not wl.isdigit()):
            zustand.append("uebersprungen")
            continue
        wg = set(_ngrams(_prep(w)))
        if not wg:
            zustand.append("uebersprungen")
            continue
        zustand.append("treffer"
                       if len(wg & claim_grams) / len(wg) >= _SPAN_FUZZ
                       else "abgelehnt")

    idx = [k for k, z in enumerate(zustand) if z == "treffer"]
    if not idx:
        return [(0, len(sent_text))]

    gruppen: list[list[int]] = [[idx[0]]]
    for k in idx[1:]:
        blockiert = any(zustand[j] == "abgelehnt"
                        for j in range(gruppen[-1][-1] + 1, k))
        if blockiert:
            gruppen.append([k])
        else:
            gruppen[-1].append(k)

    regionen: list[tuple[int, int]] = []
    for g in gruppen:
        lo_k, hi_k = g[0], g[-1]
        if all(zustand[j] == "uebersprungen" for j in range(hi_k + 1, len(zustand))):
            hi_k = len(zustand) - 1
        if all(zustand[j] == "uebersprungen" for j in range(0, lo_k)):
            lo_k = 0
        lo, hi = toks[lo_k][1], toks[hi_k][2]
        if not sent_text[hi:].strip(" .,;:!?\u201c\u201e\u201d\"')»"):
            hi = len(sent_text)
        if not sent_text[:lo].strip(" \u201e\u201c\"('«"):
            lo = 0
        regionen.append((lo, hi))

    for a, b in anchor_spans:
        if not any(lo <= a and b <= hi for lo, hi in regionen):
            regionen.append((a, b))

    regionen.sort()
    verschmolzen: list[tuple[int, int]] = []
    for lo, hi in regionen:
        if verschmolzen and lo <= verschmolzen[-1][1]:
            verschmolzen[-1] = (verschmolzen[-1][0], max(verschmolzen[-1][1], hi))
        else:
            verschmolzen.append((lo, hi))
    return verschmolzen


def _numeric(ents: list[Entity]) -> list[Entity]:
    return [e for e in ents if e.type in ("geld", "prozent", "zahl", "datum")]


def _anchorworthy(e: Entity) -> bool:
    """Taugt die Entität als Anker bzw. als Teilspanne?

    Bloße kleine Zahlen („zwei Ministerpräsidenten", „drei Punkte") kommen
    in jedem Text vor, unterscheiden also nichts und erzeugen als
    Teilspanne nur vier Zeichen lange Schnipsel. Geldbeträge, Prozentwerte,
    Jahreszahlen und Verhältnisse bleiben vollwertige Anker.
    """
    if e.type != "zahl":
        return True
    if isinstance(e.value, str):        # Verhältnis wie 28:11
        return True
    return float(e.value) >= 10


def _values_equal(a: Entity, b: Entity) -> bool:
    if isinstance(a.value, str) or isinstance(b.value, str):
        return str(a.value) == str(b.value)
    if a.type != b.type and {a.type, b.type} != {"zahl", "datum"}:
        return False
    return abs(float(a.value) - float(b.value)) < 1e-6


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

_COLOC_W = 8       # Fenstergröße in Tokens
_COLOC_MIN = 5     # ab so vielen Treffern zählt das Maß voll


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


def _colocality(claim_tok_grams: list[set[str]], claim_pos: list[int],
                sent_tok_grams: list[set[str]], sent_pos: list[int],
                schwelle: float = 0.6) -> float:
    """Liegen Wörter, die im Artikelsatz nah beieinanderstehen, auch im
    Claim nah beieinander?

    Reihenfolgefrei — es zählt nur der Abstand, nicht die Richtung. Beim
    Zusammenfassen für Audio wird die Wortstellung regelmäßig gedreht;
    ein reihenfolgetreues Maß bestraft das zu Unrecht und findet bei
    umgestellten Sätzen nur Bruchstücke.

    Gedämpft bei wenigen Treffern: Aus zwei zufällig passenden Wörtern
    lässt sich keine Struktur ablesen.
    """
    treffer: list[tuple[int, int]] = []
    for sg, sp in zip(sent_tok_grams, sent_pos):
        if not sg:
            continue
        best, bi = 0.0, -1
        for k, cg in enumerate(claim_tok_grams):
            if not cg:
                continue
            v = len(sg & cg) / len(sg)
            if v > best:
                best, bi = v, k
        if best >= schwelle:
            treffer.append((claim_pos[bi], sp))
    if len(treffer) < 2:
        return 0.0
    nah = ges = 0
    for i in range(len(treffer)):
        for j in range(i + 1, len(treffer)):
            if abs(treffer[i][0] - treffer[j][0]) <= _COLOC_W:
                ges += 1
                nah += abs(treffer[i][1] - treffer[j][1]) <= _COLOC_W
    if not ges:
        return 0.0
    return (nah / ges) * min(1.0, len(treffer) / _COLOC_MIN)


def _covered_weight(claim_vec: dict[str, float], grams: set[str],
                    exclude: set[str] = frozenset()) -> float:
    """Anteil des Claim-Gewichts, den `grams` abdeckt (ohne `exclude`)."""
    total = sum(claim_vec.values()) or 1.0
    return sum(w for g, w in claim_vec.items()
               if g not in exclude and g in grams) / total


def _coverage_score(claim_cvec, claim_cgrams, sent_cvec, sent_cgrams,
                    coloc: float) -> float:
    """Asymmetrischer Abdeckungsscore für ein Paar.

    Drei Bestandteile, die unterschiedliche Fehler abfangen:

      A  Anteil des CLAIMS, den der Satz abdeckt — das Hauptsignal, denn
         belegt zu sein heißt, dass der Satz den Claim erklärt.
      B  Anteil des SATZES, den der Claim abdeckt — nur als milder
         Dämpfer. Lange Sätze decken kurze Claims zufällig leichter ab
         (gemessene Korrelation Satzlänge/A: +0,40). Eine symmetrische
         Verrechnung wäre falsch: Bei echter Zusammenfassung ist B
         naturgemäß klein, ohne dass die Zuordnung schlechter wäre.
      K  Ko-Lokalität — stehen im Satz benachbarte Wörter auch im Claim
         benachbart? Reihenfolgefrei.

    A und B laufen nur über Inhaltswörter. Sonst sammelt sich Gewicht in
    Artikeln und Hilfsverben: Gemessen tragen Funktionswörter im Schnitt
    15 bis 18 Prozent des Claim-Gewichts, in Einzelfällen über 35. Genau
    daran scheiterte ein Fall, in dem „diese … sind" eine Verdichtung mit
    einem inhaltlich unbeteiligten Satz auslöste (13,7 % Restbeitrag; nach
    der Filterung 1,3 %).
    """
    total = sum(claim_cvec.values()) or 1.0
    a = sum(w for g, w in claim_cvec.items() if g in sent_cgrams) / total
    tot_s = sum(sent_cvec.values()) or 1.0
    b = sum(w for g, w in sent_cvec.items() if g in claim_cgrams) / tot_s

    floor, ref = CFG["cov_b_floor"], CFG["cov_b_ref"]
    damp = floor + (1.0 - floor) * min(1.0, b / ref if ref else 1.0)
    return min(1.0, a * damp + CFG["cov_contig"] * coloc)


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


def _normalize_matrix(rows: list[list[float]]) -> list[list[float]]:
    """Lineare Spreizung der Embedding-Kosinuswerte über alle Paare.

    Bewusst **global** und nicht zeilenweise: Das absolute Niveau bleibt
    erhalten, damit ein Claim ohne gute Fundstelle auch nach der
    Normalisierung niedrig liegt — Voraussetzung für `keine_quelle`.

    Oberer Anker ist das Maximum, nicht P95. Mit P95 lagen bei realen
    Dokumenten sämtliche Zeilenmaxima oberhalb der Grenze und wurden auf
    1,0 geklemmt; das Embedding unterschied am oberen Ende dann gar nichts
    mehr, und die Rangfolge entschied sich allein über Lexik und Position.
    Die untere Grenze bleibt bei P10, weil E5-Modelle auch für völlig
    unverwandte Paare noch Werte um 0,7 liefern.
    """
    flat = sorted(v for row in rows for v in row)
    if not flat:
        return rows
    lo = flat[int(0.10 * (len(flat) - 1))]
    hi = flat[-1]
    span = (hi - lo) or 1e-9
    return [[min(1.0, max(0.0, (v - lo) / span)) for v in row] for row in rows]


def _choose_claims(transcript_text: str, art_sents: list[Sent]) -> list[Sent]:
    """Claims bilden — ganze Sätze oder Teilaussagen (Stufe 1.2).

    Eine Zerlegung wird zurückgenommen, wenn ein Teil im Artikel nichts
    findet **und** einen Rückverweis auf den Nachbarteil enthält („ohne
    sie", „dabei"). Solche Fragmente sind allein nicht prüfbar und würden
    fälschlich als unbelegt erscheinen.

    Ein Teil ohne Rückverweis, der im Artikel nichts findet, bleibt
    dagegen bewusst getrennt: Das ist der Fall einer erfundenen zweiten
    Satzhälfte, und der soll als `keine_quelle` sichtbar werden statt in
    der Zuordnung des ersten Teils zu verschwinden.

    Die Prüfung läuft rein lexikalisch und kostet daher keine Embeddings —
    eingebettet wird erst der endgültige Claim-Satz.
    """
    sentences = segment(transcript_text, "transcript", "c")
    if not CFG["split_claims"] or not art_sents:
        return sentences

    cand = {s.id: claims.split_sentence(s.text, s.start) for s in sentences}
    if all(len(v) < 2 for v in cand.values()):
        return sentences

    tmp = TfIdf([s.text for s in art_sents] + [s.text for s in sentences]
                + [p[0] for v in cand.values() for p in v])
    art_vecs = [tmp.vec(s.text) for s in art_sents]
    art_gr = [set(_ngrams(_prep(s.text)).keys()) for s in art_sents]

    final: list[Sent] = []
    for s in sentences:
        parts = cand[s.id]
        if len(parts) > 1:
            orphan = any(
                max(_cos_sparse(tmp.vec(t), av) for av in art_vecs)
                < CFG["split_min_lex"] and claims.has_anaphor(t)
                for t, _a, _b in parts)
            # Eine Zerlegung lohnt nur, wenn die Teile auf verschiedene
            # Artikelsätze zeigen. Landen alle beim selben Satz, war die
            # Trennung folgenlos und erzeugt nur zusätzliche Zeilen.
            besten = []
            for t, _a, _b in parts:
                cv = tmp.vec(t)
                besten.append(max(range(len(art_sents)),
                                  key=lambda i: _covered_weight(cv, art_gr[i])))
            if orphan or len(set(besten)) < 2:
                parts = [(s.text, s.start, s.end)]
        for t, a, b in parts:
            final.append(Sent("", a, b, t, s.paragraph, s.block))

    for i, s in enumerate(final, 1):
        s.id = f"c{i}"
    return final


def align(article_text: str, transcript_text: str,
          embed_fn=None, model_label: str = "ohne Embeddings") -> dict:
    """Hauptfunktion. embed_fn(texts, is_query) -> list[list[float]] | None."""
    article_text = strip_html(article_text)
    transcript_text = strip_html(transcript_text)
    art_sents = segment(article_text, "article", "s")
    claims_raw = _choose_claims(transcript_text, art_sents)

    art_ents = [extract_entities(s.text) for s in art_sents]
    # Offsets der Satz-Entities auf Dokumentkoordinaten heben
    for s, es in zip(art_sents, art_ents):
        for e in es:
            e.start += s.start
            e.end += s.start
    claim_ents = [extract_entities(c.text) for c in claims_raw]
    for c, es in zip(claims_raw, claim_ents):
        for e in es:
            e.start += c.start
            e.end += c.start

    # Stufe 0.5: Personen getrennt von den Zahlen (ner.py, spaCy o. Rückfall)
    art_persons = [ner.persons(s.text) for s in art_sents]
    claim_persons = [ner.persons(c.text) for c in claims_raw]

    m, n = len(claims_raw), len(art_sents)
    if m == 0 or n == 0:
        return _assemble(article_text, transcript_text, art_sents, [], model_label)

    # ---------------- Stufe 1: lexikalische Matrix
    tfidf = TfIdf([s.text for s in art_sents] + [c.text for c in claims_raw])
    art_vecs = [tfidf.vec(s.text) for s in art_sents]
    claim_vecs = [tfidf.vec(c.text) for c in claims_raw]
    lex = [[_cos_sparse(cv, av) for av in art_vecs] for cv in claim_vecs]

    # Inhaltswort-Sicht für Abdeckung und Nähe. Der volle Text bleibt für
    # den Kosinus erhalten — beide Sichten fangen andere Fehler ab.
    art_grams = [set(_ngrams(_prep(s.text)).keys()) for s in art_sents]
    claim_grams = [set(_ngrams(_prep(c.text)).keys()) for c in claims_raw]

    art_ctoks = [_content_tokens(s.text) for s in art_sents]
    claim_ctoks = [_content_tokens(c.text) for c in claims_raw]
    art_cgrams = [_content_grams(t) for t in art_ctoks]
    claim_cgrams = [_content_grams(t) for t in claim_ctoks]
    art_cvecs = [{g: w for g, w in art_vecs[si].items() if g in art_cgrams[si]}
                 for si in range(n)]
    claim_cvecs = [{g: w for g, w in claim_vecs[ci].items()
                    if g in claim_cgrams[ci]} for ci in range(m)]
    art_tokgrams = [[set(_ngrams(_prep(w))) for w, _ in t] for t in art_ctoks]
    claim_tokgrams = [[set(_ngrams(_prep(w))) for w, _ in t] for t in claim_ctoks]
    art_tokpos = [[p for _, p in t] for t in art_ctoks]
    claim_tokpos = [[p for _, p in t] for t in claim_ctoks]

    cov = []
    for ci in range(m):
        zeile = []
        for si in range(n):
            # Ko-Lokalität nur rechnen, wo überhaupt Inhalt gemeinsam ist —
            # spart den teuren Tokenvergleich für die meisten Paare.
            grob = (len(claim_cgrams[ci] & art_cgrams[si])
                    / max(len(claim_cgrams[ci]), 1))
            k = 0.0
            if grob >= 0.10:
                k = _colocality(claim_tokgrams[ci], claim_tokpos[ci],
                                art_tokgrams[si], art_tokpos[si])
            zeile.append(_coverage_score(claim_cvecs[ci], claim_cgrams[ci],
                                         art_cvecs[si], art_cgrams[si], k))
        cov.append(zeile)

    # ---------------- Stufe 2: Embeddings (optional)
    emb = None
    if embed_fn is not None:
        doc_vecs = embed_fn([s.text for s in art_sents], is_query=False)
        q_vecs = embed_fn([c.text for c in claims_raw], is_query=True)
        if doc_vecs and q_vecs:
            emb = _normalize_matrix(
                [[_cos_dense(q, d) for d in doc_vecs] for q in q_vecs])

    # ---------------- Stufe 0: Anker
    anchor = [[0.0] * n for _ in range(m)]
    anchor_notes: list[list[str]] = [[] for _ in range(m)]
    for ci, ents in enumerate(claim_ents):
        for e in _numeric(ents):
            if not _anchorworthy(e):
                continue
            hits = [si for si, ses in enumerate(art_ents)
                    if any(_values_equal(e, se) for se in _numeric(ses))]
            bonus = (CFG["anchor_unique"] if len(hits) == 1
                     else CFG["anchor_multi"] if 2 <= len(hits) <= 3 else 0.0)
            for si in hits:
                anchor[ci][si] += bonus
            if len(hits) == 1:
                anchor_notes[ci].append(
                    f"Anker {e.norm} eindeutig in {art_sents[hits[0]].id}")
        for surface, _s, _e in claim_persons[ci]:
            hits = [si for si, names in enumerate(art_persons)
                    if ner.matches(surface, [nm for nm, _a, _b in names])]
            if 1 <= len(hits) <= 2:
                for si in hits:
                    anchor[ci][si] += CFG["anchor_name"]
    anchor = [[min(v, CFG["anchor_cap"]) for v in row] for row in anchor]

    # ---------------- Fusion
    if emb is not None:
        w_e, w_c = CFG["w_emb"], CFG["w_cov"]
        w_l, w_p = CFG["w_lex"], CFG["w_pos"]
    else:
        # Ohne Embeddings wird auf dieselbe Summe renormalisiert statt
        # gestaucht — sonst bedeuten t_direct und t_none im Offline- und
        # im Embedding-Modus verschiedene Dinge.
        tot = CFG["w_cov"] + CFG["w_lex"] + CFG["w_pos"]
        w_e = 0.0
        w_c = CFG["w_cov"] / tot
        w_l = CFG["w_lex"] / tot
        w_p = CFG["w_pos"] / tot

    def fused_at(ci: int, si: int) -> float:
        pos = 1.0 - abs(si / max(n - 1, 1) - ci / max(m - 1, 1))
        base = w_c * cov[ci][si] + w_l * lex[ci][si] + w_p * pos
        if emb is not None:
            base += w_e * emb[ci][si]
        base = min(base, 1.0)
        # Anker werden in den verbleibenden Spielraum skaliert statt addiert.
        # Additiv überschritten Basis + Anker regelmäßig 1,0 und wurden
        # abgeschnitten — dann lagen Platz 1 und Platz 2 gleichauf und die
        # Margin fiel fälschlich auf 0.
        return base + anchor[ci][si] * (1.0 - base)

    fused = [[fused_at(ci, si) for si in range(n)] for ci in range(m)]

    def residual_gain(ci: int, chosen: list[int], cand: int) -> float:
        """Anteil des Claims, den `cand` zusätzlich zu `chosen` erklärt.

        Dieselbe Rechnung wie das A aus `_coverage_score`, nur mit den
        bereits erklärten n-Grammen als Ausschluss.

        Zusätzlich muss der Beitrag von mindestens `residual_min_carriers`
        verschiedenen Inhaltswörtern getragen werden. Gemessen: echte
        Verdichtungen werden von zwei bis sieben Wörtern getragen — meist
        Eigennamen, Zahlen oder Sachbegriffe. Scheinbelege hängen dagegen
        an einem einzigen Wort. Einzelne Zahlen-Anker fallen dadurch nicht
        durchs Raster: für die gibt es weiter unten den eigenen Pfad über
        `anchor_extra`.
        """
        covered: set[str] = set()
        for si in chosen:
            covered |= art_cgrams[si]
        rest = {g: w for g, w in claim_cvecs[ci].items()
                if g not in covered and g in art_cgrams[cand]}
        if not rest:
            return 0.0
        total = sum(claim_cvecs[ci].values()) or 1.0
        gewinn = sum(rest.values()) / total

        traeger = 0
        for w, _p in claim_ctoks[ci]:
            wg = set(_ngrams(_prep(w)))
            if wg and sum(v for g, v in rest.items() if g in wg) / total > 0.01:
                traeger += 1
                if traeger >= CFG["residual_min_carriers"]:
                    return gewinn
        return 0.0

    # ---------------- Entscheidungen pro Claim
    claims_json = []
    for ci, c in enumerate(claims_raw):
        row = fused[ci]
        order = sorted(range(n), key=lambda si: -row[si])
        s1, si1 = row[order[0]], order[0]
        s2 = row[order[1]] if n > 1 else 0.0
        margin = round(max(s1 - s2, 0.0), 2)
        note_parts = list(anchor_notes[ci])
        flags: list[str] = []

        # ---------------- Primärzuordnung
        redundant: list[int] = []
        if s1 >= CFG["t_direct"]:
            relation = "direkt"
            srcs = [si1]
            for si in order[1:]:
                if row[si] >= max(CFG["t_direct"], s1 - CFG["redundant_delta"]):
                    redundant.append(si)
                else:
                    break
            conf = 0.0          # wird unten aus der Abdeckung gesetzt
        elif s1 >= CFG["t_none"]:
            relation = "direkt"
            srcs = [si1]
            conf = 0.0          # wird unten aus der Abdeckung gesetzt
            note_parts.append("Unter der Direkt-Schwelle — zur Prüfung empfohlen.")
        else:
            relation = "keine_quelle"
            srcs = []
            conf = round(min(0.97, 0.55 + (CFG["t_none"] - s1) * 2.2), 2)
            note_parts.append("Keine ausreichend ähnliche Stelle im Artikel.")

        # ---------------- Stufe 1.5: Restabdeckung (gierig)
        # Nicht „ähnelt Satz X dem Claim?", sondern „erklärt Satz X etwas,
        # das noch keine Fundstelle erklärt?". Ein Member einer Verdichtung
        # trägt definitionsgemäß nur einen Teil bei und wäre an einer
        # Ähnlichkeitsschwelle gegen den ganzen Claim gescheitert.
        gains: list[tuple[int, float]] = []
        if relation != "keine_quelle" and len(c.text) >= CFG["agg_min_claim_len"]:
            while len(srcs) < CFG["residual_max_sources"]:
                cands = [(si, residual_gain(ci, srcs, si)) for si in range(n)
                         if si not in srcs and si not in redundant]
                if not cands:
                    break
                best_si, best_gain = max(cands, key=lambda t: t[1])
                if best_gain < CFG["residual_min"]:
                    break
                srcs.append(best_si)
                gains.append((best_si, best_gain))

        # Komplementäre Zahlen-Anker: eindeutige Anker außerhalb der
        # bisherigen Fundstellen ergänzen, auch wenn ihr Wortbeitrag klein ist.
        anchor_extra: list[int] = []
        if relation != "keine_quelle":
            covered_vals = {str(ae.value) for si in srcs
                            for ae in _numeric(art_ents[si])}
            for e in _numeric(claim_ents[ci]):
                if not _anchorworthy(e):
                    continue
                hits = [si for si, ses in enumerate(art_ents)
                        if any(_values_equal(e, se) for se in _numeric(ses))]
                if len(hits) == 1 and hits[0] not in srcs \
                        and str(e.value) not in covered_vals:
                    anchor_extra.append(hits[0])
            for si in sorted(set(anchor_extra)):
                if si not in srcs:
                    srcs.append(si)

        if relation == "direkt" and len(srcs) > 1:
            relation = "aggregiert"
            teile = []
            if gains:
                teile.append(", ".join(
                    f"{art_sents[si].id} erklärt zusätzlich "
                    f"{g:.0%}".replace("%", " %") for si, g in gains))
            if anchor_extra:
                teile.append("Zahlen-Anker in " + ", ".join(
                    art_sents[si].id for si in sorted(set(anchor_extra))))
            note_parts.append(
                "Verdichtet aus " + " + ".join(art_sents[si].id for si in srcs)
                + (" (" + "; ".join(teile) + ")." if teile else "."))

        srcs = srcs + [si for si in redundant if si not in srcs]

        # ---------------- Confidence aus zwei unabhängigen Signalen
        # Nicht der Mittelwert (ein starkes Signal würde heruntergezogen)
        # und kein logisches Oder (zwei mittelmäßige lägen fälschlich im
        # sicheren Bereich), sondern das Potenzmittel dazwischen.
        cov_total = 0.0
        if relation != "keine_quelle":
            union: set[str] = set()
            for si in srcs:
                union |= art_cgrams[si]
            cov_total = _covered_weight(claim_cvecs[ci], union)
            emb_sig = emb[ci][si1] if emb is not None else None
            core = _pmean([cov_total, emb_sig], CFG["conf_power"])
            core *= 0.85 + 0.15 * min(1.0, margin / CFG["conf_margin_ref"])
            conf = round(min(0.98, max(0.05, core)), 2)
            note_parts.append(
                f"Fundstellen erklären {cov_total:.0%}".replace("%", " %")
                + " des Claims.")
            if emb_sig is not None and abs(cov_total - emb_sig) > CFG["dissens_delta"]:
                flags.append("signale_uneinig")
                traeger = "der Wortlaut" if cov_total > emb_sig else "die Bedeutung"
                note_parts.append(
                    f"Signale uneinig — nur {traeger} stützt die Zuordnung.")

        # ---------------- Stufe 0: Entity-Verifikation gegen die Fundstellen
        ents_json = []
        src_sent_ids = set(srcs)
        near_ids = set(src_sent_ids)
        for si in src_sent_ids:
            near_ids |= {k for k in range(n)
                         if art_sents[k].paragraph == art_sents[si].paragraph}
        all_art_numeric = [(si, e) for si, es in enumerate(art_ents)
                           for e in _numeric(es)]

        for e in _numeric(claim_ents[ci]):
            exact = [si for si, ae in all_art_numeric if _values_equal(e, ae)]
            if exact:
                ents_json.append({"type": e.type, "surface": e.surface,
                                  "norm": str(e.norm), "status": "match"})
                continue
            same_type_near = [(si, ae) for si, ae in all_art_numeric
                              if ae.type == e.type and si in near_ids]
            if not same_type_near:
                same_type_near = [(si, ae) for si, ae in all_art_numeric
                                  if ae.type == e.type]
            if same_type_near and srcs:
                def _dist(pair):
                    si, ae = pair
                    try:
                        return abs(float(ae.value) - float(e.value))
                    except (TypeError, ValueError):
                        return float("inf")
                si, ae = min(same_type_near, key=_dist)
                ents_json.append({
                    "type": e.type, "surface": e.surface, "norm": str(e.norm),
                    "status": "konflikt",
                    "quelle_surface": ae.surface, "quelle_norm": str(ae.norm),
                })
                if "zahlkonflikt" not in flags:
                    flags.append("zahlkonflikt")
                note_parts.append(
                    f"{e.norm} weicht ab — Artikel nennt {ae.norm} "
                    f"({art_sents[si].id}).")
            else:
                ents_json.append({"type": e.type, "surface": e.surface,
                                  "norm": str(e.norm), "status": "unbelegt"})
                if "zahl_unbelegt" not in flags:
                    flags.append("zahl_unbelegt")
                note_parts.append(f"{e.norm} im Artikel nicht auffindbar.")

        art_person_names = [nm for names in art_persons for nm, _a, _b in names]
        for surface, _s, _e in claim_persons[ci]:
            found = ner.matches(surface, art_person_names, article_text)
            ents_json.append({"type": "person", "surface": surface,
                              "norm": surface.lower(),
                              "status": "match" if found else "unbelegt"})
            if not found:
                note_parts.append(
                    "Name \u201e" + surface + "\u201c nicht im Artikel belegt.")

        # ---------------- Quellspannen (Teilspanne = Ankerregion, sonst Satz)
        sources_json = []
        for rank, si in enumerate(srcs):
            s = art_sents[si]
            hits = [ae for ae in _numeric(art_ents[si])
                    if _anchorworthy(ae) and any(_values_equal(ce, ae)
                           for ce in _numeric(claim_ents[ci]))]
            anchor_spans = [(h.start - s.start, h.end - s.start) for h in hits]
            inseln = _evidence_spans(claim_grams[ci], s.text, anchor_spans)
            spans = [[s.start + lo, s.start + hi] for lo, hi in inseln]
            role = "redundant" if si in redundant else "primaer"
            # start/end bleibt die Hülle — ältere Viewer lesen nur diese.
            sources_json.append({"sentence": s.id,
                                 "start": spans[0][0], "end": spans[-1][1],
                                 "spans": spans, "role": role})

        claims_json.append({
            "id": c.id, "start": c.start, "end": c.end, "text": c.text,
            "relation": relation, "sources": sources_json,
            "confidence": conf, "margin": margin,
            "entities": ents_json, "flags": flags,
            "note": " · ".join(note_parts),
            "scores": {"top": round(s1, 3),
                       "lex": round(lex[ci][si1], 3),
                       "emb": (round(emb[ci][si1], 3) if emb else None),
                       "anchor": round(anchor[ci][si1], 3)},
        })

    return _assemble(article_text, transcript_text, art_sents, claims_json,
                     model_label)


def _assemble(article_text, transcript_text, art_sents, claims_json, model_label):
    title = art_sents[0].text if art_sents else "Eigene Analyse"
    return {
        "meta": {"titel": title, "quelle": "Eigenes Paar",
                 "modell": f"stufe0-2 · {model_label}"},
        "article": {
            "text": article_text,
            "sentences": [{"id": s.id, "start": s.start, "end": s.end,
                           "block": s.block, "paragraph": s.paragraph,
                           "text": s.text} for s in art_sents],
        },
        "transcript": {"text": transcript_text, "claims": claims_json},
    }
