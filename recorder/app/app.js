// The meeting window of Vinutes: the list of meetings on the left, one meeting on the right.
// Everything that reads or changes a meeting goes through the app (window.webkit.messageHandlers.app), which runs
// scripts/minutes_app.py and answers with window.reply(id, ok, data). The app also calls window.onEvent(name, data):
//   jobs    a recording started, finished or failed: reload the list
//   select  the user picked a meeting in the menu or a notification: show it
//   player  the recording's position while it plays
'use strict';

// --- talking to the app ----------------------------------------------------------------------

const waiting = new Map();
let seq = 0;

function call(cmd, args = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    waiting.set(id, { resolve, reject });
    window.webkit.messageHandlers.app.postMessage({ id, cmd, args });
  });
}

window.reply = (id, ok, data) => {
  const w = waiting.get(id);
  if (!w) return;
  waiting.delete(id);
  if (ok) w.resolve(data || {});
  else w.reject(new Error((data && data.message) || '沒有完成，請再試一次。'));
};

// --- small helpers ---------------------------------------------------------------------------

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pad = (n) => String(n).padStart(2, '0');
const mmss = (t) => { t = Math.max(0, Math.floor(t)); return t >= 3600 ? `${Math.floor(t / 3600)}:${pad(Math.floor(t % 3600 / 60))}:${pad(t % 60)}` : `${pad(Math.floor(t / 60))}:${pad(t % 60)}`; };
const clock = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const hhmm = () => { const d = new Date(); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

const ICON = {
  plus: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  image: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-5-5-8 8"/></svg>',
  clip: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11l-8.6 8.6a5 5 0 0 1-7-7L14 4a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4L15.6 7"/></svg>',
  link: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>',
  search: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>',
  working: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8a8a90" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9"/></svg>',
  ready: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0a64d8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>',
  sent: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1e7b34" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8L16 9.8"/></svg>',
  failed: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#d1242f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/></svg>',
  chevR: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>',
  chevL: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>',
  chevU: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>',
  open: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M10 14l7-7M12 7h5v5"/></svg>',
  sync: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5"/></svg>',
  spin: '<svg class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0a64d8" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.2-8.6"/></svg>',
  check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1e7b34" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  checkSmall: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#1e7b34" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  done: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1e7b34" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8L16 9.8"/></svg>',
  dot: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a1a1a6" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/></svg>',
  collapse: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l6 6-6 6M13 6l6 6-6 6"/></svg>',
  expand: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6l-6 6 6 6M11 6l-6 6 6 6"/></svg>',
  bubble: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
  clock: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  up: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  book: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h6"/></svg>',
  play: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#ffffff" aria-hidden="true"><path d="M7 5v14l12-7z"/></svg>',
  pause: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#ffffff" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
  x: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  xs: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  headset: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/></svg>',
  lines: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M4 11h16M4 16h10"/></svg>',
  mail: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>',
  prompt: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
};

const STATUS = { working: '整理中', ready: '待寄出', sent: '已寄出', failed: '沒有整理完成' };
const QUICK = [
  ['精簡摘要', '每一節只留結論和數字，刪掉重複的說明'],
  ['完整詳盡', '照逐字稿補回討論過程、每個人的說法和理由'],
  ['正式嚴謹', '改成正式的書面語氣，口語說法全部換掉'],
  ['視覺呈現', '能做成表格的內容改成表格，時程照時間先後排'],
  ['對外版本', '刪掉只適合內部看的討論，人名改成單位'],
];
const FORMATS = [['gdoc', 'Google 文件連結'], ['word', 'Word 檔'], ['pdf', 'PDF 檔']];

// --- state -----------------------------------------------------------------------------------

const S = {
  jobs: [], sel: null, q: '', proj: '全部',
  d: null,                   // the open meeting, as minutes_app.py open returned it
  loadError: '',
  tab: null, railOpen: true, cfocus: null, resolved: new Set(),
  dirty: false, saving: null, saveTimer: null, saveText: '', saveErr: false,
  shown: '',                 // which preview the editor holds, so a save is compared with what the user saw
  giveUp: null,              // the meeting the user clicked once while this one had unsaved text
  busy: false, asked: '', said: '', saidErr: false, canUndo: false,
  busyText: '',              // what the line above the box says while busy ('' = Claude is rewriting)
  setupSeq: 0,               // goes up with every click in 環境設定自檢: an older answer is not shown
  attach: [],                // files, links and pictures picked for 「八、補充資訊」, sent with the next sentence
  urlOpen: false, menuOpen: false,
  learned: [], banner: null, bannerTimer: null, alert: null,
  player: { open: false, playing: false, pos: 0, dur: 0, speed: 1 },
  sheet: null, mail: null,
  placed: '',                // where the Google Doc was last put, so it moves only when that changes
  reloadDoc: false,          // the Doc must load again once its place shows (it was covered by a sheet)
  docFailed: false,          // the Doc did not load for this meeting: the preview shows instead
  refreshing: null,          // {id, p}: a refresh on its way, what was typed in the Doc coming into the side panel
  docWarning: '',            // what the last refresh said, kept apart from what opening the meeting said
  editSeq: 0,                // counts changes made here (confirm, Claude, undo), so an older refresh never undoes one
  version: null,             // {version, newest, update}: the list's corner
  recording: false,          // a recording runs: 版本更新 waits for it to end
  updating: false,           // 版本更新 was pressed: the app is about to close and open again
};

// A meeting with a Google Doc shows the Doc itself in the middle (the app lays it over #gdoc); the side panel
// keeps 待補充, 待確認 and 操作紀錄. Without one (no Google connection), the editable preview stays.
// When this computer is offline or the Doc did not load (S.docFailed), the preview shows the minutes instead.
function docsMode() {
  return !!(S.d && S.d.doc_url && !S.d.readonly && !S.d.offline && !S.docFailed
            && S.d.status !== 'working' && S.d.status !== 'failed');
}

function placeDoc(reload = false) {
  const el = $('#gdoc');
  const show = !!el && docsMode() && !S.sheet;
  if (reload && !show) { S.reloadDoc = true; return; }          // loads again once the place shows
  if (show && S.reloadDoc) { reload = true; S.reloadDoc = false; }
  const r = show ? el.getBoundingClientRect() : { x: 0, y: 0, width: 0, height: 0 };
  // the AI menu opens upward, into the Doc's place: the Doc ends above it while it is open
  const menu = show && S.aiOpen ? $('#aiMenu') : null;
  const h = menu ? Math.max(0, Math.min(r.height, menu.getBoundingClientRect().top - r.y - 8)) : r.height;
  const key = [show, show ? S.d.doc_url : '', Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(h)].join('|');
  if (key === S.placed && !reload) return;
  S.placed = key;
  call('gdoc', { show, reload, url: show ? S.d.doc_url : '', account: show ? S.d.account || '' : '',
                 x: r.x, y: r.y, w: r.width, h }).catch(() => {});
}
const docSpot = new ResizeObserver(() => placeDoc());
window.addEventListener('resize', () => placeDoc());

// what was typed into the Doc: into the minutes, the side panel, and what Claude learns. One at a time per
// meeting; `again` waits for one already on its way and then asks once more (closing the window, leaving a meeting)
function refreshDoc(id = S.sel, again = false) {
  if (!id) return Promise.resolve();
  const running = S.refreshing && S.refreshing.id === id ? S.refreshing.p : null;
  if (running) return again ? running.then(() => refreshDoc(id)) : running;
  const seq = S.editSeq;
  const p = call('refresh', { id }).then((r) => {
    if (r.busy || S.sel !== id || !S.d || !docsMode()) return;
    const before = JSON.stringify([S.d.todo, S.d.check, S.d.log]);
    if (seq === S.editSeq) { S.d.todo = r.todo || []; S.d.check = r.check || []; }   // not over a confirm made meanwhile
    S.d.log = r.log || [];
    if ('can_undo' in r && !S.busy) S.canUndo = !!r.can_undo;
    if (r.learned && r.learned.length) { S.learned.push(...r.learned); renderLearned(); }
    if ((r.warning || '') !== S.docWarning) { S.docWarning = r.warning || ''; renderBanners(); }
    if (JSON.stringify([S.d.todo, S.d.check, S.d.log]) !== before) renderRail();
  }).catch(() => {}).finally(() => { if (S.refreshing && S.refreshing.p === p) S.refreshing = null; });
  S.refreshing = { id, p };
  return p;
}
// every 15 seconds while the window is on screen; a minimized window waits
setInterval(() => { if (docsMode() && !S.busy && !document.hidden) refreshDoc(); }, 15000);

// a 待補充 or 待確認 item: the Doc moves to where it is and selects it (the keyboard stays here, so nothing typed
// next lands on the selected words)
function showInDoc(words, blink = false) {
  if (!words || !docsMode()) return;
  call('find', { id: S.sel, text: words, blink }).catch(() => {});
}

// every [__] blinks three times, then keeps its pale red: on opening a meeting, and on picking a 待補充 item
function blinkBlanks() {
  if (docsMode()) { call('blink', {}).catch(() => {}); return; }
  const el = docEl();
  if (!el || !el.querySelector('.blank')) return;
  el.classList.remove('blinking');
  void el.offsetWidth;                                 // the animation starts over
  el.classList.add('blinking');
  clearTimeout(S.blinkTimer);
  S.blinkTimer = setTimeout(() => el.classList.remove('blinking'), 2200);
}

// --- the list --------------------------------------------------------------------------------

function projects() {
  const names = [...new Set(S.jobs.map((j) => j.project).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-Hant'));
  const loose = S.jobs.some((j) => !j.project && (j.status === 'ready' || j.status === 'sent'));
  return ['全部', ...names, ...(loose ? ['未分類'] : [])];
}

function shownJobs() {
  const q = S.q.trim();
  const digits = (t) => t.replace(/[^0-9]/g, '');
  return S.jobs.filter((j) => {
    if (S.proj === '未分類' && j.project) return false;
    if (S.proj !== '全部' && S.proj !== '未分類' && j.project !== S.proj) return false;
    if (!q) return true;
    const text = `${j.title} ${j.project} ${j.day} ${j.date} ${j.time}`;
    return text.includes(q) || (digits(q) !== '' && (digits(j.day + j.time).includes(digits(q))
                                                     || digits(j.date + j.time).includes(digits(q))));
  });
}

function titleOf(j) {
  if (j.status === 'working') return '整理中';
  if (j.status === 'failed') return '沒有整理完成';
  return j.title || '會議紀錄';
}

function renderSide() {
  const side = $('#side');
  const list = shownJobs();
  const opts = projects();
  if (!opts.includes(S.proj)) S.proj = '全部';
  const groups = [];
  for (const j of list) {
    let g = groups.find((x) => x.date === j.date);
    if (!g) groups.push(g = { date: j.date, day: j.day, items: [] });
    g.items.push(j);
  }
  const keepFocus = document.activeElement && document.activeElement.id === 'q';
  const scrolled = side.querySelector('.sidelist') ? side.querySelector('.sidelist').scrollTop : 0;
  side.innerHTML = `<div class="sidelist">
    <h1>所有會議記錄</h1>
    <div class="search">${ICON.search}<input id="q" aria-label="搜尋會議記錄" placeholder="日期或關鍵字" value="${esc(S.q)}"></div>
    <div class="proj"><label for="proj">專案</label><select id="proj">${opts.map((p) => `<option${p === S.proj ? ' selected' : ''}>${esc(p)}</option>`).join('')}</select></div>
    <div class="count">${list.length} 筆</div>
    ${groups.map((g) => `
      <div class="day"><span>${esc(g.day)}</span><i></i></div>
      ${g.items.map((j) => `
        <div class="item${j.id === S.sel ? ' on' : ''}${playingRow(j.id) ? ' playing' : ''}" role="button" tabindex="0" data-id="${esc(j.id)}">
          <span class="ico">${ICON[j.status] || ICON.ready}</span>
          <span class="txt"><span class="t">${esc(titleOf(j))}</span>
            <span class="s">${esc(j.time)}　${esc(STATUS[j.status] || '')}${S.proj === '全部' && j.project ? '　·　' + esc(j.project) : ''}</span></span>
          <span class="tools">${j.has_transcript ? `<button class="tb" data-act="read" title="看逐字稿" aria-label="看逐字稿">${ICON.lines}</button>` : ''}${j.has_audio ? playButton(playingRow(j.id)) : ''}</span>
        </div>`).join('')}`).join('')}
    ${list.length ? '' : '<div class="empty">找不到符合的會議</div>'}</div>
    <div class="ver" id="ver"></div>`;
  side.querySelector('.sidelist').scrollTop = scrolled;
  renderVersion();
  const q = $('#q');
  q.addEventListener('input', () => { S.q = q.value; renderSide(); });
  if (keepFocus) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  $('#proj').addEventListener('change', (e) => { S.proj = e.target.value; renderSide(); });
  // the meeting already open stays as it is: opening it again would drop what Claude is about to answer
  side.querySelectorAll('.item').forEach((b) => {
    const go = () => { if (b.dataset.id !== S.sel || !S.d) select(b.dataset.id); };
    b.addEventListener('click', (e) => { if (!e.target.closest('.tb')) go(); });
    b.addEventListener('keydown', (e) => { if (e.target === b && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); go(); } });
  });
}
// the buttons on a row, also the ones drawn again while the recording plays
$('#side').addEventListener('click', (e) => {
  const t = e.target.closest('.item .tb');
  if (t) rowAction(t.closest('.item').dataset.id, t.dataset.act);
});

const playingRow = (id) => id === S.sel && S.player.playing;
const playButton = (on) => `<button class="tb${on ? ' on' : ''}" data-act="play" title="${on ? '暫停播放' : '聽錄音檔'}" aria-label="${on ? '暫停播放' : '聽錄音檔'}">${on ? ICON.pause : ICON.headset}</button>`;

// the two buttons on a meeting in the list: its transcript, its recording; another meeting opens first
async function rowAction(id, act) {
  if (act === 'play' && playingRow(id)) return audio('pause', { at: S.player.pos });
  if (id !== S.sel || !S.d) {
    await select(id);
    if (S.sel !== id || !S.d) return;             // stayed on a meeting with unsaved text, or this one did not open
  }
  if (act === 'read') {
    if ((S.d.transcript || []).length) openTranscript();
    else showAlert('這場會議還沒有逐字稿。');
  } else if (S.d.audio) {
    audio('play', { at: S.player.open ? S.player.pos : 0 });
  }
}

// the meeting playing keeps its pause button showing; the others show 聽錄音檔 on hover
function markPlaying() {
  document.querySelectorAll('#side .item').forEach((row) => {
    const on = playingRow(row.dataset.id);
    row.classList.toggle('playing', on);
    const b = row.querySelector('[data-act="play"]');
    if (b && b.classList.contains('on') !== on) b.outerHTML = playButton(on);
  });
}

// the list's corner: the version, and 版本更新 when GitHub has a newer one (looked up once a day); a recording
// has to end first, since updating closes the app
function renderVersion() {
  const el = $('#ver');
  if (!el) return;
  const v = S.version;
  if (!v || !v.version) { el.innerHTML = ''; return; }
  const tip = S.recording ? '錄音結束後才能更新' : `更新到 ${v.newest}`;
  el.innerHTML = `<span>版本 ${esc(v.version)}</span>${v.update ? `<button class="upd${S.updating || S.recording ? ' off' : ''}" id="updBtn" title="${esc(tip)}" aria-disabled="${S.updating || S.recording}">${S.updating ? '更新中⋯' : '版本更新'}</button>` : ''}`;
  const b = $('#updBtn');
  if (b) b.addEventListener('click', updateApp);
}

async function loadVersion() {
  try {
    const v = await call('version', {});
    S.version = v;
    S.recording = !!v.recording;
    renderVersion();
  } catch (e) { /* no corner this time */ }
}

async function updateApp() {
  if (S.updating || S.recording) return;
  S.updating = true;
  renderVersion();
  try {
    await flush();                                 // what was typed is saved before the app closes
    await call('update', {});                      // the app closes and opens again as the new version
  } catch (e) {
    S.updating = false;
    renderVersion();
    showAlert(e.message);
  }
}

async function loadList() {
  try {
    const r = await call('list');
    S.jobs = r.jobs || [];
  } catch (e) {
    S.jobs = [];
  }
  renderSide();
}

// --- choosing a meeting ----------------------------------------------------------------------

async function select(id) {
  if (!id) return;
  if (S.sel && S.d) {
    await flush();
    if (S.dirty && S.giveUp !== id) {          // a second click on the same meeting leaves the unsaved text behind
      S.giveUp = id;
      showAlert('這一場改過的內容還沒存好。要放棄這些修改直接換過去，再點一次那場會議。');
      return;
    }
    S.giveUp = null;
    if (docsMode()) refreshDoc(S.sel, true);
    else learnLater(S.sel);
  }
  S.sel = id;
  S.d = null; S.loadError = ''; S.cfocus = null; S.resolved = new Set(); S.tab = null;
  S.busy = false; S.asked = ''; S.said = ''; S.canUndo = false; S.learned = []; S.alert = null;
  S.attach = []; S.urlOpen = false; S.menuOpen = false;
  S.dirty = false; S.saveText = ''; S.saveErr = false;
  S.docFailed = false; S.docWarning = ''; S.reloadDoc = false;
  clearTimeout(S.bannerTimer); S.banner = null;
  if (S.player.open) audio('stop');
  if (S.sheet !== 'setup') closeSheet();          // 環境設定自檢 stays over whichever meeting opens under it
  renderSide();
  renderMain();
  try {
    const d = await call('open', { id });
    if (S.sel !== id) return;
    S.d = d;
    S.shown = d.shown || '';
    S.canUndo = !!d.can_undo;
    S.learned = d.learned || [];
    S.saveText = d.doc_url && !d.offline ? `已同步 Google 文件 ${hhmm()}` : '';
    const n = d.news || {};
    if ((n.edits || 0) + (n.new_comments || 0) > 0 && !docsMode()) {    // beside the Doc, 操作紀錄 has them
      const names = (n.editors || []).join('、') || '有人';
      const parts = [];
      if (n.edits) parts.push(`${names} 改了 ${n.edits} 處（綠色底線）`);
      if (n.new_comments) parts.push(`有 ${n.new_comments} 則新留言（黃色標示）`);
      S.banner = '已載入 Google 文件的最新版本：' + parts.join('，');
      S.bannerTimer = setTimeout(() => { S.banner = null; renderBanners(); }, 5000);
    }
    const job = S.jobs.find((j) => j.id === id);
    if (job && job.status !== d.status) loadList();
  } catch (e) {
    if (S.sel !== id) return;
    S.loadError = e.message;
  }
  renderMain();
  if (S.d && !S.loadError) blinkBlanks();
}

// before showing another meeting or closing the window: what was typed is saved and learned
async function leave() {
  await flush();
  if (S.d && S.sel) {
    try {
      const r = await call('learn', { id: S.sel });
      return r;
    } catch (e) { /* the next open learns it */ }
  }
}
// learning waits its turn behind a Claude rewrite of the same meeting; nobody should wait for that
function learnLater(id) { call('learn', { id }).catch(() => {}); }
window.beforeClose = async () => {
  await flush();
  if (docsMode()) {
    await new Promise((r) => setTimeout(r, 1500));   // Google saves the last words typed into the Doc first
    await refreshDoc(S.sel, true);
  } else if (S.d && S.sel) learnLater(S.sel);
  return true;
};

// --- the meeting -----------------------------------------------------------------------------

function renderMain() {
  docSpot.disconnect();
  drawMain();
  const spot = $('#gdoc');
  if (spot) docSpot.observe(spot);
  placeDoc();
}

function drawMain() {
  const main = $('#main');
  const job = S.jobs.find((j) => j.id === S.sel);
  if (!S.sel) { main.innerHTML = '<div class="state"><div class="sub">還沒有錄音。</div></div>'; return; }
  if (S.loadError) {
    main.innerHTML = `<div class="state"><h2>${esc(job ? titleOf(job) : '')}</h2><div class="banner err"><span>${esc(S.loadError)}</span></div>
      <div><button class="btn ghost" id="again">再試一次</button></div></div>`;
    $('#again').addEventListener('click', () => select(S.sel));
    return;
  }
  if (!S.d) {
    main.innerHTML = `<div class="state"><div class="busy">${ICON.spin}<span>正在讀取 Google 文件的最新版本⋯</span></div></div>`;
    return;
  }
  const d = S.d;
  if (d.status === 'working') return renderWorking(main, d);
  if (d.status === 'failed') return renderFailed(main, d);
  if (docsMode()) {
    main.innerHTML = `
      <div class="head" id="head"></div>
      <div class="body">
        <div class="paper docs"><div id="banners"></div>
          <div id="gdoc" class="gdoc"><div class="busy">${ICON.spin}<span>正在打開 Google 文件⋯</span></div></div></div>
        <aside class="rail" id="rail" aria-label="待補充、待確認與操作紀錄"></aside>
      </div>
      <div class="ask" id="ask"></div>
      <div class="foot" id="foot"></div>`;
    renderHead(); renderBanners(); renderRail(); renderAsk(); renderFoot();
    return;
  }
  main.innerHTML = `
    <div class="head" id="head"></div>
    <div class="body">
      <div class="paper"><div id="banners"></div><div id="doc" contenteditable="true" spellcheck="false"></div></div>
      <aside class="rail" id="rail" aria-label="留言與操作紀錄"></aside>
    </div>
    <div class="ask" id="ask"></div>
    <div class="foot" id="foot"></div>`;
  setDoc(d.html);
  if (d.readonly) docEl().contentEditable = 'false';
  wireDoc();
  renderHead(); renderBanners(); renderRail(); renderAsk(); renderFoot();
}

function renderWorking(main, d) {
  const step = d.step;
  const st = (n) => {
    const order = { transcribing: 0, writing: 1 }[step] ?? 0;
    if (n < order) return ['', ICON.done];
    if (n === order) return ['now', ICON.spin];
    return ['later', ICON.dot];
  };
  const names = ['轉成逐字稿', '整理成會議紀錄', '發成 Google 文件'];
  main.innerHTML = `<div class="state"><h2>整理中</h2>
    <div class="sub">錄音 ${esc(d.day)} ${esc(d.time)}${d.ended_time ? '–' + esc(d.ended_time) : ''}</div>
    <div class="steps">${names.map((n, i) => { const [c, ic] = st(i); return `<div class="${c}">${ic}<span>${n}</span></div>`; }).join('')}</div>
    ${d.message ? `<div class="sub">${esc(d.message)}</div>` : ''}</div>`;
}

function renderFailed(main, d) {
  main.innerHTML = `<div class="state"><h2>沒有整理完成</h2>
    <div class="sub">錄音 ${esc(d.day)} ${esc(d.time)}</div>
    <div class="banner err"><span>${esc(d.message || '整理中斷了。')}</span></div>
    <div class="buttons"><button class="btn primary" id="retry">重新整理</button><button class="btn ghost" id="folder">打開錄音資料夾</button></div></div>`;
  $('#retry').addEventListener('click', async () => {
    try { await call('retry', { id: S.sel }); } catch (e) { /* the list shows what happens */ }
    await loadList();
    select(S.sel);
  });
  $('#folder').addEventListener('click', () => call('folder', { id: S.sel }).catch(() => {}));
}

function renderHead() {
  const d = S.d;
  const el = $('#head');
  if (!el) return;
  const planned = d.planned ? `下次會議排在 ${d.planned}，還沒開會` : '之後沒有同名會議';
  el.innerHTML = `
    <nav class="crumbs" aria-label="目前位置">
      <button class="crumb" id="toProj">${esc(d.project || '未分類')}</button>${ICON.chevR}
      <button class="crumb" id="toDate">${esc(shortDay(d))}</button>
      <b>（${esc(d.title || '會議紀錄')}）</b>
    </nav>
    <button class="sib${d.prev ? '' : ' off'}" id="prev" title="${esc(d.prev ? d.prev_title : '之前沒有同名會議')}">${ICON.chevL}<span>上次會議</span></button>
    <button class="sib${d.next ? '' : ' off'}" id="next" title="${esc(d.next ? d.next_title : planned)}"><span>下次會議</span>${ICON.chevR}</button>
    ${docsMode() ? '' : `<span class="savetext${S.saveErr ? ' err' : ''}" id="savetext">${esc(S.saveText)}</span>`}
    ${d.doc_url ? `<span class="iconlink" id="openDoc" title="在瀏覽器打開 Google 文件">${ICON.open}</span>` : ''}`;
  $('#toProj').addEventListener('click', () => { S.proj = d.project || '未分類'; S.q = ''; renderSide(); });
  $('#toDate').addEventListener('click', () => { S.q = shortDay(d); S.proj = '全部'; renderSide(); });
  $('#prev').addEventListener('click', () => d.prev && select(d.prev));
  $('#next').addEventListener('click', () => d.next && select(d.next));
  if (d.doc_url) $('#openDoc').addEventListener('click', () => call('link', { url: d.doc_url }).catch(() => {}));
}

function setSave(text, err = false) {
  S.saveText = text; S.saveErr = err;
  const el = $('#savetext');
  if (el) { el.textContent = text; el.className = 'savetext' + (err ? ' err' : ''); }
}

function renderBanners() {
  const el = $('#banners');
  if (!el) return;
  const rows = [];
  if (S.banner) rows.push(`<div class="banner news">${ICON.sync}<span>${esc(S.banner)}</span><button id="seen">知道了</button></div>`);
  if (S.d.warning) rows.push(`<div class="banner warn"><span>${esc(S.d.warning)}</span></div>`);
  if (S.docWarning && S.docWarning !== S.d.warning) rows.push(`<div class="banner warn"><span>${esc(S.docWarning)}</span></div>`);
  if (S.alert) rows.push(`<div class="banner err"><span>${esc(S.alert)}</span><button id="alertOk">知道了</button></div>`);
  el.innerHTML = rows.join('');
  const seen = $('#seen');
  if (seen) seen.addEventListener('click', () => { clearTimeout(S.bannerTimer); S.banner = null; renderBanners(); });
  const ok = $('#alertOk');
  if (ok) ok.addEventListener('click', () => { S.alert = null; renderBanners(); });
}

function showAlert(text) { S.alert = text; renderBanners(); }

// --- the editable minutes --------------------------------------------------------------------

function docEl() { return $('#doc'); }
function editable() { return S.d && S.d.readonly ? 'false' : 'true'; }

// 10/14 for this year, 2025/10/14 for another
function shortDay(d) {
  if (!d.date) return d.day.split('（')[0];
  const [y, m, day] = d.date.split('-');
  const md = `${m}/${day}`;
  return y === String(new Date().getFullYear()) ? md : `${y}/${md}`;
}

function setDoc(html) {
  const el = docEl();
  if (!el) return;
  el.innerHTML = html || '';
  el.querySelectorAll('.anchor').forEach((a) => {
    const n = Number(a.dataset.c);
    if (S.resolved.has(n)) unmarkAnchor(n);
  });
}

function wireDoc() {
  const el = docEl();
  el.addEventListener('input', () => {
    el.querySelectorAll('.blank').forEach((b) => { if (b.textContent !== '[__]') b.classList.remove('blank'); });
    // WebKit keeps the look of replaced text with <font> and inline styles; the minutes have neither
    el.querySelectorAll('font').forEach((f) => f.replaceWith(...f.childNodes));
    el.querySelectorAll('[style]').forEach((x) => x.removeAttribute('style'));
    S.dirty = true;
    setSave('未儲存');
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(save, 2500);
  });
  el.addEventListener('blur', () => {
    leave().then((r) => {
      if (r && r.learned && r.learned.length && S.d) { S.learned.push(...r.learned); renderLearned(); refreshLog(); }
    });
  });
  el.addEventListener('click', (e) => {
    const a = e.target.closest('.anchor');
    if (a) focusComment(Number(a.dataset.c));
  });
  el.addEventListener('paste', (e) => {           // pasted text arrives as plain text, never as someone else's HTML
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData('text/plain');
    document.execCommand('insertText', false, text);
  });
}

function save() {
  clearTimeout(S.saveTimer);
  if (S.saving) return S.saving.then(() => (S.dirty ? save() : undefined));
  if (!S.dirty || !S.d) return Promise.resolve();
  const id = S.sel;
  const html = docEl().innerHTML;
  S.dirty = false;
  setSave('儲存中⋯');
  S.saving = call('save', { id, html, shown: S.shown }).then((r) => {
    if (S.sel !== id || !S.d) return;
    afterEdit(r);
  }).catch((e) => {
    if (S.sel !== id) return;
    S.dirty = true;
    setSave(e.message || '沒有存到 Google 文件', true);
  }).finally(() => { S.saving = null; });
  return S.saving;
}

async function flush() {
  if (S.dirty) await save();
  else if (S.saving) await S.saving;
}

// every edit answers the same way: saved where, what a colleague changed meanwhile, what did not fit
function afterEdit(r) {
  if (!S.d) return;                                 // the meeting is loading again: what it loads already has this
  if (r.unsaved) setSave('這次的修改沒有存', true);
  else setSave(r.held ? `先存在這台電腦 ${r.saved_at || hhmm()}` : `已存回 Google 文件 ${r.saved_at || hhmm()}`);
  if (r.todo) { S.d.todo = r.todo; renderFoot(); renderRail(); }
  if ('can_undo' in r) S.canUndo = !!r.can_undo;
  if (r.reload_doc) placeDoc(true);                 // the whole Doc was uploaded again: the one shown loads again
  if (r.learned && r.learned.length) { S.learned.push(...r.learned); renderLearned(); }
  const notes = [];
  if (r.held) notes.push(r.held);
  if (r.conflicts && r.conflicts.length) {
    notes.push(`有人同時在 Google 文件改了同一段，這幾段保留對方的版本：${r.conflicts.map((c) => '「' + c.slice(0, 20) + '」').join('、')}`);
  }
  if (r.skipped && r.skipped.length) {
    notes.push(`有幾段改過的內容對不到原本的段落，沒有存：${r.skipped.map((c) => '「' + c.slice(0, 20) + '」').join('、')}`);
  }
  if (r.kept && r.kept.length) {
    notes.push(`有幾段在 ${aiName()} 改完之後又被改過，這幾段沒有復原：${r.kept.map((c) => '「' + c.slice(0, 20) + '」').join('、')}`);
  }
  if (r.warning) notes.push(r.warning);
  if (notes.length) showAlert(notes.join(' '));
  if (r.html && !S.dirty) { setDoc(r.html); S.shown = r.shown || ''; }
  else if (r.typed) S.shown = r.typed;              // the page as it was saved: later typing is compared with it
}

// a change that needs the latest text (Claude, undo, a mail) waits for typing to be saved first
async function savedFirst() {
  await flush();
  if (S.dirty) { showAlert('改過的內容還沒存好，存好之後再試一次。'); return false; }
  return true;
}

function jumpTo(item) {
  const el = docEl();
  const blocks = [...el.querySelectorAll('p, li, tr, h1, h2, h3')];
  const hit = blocks.find((b) => b.textContent.includes(item.anchor) && b.querySelector('.blank'))
           || blocks.find((b) => b.textContent.includes(item.anchor));
  const target = hit ? (hit.querySelector('.blank') || hit) : el.querySelector('.blank');
  const prompt = $('#promptInput');
  if (prompt) prompt.value = `${item.label}是`;
  if (!target) return;
  target.scrollIntoView({ block: 'center', behavior: 'smooth' });
  el.focus({ preventScroll: true });
  const block = target.closest('td, th, li, p, h1, h2, h3') || target;
  block.classList.add('flash');
  setTimeout(() => block.classList.remove('flash'), 1400);
  blinkBlanks();
  const range = document.createRange();
  if (target.classList.contains('blank')) {
    // select the words, not the tinted box, so what is typed comes out as plain text
    const text = document.createTextNode(target.textContent);
    target.replaceWith(text);
    range.setStart(text, 0);
    range.setEnd(text, text.length);
  } else {
    range.selectNodeContents(target);
  }
  const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
}

// --- comments and the activity log -----------------------------------------------------------

function openComments() { return (S.d.comments || []).filter((c) => !S.resolved.has(c.n)); }

function renderRail() {
  const el = $('#rail');
  if (!el) return;
  if (docsMode()) return renderDocsRail(el);
  const d = S.d;
  const open = openComments().length;
  const tab = S.tab || (open ? 'comments' : 'log');
  if (!S.railOpen) {
    el.className = 'rail closed';
    el.innerHTML = `
      <button class="iconbtn" id="expand" title="展開" aria-label="展開">${ICON.expand}</button>
      <button class="iconbtn" id="railC" title="留言" aria-label="留言">${ICON.bubble}${open ? `<span class="badge">${open}</span>` : ''}</button>
      <button class="iconbtn" id="railL" title="操作紀錄" aria-label="操作紀錄">${ICON.clock}</button>`;
    $('#expand').addEventListener('click', () => { S.railOpen = true; renderRail(); });
    $('#railC').addEventListener('click', () => { S.railOpen = true; S.tab = 'comments'; renderRail(); });
    $('#railL').addEventListener('click', () => { S.railOpen = true; S.tab = 'log'; renderRail(); });
    return;
  }
  el.className = 'rail';
  const comments = d.comments || [];
  el.innerHTML = `
    <div class="railhead">
      <div class="tabs" role="tablist">
        <button class="tab${tab === 'comments' ? ' on' : ''}" role="tab" id="tabC">留言${open ? ' ' + open : ''}</button>
        <button class="tab${tab === 'log' ? ' on' : ''}" role="tab" id="tabL">操作紀錄</button>
      </div>
      <span style="flex:1"></span>
      <button class="iconbtn" id="collapse" title="收合" aria-label="收合">${ICON.collapse}</button>
    </div>
    <div class="railbody" id="railbody">${tab === 'comments' ? commentsHTML(comments) : logHTML(d.log || [])}</div>`;
  $('#tabC').addEventListener('click', () => { S.tab = 'comments'; renderRail(); });
  $('#tabL').addEventListener('click', () => { S.tab = 'log'; renderRail(); });
  $('#collapse').addEventListener('click', () => { S.railOpen = false; renderRail(); });
  if (tab === 'comments') wireComments();
}

// beside the Google Doc: what is still blank, Claude's guesses to check, and the activity log (the Doc shows its
// own comments)
function renderDocsRail(el) {
  const d = S.d;
  const todo = d.todo || [];
  const check = d.check || [];
  const tab = ['fill', 'check', 'log'].includes(S.tab) ? S.tab : (todo.length ? 'fill' : check.length ? 'check' : 'log');
  const pick = (t) => () => { S.railOpen = true; S.tab = t; renderRail(); };
  if (!S.railOpen) {
    el.className = 'rail closed';
    el.innerHTML = `
      <button class="iconbtn" id="expand" title="展開" aria-label="展開">${ICON.expand}</button>
      <button class="iconbtn" id="railF" title="待補充" aria-label="待補充">${ICON.lines}${todo.length ? `<span class="badge red">${todo.length}</span>` : ''}</button>
      <button class="iconbtn" id="railK" title="待確認" aria-label="待確認">${ICON.check}${check.length ? `<span class="badge">${check.length}</span>` : ''}</button>
      <button class="iconbtn" id="railL" title="操作紀錄" aria-label="操作紀錄">${ICON.clock}</button>`;
    $('#expand').addEventListener('click', () => { S.railOpen = true; renderRail(); });
    $('#railF').addEventListener('click', pick('fill'));
    $('#railK').addEventListener('click', pick('check'));
    $('#railL').addEventListener('click', pick('log'));
    return;
  }
  el.className = 'rail';
  const body = tab === 'fill'
    ? (todo.length ? todo.map((t, i) => `<button class="todo" data-t="${i}"><b>${esc(t.label)}</b>${t.anchor && t.anchor !== t.label ? `<span>${esc(t.anchor)}</span>` : ''}</button>`).join('')
                   : '<div class="empty">都補完了</div>')
    : tab === 'check'
      ? (check.length ? check.map((c, i) => `<div class="card guess"><div class="text">${esc(c.label)}</div>
          <button class="okc2" data-c="${i}">${ICON.checkSmall}<span>確認無誤</span></button></div>`).join('')
                      : '<div class="empty">都確認了</div>')
      : logHTML(d.log || []);
  el.innerHTML = `
    <div class="railhead">
      <div class="tabs" role="tablist">
        <button class="tab${tab === 'fill' ? ' on' : ''}" role="tab" id="tabF">待補充${todo.length ? ` <b class="n red">${todo.length}</b>` : ''}</button>
        <button class="tab${tab === 'check' ? ' on' : ''}" role="tab" id="tabK">待確認${check.length ? ` <b class="n yellow">${check.length}</b>` : ''}</button>
        <button class="tab${tab === 'log' ? ' on' : ''}" role="tab" id="tabL">操作紀錄</button>
      </div>
      <span style="flex:1"></span>
      <button class="iconbtn" id="collapse" title="收合" aria-label="收合">${ICON.collapse}</button>
    </div>
    <div class="railbody" id="railbody">${body}</div>`;
  $('#tabF').addEventListener('click', pick('fill'));
  $('#tabK').addEventListener('click', pick('check'));
  $('#tabL').addEventListener('click', pick('log'));
  $('#collapse').addEventListener('click', () => { S.railOpen = false; renderRail(); });
  el.querySelectorAll('.todo').forEach((b) => b.addEventListener('click', () => {
    const item = todo[Number(b.dataset.t)];
    showInDoc(item.find, true);
    askAbout(item);
  }));
  el.querySelectorAll('.card.guess .text').forEach((t, i) => t.addEventListener('click', () => showInDoc(check[i].find)));
  el.querySelectorAll('.okc2').forEach((b) => b.addEventListener('click', () => { b.disabled = true; confirmCheck(check[Number(b.dataset.c)]); }));
}

// a blank to fill: the question goes into the box under the Doc, ready for the answer
function askAbout(item) {
  const input = $('#promptInput');
  if (!input || S.busy) return;
  input.value = `${item.label}是`;
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

function commentsHTML(list) {
  if (!list.length) return '<div class="empty">沒有留言</div>';
  return list.map((c) => {
    const done = S.resolved.has(c.n);
    return `<div class="card${S.cfocus === c.n ? ' focus' : ''}${done ? ' done' : ''}" data-n="${c.n}" data-id="${esc(c.id)}">
      <div class="top"><span class="num">${c.n}</span><span class="who">${esc(c.who)}</span><span class="at">${esc(c.at)}</span>
        <span style="flex:1"></span>
        ${done ? '<span style="font-size:11px;color:var(--green)">已解決</span>'
               : `<button class="okc" title="標記為已解決" aria-label="標記為已解決">${ICON.check}</button>`}</div>
      ${c.quote ? `<div class="quote">${esc(c.quote)}</div>` : ''}
      <div class="text">${esc(c.text)}</div>
      ${(c.replies || []).map((r) => `<div class="rep"><b>${esc(r.who)}</b>　${esc(r.text)}</div>`).join('')}
      ${done ? '' : '<input aria-label="回覆這則留言" placeholder="回覆">'}
    </div>`;
  }).join('');
}

function wireComments() {
  $('#railbody').querySelectorAll('.card').forEach((card) => {
    const n = Number(card.dataset.n);
    const id = card.dataset.id;
    const ok = card.querySelector('.okc');
    if (ok) ok.addEventListener('click', async () => {
      ok.disabled = true;
      try {
        await call('resolve', { id: S.sel, comment: id });
        S.resolved.add(n);
        unmarkAnchor(n);
        renderRail();
        refreshLog();
      } catch (e) { showAlert(e.message); ok.disabled = false; }
    });
    const input = card.querySelector('input');
    if (input) input.addEventListener('keydown', async (e) => {
      if (e.key !== 'Enter' || e.isComposing || !input.value.trim()) return;
      const text = input.value.trim();
      input.disabled = true;
      try {
        const r = await call('reply', { id: S.sel, comment: id, text });
        const c = S.d.comments.find((x) => x.id === id);
        c.replies = [...(c.replies || []), r.reply];
        renderRail();
        refreshLog();
      } catch (err) { showAlert(err.message); input.disabled = false; }
    });
  });
}

function unmarkAnchor(n) {
  const el = docEl();
  if (!el) return;
  el.querySelectorAll(`.anchor[data-c="${n}"]`).forEach((a) => a.classList.remove('anchor'));
  el.querySelectorAll('sup.cnum').forEach((s) => { if (s.textContent === String(n)) s.remove(); });
}

function focusComment(n) {
  S.cfocus = n; S.railOpen = true; S.tab = 'comments';
  renderRail();
  docEl().querySelectorAll('.anchor').forEach((a) => a.classList.toggle('focus', Number(a.dataset.c) === n));
  const card = $(`.card[data-n="${n}"]`);
  if (card) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function logHTML(list) {
  if (!list.length) return '<div class="empty">還沒有紀錄</div>';
  return list.map((g) => `<div class="logrow ${esc(g.kind || '')}"><span class="when">${esc(clock(g.at))}</span>
    <span class="what"><b>${esc(g.who)}</b>　${esc(g.text)}</span></div>`).join('');
}

async function refreshLog() {
  const id = S.sel;
  try {
    const r = await call('log', { id });
    if (S.sel !== id || !S.d) return;
    S.d.log = r.log || [];
    if (docsMode() || (S.tab || (openComments().length ? 'comments' : 'log')) === 'log') renderRail();
  } catch (e) { /* the log is only a view */ }
}

// --- talking to Claude about the minutes -----------------------------------------------------

// The box stays put while the lines above it change, so text being typed (and an input method's unfinished
// syllables) survives Claude's answer and what a refresh learned.
function renderAsk() {
  const el = $('#ask');
  if (!el) return;
  if (!$('#promptInput')) {
    // files, links and pictures need the Google Doc: they go to Drive and into its 「八、補充資訊」
    const canAttach = !!(S.d && S.d.doc_url && !S.d.readonly);
    el.innerHTML = `<div id="askTop"></div>
      <div class="quick">${QUICK.map(([k, hint]) => `<button class="qk" title="${esc(hint)}" data-k="${esc(k)}">${esc(k)}</button>`).join('')}</div>
      <div id="attachBox"></div>
      <div class="prompt with-tools">
        <div class="mwrap"><button class="model" id="aiPick" title="換一個 AI 整理會議記錄" aria-label="換一個 AI 整理會議記錄"
            aria-haspopup="menu"></button><div class="mmenu" id="aiMenu" role="menu" hidden></div></div><span class="sep"></span>${canAttach ? `
        <div class="awrap"><button class="ib" id="attachPlus" title="加上附件或超連結" aria-label="加上附件或超連結" aria-haspopup="menu">${ICON.plus}</button>
          <div class="amenu" id="attachMenu" role="menu" hidden>
            <button role="menuitem" data-a="file">${ICON.clip}<span>上傳檔案</span></button>
            <button role="menuitem" data-a="link">${ICON.link}<span>貼上超連結</span></button></div></div>
        <button class="ib" id="attachImage" title="插入圖片" aria-label="插入圖片">${ICON.image}</button>` : ''}
        <input id="promptInput" aria-label="跟 ${aiName()} 說要改什麼" placeholder="跟 ${aiName()} 說要改什麼，例如：主持人是王小明">
        <button class="send" id="askGo" aria-label="送出">${ICON.up}</button></div>`;
    const input = $('#promptInput');
    const go = () => (S.attach.length ? sendAttach(input.value.trim()) : ask(input.value.trim()));
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) go(); });
    $('#askGo').addEventListener('click', go);
    el.querySelectorAll('.qk').forEach((b) => b.addEventListener('click', () => ask('', b.dataset.k)));
    $('#aiPick').addEventListener('click', (e) => {
      e.stopPropagation();
      S.aiOpen = !S.aiOpen;
      renderAiMenu();
      if (S.aiOpen) loadAiStates();
    });
    $('#aiMenu').addEventListener('click', (e) => {
      e.stopPropagation();
      const b = e.target.closest('.mi');
      if (b && !b.disabled) switchAi(b.dataset.ai);
    });
    if (canAttach) {
      $('#attachPlus').addEventListener('click', (e) => { e.stopPropagation(); S.menuOpen = !S.menuOpen; renderAttachMenu(); });
      $('#attachImage').addEventListener('click', () => pickAttach('image'));
      el.querySelectorAll('#attachMenu button').forEach((b) => b.addEventListener('click', () => {
        if (b.dataset.a === 'file') return pickAttach('file');
        S.menuOpen = false; S.urlOpen = true; renderAttachMenu(); renderAttach();
      }));
    }
    renderAttach();
  }
  $('#promptInput').disabled = S.busy;
  el.querySelectorAll('.qk, .ib').forEach((b) => { b.disabled = S.busy; });
  if (S.busy) S.aiOpen = false;
  renderAiMenu();
  renderLearned();
}

// Claude, Codex or Antigravity: the AI chosen here or in 環境設定自檢 writes and changes the minutes
function aiName() { return (S.d && S.d.ai_name) || 'Claude'; }
function aiKey() { return (S.d && S.d.ai) || 'claude'; }
const AI_SHORT = { claude: 'Claude', codex: 'Codex', antigravity: 'Antigravity' };

// left of the prompt box: the AI in use, and a menu to change it; the ones not installed or not signed in here are
// greyed out (S.aiStates, asked when the window opens and again when the menu opens a minute later)
function renderAiMenu() {
  const btn = $('#aiPick');
  const menu = $('#aiMenu');
  if (!btn || !menu) return;
  const key = aiKey();
  const have = (S.d && S.d.ai_installed) || [key];
  const states = (S.aiStates && S.aiStates.ais) || {};
  btn.innerHTML = `<i class="dot ${key}"></i>${esc(aiName())}${ICON.chevU}`;
  btn.disabled = S.busy || S.aiSaving;
  btn.classList.toggle('on', !!S.aiOpen);
  menu.hidden = !S.aiOpen;
  placeDoc();
  menu.innerHTML = '<div class="mhead">AI模型</div>' + AIS.map(([k]) => {
    const why = !have.includes(k) || states[k] === 'install' ? 'install' : states[k] === 'login' ? 'login' : '';
    const off = why && k !== key;
    return `<button class="mi${off ? ' off' : ''}" role="menuitemradio" aria-checked="${k === key}" data-ai="${k}"${off ? ' disabled' : ''}>
      <i class="dot ${k}"></i><span class="mn">${AI_SHORT[k]}</span>${k === key ? `<span class="ck">${ICON.check}</span>` : ''}
      ${why ? `<span class="ms">${why === 'install' ? '這台電腦還沒安裝' : '還沒登入'}</span>` : ''}</button>`;
  }).join('');
  const input = $('#promptInput');
  if (input && !S.attach.length) {
    input.placeholder = `跟 ${aiName()} 說要改什麼，例如：主持人是王小明`;
    input.setAttribute('aria-label', `跟 ${aiName()} 說要改什麼`);
  }
}

async function loadAiStates() {
  if (S.aiStates && Date.now() - S.aiStates.at < 60 * 1000) return;
  try {
    const r = await call('aiStates');
    S.aiStates = { at: Date.now(), ais: r.ais || {} };
    renderAiMenu();
  } catch (e) { /* the menu falls back to what is installed */ }
}

function showAi(key) {
  if (S.d) { S.d.ai = key; S.d.ai_name = AI_SHORT[key]; }
  renderAiMenu();
  renderLearned();
}

// kept in settings.json, so recordings are also written up by it; one that is not signed in is not kept
async function switchAi(key) {
  const was = aiKey();
  S.aiOpen = false;
  if (key === was || S.busy || S.aiSaving) return renderAiMenu();
  S.aiSaving = true;
  showAi(key);
  try {
    const r = await call('setupAI', { ai: key });
    if (r.ai && r.ai.state === 'login') {
      await call('setupAI', { ai: was }).catch(() => {});
      showAi(was);
      showAlert(`${AI_SHORT[key]} 在這台電腦還沒登入，所以會議記錄還是用 ${AI_SHORT[was]} 修改。到「環境設定自檢」第 5 項登入 ${AI_SHORT[key]} 以後，就能換成它。`);
    } else if (S.setup) S.setup.ai = r.ai;
  } catch (e) {
    showAi(was);
    showAlert(e.message);
  } finally {
    S.aiSaving = false;
    renderAiMenu();
  }
}

// --- 附件: files, links and pictures for 「八、補充資訊」 ------------------------------------------

function renderAttachMenu() {
  const menu = $('#attachMenu');
  if (!menu) return;
  menu.hidden = !S.menuOpen;
  $('#attachPlus').classList.toggle('on', S.menuOpen);
}
document.addEventListener('click', (e) => {
  if (S.menuOpen && !e.target.closest('#attachMenu')) { S.menuOpen = false; renderAttachMenu(); }
  if (S.aiOpen && !e.target.closest('#aiMenu')) { S.aiOpen = false; renderAiMenu(); }
});

// what was picked, above the box; each one can be taken off again
function renderAttach() {
  const box = $('#attachBox');
  if (!box) return;
  const items = S.attach;
  const icon = { image: ICON.image, link: ICON.link, file: ICON.clip };
  box.innerHTML = `${items.length ? `<div class="achips">${items.map((it, i) => `<span class="achip" title="${esc(it.name)}">
      ${icon[it.kind]}<span class="an">${esc(it.name)}</span>
      ${S.busy ? '' : `<button class="ax" data-i="${i}" aria-label="移除">✕</button>`}</span>`).join('')}</div>` : ''}
    ${S.urlOpen ? `<div class="aurl"><input id="attachUrl" aria-label="網址" placeholder="貼上網址">
      <button class="btn" id="attachUrlAdd">加入</button></div>` : ''}`.trim();
  box.querySelectorAll('.ax').forEach((b) => b.addEventListener('click', () => {
    S.attach.splice(Number(b.dataset.i), 1);
    renderAttach();
  }));
  const url = $('#attachUrl');
  if (url) {
    const add = () => {
      const u = url.value.trim();
      if (!/^https?:\/\/\S+$/.test(u)) { showAlert('網址要用 http:// 或 https:// 開頭。'); return; }
      S.attach.push({ kind: 'link', url: u, name: u });
      S.urlOpen = false;
      renderAttach();
      $('#promptInput').focus();
    };
    url.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.isComposing) add();
      if (e.key === 'Escape') { S.urlOpen = false; renderAttach(); }
    });
    $('#attachUrlAdd').addEventListener('click', add);
    url.focus();
  }
  const input = $('#promptInput');
  if (input) {
    input.placeholder = items.length ? '寫一句這是什麼、誰提供的，例如：Amy 提供的 9 月流量報表'
                                     : `跟 ${aiName()} 說要改什麼，例如：主持人是王小明`;
  }
}

async function pickAttach(kind) {
  S.menuOpen = false;
  renderAttachMenu();
  try {
    const r = await call('pick', { kind });
    for (const f of r.files || []) {
      if (!S.attach.some((a) => a.path === f.path)) S.attach.push({ kind, path: f.path, name: f.name });
    }
    renderAttach();
    const input = $('#promptInput');
    if (input) input.focus();
  } catch (e) { showAlert(e.message); }
}

// the picked items and the sentence about them: one line each in 「八、補充資訊」
async function sendAttach(text) {
  if (S.busy || !S.attach.length) return;
  const id = S.sel;
  if (!(await savedFirst())) return;
  const items = S.attach.map(({ kind, path, url }) => ({ kind, path, url }));
  S.busy = true; S.busyText = '正在把檔案存進雲端硬碟，再寫進第八章⋯';
  S.asked = text || S.attach.map((a) => a.name).join('、'); S.said = ''; S.saidErr = false; S.editSeq++;
  const box = $('#promptInput');
  if (box) box.value = '';
  renderAsk(); renderAttach();
  try {
    const r = await call('attach', { id, text, items });
    if (S.sel !== id || !S.d) return;
    S.attach = []; S.urlOpen = false;
    S.said = r.reply || '';
    afterEdit(r);
  } catch (e) {
    if (S.sel !== id) return;
    S.said = e.message; S.saidErr = true;
  } finally {
    if (S.sel === id) {
      S.busy = false; S.busyText = '';
      renderAsk(); renderAttach(); renderFoot(); refreshLog();
    }
  }
}

// above the box: Claude at work, its answer with 復原, and what it learned from the user's own edits
function renderLearned() {
  const top = $('#askTop');
  if (!top) return;
  const learned = S.learned;
  top.innerHTML = `
    ${S.busy ? `<div class="busy">${ICON.spin}<span>${esc(S.busyText || `${aiName()} 正在修改⋯`)}</span></div>` : ''}
    ${!S.busy && S.said ? `<div class="replyline${S.saidErr ? ' err' : ''}">${S.saidErr ? '' : ICON.done}
        <span class="asked">「${esc(S.asked)}」</span><span class="said">${esc(S.said)}</span>
        ${S.canUndo && !S.saidErr ? '<button class="btn ghost" id="undo" style="height:24px;padding:0 10px;font-size:12px">復原</button>' : ''}</div>` : ''}
    ${learned.length ? `<div class="learn"><div class="lh">${ICON.book}<span>${aiName()} 看過你的修改</span></div>
        ${learned.map((l, i) => {
          const keep = l.kind !== 'once';
          const where = keep && l.off ? '不記' : { term: '寫進詞彙表', pref: '寫進個人偏好', style: '寫進個人偏好', once: '只改這份' }[l.kind];
          return `<div class="lr${keep && l.off ? ' off' : ''}"><span class="lt">${esc(l.text)}</span>
            <span class="tag${keep && !l.off ? '' : ' gray'}">${where}</span><span style="flex:1"></span>
            ${keep ? `<button class="btn ghost" data-i="${i}" style="height:22px;padding:0 8px;font-size:11px">${l.off ? '要記' : '不要記'}</button>` : ''}</div>`;
        }).join('')}</div>` : ''}`.trim();
  const undo = $('#undo');
  if (undo) undo.addEventListener('click', undoLast);
  top.querySelectorAll('.learn button').forEach((b) => b.addEventListener('click', () => toggleLearned(Number(b.dataset.i))));
}

async function ask(text, quick) {
  if (S.busy || (!text && !quick)) return;
  const id = S.sel;
  if (!(await savedFirst())) return;
  S.busy = true; S.asked = quick || text; S.said = ''; S.saidErr = false; S.editSeq++;
  if (docEl()) docEl().contentEditable = 'false';
  const box = $('#promptInput');
  if (box) box.value = '';
  renderAsk();
  try {
    const r = await call(quick ? 'quick' : 'ask', { id, text: quick || text });
    if (S.sel !== id || !S.d) return;
    S.said = r.reply || ''; S.canUndo = !!r.changed || S.canUndo;
    if (r.changed || r.html) afterEdit(r);
  } catch (e) {
    if (S.sel !== id) return;
    S.said = e.message; S.saidErr = true;
  } finally {
    if (S.sel === id) {
      S.busy = false;
      if (docEl()) docEl().contentEditable = editable();
      renderAsk(); renderFoot(); refreshLog();
    }
  }
}

async function undoLast() {
  const id = S.sel;
  if (!(await savedFirst())) return;
  S.busy = true; S.editSeq++; if (docEl()) docEl().contentEditable = 'false'; renderAsk();
  try {
    const r = await call('undo', { id });
    if (S.sel !== id || !S.d) return;
    S.said = ''; S.canUndo = false;
    afterEdit(r);
  } catch (e) {
    S.said = e.message; S.saidErr = true;
  } finally {
    if (S.sel === id) { S.busy = false; if (docEl()) docEl().contentEditable = editable(); renderAsk(); renderFoot(); refreshLog(); }
  }
}

async function toggleLearned(i) {
  const l = S.learned[i];
  try {
    const r = await call(l.off ? 'relearn' : 'unlearn', { id: S.sel, item: l.id });
    S.learned[i] = r.learned;
    renderAsk(); refreshLog();
  } catch (e) { showAlert(e.message); }
}

// --- bottom: open items, recording, buttons --------------------------------------------------

function renderFoot() {
  const el = $('#foot');
  if (!el) return;
  const d = S.d;
  const todo = d.todo || [];
  const check = d.check || [];
  const p = S.player;
  const docs = docsMode();
  el.innerHTML = `
    ${todo.length && !docs ? `<div class="row"><span class="lbl" style="color:var(--red)">待補充 ${todo.length}</span>
      <div class="chips">${todo.map((t, i) => `<button class="chip red" data-t="${i}">${esc(t.label)}</button>`).join('')}</div></div>` : ''}
    ${check.length && !docs ? `<div class="row"><span class="lbl" style="color:var(--yellow-label)">待確認 ${check.length}</span>
      <div class="chips">${check.map((c, i) => `<span class="chip yellow"><span>${esc(c.label)}</span>
        <button class="okbtn" data-c="${i}" title="確認無誤" aria-label="確認無誤">${ICON.checkSmall}</button></span>`).join('')}</div></div>` : ''}
    ${p.open ? `<div class="player">
        <button class="play" id="pp" aria-label="${p.playing ? '暫停' : '播放'}">${p.playing ? ICON.pause : ICON.play}</button>
        <span class="tm" id="ptime">${mmss(p.pos)}</span>
        <div class="bar" id="pbar"><i id="pfill" style="width:${p.dur ? (p.pos / p.dur * 100).toFixed(2) : 0}%"></i></div>
        <span class="dur">${mmss(p.dur)}</span>
        <button class="speed" id="pspeed" aria-label="播放速度">${p.speed}x</button>
        <button class="iconbtn" id="pclose" aria-label="關閉錄音">${ICON.x}</button></div>` : ''}
    <div class="buttons">
      ${d.sent ? `<div class="sentline">${ICON.done}<span>已寄出　${esc(d.sent.at)}　${d.sent.count} 人　${esc(d.sent.format)}</span></div>` : ''}
      <span style="flex:1"></span>
      ${d.doc_url && !docs ? `<button class="btn ghost" id="openGdoc">${ICON.open}<span>在 Google 文件打開</span></button>` : ''}
      ${d.mail && !d.sent ? `<button class="btn primary" id="mailBtn">${ICON.mail}<span>發送信件</span></button>` : ''}
    </div>`;
  el.querySelectorAll('.chip.red').forEach((b) => b.addEventListener('click', () => jumpTo(todo[Number(b.dataset.t)])));
  el.querySelectorAll('.okbtn').forEach((b) => b.addEventListener('click', () => confirmCheck(check[Number(b.dataset.c)])));
  const on = (sel, fn) => { const x = $(sel); if (x) x.addEventListener('click', fn); };
  on('#openGdoc', () => call('link', { url: d.doc_url }).catch(() => {}));
  on('#mailBtn', openMail);
  on('#pp', () => audio(S.player.playing ? 'pause' : 'play', { at: S.player.pos }));
  on('#pspeed', () => audio('rate', { rate: S.player.speed === 1 ? 1.5 : S.player.speed === 1.5 ? 2 : 1 }));
  on('#pclose', () => audio('stop'));
  const bar = $('#pbar');
  if (bar) bar.addEventListener('click', (e) => {
    const r = bar.getBoundingClientRect();
    audio('play', { at: S.player.dur * Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) });
  });
}

async function confirmCheck(item) {
  S.editSeq++;
  try {
    const r = await call('confirm', { id: S.sel, item: item.label });
    S.d.check = r.check || [];
    if (r.learned && r.learned.length) { S.learned.push(...r.learned); renderAsk(); }
    renderFoot(); renderRail(); refreshLog();
  } catch (e) { showAlert(e.message); }
}

function audio(action, args = {}) {
  if (action === 'stop') { S.player.open = false; S.player.playing = false; renderFoot(); markPlaying(); }
  if (action === 'play') { S.player.open = true; }
  if (action === 'rate') { S.player.speed = args.rate; renderFoot(); }
  call('audio', { id: S.sel, action, ...args }).catch((e) => showAlert(e.message));
  if (action === 'play') renderFoot();
}

window.onEvent = (name, data) => {
  if (name === 'jobs' && data && 'recording' in data && !!data.recording !== !!S.recording) {
    S.recording = !!data.recording;
    renderVersion();
  }
  if (name === 'jobs') { loadList().then(() => {
    const job = S.jobs.find((j) => j.id === S.sel);
    if (S.d && job && job.status !== S.d.status && !(S.d.status === 'ready' && job.status === 'sent')) select(S.sel);
  }); }
  if (name === 'select' && (data.id !== S.sel || !S.d)) select(data.id);
  if (name === 'docfail' && docsMode()) { S.docFailed = true; renderMain(); }
  if (name === 'setup') openSetup();
  if (name === 'player') {
    const p = S.player;
    const wasPlaying = p.playing;
    p.pos = data.pos; p.dur = data.dur || p.dur; p.playing = !!data.playing; p.speed = data.rate || p.speed;
    const t = $('#ptime'); const f = $('#pfill');
    if (t && wasPlaying === p.playing) { t.textContent = mmss(p.pos); if (f) f.style.width = p.dur ? (p.pos / p.dur * 100).toFixed(2) + '%' : '0'; }
    else { renderFoot(); markPlaying(); }
  }
};

// --- sheets ----------------------------------------------------------------------------------

function closeSheet() { S.sheet = null; $('#sheet').innerHTML = ''; placeDoc(); }

// the transcript, each line with who said it (by voice). A voice not named yet shows as 講者 A; clicking a
// name asks who it is, for every line of that voice or just this line, and the app remembers the voice
const TINTS = [['#dbe8fd', '#1c4f9e'], ['#fde8d7', '#9a4a07'], ['#ece3fb', '#5b2d9e'], ['#dff3e3', '#14532d'],
               ['#fde2ec', '#9d1b4f'], ['#d9f2f2', '#0f5e5e']];
function voiceStyle(group, named) {
  const at = Math.max(0, (S.d.voices || []).findIndex((v) => v.group === group));
  const [bg, fg] = TINTS[at % TINTS.length];
  return named ? `background:${bg};color:${fg}` : `background:transparent;color:${fg};border:1px dashed ${fg}`;
}

function openTranscript(keep = {}) {
  const d = S.d;
  const voices = d.voices || [];
  const before = $('#sheet .lines');
  const scrolled = before ? before.scrollTop : 0;
  S.sheet = 'transcript';
  placeDoc();
  const ask = keep.ask;
  const askVoice = ask ? voices.find((v) => v.group === ask.group) : null;
  const askLabel = ask && ask.line != null ? (d.transcript[ask.line].who || (askVoice && askVoice.label)) : askVoice && askVoice.label;
  const names = [...new Set([...(d.voice_names || []), ...voices.filter((v) => v.name).map((v) => v.name)])];
  $('#sheet').innerHTML = `<div class="veil"><div class="sheet" role="dialog" aria-label="逐字稿">
    <div style="display:flex;align-items:baseline;gap:10px"><h3>逐字稿</h3><span style="font-size:12px;color:var(--muted)">${esc(d.title)}　${esc(shortDay(d))}</span></div>
    ${voices.length ? `<div class="vchips">${voices.map((v) => `<button class="vchip" data-g="${esc(v.group)}" style="${voiceStyle(v.group, v.name)}">${esc(v.label)}<span>${v.minutes} 分鐘</span></button>`).join('')}</div>` : ''}
    ${ask ? `<div class="vname">
      <div class="vrow"><b>${esc(askLabel)} 是誰？</b><span style="flex:1"></span><button class="btn ghost" id="vplay">${S.player.playing ? '■ 停止播放' : '▶ 聽一段聲音'}</button></div>
      <div class="vrow">${names.map((n) => `<button class="vsug" data-n="${esc(n)}">${esc(n)}</button>`).join('')}<input id="vinput" maxlength="30" placeholder="輸入名字" aria-label="輸入名字"></div>
      <div class="vrow"><button class="btn primary" id="vall">套用到這位的每一句</button>${ask.line != null ? '<button class="btn ghost" id="vone">只改這一句</button>' : ''}<button class="btn ghost" id="vcancel">取消</button></div>
    </div>` : ''}
    ${keep.toast ? `<div class="vtoast">${esc(keep.toast)}</div>` : ''}
    <div class="lines">${(d.transcript || []).map((t, i) => `<div><button class="tm" data-i="${i}" title="從這裡開始聽">${esc(t.at)}</button>${t.who ? `<button class="who" data-g="${esc(t.group || '')}" data-line="${i}" style="${voiceStyle(t.group, !t.who.startsWith('講者 '))}">${esc(t.who)}</button>` : ''}<span>${esc(t.text)}</span></div>`).join('')}</div>
    <div style="display:flex;justify-content:flex-end"><button class="btn ghost" id="closeT">關閉</button></div></div></div>`;
  $('#sheet .lines').scrollTop = scrolled;
  $('#closeT').addEventListener('click', closeSheet);
  $('#sheet').querySelectorAll('.lines .tm').forEach((b) => b.addEventListener('click', () => {
    closeSheet();
    audio('play', { at: d.transcript[Number(b.dataset.i)].sec });
  }));
  $('#sheet').querySelectorAll('.vchip').forEach((b) => b.addEventListener('click', () => openTranscript({ ask: { group: b.dataset.g, line: null } })));
  $('#sheet').querySelectorAll('.lines .who').forEach((b) => b.addEventListener('click', () => openTranscript({ ask: { group: b.dataset.g, line: Number(b.dataset.line) } })));
  if (!ask) return;
  let picked = '';
  const input = $('#vinput');
  $('#sheet').querySelectorAll('.vsug').forEach((b) => b.addEventListener('click', () => {
    picked = b.dataset.n; input.value = '';
    $('#sheet').querySelectorAll('.vsug').forEach((x) => x.classList.toggle('on', x === b));
  }));
  input.addEventListener('input', () => { picked = ''; $('#sheet').querySelectorAll('.vsug').forEach((x) => x.classList.remove('on')); });
  $('#vcancel').addEventListener('click', () => openTranscript());
  $('#vplay').addEventListener('click', () => {
    if (S.player.playing) audio('pause', { at: S.player.pos });
    else if (askVoice) audio('play', { at: ask.line != null ? d.transcript[ask.line].sec : askVoice.sample[0] });
    setTimeout(() => { const b = $('#vplay'); if (b) b.textContent = S.player.playing ? '■ 停止播放' : '▶ 聽一段聲音'; }, 600);
  });
  const apply = async (oneLine) => {
    const name = (picked || input.value).trim();
    if (!name) { input.focus(); return; }
    try {
      const r = await call('speaker', { id: S.sel, group: ask.group, name, ...(oneLine ? { line: ask.line } : {}) });
      d.transcript = r.transcript || d.transcript;
      d.voices = r.voices || d.voices;
      d.voice_names = r.voice_names || d.voice_names;
      openTranscript({ toast: oneLine ? '' : `已記住 ${name} 的聲音，下次開會會自動標上名字` });
      refreshLog();
    } catch (e) { showAlert(e.message); }
  };
  $('#vall').addEventListener('click', () => apply(false));
  if ($('#vone')) $('#vone').addEventListener('click', () => apply(true));
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); apply(false); } });
}

// a Word or PDF attachment: the mail says 詳細如附件 where the Doc's address was (Vin 2026-10-15), and the
// address comes back when the Google 文件連結 is picked again
const DOC_URL = /[:：]?[ \t]*\n?[ \t]*https:\/\/docs\.google\.com\/document\/[^\s]+/;
const ATTACHED = '，詳細如附件。';
function withAttachment(body) {
  return DOC_URL.test(body) ? body.replace(DOC_URL, ATTACHED).replace(/。，詳細如附件。/, ATTACHED) : body;
}
function withLink(body, url) {
  if (DOC_URL.test(body)) return body;
  return body.includes(ATTACHED) ? body.replace(ATTACHED, `：\n${url}`) : `${body.trimEnd()}\n\n${url}`;
}

function openMail() {
  const m = S.d.mail;
  S.mail = { to: [...m.to], subject: m.subject, body: m.body, linkBody: m.body, fmt: 'gdoc', info: '', sending: false, err: '',
             files: S.d.attach_files || 0 };
  S.sheet = 'mail';
  placeDoc();
  renderMail();
}

function renderMail() {
  const m = S.mail;
  const d = S.d;
  $('#sheet').innerHTML = `<div class="veil"><div class="sheet" role="dialog" aria-label="發送信件">
    <h3>發送信件</h3>
    <div class="grid">
      <span class="k">寄件人</span><span>${esc(d.mail.from)}</span>
      <span class="k" style="align-self:start;padding-top:6px">收件人</span>
      <div class="field tokens" id="tokens">${m.to.map((a, i) => `<span class="token"><span>${esc(a)}</span>
        <button data-i="${i}" aria-label="移除這位收件人">${ICON.xs}</button></span>`).join('')}
        <input id="addTo" aria-label="加收件人" placeholder="加收件人"></div>
      <label class="k" for="subj">主旨</label><input class="field" id="subj" value="${esc(m.subject)}">
      <span class="k">附件</span>
      <div style="display:flex;align-items:center;gap:10px"><div class="seg" role="radiogroup" aria-label="附件">
        ${FORMATS.map(([k, l]) => `<button role="radio" aria-checked="${m.fmt === k}" class="${m.fmt === k ? 'on' : ''}" data-f="${k}">${l}</button>`).join('')}</div>
        <span style="font-size:12px;color:var(--muted)">${esc(m.info)}</span></div>
    </div>
    <textarea id="body" aria-label="信件內容">${esc(m.body)}</textarea>
    <div style="display:flex;align-items:center;gap:10px">
      <span class="note${m.err ? ' err' : ''}">${esc(m.err || ((m.fmt === 'gdoc' ? '收件人可以在 Google 文件上加註' : '收件人會收到附件，不會拿到 Google 文件的連結')
        + (m.files ? `，也可以打開第八章的 ${m.files} 個檔案` : '')))}</span>
      <button class="btn ghost" id="mailCancel"${m.sending ? ' disabled' : ''}>取消</button>
      <button class="btn primary" id="mailSend"${m.sending ? ' disabled' : ''}>${m.sending ? '寄出中⋯' : '寄出'}</button></div>
  </div></div>`;
  const keep = () => { m.subject = $('#subj').value; m.body = $('#body').value; };
  $('#tokens').querySelectorAll('.token button').forEach((b) => b.addEventListener('click', () => { keep(); m.to.splice(Number(b.dataset.i), 1); renderMail(); }));
  const add = $('#addTo');
  const addTokens = () => {
    const parts = add.value.split(/[,，、;\s]+/).map((t) => t.trim().toLowerCase()).filter((t) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(t));
    if (!parts.length) return false;
    keep();
    for (const a of parts) if (!m.to.includes(a)) m.to.push(a);
    renderMail();
    $('#addTo').focus();
    return true;
  };
  add.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ',') && !e.isComposing) { e.preventDefault(); addTokens(); } });
  add.addEventListener('blur', () => { if (add.value.trim()) addTokens(); });
  $('#subj').addEventListener('input', keep);
  $('#body').addEventListener('input', keep);
  $('#sheet').querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', async () => {
    keep();
    const before = m.fmt;
    m.fmt = b.dataset.f; m.info = m.fmt === 'gdoc' ? '' : '準備附件中⋯'; m.err = '';
    if (before === 'gdoc' && m.fmt !== 'gdoc') { m.linkBody = m.body; m.body = withAttachment(m.body); }
    if (before !== 'gdoc' && m.fmt === 'gdoc') {
      m.body = m.body === withAttachment(m.linkBody) ? m.linkBody : withLink(m.body, S.d.doc_url || '');
    }
    renderMail();
    if (m.fmt === 'gdoc') return;
    const fmt = m.fmt;
    try {
      const r = await call('mailPrepare', { id: S.sel, to: m.to, subject: m.subject, body: m.body, format: fmt });
      if (m.fmt === fmt) { m.info = `${r.attachment}　${r.attachment_kb} KB`; renderMail(); }
    } catch (e) { if (m.fmt === fmt) { m.info = ''; m.err = e.message; renderMail(); } }
  }));
  $('#mailCancel').addEventListener('click', () => { if (!m.sending) closeSheet(); });
  $('#mailSend').addEventListener('click', sendMail);
}

async function sendMail() {
  const m = S.mail;
  if (m.sending) return;
  m.subject = $('#subj').value; m.body = $('#body').value;
  if (!m.to.length) { m.err = '至少要有一位收件人。'; renderMail(); return; }
  await flush();
  if (S.dirty) { m.err = '紀錄改過的內容還沒存好，存好之後再寄出。'; renderMail(); return; }
  m.sending = true; m.err = '';
  renderMail();
  const id = S.sel;
  try {
    const r = await call('send', { id, to: m.to, subject: m.subject, body: m.body, format: m.fmt });
    if (S.sel !== id) return;
    S.d.sent = r.sent;
    closeSheet();
    renderFoot();
    loadList();
    refreshLog();
  } catch (e) {
    m.sending = false; m.err = e.message;
    if (S.sheet === 'mail') renderMail();
  }
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && S.aiOpen) { S.aiOpen = false; renderAiMenu(); return; }
  if (e.key === 'Escape' && S.sheet && !(S.mail && S.mail.sending)) closeSheet();
});

// --- 環境設定自檢 ------------------------------------------------------------------------------------
// what this computer still needs: two items macOS answers (microphone, notifications), eight setup_check.py does

// [key, icon, icon colour, name, needed, the one line shown while it is not done yet, button]
const SETUP = [
  ['mic', '🎙', '#fde8e7', '麥克風', true, '錄音時要用', '允許'],
  ['notify', '🔔', '#fdf3d7', '通知', false, '會議記錄整理好時通知你', '允許'],
  ['speech', '📝', '#e3ecfd', '語音轉文字模型', true, '約 1.6 GB', '下載'],
  ['voice', '👥', '#ece3fb', '聲紋識別模型', false, '約 28 MB', '下載'],
  ['ai', '🤖', '#fde8d7', '內容生成模型', true, '選一個 AI，在這台電腦安裝並登入', ''],
  ['client', '🔑', '#eef0f2', 'Google 連線設定', false, '約 15 分鐘，有步驟帶著做', '開始設定'],
  ['login', '👤', '#eef0f2', 'Google 帳號登入', false, '用公司的 Google 帳號', '登入'],
  ['docs', '📄', '#e3ecfd', 'Google 文件與雲端硬碟', false, '', '開啟'],
  ['gmail', '✉', '#fde8e7', 'Gmail', false, '', '開啟'],
  ['calendar', '📅', '#dff3e3', 'Google 行事曆', false, '', '開啟'],
];
const AIS = [['claude', 'Claude Code'], ['codex', 'Codex'], ['antigravity', 'Antigravity']];
const GOOGLE_STEPS = [
  ['建立 Google Cloud 專案', '用公司的 Google 帳號登入，專案名稱可以自己取，例如 meeting-minutes。',
   'https://console.cloud.google.com/projectcreate'],
  ['開啟會用到的五個 API', '打開之後確認上方選的是第 1 步的專案，再按「啟用」。',
   'https://console.cloud.google.com/flows/enableapi?apiid=drive.googleapis.com,docs.googleapis.com,gmail.googleapis.com,calendar-json.googleapis.com,people.googleapis.com'],
  ['設定 OAuth 同意畫面', '按「開始」，應用程式名稱可以自己取。用公司帳號的話，目標對象選「內部」；用個人 Gmail 的話選「外部」，再把自己的信箱加進測試使用者。',
   'https://console.cloud.google.com/auth/overview'],
  ['建立用戶端，下載 JSON 檔', '應用程式類型選「電腦版應用程式」，建立之後按「下載 JSON」。',
   'https://console.cloud.google.com/auth/clients/create'],
];

function openSetup() {
  S.sheet = 'setup'; S.setupGuide = false;
  placeDoc();
  renderSetup();
  refreshSetup();
}

// one check at a time; a click meanwhile asks for one more, and an answer from before the click is not shown.
// While something downloads (or the Google login waits), only that is asked again every few seconds.
async function refreshSetup(progress = false) {
  if (S.sheet !== 'setup') return;
  if (S.setupAsking) { S.setupAgain = true; return; }
  S.setupAsking = true;
  const seq = S.setupSeq;
  const was = Object.fromEntries(['speech', 'voice', 'login'].map((k) => [k, ((S.setup || {})[k] || {}).state]));
  let got = null, err = '';
  try { got = await call('setupState', { progress }); } catch (e) { err = e.message; }
  S.setupAsking = false;
  const stale = seq !== S.setupSeq;
  if (!stale) {
    const running = got && progress ? Object.fromEntries(Object.entries(got).filter(([, v]) => v.state !== 'ended')) : got;
    if (got) S.setup = progress && S.setup ? { ...S.setup, ...running } : got;
    S.setupErr = err;
  }
  if (S.sheet !== 'setup') return;
  renderSetup();
  clearTimeout(S.setupTimer);
  const st = S.setup || {};
  // a job that was running and is not any more: everything is checked once again
  const ended = progress && got && ['speech', 'voice', 'login'].some((k) => was[k] === 'loading' && got[k] && got[k].state === 'ended');
  if (S.setupAgain || stale || ended) { S.setupAgain = false; return refreshSetup(); }
  const waiting = ['speech', 'voice', 'login'].some((k) => st[k] && st[k].state === 'loading');
  if (waiting) S.setupTimer = setTimeout(() => refreshSetup(true), 2500);   // a download or the login is on its way
}
window.addEventListener('focus', () => { if (S.sheet === 'setup') refreshSetup(); });   // back from the browser

function setupSide(key, it, label) {
  const st = (S.setup || {})[key] || {};
  const btn = (text, act, extra = '') => `<button class="btn primary sbtn" data-k="${key}" data-act="${act}"${extra}>${esc(text)}</button>`;
  switch (st.state) {
    case 'done': return '<span class="sok">✓ 已完成</span>';
    case 'denied': return '<span class="sbad">✕ 未開啟</span><button class="slink" data-k="' + key + '" data-act="settings">打開系統設定</button>';
    case 'locked': return `<span class="slock">${key === 'login' ? '先完成 Google 連線設定' : '先完成 Google 帳號登入'}</span>`;
    case 'loading':
      if (key === 'login') return '<span class="swait">請在瀏覽器完成登入⋯</span>';
      return `<span class="swait">下載中 ${st.pct || 0}%</span><div class="sbar"><i style="width:${st.pct || 0}%"></i></div>`;
    case 'install': return btn('安裝說明', 'install');
    case 'login': return btn('登入', 'ailogin');
    case 'unknown': return btn('重新檢查', 'recheck');
    case 'off': return btn('開啟', 'open');
    case 'scope': return btn('重新登入', 'glogin');
    case 'offline': return '<span class="slock">沒有連上網路</span>';
    case 'error': return btn('重新檢查', 'recheck');
    case 'todo': return btn(label, 'do') + (st.failed ? '<span class="slock">上次下載沒有完成</span>' : '');
    default: return '<span class="slock">檢查中⋯</span>';
  }
}

function renderSetup() {
  const el = $('#sheet');
  if (!el || S.sheet !== 'setup') return;
  const st = S.setup;
  if (S.setupGuide) return renderGoogleGuide(el);
  const done = st ? SETUP.filter(([k]) => (st[k] || {}).state === 'done').length : 0;
  const chosen = st && st.ai ? st.ai.ai : 'claude';
  el.innerHTML = `<div class="veil"><div class="sheet setup" role="dialog" aria-label="環境設定自檢">
    <div class="shead"><h3>Vinutes 需要的設定</h3></div>
    ${S.setupErr ? `<div class="sinfo err">${esc(S.setupErr)}</div>` : ''}
    <div class="slist">${SETUP.map(([k, icon, bg, title, req, desc, label], i) => `<div class="srow">
      <div class="sico" style="background:${bg}">${icon}</div>
      <div class="stxt"><div class="stt">${i + 1}. ${esc(title)}${req ? '<span class="sreq">必要</span>' : ''}</div>
        ${desc && st && st[k] && st[k].state !== 'done' ? `<div class="sds">${esc(desc)}</div>` : ''}
        ${k === 'ai' ? `<div class="spills">${AIS.map(([a, n]) => `<button class="spill${a === chosen ? ' on' : ''}" data-ai="${a}">${n}</button>`).join('')}</div>` : ''}
        ${k === 'login' && st && st.login && st.login.email ? `<div class="sds">${esc(st.login.email)}</div>` : ''}</div>
      <div class="sside">${st ? setupSide(k, null, label) : '<span class="slock">檢查中⋯</span>'}</div></div>`).join('')}</div>
    <div class="sfoot"><span class="scount">已完成 ${done} / ${SETUP.length}</span><button class="btn ghost" id="closeS">關閉</button></div>
  </div></div>`;
  $('#closeS').addEventListener('click', () => { clearTimeout(S.setupTimer); closeSheet(); });
  el.querySelectorAll('.sbtn, .slink').forEach((b) => b.addEventListener('click', () => setupAct(b.dataset.k, b.dataset.act)));
  el.querySelectorAll('.spill').forEach((b) => b.addEventListener('click', () => chooseAi(b.dataset.ai)));
}

async function setupAct(key, act) {
  const st = (S.setup || {})[key] || {};
  S.setupSeq++;
  try {
    if (key === 'mic' || key === 'notify') await call(key === 'mic' ? 'setupMic' : 'setupNotify');
    else if (act === 'install') await call('setupOpen', { url: st.install_url });
    else if (act === 'ailogin') await call('setupAILogin', { ai: st.ai });
    else if (act === 'open') await call('setupOpen', { url: st.url });
    else if (act === 'glogin' || key === 'login') await call('setupRun', { what: 'login' });
    else if (key === 'speech' || key === 'voice') await call('setupRun', { what: key });
    else if (key === 'client') { S.setupGuide = true; return renderSetup(); }
  } catch (e) { showAlert(e.message); }
  refreshSetup();
}

async function chooseAi(key) {
  if (!S.setup || (S.setup.ai && S.setup.ai.ai === key)) return;
  const before = S.setup.ai;
  S.setupSeq++;
  S.setup.ai = { state: '', ai: key };
  renderSetup();
  try {
    const r = await call('setupAI', { ai: key });
    S.setup.ai = r.ai;
    showAi(key);
  } catch (e) { S.setup.ai = before; showAlert(e.message); }
  renderSetup();
}

// item 6, step by step: each step opens its Google Cloud page; the last one takes the downloaded file
function renderGoogleGuide(el) {
  el.innerHTML = `<div class="veil"><div class="sheet setup" role="dialog" aria-label="Google 連線設定">
    <div class="shead"><h3>Google 連線設定</h3><div class="ssub">照順序做完四個步驟，最後選擇下載的 JSON 檔。</div></div>
    <div class="slist">${GOOGLE_STEPS.map(([title, desc], i) => `<div class="srow">
      <div class="sico snum">${i + 1}</div>
      <div class="stxt"><div class="stt">${esc(title)}</div><div class="sds">${esc(desc)}</div></div>
      <div class="sside"><button class="btn ghost sopen" data-i="${i}">打開這一頁</button></div></div>`).join('')}
      <div class="srow"><div class="sico snum">5</div>
        <div class="stxt"><div class="stt">選擇下載的檔案</div><div class="sds">這個檔案的檔名通常是 client_secret 開頭，會在「下載項目」資料夾裡。</div></div>
        <div class="sside"><button class="btn primary" id="pickClient">選擇檔案</button></div></div></div>
    <div class="sfoot"><span></span><button class="btn ghost" id="backS">回到清單</button></div>
  </div></div>`;
  el.querySelectorAll('.sopen').forEach((b) => b.addEventListener('click', () => {
    call('setupOpen', { url: GOOGLE_STEPS[Number(b.dataset.i)][2] }).catch((e) => showAlert(e.message));
  }));
  $('#backS').addEventListener('click', () => { S.setupGuide = false; renderSetup(); });
  $('#pickClient').addEventListener('click', async () => {
    try {
      const r = await call('setupClient');
      if (r.cancelled) return;
      S.setupGuide = false;
    } catch (e) { showAlert(e.message); return; }
    refreshSetup();
  });
}

// --- start -----------------------------------------------------------------------------------

(async () => {
  await loadList();
  renderMain();
  loadAiStates();
  loadVersion();
  setInterval(loadVersion, 3600 * 1000);
  try {
    const r = await call('ready');
    if (r.setup) openSetup();
    if (r.select) return select(r.select);
  } catch (e) { /* no meeting asked for */ }
  if (!S.sel && S.jobs.length) select(S.jobs[0].id);
})();
