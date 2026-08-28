"""
Embeddings für das Alignment Lab — zwei Backends, eine Schnittstelle.

  remote  SAIA-API (GWDG / Academic Cloud / KISSKI), OpenAI-kompatibel
          POST https://chat-ai.academiccloud.de/v1/embeddings
          Modelle: multilingual-e5-large-instruct, qwen3-embedding-4b,
                   e5-mistral-7b-instruct

  local   sentence-transformers auf der CPU, ohne Netz und ohne Key
          Modell: local-multilingual-e5-large-instruct
                  -> intfloat/multilingual-e5-large-instruct (560M, ~2,2 GB)

Beide Backends nutzen dieselbe asymmetrische Konvention der E5-/Qwen-Autoren:
Anfragen (Claims) bekommen ein "Instruct:/Query:"-Präfix, Dokumente
(Artikelsätze) bleiben roh. Dadurch sind die Ergebnisse beider Backends
direkt miteinander vergleichbar.

Lokal einrichten (einmalig, ~2,2 GB Download beim ersten Lauf):

    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install "sentence-transformers>=3.0"

Zwei getrennte Aufrufe, weil --index-url den PyPI-Index ersetzt statt
ihn zu ergänzen — der PyTorch-Index kennt sonst kein sentence-transformers.
Der CPU-Wheel-Index spart ~2 GB CUDA-Ballast, den eine Iris Xe ohnehin
nicht nutzt.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------- Modelle

BASE_URL = "https://chat-ai.academiccloud.de/v1/embeddings"

REMOTE_MODELS = (
    "multilingual-e5-large-instruct",
    "qwen3-embedding-4b",
    "e5-mistral-7b-instruct",
)

# UI-Name -> HuggingFace-Repo
LOCAL_MODELS = {
    "local-multilingual-e5-large-instruct": "intfloat/multilingual-e5-large-instruct",
    "local-multilingual-e5-base": "intfloat/multilingual-e5-base",
    "local-bge-m3": "BAAI/bge-m3",
}

MODELS = REMOTE_MODELS + tuple(LOCAL_MODELS)

_TASK = ("Given a claim from a German audio transcript, retrieve the "
         "sentence from the original German news article that supports it")

# Blockgröße für Remote-Anfragen. Kleinere Blöcke bedeuten mehr Aufrufe
# (also mehr Ratelimit-Verbrauch), aber kürzere Einzelanfragen — und genau
# lange Anfragen erwischt ein überlastetes Gateway mit einem leeren 500er.
# Von `batch.py` per --batch überschreibbar, damit sich beides ohne
# Codeänderung gegeneinander testen lässt.
_BATCH_REMOTE = 64
_BATCH_LOCAL = 16          # RAM-schonend; auf i5/16 GB unkritisch
_TIMEOUT = 20


class EmbedError(RuntimeError):
    """Fehler in einem der beiden Embedding-Backends."""


SaiaError = EmbedError      # Rückwärtskompatibler Name


def _prep(texts: list[str], is_query: bool, style: str = "instruct") -> list[str]:
    """Präfixe nach Modellkonvention setzen."""
    if style == "e5-plain":                  # multilingual-e5-base/-large (ohne -instruct)
        p = "query: " if is_query else "passage: "
        return [p + t for t in texts]
    if style == "none":                      # bge-m3 braucht keine Präfixe
        return list(texts)
    if is_query:                             # *-instruct
        return [f"Instruct: {_TASK}\nQuery: {t}" for t in texts]
    return list(texts)


def _style_for(repo: str) -> str:
    low = repo.lower()
    if "bge-m3" in low:
        return "none"
    if "e5" in low and "instruct" not in low:
        return "e5-plain"
    return "instruct"


# ------------------------------------------------------------ Rate-Limits
#
# SAIA meldet Kontingent und Verbrauch in den Response-Headern jeder
# Anfrage (dokumentiert unter docs.hpc.gwdg.de/services/ai-services/saia),
# nicht über einen eigenen Endpunkt. Ein separater "Prüf"-Aufruf ist daher
# nichts anderes als eine reguläre, minimale Embedding-Anfrage — das
# Ergebnis wird verworfen, die Header werden ausgewertet.

_RATELIMIT_KEYS = (
    "x-ratelimit-limit-minute", "x-ratelimit-remaining-minute",
    "x-ratelimit-limit-hour", "x-ratelimit-remaining-hour",
    "x-ratelimit-limit-day", "x-ratelimit-remaining-day",
    # Sekundenfenster. SAIA setzt es zusätzlich zu Minute/Stunde/Tag durch
    # (beobachtet: 2/s) und meldet es getrennt. Es ist die Grenze, die bei
    # Stapelläufen zuerst reißt — das Minutenkontingent kann dabei satt im
    # Grünen stehen.
    "x-ratelimit-limit-second", "x-ratelimit-remaining-second",
    # Sekunden bis zum Zurücksetzen des Fensters. Der Server sagt damit
    # selbst an, wie lange zu warten ist — genauer als jede pauschale
    # Wartezeit und laut GWDG-Doku Teil der Standardantwort.
    "ratelimit-reset", "ratelimit-limit", "ratelimit-remaining",
    "retry-after",
)

_rl_lock = threading.Lock()
_rl_state: dict | None = None


def _capture_ratelimit(headers, model: str) -> None:
    global _rl_state
    werte = {k: headers.get(k) for k in _RATELIMIT_KEYS if headers.get(k) is not None}
    if not werte:
        return
    _limit_uebernehmen(werte.get("x-ratelimit-limit-second"))
    with _rl_lock:
        _rl_state = {"model": model, "checked_at": time.time(), **werte}


def last_ratelimit() -> dict | None:
    """Letzter bekannter Kontingentstand, oder None vor der ersten Anfrage.

    Prozessweit, nicht pro Nutzer — für den lokalen Einzelplatzbetrieb
    dieses Tools ausreichend, bei mehreren gleichzeitigen Nutzern am
    selben Server nicht aussagekräftig."""
    with _rl_lock:
        return dict(_rl_state) if _rl_state else None


# ---------------------------------------------------------------- Taktung
#
# Das Sekundenfenster ist die Grenze, die bei Stapelläufen zuerst reißt:
# `_embed_remote` zerlegt eine Satzliste in `_BATCH_REMOTE`-Blöcke und
# schickt sie ohne Pause hintereinander los. Bei 2 Anfragen/Sekunde reicht
# ein Artikel mit mehr als 16 Sätzen, damit der dritte Block im selben
# Sekundenfenster landet und 429 bekommt — während Minute, Stunde und Tag
# noch fast unberührt sind. Genau dieses Bild zeigen die Header eines
# solchen 429: remaining-second 0, remaining-minute 11.
#
# Getaktet wird deshalb hier, an der einzigen Stelle, durch die *jede*
# ausgehende Anfrage läuft — nicht beim Aufrufer. `batch.py` hat eine
# eigene Drossel, aber die greift nur einmal je Satzliste, nicht je Block;
# und `app.py` ruft `embed()` ohne jede Drossel auf. Eine Taktung im
# Aufrufer würde also beide Lücken offenlassen.

_LIMIT_SEKUNDE_STANDARD = 2.0     # bis die erste Antwort das echte Limit nennt
_TAKT_LUFT = 1.15                 # 15 % Sicherheitsabstand gegen Uhrendrift

_takt_lock = threading.Lock()
_letzte_anfrage = 0.0
_limit_sekunde = _LIMIT_SEKUNDE_STANDARD


def _limit_uebernehmen(wert) -> None:
    """Sekundenlimit aus den Headern übernehmen, statt es zu raten."""
    global _limit_sekunde
    try:
        limit = float(wert)
    except (TypeError, ValueError):
        return
    if limit > 0:
        with _takt_lock:
            _limit_sekunde = limit


def _takten() -> None:
    """Vor jeder Anfrage warten, bis der Mindestabstand erreicht ist.

    Der Schlaf liegt absichtlich *innerhalb* des Locks: Damit reserviert
    sich jeder Thread seinen Sendezeitpunkt der Reihe nach, und mehrere
    gleichzeitige Anfragen (app.py läuft im ThreadingHTTPServer) können
    sich nicht denselben Sekundenslot teilen. Der eigentliche HTTP-Aufruf
    findet danach ohne Lock statt, bleibt also parallelisierbar.
    """
    global _letzte_anfrage
    with _takt_lock:
        abstand = _TAKT_LUFT / max(_limit_sekunde, 0.1)
        warten = _letzte_anfrage + abstand - time.monotonic()
        if warten > 0:
            time.sleep(warten)
        _letzte_anfrage = time.monotonic()


def _takt_zuruecksetzen(sekunden: float) -> None:
    """Nach einem 429 den nächsten Sendezeitpunkt nach hinten schieben.

    `Retry-After` ist die Ansage des Servers selbst; sie zu ignorieren
    hieße, direkt in den nächsten 429 zu laufen.
    """
    global _letzte_anfrage
    if sekunden <= 0:
        return
    with _takt_lock:
        ziel = time.monotonic() + sekunden
        _letzte_anfrage = max(_letzte_anfrage, ziel)


# ------------------------------------------------------------ Backend: remote

def _request(payload: dict, api_key: str) -> dict:
    req = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        _takten()
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            _capture_ratelimit(r.headers, payload.get("model", ""))
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        _capture_ratelimit(e.headers, payload.get("model", ""))
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        hint = ""
        if e.code == 401:
            hint = (" — Key ungültig, noch nicht freigeschaltet oder mit "
                    "Leerzeichen eingefügt. Alternativ lokales Modell wählen.")
        elif e.code == 404:
            hint = " — Modellname prüfen (siehe /v1/models)."
        elif e.code == 429:
            # Welches Fenster gerissen ist, steht in den Headern. Das
            # Sekundenfenster mit auszugeben, spart die Rückfrage "aber im
            # Frontend war doch noch alles grün" — dort steht die Minute.
            frei_s = e.headers.get("x-ratelimit-remaining-second")
            frei_m = e.headers.get("x-ratelimit-remaining-minute")
            hint = (f" — Ratelimit erreicht (Sekundenfenster {frei_s}/"
                    f"{e.headers.get('x-ratelimit-limit-second')} frei, "
                    f"Minute {frei_m} frei).")
            try:
                _takt_zuruecksetzen(float(e.headers.get("retry-after") or 0))
            except (TypeError, ValueError):
                pass
        raise EmbedError(f"SAIA HTTP {e.code}{hint} {body}") from None
    except urllib.error.URLError as e:
        raise EmbedError(f"SAIA nicht erreichbar: {e.reason}") from None
    except TimeoutError:
        # Ein Lesetimeout ist KEIN URLError: urllib reicht die
        # socket.timeout des Sockets unverändert durch. Ohne diesen Zweig
        # entkommt sie als blanker TimeoutError an `_request` vorbei —
        # dann greift weder die Wiederholung in `batch.py` (die fängt
        # EmbedError) noch der Rückfall auf das lokale Modell, und der
        # ganze Lauf stirbt an einem einzelnen hängenden Aufruf.
        raise EmbedError(
            f"SAIA hat innerhalb von {_TIMEOUT}s nicht geantwortet "
            f"(Lesetimeout). Meist ein überlastetes Gateway — dieselbe "
            f"Ursache wie die leeren 500er."
        ) from None
    except OSError as e:
        # Verbindungsabbrüche (ConnectionReset, WinError 10054) kommen
        # ebenfalls roh durch. Gleiche Behandlung: als EmbedError melden,
        # damit Wiederholung und Rückfall greifen.
        raise EmbedError(f"SAIA-Verbindung abgebrochen: {e}") from None


def _embed_remote(texts: list[str], model: str, api_key: str | None,
                  is_query: bool) -> list[list[float]]:
    key = api_key or os.environ.get("SAIA_API_KEY", "")
    if not key:
        raise EmbedError("Kein API-Key: im Formular eintragen, SAIA_API_KEY "
                         "setzen oder ein lokales Modell wählen.")
    prepped = _prep(texts, is_query, _style_for(model))
    out: list[list[float]] = []
    schritt = max(1, _BATCH_REMOTE)
    for i in range(0, len(prepped), schritt):
        chunk = prepped[i:i + schritt]
        res = _request({"input": chunk, "model": model,
                        "encoding_format": "float"}, key.strip())
        data = res.get("data")
        if not data or len(data) != len(chunk):
            raise EmbedError("Unerwartete Antwortstruktur der Embeddings-API.")
        data.sort(key=lambda d: d.get("index", 0))
        out.extend(d["embedding"] for d in data)
    return out


# ------------------------------------------------------------- Backend: local

_cache: dict[str, object] = {}
_cache_lock = threading.Lock()


def load_local(model: str):
    """Lädt das lokale Modell einmalig und hält es im Speicher."""
    repo = LOCAL_MODELS.get(model)
    if repo is None:
        raise EmbedError(f"Unbekanntes lokales Modell: {model!r}")
    with _cache_lock:
        if repo in _cache:
            return _cache[repo]
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise EmbedError(
                "sentence-transformers fehlt. Installieren mit:\n"
                "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
                '  pip install "sentence-transformers>=3.0"'
            ) from None
        try:
            import torch
            # Auf i5-Kernen bringt Oversubscription nichts.
            torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
        except Exception:
            pass
        cache_dir = os.environ.get("ALIGNMENT_LAB_MODELS") or None
        print(f"[local] lade {repo} … (beim ersten Mal wird das Modell "
              f"heruntergeladen)", flush=True)
        try:
            m = SentenceTransformer(repo, device="cpu", cache_folder=cache_dir)
            # float16-Checkpoint + CPU = Emulation statt AVX-512 (Faktor 16,
            # siehe Kommentar in stufe3/nli.py). Ergebnis bleibt gleich.
            m = m.float()
        except Exception as e:
            raise EmbedError(
                f"Modell {repo} konnte nicht geladen werden: {e}. "
                "Bei fehlendem Netz vorher einmal online laden, danach läuft "
                "es aus dem lokalen Cache."
            ) from None
        m.max_seq_length = min(getattr(m, "max_seq_length", 512) or 512, 512)
        _cache[repo] = m
        print(f"[local] {repo} bereit", flush=True)
        return m


def _embed_local(texts: list[str], model: str,
                 is_query: bool) -> list[list[float]]:
    m = load_local(model)
    prepped = _prep(texts, is_query, _style_for(LOCAL_MODELS[model]))
    try:
        vecs = m.encode(prepped, batch_size=_BATCH_LOCAL,
                        normalize_embeddings=True,
                        convert_to_numpy=True, show_progress_bar=False)
    except Exception as e:
        raise EmbedError(f"Lokale Berechnung fehlgeschlagen: {e}") from None
    return [[float(x) for x in v] for v in vecs]


# ------------------------------------------------------------------ Dispatch

def backend(model: str) -> str:
    """Welchen Weg `embed` für dieses Modell nimmt: 'api' oder 'lokal'.

    Dieselbe Fallunterscheidung wie in `embed`, nur öffentlich — damit
    Aufrufer ihre Zeitmarken beschriften können, ohne LOCAL_MODELS selbst
    zu kennen. Nötig ist das, weil beide Wege dieselbe Funktion mit
    derselben Signatur bedienen: Ob eine Sekundenzahl von der API oder
    von der CPU stammt, steht sonst nirgends.
    """
    if model in LOCAL_MODELS:
        return "lokal"
    if model in REMOTE_MODELS:
        return "api"
    return "unbekannt"


def embed(texts: list[str], model: str, api_key: str | None = None,
          is_query: bool = False) -> list[list[float]]:
    """Embeddings für eine Textliste, in Eingabereihenfolge.

    model bestimmt das Backend: Namen mit Präfix 'local-' rechnen auf der
    CPU, alle anderen gehen an die SAIA-API.
    """
    if not texts:
        return []
    if model in LOCAL_MODELS:
        return _embed_local(texts, model, is_query)
    if model in REMOTE_MODELS:
        return _embed_remote(texts, model, api_key, is_query)
    raise EmbedError(f"Unbekanntes Embedding-Modell: {model!r}")


if __name__ == "__main__":          # Schnelltest:  python3 saia.py
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "local-multilingual-e5-large-instruct"
    docs = ["Die Stadt investiert 5,3 Millionen Euro in die Sanierung ihrer Schulen.",
            "Der Verkehr wird während der Bauzeit über die Ostumgehung geführt."]
    q = ["Fünf Komma drei Millionen Euro fließen in die Schulen."]
    d = embed(docs, name, is_query=False)
    qv = embed(q, name, is_query=True)
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    print(f"{name}: dim={len(d[0])}")
    for i, s in enumerate(docs):
        print(f"  cos={dot(qv[0], d[i]):+.4f}  {s[:60]}")
