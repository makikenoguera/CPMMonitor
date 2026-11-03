#!/usr/bin/env python3
"""
Genera un visor HTML de los registros de fingerprints.
Uso: python3 generar_visor.py [--db fingerprints.db] [--out visor.html]
"""

import sqlite3, json, argparse, os, datetime
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db',  default='fingerprints.db')
    ap.add_argument('--out', default='visor_fingerprints.html')
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            filepath,
            filename,
            artista_final  AS artista,
            titulo_final   AS titulo,
            isrc,
            isrc_fuente    AS fuente_isrc,
            isrc_estado    AS estado_isrc,
            procesado,
            duration_seg,
            acoustid_score AS score,
            error,
            afiliado
        FROM tracks
        ORDER BY artista COLLATE NOCASE, titulo COLLATE NOCASE
    """)
    rows = [dict(r) for r in cur.fetchall()]

    # Stats
    total     = len(rows)
    procesado = sum(1 for r in rows if r['procesado'])
    pendiente = total - procesado
    con_isrc  = sum(1 for r in rows if r['isrc'])
    pct_isrc  = round(con_isrc / total * 100, 1) if total else 0

    # Extract unique folders for filter
    folders = sorted(set(
        Path(r['filepath']).parent.name for r in rows
    ))

    conn.close()

    # Serialize data as JSON embedded in HTML
    data_json   = json.dumps(rows,    ensure_ascii=False)
    folder_json = json.dumps(folders, ensure_ascii=False)
    gen_time    = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SumarteRed — Fingerprints</title>
<style>
  :root {{
    --bg:#0f1117; --surface:#1a1d26; --card:#22263a;
    --accent:#7c6af7; --accent2:#4ecdab;
    --text:#e8e8f0; --muted:#888aa0; --border:#2e3248;
    --red:#f0506e; --green:#4ecdab; --yellow:#f5a623;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
  header{{background:var(--surface);border-bottom:1px solid var(--border);
          padding:18px 24px;display:flex;align-items:center;gap:16px}}
  header h1{{font-size:20px;font-weight:700;letter-spacing:.5px}}
  header span{{color:var(--muted);font-size:12px}}
  .header-right{{margin-left:auto;display:flex;align-items:center;gap:10px}}
  .btn-reload{{background:var(--card);border:1px solid var(--border);
               color:var(--text);border-radius:8px;padding:8px 16px;font-size:13px;
               cursor:pointer;display:flex;align-items:center;gap:6px;transition:all .2s}}
  .btn-reload:hover{{border-color:var(--accent);color:var(--accent)}}
  .btn-reload.spinning svg{{animation:spin .7s linear infinite}}
  @keyframes spin{{to{{transform:rotate(360deg)}}}}
  .auto-badge{{background:var(--card);border:1px solid var(--border);border-radius:8px;
               padding:6px 12px;font-size:12px;color:var(--muted);display:flex;
               align-items:center;gap:6px;cursor:pointer;transition:all .2s;white-space:nowrap}}
  .auto-badge:hover{{border-color:var(--accent2);color:var(--text)}}
  .auto-badge .dot{{width:7px;height:7px;border-radius:50%;background:var(--green);
                    flex-shrink:0;transition:background .3s}}
  .auto-badge.paused .dot{{background:var(--yellow)}}
  .ring{{position:relative;width:18px;height:18px;flex-shrink:0}}
  .ring svg{{position:absolute;top:0;left:0;transform:rotate(-90deg)}}
  .ring .track{{stroke:var(--border)}}
  .ring .fill{{stroke:var(--accent2);stroke-dasharray:50.3;stroke-dashoffset:50.3;
               transition:stroke-dashoffset .9s linear}}
  .stats{{display:flex;gap:16px;padding:16px 24px;flex-wrap:wrap}}
  .stat{{background:var(--card);border:1px solid var(--border);border-radius:10px;
         padding:14px 20px;min-width:140px;flex:1}}
  .stat .val{{font-size:28px;font-weight:700;color:var(--accent)}}
  .stat .lbl{{color:var(--muted);font-size:11px;margin-top:4px}}
  .bar-wrap{{background:var(--border);border-radius:999px;height:6px;margin-top:8px}}
  .bar{{background:linear-gradient(90deg,var(--accent),var(--accent2));
        height:6px;border-radius:999px;transition:width .6s}}
  .controls{{padding:0 24px 12px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
  input,select{{background:var(--card);border:1px solid var(--border);color:var(--text);
                border-radius:8px;padding:8px 12px;font-size:13px;outline:none}}
  input{{flex:1;min-width:200px}}
  input:focus,select:focus{{border-color:var(--accent)}}
  select option{{background:var(--surface)}}
  .count-label{{color:var(--muted);font-size:12px;margin-left:auto}}
  .table-wrap{{overflow-x:auto;padding:0 24px 40px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:var(--card);color:var(--muted);font-weight:600;text-align:left;
      padding:10px 12px;border-bottom:2px solid var(--border);cursor:pointer;
      white-space:nowrap;user-select:none;position:sticky;top:0}}
  th:hover{{color:var(--text)}}
  th .sort-icon{{opacity:.4;margin-left:4px}}
  th.asc .sort-icon::after{{content:'▲'}}
  th.desc .sort-icon::after{{content:'▼'}}
  th:not(.asc):not(.desc) .sort-icon::after{{content:'⇅'}}
  tr{{border-bottom:1px solid var(--border);transition:background .15s}}
  tr:hover td{{background:rgba(124,106,247,.07)}}
  td{{padding:9px 12px;vertical-align:middle}}
  td.file{{color:var(--muted);font-size:11px;max-width:260px;
           overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  td.artista{{font-weight:600;color:var(--text)}}
  td.titulo{{color:#c8cadf}}
  td.isrc{{font-family:monospace;font-size:12px;color:var(--accent2)}}
  td.isrc.empty{{color:var(--border)}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:999px;
           font-size:11px;font-weight:600;letter-spacing:.3px}}
  .badge.ok{{background:rgba(78,205,171,.18);color:var(--green)}}
  .badge.pend{{background:rgba(245,166,35,.12);color:var(--yellow)}}
  .badge.err{{background:rgba(240,80,110,.15);color:var(--red)}}
  .badge.sin{{background:rgba(255,255,255,.06);color:var(--muted)}}
  td.dur{{color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}}
  td.score{{color:var(--muted);text-align:right;font-size:12px}}
  .no-results{{text-align:center;padding:48px;color:var(--muted)}}
  footer{{text-align:center;color:var(--muted);font-size:11px;padding:16px;
          border-top:1px solid var(--border)}}
</style>
</head>
<body>

<header>
  <div>
    <h1>🎵 SumarteRed — Fingerprints</h1>
    <span id="gen-time">Generado {gen_time} · {total:,} tracks · fingerprints.db</span>
  </div>
  <div class="header-right">
    <div class="auto-badge" id="auto-badge" onclick="toggleAuto()" title="Clic para pausar/reanudar">
      <span class="dot" id="auto-dot"></span>
      <div class="ring">
        <svg width="18" height="18" viewBox="0 0 18 18">
          <circle class="track" cx="9" cy="9" r="8" fill="none" stroke-width="2"/>
          <circle class="fill"  cx="9" cy="9" r="8" fill="none" stroke-width="2" id="ring-fill"/>
        </svg>
      </div>
      <span id="auto-label">5:00</span>
    </div>
    <button class="btn-reload" id="btn-reload" onclick="recargar()">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
        <path d="M3.51 9a9 9 0 0 1 14.36-3.36L23 10M1 14l5.13 4.36A9 9 0 0 0 20.49 15"/>
      </svg>
      Actualizar
    </button>
  </div>
</header>

<div class="stats">
  <div class="stat">
    <div class="val">{total:,}</div>
    <div class="lbl">Total tracks</div>
    <div class="bar-wrap"><div class="bar" style="width:100%"></div></div>
  </div>
  <div class="stat">
    <div class="val" id="s-proc">{procesado:,}</div>
    <div class="lbl">Procesados</div>
    <div class="bar-wrap"><div class="bar" style="width:{round(procesado/total*100,1) if total else 0}%"></div></div>
  </div>
  <div class="stat">
    <div class="val" style="color:var(--yellow)">{pendiente:,}</div>
    <div class="lbl">Pendientes</div>
    <div class="bar-wrap"><div class="bar" style="width:{round(pendiente/total*100,1) if total else 0}%;background:var(--yellow)"></div></div>
  </div>
  <div class="stat">
    <div class="val" style="color:var(--green)">{con_isrc}</div>
    <div class="lbl">Con ISRC · {pct_isrc}%</div>
    <div class="bar-wrap"><div class="bar" style="width:{pct_isrc}%;background:var(--green)"></div></div>
  </div>
</div>

<div class="controls">
  <input type="search" id="q" placeholder="🔍  Buscar artista, título, ISRC, archivo…">
  <select id="filtro-estado">
    <option value="">Todos los estados</option>
    <option value="procesado">Procesados</option>
    <option value="pendiente">Pendientes</option>
    <option value="con_isrc">Con ISRC</option>
    <option value="sin_isrc">Sin ISRC</option>
    <option value="error">Con error</option>
  </select>
  <select id="filtro-carpeta">
    <option value="">Todas las carpetas</option>
  </select>
  <span class="count-label" id="count-label"></span>
</div>

<div class="table-wrap">
<table id="tbl">
  <thead>
    <tr>
      <th data-col="artista">Artista<span class="sort-icon"></span></th>
      <th data-col="titulo">Título<span class="sort-icon"></span></th>
      <th data-col="isrc">ISRC<span class="sort-icon"></span></th>
      <th data-col="fuente_isrc">Fuente<span class="sort-icon"></span></th>
      <th data-col="procesado">Estado<span class="sort-icon"></span></th>
      <th data-col="duration_seg">Duración<span class="sort-icon"></span></th>
      <th data-col="score">Score<span class="sort-icon"></span></th>
      <th data-col="filepath">Archivo<span class="sort-icon"></span></th>
    </tr>
  </thead>
  <tbody id="tbody"></tbody>
</table>
<div class="no-results" id="no-results" style="display:none">Sin resultados para esta búsqueda.</div>
</div>

<footer>SumarteRed Music Library · {total:,} tracks · Exportado {gen_time}</footer>

<script>
const RAW = {data_json};
const FOLDERS = {folder_json};

// Populate folder filter
const folderSel = document.getElementById('filtro-carpeta');
FOLDERS.forEach(f => {{
  const o = document.createElement('option'); o.value = f; o.textContent = f;
  folderSel.appendChild(o);
}});

let sortCol = 'artista', sortDir = 1;
let filtered = [...RAW];

function fmt_dur(s) {{
  if (!s) return '—';
  const m = Math.floor(s/60), sec = Math.round(s%60);
  return m+':'+(sec<10?'0':'')+sec;
}}

function badge(row) {{
  if (row.error)    return '<span class="badge err">Error</span>';
  if (row.procesado && row.isrc) return '<span class="badge ok">✓ ISRC</span>';
  if (row.procesado) return '<span class="badge ok">Procesado</span>';
  return '<span class="badge pend">Pendiente</span>';
}}

function getFolder(fp) {{
  const parts = fp.split('/');
  return parts[parts.length-2] || '';
}}

function render() {{
  const q      = document.getElementById('q').value.toLowerCase();
  const estado = document.getElementById('filtro-estado').value;
  const folder = document.getElementById('filtro-carpeta').value;

  filtered = RAW.filter(r => {{
    if (q) {{
      const hay = (r.artista||'') + (r.titulo||'') + (r.isrc||'') + (r.filepath||'');
      if (!hay.toLowerCase().includes(q)) return false;
    }}
    if (folder && getFolder(r.filepath) !== folder) return false;
    if (estado === 'procesado' && !r.procesado) return false;
    if (estado === 'pendiente' && r.procesado)  return false;
    if (estado === 'con_isrc'  && !r.isrc)       return false;
    if (estado === 'sin_isrc'  && r.isrc)        return false;
    if (estado === 'error'     && !r.error)      return false;
    return true;
  }});

  filtered.sort((a,b) => {{
    let av = a[sortCol]??'', bv = b[sortCol]??'';
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  }});

  const PAGE = 500;
  const shown = filtered.slice(0, PAGE);
  document.getElementById('count-label').textContent =
    filtered.length === RAW.length
      ? `${{RAW.length.toLocaleString()}} registros`
      : `${{filtered.length.toLocaleString()}} de ${{RAW.length.toLocaleString()}}`;

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = shown.map(r => {{
    const isrc_cls = r.isrc ? 'isrc' : 'isrc empty';
    const fname = r.filepath.split('/').pop();
    return `<tr>
      <td class="artista">${{r.artista||'—'}}</td>
      <td class="titulo">${{r.titulo||'—'}}</td>
      <td class="${{isrc_cls}}">${{r.isrc||'—'}}</td>
      <td><span class="badge sin">${{r.fuente_isrc||'—'}}</span></td>
      <td>${{badge(r)}}</td>
      <td class="dur">${{fmt_dur(r.duration_seg)}}</td>
      <td class="score">${{r.score ? r.score.toFixed(2) : '—'}}</td>
      <td class="file" title="${{r.filepath}}">${{fname}}</td>
    </tr>`;
  }}).join('');

  document.getElementById('no-results').style.display = filtered.length ? 'none' : 'block';

  if (filtered.length > PAGE) {{
    const note = document.createElement('tr');
    note.innerHTML = `<td colspan="8" style="text-align:center;color:var(--muted);padding:12px">
      Mostrando primeros ${{PAGE}} de ${{filtered.length}} resultados. Usa el buscador para filtrar más.
    </td>`;
    tbody.appendChild(note);
  }}
}}

// Sort on header click
document.querySelectorAll('th[data-col]').forEach(th => {{
  th.addEventListener('click', () => {{
    const col = th.dataset.col;
    if (sortCol === col) sortDir *= -1; else {{ sortCol = col; sortDir = 1; }}
    document.querySelectorAll('th').forEach(t => t.classList.remove('asc','desc'));
    th.classList.add(sortDir===1?'asc':'desc');
    render();
  }});
}});

document.getElementById('q').addEventListener('input', render);
document.getElementById('filtro-estado').addEventListener('change', render);
document.getElementById('filtro-carpeta').addEventListener('change', render);

render();

// ── Auto-refresh ──────────────────────────────────────────────
const INTERVAL = 300; // segundos (5 minutos)
let countdown  = INTERVAL;
let autoPaused = false;
let ticker;

const ringFill  = document.getElementById('ring-fill');
const autoLabel = document.getElementById('auto-label');
const autoBadge = document.getElementById('auto-badge');
const autoDot   = document.getElementById('auto-dot');
const CIRCUM    = 50.3; // 2π × r(8)

function fmtCountdown(s) {{
  const m = Math.floor(s / 60), sec = s % 60;
  return m + ':' + String(sec).padStart(2, '0');
}}

function updateRing() {{
  const offset = CIRCUM * (countdown / INTERVAL); // lleno al inicio, vacío al final
  ringFill.style.strokeDashoffset = offset;
}}

function startTicker() {{
  clearInterval(ticker);
  ticker = setInterval(() => {{
    if (autoPaused) return;
    countdown--;
    autoLabel.textContent = fmtCountdown(countdown);
    updateRing();
    if (countdown <= 0) {{
      countdown = INTERVAL;
      updateRing();
      recargar();
    }}
  }}, 1000);
}}

function toggleAuto() {{
  autoPaused = !autoPaused;
  autoBadge.classList.toggle('paused', autoPaused);
  autoLabel.textContent = autoPaused ? 'pausado' : fmtCountdown(countdown);
}}

function recargar() {{
  const btn = document.getElementById('btn-reload');
  btn.classList.add('spinning');
  autoDot.style.background = 'var(--accent)';
  countdown = INTERVAL;
  updateRing();
  // location.reload() es lo único que funciona desde file:// en Chrome
  location.reload();
}}

// Arrancar
updateRing();
startTicker();
</script>
</body>
</html>"""

    out = Path(args.out)
    out.write_text(html, encoding='utf-8')
    print(f"✅  Visor generado: {out.resolve()}")
    print(f"   {total:,} tracks · {procesado:,} procesados · {con_isrc} con ISRC ({pct_isrc}%)")
    print(f"   Abre el archivo en tu navegador (doble clic o arrástralo a Chrome/Safari)")

if __name__ == '__main__':
    main()
