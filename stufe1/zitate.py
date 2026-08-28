"""
Zitatblöcke und Sprecherkontext.

Das Problem: Zitatsätze nennen ihren Sprecher fast nie. Die Attribution
steht ein oder zwei Sätze vorher, und was „wir" bezeichnet, steht nochmal
woanders. Ein Transkript macht daraus dritte Person mit Namen — und die
Wortüberlappung bricht weg.

    Artikel s7   „Das ist ein wunder Punkt für mich und meine Kollegen aus
                 dem Kreis", sagt Wolfgang Wahl, Vorsitzender des …
    Artikel s8   „Natürlich würden wir die Reit-WM auch gerne für uns als
                 Gästebringer verzeichnen …"                 <- kein Name
    Transkript   Er und viele Kollegen hätten gern mehr Gäste durch die
                 Reit-WM gewonnen.                           <- „Kollegen"

„Kollegen" steht in s7, der Beleg in s8. Gemessen an diesem Paar hebt der
geerbte Kontext die Abdeckung von s8 für diesen Claim von 0,169 auf 0,451
— und damit über den bisherigen Fehltreffer s11 (0,273).

Was dieses Modul NICHT tut: Pronomen auflösen. „wir" wird nicht durch
„Wolfgang Wahl und die Gastronomiebetriebe im Kreis" ersetzt. Das wäre
Koreferenzanalyse, im Deutschen unzuverlässig, und ein Fehler wirkte
still. Gesammelt werden nur die Wörter, mit denen der Block selbst seine
Bezugsgruppe benennt — „meine Kollegen aus dem Kreis", „unsere
Buchungen". Rein additiv, nichts wird ersetzt.

Zwei Bestandteile, weil sie unterschiedlich wirken (gemessen):

  Sprechername   half c11 (+0,175), bei c5 wirkungslos
  Gruppenwörter  halfen c5 (+0,29) und c7 (+0,13)

Welcher Teil greift, hängt am Claim — deshalb beide.
"""
from __future__ import annotations

import re

from stufe0 import personen as ner

# Anführungszeichen. Achtung: Im Deutschen ist U+201E („) das öffnende und
# U+201C (“) das SCHLIESSENDE Zeichen — genau umgekehrt zum Englischen.
# Beide Rollen zu vermischen lässt jeden Block offen bleiben.
_AUF = "\u201e\u00ab\u201a"      # „ « ‚
_ZU = "\u201c\u201d\u00bb\u2018\""   # “ ” » ‘ "

# Attribution wird STRUKTURELL erkannt, nicht über eine Verbliste.
#
# Eine Positivliste von Redeverben ist prinzipiell unvollständig: „fügt
# hinzu", „räumt ein", „kritisiert", „beklagt", „versichert", „zufolge" —
# und jede Flexionsform müsste einzeln stehen. Die Satzstruktur trägt
# dagegen zuverlässig, weil das Deutsche nach einem Zitat invertiert:
#
#     …“,  sagt   Wolfgang Wahl, Vorsitzender des …
#          ^Verb  ^Eigenname
#     …,   weiß   Wolfgang Wahl.
#     …“,  so     eine Sprecherin.
#
# Gesucht wird also: Trennzeichen, ein bis zwei Wörter, Eigenname. Was in
# der Mitte steht, muss nicht bekannt sein — es genügt zu wissen, was dort
# NICHT stehen kann. Diese Negativliste ist im Gegensatz zur Verbliste
# geschlossen: Funktionswörter sind eine endliche Klasse, und ein finites
# Verb gehört nie dazu. Damit fällt „, die zur Reit-WM angereist sind"
# heraus (Relativpronomen) und „, also im südlichen Kreis Heinsberg"
# ebenfalls (zu großer Abstand).
#
# Die Eigennamen kommen aus ner.py — demselben Modul, das die
# Personenerkennung der Stufe 0.5 leistet. Mit spaCy ließe sich die Mitte
# zusätzlich über `token.pos_` als finites Verb prüfen; die Struktur
# bliebe dieselbe.
_NICHT_VERB = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen",
    "einem", "einer", "eines", "welche", "welcher", "welches", "dessen",
    "deren", "sein", "seine", "ihr", "ihre", "diese", "dieser", "dieses",
    "und", "oder", "aber", "doch", "jedoch", "sondern", "also", "zwar",
    "denn", "wenn", "weil", "dass", "ob", "als", "wie", "wo", "während",
    "obwohl", "damit", "sobald", "nachdem", "bevor", "falls",
    "in", "im", "an", "am", "auf", "für", "mit", "von", "vom", "bei",
    "beim", "nach", "über", "unter", "vor", "seit", "bis", "durch",
    "ohne", "gegen", "um", "zu", "zur", "zum", "aus", "neben", "trotz",
    "nicht", "auch", "noch", "schon", "nur", "sehr", "immer", "dort",
    "hier", "dann", "darum", "deshalb", "dabei", "etwa", "rund",
}

# Rollenbezeichnungen für die generische Attribution („so eine Sprecherin")
_ROLLE = (r"Sprecher(?:in)?|Hotelier|Wirt|Wirtin|Betreiber(?:in)?|"
          r"Inhaber(?:in)?|Vertreter(?:in)?|Mitarbeiter(?:in)?|"
          r"Gesch\u00e4ftsf\u00fchrer(?:in)?|Hoteldirektor(?:in)?")
_ATTR_GENERISCH = re.compile(
    r"[,\u201c]\s*\S+\s+(?:eine?[rmn]?|der|die|das|den|dem)\s+(?:"
    + _ROLLE + r")\b", re.UNICODE)

_TRENNER = re.compile(r"[,\u201c:]")
_MAX_ZWISCHEN = 2       # Wörter zwischen Trennzeichen und Eigenname

# Nominalphrase nach Possessivpronomen der 1. Person.
# „meine Kollegen aus dem Kreis" -> „Kollegen aus dem Kreis"
_GRUPPE = re.compile(
    r"\b(?:mein|meine|meinen|meiner|meinem|unser|unsere|unseren|unserer|"
    r"unserem)\s+([A-ZÄÖÜ][\wäöüß\-]+"
    r"(?:\s+(?:aus|in|im|von|vom|bei|für)"
    r"(?:\s+(?:der|die|das|dem|den|des))?"
    r"\s+[A-ZÄÖÜ][\wäöüß\-]+){0,2})",
    re.UNICODE)
# „für uns als Gästebringer"
_GRUPPE_UNS = re.compile(r"\buns\s+als\s+([A-ZÄÖÜ][\wäöüß\-]+)", re.UNICODE)

# Wörter, die als Sprechername nichts taugen (Satzanfänge, Füllsel)
_TITEL_RE = re.compile(
    r"^(?:[A-ZÄÖÜ][\wäöüß-]*(?:direktor|direktorin|chef|chefin|leiter|"
    r"leiterin|meister|meisterin|sprecher|sprecherin|vorsitzende[rn]?)"
    r"|Dr\.|Prof\.|Herr|Frau)$", re.UNICODE)

_MAX_NAME = 80          # Zeichen; Appositionen können lang werden
_MAX_GRUPPEN = 3        # Gruppenphrasen je Block

# Sollen Gruppenwörter über Blockgrenzen hinweg beim selben Sprecher
# gelten? Gemessen am Heinsberg-Paar ein Nullsummenspiel mit leichtem
# Minus: c7 wird dadurch gefunden (s13), c5 bekommt aber s11 statt s8 —
# F1 0,84 statt 0,86. Ein falscher Beleg wiegt schwerer als ein
# fehlender, deshalb aus. Umschaltbar, weil ein zweites Gold-Paar die
# Abwägung kippen kann.
GRUPPEN_UEBER_BLOECKE = False


def _zitatzeichen(text: str) -> tuple[int, bool]:
    """(Bilanz offener Anführungen, ob überhaupt eines vorkam)."""
    saldo = 0
    gesehen = False
    for ch in text:
        if ch in _AUF:
            saldo += 1
            gesehen = True
        elif ch in _ZU:
            saldo -= 1
            gesehen = True
    return saldo, gesehen


def _attribution(text: str) -> str | None:
    """Sprechername aus einem Satz, strukturell bestimmt.

    Muster A (Inversion nach Zitat oder Komma):
        <Trennzeichen> <1-2 Wörter> <Eigenname> [, Apposition]
    Muster B (Voranstellung):
        <Eigenname> <1-2 Wörter> <Doppelpunkt oder öffnendes Zitat>

    Der Eigenname stammt aus ner.py; die Wörter dazwischen müssen nur
    frei von Funktionswörtern sein. Steht der Name unmittelbar hinter dem
    Trennzeichen, ist es eine Apposition und keine Attribution.
    """
    ents = ner.entities(text)
    if not ents:
        return None

    for surface, start, end, _lab in ents:
        # --- Muster A
        vorher = text[:start]
        treffer = list(_TRENNER.finditer(vorher))
        if treffer:
            zwischen = vorher[treffer[-1].end():].split()
            # Titel vor dem Namen gehören zur Attribution, nicht dazwischen
            while zwischen and _TITEL_RE.match(zwischen[-1]):
                zwischen = zwischen[:-1]
            if (1 <= len(zwischen) <= _MAX_ZWISCHEN
                    and zwischen[0].lower().strip(".,") not in _NICHT_VERB
                    and zwischen[0][:1].islower()):
                return _mit_apposition(text, start, end)

        # --- Muster B
        nachher = text[end:]
        m = re.match(r"\s*((?:\S+\s+){0,2})[:\u201e]", nachher)
        if m:
            woerter = m.group(1).split()
            if woerter and woerter[0].lower() not in _NICHT_VERB:
                return _mit_apposition(text, start, end)
    return None


def _mit_apposition(text: str, start: int, end: int) -> str:
    """Name plus unmittelbar folgende Apposition („, Vorsitzender des …")."""
    rest = text[end:]
    m = re.match(r",\s*([A-ZÄÖÜ][^.\u201e\u201c]{0,70})", rest)
    name = text[start:end]
    if m:
        name = name + ", " + m.group(1).rstrip(" ,.;:")
    return name[:_MAX_NAME]


def _namen_im_satz(text: str) -> list[str]:
    """Eigennamen eines Satzes — über ner.py, nicht über Großschreibung.

    Die frühere Fassung dieses Moduls verlangte zwei großgeschriebene
    Wörter in Folge. Genau diese Heuristik hatte ner.py schon einmal
    abgelöst, und aus gutem Grund: Im Deutschen wird jedes Substantiv
    großgeschrieben, „Wolfgang Wahl Verständnis" sieht deshalb aus wie ein
    dreiteiliger Name. Mit spaCy ist das eine saubere Entitätsgrenze, im
    Regex-Rückfall greifen die dort gepflegten Stopplisten.
    """
    return [s for s, _a, _b, _l in ner.entities(text)]


def bloecke(sents) -> list[list[int]]:
    """Zitatblöcke als Listen von Satzindizes.

    Ein Block ist ein Lauf zusammenhängender Sätze innerhalb EINES
    Absatzes, der durch Anführungszeichen zusammengehalten wird.

    Absatzgrenzen beenden einen Block immer. Eigennamen dagegen NICHT:
    „Anders sei das beim Pink-Pop-Festival in Landgraaf" steht mitten in
    der Rede einer Hotelsprecherin — würde der Name den Block beenden,
    erbte der Folgesatz den falschen Kontext.
    """
    out: list[list[int]] = []
    aktuell: list[int] = []
    offen = 0
    for i, s in enumerate(sents):
        neuer_absatz = i > 0 and s.paragraph != sents[i - 1].paragraph
        if neuer_absatz and aktuell:
            out.append(aktuell)
            aktuell, offen = [], 0
        saldo, gesehen = _zitatzeichen(s.text)
        if offen > 0 or gesehen:
            aktuell.append(i)
            offen = max(0, offen + saldo)
        elif aktuell:
            out.append(aktuell)
            aktuell = []
    if aktuell:
        out.append(aktuell)
    return [b for b in out if b]


def _kern(sprecher: str) -> str:
    """Nachname bzw. letztes Namenswort — Schlüssel für die Gruppenwörter."""
    teile = sprecher.split(",")[0].split()
    return teile[-1] if teile else ""


def _bestimme_sprecher(block, sents, letzter_name, vorheriger: str) -> str:
    """Sprecher eines Blocks.

    Reihenfolge: eigene Attribution, dann generische Attribution („so eine
    Sprecherin") aufgelöst über den nächstliegenden Namen, dann der
    Sprecher des VORHERIGEN Blocks im selben Absatz, zuletzt der
    nächstliegende Name.

    Der vorherige Block muss vor den nächstliegenden Namen: Ein Block
    ohne eigene Attribution setzt fast immer dieselbe Rede fort, die ein
    eingeschobener Erzählsatz nur unterbrochen hat. „Anders sei das beim
    Pink-Pop-Festival in Landgraaf" steht zwischen zwei Zitaten derselben
    Sprecherin — der nächstliegende Name wäre dort das Festival.
    """
    for i in block:
        name = _attribution(sents[i].text)
        if name:
            return name
    vor = block[0] - 1
    if vor >= 0 and sents[vor].paragraph == sents[block[0]].paragraph:
        name = _attribution(sents[vor].text)
        if name:
            return name
    for i in block:
        if _ATTR_GENERISCH.search(sents[i].text):
            return letzter_name[i]
    return vorheriger or letzter_name[block[0]]


def _reichste_form(name: str, bekannt: list[str]) -> str:
    """Reichste im Text belegte Form eines Sprechernamens.

    Ein Sprecher wird einmal vollständig eingeführt („sagt Hoteldirektor
    Eugene Mandele") und später abgekürzt („sagt Mandele"). Für den
    Suchkontext ist die vollständige Form mit Funktionsbezeichnung
    wertvoller — sie bringt gerade die Wörter mit, die eine
    Zusammenfassung aufgreift („Dehoga-Kreisverband Heinsberg" ->
    „im Kreis Heinsberg").

    Nebeneffekt: Verunreinigte Treffer des Regex-Rückfalls werden
    geglättet. „Wolfgang Wahl Verständnis" teilt den Namensbestandteil
    „Wahl" mit der vollständigen Form und wird durch sie ersetzt.
    """
    if not name:
        return name
    eigene = ner.name_tokens(name.split(",")[0])
    beste = name
    for b in bekannt:
        if b == name:
            continue
        andere = ner.name_tokens(b.split(",")[0])
        if eigene & andere and len(b) > len(beste):
            beste = b
    return beste


def _waehle_name(namen: list[str], bekannt: list[str]) -> str:
    """Aus den Namen eines Satzes den plausibelsten Sprecher wählen.

    Vorrang hat ein Name, der im Text schon einmal als Sprecher einer
    Attribution aufgetreten ist — zurückgegeben wird dann dessen volle
    Form samt Funktionsbezeichnung. Das löst zwei Fälle auf einmal:

      „Dafür, dass Aachener Hotels … aufschlagen, hat Wolfgang Wahl
       Verständnis."      -> nicht „Aachener Hotels", sondern Wahl
      „… sagt Hoteldirektor Eugene Mandele."
       -> nicht die gekappte Form „Hoteldirektor Eugene"

    Sonst der erste Name: Im Deutschen steht das Subjekt vorn, und
    „Darum kann das City-Hotel Geilenkirchen, also im südlichen Kreis
    Heinsberg, …" nennt zuerst den Betrieb und dann den Ort.
    """
    for n in namen:
        for b in bekannt:
            if n in b or b.split(",")[0] in n:
                return b
    return namen[0] if namen else ""


def sprecherkontexte(sents) -> list[str]:
    """Je Satzindex der geerbte Kontextstring ('' = keine Anreicherung).

    Angereichert wird nur, wo es nötig ist:
      1. der Satz gehört zu einem Zitatblock,
      2. er trägt ein Pronomen der 1. Person oder öffnet/setzt ein Zitat
         fort, und
      3. er nennt keinen eigenen Eigennamen.

    Bedingung 3 ist die wichtigste: Sätze wie „Wolfgang Wahl selbst
    betreibt das Hotel am Weiher" nennen ihren Bezug selbst und dürfen
    nicht angereichert werden — sonst verstärkt man, was ohnehin
    funktioniert, und verwischt die Unterscheidung innerhalb des Blocks.
    """
    kontexte = [""] * len(sents)
    ich_wir = re.compile(r"\b(wir|uns|unser\w*|ich|mich|mir|mein\w*)\b", re.I)

    # Nächstliegender benannter Bezug vor einer Position. Genommen wird
    # der ERSTE Name des jüngsten Satzes, der überhaupt einen enthält:
    # Im Deutschen steht das Subjekt vorn, und „Darum kann das City-Hotel
    # Geilenkirchen, also im südlichen Kreis Heinsberg, …" nennt zuerst
    # den Sprecher und danach die Ortsangabe. Der letzte Name wäre hier
    # „Kreis Heinsberg" — also der Ort statt des Betriebs.
    bekannt = [a for a in (_attribution(s.text) for s in sents) if a]
    letzter_name: list[str] = []
    laufend = ""
    for s in sents:
        letzter_name.append(laufend)
        namen = _namen_im_satz(s.text)
        if namen:
            laufend = _waehle_name(namen, bekannt)

    # Gruppenwörter gehören zum SPRECHER, nicht zum einzelnen Block:
    # „meine Kollegen aus dem Kreis" fällt in einem Block, der Beleg steht
    # im nächsten. Deshalb zwei Durchgänge — erst je Sprecher sammeln,
    # dann verteilen.
    blockliste = bloecke(sents)
    sprecher_je_block: list[str] = []
    gruppen_je_sprecher: dict[str, list[str]] = {}
    gruppen_je_block: list[list[str]] = []

    vorheriger = ""
    vor_absatz = None
    for block in blockliste:
        absatz = sents[block[0]].paragraph
        if absatz != vor_absatz:
            vorheriger, vor_absatz = "", absatz
        sprecher = _reichste_form(
            _bestimme_sprecher(block, sents, letzter_name, vorheriger),
            bekannt)
        vorheriger = sprecher
        sprecher_je_block.append(sprecher)
        kern = _kern(sprecher)
        eimer = gruppen_je_sprecher.setdefault(kern, [])
        eigen: list[str] = []
        gruppen_je_block.append(eigen)
        for i in block:
            for m in list(_GRUPPE.finditer(sents[i].text)) + \
                     list(_GRUPPE_UNS.finditer(sents[i].text)):
                phrase = m.group(1).strip(" ,.;:")
                if not phrase:
                    continue
                if phrase not in eimer and len(eimer) < _MAX_GRUPPEN:
                    eimer.append(phrase)
                if phrase not in eigen and len(eigen) < _MAX_GRUPPEN:
                    eigen.append(phrase)

    for bi, (block, sprecher) in enumerate(zip(blockliste, sprecher_je_block)):
        gruppen = (gruppen_je_sprecher.get(_kern(sprecher), [])
                   if GRUPPEN_UEBER_BLOECKE else gruppen_je_block[bi])
        teile = [t for t in (sprecher, " ".join(gruppen)) if t]
        if not teile:
            continue
        kontext = " ".join(teile)
        # Nachname als Prüfmarke: Nennt ein Satz den Sprecher selbst, wäre
        # die Anreicherung nur Verstärkung des ohnehin Funktionierenden —
        # und sie verwischt die Unterscheidung innerhalb des Blocks.
        kern = sprecher.split(",")[0].split()
        marke = kern[-1] if kern else ""

        for i in block:
            satz = sents[i].text
            nennt_sich_selbst = bool(marke and marke in satz) or \
                bool(_namen_im_satz(satz))
            braucht = bool(ich_wir.search(satz)) or \
                _zitatzeichen(satz)[1]
            if braucht and not nennt_sich_selbst:
                kontexte[i] = kontext
    return kontexte


if __name__ == "__main__":      # Schnelltest ohne Pipeline
    from dataclasses import dataclass

    @dataclass
    class S:
        text: str
        paragraph: int

    beispiel = [
        ("Kreis Heinsberg", 0),
        ("Aber hat das Großereignis Auswirkungen auf den Kreis?", 1),
        ("„Das ist ein wunder Punkt für mich und meine Kollegen aus dem "
         "Kreis“, sagt Wolfgang Wahl, Vorsitzender des Dehoga-Kreisverbands "
         "Heinsberg.", 2),
        ("„Natürlich würden wir die Reit-WM auch gerne für uns als "
         "Gästebringer verzeichnen, aber tatsächlich sehen wir hier kaum "
         "einen Effekt auf unsere Buchungen.“", 2),
        ("Wolfgang Wahl selbst betreibt das Hotel am Weiher in Erkelenz.", 2),
    ]
    sents = [S(t, p) for t, p in beispiel]
    print("Blöcke:", bloecke(sents))
    for i, k in enumerate(sprecherkontexte(sents)):
        print(f"  s{i+1}: {k or '—'}")
