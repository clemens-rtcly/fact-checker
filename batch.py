"""
Alle Paare neu durchrechnen — ohne Frontend, ohne Klickarbeit.

Liest bestehende Lauf-JSONs (die Dateien aus dem Viewer), nimmt daraus
Artikel- und Transkripttext und schickt beides erneut durch die Pipeline.
Damit lässt sich nach jeder Codeänderung der ganze Bestand in einem
Durchgang erneuern — Voraussetzung dafür, dass `eval.py` überhaupt etwas
Vergleichbares zu sehen bekommt.

    python3 batch.py laeufe/voll -o laeufe/voll
    python3 batch.py laeufe/voll -o laeufe/ohne_nli --nli ohne
    python3 batch.py laeufe/voll -o laeufe/lokal --emb local-e5-large
    python3 batch.py laeufe/voll -o laeufe/voll --neu      # auch fertige neu
    python3 batch.py laeufe/voll -o laeufe/voll --batch 4  # kleinere Blöcke
    python3 batch.py laeufe/voll -o laeufe/ohne05 --ohne 0.5
    python3 batch.py laeufe/voll -o laeufe/kern --ohne 0,0.5,0.6,0.8,1.5

**Stufen abschalten.** `--ohne` nimmt Nummern oder Namen (Komma-Liste,
siehe konfig.STUFEN): `--ohne 0.5,wortlaut` rechnet ohne Personen-NER
und ohne Wortlaut-Diff. Gedacht für Beitragsmessungen — ein Lauf je
abgeschalteter Stufe, dann `eval.py --laeufe` über alle Ordner. Bei
Abweichung vom Standard steht die Schalterstellung in `meta.stufen`.

**Modell wird einmal geladen.** `nli.load_nli` hält einen modulweiten
Cache; da alle Paare in einem Prozess laufen, fällt der Ladevorgang genau
einmal an. Das Modell wird vor der Schleife einmal angefasst, damit ein
Ladefehler sofort auffällt und nicht erst nach dem ersten Paar.

**Ratelimits.** SAIA wirft bei Überschreitung 429, drosselt aber nicht von
selbst. Dieses Skript liest nach jedem Aufruf die Header über
`saia.last_ratelimit()` und legt sich schlafen, bevor das Minutenfenster
leerläuft. Bei erschöpftem Tageskontingent bricht es ab, statt in eine
Fehlerserie zu laufen — die bereits geschriebenen Dateien bleiben
erhalten, ein späterer Aufruf macht dort weiter.

**Wiederaufnahme.** Vorhandene Zieldateien werden übersprungen. Nach einem
Abbruch (Ratelimit, Strg-C, Netzfehler) genügt derselbe Aufruf.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import konfig
import pipeline as P
from stufe2 import saia
from stufe3 import nli

# So viele Anfragen im Minutenfenster bleiben ungenutzt, bevor gewartet
# wird. Ein Puffer ist nötig, weil ein Paar mehrere Aufrufe auslöst und
# die Header immer den Stand *vor* dem nächsten Aufruf zeigen.
RESERVE_MINUTE = 2
# Nach Ablauf des Fensters plus etwas Luft für Uhrendrift.
WARTEN_MINUTE = 62
# Staffel bei 429 und 5xx, in dieser Reihenfolge:
#   1. Fehlschlag: so lange warten, wie der Server über `ratelimit-reset`
#      selbst ansagt (Sekunden bis zum Fensterwechsel). Das ist die
#      genaueste verfügbare Angabe; fehlt der Header, greift RESET_ERSATZ.
#   2. Fehlschlag: volle Fensterlänge abwarten (WARTEN_MINUTE).
#   3. Fehlschlag: aufgeben und das Paar lokal rechnen.
# Absicht dahinter: Ein einzelner Aussetzer kostet Sekunden statt einer
# Minute, ein anhaltendes Problem wird schnell an das lokale Modell
# übergeben, statt den Lauf minutenlang zu blockieren.
VERSUCHE = 3
RESET_ERSATZ = 15          # falls der Server keinen Reset-Wert schickt

# Lokale Entsprechung je Remote-Modell. Nur exakte Gegenstücke — dasselbe
# HuggingFace-Repo, also derselbe Vektorraum. Das ist die Bedingung, unter
# der ein Rückfall überhaupt zulässig ist: Embeddings aus zwei
# verschiedenen Modellen sind nicht vergleichbar, und eine Mischung
# innerhalb eines Paares würde alle Ähnlichkeiten unbrauchbar machen,
# ohne dass es irgendwo auffiele.
LOKALE_ENTSPRECHUNG = {
    "multilingual-e5-large-instruct": "local-multilingual-e5-large-instruct",
}


class Kontingent(Exception):
    """Tageskontingent erschöpft — geordnet abbrechen."""


def _int(wert) -> int | None:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None


def _reset_sekunden() -> int:
    """Wartezeit, die der Server selbst ansagt.

    `ratelimit-reset` steht laut GWDG-Doku in jeder Antwort und nennt die
    Sekunden bis zum Zurücksetzen des Zählers. Genauer als jede pauschale
    Pause — und bei einem kurzen Aussetzer meist nur wenige Sekunden.
    """
    rl = saia.last_ratelimit() or {}
    wert = _int(rl.get("ratelimit-reset"))
    if wert is None or wert < 0:
        return RESET_ERSATZ
    return min(max(wert, 1), WARTEN_MINUTE) + 3     # eine Sekunde Luft


def _drosseln(still: bool) -> None:
    """Vor dem nächsten Aufruf prüfen, ob noch Luft im Fenster ist."""
    rl = saia.last_ratelimit()
    if not rl:
        return
    tag = _int(rl.get("x-ratelimit-remaining-day"))
    if tag is not None and tag <= 0:
        raise Kontingent("Tageskontingent erschöpft.")
    minute = _int(rl.get("x-ratelimit-remaining-minute"))
    if minute is not None and minute <= RESERVE_MINUTE:
        pause = _reset_sekunden()
        if not still:
            print(f"    Minutenfenster fast leer ({minute} übrig) — "
                  f"warte {pause}s", flush=True)
        time.sleep(pause)


def _zeitmarke(woher: str, modell: str, anzahl: int, t_start: float,
               einzahl: str, mehrzahl: str) -> None:
    """Eine Zeile je Teilschritt: welches Backend, welches Modell, wie lang.

    Das Backend-Präfix ist der Punkt an der Sache. Dieselbe Satzliste
    kann in einem Lauf über die API gehen oder auf der CPU landen — bei
    `--emb local-…` von vornherein, beim Rückfall nach einem
    SAIA-Ausfall mitten im Lauf. Ohne das Präfix stehen zwei nicht
    vergleichbare Zahlen untereinander, und bis eben stand über beiden
    „SAIA fertig“.

    Die Angabe je Stück steht dabei, weil die Blockgrößen sich
    unterscheiden (`_BATCH_REMOTE` 64, `_BATCH_LOCAL` 16): Nur die
    Gesamtdauer zu vergleichen wäre irreführend.
    """
    dauer = time.time() - t_start
    print(f"    [{woher}] {modell}: {anzahl} {mehrzahl} in {dauer:.1f}s "
          f"({dauer / max(anzahl, 1) * 1000:.0f} ms/{einzahl})", flush=True)


def embed_fn_bauen(modell: str, api_key: str | None, still: bool,
                   zaehler: dict):
    """Embedding-Funktion mit Drosselung, Wiederholung und Zählwerk.

    Der Zähler ersetzt den, den `app.py` um den Aufruf legt — sonst
    fehlte in den erzeugten Dateien der Statistikblock, und die Ausgabe
    des Stapellaufs sähe anders aus als die aus dem Viewer.
    """
    # Einmal vorab statt je Aufruf — das Modell wechselt während eines
    # Laufs nicht.
    woher = saia.backend(modell)

    def embed_fn(texts, is_query=False):
        zaehler["n"] += len(texts)
        for versuch in range(1, VERSUCHE + 1):
            _drosseln(still)
            try:
                t_start = time.time()
                vecs = saia.embed(texts, modell, api_key, is_query)
                if not still:
                    _zeitmarke(woher, modell, len(texts), t_start,
                               "Text", "Texte")
                return vecs
            except saia.EmbedError as e:
                if versuch == VERSUCHE:
                    raise            # -> Paar wird lokal gerechnet
                if versuch == 1:
                    pause = _reset_sekunden()
                    grund = "laut ratelimit-reset"
                else:
                    pause = WARTEN_MINUTE
                    grund = "volles Fenster"
                print(f"    {e}\n    Versuch {versuch}/{VERSUCHE} "
                      f"gescheitert, warte {pause}s ({grund})", flush=True)
                time.sleep(pause)
        raise saia.EmbedError("Embedding nach mehreren Versuchen gescheitert.")
    return embed_fn


def paare_einlesen(muster: list[str]) -> list[tuple[str, dict]]:
    quellen: list[str] = []
    for m in muster:
        if os.path.isdir(m):
            quellen += sorted(glob.glob(os.path.join(m, "*.json")))
        else:
            quellen += sorted(glob.glob(m)) or [m]
    raus = []
    for pfad in quellen:
        try:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            if "article" not in daten or "transcript" not in daten:
                continue
            raus.append((pfad, daten))
        except (OSError, ValueError) as e:
            print(f"[!] {pfad}: {e}", file=sys.stderr)
    return raus


def main(argv: list[str]) -> int:
    ziel = None
    emb_modell = "multilingual-e5-large-instruct"
    nli_modell = "nli-mdeberta-2mil7"
    for schalter, ziel_var in (("-o", "ziel"), ("--emb", "emb"),
                               ("--nli", "nli")):
        if schalter in argv:
            k = argv.index(schalter)
            wert = argv[k + 1]
            del argv[k:k + 2]
            if ziel_var == "ziel":
                ziel = wert
            elif ziel_var == "emb":
                emb_modell = wert
            else:
                nli_modell = wert
    neu = "--neu" in argv
    still = "--still" in argv
    kein_fallback = "--kein-fallback" in argv
    if "--batch" in argv:
        k = argv.index("--batch")
        saia._BATCH_REMOTE = max(1, int(argv[k + 1]))
        del argv[k:k + 2]
    stufen = None
    if "--ohne" in argv:
        k = argv.index("--ohne")
        try:
            stufen = konfig.stufen_aus_kuerzeln(argv[k + 1].split(","))
        except KeyError as e:
            print(f"[!] {e.args[0]}", file=sys.stderr)
            return 1
        del argv[k:k + 2]
    muster = [a for a in argv if not a.startswith("-")]
    if not muster or not ziel:
        print(__doc__.strip())
        return 1

    api_key = os.environ.get("SAIA_API_KEY", "").strip() or None
    if emb_modell != "ohne" and emb_modell not in saia.LOCAL_MODELS \
            and not api_key:
        print("[!] SAIA_API_KEY nicht gesetzt. Entweder exportieren, ein "
              "lokales Modell wählen (--emb local-…) oder --emb ohne.",
              file=sys.stderr)
        return 1

    paare = paare_einlesen(muster)
    if not paare:
        print("Keine Lauf-Dateien gefunden.", file=sys.stderr)
        return 1
    os.makedirs(ziel, exist_ok=True)

    # Modelle einmal vorab laden, damit Fehler sofort auffallen statt
    # nach dem ersten Paar.
    zaehler = {"n": 0, "nli": 0}
    nli_fn = None
    if nli_modell != "ohne":
        print(f"Lade NLI-Modell {nli_modell} …", flush=True)
        try:
            nli.load_nli(nli_modell)
        except nli.NliError as e:
            print(f"[!] {e}", file=sys.stderr)
            return 2
        def nli_fn(pairs):
            zaehler["nli"] += len(pairs)
            t_start = time.time()
            probs = nli.classify(pairs, nli_modell)
            if not still:
                # NLI rechnet immer auf der CPU, es gibt kein API-Backend.
                _zeitmarke("lokal", nli_modell, len(pairs), t_start,
                           "Paar", "Paare")
            return probs

    embed_fn = None
    lokal_fn = None
    lokal_modell = None
    label = "ohne Embeddings"
    if emb_modell != "ohne":
        embed_fn = embed_fn_bauen(emb_modell, api_key, still, zaehler)
        label = emb_modell
        # Rückfallmodell vorab laden, nicht erst beim ersten Fehler —
        # sonst kommt zum Serverausfall noch ein Minutendownload dazu,
        # und zwar mitten im Lauf.
        lokal_modell = LOKALE_ENTSPRECHUNG.get(emb_modell)
        if lokal_modell and not kein_fallback:
            print(f"Lade Rückfallmodell {lokal_modell} …", flush=True)
            try:
                saia.load_local(lokal_modell)

                def lokal_fn(texts, is_query=False):
                    zaehler["n"] += len(texts)
                    t_start = time.time()
                    vecs = saia.embed(texts, lokal_modell, None, is_query)
                    if not still:
                        _zeitmarke(saia.backend(lokal_modell), lokal_modell,
                                   len(texts), t_start, "Text", "Texte")
                    return vecs
            except Exception as e:                   # noqa: BLE001
                print(f"    [!] Rückfall nicht verfügbar: {e}",
                      file=sys.stderr)
                lokal_fn = None

    fertig = uebersprungen = gescheitert = lokal_gerechnet = 0
    begonnen = time.time()
    for pfad, daten in paare:
        name = os.path.basename(pfad)
        zielpfad = os.path.join(ziel, name)
        if os.path.exists(zielpfad) and not neu \
                and os.path.abspath(zielpfad) != os.path.abspath(pfad):
            uebersprungen += 1
            continue
        print(f"[{fertig + uebersprungen + gescheitert + 1}/{len(paare)}] "
              f"{name} …", flush=True)
        t0 = time.time()
        zaehler["n"] = zaehler["nli"] = 0
        label_lauf = label
        try:
            ergebnis = P.align(daten["article"]["text"],
                               daten["transcript"]["text"],
                               embed_fn, label, nli_fn, stufen=stufen)
        except Kontingent as e:
            print(f"\n[!] {e} Bereits geschriebene Dateien bleiben erhalten; "
                  "denselben Aufruf später wiederholen.", file=sys.stderr)
            return 3
        except saia.EmbedError as e:
            if lokal_fn is None:
                print(f"    [!] gescheitert: {e}", file=sys.stderr)
                gescheitert += 1
                continue
            # Das GANZE Paar noch einmal, lokal. Nicht nur den gescheiterten
            # Aufruf: Ein Dokument, dessen Sätze teils remote und teils
            # lokal eingebettet sind, hätte zwar denselben Vektorraum, aber
            # der Zustand wäre nicht mehr nachvollziehbar. Ein Paar, eine
            # Quelle.
            print(f"    [!] {e}\n    SAIA gibt auf — rechne dieses Paar "
                  f"lokal mit {lokal_modell}", flush=True)
            zaehler["n"] = zaehler["nli"] = 0
            try:
                ergebnis = P.align(daten["article"]["text"],
                                   daten["transcript"]["text"],
                                   lokal_fn, lokal_modell, nli_fn,
                                   stufen=stufen)
                lokal_gerechnet += 1
                label_lauf = lokal_modell
            except Exception as e2:                  # noqa: BLE001
                print(f"    [!] auch lokal gescheitert: "
                      f"{type(e2).__name__}: {e2}", file=sys.stderr)
                gescheitert += 1
                continue
        except Exception as e:                       # noqa: BLE001
            print(f"    [!] gescheitert: {type(e).__name__}: {e}",
                  file=sys.stderr)
            gescheitert += 1
            continue
        # Titel aus der Vorlage übernehmen, falls vorhanden
        meta = ergebnis.setdefault("meta", {})
        if label_lauf != label:
            meta["modell"] = f"stufe0-3 · {label_lauf} (Rückfall)"
        alt_titel = (daten.get("meta") or {}).get("titel")
        if alt_titel:
            meta["titel"] = alt_titel
        meta["statistik"] = {
            "saetze": len(ergebnis["article"]["sentences"]),
            "claims": len(ergebnis["transcript"]["claims"]),
            "embeddings": zaehler["n"],
            "nli_paare": zaehler["nli"],
            "dauer_s": round(time.time() - t0, 1),
        }
        rl_jetzt = saia.last_ratelimit()
        if rl_jetzt:
            meta["ratelimit"] = rl_jetzt
        tmp = zielpfad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ergebnis, f, ensure_ascii=False)
        os.replace(tmp, zielpfad)                    # atomar ersetzen
        st = ergebnis.get("meta", {}).get("statistik", {})
        print(f"    {st.get('saetze', '?')} Sätze, {st.get('claims', '?')} "
              f"Claims, {time.time() - t0:.1f}s", flush=True)
        fertig += 1

    print(f"\n{fertig} neu berechnet, {uebersprungen} übersprungen, "
          f"{gescheitert} gescheitert — {time.time() - begonnen:.0f}s")
    if lokal_gerechnet:
        print(f"[!] {lokal_gerechnet} Paar(e) lokal gerechnet, weil SAIA "
              "ausfiel. Vergleichbar sind sie (gleiches Repo), aber für\n"
              "    eine saubere Messreihe würde ich sie mit --neu "
              "nachziehen, sobald der Dienst wieder läuft.")
    if uebersprungen and not neu:
        print("Übersprungene Dateien existierten bereits im Zielordner "
              "(--neu erzwingt die Neuberechnung).")
    rl = saia.last_ratelimit()
    if rl:
        print(f"Kontingent: {rl.get('x-ratelimit-remaining-minute', '?')}/min, "
              f"{rl.get('x-ratelimit-remaining-hour', '?')}/h, "
              f"{rl.get('x-ratelimit-remaining-day', '?')}/Tag")
    return 1 if gescheitert else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
