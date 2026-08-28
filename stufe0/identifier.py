"""
Stufe 0.6 — Identifier-Prüfung: Orte, Organisationen, Kürzel.

Warum eine eigene Stufe. Die Stufen 1 und 2 messen Ähnlichkeit und lesen
Ähnlichkeit als Belegtheit. Zeichen-3/4-Gramme sind absichtlich
kompositionstolerant, damit „Gewerbesteuereinnahmen" auf
„Gewerbesteuer" passt — dieselbe Toleranz macht aber „Langenharm" zu
einem sehr guten Treffer für „Langenhorn" und „XL-Rechenzentrum" zu
einem für „XXL-Rechenzentrum". Gemessen an einem absichtlich
verfälschten Satz: Abdeckung 1,00 bei lex 0,90. Eine solche Verfälschung
*erhöht* den Score und ist über keine Schwelle erreichbar.

Deshalb ein Kanal mit umgekehrter Logik: Hier ist **Fast-Identität
verdächtig** statt bestätigend. Ein Identifier im Claim, der nirgends im
Artikel wörtlich vorkommt, für den es aber einen sehr nahen Nachbarn
gibt, ist die Signatur einer Verfälschung.

Zwei Klassen, zwei Vergleichsverfahren:

  Namen   Orte und Organisationen aus `ner.entities` (LOC/ORG).
          Verglichen wird morphologisch: gemeinsamer Stamm plus beide
          Reste aus einer geschlossenen Endungsliste = Flexionsvariante,
          also in Ordnung. „Langenhorn"/„Langenharm" teilt den Stamm
          „langenh", die Reste „orn"/„arm" sind keine Endungen.

  Kürzel  Allcaps- und Alphanumerik-Token (XXL, EGNF, B5, 5G), an
          Bindestrichen aus Komposita gelöst. Hier gilt ausschließlich
          exakte Gleichheit; der nächste Nachbar wird über
          Editierdistanz gesucht, weil bei zwei- bis vierstelligen
          Kürzeln kein Stamm zu finden ist.

Geprüft wird gegen den **ganzen Artikel**, nicht gegen die zugeordneten
Fundstellen. Ortsnamen stehen in Lokalnachrichten in fast jedem Absatz;
eine Prüfung gegen die Fundstelle allein würde bei jeder Verdichtung
Fehlalarme erzeugen, ohne einen echten Fehler zu finden. Dieselbe Wahl
trifft `ner.matches` für Personen.

Personen prüft weiterhin Stufe 0.5. Hier sind sie ausgeschlossen, sonst
stünde jeder Name doppelt im Inspector.
"""
from __future__ import annotations

import difflib
import re

from stufe0 import personen as ner

# Endungen, die im Deutschen flektieren oder ableiten, ohne den Stamm zu
# wechseln. Geschlossene Klasse — was hier nicht steht, gilt als
# Stammabweichung. Bewusst knapp gehalten: jede Ergänzung macht die
# Prüfung blinder.
_ENDUNGEN = {
    "", "e", "en", "n", "s", "es", "er", "ern", "em", "ns",
    "in", "innen", "nen",
    "ung", "ungen", "um", "a", "as", "os", "us",
}

# Ableitungen von Ortsnamen: Einwohner- und Adjektivformen. Eigene Menge,
# weil sie nur zusammen mit der Umlautfaltung gebraucht werden —
# „Münchner" gegen „München", „bayerische" gegen „Bayern". Ohne sie meldet
# die Prüfung in Lokalnachrichten laufend Fehlalarme, mit ihnen wird sie
# gegen reine Endungsvertauschungen blinder.
_ABLEITUNGEN = {
    "er", "ner", "ler", "aner", "ianer",
    "isch", "ische", "ischer", "ischen", "isches",
    "sche", "scher", "schen",
}

# So viele Zeichen müssen zwei Wörter am Anfang teilen, damit sie
# überhaupt als Variantenpaar in Frage kommen. Darunter ist der Vergleich
# Zufall („Bau" und „Bad" teilen zwei Zeichen).
_MIN_STAMM = 4


def _falte(w: str) -> str:
    """Umlaute auf ihre Grundform. Nur für den Ableitungsvergleich."""
    return w.replace("ä", "a").replace("ö", "o").replace("ü", "u")

# Kürzel: mindestens zwei Zeichen, komplett groß, oder Buchstaben und
# Ziffern gemischt. Reine Zahlen gehören zu Stufe 0 (stufe0/zahlen.py).
_CODE = re.compile(r"[A-ZÄÖÜ]{2,}|[A-Za-zÄÖÜäöü]+\d+|\d+[A-Za-zÄÖÜäöü]+")

_WORT = re.compile(r"[\wÄÖÜäöüß]+")

# Editierdistanz, bis zu der zwei Kürzel als „verwechselt" gelten.
_CODE_DIST = 2


def _tokens(text: str) -> dict[str, str]:
    """Wörter kleingeschrieben -> erste Originalschreibweise.

    Der Vergleich läuft kleingeschrieben, die Anzeige braucht aber die
    Schreibweise aus dem Artikel: „dort ‚Langenhorn'", nicht
    „dort ‚langenhorn'".
    """
    out: dict[str, str] = {}
    teile = [text] + re.split(r"[-–/]", text)
    for teil in teile:
        for w in _WORT.findall(teil):
            out.setdefault(w.lower(), w)
    return out


def _ketten(text: str) -> set[str]:
    """Ausgeschriebene Ziffernketten in ihrer Ziffernform.

    „zwei-eins-zwei-C-D" -> „212CD". Das Transkript spricht
    Typbezeichnungen aus, der Artikel schreibt sie. Ohne diese Auflösung
    stünde auf der einen Seite ein Kürzel und auf der anderen gar nichts
    Vergleichbares — `stufe0/zahlen.py` unterdrückt beide Formen inzwischen
    als Mengenangabe, also muss der Abgleich hier stattfinden.
    """
    from stufe0.zahlen import _kette_aufloesen, _kettenspannen
    return {aufgeloest for a, b in _kettenspannen(text)
            if (aufgeloest := _kette_aufloesen(text[a:b]))}


def _codes(text: str) -> set[str]:
    """Kürzel im Text, Groß-/Kleinschreibung erhalten für die Anzeige."""
    out: set[str] = set()
    for teil in re.split(r"[-–/\s]", text):
        for m in _CODE.finditer(teil):
            t = m.group(0)
            if t.isdigit():
                continue
            out.add(t)
    out |= _ketten(text)
    return out


def _distanz(a: str, b: str) -> int:
    """Levenshtein, iterativ. Nur für Kürzel — die Strings sind kurz."""
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    vorher = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        jetzt = [i]
        for j, cb in enumerate(b, 1):
            jetzt.append(min(vorher[j] + 1, jetzt[j - 1] + 1,
                             vorher[j - 1] + (ca != cb)))
        vorher = jetzt
    return vorher[-1]


def _teilbar(a: str, b: str, endungen: set[str],
             leer_erlaubt: bool = True) -> bool | None:
    """Gibt es eine Trennstelle, an der beide Reste Endungen sind?"""
    if a.startswith(b) or b.startswith(a):
        if leer_erlaubt or len(a) != len(b):
            return True
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if i < _MIN_STAMM:
        return None
    # Alle Trennstellen prüfen, nicht nur die maximale. Der gierige
    # Präfix frisst sonst den Anfang der Endung: „grünen"/„grüner" teilt
    # gierig „grüne", übrig bleiben „n" und „r" — und „r" allein ist keine
    # Endung. Bei Trennstelle 4 bleiben „en" und „er", beides Endungen.
    for k in range(_MIN_STAMM, i + 1):
        if a[k:] in endungen and b[k:] in endungen:
            if leer_erlaubt or a[k:] or b[k:]:
                return True
    return False


def _aehnlich(a: str, b: str) -> float:
    """Zeichenähnlichkeit zweier Wörter, für die Kandidatenwahl."""
    return difflib.SequenceMatcher(a=a, b=b).ratio()


def _variante(a: str, b: str) -> bool | None:
    """Sind `a` und `b` Formen desselben Wortes?

    True   Flexions- oder Ableitungsvariante — kein Befund
    False  gemeinsamer Stamm, aber abweichende Fortsetzung — Verdacht
    None   zu wenig gemeinsam, um überhaupt ein Paar zu sein

    Drei Regeln, in dieser Reihenfolge:

    **Präfix.** Ist ein Wort echter Präfix des anderen, ist es nie ein
    Konflikt. Das deckt Komposition („Nord" aus „Nord- und Ostsee" gegen
    „Nordsee"), Ableitung („Münsteraner" gegen „Münster") und Genitiv
    („Nordfrieslands") mit einer Regel ab. Verfälschungen *tauschen*
    Zeichen, sie kürzen nicht — „Langenharm" ist kein Präfix von
    „Langenhorn".

    **Alle Trennstellen.** Siehe `_teilbar`.

    **Umlautfaltung, aber nur mit echter Ableitung.** „Lippstädter" gegen
    „Lippstadt" und „Münchner" gegen „München" sind ohne Faltung nicht
    lösbar, weil der Umlaut mitten im Stamm wechselt. Unterscheiden sich
    zwei Wörter dagegen *ausschließlich* im Umlaut („Munster" gegen
    „Münster"), bleibt es ein Konflikt — genau das ist ein
    Transkriptionsfehler und kein Wortbildungsmuster.
    """
    a, b = a.lower(), b.lower()
    if a == b:
        return True
    r = _teilbar(a, b, _ENDUNGEN)
    if r is True:
        return True
    fa, fb = _falte(a), _falte(b)
    if (fa != a or fb != b) and fa != fb:
        if _teilbar(fa, fb, _ENDUNGEN | _ABLEITUNGEN,
                    leer_erlaubt=False) is True:
            return True
    return r


def _namen(text: str) -> list[str]:
    """Orte und Organisationen. Personen bleiben bei Stufe 0.5.

    Im Regex-Rückfall von `ner` sind die Klassen nicht trennbar (alle
    Treffer tragen '?'), dann würden hier Personen doppelt gemeldet.
    Deshalb liefert der Rückfall bewusst nichts — die Kürzelprüfung
    läuft weiter, sie braucht kein Modell.
    """
    if ner.backend() != "spacy":
        return []
    return [s for s, _a, _b, _l in ner.entities(text, ("LOC", "ORG"))]


def pruefe(claim_text: str, artikel_text: str) -> list[dict]:
    """Identifier im Claim gegen den Artikel prüfen.

    Liefert Befunde als
    `{"art": "ort"|"kuerzel", "surface", "status", "quelle_surface"?}`
    mit `status` = `konflikt` (naher Nachbar im Artikel, aber nicht
    wörtlich vorhanden) oder `unbelegt` (nichts Vergleichbares im
    Artikel).
    """
    befunde: list[dict] = []
    art_tokens = _tokens(artikel_text)
    art_codes = _codes(artikel_text)
    gesehen: set[str] = set()

    # ---------------- Namen (Ort / Organisation)
    for surface in _namen(claim_text):
        for w in _WORT.findall(surface):
            wl = w.lower()
            if len(wl) < 4 or wl in gesehen:
                continue
            gesehen.add(wl)
            if wl in art_tokens:
                continue
            # Nur der ÄHNLICHSTE Kandidat wird beurteilt, nicht die
            # Disjunktion über alle. Sonst hebt ein zufälliger Treffer
            # irgendwo im Artikel einen echten Konflikt auf: „Langenharm"
            # gegen „Länge" ergibt nach Umlautfaltung „lange", und das ist
            # ein Präfix von „langenharm" — die Regel meldete den Fall als
            # Flexionsvariante und verwarf den Befund gegen „Langenhorn".
            kand = max(art_tokens, key=lambda v: _aehnlich(wl, v))
            urteil = _variante(wl, kand)
            if urteil is True:
                continue                      # Flexionsvariante — in Ordnung
            if urteil is False:
                befunde.append({"art": "ort", "surface": w,
                                "status": "konflikt",
                                "quelle_surface": art_tokens[kand]})
            else:
                befunde.append({"art": "ort", "surface": w,
                                "status": "unbelegt"})

    # ---------------- Kürzel
    art_codes_low = {c.lower() for c in art_codes}
    for code in _codes(claim_text):
        cl = code.lower()
        if cl in gesehen or cl in art_codes_low or cl in art_tokens:
            continue
        gesehen.add(cl)
        nah = [c for c in art_codes if 0 < _distanz(cl, c) <= _CODE_DIST]
        if nah:
            nah.sort(key=lambda c: (_distanz(cl, c), len(c)))
            befunde.append({"art": "kuerzel", "surface": code,
                            "status": "konflikt",
                            "quelle_surface": nah[0]})
        else:
            befunde.append({"art": "kuerzel", "surface": code,
                            "status": "unbelegt"})

    return befunde


if __name__ == "__main__":                     # Selbsttest ohne Modell
    artikel = ("Die Pläne für ein XXL-Rechenzentrum in Langenhorn sorgen "
               "seit Wochen für Diskussionen. Die kreiseigene "
               "Erschließungsgesellschaft Nordfriesland (EGNF) vermarktet "
               "die Fläche im Ortsteil Mönkebüll.")
    faelle = [
        "Die Pläne für ein XL-Rechenzentrum in Langenharm sorgen für Ärger.",
        "Die Pläne für ein XXL-Rechenzentrum in Langenhorn sorgen für Ärger.",
        "Die EGNF vermarktet die Fläche in Mönkebüll.",
        "Die EGFN vermarktet die Fläche.",
    ]
    print("Backend:", ner.backend(), "(ohne spaCy nur Kürzelprüfung)\n")
    for f in faelle:
        print(f"{f}\n  -> {pruefe(f, artikel) or 'sauber'}\n")
