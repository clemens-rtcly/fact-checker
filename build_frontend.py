"""Erzeugt static/index.html aus dem Original-Split-View-Prototyp.

Chirurgische Patches, keine Neuschreibung:
  1  Titel + Brandmark
  2  Eingabe-Toggle in der Topbar
  3  Eingabe-Panel (Artikel/Transkript, Modellwahl, API-Key, Analysieren)
  4  Zusätzliches CSS im Brand-System
  5  DATA-Block -> leerer Zustand + Demo-Texte als Konstanten
  6  has-conflict nur noch bei echtem Zahlkonflikt (nicht bei zahl_unbelegt)
  7  Befund-Chip "Zahl unbelegt"
  8  Inspector: Entitäten-Status "unbelegt" + Score-Debug-Spalte
  9  Tastatur-Guard auch für INPUT/SELECT
 10  Eingabe-Logik (fetch /api/align, localStorage, Strg+Enter)
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src = (ROOT / "_original_viewer.html").read_text(encoding="utf-8")

m = re.search(r"const DATA = (\{.*?\n\});\n</script>", src, re.S)
DATA = json.loads(m.group(1))
demo_article = DATA["article"]["text"]
demo_transcript = DATA["transcript"]["text"]


def patch(old, new, count=1):
    global src
    assert src.count(old) == count, f"Anker nicht eindeutig ({src.count(old)}x): {old[:60]!r}"
    src = src.replace(old, new, count)


# 1 ------------------------------------------------------------------ Titel
patch("<title>Claim-Alignment — Split View</title>",
      "<title>Articly Alignment Lab — Stufe 0–2</title>")
patch('<div class="brandmark"><b>Alignment</b><span>Prototyp v0.1</span></div>',
      '<div class="brandmark"><b>Articly</b><span>Alignment Lab · Stufe 0–2</span></div>')

# 2 --------------------------------------------------- Eingabe-Toggle Topbar
patch('''  <div class="ctrl-group">
    <span class="ctrl-label">Markieren</span>''',
      '''  <div class="ctrl-group">
    <span class="ctrl-label">Analyse</span>
    <div class="ctrl"><button id="btn-intake" aria-pressed="true">Eingabe</button></div>
  </div>

  <div class="ctrl-group">
    <span class="ctrl-label">Markieren</span>''')

# 3 --------------------------------------------------------- Eingabe-Panel
patch('''</header>

<div class="stage" id="stage">''',
      '''</header>

<section class="intake" id="intake">
  <div class="intake-grid">
    <label class="intake-field">
      <span class="intake-k">Originalartikel</span>
      <textarea id="in-article" class="ta ta--serif" spellcheck="false"
        placeholder="Artikeltext einfügen. Erster Absatz = Überschrift, zweiter = Vorspann, Leerzeilen trennen Absätze."></textarea>
    </label>
    <label class="intake-field">
      <span class="intake-k">Transkript</span>
      <textarea id="in-transcript" class="ta" spellcheck="false"
        placeholder="Transkripttext einfügen. Jeder Satz wird ein Claim."></textarea>
    </label>
  </div>
  <div class="intake-row">
    <span class="ctrl-label">Embeddings</span>
    <select id="model" class="sel">
      <optgroup label="SAIA · Academic Cloud (API-Key)">
        <option value="multilingual-e5-large-instruct">multilingual-e5-large-instruct</option>
        <option value="qwen3-embedding-4b">qwen3-embedding-4b</option>
        <option value="e5-mistral-7b-instruct">e5-mistral-7b-instruct</option>
      </optgroup>
      <optgroup label="Lokal · CPU (kein Key)">
        <option value="local-multilingual-e5-large-instruct">local · multilingual-e5-large-instruct</option>
        <option value="local-multilingual-e5-base">local · multilingual-e5-base (klein)</option>
        <option value="local-bge-m3">local · bge-m3</option>
      </optgroup>
      <option value="">ohne — nur Stufe 0+1 (offline)</option>
    </select>
    <input id="apikey" class="key" type="password" autocomplete="off"
      placeholder="SAIA-API-Key (bleibt lokal)">
    <button class="btn btn--primary" id="run">Analysieren</button>
    <button class="btn" id="load-demo">Beispiel laden</button>
    <button class="btn" id="clear-all">Leeren</button>
    <span class="intake-status" id="status">Strg+Enter startet die Analyse</span>
  </div>
</section>

<div class="stage" id="stage">''')

# 4 ------------------------------------------------------------------- CSS
patch("</head>", """<style>
/* ------------------------------------------------------------ Eingabe */
.intake{flex:0 0 auto;background:var(--ground);border-bottom:1px solid var(--rule-strong);
  padding:13px 18px 12px}
.intake[hidden]{display:none}
.intake-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.intake-field{display:flex;flex-direction:column;gap:6px;min-width:0}
.intake-k{font-family:var(--cond);font-size:12px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink-faint)}
.ta{width:100%;min-height:168px;resize:vertical;border:1px solid var(--rule-strong);
  border-radius:2px;background:var(--paper);color:var(--ink);padding:11px 13px;
  font-family:var(--sans);font-size:14px;line-height:1.55}
.ta--serif{font-family:var(--serif);font-size:15px}
.ta:focus,.sel:focus,.key:focus{outline:2px solid var(--ink);outline-offset:-1px}
.intake-row{display:flex;align-items:center;gap:10px;margin-top:11px;flex-wrap:wrap}
.sel,.key{border:1px solid var(--rule-strong);border-radius:2px;background:var(--paper);
  color:var(--ink);padding:7px 10px;font-family:var(--cond);font-size:13.5px;
  letter-spacing:.04em}
.key{flex:0 1 250px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.intake-status{font-family:var(--cond);font-size:12.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-faint);margin-left:auto}
.intake-status.err{color:var(--conflict);text-transform:none;letter-spacing:.02em}
.intake-status.busy{color:var(--ink-soft)}
.ent .warn{color:#B98A1F;font-weight:600}
.insp-scores{font-family:var(--cond);font-size:13px;letter-spacing:.05em;
  color:var(--ink-soft);white-space:nowrap}
@media (max-width:900px){.intake-grid{grid-template-columns:1fr}.intake-status{margin-left:0;flex-basis:100%}}
</style>
</head>""")

# 5 ----------------------------------------------- DATA-Block ersetzen
empty = ('{"meta":{"titel":"","quelle":"","modell":""},'
         '"article":{"text":"","sentences":[]},'
         '"transcript":{"text":"","claims":[]}}')
replacement = (
    "const DEMO_ARTICLE = " + json.dumps(demo_article, ensure_ascii=False) + ";\n"
    "const DEMO_TRANSCRIPT = " + json.dumps(demo_transcript, ensure_ascii=False) + ";\n"
    "const DATA = " + empty + ";\n</script>")
src = re.sub(r"const DATA = \{.*?\n\};\n</script>", lambda _: replacement,
             src, count=1, flags=re.S)

# 6 ------------------------------- has-conflict nur bei echtem Zahlkonflikt
patch("if (lead.flags && lead.flags.length) cls.push('has-conflict');",
      "if ((lead.flags||[]).includes('zahlkonflikt')) cls.push('has-conflict');")
patch("""      const conflict = (c.flags||[]).length > 0;
      const cls = act.get(hit);""",
      """      const conflict = (c.flags||[]).includes('zahlkonflikt');
      const cls = act.get(hit);""")
patch("""  const c = claimById.get(id);
  const conflict = (c.flags||[]).length > 0;""",
      """  const c = claimById.get(id);
  const conflict = (c.flags||[]).includes('zahlkonflikt');""")
patch("const stroke = (c.flags||[]).length ? 'var(--conflict)'",
      "const stroke = (c.flags||[]).includes('zahlkonflikt') ? 'var(--conflict)'")

# 7 --------------------------------------------------- Chip "Zahl unbelegt"
patch("""    { key:'ohnequelle', label:'ohne Quelle',""",
      """    { key:'unbelegt', label:'Zahl unbelegt',
      ids: cs.filter(c => (c.flags||[]).includes('zahl_unbelegt')).map(c=>c.id) },
    { key:'ohnequelle', label:'ohne Quelle',""")

# 8 ------------------------------ Inspector: unbelegt-Status + Score-Spalte
patch("""  const ents = (c.entities||[]).map(e => e.status === 'konflikt'
    ? `<div class="ent"><span class="bad">≠</span><span>${e.surface} <code>→ ${e.norm}</code></span>
       <span class="bad">Artikel: ${e.quelle_surface} <code>→ ${e.quelle_norm}</code></span></div>`
    : `<div class="ent"><span class="ok">=</span><span>${e.surface} <code>→ ${e.norm}</code></span></div>`
  ).join('') || '<div class="ent" style="color:#7F9A9C">keine</div>';""",
      """  const ents = (c.entities||[]).map(e => {
    if (e.status === 'konflikt')
      return `<div class="ent"><span class="bad">≠</span><span>${e.surface} <code>→ ${e.norm}</code></span>
       <span class="bad">Artikel: ${e.quelle_surface} <code>→ ${e.quelle_norm}</code></span></div>`;
    if (e.status === 'unbelegt')
      return `<div class="ent"><span class="warn">?</span><span>${e.surface} <code>→ ${e.norm}</code></span>
       <span class="warn">nicht im Artikel gefunden</span></div>`;
    return `<div class="ent"><span class="ok">=</span><span>${e.surface} <code>→ ${e.norm}</code></span></div>`;
  }).join('') || '<div class="ent" style="color:#7F9A9C">keine</div>';""")

patch("""      ${meter('Margin zu Top-2', c.margin, c.margin < .10)}
      <div class="insp-col" style="flex:1 1 260px">
        <div class="insp-k">Entitäten (normalisiert)</div>${ents}
      </div>""",
      """      ${meter('Margin zu Top-2', c.margin, c.margin < .10)}
      ${c.scores ? (f => `<div class="insp-col">
        <div class="insp-k">Scores</div>
        <div class="insp-scores">top ${f(c.scores.top)} · lex ${f(c.scores.lex)} · emb ${f(c.scores.emb)} · anker ${f(c.scores.anchor)}</div>
      </div>`)(v => v == null ? '—' : v.toFixed(2).replace('.', ',')) : ''}
      <div class="insp-col" style="flex:1 1 260px">
        <div class="insp-k">Entitäten (normalisiert)</div>${ents}
      </div>""")

# 9 --------------------------------------------- Tastatur-Guard erweitern
patch("  if (e.target.tagName === 'TEXTAREA') return;",
      "  if (/^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName)) return;")

# 10 ------------------------------------------------------- Eingabe-Logik
patch("""build();
if (document.fonts && document.fonts.ready)""",
      """/* =====================================================================
   Eingabe & Analyse (Stufe 0–2 über /api/align)
   ===================================================================== */
const intake = $('#intake'), stat = $('#status'), btnIntake = $('#btn-intake');
const LS = 'articly-alignment-lab';

(function restore(){
  let s = {};
  try{ s = JSON.parse(localStorage.getItem(LS) || '{}'); }catch(_){}
  $('#in-article').value    = s.article    ?? '';
  $('#in-transcript').value = s.transcript ?? '';
  if (s.model !== undefined) $('#model').value = s.model;
  if (s.key) $('#apikey').value = s.key;
})();

function persist(){
  localStorage.setItem(LS, JSON.stringify({
    article: $('#in-article').value, transcript: $('#in-transcript').value,
    model: $('#model').value, key: $('#apikey').value,
  }));
}

function setIntake(open){
  if (open) intake.removeAttribute('hidden'); else intake.setAttribute('hidden','');
  btnIntake.setAttribute('aria-pressed', String(open));
  buildRail(); redraw();
}
btnIntake.onclick = () => setIntake(intake.hasAttribute('hidden'));

$('#load-demo').onclick = () => {
  $('#in-article').value = DEMO_ARTICLE;
  $('#in-transcript').value = DEMO_TRANSCRIPT;
  persist();
  stat.className = 'intake-status';
  stat.textContent = 'Beispiel ersetzt beide Felder — Analysieren starten';
};

$('#clear-all').onclick = () => {
  $('#in-article').value = '';
  $('#in-transcript').value = '';
  persist();
  $('#in-article').focus();
  stat.className = 'intake-status';
  stat.textContent = 'Felder geleert';
};

function syncKeyField(){
  const m = $('#model').value;
  const local = !m || m.startsWith('local-');
  $('#apikey').disabled = local;
  $('#apikey').style.opacity = local ? .4 : 1;
  $('#apikey').placeholder = local ? 'kein Key nötig' : 'SAIA-API-Key (bleibt lokal)';
}
$('#model').addEventListener('change', () => { syncKeyField(); persist(); });
syncKeyField();

async function run(){
  const article = $('#in-article').value.trim();
  const transcript = $('#in-transcript').value.trim();
  if (!article || !transcript){
    stat.className = 'intake-status err';
    stat.textContent = 'Artikel und Transkript werden beide benötigt.';
    return;
  }
  persist();
  const model = $('#model').value;
  stat.className = 'intake-status busy';
  stat.textContent = !model ? 'Analysiere · Stufe 0+1 offline …'
    : model.startsWith('local-')
      ? `Analysiere · ${model.slice(6)} auf der CPU … (erster Lauf lädt das Modell)`
      : `Analysiere · ${model} …`;
  $('#run').disabled = true;
  try{
    const r = await fetch('/api/align', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({article, transcript, model, api_key: $('#apikey').value}),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
    data = j; pins.clear(); hoverClaim = null; revSentence = null;
    build();
    const st = (j.meta && j.meta.statistik) || {};
    stat.className = 'intake-status';
    stat.textContent = `${st.saetze} Sätze · ${st.claims} Claims` +
      (st.embeddings ? ` · ${st.embeddings} Embeddings` : ' · offline') +
      ` · ${st.dauer_s} s`;
    setIntake(false);
  }catch(err){
    stat.className = 'intake-status err';
    stat.textContent = String(err.message || err);
  }finally{
    $('#run').disabled = false;
  }
}
$('#run').onclick = run;
for (const el of [$('#in-article'), $('#in-transcript')])
  el.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') run();
  });

build();
if (document.fonts && document.fonts.ready)""")

out = ROOT / "static" / "index.html"
out.write_text(src, encoding="utf-8")
print(f"geschrieben: {out} ({len(src)} Zeichen)")
