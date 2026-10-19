// 用量統計: what the meetings used in a month (AI, Token, Google, mail, audio, disk), by day or by project, as
// minutes_app.py usage reports it (scripts/usage.py). Opened from the corner of the list and from the menu bar panel
// (the app sends 'usage'); picking a meeting in the list, or one of a project's meetings here, leaves it.
// Loaded after app.js and uses its helpers (S, t, esc, call, $, flush, select, renderSide, renderMain, projectMark).
'use strict';

S.usage = false;                 // the main area shows 用量統計 instead of a meeting
const U = { view: 'day', month: '', data: null, open: new Set(), busy: false, err: '', seq: 0 };
const OTHER = '⁠other';     // the project row of what belongs to no meeting (setting the AI up)

const CHART = '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M3 13V8M8 13V3M13 13V6"/></svg>';

// --- opening and leaving ---------------------------------------------------------------------

function usageEntry() {
  return `<button class="usebtn${S.usage ? ' on' : ''}" id="usageBtn"${S.usage ? ' aria-current="page"' : ''}>${CHART}<span>${esc(t('usage'))}</span></button>`;
}
$('#side').addEventListener('click', (e) => { if (e.target.closest('#usageBtn')) openUsage(); });

async function openUsage() {
  if (S.sel && S.d) {                             // what was typed in the meeting is saved first
    await flush();
    if (S.dirty && S.giveUp !== OTHER) {          // not saved: a second click leaves it behind, as select() does
      S.giveUp = OTHER;
      showAlert(t('usage_unsaved'));
      return;
    }
    S.giveUp = null;
    clearTimeout(S.saveTimer); S.dirty = false;
    if (docsMode()) refreshDoc(S.sel, true);
    else learnLater(S.sel);
  }
  if (S.player.open) audio('stop');
  if (S.sheet && S.sheet !== 'setup') closeSheet();   // the mail or delete sheet belonged to that meeting
  S.sel = null; S.d = null; S.loadError = '';
  S.usage = true;
  renderSide();
  renderMain();
  loadUsage(U.month);
}

async function loadUsage(month) {
  const seq = ++U.seq;
  U.busy = true; U.err = '';
  if (S.usage) renderMain();
  try {
    const d = await call('usage', { month: month || '' });
    if (seq !== U.seq) return;
    U.data = d; U.month = d.month;
  } catch (e) {
    if (seq !== U.seq) return;
    U.err = e.message;
  }
  U.busy = false;
  if (S.usage) renderMain();
}

// --- numbers in words ------------------------------------------------------------------------

const minutes = (s) => Math.round((s || 0) / 60);
function duration(s) {
  const m = minutes(s);
  return m >= 60 ? t('u_hours', Math.floor(m / 60), m % 60) : t('u_minutes', m);
}
function bytes(n) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} MB`;
  return n > 0 ? `${Math.max(1, Math.round(n / 1e3))} KB` : '0';
}
const dash = '<span class="unone">—</span>';
const runs = (r) => ({ n: r.write.n + r.edit.n + r.test.n, s: r.write.s + r.edit.s + r.test.s });
function dayName(date) {
  const d = new Date(`${date}T12:00:00`);
  const week = d.toLocaleDateString(LANG === 'zh-TW' ? 'zh-TW' : 'en-US', { weekday: 'short' });
  return `${date.slice(5, 7)}/${date.slice(8, 10)} ${week}`;
}
const filledTag = (on) => (on ? `<span class="utag">${esc(t('u_filled'))}</span>` : '');

// a bar per row: the write-ups and the edits, as long as their minutes against the longest row on screen
function aiBar(r, most) {
  const scale = (s) => (most ? Math.round(s / most * 120) : 0);
  const w = scale(r.write.s), e = scale(r.edit.s + r.test.s);
  const tip = `${t('u_write')} ${t('u_runs_minutes', r.write.n, minutes(r.write.s))}, ${t('u_edit')} ${t('u_runs_minutes', r.edit.n + r.test.n, minutes(r.edit.s + r.test.s))}`;
  return `<span class="ubar" title="${esc(tip)}">${w ? `<i class="w" style="width:${w}px"></i>` : ''}${e ? `<i class="e" style="width:${e}px"></i>` : ''}</span>`;
}
function aiCell(r, most) {
  const all = runs(r);
  if (!all.n) return dash;
  return `<span class="uai">${aiBar(r, most)}<span>${esc(t('u_runs_minutes', all.n, minutes(all.s)))}</span>${r.limit ? `<span class="ulimit">${esc(t('ai_quota'))}</span>` : ''}</span>`;
}
const num = (n, words) => (n > 0 ? esc(words ? words(n) : n.toLocaleString()) : dash);

// --- drawing ---------------------------------------------------------------------------------

function drawUsage(main) {
  const d = U.data;
  const months = d ? d.months : [];
  const at = months.indexOf(U.month);
  const [y, m] = (U.month || '').split('-').map(Number);
  main.innerHTML = `<div class="usage">
    <div class="uhead"><h2>${esc(t('usage'))}</h2>
      <div class="useg" role="tablist" aria-label="${esc(t('usage'))}">
        ${['day', 'project'].map((v) => `<button role="tab" data-view="${v}" aria-selected="${U.view === v}">${esc(t(v === 'day' ? 'usage_by_day' : 'usage_by_project'))}</button>`).join('')}</div>
      <span class="ugrow"></span>
      ${U.month ? `<div class="umonth">
        <button class="tb" data-month="${esc(months[at - 1] || '')}" aria-label="${esc(t('usage_prev'))}" title="${esc(t('usage_prev'))}"${at > 0 ? '' : ' disabled'}>${ICON.chevL}</button>
        <span>${U.busy ? ICON.spin : ''}${esc(t('usage_month', y, m))}</span>
        <button class="tb" data-month="${esc(months[at + 1] || '')}" aria-label="${esc(t('usage_next'))}" title="${esc(t('usage_next'))}"${at >= 0 && at < months.length - 1 ? '' : ' disabled'}>${ICON.chevR}</button></div>` : ''}
    </div>
    ${U.err ? `<div class="banner err"><span>${esc(U.err)}</span></div>` : ''}
    ${d ? tilesHTML(d) + (U.view === 'day' ? daysHTML(d) : projectsHTML(d))
      : U.busy ? `<div class="busy">${ICON.spin}</div>` : ''}
  </div>`;
  main.querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => { U.view = b.dataset.view; renderMain(); }));
  main.querySelectorAll('[data-month]').forEach((b) => b.addEventListener('click', () => { if (b.dataset.month) loadUsage(b.dataset.month); }));
  main.querySelectorAll('.urow.proj').forEach((b) => b.addEventListener('click', () => {
    const key = b.dataset.key;
    if (U.open.has(key)) U.open.delete(key); else U.open.add(key);
    renderMain();
  }));
  main.querySelectorAll('.urow.meet[data-id]').forEach((b) => {
    b.addEventListener('click', () => select(b.dataset.id));
    b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(b.dataset.id); } });
  });
}

function tilesHTML(d) {
  const T = d.total, all = runs(T), disk = d.disk || { meetings: 0, speech: 0, program: 0 };
  const diskAll = disk.meetings + disk.speech + disk.program;
  const share = (n, of) => (of ? Math.max(n ? 1 : 0, Math.round(n / of * 1000) / 10) : 0);
  const key = (cls, text) => `<span class="ukey"><i class="${cls}"></i>${esc(text)}</span>`;
  return `<div class="utiles">
    <div class="utile"><div class="ulabel">${esc(t('u_meetings'))}</div><div class="ubig">${esc(t('u_n_meetings', T.meetings))}</div>
      <div class="usub">${esc(t('u_audio'))} ${esc(duration(T.audio))}</div></div>
    <div class="utile"><div class="ulabel">AI</div><div class="ubig">${esc(t('u_runs', all.n))} <small>· ${esc(t('u_minutes', minutes(all.s)))}</small></div>
      <div class="ustack" title="${esc(`${t('u_write')} ${minutes(T.write.s)} · ${t('u_edit')} ${minutes(T.edit.s + T.test.s)}`)}">
        <i class="w" style="width:${share(T.write.s, all.s)}%"></i><i class="e" style="width:${share(T.edit.s + T.test.s, all.s)}%"></i></div>
      <div class="ukeys">${key('w', t('u_write_n', T.write.n))}${key('e', t('u_edit_n', T.edit.n + T.test.n))}</div></div>
    <div class="utile"><div class="ulabel">${esc(t('u_tokens'))}</div><div class="ubig">${T.tokens ? esc(t('u_tokens_n', T.tokens)) : '—'}</div></div>
    <div class="utile"><div class="ulabel">Google</div><div class="ubig">${T.google ? esc(t('u_requests', T.google.toLocaleString())) : '—'}</div>
      <div class="usub">${esc(t('u_mails_n', T.mails))}</div></div>
    <div class="utile wide"><div class="ulabel">${esc(t('u_disk'))}</div><div class="ubig">${esc(bytes(diskAll))}</div>
      <div class="ustack"><i class="m" style="width:${share(disk.meetings, diskAll)}%"></i><i class="s" style="width:${share(disk.speech, diskAll)}%"></i><i class="p" style="width:${share(disk.program, diskAll)}%"></i></div>
      <div class="ukeys">${key('m', `${t('u_meetings')} ${bytes(disk.meetings)}`)}${key('s', `${t('setup_speech')} ${bytes(disk.speech)}`)}${key('p', `${t('u_program')} ${bytes(disk.program)}`)}</div></div>
  </div>`;
}

function headHTML(first, last) {
  return `<div class="urow uth" role="row"><span role="columnheader">${esc(first)}</span>
    <span role="columnheader" class="r">${esc(t('u_meetings'))}</span><span role="columnheader" class="r">${esc(t('u_audio'))}</span>
    <span role="columnheader" class="uaihead">AI <span class="ukey"><i class="w"></i>${esc(t('u_write'))}</span><span class="ukey"><i class="e"></i>${esc(t('u_edit'))}</span></span>
    <span role="columnheader" class="r">${esc(t('u_tokens'))}</span><span role="columnheader" class="r">Google</span>
    <span role="columnheader" class="r">${esc(t('u_mails'))}</span><span role="columnheader" class="r">${esc(last)}</span></div>`;
}
function cellsHTML(r, most, disk) {
  return `<span role="cell" class="r">${num(r.meetings, (n) => t('u_n_meetings', n))}</span>
    <span role="cell" class="r">${r.audio ? esc(t('u_minutes', minutes(r.audio))) : dash}</span>
    <span role="cell">${aiCell(r, most)}</span>
    <span role="cell" class="r">${r.tokens ? esc(t('u_tokens_n', r.tokens)) : dash}</span>
    <span role="cell" class="r">${num(r.google)}</span>
    <span role="cell" class="r">${num(r.mails)}</span>
    <span role="cell" class="r">${disk}</span>`;
}

function daysHTML(d) {
  if (!d.days.length) return `<div class="uempty">${esc(t('usage_empty'))}</div>`;
  const most = Math.max(...d.days.map((r) => runs(r).s));
  return `<div class="utable days" role="table" aria-label="${esc(t('usage_by_day'))}">${headHTML(t('u_date'), t('u_disk_added'))}
    ${d.days.map((r) => `<div class="urow" role="row"><span role="cell" class="ufirst"><b>${esc(dayName(r.date))}</b>${filledTag(r.filled)}</span>
      ${cellsHTML(r, most, r.disk ? '+' + esc(bytes(r.disk)) : dash)}</div>`).join('')}</div>`;
}

function projectsHTML(d) {
  if (!d.projects.length) return `<div class="uempty">${esc(t('usage_empty'))}</div>`;
  const most = Math.max(...d.projects.map((r) => runs(r).s));
  const rows = d.projects.map((p) => {
    const key = p.name === null ? OTHER : p.name;
    const open = U.open.has(key) && p.items.length > 0;
    const name = p.name === null ? t('u_other') : p.name || t('proj_loose');
    const head = `<button class="urow proj" role="row" data-key="${esc(key)}" aria-expanded="${open}"${p.items.length ? '' : ' disabled'}>
      <span role="cell" class="ufirst"><span class="uchev${open ? ' open' : ''}">${p.items.length ? ICON.chevR : ''}</span>${p.name === null ? '' : projectMark(p.name)}<b>${esc(name)}</b>${filledTag(p.filled)}</span>
      ${cellsHTML(p, most, p.disk ? esc(bytes(p.disk)) : dash)}</button>`;
    const items = !open ? '' : p.items.map((m) => `<div class="urow meet" role="row"${m.exists ? ` data-id="${esc(m.id)}" tabindex="0"` : ''}>
      <span role="cell" class="ufirst"><span class="udate">${esc(m.date.slice(5, 7) + '/' + m.date.slice(8, 10))}</span><span class="utitle">${esc(m.title || t('untitled'))}</span>${m.exists ? '' : `<span class="utag">${esc(t('u_deleted'))}</span>`}${filledTag(m.filled)}</span>
      ${cellsHTML({ ...m, meetings: 0 }, most, m.disk ? esc(bytes(m.disk)) : dash)}</div>`).join('');
    return head + items;
  }).join('');
  return `<div class="utable" role="table" aria-label="${esc(t('usage_by_project'))}">${headHTML(t('project'), t('u_disk'))}${rows}</div>`;
}
