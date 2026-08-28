"""
Entwurfs-Annotation aus einem Lauf erzeugen — Grundlage fürs Gold-Set.

Korrigieren statt neu anlegen: Die Pipeline trifft grob 70–80 % richtig,
also ist es billiger, ihre Ausgabe zu prüfen als jede Fundstelle von Hand
zu suchen. Das erkauft einen **Bestätigungs-Bias** — man übersieht eher
eine fehlende Quelle, als dass man eine falsche entfernt. Gegenmittel
steht in der erzeugten Datei als Arbeitsanweisung: einmal umgekehrt durch
den Artikel gehen und fragen, welcher Transkriptsatz diese Stelle nutzt.

**Annotiert wird der Transkriptsatz, nicht der Claim.** Claim-Grenzen und
-IDs ändern sich, sobald an `claims.py` gedreht wird; ein Gold-Set auf
Claim-Ebene wäre nach der nächsten Änderung an der Teilaussagen-Zerlegung
wertlos. Sätze sind stabil. Beim Auswerten mappt `eval.py` jeden Claim
auf den Satz, in dem er liegt, und vereinigt die Fundstellen.

**Zwei Quellenmengen.** `notwendig` sind die Sätze, ohne die ein Teil der
Behauptung unbelegt bliebe. `zulaessig` sind Sätze, die ebenfalls stützen,
aber entbehrlich sind — typischerweise das, was die Pipeline als
`redundant` ausgibt. CIR misst gegen `notwendig`, CIP zählt beide als
richtig. Ohne diese Trennung würde jede korrekt erkannte redundante
Quelle als Präzisionsfehler zählen.

    python3 gold_entwurf.py laeufe/voll/*.json -o gold/
    python3 gold_entwurf.py laeufe/voll/ -o gold/ --test-anteil 0.25
    python3 gold_entwurf.py lauf.json -o gold/heinsberg.json --split test

Mehrere Läufe auf einmal: Verzeichnis oder Glob angeben, `-o` auf einen
Ordner zeigen lassen. Der Dateiname wird dann aus dem Lauf abgeleitet.

**Die Split-Zuteilung passiert automatisch** über einen stabilen Hash des
Paarnamens. Stabil heißt: Dasselbe Paar landet bei jedem Aufruf im selben
Split, unabhängig von Reihenfolge oder Anzahl der Läufe — sonst würde ein
neu hinzugefügtes Paar die ganze Aufteilung verschieben und die
Testmenge wäre wertlos. `--test-anteil` steuert die Größe (Standard 0,25),
`--split` erzwingt einen festen Wert für alle angegebenen Läufe.

Bestehende Dateien werden nicht überschrieben; stattdessen wird eine
Zusammenführung angeboten (`--aktualisieren`), die bereits geprüfte
Einträge unangetastet lässt und nur neue Sätze anhängt.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

from kern import segmentierung

# Reihenfolge für den Fall, dass ein Satz in mehrere Claims mit
# unterschiedlichen Relationen zerfällt: Der auffälligste Befund gewinnt,
# damit die Entwurfszeile nicht harmloser aussieht, als der Lauf war.
REL_RANG = ["keine_quelle", "bedeutung_verschoben", "inferiert",
            "aggregiert", "direkt"]

ANLEITUNG = [
    "Arbeitsanweisung (diese Zeilen bleiben in der Datei stehen):",
    "1. Jede Zeile mit \"geprueft\": false durchgehen und auf true setzen.",
    "2. notwendig = Sätze, ohne die ein Teil der Aussage unbelegt bliebe.",
    "   zulaessig = stützt ebenfalls, ist aber entbehrlich (Dubletten).",
    "3. relation prüfen: direkt | aggregiert | bedeutung_verschoben |",
    "   inferiert | keine_quelle.",
    "4. flags_erwartet: nur Befunde, die WIRKLICH zutreffen sollten",
    "   (zahlkonflikt, ort_konflikt, kuerzel_konflikt, wortlaut_abweichung,",
    "   ident_unbelegt, zahl_unbelegt). Leere Liste heißt: kein Befund.",
    "5. Zum Schluss EINMAL umgekehrt: den Artikel lesen und fragen, welcher",
    "   Transkriptsatz diese Stelle nutzt. Das fängt die Quellen, die die",
    "   Pipeline gar nicht erst vorgeschlagen hat — der Bias des Entwurfs.",
    "6. Artikel- und Transkripttext danach NICHT mehr ändern, auch keine",
    "   Tippfehler: Die Zeichen-Offsets sind Teil der Annotation.",
]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _split_fuer(paar: str, anteil: float) -> str:
    """Stabile Split-Zuteilung aus dem Paarnamen.

    Bewusst kein Zufall und keine Reihenfolge: Ein später hinzugefügtes
    Paar darf die Zuteilung der bestehenden nicht verschieben, sonst
    wandern Paare zwischen dev und test und die Testmenge ist nicht mehr
    zurückgehalten, sondern nur noch zufällig unbenutzt.
    """
    wert = int(hashlib.sha256(paar.encode("utf-8")).hexdigest()[:8], 16)
    return "test" if (wert % 1000) / 1000.0 < anteil else "dev"


def _satz_von_claim(claim: dict, saetze: list) -> int | None:
    """Index des Transkriptsatzes, in dem der Claim beginnt."""
    start = claim.get("start")
    if start is None:
        return None
    for i, s in enumerate(saetze):
        if s.start <= start < s.end:
            return i
    # Claims können durch Normalisierung minimal verrutschen — nächster
    # Satz, dessen Anfang nicht hinter dem Claim liegt.
    davor = [i for i, s in enumerate(saetze) if s.start <= start]
    return davor[-1] if davor else None


def entwurf(daten: dict, paar: str, split: str) -> dict:
    transkript = daten["transcript"]["text"]
    artikel = daten["article"]["text"]
    saetze = segmentierung.segment(transkript, "transcript", "t")

    # Claims den Sätzen zuordnen
    proSatz: dict[int, list[dict]] = {}
    for c in daten["transcript"]["claims"]:
        i = _satz_von_claim(c, saetze)
        if i is not None:
            proSatz.setdefault(i, []).append(c)

    eintraege = []
    for i, s in enumerate(saetze):
        claims = proSatz.get(i, [])
        notwendig: list[str] = []
        zulaessig: list[str] = []
        flags: set[str] = set()
        for c in claims:
            for q in c.get("sources") or []:
                ziel = zulaessig if q.get("role") == "redundant" else notwendig
                if q["sentence"] not in ziel:
                    ziel.append(q["sentence"])
            flags |= set(c.get("flags") or [])
        zulaessig = [x for x in zulaessig if x not in notwendig]

        relationen = [c["relation"] for c in claims]
        if relationen:
            rel = min(relationen,
                      key=lambda r: REL_RANG.index(r) if r in REL_RANG
                      else len(REL_RANG))
        else:
            rel = "keine_quelle"

        eintraege.append({
            "satz": s.id,
            "text": s.text,
            "start": s.start,
            "end": s.end,
            "geprueft": False,
            "notwendig": sorted(notwendig, key=lambda x: int(x[1:])),
            "zulaessig": sorted(zulaessig, key=lambda x: int(x[1:])),
            "relation": rel,
            "flags_erwartet": sorted(f for f in flags
                                     if f not in ("signale_uneinig",)),
            "claims_im_lauf": [c["id"] for c in claims],
            "relationen_gemischt": len(set(relationen)) > 1,
            "notiz": "",
        })

    return {
        "paar": paar,
        "split": split,
        "anleitung": ANLEITUNG,
        "artikel_hash": _hash(artikel),
        "transkript_hash": _hash(transkript),
        "artikel_saetze": [{"id": s["id"], "text": s["text"]}
                           for s in daten["article"]["sentences"]],
        "eintraege": eintraege,
    }


def zusammenfuehren(alt: dict, neu: dict) -> dict:
    """Geprüfte Einträge behalten, neue Sätze anhängen.

    Nur für den Fall, dass sich die Satzsegmentierung geändert hat. Ein
    geprüfter Eintrag wird nie überschrieben — sonst wäre die Handarbeit
    beim nächsten Lauf wieder weg.
    """
    if alt.get("transkript_hash") != neu.get("transkript_hash"):
        print("[!] Transkripttext hat sich geändert — Offsets stimmen nicht "
              "mehr. Zusammenführung abgebrochen.", file=sys.stderr)
        return alt
    bekannt = {e["satz"]: e for e in alt["eintraege"]}
    raus = []
    for e in neu["eintraege"]:
        vorhanden = bekannt.get(e["satz"])
        if vorhanden and vorhanden.get("geprueft"):
            raus.append(vorhanden)
        else:
            raus.append(e)
    alt["eintraege"] = raus
    return alt


def main(argv: list[str]) -> int:
    ziel = None
    if "-o" in argv:
        k = argv.index("-o")
        ziel = argv[k + 1]
        del argv[k:k + 2]
    paar_fest = None
    if "--paar" in argv:
        k = argv.index("--paar")
        paar_fest = argv[k + 1]
        del argv[k:k + 2]
    split_fest = None
    if "--split" in argv:
        k = argv.index("--split")
        split_fest = argv[k + 1]
        del argv[k:k + 2]
    anteil = 0.25
    if "--test-anteil" in argv:
        k = argv.index("--test-anteil")
        anteil = float(argv[k + 1])
        del argv[k:k + 2]
    aktualisieren = "--aktualisieren" in argv
    muster = [a for a in argv if not a.startswith("-")]
    if not muster:
        print(__doc__.strip())
        return 1

    # Verzeichnisse und Globs auflösen
    quellen: list[str] = []
    for m in muster:
        if os.path.isdir(m):
            quellen += sorted(glob.glob(os.path.join(m, "*.json")))
        else:
            treffer = sorted(glob.glob(m))
            quellen += treffer if treffer else [m]
    if not quellen:
        print("Keine Lauf-Dateien gefunden.", file=sys.stderr)
        return 1
    if len(quellen) > 1 and paar_fest:
        print("--paar geht nur bei einer einzelnen Datei.", file=sys.stderr)
        return 1

    ziel_ist_ordner = bool(ziel) and (ziel.endswith(("/", os.sep))
                                      or os.path.isdir(ziel)
                                      or len(quellen) > 1)
    if ziel_ist_ordner:
        os.makedirs(ziel, exist_ok=True)

    fehler = 0
    zeilen: list[tuple[str, str, int, int]] = []
    for quelle in quellen:
        try:
            with open(quelle, encoding="utf-8") as f:
                daten = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[!] {quelle}: {e}", file=sys.stderr)
            fehler += 1
            continue

        paar = paar_fest or os.path.splitext(os.path.basename(quelle))[0]
        split = split_fest or _split_fuer(paar, anteil)
        if ziel_ist_ordner:
            pfad = os.path.join(ziel, f"{paar}.json")
        else:
            pfad = ziel or f"gold_{paar}.json"

        neu = entwurf(daten, paar, split)

        if os.path.exists(pfad):
            if not aktualisieren:
                print(f"[!] {pfad} existiert bereits — übersprungen. Mit "
                      "--aktualisieren zusammenführen.", file=sys.stderr)
                fehler += 1
                continue
            with open(pfad, encoding="utf-8") as f:
                neu = zusammenfuehren(json.load(f), neu)

        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(neu, f, ensure_ascii=False, indent=2)

        offen = sum(1 for e in neu["eintraege"] if not e["geprueft"])
        zeilen.append((pfad, neu["split"], len(neu["eintraege"]), offen))

    if zeilen:
        print(f"{'Datei':<34}{'Split':<7}{'Sätze':>7}{'offen':>7}")
        for pfad, split, n, offen in zeilen:
            print(f"{pfad:<34}{split:<7}{n:>7}{offen:>7}")
        test = sum(1 for _p, s2, _n, _o in zeilen if s2 == "test")
        print(f"\n{len(zeilen)} Paar(e), davon {test} im Test-Split "
              "(automatisch über den Paarnamen zugeteilt, stabil bei "
              "späteren Ergänzungen).")
        print("Zum Annotieren: annotate.html im Browser öffnen und die "
              "Gold-Datei hineinziehen.")
    return 1 if fehler and not zeilen else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
