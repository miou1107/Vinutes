// The meeting window of Vinutes: the list of meetings on the left, one meeting on the right.
// Everything that reads or changes a meeting goes through the app (window.webkit.messageHandlers.app), which runs
// scripts/minutes_app.py and answers with window.reply(id, ok, data). The app also calls window.onEvent(name, data):
//   jobs    a recording started, finished or failed: reload the list
//   select  the user picked a meeting in the menu or a notification: show it
//   player  the recording's position while it plays
//   language  the user picked English or 中文: every word on screen is drawn again in that language
'use strict';

// --- words -----------------------------------------------------------------------------------
// strings.js (loaded first) holds every word in both languages; the app sets window.VINUTES_LANG before the page
// loads and sends 'language' when the user switches

let LANG = (window.VINUTES_LANG === 'zh-TW') ? 'zh-TW' : 'en';
const t = (key, ...a) => { const v = (STRINGS[LANG] && key in STRINGS[LANG] ? STRINGS[LANG] : STRINGS.en)[key]; return typeof v === 'function' ? v(...a) : v; };
// a text kept in the state as [key, ...args] is turned into words when it is drawn, so it follows a language switch
const say = (x) => (Array.isArray(x) ? t(...x) : x);

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
  else w.reject(new Error((data && data.message) || t('err_retry')));
};

// --- small helpers ---------------------------------------------------------------------------

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pad = (n) => String(n).padStart(2, '0');
const mmss = (t) => { t = Math.max(0, Math.floor(t)); return t >= 3600 ? `${Math.floor(t / 3600)}:${pad(Math.floor(t % 3600 / 60))}:${pad(t % 60)}` : `${pad(Math.floor(t / 60))}:${pad(t % 60)}`; };
const clock = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const hhmm = () => { const d = new Date(); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
// the key belongs to Zhuyin or another input method: its Enter picks a word and is not a send. WebKit fires that
// keydown after the word is already in the box, with isComposing false but keyCode 229.
const inputMethod = (e) => e.isComposing || e.keyCode === 229;
// the AI is on a request of this meeting; another meeting's requests go on by themselves meanwhile
const aiBusy = (id = S.sel) => !!(S.work[id] && S.work[id].now);
const cut = (s, n = 30) => (s.length > n ? `${s.slice(0, n)}…` : s);

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
  spinWhite: '<svg class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.2-8.6"/></svg>',
  tick: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1e7b34" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  checkSmall: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#1e7b34" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  done: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1e7b34" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8L16 9.8"/></svg>',
  dot: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a1a1a6" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/></svg>',
  collapse: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l6 6-6 6M13 6l6 6-6 6"/></svg>',
  expand: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6l-6 6 6 6M11 6l-6 6 6 6"/></svg>',
  bubble: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
  people: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.2a5 5 0 0 1 5.5 4.8"/></svg>',
  clock: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  up: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  book: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h6"/></svg>',
  play: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#ffffff" aria-hidden="true"><path d="M7 5v14l12-7z"/></svg>',
  pause: '<svg width="12" height="12" viewBox="0 0 24 24" fill="#ffffff" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
  x: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  xs: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
 plusSm: '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  gear: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
  headset: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/></svg>',
  lines: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M4 11h16M4 16h10"/></svg>',
  mail: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>',
  prompt: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
};

const STATUS = { working: 'st_working', ready: 'st_ready', sent: 'st_sent', failed: 'st_failed' };
const statusText = (s) => (STATUS[s] ? t(STATUS[s]) : '');
// the five quick rewrites: the app gets the id, the button shows t('quick_<id>') and t('quick_<id>_hint')
const QUICK = ['short', 'detail', 'formal', 'visual', 'external'];
const FORMATS = ['gdoc', 'word', 'pdf'];          // the label is t('fmt_<key>')
// the project picker's two choices that are not projects (an invisible word joiner first, so no project's name
// can be the same); the <option> value carries them, its text says them in the window's language
const ALL = '\u2060all';
const LOOSE = '\u2060loose';
const ARCHIVED = '\u2060archived';           // 已封存: the meetings the list hides everywhere else
const projName = (p) => (p === ALL ? t('proj_all') : p === LOOSE ? t('proj_loose') : p === ARCHIVED ? t('proj_archived') : p);

// --- state -----------------------------------------------------------------------------------

const S = {
  jobs: [], sel: null, q: '', proj: ALL,
  tag: ALL,                  // the list's 標籤 picker: ALL, or one tag
  tagAdding: false,          // 加標籤 became a box to type the tag in
  pset: null,                // 專案設定: {name, move, adding, busy, err, tab ('brief' | 'name'), brief}
  picking: false, picked: new Set(),   // 選取: the list shows a checkbox on each meeting; picked = the ones checked
  ctx: null,                 // the right-click menu: {ids, x, y}
  del: null,                 // the 刪除 sheet: {ids, busy, err}
  d: null,                   // the open meeting, as minutes_app.py open returned it
  loadError: '',
  tab: null, railOpen: true, cfocus: null, resolved: new Set(),
  dirty: false, saving: null, saveTimer: null, saveText: '', saveErr: false,
  shown: '',                 // which preview the editor holds, so a save is compared with what the user saw
  giveUp: null,              // the meeting the user clicked once while this one had unsaved text
  busy: false, asked: '', askedQuick: '', said: '', saidErr: false, canUndo: false,
  busyText: '',              // the key of what the line above the box says while busy ('' = Claude is rewriting)
  sending: false,            // a sentence is on its way while the user's own edits are saved: a second Enter waits
  work: {},                  // meeting id → { now, waits }: the request the AI is on and the ones sent after it
  peopleLater: {},           // meeting id → { voice: name } picked under 人員 while the AI rewrote it, on its way in
  peopleSending: {},         // meeting id → { group, name } of the one on its way now
  pics: [],                  // pictures pasted or picked beside the box, for the AI to look at with the next sentence
  refs: [],                  // files and links picked with ＋ beside the box, for the AI to read with the next sentence
  askedPic: '',              // the picture that went with the last answered sentence, shown small beside it
  fixing: '', fixText: '', fixFocus: false, fixPick: false,   // the 待確認 item open to type what it should be: its label, the text
  railLate: false,           // the side panel has news it held back while a Fix box had the keyboard
  skipping: new Set(),       // 待確認 items skipped whose answer has not come back (it waits for the AI's turn)
  setupSeq: 0,               // goes up with every click in 環境設定自檢: an older answer is not shown
  att: null,                 // 加入會議附件 open: { items: [{kind, path, url, name, note}], urlOpen, busy, err }
  urlOpen: false, menuOpen: false,
  learned: [], learnOpen: false, learnShown: 0,   // learnOpen: the list of what Claude learned shows six rows instead of two
  banner: null, bannerTimer: null, alert: null,
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
  // the AI and ＋ menus open upward, into the Doc's place: the Doc ends above the open one
  const open = !show ? null : S.aiOpen ? $('#aiMenu') : S.menuOpen ? $('#attachMenu') : null;
  const menu = open && !open.hidden ? open : null;
  let h = menu ? Math.max(0, Math.min(r.height, menu.getBoundingClientRect().top - r.y - 8)) : r.height;
  let y = r.y;
  const projMenu = show && S.pmenu ? $('#projMenu') : null;   // the project list opens downward: the Doc starts below it
  if (projMenu && !projMenu.hidden) {
    const below = projMenu.getBoundingClientRect().bottom + 8;
    if (below > y) { h = Math.max(0, h - (below - y)); y = below; }
  }
  const key = [show, show ? S.d.doc_url : '', Math.round(r.x), Math.round(y), Math.round(r.width), Math.round(h)].join('|');
  if (key === S.placed && !reload) return;
  S.placed = key;
  call('gdoc', { show, reload, url: show ? S.d.doc_url : '', account: show ? S.d.account || '' : '',
                 x: r.x, y, w: r.width, h }).catch(() => {});
}
const docSpot = new ResizeObserver(() => placeDoc());
window.addEventListener('resize', () => (S.pmenu ? renderProjMenu() : placeDoc()));   // the project list follows its name

// what was typed into the Doc: into the minutes, the side panel, and what Claude learns. One at a time per
// meeting; `again` waits for one already on its way and then asks once more (closing the window, leaving a meeting)
function refreshDoc(id = S.sel, again = false) {
  if (!id) return Promise.resolve();
  const running = S.refreshing && S.refreshing.id === id ? S.refreshing.p : null;
  if (running) return again ? running.then(() => refreshDoc(id)) : running;
  const seq = S.editSeq;
  const p = call('refresh', { id }).then((r) => {
    if (r.busy || S.sel !== id || !S.d || !docsMode()) return;
    const seen = () => JSON.stringify([S.d.todo, S.d.check, S.d.log, S.d.attendees, S.d.people, S.d.speakers, S.d.silent, S.d.calendar, S.d.score]);
    const before = seen();
    if (seq === S.editSeq) { S.d.todo = r.todo || []; S.d.check = checkShown(r.check, id); }   // not over a confirm made meanwhile
    if (r.attendees) S.d.attendees = r.attendees;
    if (r.attachments) setAttachments(r.attachments);
    if (r.people && !S.peopleBusy) S.d.people = r.people;
    if (r.speakers && !S.peopleBusy) S.d.speakers = r.speakers;
    if (r.silent && !S.peopleBusy) S.d.silent = r.silent;
    if (r.calendar && !S.peopleBusy) S.d.calendar = r.calendar;
    S.d.log = r.log || [];
    if ('score' in r && JSON.stringify(r.score) !== JSON.stringify(S.d.score)) {
      S.d.score = r.score;
      if (!S.tagAdding) renderTags();               // not while a tag is being typed
    }
    if ('can_undo' in r && !S.busy && !aiBusy(id)) S.canUndo = !!r.can_undo;
    if (r.learned && r.learned.length) { S.learned.push(...r.learned); renderLearned(); }
    if ((r.warning || '') !== S.docWarning) { S.docWarning = r.warning || ''; renderBanners(); }
    // while a Fix box has the keyboard (an input method may be picking a word) the panel waits for the next round;
    // with the box open but the keyboard elsewhere it is drawn again, the box with what was typed
    if ((seen() !== before || S.railLate) && !S.pickOpen) {
      if (S.fixing && S.fixFocus) S.railLate = true; else { S.railLate = false; renderRail(); }
    }
  }).catch(() => {}).finally(() => { if (S.refreshing && S.refreshing.p === p) S.refreshing = null; });
  S.refreshing = { id, p };
  return p;
}
// every 15 seconds while the window is on screen; a minimized window waits
setInterval(() => {
  const deleting = S.del && S.del.busy && S.del.ids.includes(S.sel);
  if (docsMode() && !S.busy && !aiBusy() && !document.hidden && !deleting) refreshDoc();
}, 15000);

// a 待補充 or 待確認 item: the Doc moves to where it is and selects it (the keyboard stays here, so nothing typed
// next lands on the selected words)
function showInDoc(words, blink = false, keep = false) {
  if (!words || !docsMode()) return;
  call('find', { id: S.sel, text: words, blink, keep }).then(() => {
    const input = $('#promptInput');
    if (keep && input && document.activeElement === input) input.focus();
  }).catch(() => {});
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
  const live = S.jobs.filter((j) => !j.archived);
  const names = [...new Set(live.map((j) => j.project).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-Hant'));
  const loose = live.some((j) => !j.project && (j.status === 'ready' || j.status === 'sent'));
  const archived = S.jobs.some((j) => j.archived);
  return [ALL, ...names, ...(loose ? [LOOSE] : []), ...(archived ? [ARCHIVED] : [])];
}

// the meetings the list can show in the place picked: archived ones only under 已封存
const inScope = (j) => (S.proj === ARCHIVED) === !!j.archived;

// tags are kept, set by the AI tools and found by the search, but not shown: no 標籤 row above the minutes, no 標籤
// filter and no tags under each meeting in the list (Vin 2026-10-28: the screen simpler; prototypes/hide-tags.html)
const SHOW_TAGS = false;

function allTags() {
  if (!SHOW_TAGS) return [];
  return [...new Set(S.jobs.filter(inScope).flatMap((j) => j.tags || []))].sort((a, b) => a.localeCompare(b, 'zh-Hant'));
}

// a project shows as its first character on a colour of its own, the same colour every time
const PROJECT_COLOURS = 7;
function projectColour(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.codePointAt(0)) >>> 0;
  return h % PROJECT_COLOURS;
}
function projectMark(name, big = false) {
  const first = name ? [...name][0].toUpperCase() : '';
  return `<span class="pav ${name ? 'p' + projectColour(name) : 'none'}${big ? ' big' : ''}" aria-hidden="true">${esc(first)}</span>`;
}
// in the list: a folder on the project's colour and its name in grey, then whether the minutes went out
// (Vin 2026-10-28, prototypes/project-folder-list.html: the names on their colours read as a mess)
const FOLDER = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h3.6a2 2 0 0 1 1.4.6L12 6h6.5A2.5 2.5 0 0 1 21 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/></svg>';
const projectTag = (name) => `<span class="ptag p${projectColour(name)}">${FOLDER}<span>${esc(name)}</span></span><span class="pdot">·</span>`;

// under a meeting's title in the list: 已寄出 3 人 once mailed, else what it is at
const listStatus = (j) => (j.status === 'sent' && j.sent_count ? t('sent_short', j.sent_count) : statusText(j.status));

function shownJobs() {
  const q = S.q.trim();
  const digits = (t) => t.replace(/[^0-9]/g, '');
  return S.jobs.filter((j) => {
    if ((S.proj === ARCHIVED) !== !!j.archived) return false;
    if (S.proj === LOOSE && j.project) return false;
    if (S.proj !== ALL && S.proj !== LOOSE && S.proj !== ARCHIVED && j.project !== S.proj) return false;
    if (S.tag !== ALL && !(j.tags || []).includes(S.tag)) return false;
    if (!q) return true;
    const text = `${j.title} ${j.project} ${(j.tags || []).join(' ')} ${j.day} ${j.date} ${j.time}`;
    return text.includes(q) || (digits(q) !== '' && (digits(j.day + j.time).includes(digits(q))
                                                     || digits(j.date + j.time).includes(digits(q))));
  });
}

function titleOf(j) {
  if (j.status === 'working') return t('st_working');
  if (j.status === 'failed') return t('st_failed');
  return j.title || t('untitled');
}

// a meeting still being written up can't be archived or deleted yet: no checkbox, no right-click menu
const pickable = (j) => j.status !== 'working';

function renderSide() {
  const side = $('#side');
  const opts = projects();
  if (!opts.includes(S.proj)) S.proj = ALL;
  const tags = allTags();
  if (!tags.includes(S.tag)) S.tag = ALL;
  const list = shownJobs();
  const choosable = list.filter(pickable);
  S.picked = new Set(choosable.filter((j) => S.picked.has(j.id)).map((j) => j.id));   // only what is on screen
  const allPicked = choosable.length > 0 && S.picked.size === choosable.length;
  const groups = [];
  for (const j of list) {
    let g = groups.find((x) => x.date === j.date);
    if (!g) groups.push(g = { date: j.date, day: j.day, items: [] });
    g.items.push(j);
  }
  const keepFocus = document.activeElement && document.activeElement.id === 'q';
  const scrolled = side.querySelector('.sidelist') ? side.querySelector('.sidelist').scrollTop : 0;
  side.innerHTML = `<div class="sidelist">
    <div class="sidehead"><h1>${esc(t('list_title'))} <span class="n">(${list.length})</span></h1>
      <button class="pickbtn" id="pickBtn" aria-pressed="${S.picking}">${esc(t(S.picking ? 'pick_done' : 'pick'))}</button></div>
    <div class="search">${ICON.search}<input id="q" aria-label="${esc(t('search_aria'))}" placeholder="${esc(t('search_ph'))}" value="${esc(S.q)}"></div>
    <div class="proj"><label for="proj">${esc(t('project'))}</label><select id="proj">${opts.map((p) => `<option value="${esc(p)}"${p === S.proj ? ' selected' : ''}>${esc(projName(p))}</option>`).join('')}</select></div>
    ${tags.length ? `<div class="proj"><label for="tagSel">${esc(t('tag'))}</label><select id="tagSel">${[ALL, ...tags].map((g) => `<option value="${esc(g)}"${g === S.tag ? ' selected' : ''}>${esc(g === ALL ? t('proj_all') : g)}</option>`).join('')}</select></div>` : ''}
    ${S.picking ? `<button class="pickall" id="pickAll" aria-pressed="${allPicked}"><span class="cbox${allPicked ? ' on' : ''}">${ICON.tick}</span>${esc(t('pick_all', choosable.length))}</button>` : ''}
    ${groups.map((g) => `
      <div class="day"><span>${esc(g.day)}</span><i></i></div>
      ${g.items.map((j) => `
        <div class="item${S.picking ? ' picking' : j.id === S.sel ? ' on' : ''}${S.picked.has(j.id) ? ' picked' : ''}${playingRow(j.id) ? ' playing' : ''}" role="button" tabindex="0" data-id="${esc(j.id)}"${S.picking && pickable(j) ? ` aria-pressed="${S.picked.has(j.id)}"` : ''}>
          ${S.picking && pickable(j) ? `<span class="ico"><span class="cbox${S.picked.has(j.id) ? ' on' : ''}">${ICON.tick}</span></span>`
            : j.status === 'working' || j.status === 'failed' ? `<span class="ico">${ICON[j.status]}</span>` : ''}
          <span class="txt"><span class="t">${esc(titleOf(j))}</span>
            <span class="s${j.status === 'failed' ? ' bad' : ''}">${(S.proj === ALL || S.proj === ARCHIVED) && j.project ? projectTag(j.project) : ''}<span>${esc(listStatus(j))}</span></span>
            ${SHOW_TAGS && (j.tags || []).length ? `<span class="tgs">${j.tags.map((g) => `<span class="tg" data-tag="${esc(g)}">${esc(g)}</span>`).join('')}</span>` : ''}</span>
          <span class="tools">${j.has_transcript ? `<button class="tb" data-act="read" title="${esc(t('read_transcript'))}" aria-label="${esc(t('read_transcript'))}">${ICON.lines}</button>` : ''}${j.has_audio ? playButton(playingRow(j.id)) : ''}</span>
        </div>`).join('')}`).join('')}
    ${list.length ? '' : `<div class="empty">${esc(t(S.jobs.length ? 'no_match' : 'no_meetings'))}</div>`}</div>
    ${S.picking ? `<div class="pickbar"><span>${esc(t('picked', S.picked.size))}</span>
      <button class="btn ghost" id="pickArchive"${S.picked.size ? '' : ' disabled'}>${esc(t(S.proj === ARCHIVED ? 'unarchive' : 'archive'))}</button>
      <button class="btn ghost danger" id="pickDelete"${S.picked.size ? '' : ' disabled'}>${esc(t('delete'))}</button></div>`
      : usageEntry() + '<div class="ver" id="ver"></div>'}`;
  side.querySelector('.sidelist').scrollTop = scrolled;
  renderVersion();
  $('#pickBtn').addEventListener('click', () => { S.picking = !S.picking; S.picked = new Set(); renderSide(); });
  if (S.picking) {
    $('#pickAll').addEventListener('click', () => {
      S.picked = allPicked ? new Set() : new Set(choosable.map((j) => j.id));
      renderSide();
    });
    $('#pickArchive').addEventListener('click', () => { if (S.picked.size) archive([...S.picked], S.proj !== ARCHIVED, true); });
    $('#pickDelete').addEventListener('click', () => { if (S.picked.size) openDelete([...S.picked], true); });
  }
  const q = $('#q');
  q.addEventListener('input', () => { S.q = q.value; renderSide(); });
  if (keepFocus) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  $('#proj').addEventListener('change', (e) => { S.proj = e.target.value; renderSide(); });
  if ($('#tagSel')) $('#tagSel').addEventListener('change', (e) => { S.tag = e.target.value; renderSide(); });
  // the meeting already open stays as it is: opening it again would drop what Claude is about to answer
  side.querySelectorAll('.item').forEach((b) => {
    const go = () => {
      const id = b.dataset.id;
      if (S.picking) {                           // a click checks or unchecks the meeting instead of opening it
        const j = S.jobs.find((x) => x.id === id);
        if (!j || !pickable(j)) return;
        if (S.picked.has(id)) S.picked.delete(id); else S.picked.add(id);
        return renderSide();
      }
      if (id !== S.sel || !S.d) select(id);
    };
    b.addEventListener('click', (e) => {
      const tag = !S.picking && e.target.closest('.tg');
      if (tag) { S.tag = tag.dataset.tag; return renderSide(); }    // a tag on a row: the list keeps only that tag
      if (!e.target.closest('.tb')) go();
    });
    b.addEventListener('keydown', (e) => { if (e.target === b && !inputMethod(e) && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); go(); } });
  });
}
// the buttons on a row, also the ones drawn again while the recording plays
$('#side').addEventListener('click', (e) => {
  const t = e.target.closest('.item .tb');
  if (t) rowAction(t.closest('.item').dataset.id, t.dataset.act);
});

// --- 封存 and 刪除 ------------------------------------------------------------------------------
// right-click on a meeting: 封存 (取消封存 under 已封存) and 刪除, for that meeting, or for every checked one
// when it is one of them

$('#side').addEventListener('contextmenu', (e) => {
  const row = e.target.closest('.item');
  if (!row) return;
  e.preventDefault();
  const j = S.jobs.find((x) => x.id === row.dataset.id);
  if (!j || !pickable(j)) return closeCtx();
  const onPicked = S.picking && S.picked.has(j.id);
  S.ctx = { ids: onPicked ? [...S.picked] : [j.id], onPicked, x: e.clientX, y: e.clientY, back: !!j.archived };
  renderCtx();
});

function renderCtx() {
  let el = $('#ctx');
  if (!S.ctx) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'ctx'; el.className = 'ctxmenu'; el.setAttribute('role', 'menu'); document.body.appendChild(el); }
  el.innerHTML = `<button role="menuitem" id="ctxArchive">${esc(t(S.ctx.back ? 'unarchive' : 'archive'))}</button>
    <button role="menuitem" class="danger" id="ctxDelete">${esc(t('delete'))}</button>`;
  // kept over the list: the Google Doc beside it is drawn by the app on top of the page
  const side = $('#side').getBoundingClientRect();
  const w = el.offsetWidth, h = el.offsetHeight;
  el.style.left = `${Math.max(4, Math.min(S.ctx.x, side.right - w - 6))}px`;
  el.style.top = `${Math.max(4, Math.min(S.ctx.y, window.innerHeight - h - 6))}px`;
  const { ids, back, onPicked } = S.ctx;
  $('#ctxArchive').addEventListener('click', () => archive(ids, !back, onPicked));
  $('#ctxDelete').addEventListener('click', () => openDelete(ids, onPicked));
  $('#ctxArchive').focus();
}

function closeCtx() { if (S.ctx) { S.ctx = null; renderCtx(); } }
document.addEventListener('mousedown', (e) => { if (S.ctx && !e.target.closest('#ctx')) closeCtx(); }, true);
window.addEventListener('blur', closeCtx);
$('#side').addEventListener('scroll', closeCtx, true);

function endPicking() { S.picking = false; S.picked = new Set(); }
// done with the checked meetings: 選取 ends; done with one meeting right-clicked: the others stay checked
function afterPicked(onPicked, gone) {
  if (onPicked) endPicking(); else gone.forEach((id) => S.picked.delete(id));
}

// after 封存 or 刪除: the list again; the open meeting, if it left the list, gives way to the first one shown
async function afterListChange(ids) {
  await loadList();
  if (!S.sel || !ids.includes(S.sel) || shownJobs().some((j) => j.id === S.sel)) return;
  const next = shownJobs()[0];
  if (next) return select(next.id);              // select() first saves what was typed in the one leaving
  if (S.d) await leave();
  S.sel = null; S.d = null;
  renderSide(); renderMain();
}

async function archive(ids, on, onPicked = false) {
  closeCtx();
  let done = [], message = '';
  try {
    const r = await call(on ? 'archive' : 'unarchive', { ids });
    done = r.done || []; message = r.message || '';
  } catch (e) { message = e.message; }
  afterPicked(onPicked && !message, done);
  await afterListChange(done);
  if (message) showAlert(message);
}

function openDelete(ids, onPicked = false) {
  closeCtx();
  const jobs = ids.map((id) => S.jobs.find((j) => j.id === id)).filter((j) => j && pickable(j));
  if (!jobs.length) return;
  S.del = { ids: jobs.map((j) => j.id), busy: false, err: '', onPicked };
  S.sheet = 'delete';
  placeDoc();
  renderDelete();
}

const monthDay = (j) => `${j.date.slice(5, 7)}/${j.date.slice(8, 10)} ${j.time}`;

function renderDelete() {
  const m = S.del;
  const jobs = m.ids.map((id) => S.jobs.find((j) => j.id === id)).filter(Boolean);
  const shared = jobs.some((j) => j.status === 'sent');
  $('#sheet').innerHTML = `<div class="veil"><div class="sheet confirm" role="alertdialog" aria-label="${esc(t('del_title', jobs.length))}">
    <h3>${esc(t('del_title', jobs.length))}</h3>
    <div class="dlist">${jobs.map((j) => `<div class="drow"><span class="dname">${esc(monthDay(j))}　${esc(titleOf(j))}</span>
      <span class="${j.status === 'sent' ? 'dsent' : 'dst'}">${esc(j.status === 'sent' && j.sent_count ? t('sent_to', j.sent_count) : statusText(j.status))}</span></div>`).join('')}</div>
    <p class="dnote">${esc(t('del_body'))}</p>
    ${shared ? `<p class="dwarn">${esc(t('del_warn'))}</p>` : ''}
    ${m.err ? `<p class="dnote err">${esc(m.err)}</p>` : ''}
    <div class="dfoot"><button class="btn ghost" id="delCancel"${m.busy ? ' disabled' : ''}>${esc(t('cancel'))}</button>
      <button class="btn danger-fill" id="delGo"${m.busy ? ' disabled' : ''}>${m.busy ? ICON.spinWhite : ''}${esc(t('del_go', jobs.length))}</button></div>
  </div></div>`;
  $('#delCancel').addEventListener('click', closeSheet);
  $('#delGo').addEventListener('click', doDelete);
  if (!m.busy) $('#delCancel').focus();
}

async function doDelete() {
  const m = S.del;
  if (!m || m.busy) return;
  m.busy = true; m.err = '';
  renderDelete();
  const open = m.ids.includes(S.sel) ? S.sel : null;
  if (open) {                                       // the open meeting: what was typed is saved, its recording stops
    await flush();
    if (S.player.open) audio('stop');
  }
  let gone = [], note = '';
  try {
    const r = await call('delete', { ids: m.ids });
    gone = r.done || []; note = r.message || '';
  } catch (e) { note = e.message; }
  m.busy = false;
  m.ids = m.ids.filter((id) => !gone.includes(id));
  const stuck = m.ids.length > 0;                   // these stay in the list: the dialog says why, to try again
  if (stuck) { m.err = note || t('err_retry'); if (S.picking && m.onPicked) S.picked = new Set(m.ids); }
  else { closeSheet(); afterPicked(m.onPicked, gone); }
  if (open && gone.includes(open)) { clearTimeout(S.saveTimer); S.dirty = false; S.sel = null; S.d = null; }
  await loadList();
  if (stuck) { if (S.sheet === 'delete') renderDelete(); if (!S.sel) renderMain(); return; }
  if (!S.sel && S.usage) loadUsage(U.month);          // deleted from 用量統計: it stays, with the new numbers
  else if (!S.sel) { const next = shownJobs()[0]; if (next) await select(next.id); else renderMain(); }
  if (note) showAlert(note);                        // every meeting went, but a file beside one stayed
}

const playingRow = (id) => id === S.sel && S.player.playing;
const playButton = (on) => { const tip = esc(t(on ? 'pause_play' : 'play_rec')); return `<button class="tb${on ? ' on' : ''}" data-act="play" title="${tip}" aria-label="${tip}">${on ? ICON.pause : ICON.headset}</button>`; };

// the two buttons on a meeting in the list: its transcript, its recording; another meeting opens first
async function rowAction(id, act) {
  if (act === 'play' && playingRow(id)) return audio('pause', { at: S.player.pos });
  if (id !== S.sel || !S.d) {
    await select(id);
    if (S.sel !== id || !S.d) return;             // stayed on a meeting with unsaved text, or this one did not open
  }
  if (act === 'read') {
    if ((S.d.transcript || []).length) openTranscript();
    else showAlert(t('no_transcript'));
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

// the list's corner: the version, and 版本更新 when GitHub has a newer one (looked up once an hour); a recording
// has to end first, since updating closes the app
function renderVersion() {
  const el = $('#ver');
  if (!el) return;
  const v = S.version;
  if (!v || !v.version) { el.innerHTML = ''; return; }
  const tip = S.recording ? t('upd_wait') : t('upd_to', v.newest);
  el.innerHTML = `<span>${esc(t('version', v.version))}</span>${v.update ? `<button class="upd${S.updating || S.recording ? ' off' : ''}" id="updBtn" title="${esc(tip)}" aria-disabled="${S.updating || S.recording}">${esc(t(S.updating ? 'updating' : 'update'))}</button>` : ''}`;
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
  S.usage = false;                                  // a meeting picked: 用量統計 closes
  if (S.sel && S.d) {
    await flush();
    if (S.dirty && S.giveUp !== id) {          // a second click on the same meeting leaves the unsaved text behind
      S.giveUp = id;
      showAlert(t('unsaved_switch'));
      return;
    }
    S.giveUp = null;
    if (docsMode()) refreshDoc(S.sel, true);
    else learnLater(S.sel);
  }
  S.sel = id;
  S.d = null; S.loadError = ''; S.cfocus = null; S.resolved = new Set(); S.tab = null; S.tabBeforeScore = null;
  S.busy = false; S.asked = ''; S.askedQuick = ''; S.said = ''; S.canUndo = false; S.learned = []; S.learnOpen = false; S.learnShown = 0; S.learnHidden = false; S.learnHover = false; S.alert = null;
  S.pickOpen = null; S.pickTyping = null; S.peopleTyped = ''; clearTimeout(S.peopleStop); S.peoplePlay = null; S.pmenu = null;
  S.tagAdding = false;
  S.att = null; S.refs = []; S.pics = []; S.askedPic = ''; S.fixing = ''; S.skipping = new Set(); S.urlOpen = false; S.menuOpen = false;
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
    S.d.check = checkShown(d.check, id);           // a correction still on its way keeps its card off
    S.shown = d.shown || '';
    S.canUndo = !!d.can_undo;
    S.learned = d.learned || [];
    S.saveText = d.doc_url && !d.offline ? ['synced', hhmm()] : '';
    const n = d.news || {};
    if ((n.edits || 0) + (n.new_comments || 0) > 0 && !docsMode()) {    // beside the Doc, 操作紀錄 has them
      S.banner = n;                                   // the words are made when it is drawn (newsText)
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
  // what still waits under 待修改, and the voices named meanwhile, is done without the window, in order, after what
  // the AI is on now
  for (const id of new Set([...Object.keys(S.work), ...Object.keys(S.peopleLater)])) {
    const w = S.work[id] || { waits: [] };
    const items = namesLeft(id).concat(w.waits.map((q) => (q.correct ? { kind: 'correct', item: q.correct.label, text: q.correct.value }
      : q.quick ? { kind: 'quick', text: q.quick } : { kind: 'ask', text: q.text, pictures: q.pics.map((x) => x.path),
        refs: refsOut(q.refs) })));
    w.waits = [];
    delete S.peopleLater[id];
    if (items.length) call('askMany', { id, items }).catch(() => {});
  }
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

// nothing recorded yet: how to record the first meeting, and what happens after
function drawFirst(main) {
  main.innerHTML = `<div class="first"><h2>${esc(t('first_title'))}</h2><p>${esc(t('first_text'))}<br>${esc(t('first_notify'))}</p>
    <button class="btn primary rec" id="firstRec"${S.recording ? ' disabled' : ''}><span class="dot" aria-hidden="true"></span>${esc(t(S.recording ? 'first_recording' : 'start_rec'))}</button>
    <div class="key">${esc(t('first_key'))}</div></div>`;
  $('#firstRec').addEventListener('click', async () => {
    try { await call('record'); } catch (e) { return showAlert(e.message); }
    await openFirst();
  });
}

// the list was empty and now has the first recording: it opens at once (never another meeting after a delete)
async function openFirst() {
  const empty = !S.jobs.length;
  await loadList();
  if (empty && !S.sel && S.jobs.length) select(S.jobs[0].id);
  return empty;
}

function drawMain() {
  const main = $('#main');
  if (S.usage) return drawUsage(main);              // 用量統計 (usage.js) in place of a meeting
  const job = S.jobs.find((j) => j.id === S.sel);
  if (!S.sel && !S.jobs.length) return drawFirst(main);
  if (!S.sel) { main.innerHTML = `<div class="state"><div class="sub">${esc(t('no_recording'))}</div></div>`; return; }
  if (S.loadError) {
    main.innerHTML = `<div class="state"><h2>${esc(job ? titleOf(job) : '')}</h2><div class="banner err"><span>${esc(S.loadError)}</span></div>
      <div><button class="btn ghost" id="again">${esc(t('try_again'))}</button></div></div>`;
    $('#again').addEventListener('click', () => select(S.sel));
    return;
  }
  if (!S.d) {
    main.innerHTML = `<div class="state"><div class="busy">${ICON.spin}<span>${esc(t('loading_doc'))}</span></div></div>`;
    return;
  }
  const d = S.d;
  if (d.status === 'working') return renderWorking(main, d);
  if (d.status === 'failed') return renderFailed(main, d);
  if (docsMode()) {
    main.innerHTML = `
      <div class="head" id="head"></div>
      <div class="tagbar" id="tagbar"></div>
      <div class="body">
        <div class="paper docs"><div id="banners"></div>
          <div id="gdoc" class="gdoc"><div class="busy">${ICON.spin}<span>${esc(t('opening_doc'))}</span></div></div></div>
        <aside class="rail" id="rail" aria-label="${esc(t('rail_docs_aria'))}"></aside>
      </div>
      <div class="ask" id="ask"></div>
      <div class="foot" id="foot"></div>`;
    renderHead(); renderTags(); renderBanners(); renderRail(); renderAsk(); renderFoot();
    return;
  }
  main.innerHTML = `
    <div class="head" id="head"></div>
    <div class="tagbar" id="tagbar"></div>
    <div class="body">
      <div class="paper"><div id="banners"></div><div id="doc" contenteditable="true" spellcheck="false"></div></div>
      <aside class="rail" id="rail" aria-label="${esc(t('rail_aria'))}"></aside>
    </div>
    <div class="ask" id="ask"></div>
    <div class="foot" id="foot"></div>`;
  setDoc(d.html);
  if (d.readonly || S.busy || aiBusy()) docEl().contentEditable = 'false';
  wireDoc();
  renderHead(); renderTags(); renderBanners(); renderRail(); renderAsk(); renderFoot();
}

function renderWorking(main, d) {
  const step = d.step;
  if (!step && S.recording && S.jobs[0] && S.jobs[0].id === d.id) {   // still recording: nothing to write up yet
    main.innerHTML = `<div class="state"><h2>${esc(t('first_recording'))}</h2>
      <div class="sub">${esc(t('rec_now'))}</div></div>`;
    return;
  }
  const st = (n) => {
    const order = { transcribing: 0, writing: 1 }[step] ?? 0;
    if (n < order) return ['', ICON.done];
    if (n === order) return ['now', ICON.spin];
    return ['later', ICON.dot];
  };
  const names = [t('step_transcribe'), t('step_write'), t('step_publish')];
  main.innerHTML = `<div class="state"><h2>${esc(t('st_working'))}</h2>
    <div class="sub">${t('recorded', esc(d.day), esc(d.time), d.ended_time ? esc(d.ended_time) : '')}</div>
    <div class="steps">${names.map((n, i) => { const [c, ic] = st(i); return `<div class="${c}">${ic}<span>${esc(n)}</span></div>`; }).join('')}</div>
    ${d.message ? `<div class="sub">${esc(d.message)}</div>` : ''}</div>`;
}

function renderFailed(main, d) {
  main.innerHTML = `<div class="state"><h2>${esc(t('st_failed'))}</h2>
    <div class="sub">${t('recorded', esc(d.day), esc(d.time), '')}</div>
    <div class="banner err"><span>${esc(d.message || t('stopped'))}</span></div>
    <div class="buttons"><button class="btn primary" id="retry">${esc(t('retry'))}</button><button class="btn ghost" id="folder">${esc(t('open_folder'))}</button></div></div>`;
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
  const planned = d.planned ? t('planned', d.planned) : t('no_next');
  el.innerHTML = `
    <nav class="crumbs" aria-label="${esc(t('crumbs_aria'))}">
      <button class="crumb pcrumb" id="toProj" title="${esc(t('proj_switch'))}" aria-haspopup="menu" aria-expanded="${!!S.pmenu}">${esc(d.project || t('proj_loose'))}<span class="caret">▾</span></button>
      ${d.project ? `<button class="iconbtn gear" id="projSet" title="${esc(t('proj_settings'))}" aria-label="${esc(t('proj_settings'))}">${ICON.gear}</button>` : ''}${ICON.chevR}
      <button class="crumb" id="toDate">${esc(shortDay(d))}</button>
      <b>${t('crumb_title', esc(d.title || t('untitled')))}</b>
    </nav>
    <button class="sib${d.prev ? '' : ' off'}" id="prev" title="${esc(d.prev ? d.prev_title : t('no_prev'))}">${ICON.chevL}<span>${esc(t('prev_meeting'))}</span></button>
    <button class="sib${d.next ? '' : ' off'}" id="next" title="${esc(d.next ? d.next_title : planned)}"><span>${esc(t('next_meeting'))}</span>${ICON.chevR}</button>
    ${docsMode() ? '' : `<span class="savetext${S.saveErr ? ' err' : ''}" id="savetext">${esc(say(S.saveText))}</span>`}
    ${d.doc_url ? `<span class="iconlink" id="openDoc" title="${esc(t('open_doc_tip'))}">${ICON.open}</span>` : ''}
    ${d.sent ? `<span class="sentmark" title="${esc(t('sent_line', d.sent.at, d.sent.count, d.sent.format))}">${ICON.done}<span>${esc(t('sent_short', d.sent.count))}</span></span>`
      : d.mail ? `<button class="btn primary sendbtn" id="mailBtn">${ICON.mail}<span>${esc(t('send_mail'))}</span></button>` : ''}
    <div class="mmenu pmenu" id="projMenu" role="menu" hidden></div>`;
  if ($('#mailBtn')) $('#mailBtn').addEventListener('click', openMail);
  $('#toProj').addEventListener('click', (e) => {
    e.stopPropagation();
    S.pmenu = S.pmenu ? null : { adding: false, typed: '', busy: false, err: '' };
    $('#toProj').setAttribute('aria-expanded', String(!!S.pmenu));
    if (S.pmenu && S.aiOpen) { S.aiOpen = false; renderAiMenu(); }      // one menu open at a time
    if (S.pmenu && S.menuOpen) { S.menuOpen = false; renderAttachMenu(); }
    renderProjMenu();
  });
  $('#projMenu').addEventListener('click', (e) => e.stopPropagation());
  if ($('#projSet')) $('#projSet').addEventListener('click', openProject);
  $('#toDate').addEventListener('click', () => { S.q = shortDay(d); S.proj = ALL; S.tag = ALL; renderSide(); });
  $('#prev').addEventListener('click', () => d.prev && select(d.prev));
  $('#next').addEventListener('click', () => d.next && select(d.next));
  if (d.doc_url) $('#openDoc').addEventListener('click', () => call('link', { url: d.doc_url }).catch(() => {}));
  if (S.pmenu) renderProjMenu();
}

// under the path: the meeting's tags, 加標籤, and the ones Claude suggested (dashed until the user adds one)
const MAX_TAGS = 8;                                 // minutes_app.py keeps the same number

function renderTags() {
  const el = $('#tagbar');
  if (!el || !S.d) return;
  if (!SHOW_TAGS) {                                 // only 附件 and the score
    el.innerHTML = `${attachmentsHTML(false)}${scoreButtonHTML()}`;
    el.hidden = !el.innerHTML.trim();
    bindAttachments(el);
    if ($('#scoreBtn')) $('#scoreBtn').addEventListener('click', toggleScore);
    return;
  }
  const tags = S.d.tags || [], offered = S.d.suggested || [];
  el.innerHTML = `<span class="tl">${esc(t('tag'))}</span>
    ${tags.map((g) => `<span class="tchip">${esc(g)}<button data-rm="${esc(g)}" title="${esc(t('remove_tag', g))}" aria-label="${esc(t('remove_tag', g))}">${ICON.xs}</button></span>`).join('')}
    ${tags.length >= MAX_TAGS ? '' : S.tagAdding ? `<input id="tagIn" class="tagin" maxlength="20" aria-label="${esc(t('add_tag'))}" placeholder="${esc(t('tag_ph'))}">`
      : `<button class="tadd" id="tagAdd">${ICON.plusSm}<span>${esc(t('add_tag'))}</span></button>`}
    ${offered.length && tags.length < MAX_TAGS ? `<span class="tl ai">${esc(t('tag_ai', aiName()))}</span>${offered.map((g) => `<button class="tchip sug" data-add="${esc(g)}" title="${esc(t('add_this_tag', g))}">${ICON.plusSm}${esc(g)}</button>`).join('')}` : ''}
    ${attachmentsHTML()}${scoreButtonHTML()}`;
  bindAttachments(el);
  if ($('#scoreBtn')) $('#scoreBtn').addEventListener('click', toggleScore);
  el.querySelectorAll('[data-rm]').forEach((b) => b.addEventListener('click', () => changeTags((now) => now.filter((g) => g !== b.dataset.rm))));
  el.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => changeTags((now) => [...now, b.dataset.add])));
  if ($('#tagAdd')) $('#tagAdd').addEventListener('click', () => { S.tagAdding = true; renderTags(); $('#tagIn').focus(); });
  const box = $('#tagIn');
  if (!box) return;
  let done = false;
  const finish = (keep) => {
    if (done) return;
    done = true;
    S.tagAdding = false;
    const g = box.value.trim().replace(/\s+/g, ' ');
    if (keep && g) changeTags((now) => [...now, g]); else renderTags();
  };
  box.addEventListener('keydown', (e) => {
    if (inputMethod(e)) return;                     // the 注音 candidate list takes Enter first
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
  });
  box.addEventListener('blur', () => finish(true));
}

// the score of the minutes (scores.py), grey at the end of the tags: a click opens 評分 beside the Doc, a second
// click goes back to the tab that was open before
const scoreOpen = () => !!(S.railOpen && S.tab === 'score' && S.d && S.d.score);

function scoreButtonHTML() {
  const sc = S.d.score;
  if (!sc) return '';
  const on = scoreOpen();
  return `<button class="tscore${on ? ' on' : ''}" id="scoreBtn" aria-expanded="${on}" title="${esc(t('score_aria', sc.score))}"
    aria-label="${esc(t('score_aria', sc.score))}">${Number(sc.score)}</button>`;
}

function toggleScore() {
  if (scoreOpen()) { S.tab = S.tabBeforeScore || null; } else { S.tabBeforeScore = S.tab === 'score' ? null : S.tab; S.railOpen = true; S.tab = 'score'; }
  renderRail();
}

function markScoreButton() {
  const b = $('#scoreBtn');
  if (!b) return;
  b.classList.toggle('on', scoreOpen());
  b.setAttribute('aria-expanded', String(scoreOpen()));
}

function scoreHTML(sc) {
  return `<div class="sbig"><b>${Number(sc.score)}</b><small>${esc(t(sc.kind === 'edits' ? 'score_edits' : 'score_check'))}</small></div>
    <div class="scats">${(sc.categories || []).map(([k, got, of]) => `<span>${esc(t('score_' + k))}</span><span class="sn${got < of ? ' lost' : ''}">${Number(got)} / ${Number(of)}</span>`).join('')}</div>
    <div class="slost">${esc(t('score_lost'))}</div>
    ${(sc.lost || []).length ? sc.lost.map((x, i) => `<button class="sitem" data-s="${i}"${x.find && docsMode() ? '' : ' disabled'}><b>${esc(x.what)}</b>${x.fix ? `<small>${esc(x.fix)}</small>` : ''}</button>`).join('')
      : `<div class="empty">${esc(t('score_none_lost'))}</div>`}`;
}

function wireScore(el, sc) {
  el.querySelectorAll('.sitem[data-s]').forEach((b) => b.addEventListener('click', () => showInDoc(sc.lost[Number(b.dataset.s)].find)));
}

// a click shows at once; the lists go out one after another, each from what the clicks before it left, so two
// quick clicks never send the same old list twice
let tagsSent = Promise.resolve();
function changeTags(change) {
  const id = S.sel, d = S.d;
  if (!d) return;
  const tags = [...new Set(change(d.tags || []))].slice(0, MAX_TAGS);
  d.tags = tags;
  d.suggested = (d.suggested || []).filter((g) => !tags.includes(g));
  renderTags();
  tagsSent = tagsSent.then(() => sendTags(id, tags));
}

async function sendTags(id, tags) {
  const j = S.jobs.find((x) => x.id === id);
  try {
    const r = await call('tags', { id, tags });
    if (j) { j.tags = r.tags; j.suggested = r.suggested; }
  } catch (e) {
    showAlert(e.message);
    await loadList();                                // what was saved after all
    const saved = S.jobs.find((x) => x.id === id);
    if (saved && S.sel === id && S.d) { S.d.tags = saved.tags || []; S.d.suggested = saved.suggested || []; renderTags(); }
  }
  renderSide();
}

// 專案設定, one page (prototypes/project-folder.html, Vin 2026-10-28): the project's name (every meeting of it),
// its folder for the AI to read, and its brief (專案背景: its people with what they do, its terms, a few lines of
// background; Vin 2026-10-19). Moving this meeting to another project is the project name above the meeting.
function openProject() {
  const d = S.d;
  if (!d || !d.project) return;
  S.pset = { name: d.project, busy: false, err: '', brief: null };
  S.sheet = 'project';
  closeProjMenu();
  placeDoc();
  renderProject();
  loadBrief(d.project);
}

async function loadBrief(project) {
  try {
    const r = await call('brief', { project });
    const m = S.pset;
    if (m && S.d && (S.d.project || '') === project) {
      m.brief = r.brief;                             // what the page showed: anything else added meanwhile is kept
      m.seen = { people: r.brief.people.map((p) => p.name), terms: r.brief.terms.map((x) => x.word) };
      if (S.sheet === 'project') renderProject();
    }
  } catch (e) {
    if (S.pset) { S.pset.err = e.message; if (S.sheet === 'project') renderProject(); }
  }
}

// one row of the brief: a new row's name or term can be typed, a kept one only has what it says about it
function briefRows(m, key) {
  const rows = m.brief[key];
  const head = key === 'people' ? ['name', 'role', 'brief_name_ph', 'brief_role_ph', 30, 20]
    : ['word', 'meaning', 'brief_word_ph', 'brief_meaning_ph', 30, 30];
  if (!rows.length) return `<div class="bempty">${esc(t(key === 'people' ? 'brief_no_people' : 'brief_no_terms'))}</div>`;
  return rows.map((r, i) => {
    const heard = r.heard && r.heard.length ? `<small>${esc(t('heard_as', r.heard.join(t('list_sep'))))}</small>` : '';
    const first = r.fresh
      ? `<input class="pinput" id="b-${key}-${i}-a" data-k="${key}" data-i="${i}" data-f="${head[0]}" maxlength="${head[4]}" placeholder="${esc(t(head[2]))}" value="${esc(r[head[0]])}">`
      : `<span>${esc(r[head[0]])}</span>`;
    return `<div class="brow"><div class="bname">${first}${heard}</div>
      <input class="pinput" id="b-${key}-${i}-b" data-k="${key}" data-i="${i}" data-f="${head[1]}" maxlength="${head[5]}" placeholder="${esc(t(head[3]))}" value="${esc(r[head[1]] || '')}">
      <button class="bx" data-k="${key}" data-i="${i}" title="${esc(t('remove_tag', r[head[0]] || ''))}" aria-label="${esc(t('remove_tag', r[head[0]] || ''))}">×</button></div>`;
  }).join('');
}

function briefHTML(m) {
  const b = m.brief;
  if (!b) return `<div class="bwait">${ICON.spin}</div>`;
  return `<section class="bsec"><header><b>${esc(t('brief_people'))}</b><span class="n">${b.people.length}</span>
      <button class="btn ghost" id="bAddP">${esc(t('brief_add_person'))}</button></header>${briefRows(m, 'people')}</section>
    <section class="bsec"><header><b>${esc(t('brief_terms'))}</b><span class="n">${b.terms.length}</span>
      <button class="btn ghost" id="bAddT">${esc(t('brief_add_term'))}</button></header>${briefRows(m, 'terms')}</section>
    <section class="bsec"><header><b>${esc(t('brief_background'))}</b></header>
      <textarea id="bBg" class="pinput bbg" maxlength="600" placeholder="${esc(t('brief_bg_ph'))}" aria-label="${esc(t('brief_background'))}">${esc(b.background)}</textarea></section>`;
}

// a folder as the Mac shows it in a sentence: the home folder as ~
const homeShort = (path) => path.replace(/^\/Users\/[^/]+(?=\/|$)/, '~');

function renderProject() {
  const m = S.pset, d = S.d;
  if (!m || !d || !d.project) return closeSheet();
  const now = d.project;
  const count = S.jobs.filter((j) => j.project === now).length;
  const folder = m.brief ? m.brief.folder || '' : '';
  // drawn again when the brief arrives or a row comes and goes: the field being typed in keeps its place
  const was = document.activeElement && $('#sheet').contains(document.activeElement) ? document.activeElement : null;
  const at = was && was.id ? { id: was.id, from: was.selectionStart, to: was.selectionEnd } : null;
  $('#sheet').innerHTML = `<div class="veil"><div class="sheet confirm pset wide" role="dialog" aria-label="${esc(t('proj_settings'))}">
    <h3>${esc(t('proj_settings'))}</h3>
    <div class="phead">${projectMark(now, true)}<div><div class="pname">${esc(now)}</div>
      <div class="pcount">${esc(t('proj_count', count))}</div></div></div>
    <label class="plbl" for="pName">${esc(t('proj_name'))}</label>
    <input id="pName" class="pinput" maxlength="30" value="${esc(m.name)}">
    <p class="dnote small">${esc(t('proj_rename_note', count))}</p>
    <span class="plbl">${esc(t('proj_folder'))}</span>
    <div class="pfolder"><span class="ppath${folder ? '' : ' none'}" title="${esc(folder)}">${esc(folder ? homeShort(folder) : t('proj_folder_none'))}</span>
      ${folder ? `<button class="bx" id="pFolderOff" title="${esc(t('proj_folder_off'))}" aria-label="${esc(t('proj_folder_off'))}"${m.busy ? ' disabled' : ''}>×</button>` : ''}
      <button class="btn ghost" id="pFolder"${m.brief && !m.busy ? '' : ' disabled'}>${esc(t('proj_folder_pick'))}</button></div>
    ${briefHTML(m)}
    ${m.err ? `<p class="dnote err">${esc(m.err)}</p>` : ''}
    <div class="dfoot"><button class="btn ghost" id="pCancel"${m.busy ? ' disabled' : ''}>${esc(t('cancel'))}</button>
      <button class="btn primary" id="pSave"${m.busy ? ' disabled' : ''}>${m.busy ? ICON.spinWhite : ''}${esc(t('save'))}</button></div>
  </div></div>`;
  $('#pCancel').addEventListener('click', closeSheet);
  $('#pSave').addEventListener('click', saveSettings);
  $('#pName').addEventListener('input', (e) => { m.name = e.target.value; });
  $('#pFolder').addEventListener('click', async () => {
    try {
      const r = await call('pickFolder', {});
      if (r.path && S.pset === m && m.brief) { m.brief.folder = r.path; m.folderChanged = true; m.err = ''; renderProject(); }
    } catch (e) { /* the panel did not open: nothing changes */ }
  });
  if ($('#pFolderOff')) $('#pFolderOff').addEventListener('click', () => { m.brief.folder = ''; m.folderChanged = true; renderProject(); });
  bindBrief(m);
  const back = at && document.getElementById(at.id);
  if (back) {
    back.focus();
    if (typeof at.from === 'number' && back.setSelectionRange) back.setSelectionRange(at.from, at.to);
  }
}

function bindBrief(m) {
  if (!m.brief) return;
  const sheet = $('#sheet');
  // typing changes the brief kept here; nothing is drawn again, so the cursor stays where it is
  sheet.querySelectorAll('.brow input').forEach((el) => el.addEventListener('input', () => {
    m.brief[el.dataset.k][Number(el.dataset.i)][el.dataset.f] = el.value;
    m.briefDirty = true;
  }));
  sheet.querySelectorAll('.bx').forEach((b) => b.addEventListener('click', () => {
    m.brief[b.dataset.k].splice(Number(b.dataset.i), 1);
    m.briefDirty = true;
    renderProject();
  }));
  const add = (key, row) => () => {
    m.brief[key].push({ ...row, heard: [], fresh: true });
    m.briefDirty = true;
    renderProject();
    const el = $(`#b-${key}-${m.brief[key].length - 1}-a`);
    if (el) el.focus();
  };
  $('#bAddP').addEventListener('click', add('people', { name: '', role: '' }));
  $('#bAddT').addEventListener('click', add('terms', { word: '', meaning: '' }));
  $('#bBg').addEventListener('input', (e) => { m.brief.background = e.target.value; m.briefDirty = true; });
}

// 儲存: the brief and the folder first (under the project's current name), then a new name
async function saveSettings() {
  const m = S.pset, d = S.d;
  if (!m || !d || !d.project || m.busy) return;
  const name = m.name.trim().replace(/\s+/g, ' ');
  if (!name) { m.err = t('proj_name_empty'); return renderProject(); }
  if (m.brief && (m.briefDirty || m.folderChanged) && !(await saveBrief())) return;
  if (name !== d.project) return renameProject(name);
  closeSheet();
}

async function saveBrief() {
  const m = S.pset, d = S.d;
  const project = d.project || '';
  const brief = {
    people: m.brief.people.filter((p) => p.name.trim()).map((p) => ({ name: p.name, role: p.role || '' })),
    terms: m.brief.terms.filter((x) => x.word.trim()).map((x) => ({ word: x.word, meaning: x.meaning || '' })),
    background: m.brief.background || '',
    seen: m.seen || { people: [], terms: [] },
    ...(m.folderChanged ? { folder: m.brief.folder || '' } : {}),   // a folder gone from the Mac stays until changed
  };
  m.busy = true; m.err = '';
  renderProject();
  try {
    await call('saveBrief', { project, brief });
    m.busy = false; m.briefDirty = false; m.folderChanged = false;
    return true;
  } catch (e) {
    m.busy = false; m.err = e.message;
    if (S.sheet === 'project') renderProject();
    return false;
  }
}

async function renameProject(name) {
  const m = S.pset, d = S.d;
  const now = d.project;
  m.busy = true; m.err = '';
  renderProject();
  const id = S.sel;
  try {
    const project = (await call('renameProject', { old: now, new: name })).project;
    if (S.sel === id && S.d) S.d.project = project;
    if (S.proj === now) S.proj = project;            // the list that showed the project follows it
    closeSheet();
    await loadList();
    if (S.sel === id && S.d) renderHead();
  } catch (e) {
    m.busy = false; m.err = e.message;
    if (S.sheet === 'project') renderProject();
  }
}

// The project name above the meeting opens a list of the projects (prototypes/project-folder.html, Vin 2026-10-28):
// picking one moves this meeting there, 新增專案… names a new one. The list sits over the Doc, so the Doc starts
// below it while it is open (placeDoc).
function renderProjMenu() {
  const el = $('#projMenu'), d = S.d, m = S.pmenu;
  if (!el) return;
  el.hidden = !m || !d;
  if (el.hidden) { el.innerHTML = ''; placeDoc(); return; }
  const now = d.project || '';
  const names = [...new Set(S.jobs.map((j) => j.project).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-Hant'));
  const item = (p) => `<button class="mi" data-p="${esc(p)}"${m.busy ? ' disabled' : ''}><span class="mn">${esc(p || t('proj_loose'))}</span>${p === now ? `<span class="ck">${ICON.tick}</span>` : ''}</button>`;
  el.innerHTML = `${[...names, ''].map(item).join('')}
    ${m.adding
      ? `<div class="pnew"><input id="pNewName" class="pinput" maxlength="30" autocomplete="off" placeholder="${esc(t('proj_new_ph'))}" aria-label="${esc(t('proj_new_ph'))}" value="${esc(m.typed)}"${m.busy ? ' disabled' : ''}></div>`
      : `<button class="mi pnewbtn" data-new="1"${m.busy ? ' disabled' : ''}><span class="mn">${esc(t('proj_new'))}</span></button>`}
    ${m.err ? `<div class="merr">${esc(m.err)}</div>` : ''}`;
  const r = $('#toProj').getBoundingClientRect();
  el.style.left = `${Math.round(r.left)}px`;
  el.style.top = `${Math.round(r.bottom + 6)}px`;
  el.querySelectorAll('.mi[data-p]').forEach((b) => b.addEventListener('click', () => moveTo(b.dataset.p)));
  if (el.querySelector('.pnewbtn')) el.querySelector('.pnewbtn').addEventListener('click', () => {
    m.adding = true; m.err = '';
    renderProjMenu();
    $('#pNewName').focus();
  });
  const input = $('#pNewName');
  if (input) {
    input.addEventListener('input', (e) => { m.typed = e.target.value; });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !inputMethod(e)) {
        const name = m.typed.trim().replace(/\s+/g, ' ');
        if (!name) { m.err = t('proj_name_empty'); renderProjMenu(); $('#pNewName').focus(); return; }
        moveTo(name);
      }
    });
  }
  placeDoc();
}

function closeProjMenu() {
  if (!S.pmenu) return;
  S.pmenu = null;
  renderProjMenu();
}

async function moveTo(project) {
  const m = S.pmenu, d = S.d;
  if (!m || !d || m.busy) return;
  const now = d.project || '';
  if (project === now) return closeProjMenu();
  m.busy = true; m.err = '';
  renderProjMenu();
  const id = S.sel;
  try {
    const moved = (await call('move', { id, project })).project;
    if (S.sel === id && S.d) S.d.project = moved;
    if (S.proj === (now || LOOSE) && S.proj !== ALL) S.proj = moved || LOOSE;   // the list that showed it follows
    S.pmenu = null;
    await loadList();
    if (S.sel === id && S.d) renderHead();
    renderProjMenu();
  } catch (e) {
    m.busy = false; m.err = e.message;
    renderProjMenu();
  }
}

// text: words, or [key, ...args] so the line follows a language switch
function setSave(text, err = false) {
  S.saveText = text; S.saveErr = err;
  const el = $('#savetext');
  if (el) { el.textContent = say(text); el.className = 'savetext' + (err ? ' err' : ''); }
}

function renderBanners() {
  const el = $('#banners');
  if (!el) return;
  const rows = [];
  if (S.banner) rows.push(`<div class="banner news">${ICON.sync}<span>${esc(newsText(S.banner))}</span><button id="seen">${esc(t('got_it'))}</button></div>`);
  if (S.d.warning) rows.push(`<div class="banner warn"><span>${esc(S.d.warning)}</span></div>`);
  if (S.docWarning && S.docWarning !== S.d.warning) rows.push(`<div class="banner warn"><span>${esc(S.docWarning)}</span></div>`);
  // the Doc did not load in the window: say so, or the minutes here look like the Doc with 待處理 gone (Vin 2026-10-30)
  if (S.docFailed) rows.push(`<div class="banner warn"><span>${esc(t('doc_failed'))}</span><button id="reloadDoc">${esc(t('reload_doc'))}</button></div>`);
  if (S.alert) rows.push(`<div class="banner err"><span>${esc(S.alert)}</span><button id="alertOk">${esc(t('got_it'))}</button></div>`);
  el.innerHTML = rows.join('');
  const seen = $('#seen');
  if (seen) seen.addEventListener('click', () => { clearTimeout(S.bannerTimer); S.banner = null; renderBanners(); });
  const ok = $('#alertOk');
  if (ok) ok.addEventListener('click', () => { S.alert = null; renderBanners(); });
  const again = $('#reloadDoc');
  if (again) again.addEventListener('click', () => { S.docFailed = false; renderMain(); });   // the window loads the Doc anew
}

function showAlert(text) { S.alert = text; renderBanners(); }

// what a colleague changed in the Google Doc since this meeting was last open (d.news)
function newsText(n) {
  const names = (n.editors || []).join(t('list_sep')) || t('someone');
  const parts = [];
  if (n.edits) parts.push(t('news_edits', names, n.edits));
  if (n.new_comments) parts.push(t('news_comments', n.new_comments));
  return t('news', parts);
}

// --- the editable minutes --------------------------------------------------------------------

function docEl() { return $('#doc'); }
function editable() { return S.d && S.d.readonly ? 'false' : 'true'; }

// 10/14 for this year, 2025/10/14 for another
function shortDay(d) {
  if (!d.date) return String(d.day || '').split('（')[0];   // an English day ("Wed, Oct 15") has no （ and stays whole
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
    setSave(['unsaved']);
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
  setSave(['saving']);
  S.saving = call('save', { id, html, shown: S.shown }).then((r) => {
    if (S.sel !== id || !S.d) return;
    afterEdit(r);
  }).catch((e) => {
    if (S.sel !== id) return;
    S.dirty = true;
    setSave(e.message || ['save_failed'], true);
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
  if (r.unsaved) setSave(['not_saved_edit'], true);
  else setSave([r.held ? 'held' : 'saved', r.saved_at || hhmm()]);
  if (r.attendees) S.d.attendees = r.attendees;       // 與會人員 under 人員, after the names went into the minutes
  if (r.attachments) setAttachments(r.attachments);
  if (r.people) S.d.people = r.people;
  if (r.speakers) S.d.speakers = r.speakers;
  if (r.calendar) S.d.calendar = r.calendar;
  if (r.check) S.d.check = checkShown(r.check);
  if (r.todo) { S.d.todo = r.todo; renderFoot(); renderRail(); }
  if ('can_undo' in r) S.canUndo = !!r.can_undo;
  if (r.reload_doc) placeDoc(true);                 // the whole Doc was uploaded again: the one shown loads again
  if (r.learned && r.learned.length) { S.learned.push(...r.learned); renderLearned(); }
  const notes = [];
  if (r.held) notes.push(r.held);
  if (r.conflicts && r.conflicts.length) {
    notes.push(t('conflicts', quoteList(r.conflicts)));
  }
  if (r.skipped && r.skipped.length) {
    notes.push(t('skipped', quoteList(r.skipped)));
  }
  if (r.kept && r.kept.length) {
    notes.push(t('kept', aiName(), quoteList(r.kept)));
  }
  if (r.warning) notes.push(r.warning);
  if (notes.length) showAlert(notes.join(' '));
  if (r.html && !S.dirty) { setDoc(r.html); S.shown = r.shown || ''; }
  else if (r.typed) S.shown = r.typed;              // the page as it was saved: later typing is compared with it
}

// the first 20 characters of each paragraph, quoted, in one line
const quoteList = (list) => list.map((c) => t('quote', c.slice(0, 20))).join(t('list_sep'));

// a change that needs the latest text (Claude, undo, a mail) waits for typing to be saved first
async function savedFirst() {
  await flush();
  if (S.dirty) { showAlert(t('save_first')); return false; }
  return true;
}

function jumpTo(item) {
  const el = docEl();
  const blocks = [...el.querySelectorAll('p, li, tr, h1, h2, h3')];
  const hit = blocks.find((b) => b.textContent.includes(item.anchor) && b.querySelector('.blank'))
           || blocks.find((b) => b.textContent.includes(item.anchor));
  const target = hit ? (hit.querySelector('.blank') || hit) : el.querySelector('.blank');
  const prompt = $('#promptInput');
  if (prompt) prompt.value = t('fill_prefix', item.label);
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
  const tab = S.tab === 'score' && d.score ? 'score' : ['comments', 'log'].includes(S.tab) ? S.tab : (open ? 'comments' : 'log');
  markScoreButton();
  if (!S.railOpen) {
    el.className = 'rail closed';
    el.innerHTML = `
      <button class="iconbtn" id="expand" title="${esc(t('expand'))}" aria-label="${esc(t('expand'))}">${ICON.expand}</button>
      <button class="iconbtn" id="railC" title="${esc(t('comments'))}" aria-label="${esc(t('comments'))}">${ICON.bubble}${open ? `<span class="badge">${open}</span>` : ''}</button>
      <button class="iconbtn" id="railL" title="${esc(t('activity'))}" aria-label="${esc(t('activity'))}">${ICON.clock}</button>`;
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
        <button class="tab${tab === 'comments' ? ' on' : ''}" role="tab" id="tabC">${esc(t('comments'))}${open ? `<b class="n">${open}</b>` : ''}</button>
        <button class="tab${tab === 'log' ? ' on' : ''}" role="tab" id="tabL">${esc(t('activity'))}</button>
        ${d.score ? `<button class="tab${tab === 'score' ? ' on' : ''}" role="tab" id="tabS">${esc(t('score_tab'))}</button>` : ''}
      </div>
      <span style="flex:1"></span>
      <button class="iconbtn" id="collapse" title="${esc(t('collapse'))}" aria-label="${esc(t('collapse'))}">${ICON.collapse}</button>
    </div>
    <div class="railbody" id="railbody">${tab === 'comments' ? commentsHTML(comments) : tab === 'score' ? scoreHTML(d.score) : logHTML(d.log || [])}</div>`;
  $('#tabC').addEventListener('click', () => { S.tab = 'comments'; renderRail(); });
  $('#tabL').addEventListener('click', () => { S.tab = 'log'; renderRail(); });
  if ($('#tabS')) $('#tabS').addEventListener('click', () => { if (S.tab !== 'score') S.tabBeforeScore = S.tab; S.tab = 'score'; renderRail(); });
  if (tab === 'score') wireScore(el, d.score);
  $('#collapse').addEventListener('click', () => { S.railOpen = false; renderRail(); markScoreButton(); });
  if (tab === 'comments') wireComments();
}

// beside the Google Doc: what is still blank, Claude's guesses to check, and the activity log (the Doc shows its
// own comments)
function renderDocsRail(el) {
  const d = S.d;
  const todo = d.todo || [];
  const all = d.check || [];
  // guesses about who a voice is go under 人員, with that voice; 待處理 has the blanks and the words heard
  const voiced = (c) => c.speaker && (d.voices || []).some((v) => v.group === c.speaker);
  const people = all.filter(voiced);
  const check = all.filter((c) => !voiced(c));
  const waiting = todo.length + check.length;
  const shown = d.speakers || {};
  const later = S.peopleLater[S.sel] || {};
  const unnamed = (d.voices || []).filter((v) => !(later[v.group] || v.name || shown[v.group])).length;   // voices nobody is picked for
  const tabs = ['todo', 'people', 'log', ...(d.score ? ['score'] : [])];
  const tab = tabs.includes(S.tab) ? S.tab : (waiting ? 'todo' : unnamed ? 'people' : 'log');
  const pick = (t) => () => { S.railOpen = true; S.tab = t; renderRail(); };
  markScoreButton();
  if (!S.railOpen) {
    el.className = 'rail closed';
    el.innerHTML = `
      <button class="iconbtn" id="expand" title="${esc(t('expand'))}" aria-label="${esc(t('expand'))}">${ICON.expand}</button>
      <button class="iconbtn" id="railF" title="${esc(t('to_handle'))}" aria-label="${esc(t('to_handle'))}">${ICON.lines}${waiting ? `<span class="badge${todo.length ? ' red' : ''}">${waiting}</span>` : ''}</button>
      <button class="iconbtn" id="railP" title="${esc(t('people'))}" aria-label="${esc(t('people'))}">${ICON.people}${unnamed ? `<span class="badge">${unnamed}</span>` : ''}</button>
      <button class="iconbtn" id="railL" title="${esc(t('activity'))}" aria-label="${esc(t('activity'))}">${ICON.clock}</button>`;
    $('#expand').addEventListener('click', () => { S.railOpen = true; renderRail(); });
    $('#railF').addEventListener('click', pick('todo'));
    $('#railP').addEventListener('click', pick('people'));
    $('#railL').addEventListener('click', pick('log'));
    return;
  }
  el.className = 'rail';
  const body = tab === 'todo'
    ? (waiting ? todo.map((it, i) => `<div class="todo" data-t="${i}"><div class="todohead"><span class="kind red">${esc(t('to_fill'))}</span>
            <button class="fixb ghost" data-skipt="${i}">${esc(t('skip'))}</button></div><button class="todobody"><b>${esc(it.label)}</b>${it.anchor && it.anchor !== it.label ? `<span>${esc(it.anchor)}</span>` : ''}</button></div>`).join('')
        + check.map((c, i) => `<div class="card guess"><span class="kind yellow">${esc(t(c.person ? 'new_person' : 'to_confirm'))}</span>${c.person
            ? `<div class="text"><b>${esc(c.person)}</b>${c.role ? `<span class="role">${esc(c.role)}</span>` : ''}</div>` : `<div class="text">${esc(c.label)}</div>`}
          ${S.fixing === c.label ? `<div class="fix"><input data-c="${i}" value="${esc(S.fixText)}" aria-label="${esc(t('fix'))}"
              placeholder="${esc(t(c.person || c.speaker || c.voice ? 'name_ph' : 'fix_ph'))}">
              <button class="fixb blue" data-save="${i}">${esc(t('save'))}</button><button class="fixb ghost" data-cancel="${i}">${esc(t('cancel'))}</button></div>`
            : `<div class="acts"><button class="okc2" data-c="${i}">${ICON.checkSmall}<span>${esc(t('looks_right'))}</span></button>
              <button class="fixb" data-fix="${i}">${esc(t('fix'))}</button><button class="fixb ghost" data-skip="${i}">${esc(t('skip'))}</button></div>`}</div>`).join('')
      : `<div class="empty">${esc(t('nothing_to_handle'))}</div>`)
    : tab === 'people' ? peopleHTML(people) : tab === 'score' ? scoreHTML(d.score) : logHTML(d.log || []);
  el.innerHTML = `
    <div class="railhead">
      <div class="tabs" role="tablist">
        <button class="tab${tab === 'todo' ? ' on' : ''}" role="tab" id="tabF">${esc(t('to_handle'))}${waiting ? `<b class="n${todo.length ? ' red' : ''}">${waiting}</b>` : ''}</button>
        <button class="tab${tab === 'people' ? ' on' : ''}" role="tab" id="tabP">${esc(t('people'))}${unnamed ? `<b class="n">${unnamed}</b>` : ''}</button>
        <button class="tab${tab === 'log' ? ' on' : ''}" role="tab" id="tabL">${esc(t('activity'))}</button>
        ${d.score ? `<button class="tab${tab === 'score' ? ' on' : ''}" role="tab" id="tabS">${esc(t('score_tab'))}</button>` : ''}
      </div>
      <span style="flex:1"></span>
      <button class="iconbtn" id="collapse" title="${esc(t('collapse'))}" aria-label="${esc(t('collapse'))}">${ICON.collapse}</button>
    </div>
    <div class="railbody" id="railbody">${body}</div>`;
  $('#tabF').addEventListener('click', pick('todo'));
  $('#tabP').addEventListener('click', pick('people'));
  $('#tabL').addEventListener('click', pick('log'));
  if ($('#tabS')) $('#tabS').addEventListener('click', () => { if (S.tab !== 'score') S.tabBeforeScore = S.tab; pick('score')(); });
  $('#collapse').addEventListener('click', () => { S.railOpen = false; renderRail(); markScoreButton(); });
  if (tab === 'score') wireScore(el, d.score);
  if (tab === 'todo') {
    // the whole card picks the item; its words are a button of their own for the keyboard, beside 略過
    el.querySelectorAll('.todo').forEach((b) => b.addEventListener('click', (e) => {
      if (e.target.closest('[data-skipt]')) return;
      const item = todo[Number(b.dataset.t)];
      const answering = !S.busy;                     // the box takes the question only when nothing is running
      showInDoc(item.find, true, answering);         // and then the keyboard stays there, ready for the answer
      askAbout(item);
    }));
    el.querySelectorAll('[data-skipt]').forEach((b) => b.addEventListener('click', () => skipBlank(todo[Number(b.dataset.skipt)])));
    el.querySelectorAll('.card.guess .text').forEach((x, i) => x.addEventListener('click', () => showInDoc(check[i].find)));
    el.querySelectorAll('.okc2[data-c]').forEach((b) => b.addEventListener('click', () => { b.disabled = true; confirmCheck(check[Number(b.dataset.c)]); }));
    wireFix(el, check, renderRail);
  }
  if (tab === 'people') wirePeople(el);
}

// 人員: one card per voice in the recording, with a menu to pick who it is. The menu starts on the name the minutes
// use (the AI's guess, put in after the write-up); picking someone puts that name in the minutes at once and
// remembers the voice. The people invited who did not speak are listed under it (Vin 2026-10-17).
function peopleHTML(people) {
  const d = S.d;
  const voices = d.voices || [];
  const shown = d.speakers || {};
  const later = S.peopleLater[S.sel] || {};        // picked while the AI rewrites: goes in after it
  const busy = S.peopleBusy || S.busy || aiBusy() || peopleQueued();
  const pickBusy = S.peopleBusy || S.busy;
  if (!voices.length) {
    const names = d.people || [];
    return `${calendarHTML()}<div class="empty">${esc(t('people_no_voices'))}</div>${names.length ? `<div class="pmin silent">${esc(t('people_attending', names.join(t('list_sep'))))}</div>` : ''}${learnedHTML()}${offHTML()}`;
  }
  const cards = voices.map((v) => {
    const waits = v.group in later;
    const name = later[v.group] || v.name || shown[v.group] || '';
    const playing = S.player.playing && S.peoplePlay === v.group;
    const open = S.pickOpen === v.group;
    const guess = (people.find((c) => c.speaker === v.group) || {}).who || '';
    const choices = [...new Set([guess, ...(d.people || [])].filter(Boolean))];
    const menu = !open ? '' : S.pickTyping === v.group
      ? `<div class="addrow"><input id="pIn" class="pin" maxlength="30" autocomplete="off" placeholder="${esc(t('people_add_ph'))}" aria-label="${esc(t('people_add_ph'))}" value="${esc(S.peopleTyped || '')}"><div class="ac" id="pAc" hidden></div></div>`
      : `<div class="menu" role="listbox">${choices.map((n) => `<div class="mi${n === name ? ' on' : ''}" role="option" data-n="${esc(n)}">${esc(n)}${n === guess ? `<span class="gs">${esc(t('people_guess_tag'))}</span>` : ''}</div>`).join('')}
          <div class="mi other" data-other="1">${esc(t('people_other'))}</div>
          ${busy ? '' : `<div class="mi drop" data-drop="1">${esc(t('people_drop', t('people_voice', v.group)))}</div>`}</div>`;   // also a voice named by mistake (Vin 2026-10-20)
    return `<div class="card person${name ? '' : ' guess'}"><div class="prow">
        <span class="pchip" style="${voiceStyle(v.group, !!name)}">${esc(t('people_voice', v.group))}</span>
        <span class="pmin">${esc(t('minutes', v.minutes))}</span><span style="flex:1"></span>
        <button class="plink phear" data-g="${esc(v.group)}">${esc(t(playing ? 'stop_play' : 'hear'))}</button></div>
      <div class="pickwrap"><button class="pick${name ? ' done' : ''}" data-g="${esc(v.group)}" aria-haspopup="listbox" aria-expanded="${open}"${pickBusy ? ' disabled' : ''}>
        ${name ? `<b>${esc(name)}</b>` : `<span class="ph">${esc(t('people_pick'))}</span>`}<span class="caret">▾</span></button>${menu}</div>
      ${waits ? `<span class="pwait">${esc(t('people_after_ai', aiName()))}</span>` : ''}</div>`;
  });
  const silent = d.silent || [];                   // the server tells names apart (陳怡君（Jessie） is Jessie)
  return `${calendarHTML()}<div class="phead">${esc(t('people_voices_n', voices.length))}</div>${cards.join('')}
    ${silentHTML(silent, busy)}${learnedHTML()}${offHTML()}`;
}

// the people listed who did not speak, each with ✕ to take them off this meeting (a name added by mistake, Vin 2026-10-20)
function silentHTML(names, busy) {
  if (!names.length) return '';
  return `<div class="pmin silent">${esc(t('people_silent_list', ''))}${names.map((n) =>
    `<span class="tchip">${esc(n)}<button data-rmp="${esc(n)}" title="${esc(t('remove'))}" aria-label="${esc(t('remove'))}"${busy ? ' disabled' : ''}>${ICON.xs}</button></span>`).join('')}</div>`;
}

// What the calendar event's note said about the meeting (a room booking names its host and department instead of
// inviting people), and where the people it brought in were learned (prototypes/department-people.html).
function calendarHTML() {
  const c = (S.d && S.d.calendar) || {};
  const depts = (c.departments || []).join(t('list_sep'));
  const parts = [];
  if (c.host) parts.push(t('people_cal_host', c.host));
  if (depts) parts.push(t('people_cal_dept', depts));
  if (c.roster_from && !c.learned) parts.push(t('people_cal_from', c.roster_from));
  return parts.length ? `<div class="fromcal">${esc(t('people_calendar', parts.join(t('people_cal_sep'))))}</div>` : '';
}

// this meeting taught the department's roster: the names it will bring into the next meeting of that department
function learnedHTML() {
  const c = (S.d && S.d.calendar) || {};
  if (!c.learned || !(c.roster || []).length) return '';
  return `<div class="learned">${esc(t('people_learned', (c.departments || []).join(t('list_sep')), c.roster.join(t('list_sep'))))}</div>`;
}

// voices taken off (移除講者 X), each with 復原 (Vin 2026-10-19)
function offHTML() {
  const busy = S.peopleBusy || S.busy || aiBusy() || peopleQueued();
  return (S.d.voices_off || []).map((v) => `<div class="pgone"><span>${esc(t('people_off', t('people_voice', v.group)))}</span>
    <button class="plink pback" data-g="${esc(v.group)}"${busy ? ' disabled' : ''}>${esc(t('undo'))}</button></div>`).join('');
}

// what the server sends back after a change to the people: who each voice is, the voices, the minutes
function peopleDone(r) {
  if (!S.d) return;
  for (const k of ['people', 'speakers', 'silent', 'calendar', 'voices', 'voices_off', 'transcript', 'voice_names', 'log', 'check']) if (r[k]) S.d[k] = r[k];
  afterEdit(r);
}

// true when the change went in
async function peopleCall(cmd, args) {
  if (S.peopleBusy || S.busy || aiBusy() || peopleQueued()) return false;
  const id = S.sel;
  S.peopleBusy = true; S.editSeq++;                 // a refresh meanwhile does not draw the old names again
  renderRail();
  try {
    const r = await call(cmd, { id, ...args });
    if (S.sel !== id) return false;
    peopleDone(r);
    return true;
  } catch (e) { showAlert(e.message); return false; } finally { S.peopleBusy = false; if (S.sel === id) renderRail(); }
}

const peopleQueued = (id = S.sel) => Object.keys(S.peopleLater[id] || {}).length > 0 || !!S.peopleSending[id];

// A voice named while the AI rewrites the minutes (Vin 2026-10-28: he could only wait): the name shows at once and
// goes in after the AI, since the app does one change to a meeting at a time. One name goes at a time; a voice named
// again before its name went sends only the last one.
function nameLater(group, name) {
  const id = S.sel;
  (S.peopleLater[id] || (S.peopleLater[id] = {}))[group] = name;
  S.editSeq++;                                      // a refresh meanwhile does not draw the old name again
  renderRail();
  if (!S.peopleSending[id]) sendLater(id);
}

async function sendLater(id) {
  const went = {};                                  // voice → the name this run put in
  for (;;) {
    const later = S.peopleLater[id] || {};
    const group = Object.keys(later).find((g) => went[g] !== later[g]);
    if (!group) break;
    const name = later[group];
    S.peopleSending[id] = { group, name };
    try {
      const r = await call('speaker', { id, group, name });
      if (S.sel === id) peopleDone(r);
    } catch (e) { showAlert(e.message); }           // also from another meeting: the name did not go in
    went[group] = name;
    if (later[group] === name) delete later[group];
  }
  delete S.peopleSending[id];
  if (!Object.keys(S.peopleLater[id] || {}).length) delete S.peopleLater[id];
  if (S.sel === id) renderRail();
}

// the names not sent yet when the window closes go with what still waits under 待修改, ahead of it
function namesLeft(id) {
  const now = S.peopleSending[id];
  return Object.entries(S.peopleLater[id] || {})
    .filter(([g, n]) => !(now && now.group === g && now.name === n))
    .map(([group, name]) => ({ kind: 'speaker', group, name }));
}

function closePick() { S.pickOpen = null; S.pickTyping = null; S.peopleTyped = ''; }

function wirePeople(el) {
  const d = S.d;
  const voices = d.voices || [];
  el.querySelectorAll('.phear').forEach((b) => b.addEventListener('click', () => {
    const v = voices.find((x) => x.group === b.dataset.g);
    if (!v) return;
    clearTimeout(S.peopleStop);
    if (S.player.playing && S.peoplePlay === v.group) { audio('pause', { at: S.player.pos }); setTimeout(renderRail, 300); return; }
    audio('play', { at: v.sample[0] }, true);
    S.peoplePlay = v.group;
    // the stretch of this voice, then it stops: what follows may be someone else
    const long = Math.max(3, (v.sample[1] || v.sample[0] + 8) - v.sample[0]) * 1000;
    S.peopleStop = setTimeout(() => {
      if (S.player.playing && S.peoplePlay === v.group) audio('pause', { at: S.player.pos }, true);
      S.peoplePlay = null;
      renderRail();
    }, long);
    setTimeout(renderRail, 600);
  }));
  el.querySelectorAll('.pick').forEach((b) => b.addEventListener('click', (e) => {
    e.stopPropagation();
    const g = b.dataset.g;
    if (S.pickOpen === g) closePick(); else { closePick(); S.pickOpen = g; }
    renderRail();
  }));
  const choose = (g, name) => {
    closePick();
    name = (name || '').trim();
    if (!name) renderRail();
    else if (aiBusy() || peopleQueued()) nameLater(g, name);
    else peopleCall('speaker', { group: g, name });   // into the minutes, and the voice is remembered
  };
  el.querySelectorAll('.menu .mi').forEach((m) => m.addEventListener('click', (e) => {
    e.stopPropagation();
    if (m.dataset.drop) { const g = S.pickOpen; closePick(); peopleCall('dropVoice', { group: g }); return; }   // no one: a split voice or a noise
    if (m.dataset.other) { S.pickTyping = S.pickOpen; S.peopleTyped = ''; renderRail(); const i = $('#pIn'); if (i) i.focus(); return; }
    choose(S.pickOpen, m.dataset.n);
  }));
  el.querySelectorAll('.pback').forEach((b) => b.addEventListener('click', () => peopleCall('dropVoice', { group: b.dataset.g, back: true })));
  el.querySelectorAll('[data-rmp]').forEach((b) => b.addEventListener('click', () => peopleCall('people', { action: 'remove', name: b.dataset.rmp })));
  const input = $('#pIn');
  if (!input) return;
  const list = $('#pAc');
  const group = S.pickTyping;
  let offered = [], at = 0;
  const offer = () => {                             // names from earlier meetings and every project's list
    const q = input.value.trim().toLowerCase();
    S.peopleTyped = input.value;
    offered = q ? (d.people_known || []).filter((n) => n.toLowerCase().includes(q)).slice(0, 6) : [];
    at = 0;
    list.hidden = !offered.length;
    list.innerHTML = offered.map((n, i) => `<div class="aci${i === at ? ' on' : ''}" data-i="${i}">${esc(n)}</div>`).join('');
  };
  input.addEventListener('click', (e) => e.stopPropagation());
  input.addEventListener('input', offer);
  input.addEventListener('keydown', (e) => {
    if (inputMethod(e)) return;                       // the 注音 candidate list takes Enter first (WebKit: 229)
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!offered.length) return;
      e.preventDefault();
      at = (at + (e.key === 'ArrowDown' ? 1 : offered.length - 1)) % offered.length;
      list.querySelectorAll('.aci').forEach((x, i) => x.classList.toggle('on', i === at));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(group, offered.length ? offered[at] : input.value);
    } else if (e.key === 'Escape') {
      closePick(); renderRail();
    }
  });
  list.addEventListener('mousedown', (e) => {       // before the box loses focus
    const x = e.target.closest('.aci');
    if (x) { e.preventDefault(); choose(group, offered[Number(x.dataset.i)]); }
  });
  offer();
}

// a blank to fill: the question goes into the box under the Doc, ready for the answer
function askAbout(item) {
  const input = $('#promptInput');
  if (!input || S.busy) return;
  input.value = t('fill_prefix', item.label);
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

function commentsHTML(list) {
  if (!list.length) return `<div class="empty">${esc(t('no_comments'))}</div>`;
  return list.map((c) => {
    const done = S.resolved.has(c.n);
    return `<div class="card${S.cfocus === c.n ? ' focus' : ''}${done ? ' done' : ''}" data-n="${c.n}" data-id="${esc(c.id)}">
      <div class="top"><span class="num">${c.n}</span><span class="who">${esc(c.who)}</span><span class="at">${esc(c.at)}</span>
        <span style="flex:1"></span>
        ${done ? `<span style="font-size:11px;color:var(--green)">${esc(t('resolved'))}</span>`
               : `<button class="okc" title="${esc(t('mark_resolved'))}" aria-label="${esc(t('mark_resolved'))}">${ICON.check}</button>`}</div>
      ${c.quote ? `<div class="quote">${esc(c.quote)}</div>` : ''}
      <div class="text">${esc(c.text)}</div>
      ${(c.replies || []).map((r) => `<div class="rep"><b>${esc(r.who)}</b>　${esc(r.text)}</div>`).join('')}
      ${done ? '' : `<input aria-label="${esc(t('reply_aria'))}" placeholder="${esc(t('reply'))}">`}
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
      if (e.key !== 'Enter' || inputMethod(e) || !input.value.trim()) return;
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
  if (!list.length) return `<div class="empty">${esc(t('no_log'))}</div>`;
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
    el.innerHTML = `<div id="askTop"></div>
      <div id="refBox"></div>
      <div class="prompt with-tools">
        <div class="mwrap"><button class="model" id="aiPick" title="${esc(t('ai_pick'))}" aria-label="${esc(t('ai_pick'))}"
            aria-haspopup="menu"></button><div class="mmenu" id="aiMenu" role="menu" hidden></div></div><span class="sep"></span>
        <div class="awrap"><button class="ib" id="attachPlus" aria-haspopup="menu">${ICON.plus}</button>
          <div class="amenu" id="attachMenu" role="menu" hidden>
            <button role="menuitem" data-a="file">${ICON.clip}<span>${esc(t('upload_file'))}</span></button>
            <button role="menuitem" data-a="link">${ICON.link}<span>${esc(t('paste_link'))}</span></button></div></div>
        <button class="ib" id="attachImage">${ICON.image}</button>
        <input id="promptInput" aria-label="${esc(t('ask_aria', aiName()))}" placeholder="${esc(t('ask_ph', aiName()))}">
        <button class="send" id="askGo" aria-label="${esc(t('send_ask'))}">${ICON.up}</button></div>
      <div class="quick">${QUICK.map((k) => `<button class="qk" title="${esc(t(`quick_${k}_hint`))}" data-k="${k}">${esc(t(`quick_${k}`))}</button>`).join('')}</div>`;
    const input = $('#promptInput');
    const go = () => { if (!S.pasting && !S.refPicking) ask(input.value.trim()); };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !inputMethod(e)) go(); });
    input.addEventListener('paste', pastePicture);    // a picture for the AI: no Google Doc needed
    $('#askGo').addEventListener('click', go);
    el.querySelectorAll('.qk').forEach((b) => b.addEventListener('click', () => ask('', b.dataset.k)));
    $('#aiPick').addEventListener('click', (e) => {
      e.stopPropagation();
      S.aiOpen = !S.aiOpen;
      if (S.menuOpen) { S.menuOpen = false; renderAttachMenu(); }
      closeProjMenu();
      renderAiMenu();
      if (S.aiOpen) loadAiStates();
    });
    $('#aiMenu').addEventListener('click', (e) => {
      e.stopPropagation();
      const b = e.target.closest('.mi');
      if (b && b.classList.contains('off')) { S.aiOpen = false; renderAiMenu(); setupAi(b.dataset.ai); }
      else if (b) switchAi(b.dataset.ai);
    });
    $('#attachPlus').addEventListener('click', (e) => {
      e.stopPropagation(); S.menuOpen = !S.menuOpen;
      if (S.aiOpen) { S.aiOpen = false; renderAiMenu(); }
      closeProjMenu();
      renderAttachMenu();
    });
    $('#attachImage').addEventListener('click', () => pickRef('refImage'));
    el.querySelectorAll('#attachMenu button').forEach((b) => b.addEventListener('click', () => {
      if (b.dataset.a === 'file') return pickRef('ref');
      S.menuOpen = false; S.urlOpen = true; renderAttachMenu(); renderRefs();
    }));
    renderRefs();
  }
  // while the AI works the box stays open and what is sent waits its turn (Vin 2026-10-19), files and pictures
  // for it too; another AI waits until it is done
  $('#promptInput').disabled = S.busy;
  el.querySelectorAll('.qk').forEach((b) => { b.disabled = S.busy; });
  el.querySelectorAll('.ib').forEach((b) => { b.disabled = S.busy; });
  for (const [sel, key] of [['#attachPlus', 'ref_plus'], ['#attachImage', 'ref_image']]) {
    $(sel).title = t(key, aiName()); $(sel).setAttribute('aria-label', t(key, aiName()));
  }
  if (S.busy || aiBusy()) S.aiOpen = false;
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
  btn.disabled = S.busy || aiBusy() || S.aiSaving;
  btn.classList.toggle('on', !!S.aiOpen);
  menu.hidden = !S.aiOpen;
  placeDoc();
  menu.innerHTML = `<div class="mhead">${esc(t('ai_menu_head'))}</div>` + AIS.map(([k]) => {
    const why = !have.includes(k) || states[k] === 'install' ? 'install' : states[k] === 'login' ? 'login' : '';
    const off = why && k !== key;
    return `<button class="mi${off ? ' off' : ''}" role="menuitemradio" aria-checked="${k === key}" data-ai="${k}">
      <i class="dot ${k}"></i><span class="mn">${AI_SHORT[k]}</span>${k === key ? `<span class="ck">${ICON.check}</span>` : ''}
      ${why ? `<span class="ms">${esc(t(why === 'install' ? 'not_installed' : 'not_signed_in'))}</span>` : ''}</button>`;
  }).join('');
  const input = $('#promptInput');
  if (input) {
    input.placeholder = t('ask_ph', aiName());
    input.setAttribute('aria-label', t('ask_aria', aiName()));
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
  if (key === was || S.busy || aiBusy() || S.aiSaving) return renderAiMenu();
  S.aiSaving = true;
  showAi(key);
  try {
    const r = await call('setupAI', { ai: key });
    if (r.ai && r.ai.state === 'login') {
      await call('setupAI', { ai: was }).catch(() => {});
      showAi(was);
      showAlert(t('ai_not_signed', AI_SHORT[key], AI_SHORT[was]));
    } else if (S.setup) S.setup.ai = r.ai;
  } catch (e) {
    showAi(was);
    showAlert(e.message);
  } finally {
    S.aiSaving = false;
    renderAiMenu();
  }
}

// --- 附件: files, links and pictures for 「參考附件」 ------------------------------------------

function renderAttachMenu() {
  const menu = $('#attachMenu');
  if (!menu) return;
  menu.hidden = !S.menuOpen;
  $('#attachPlus').classList.toggle('on', S.menuOpen);
  placeDoc();
}
document.addEventListener('click', (e) => {
  if (S.menuOpen && !e.target.closest('#attachMenu')) { S.menuOpen = false; renderAttachMenu(); }
  if (S.pickOpen && !e.target.closest('.pickwrap')) { closePick(); renderRail(); }
  if (S.aiOpen && !e.target.closest('#aiMenu')) { S.aiOpen = false; renderAiMenu(); }
  if (S.pmenu && !S.pmenu.busy && !e.target.closest('#projMenu')) closeProjMenu();
});

// what goes to the AI with the next sentence, above the box under 「給 Claude 參考」; each one can be taken off again.
// A pasted picture shows small; a picked picture, file or link by its name.
function renderRefs() {
  const box = $('#refBox');
  if (!box) return;
  const chip = (icon, name, attr) => `<span class="achip" title="${esc(name)}">${icon}<span class="an">${esc(name)}</span>
      <button class="ax" ${attr} aria-label="${esc(t('remove'))}">✕</button></span>`;
  const any = S.pics.length || S.refs.length;
  box.innerHTML = `${any ? `<div class="achips"><span class="forai">${esc(t('for_ai', aiName()))}</span>
      ${S.pics.map((x, i) => (x.url ? `<span class="picchip" title="${esc(x.name)}"><img src="${esc(x.url)}" alt="">
        <button class="ax" data-p="${i}" aria-label="${esc(t('remove'))}">✕</button></span>` : chip(ICON.image, x.name, `data-p="${i}"`))).join('')}
      ${S.refs.map((x, i) => chip(x.kind === 'link' ? ICON.link : ICON.clip, x.name, `data-r="${i}"`)).join('')}</div>` : ''}
    ${S.urlOpen ? `<div class="aurl"><input id="refUrl" aria-label="${esc(t('url_aria'))}" placeholder="${esc(t('url_ph'))}">
      <button class="btn" id="refUrlAdd">${esc(t('add'))}</button></div>` : ''}`.trim();
  box.querySelectorAll('[data-p]').forEach((b) => b.addEventListener('click', () => { S.pics.splice(Number(b.dataset.p), 1); renderRefs(); }));
  box.querySelectorAll('[data-r]').forEach((b) => b.addEventListener('click', () => { S.refs.splice(Number(b.dataset.r), 1); renderRefs(); }));
  const url = $('#refUrl');
  if (!url) return;
  const add = () => {
    const u = url.value.trim();
    if (!/^https?:\/\/\S+$/.test(u)) { showAlert(t('url_bad')); return; }
    if (!S.refs.some((x) => x.url === u)) S.refs.push({ kind: 'link', url: u, name: u });
    S.urlOpen = false;
    renderRefs();
    $('#promptInput').focus();
  };
  url.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !inputMethod(e)) add();
    if (e.key === 'Escape') { e.stopPropagation(); S.urlOpen = false; renderRefs(); }
  });
  $('#refUrlAdd').addEventListener('click', add);
  url.focus();
}

// what the window sends for the files and links handed to the AI
const refsOut = (refs) => (refs || []).map(({ kind, path, url }) => (kind === 'link' ? { kind, url } : { kind, path }));

// ＋ 上傳檔案 and the picture button beside the box: files to read and pictures to look at, with the next sentence
async function pickRef(kind) {
  S.menuOpen = false;
  renderAttachMenu();
  const id = S.sel;
  S.refPicking = true;                             // Enter waits: what is being picked goes with this sentence
  try {
    const r = await call('pick', { kind });
    if (S.sel !== id) return;
    for (const f of r.files || []) {
      if (kind === 'refImage') { if (!S.pics.some((x) => x.path === f.path)) S.pics.push({ path: f.path, name: f.name, url: '' }); }
      else if (!S.refs.some((x) => x.path === f.path)) S.refs.push({ kind: 'file', path: f.path, name: f.name });
    }
    renderRefs();
    const input = $('#promptInput');
    if (input) input.focus();
  } catch (e) { showAlert(e.message); } finally { S.refPicking = false; }
}

// ⌘V of a picture (a screenshot, an image copied from a page, a picture file copied in Finder): shown small above
// the box and sent with the next sentence for the AI to look at; it does not go into the minutes (Vin 2026-10-19: a
// screenshot pasted to show what to change had become an attachment). Pictures for 「參考附件」 come from the
// picture button. Text pastes as text.
async function pastePicture(e) {
  const clip = e.clipboardData;
  if (!clip || S.busy) return;
  const item = [...clip.items].find((i) => i.kind === 'file' && i.type.startsWith('image/'));
  if (!item && ![...clip.types].includes('Files')) return;
  e.preventDefault();
  const input = e.target;
  const text = clip.getData('text/plain');
  const blob = item && item.getAsFile();
  const id = S.sel;
  S.pasting = true;                                // Enter waits: the picture goes with this message
  try {
    const r = await call('pastePicture');
    if (S.sel !== id) return;                      // another meeting
    const files = r.files || [];
    files.forEach((f, i) => {
      if (!S.pics.some((x) => x.path === f.path)) S.pics.push({ path: f.path, name: f.name, url: !i && blob ? URL.createObjectURL(blob) : '' });
    });
    if (files.length) renderRefs();
    else if (text) input.setRangeText(text, input.selectionStart, input.selectionEnd, 'end');   // text, or a file that is no picture
  } catch (err) { showAlert(err.message); } finally { S.pasting = false; }
}

// --- 加入會議附件: files, links and pictures for 「參考附件」, each with its own 說明 ---------------------

// in the tag bar: what 「參考附件」 holds (a click opens it) and 加入會議附件, when the minutes have a Google Doc
function attachmentsHTML(after = true) {           // after the tags: a line between them
  const d = S.d, list = d.attachments || [];
  const can = !!(d.doc_url && !d.readonly);
  if (!list.length && !can) return '';
  const icon = { image: ICON.image, link: ICON.link, file: ICON.clip };
  return `${after ? '<span class="tsep"></span>' : ''}<span class="tl">${esc(t('attachments'))}</span>
    ${list.map((a, i) => `<button class="tfile" data-open="${i}" title="${esc(a.note ? `${a.note}${t('colon')}${a.name}` : a.name)}">${icon[a.kind] || ICON.clip}<span>${esc(a.name)}</span></button>`).join('')}
    ${can ? `<button class="tadd" id="attOpen"${S.busy ? ' disabled' : ''}>${ICON.plusSm}<span>${esc(t('add_attachment'))}</span></button>` : ''}`;
}

function bindAttachments(el) {
  const list = (S.d && S.d.attachments) || [];
  el.querySelectorAll('[data-open]').forEach((b) => b.addEventListener('click', () => {
    const a = list[Number(b.dataset.open)];
    if (a) call('link', { url: a.link, attachment: true }).catch(() => {});
  }));
  if ($('#attOpen')) $('#attOpen').addEventListener('click', openAttach);
}

function setAttachments(list) {
  if (!S.d || JSON.stringify(list) === JSON.stringify(S.d.attachments || [])) return;
  S.d.attachments = list;
  if (!S.tagAdding) renderTags();
}

function openAttach() {
  if (!S.d || S.busy) return;
  S.att = { items: [], urlOpen: false, busy: false, err: '' };
  S.sheet = 'attach';
  renderAttachSheet();
  placeDoc();
}

function renderAttachSheet() {
  const m = S.att;
  if (!m) return closeSheet();
  const icon = { image: ICON.image, link: ICON.link, file: ICON.clip };
  $('#sheet').innerHTML = `<div class="veil"><div class="sheet confirm pset attsheet" role="dialog" aria-label="${esc(t('add_attachment'))}">
    <h3>${esc(t('add_attachment'))}</h3>
    ${m.items.length ? `<div class="attitems">${m.items.map((it, i) => `<div class="attitem">
      <div class="attname">${icon[it.kind]}<span title="${esc(it.name)}">${esc(it.name)}</span>
        <button class="ax" data-rm="${i}" aria-label="${esc(t('remove'))}"${m.busy ? ' disabled' : ''}>✕</button></div>
      <input class="pinput" id="attNote${i}" data-i="${i}" maxlength="100" value="${esc(it.note)}" aria-label="${esc(t('att_note_for', it.name))}"
        placeholder="${esc(i ? t('att_note') : t('att_note_ph'))}"${m.busy ? ' disabled' : ''}></div>`).join('')}</div>` : ''}
    ${m.urlOpen ? `<div class="aurl"><input id="attUrl" class="pinput" aria-label="${esc(t('url_aria'))}" placeholder="${esc(t('url_ph'))}">
      <button class="btn" id="attUrlAdd">${esc(t('add'))}</button></div>` : ''}
    <div class="attadd">
      <button class="tadd" data-k="file"${m.busy ? ' disabled' : ''}>${ICON.clip}<span>${esc(t('upload_file'))}</span></button>
      <button class="tadd" data-k="link"${m.busy ? ' disabled' : ''}>${ICON.link}<span>${esc(t('paste_link'))}</span></button>
      <button class="tadd" data-k="image"${m.busy ? ' disabled' : ''}>${ICON.image}<span>${esc(t('insert_image'))}</span></button></div>
    ${m.err ? `<p class="dnote err">${esc(m.err)}</p>` : ''}
    <div class="dfoot"><button class="btn ghost" id="attCancel"${m.busy ? ' disabled' : ''}>${esc(t('cancel'))}</button>
      <button class="btn primary" id="attGo"${m.busy || !m.items.length ? ' disabled' : ''}>${m.busy ? ICON.spinWhite : ''}${esc(t('add'))}</button></div>
  </div></div>`;
  const sheet = $('#sheet');
  // typing changes the note kept here; nothing is drawn again, so the cursor stays where it is
  sheet.querySelectorAll('.attitem input').forEach((el) => el.addEventListener('input', () => { m.items[Number(el.dataset.i)].note = el.value; }));
  sheet.querySelectorAll('[data-rm]').forEach((b) => b.addEventListener('click', () => { m.items.splice(Number(b.dataset.rm), 1); renderAttachSheet(); }));
  sheet.querySelectorAll('.attadd [data-k]').forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.k === 'link') { m.urlOpen = true; renderAttachSheet(); return; }
    pickAttach(b.dataset.k);
  }));
  $('#attCancel').addEventListener('click', closeSheet);
  $('#attGo').addEventListener('click', sendAttach);
  const url = $('#attUrl');
  if (url) {
    const add = () => {
      const u = url.value.trim();
      if (!/^https?:\/\/\S+$/.test(u)) { m.err = t('url_bad'); renderAttachSheet(); return; }
      m.items.push({ kind: 'link', url: u, name: u, note: '' });
      m.urlOpen = false; m.err = '';
      renderAttachSheet();
      focusNote(m.items.length - 1);
    };
    url.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !inputMethod(e)) add();
      if (e.key === 'Escape') { e.stopPropagation(); m.urlOpen = false; renderAttachSheet(); }
    });
    $('#attUrlAdd').addEventListener('click', add);
    url.focus();
  }
}

function focusNote(i) { const el = $(`#attNote${i}`); if (el) el.focus(); }

async function pickAttach(kind) {
  const m = S.att;
  if (!m || m.busy) return;
  try {
    const r = await call('pick', { kind });
    if (S.att !== m) return;
    const first = m.items.length;
    for (const f of r.files || []) {
      if (!m.items.some((a) => a.path === f.path)) m.items.push({ kind, path: f.path, name: f.name, note: '' });
    }
    m.err = '';
    renderAttachSheet();
    if (m.items.length > first) focusNote(first);
  } catch (e) { m.err = e.message; renderAttachSheet(); }
}

// 加入: one line each in 「參考附件」, led by its note. The sheet stays open while the files go to Drive, and
// opens again with what was typed if they could not
async function sendAttach() {
  const m = S.att, id = S.sel;
  if (!m || m.busy || !m.items.length) return;
  if (S.busy || S.sending || aiBusy()) { m.err = t('attach_wait', aiName()); return renderAttachSheet(); }
  m.busy = true; m.err = ''; renderAttachSheet();
  S.sending = true;
  let saved = false;
  try { saved = await savedFirst(); } finally { S.sending = false; }
  if (!saved || S.att !== m) { m.busy = false; if (S.att === m) renderAttachSheet(); return; }
  const items = m.items.map(({ kind, path, url, note }) => ({ kind, path, url, note: note.trim() }));
  S.busy = true; S.busyText = 'attaching';
  S.asked = m.items.map((a) => a.name).join(t('list_sep')); S.askedQuick = ''; S.askedPic = ''; S.said = ''; S.saidErr = false; S.editSeq++;
  renderAsk(); renderTags();
  try {
    const r = await call('attach', { id, text: '', items });
    if (S.sel !== id || !S.d) return;
    if (S.att === m) closeSheet();
    S.said = r.reply || '';
    afterEdit(r);
  } catch (e) {
    if (S.sel !== id) return;
    m.busy = false; m.err = e.message; S.asked = '';
    if (S.att === m) renderAttachSheet(); else showAlert(e.message);
  } finally {
    if (S.sel === id) {
      S.busy = false; S.busyText = '';
      renderAsk(); renderTags(); renderFoot(); refreshLog();
    }
    runNext(id);
  }
}

// above the box: Claude at work, its answer with 復原, and what it learned from the user's own edits
function renderLearned() {
  const top = $('#askTop');
  if (!top) return;
  const learned = S.learned;
  const fresh = learned.length > S.learnShown;        // something new: the box comes back for it
  if (fresh) S.learnHidden = false;
  const kept = top.querySelector('.lrows');
  const scroll = kept ? kept.scrollTop : 0;        // turning one row off keeps the list where it was
  const w = S.work[S.sel];
  const now = w && w.now;
  const mini = (q) => (q && q.pics && q.pics[0] && q.pics[0].url ? `<img class="mini" src="${esc(q.pics[0].url)}" alt="">` : '');
  top.innerHTML = `
    ${S.busy ? `<div class="busy">${ICON.spin}<span>${esc(S.busyText ? t(S.busyText) : t('ai_working', aiName()))}</span></div>` : ''}
    ${!S.busy && S.said ? `<div class="replyline${S.saidErr ? ' err' : ''}">${S.saidErr ? '' : ICON.done}${S.askedPic ? `<img class="mini" src="${esc(S.askedPic)}" alt="">` : ''}
        <span class="asked">${esc(t('quote', S.askedQuick ? t(`quick_${S.askedQuick}`) : S.asked))}</span><span class="said">${esc(S.said)}</span>
        ${S.canUndo && !S.saidErr && !now ? `<button class="btn ghost" id="undo" style="height:24px;padding:0 10px;font-size:12px">${esc(t('undo'))}</button>` : ''}</div>` : ''}
    ${now ? `<div class="busy">${ICON.spin}${mini(now)}<span>${esc(t('ai_working_on', aiName(), cut(asked(now))))}</span></div>` : ''}
    ${w && w.waits.length ? `<div class="waits"><span class="wh">${esc(t('waiting'))} ${w.waits.length}</span>${w.waits.map((q, i) => `<div class="wr">
        <span class="wn">${i + 1}</span>${mini(q)}<span class="wt">${esc(asked(q))}</span>
        <button class="ax" data-w="${i}" aria-label="${esc(t('remove'))}">✕</button></div>`).join('')}</div>` : ''}
    ${learned.length && !S.learnHidden ? `<div class="learn${S.learnOpen ? ' open' : ''}"><div class="lh">${ICON.book}<span>${esc(t('learned_head', aiName()))}</span>
        ${learned.length > 2 ? `<span style="flex:1"></span><button class="btn ghost" id="learnMore" style="height:22px;padding:0 8px;font-size:11px">${esc(t(S.learnOpen ? 'collapse' : 'expand'))}</button>` : ''}</div>
        <div class="lrows">${learned.map((l, i) => {
          const keep = l.kind !== 'once';
          const where = t(keep && l.off ? 'learn_off' : { term: 'learn_term', pref: 'learn_pref', style: 'learn_pref', once: 'learn_once' }[l.kind]);
          const place = keep && !l.off && l.where
            ? `<span class="seg lseg">${['brief', 'glossary'].map((w) => `<button class="${l.where === w ? 'on' : ''}" data-mv="${i}" data-w="${w}">${esc(t(w === 'brief' ? 'learn_brief' : 'learn_term'))}</button>`).join('')}</span>`
            : `<span class="tag${keep && !l.off ? '' : ' gray'}">${where}</span>`;
          return `<div class="lr${keep && l.off ? ' off' : ''}"><span class="lt">${esc(l.text)}</span>
            ${place}<span style="flex:1"></span>
            ${keep ? `<button class="btn ghost" data-i="${i}" style="height:22px;padding:0 8px;font-size:11px">${esc(t(l.off ? 'learn_on_btn' : 'learn_off_btn'))}</button>` : ''}</div>`;
        }).join('')}</div></div>` : ''}`.trim();
  const rows = top.querySelector('.lrows');
  if (rows) rows.scrollTop = fresh ? rows.scrollHeight : scroll;   // something new: show it
  S.learnShown = learned.length;
  // the box shows what was just learned for 5 seconds, then goes (Vin 2026-10-18); not while the pointer is on it
  // or it is expanded. 操作紀錄 keeps every line.
  const box = top.querySelector('.learn');
  const hideLater = () => {
    clearTimeout(S.learnTimer);
    S.learnTimer = setTimeout(() => { if (!S.learnOpen && !S.learnHover) { S.learnHidden = true; renderLearned(); } }, 5000);
  };
  if (fresh) hideLater();
  if (box) {
    box.addEventListener('mouseenter', () => { S.learnHover = true; clearTimeout(S.learnTimer); });
    box.addEventListener('mouseleave', () => { S.learnHover = false; hideLater(); });
  }
  const more = $('#learnMore');
  if (more) more.addEventListener('click', () => { S.learnOpen = !S.learnOpen; if (!S.learnOpen) hideLater(); renderLearned(); });
  const undo = $('#undo');
  if (undo) undo.addEventListener('click', undoLast);
  top.querySelectorAll('.wr .ax').forEach((b) => b.addEventListener('click', () => {
    const q = w.waits.splice(Number(b.dataset.w), 1)[0];
    if (q && q.card) putBack(q.card);               // a correction taken off: its card is back to handle
    renderLearned();
  }));
  top.querySelectorAll('.learn .lr button[data-i]').forEach((b) => b.addEventListener('click', () => toggleLearned(Number(b.dataset.i))));
  top.querySelectorAll('.learn .lr button[data-mv]').forEach((b) => b.addEventListener('click', () => {
    if (!b.classList.contains('on')) moveLearned(Number(b.dataset.mv), b.dataset.w);
  }));
}

// what is sent goes to the AI one after another, per meeting: while it works on one the box stays open and what is
// sent meanwhile waits under 待修改 (Vin 2026-10-19: he could only wait). Each answer shows as it comes in; a meeting
// left meanwhile goes on by itself and shows its changes when it is opened again.
function ask(text, quick, extra = {}) {
  if (S.busy || (!text && !quick)) return;
  const id = S.sel;
  const w = S.work[id] || (S.work[id] = { now: null, waits: [] });
  const own = !extra.correct && !quick;              // a quick button leaves the pasted pictures for the next sentence
  w.waits.push({ text, quick: quick || '', pics: own ? S.pics : [], refs: own ? S.refs : [], ...extra });
  if (own) {
    S.pics = []; S.refs = []; S.urlOpen = false; renderRefs();
    const box = $('#promptInput');
    if (box) box.value = '';
  }
  if (w.now) renderLearned(); else runNext(id);
}

// a request as the user sees it: the sentence, the quick button's name, or the correction
function asked(q) { return q.quick ? t(`quick_${q.quick}`) : q.text; }

async function runNext(id) {
  const w = S.work[id];
  if (!w || w.now || !w.waits.length || (S.sel === id && (S.busy || S.sending))) return;
  if (S.sel === id) {                              // the user's own typing goes in before the AI starts
    S.sending = true;
    try {
      if (!(await savedFirst())) return renderLearned();   // the edits did not save: what was sent stays waiting
    } finally { S.sending = false; }
    if (w.now || !w.waits.length) return;
  }
  const q = w.now = w.waits.shift();
  if (S.sel === id) {
    S.said = ''; S.saidErr = false; S.editSeq++;
    if (docEl()) docEl().contentEditable = 'false';
    renderAsk();
  }
  let r = null, err = null;
  try {
    r = q.correct ? await call('correct', { id, item: q.correct.label, text: q.correct.value })
      : await call(q.quick ? 'quick' : 'ask', { id, text: q.quick || q.text, pictures: q.pics.map((x) => x.path),
        refs: refsOut(q.refs) });
  } catch (e) { err = e; }
  w.now = null;
  if (!w.waits.length) delete S.work[id];
  if (S.sel === id && S.d) {
    S.asked = q.text; S.askedQuick = q.quick; S.askedPic = (q.pics[0] && q.pics[0].url) || '';
    if (err) {
      S.said = err.message; S.saidErr = true;
      if (q.card) putBack(q.card);                 // the change did not go in: the card is back
    } else {
      S.said = r.reply || ''; S.canUndo = !!r.changed || S.canUndo;
      if (r.voices) peopleDone(r);                   // a voice named through 修改: 人員 and the transcript too
      else if (r.changed || r.html || q.correct) afterEdit(r);
    }
    if (docEl()) docEl().contentEditable = editable();
    renderAsk(); renderFoot(); renderRail(); refreshLog();
  }
  runNext(id);
}

// 待確認 cards skipped or put right whose answer is still on its way stay off the list, whatever an answer that
// started before them brings
function checkShown(list, id = S.sel) {
  const w = S.work[id];
  const going = new Set(w ? [w.now, ...w.waits].filter((q) => q && q.card).map((q) => q.card.label) : []);
  S.skipping.forEach((label) => going.add(label));
  return (list || []).filter((c) => !going.has(c.label));
}

function putBack(card) {
  if (!S.d || (S.d.check || []).some((c) => c.label === card.label)) return;
  S.d.check = [...(S.d.check || []), card];
  renderRail(); renderFoot();
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
    runNext(id);
  }
}

async function moveLearned(i, where) {
  const l = S.learned[i];
  try {
    const r = await call('moveLearned', { id: S.sel, item: l.id, where });
    S.learned[i] = r.learned;
    renderAsk(); refreshLog();
  } catch (e) { showAlert(e.message); }
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
    ${todo.length && !docs ? `<div class="row"><span class="lbl" style="color:var(--red)">${esc(t('to_fill'))} ${todo.length}</span>
      <div class="chips">${todo.map((t, i) => `<button class="chip red" data-t="${i}">${esc(t.label)}</button>`).join('')}</div></div>` : ''}
    ${check.length && !docs ? `<div class="row"><span class="lbl" style="color:var(--yellow-label)">${esc(t('to_confirm'))} ${check.length}</span>
      <div class="chips">${check.map((c, i) => (S.fixing === c.label
        ? `<span class="chip yellow fixchip"><span>${esc(c.label)}</span><input data-c="${i}" value="${esc(S.fixText)}" aria-label="${esc(t('fix'))}"
            placeholder="${esc(t(c.person || c.speaker || c.voice ? 'name_ph' : 'fix_ph'))}"><button class="okbtn" data-save="${i}" title="${esc(t('save'))}"
            aria-label="${esc(t('save'))}">${ICON.checkSmall}</button><button class="okbtn skip" data-cancel="${i}" title="${esc(t('cancel'))}"
            aria-label="${esc(t('cancel'))}">✕</button></span>`
        : `<span class="chip yellow"><button class="cl" data-fix="${i}" title="${esc(t('fix'))}">${esc(c.label)}</button>
            <button class="okbtn" data-c="${i}" title="${esc(t('looks_right'))}" aria-label="${esc(t('looks_right'))}">${ICON.checkSmall}</button>
            <button class="okbtn skip" data-skip="${i}" title="${esc(t('skip'))}" aria-label="${esc(t('skip'))}">✕</button></span>`)).join('')}</div></div>` : ''}
    ${p.open ? `<div class="player">
        <button class="play" id="pp" aria-label="${esc(t(p.playing ? 'pause' : 'play'))}">${p.playing ? ICON.pause : ICON.play}</button>
        <span class="tm" id="ptime">${mmss(p.pos)}</span>
        <div class="bar" id="pbar"><i id="pfill" style="width:${p.dur ? (p.pos / p.dur * 100).toFixed(2) : 0}%"></i></div>
        <span class="dur">${mmss(p.dur)}</span>
        <button class="speed" id="pspeed" aria-label="${esc(t('speed_aria'))}">${p.speed}x</button>
        <button class="iconbtn" id="pclose" aria-label="${esc(t('close_rec'))}">${ICON.x}</button></div>` : ''}
    <div class="buttons">
      <span style="flex:1"></span>
      ${d.doc_url && !docs ? `<button class="btn ghost" id="openGdoc">${ICON.open}<span>${esc(t('open_in_docs'))}</span></button>` : ''}
    </div>`;
  el.hidden = !el.querySelector('button, .row');      // 發送信件 is at the top: nothing left here, no empty row
  el.querySelectorAll('.chip.red').forEach((b) => b.addEventListener('click', () => jumpTo(todo[Number(b.dataset.t)])));
  el.querySelectorAll('.okbtn[data-c]').forEach((b) => b.addEventListener('click', () => confirmCheck(check[Number(b.dataset.c)])));
  if (!docs) wireFix(el, check, renderFoot);
  const on = (sel, fn) => { const x = $(sel); if (x) x.addEventListener('click', fn); };
  on('#openGdoc', () => call('link', { url: d.doc_url }).catch(() => {}));
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
    S.d.check = checkShown(r.check);
    if (r.learned && r.learned.length) { S.learned.push(...r.learned); renderAsk(); }
    renderFoot(); renderRail(); refreshLog();
  } catch (e) { showAlert(e.message); }
}

// 修改 and 略過 on the 待確認 items, in the side panel or along the bottom (Vin 2026-10-19): 修改 opens a box for what
// it should be, starting from the guess; 略過 takes the item off and nothing is learned
function wireFix(el, check, redraw) {
  if (S.fixing && !check.some((c) => c.label === S.fixing)) { S.fixing = ''; S.fixFocus = false; }   // handled elsewhere
  el.querySelectorAll('[data-fix]').forEach((b) => b.addEventListener('click', () => {
    const c = check[Number(b.dataset.fix)];
    S.fixing = c.label; S.fixText = c.who || c.person || c.meant || ''; S.fixFocus = true; S.fixPick = true;
    redraw();
  }));
  el.querySelectorAll('[data-skip]').forEach((b) => b.addEventListener('click', () => skipCheck(check[Number(b.dataset.skip)])));
  el.querySelectorAll('[data-cancel]').forEach((b) => b.addEventListener('click', () => { S.fixing = ''; redraw(); }));
  const fixed = (i) => {
    const box = el.querySelector(`input[data-c="${i}"]`);
    const right = box.value.trim();
    if (!right) return box.focus();
    S.fixing = '';
    fixCheck(check[i], right);
  };
  el.querySelectorAll('[data-save]').forEach((b) => b.addEventListener('click', () => fixed(Number(b.dataset.save))));
  const box = el.querySelector('input[data-c]');
  if (!box) return;
  box.addEventListener('input', () => { S.fixText = box.value; });
  box.addEventListener('focus', () => { S.fixFocus = true; });
  box.addEventListener('blur', () => { if (box.isConnected) S.fixFocus = false; });
  box.addEventListener('keydown', (e) => {
    if (inputMethod(e)) return;
    if (e.key === 'Enter') { e.preventDefault(); fixed(Number(box.dataset.c)); }
    if (e.key === 'Escape') { e.stopPropagation(); S.fixing = ''; redraw(); }
  });
  if (S.fixFocus) {                                // just opened, or drawn again while typing (an answer came in)
    box.focus();
    if (S.fixPick) box.select(); else box.setSelectionRange(box.value.length, box.value.length);
    S.fixPick = false;
  }
}

// 略過: the card goes at once (the answer may wait for the AI's turn) and comes back if it could not be skipped
async function skipCheck(item) {
  const id = S.sel;
  S.editSeq++;
  S.d.check = (S.d.check || []).filter((c) => c.label !== item.label);
  S.skipping.add(item.label);
  renderRail(); renderFoot();
  try {
    const r = await call('skip', { id, item: item.label });
    S.skipping.delete(item.label);
    if (S.sel !== id || !S.d) return;
    S.d.check = checkShown(r.check);
    renderFoot(); renderRail(); refreshLog();
  } catch (e) { S.skipping.delete(item.label); if (S.sel === id) { putBack(item); showAlert(e.message); } }
}

// 略過 on a 待補充 item: nobody is going to fill it, so its blank goes from the minutes (復原 brings it back). The
// card goes at once and comes back if the minutes could not be changed.
async function skipBlank(item) {
  const id = S.sel;
  if (S.busy || aiBusy(id) || !(await savedFirst())) return;   // 復原 stays for the change Claude is making
  S.busy = true; S.editSeq++;
  S.d.todo = (S.d.todo || []).filter((x) => x.label !== item.label);
  renderRail(); renderFoot(); renderAsk();
  try {
    const r = await call('skipBlank', { id, item: item.label });
    if (S.sel === id) afterEdit(r);
  } catch (e) {
    if (S.sel === id && S.d && !(S.d.todo || []).some((x) => x.label === item.label)) {
      S.d.todo = [...(S.d.todo || []), item];
      showAlert(e.message);
    }
  } finally {
    if (S.sel === id) { S.busy = false; renderAsk(); renderFoot(); renderRail(); refreshLog(); }
    runNext(id);
  }
}

// 修改 on a guess: what it should be goes to the AI like a sentence typed in the box (a voice is named at once). The
// card goes now and comes back if the change could not be made.
function fixCheck(item, right) {
  if (S.busy) return;
  S.d.check = (S.d.check || []).filter((c) => c.label !== item.label);
  renderRail(); renderFoot();
  const was = item.who || item.person || item.meant;
  ask(was ? t('fixed_as', was, right) : t('fixed_note', item.label, right), '', { correct: { label: item.label, value: right }, card: item });
}

function audio(action, args = {}, fromPeople = false) {
  if (!fromPeople && action !== 'rate') { clearTimeout(S.peopleStop); S.peoplePlay = null; }   // ▶ 聽錄音's stop is off
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
  if (name === 'jobs') { openFirst().then((empty) => {
    if (empty) return;
    const job = S.jobs.find((j) => j.id === S.sel);
    if (S.d && job && S.d.status === 'working' && job.step !== S.d.step) return select(S.sel);   // recording → 轉成逐字稿 → …
    if (S.d && job && job.status !== S.d.status && !(S.d.status === 'ready' && job.status === 'sent')) select(S.sel);
  }); }
  if (name === 'select' && (data.id !== S.sel || !S.d)) select(data.id);
  if (name === 'docfail' && docsMode()) { S.docFailed = true; renderMain(); }
  if (name === 'setup') openSetup();
  if (name === 'usage') openUsage();
  if (name === 'language' && data) setLang(data.lang);
  if (name === 'player') {
    const p = S.player;
    const wasPlaying = p.playing;
    p.pos = data.pos; p.dur = data.dur || p.dur; p.playing = !!data.playing; p.speed = data.rate || p.speed;
    const t = $('#ptime'); const f = $('#pfill');
    if (t && wasPlaying === p.playing) { t.textContent = mmss(p.pos); if (f) f.style.width = p.dur ? (p.pos / p.dur * 100).toFixed(2) + '%' : '0'; }
    else { renderFoot(); markPlaying(); }
  }
};

// --- switching language ----------------------------------------------------------------------

// the words outside what app.js draws: the page's language and the list's name for screen readers
function applyLang() {
  document.documentElement.lang = LANG === 'zh-TW' ? 'zh-Hant' : 'en';
  $('#side').setAttribute('aria-label', t('side_aria'));
}

// everything on screen is drawn again in the new language; what is being typed (the minutes in the preview, the
// box under them, a name in the transcript) stays as it is
function setLang(lang) {
  lang = lang === 'zh-TW' ? 'zh-TW' : 'en';
  if (lang === LANG) return;
  LANG = lang;
  applyLang();
  renderSide();
  if (S.sel) {
    const input = $('#promptInput');
    const typed = input ? { value: input.value, focus: document.activeElement === input,
                            start: input.selectionStart, end: input.selectionEnd } : null;
    const doc = docEl();
    const docHtml = doc && S.d && !docsMode() ? doc.innerHTML : null;
    const paper = $('#main .paper');
    const scrolled = paper ? paper.scrollTop : 0;
    renderMain();
    if (docHtml !== null && docEl()) docEl().innerHTML = docHtml;
    const paperNow = $('#main .paper');
    if (paperNow) paperNow.scrollTop = scrolled;
    const inputNow = $('#promptInput');
    if (typed && inputNow) {
      inputNow.value = typed.value;
      if (typed.focus) { inputNow.focus(); inputNow.setSelectionRange(typed.start, typed.end); }
    }
  } else renderMain();
  if (S.sheet === 'setup') renderSetup();
  else if (S.sheet === 'mail') renderMail();
  else if (S.sheet === 'delete') renderDelete();
  else if (S.sheet === 'project') renderProject();
  else if (S.sheet === 'transcript') {
    const v = $('#vinput');
    openTranscript({ ask: S.tAsk, typed: v ? v.value : '' });
  }
}

// --- sheets ----------------------------------------------------------------------------------

function closeSheet() { S.sheet = null; S.att = null; $('#sheet').innerHTML = ''; placeDoc(); }

// the transcript, each line with who said it (by voice). A voice not named yet shows as 講者 A; clicking a
// name asks who it is, for every line of that voice or just this line, and the app remembers the voice
const TINTS = [['#dbe8fd', '#1c4f9e'], ['#fde8d7', '#9a4a07'], ['#ece3fb', '#5b2d9e'], ['#dff3e3', '#14532d'],
               ['#fde2ec', '#9d1b4f'], ['#d9f2f2', '#0f5e5e']];
function voiceStyle(group, named) {
  const at = Math.max(0, (S.d.voices || []).findIndex((v) => v.group === group));
  const [bg, fg] = TINTS[at % TINTS.length];
  return named ? `background:${bg};color:${fg}` : `background:transparent;color:${fg};border:1px dashed ${fg}`;
}

// a voice nobody has named yet comes from the transcript as 講者 A (Chinese minutes) or Speaker A (English ones)
const UNNAMED = /^(講者|Speaker) /;

function openTranscript(keep = {}) {
  const d = S.d;
  const voices = d.voices || [];
  const before = $('#sheet .lines');
  const scrolled = before ? before.scrollTop : 0;
  S.sheet = 'transcript';
  S.tAsk = keep.ask || null;                     // a language switch draws the sheet again with the same question
  placeDoc();
  const ask = keep.ask;
  const askVoice = ask ? voices.find((v) => v.group === ask.group) : null;
  const askLabel = ask && ask.line != null ? (d.transcript[ask.line].who || (askVoice && askVoice.label)) : askVoice && askVoice.label;
  const names = [...new Set([...(d.voice_names || []), ...voices.filter((v) => v.name).map((v) => v.name)])];
  $('#sheet').innerHTML = `<div class="veil"><div class="sheet" role="dialog" aria-label="${esc(t('transcript'))}">
    <div style="display:flex;align-items:baseline;gap:10px"><h3>${esc(t('transcript'))}</h3><span style="font-size:12px;color:var(--muted)">${esc(d.title)}　${esc(shortDay(d))}</span></div>
    ${voices.length ? `<div class="vchips">${voices.map((v) => `<button class="vchip" data-g="${esc(v.group)}" style="${voiceStyle(v.group, v.name)}">${esc(v.label)}<span>${esc(t('minutes', v.minutes))}</span></button>`).join('')}</div>` : ''}
    ${ask ? `<div class="vname">
      <div class="vrow"><b>${t('who_is', esc(askLabel))}</b><span style="flex:1"></span><button class="btn ghost" id="vplay">${esc(t(S.player.playing ? 'stop_play' : 'hear'))}</button></div>
      <div class="vrow">${names.map((n) => `<button class="vsug" data-n="${esc(n)}">${esc(n)}</button>`).join('')}<input id="vinput" maxlength="30" placeholder="${esc(t('name_ph'))}" aria-label="${esc(t('name_ph'))}" value="${esc(keep.typed || '')}"></div>
      <div class="vrow"><button class="btn primary" id="vall">${esc(t('apply_all'))}</button>${ask.line != null ? `<button class="btn ghost" id="vone">${esc(t('only_line'))}</button>` : ''}<button class="btn ghost" id="vcancel">${esc(t('cancel'))}</button></div>
    </div>` : ''}
    ${keep.toast ? `<div class="vtoast">${esc(keep.toast)}</div>` : ''}
    <div class="lines">${(d.transcript || []).map((line, i) => `<div><button class="tm" data-i="${i}" title="${esc(t('listen_here'))}">${esc(line.at)}</button>${line.who ? `<button class="who" data-g="${esc(line.group || '')}" data-line="${i}" style="${voiceStyle(line.group, !UNNAMED.test(line.who))}">${esc(line.who)}</button>` : ''}<span>${esc(line.text)}</span></div>`).join('')}</div>
    <div style="display:flex;justify-content:flex-end"><button class="btn ghost" id="closeT">${esc(t('close'))}</button></div></div></div>`;
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
    setTimeout(() => { const b = $('#vplay'); if (b) b.textContent = t(S.player.playing ? 'stop_play' : 'hear'); }, 600);
  });
  const apply = async (oneLine) => {
    const name = (picked || input.value).trim();
    if (!name) { input.focus(); return; }
    try {
      const r = await call('speaker', { id: S.sel, group: ask.group, name, ...(oneLine ? { line: ask.line } : {}) });
      d.transcript = r.transcript || d.transcript;
      d.voices = r.voices || d.voices;
      d.voice_names = r.voice_names || d.voice_names;
      if (!oneLine) { if (r.people) d.people = r.people; afterEdit(r); }   // the minutes say the name now
      const guess = oneLine ? null : (d.check || []).find((c) => c.speaker === ask.group);
      openTranscript({ toast: oneLine ? '' : t('voice_saved', name) });
      if (guess) await confirmCheck(guess);          // named by hand: the guess about this voice is settled
      else renderRail();
      refreshLog();
    } catch (e) { showAlert(e.message); }
  };
  $('#vall').addEventListener('click', () => apply(false));
  if ($('#vone')) $('#vone').addEventListener('click', () => apply(true));
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !inputMethod(e)) { e.preventDefault(); apply(false); } });
}

// a Word or PDF attachment: the mail says 詳細如附件 where the Doc's address was (Vin 2026-10-15), and the
// address comes back when the Google 文件連結 is picked again. These words go into the mail, so they follow the
// minutes' language (d.minutes_lang), not the window's: English minutes get "; please see the attached file."
const DOC_URL = /[:：]?[ \t]*\n?[ \t]*https:\/\/docs\.google\.com\/document\/[^\s]+/;
const mailWords = () => STRINGS[S.d && S.d.minutes_lang === 'en' ? 'en' : 'zh-TW'];
function withAttachment(body) {
  const w = mailWords();
  const attached = w.mail_attached;
  return DOC_URL.test(body) ? body.replace(DOC_URL, attached).replace(w.mail_period + attached, attached) : body;
}
function withLink(body, url) {
  if (DOC_URL.test(body)) return body;
  const w = mailWords();
  return body.includes(w.mail_attached) ? body.replace(w.mail_attached, `${w.mail_link_colon}\n${url}`) : `${body.trimEnd()}\n\n${url}`;
}

// The recipients open as the meeting's people, each with the address Vinutes found (the calendar invitation, the
// company directory, a mail sent before); one without an address is a dashed chip. Typing offers people to pick
// (prototypes/mail-recipients.html, Vin 2026-10-20).
function openMail() {
  const m = S.d.mail;
  const rcpts = (m.people || []).map((p) => ({ name: p.name, mail: p.mail || '' }));
  for (const a of m.to || []) if (!rcpts.some((r) => r.mail === a)) rcpts.push({ name: a, mail: a });
  // the sheet opens on the Doc link: a text a Word or PDF preview kept gets its link back
  const body = S.d.doc_url && !DOC_URL.test(m.body) ? withLink(m.body, S.d.doc_url) : m.body;
  S.mail = { rcpts, subject: m.subject, body, linkBody: body, fmt: 'gdoc', info: '', sending: false, err: '',
             files: S.d.attach_files || 0, typed: '', sugg: [], at: 0, seq: 0 };
  S.sheet = 'mail';
  placeDoc();
  renderMail();
  mailSummary();
}

// The mail's 會議目的 and 重點 for the minutes as they are now, edits still being saved included: when the minutes
// changed after the AI wrote the mail, the AI writes them again from the minutes (Vin 2026-10-27). Only those two
// paragraphs are swapped, where the text still has them as the sheet opened with them: whatever else the user typed
// meanwhile stays, and a word being composed (注音) is not broken. 寄出 waits for the answer.
async function mailSummary() {
  const m = S.mail;
  const id = S.sel;
  const old = summaryOf(m.body);
  m.asking = true; showMailNote();
  const slow = setTimeout(() => { if (S.mail === m) { m.wait = true; showMailNote(); } }, 500);
  let r = null;
  try { await flush(); r = await call('mailSummary', { id }); } catch (e) { /* the text the sheet opened with stays */ }
  clearTimeout(slow);
  if (S.sheet !== 'mail' || S.mail !== m || S.sel !== id) return;
  m.wait = false; m.asking = false;
  const box = $('#body');
  if (box) m.body = box.value;
  if (r && r.summary && old && r.summary !== old) {
    // the paragraphs as the text has them, whatever the blank lines between them
    const at = new RegExp(old.split('\n\n').map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\n\\s*\\n'));
    const swap = (text) => text.replace(at, () => r.summary);
    m.linkBody = swap(m.linkBody);
    const next = swap(m.body);
    if (next !== m.body) { m.body = next; if (box) box.value = next; }
  } else if (r && r.body && !old && m.body === m.linkBody && m.fmt === 'gdoc') {   // no summary in the text yet
    m.body = r.body; m.linkBody = r.body; if (box) box.value = r.body;
  }
  showMailNote();
}

// the 會議目的 and 重點 paragraphs of a mail text, with the list right after them (minutes_app.summary_text)
function summaryOf(text) {
  const label = /^\s*(會議目的|重點|Purpose|Highlights)\s*[:：]/;
  const item = /^\s*(?:[-*•]|\d+[.、)])\s+\S/;
  const found = [];
  let after = false;
  for (const p of text.trim().split(/\n\s*\n/)) {
    if (label.test(p) || (after && p.split('\n').every((l) => item.test(l)))) { found.push(p); after = true; } else after = false;
  }
  return found.join('\n\n');
}

function mailNote(m) {
  return say(m.err) || (m.wait ? t('summary_wait') : '') || (t(m.fmt === 'gdoc' ? 'note_gdoc' : 'note_file')
    + (m.files ? t('note_files', m.files) : ''));
}

function showMailNote() {
  const m = S.mail;
  const note = $('#sheet .note');
  if (note) { note.textContent = mailNote(m); note.classList.toggle('err', !!m.err); }
  const send = $('#mailSend');
  if (send) send.disabled = !!(m.sending || m.asking);
}

const mailTo = () => S.mail.rcpts.filter((r) => r.mail).map((r) => r.mail);

function renderMail() {
  const m = S.mail;
  const d = S.d;
  $('#sheet').innerHTML = `<div class="veil"><div class="sheet" role="dialog" aria-label="${esc(t('send_mail'))}">
    <h3>${esc(t('send_mail'))}</h3>
    <div class="grid">
      <span class="k">${esc(t('mail_from'))}</span><span>${esc(d.mail.from)}</span>
      <span class="k" style="align-self:start;padding-top:6px">${esc(t('mail_to'))}</span>
      <div class="field tokens" id="tokens">${m.rcpts.map((r, i) => `<span class="token${r.mail ? '' : ' missing'}"${r.mail ? '' : ` data-fill="${esc(r.name)}" title="${esc(t('add_rcpt'))}"`}><span>${esc(r.name)}</span>${r.mail && r.mail !== r.name ? `<small>${esc(r.mail)}</small>` : ''}${r.mail ? '' : `<small>${esc(t('rcpt_no_mail'))}</small>`}
        <button data-i="${i}" aria-label="${esc(t('remove_rcpt'))}">${ICON.xs}</button></span>`).join('')}
        <input id="addTo" autocomplete="off" aria-label="${esc(t('add_rcpt'))}" placeholder="${esc(t('add_rcpt'))}" value="${esc(m.typed)}">
        ${rcptMenuHTML()}</div>
      <label class="k" for="subj">${esc(t('mail_subject'))}</label><input class="field" id="subj" value="${esc(m.subject)}">
      <span class="k">${esc(t('mail_attachment'))}</span>
      <div style="display:flex;align-items:center;gap:10px"><div class="seg" role="radiogroup" aria-label="${esc(t('mail_attachment'))}">
        ${FORMATS.map((k) => `<button role="radio" aria-checked="${m.fmt === k}" class="${m.fmt === k ? 'on' : ''}" data-f="${k}">${esc(t(`fmt_${k}`))}</button>`).join('')}</div>
        <span style="font-size:12px;color:var(--muted)">${esc(say(m.info))}</span></div>
    </div>
    <textarea id="body" aria-label="${esc(t('mail_body'))}">${esc(m.body)}</textarea>
    <div style="display:flex;align-items:center;gap:10px">
      <span class="note${m.err ? ' err' : ''}">${esc(mailNote(m))}</span>
      <button class="btn ghost" id="mailCancel"${m.sending ? ' disabled' : ''}>${esc(t('cancel'))}</button>
      <button class="btn primary" id="mailSend"${m.sending || m.asking ? ' disabled' : ''}>${esc(t(m.sending ? 'sending' : 'send_mail_btn'))}</button></div>
  </div></div>`;
  const keep = () => { m.subject = $('#subj').value; m.body = $('#body').value; };
  const again = () => { keep(); renderMail(); const i = $('#addTo'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
  $('#tokens').querySelectorAll('.token button').forEach((b) => b.addEventListener('click', () => { keep(); m.rcpts.splice(Number(b.dataset.i), 1); renderMail(); }));
  $('#tokens').querySelectorAll('.token[data-fill]').forEach((c) => c.addEventListener('click', (e) => {   // no address: type one for this name
    if (e.target.closest('button')) return;
    m.rcpts.splice(m.rcpts.findIndex((r) => r.name === c.dataset.fill && !r.mail), 1);
    m.typed = c.dataset.fill; m.sugg = []; again(); suggestRcpts();
  }));
  const add = $('#addTo');
  const addTokens = () => {
    const parts = add.value.split(/[,，、;\s]+/).map((t) => t.trim().toLowerCase()).filter((t) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(t));
    if (!parts.length) return false;
    for (const a of parts) if (!m.rcpts.some((r) => r.mail === a)) m.rcpts.push({ name: a, mail: a });
    m.typed = ''; m.sugg = [];
    again();
    return true;
  };
  // while an input method is composing (注音, 拼音) nothing is asked and nothing is redrawn: the menu comes after the word
  add.addEventListener('input', (e) => { m.typed = add.value; m.at = 0; if (!inputMethod(e)) suggestRcpts(); });
  add.addEventListener('compositionend', () => { m.typed = add.value; m.at = 0; suggestRcpts(); });
  add.addEventListener('keydown', (e) => {
    if (inputMethod(e)) return;
    if (e.key === 'ArrowDown' && m.sugg.length) { e.preventDefault(); m.at = (m.at + 1) % m.sugg.length; renderRcptMenu(); }
    else if (e.key === 'ArrowUp' && m.sugg.length) { e.preventDefault(); m.at = (m.at + m.sugg.length - 1) % m.sugg.length; renderRcptMenu(); }
    else if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); if (m.sugg.length) pickRcpt(m.at); else addTokens(); }
    else if (e.key === 'Escape' && m.sugg.length) { e.stopPropagation(); m.seq++; m.sugg = []; renderRcptMenu(); }
  });
  add.addEventListener('blur', () => { if (add.value.trim() && !m.sugg.length) addTokens(); });
  wireRcptMenu();
  $('#subj').addEventListener('input', keep);
  $('#body').addEventListener('input', keep);
  $('#sheet').querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', async () => {
    keep();
    const before = m.fmt;
    m.fmt = b.dataset.f; m.info = m.fmt === 'gdoc' ? '' : ['preparing']; m.err = '';
    if (before === 'gdoc' && m.fmt !== 'gdoc') { m.linkBody = m.body; m.body = withAttachment(m.body); }
    if (before !== 'gdoc' && m.fmt === 'gdoc') {
      m.body = m.body === withAttachment(m.linkBody) ? m.linkBody : withLink(m.body, S.d.doc_url || '');
    }
    renderMail();
    if (m.fmt === 'gdoc') return;
    const fmt = m.fmt;
    try {
      const r = await call('mailPrepare', { id: S.sel, to: mailTo(), subject: m.subject, body: m.body, format: fmt });
      if (m.fmt === fmt) { m.info = `${r.attachment}　${r.attachment_kb} KB`; renderMail(); }
    } catch (e) { if (m.fmt === fmt) { m.info = ''; m.err = e.message; renderMail(); } }
  }));
  $('#mailCancel').addEventListener('click', () => { if (!m.sending) closeSheet(); });
  $('#mailSend').addEventListener('click', sendMail);
}

// the people whose name or address holds what was typed, from contacts.py; an address being typed needs no menu.
// Only the menu is redrawn (renderRcptMenu), never the box being typed in.
let suggestTimer = null;
function suggestRcpts() {
  const m = S.mail;
  clearTimeout(suggestTimer);
  const q = (m.typed || '').trim();
  const seq = ++m.seq;                              // an answer to an earlier question is dropped
  if (!q || q.includes('@')) { if (m.sugg.length) { m.sugg = []; renderRcptMenu(); } return; }
  suggestTimer = setTimeout(async () => {
    try {
      const r = await call('suggest', { id: S.sel, q });
      if (S.sheet !== 'mail' || S.mail !== m || seq !== m.seq) return;
      const have = new Set(m.rcpts.map((x) => x.mail));
      m.sugg = (r.people || []).filter((p) => !have.has(p.mail));
      m.at = 0;
      renderRcptMenu();
    } catch (e) { /* no menu: the address can still be typed */ }
  }, 150);
}

function rcptMenuHTML() {
  const m = S.mail;
  return m.sugg.length ? `<div class="ac rcpts" id="rcptAc" role="listbox">${m.sugg.map((p, i) => `<div class="aci${i === m.at ? ' on' : ''}" role="option" data-i="${i}"><span>${esc(p.name)}</span><small>${esc(p.mail)}</small><span class="src">${esc(t('rcpt_src_' + (p.src || 'mail')) || '')}</span></div>`).join('')}</div>` : '';
}

function renderRcptMenu() {
  const box = $('#tokens');
  if (!box) return;
  const old = $('#rcptAc');
  if (old) old.remove();
  box.insertAdjacentHTML('beforeend', rcptMenuHTML());
  wireRcptMenu();
}

function wireRcptMenu() {
  const box = $('#tokens');
  if (!box) return;
  box.querySelectorAll('.aci').forEach((el) => el.addEventListener('mousedown', (e) => { e.preventDefault(); pickRcpt(Number(el.dataset.i)); }));
}

function renderMailKeepingFocus() {
  const m = S.mail;
  const focused = document.activeElement && document.activeElement.id === 'addTo';
  m.subject = $('#subj').value; m.body = $('#body').value;
  renderMail();
  if (focused) { const i = $('#addTo'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
}

function pickRcpt(i) {
  const m = S.mail;
  const p = m.sugg[i];
  if (!p) return;
  if (!m.rcpts.some((r) => r.mail === p.mail)) m.rcpts.push({ name: p.name, mail: p.mail });
  m.typed = ''; m.sugg = []; m.at = 0; m.seq++;
  renderMailKeepingFocus();
  const input = $('#addTo'); if (input) input.focus();
}

// the menu goes when the user clicks somewhere else in the sheet
document.addEventListener('mousedown', (e) => {
  if (S.sheet === 'mail' && S.mail && S.mail.sugg.length && !e.target.closest('#tokens')) { S.mail.sugg = []; S.mail.seq++; renderRcptMenu(); }
});

async function sendMail() {
  const m = S.mail;
  if (m.sending || m.asking) return;
  m.subject = $('#subj').value; m.body = $('#body').value;
  if (!mailTo().length) { m.err = ['need_rcpt']; renderMail(); return; }
  await flush();
  if (S.dirty) { m.err = ['mail_unsaved']; renderMail(); return; }
  m.sending = true; m.err = '';
  renderMail();
  const id = S.sel;
  try {
    const sent_to = m.rcpts.filter((r) => r.mail).map((r) => ({ name: r.name === r.mail ? '' : r.name, mail: r.mail }));
    const r = await call('send', { id, to: mailTo(), subject: m.subject, body: m.body, format: m.fmt });
    call('contacts', { id, people: sent_to }).catch(() => {});   // remembered for the next mail's menu (寄過)
    if (S.sel !== id) return;
    S.d.sent = r.sent;
    closeSheet();
    renderHead();
    loadList();
    refreshLog();
  } catch (e) {
    m.sending = false; m.err = e.message;
    if (S.sheet === 'mail') renderMail();
  }
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && S.ctx) { closeCtx(); return; }
  if (e.key === 'Escape' && S.aiOpen) { S.aiOpen = false; renderAiMenu(); return; }
  if (e.key === 'Escape' && S.pmenu) { if (!S.pmenu.busy) closeProjMenu(); return; }
  if (e.key === 'Escape' && S.sheet === 'delete' && S.del && S.del.busy) return;
  if (e.key === 'Escape' && S.sheet === 'project' && S.pset && S.pset.busy) return;
  if (e.key === 'Escape' && S.sheet === 'attach' && S.att && S.att.busy) return;
  if (e.key === 'Escape' && S.sheet && !(S.mail && S.mail.sending)) { closeSheet(); return; }
  if (e.key === 'Escape' && S.picking) { endPicking(); renderSide(); }
});

// --- 環境設定自檢 ------------------------------------------------------------------------------------
// what this computer still needs: two items macOS answers (microphone, notifications), eight setup_check.py does

// [key, icon, icon colour, needed]; the name, the one line shown while it is not done yet and the button are
// t('setup_<key>'), t('setup_<key>_desc') and t('setup_<key>_btn')
const SETUP = [
  ['mic', '🎙', '#fde8e7', true],
  ['notify', '🔔', '#fdf3d7', false],
  ['speech', '📝', '#e3ecfd', true],
  ['voice', '👥', '#ece3fb', false],
  ['ai', '🤖', '#fde8d7', true],
  ['client', '🔑', '#eef0f2', false],
  ['login', '👤', '#eef0f2', false],
  ['docs', '📄', '#e3ecfd', false],
  ['gmail', '✉', '#fde8e7', false],
  ['calendar', '📅', '#dff3e3', false],
];
const AIS = [['claude', 'Claude Code'], ['codex', 'Codex'], ['antigravity', 'Antigravity']];
// the page each step opens; step i's title and description are t('g<i+1>') and t('g<i+1>_desc')
const GOOGLE_STEPS = [
  'https://console.cloud.google.com/projectcreate',
  'https://console.cloud.google.com/flows/enableapi?apiid=drive.googleapis.com,docs.googleapis.com,gmail.googleapis.com,calendar-json.googleapis.com,people.googleapis.com',
  'https://console.cloud.google.com/auth/overview',
  'https://console.cloud.google.com/auth/clients/create',
];

function openSetup() {
  S.sheet = 'setup'; S.setupGuide = false; S.aiTest = null; S.aiLoginWait = 0; S.aiBusy = false;
  placeDoc();
  renderSetup();
  refreshSetup();
}

// the jobs that run in the background, and the state each item shows while its job runs
const SETUP_JOBS = { speech: 'loading', voice: 'loading', login: 'loading', ai: 'installing' };

// one check at a time; a click meanwhile asks for one more, and an answer from before the click is not shown.
// While something downloads (or the Google login waits, or the AI installs), only that is asked again every few
// seconds; while the AI's sign-in waits in the browser, everything is asked again every few seconds.
async function refreshSetup(progress = false) {
  if (S.sheet !== 'setup') return;
  if (S.setupAsking) { S.setupAgain = true; return; }
  S.setupAsking = true;
  const seq = S.setupSeq;
  const was = Object.fromEntries(Object.keys(SETUP_JOBS).map((k) => [k, ((S.setup || {})[k] || {}).state]));
  let got = null, err = '';
  try { got = await call('setupState', { progress }); } catch (e) { err = e.message; }
  S.setupAsking = false;
  const stale = seq !== S.setupSeq;
  if (!stale) {
    const running = got && progress ? Object.fromEntries(Object.entries(got).filter(([, v]) => v.state !== 'ended')) : got;
    if (got && progress && S.setup) {
      const before = S.setup.ai;                  // the AI item keeps its other fields while only its job is asked
      S.setup = { ...S.setup, ...running };
      if (running.ai) S.setup.ai = { ...before, ...running.ai };
    } else if (got) S.setup = got;
    S.setupErr = err;
  }
  if (S.sheet !== 'setup') return;
  const st = S.setup || {};
  if (S.aiLoginWait && st.ai) {
    // the wait is over when the sign-in window's command has ended, when an AI that was signed out is signed in,
    // or after ten minutes (the window was closed): then the step shows its button again and the test runs anew
    const ended = st.ai.login_at && st.ai.login_at >= S.aiLoginWait - 2000;
    const signedNow = !S.aiLoginWasDone && st.ai.state === 'done';
    if (ended || signedNow || Date.now() - S.aiLoginWait > 10 * 60 * 1000) { S.aiLoginWait = 0; S.aiTest = null; }
  }
  renderSetup();
  clearTimeout(S.setupTimer);
  // a job that was running and is not any more: everything is checked once again
  const ended = progress && got && Object.entries(SETUP_JOBS).some(([k, v]) => was[k] === v && got[k] && got[k].state === 'ended');
  if (S.setupAgain || stale || ended) { S.setupAgain = false; return refreshSetup(); }
  const waiting = Object.entries(SETUP_JOBS).some(([k, v]) => st[k] && st[k].state === v);
  if (waiting) S.setupTimer = setTimeout(() => refreshSetup(true), 2500);   // a download or the login is on its way
  else if (S.aiLoginWait) S.setupTimer = setTimeout(() => refreshSetup(), 4000);
}
window.addEventListener('focus', () => { if (S.sheet === 'setup') refreshSetup(); });   // back from the browser

function setupSide(key, label) {
  const st = (S.setup || {})[key] || {};
  if (key === 'ai') return aiSide(st);
  // item 3 also opens its model page (Whisper or Qwen3-ASR), except while a download runs
  if (key === 'speech' && st.state && st.state !== 'loading') {
    return plainSide(key, label, st) + `<button class="slink" data-k="speech" data-act="change">${esc(t('speech_change'))}</button>`;
  }
  return plainSide(key, label, st);
}

function plainSide(key, label, st) {
  const btn = (text, act, extra = '') => `<button class="btn primary sbtn" data-k="${key}" data-act="${act}"${extra}>${esc(text)}</button>`;
  switch (st.state) {
    case 'done': return `<span class="sok">${esc(t('s_done'))}</span>`;
    case 'denied': return `<span class="sbad">${esc(t('s_denied'))}</span><button class="slink" data-k="${key}" data-act="settings">${esc(t('open_settings'))}</button>`;
    case 'locked': return `<span class="slock">${esc(t(key === 'login' ? 'lock_client' : 'lock_login'))}</span>`;
    case 'loading':
      if (key === 'login') return `<span class="swait">${esc(t('browser_login'))}</span>`;
      return `<span class="swait">${esc(t('downloading', st.pct || 0))}</span><div class="sbar"><i style="width:${st.pct || 0}%"></i></div>`;
    case 'unknown': return btn(t('recheck'), 'recheck');
    case 'off': return btn(t('turn_on'), 'open');
    case 'scope': return btn(t('sign_in_again'), 'glogin');
    case 'offline': return `<span class="slock">${esc(t('offline'))}</span>`;
    case 'error': return btn(t('recheck'), 'recheck');
    case 'todo': return btn(label, 'do') + (st.failed ? `<span class="slock">${esc(t('dl_failed'))}</span>` : '');
    default: return `<span class="slock">${esc(t('checking'))}</span>`;
  }
}

function renderSetup() {
  const el = $('#sheet');
  if (!el || S.sheet !== 'setup') return;
  const st = S.setup;
  if (S.setupGuide === 'ai') return renderAiGuide(el);
  if (S.setupGuide === 'speech') return renderSpeechGuide(el);
  if (S.setupGuide) return renderGoogleGuide(el);
  const done = st ? SETUP.filter(([k]) => (st[k] || {}).state === 'done').length : 0;
  const desc = (k) => t(`setup_${k}_desc`);
  el.innerHTML = `<div class="veil"><div class="sheet setup" role="dialog" aria-label="${esc(t('setup_aria'))}">
    <div class="shead lang"><h3>${esc(t('setup_title'))}</h3>
      <div class="langseg" role="radiogroup" aria-label="${esc(t('language'))}">${[['en', 'lang_en'], ['zh-TW', 'lang_zh']].map(([l, key]) =>
        `<button role="radio" aria-checked="${LANG === l}" class="${LANG === l ? 'on' : ''}" data-lang="${l}">${esc(t(key))}</button>`).join('')}</div></div>
    ${S.setupErr ? `<div class="sinfo err">${esc(S.setupErr)}</div>` : ''}
    <div class="slist">${SETUP.map(([k, icon, bg, req], i) => `<div class="srow">
      <div class="sico" style="background:${bg}">${icon}</div>
      <div class="stxt"><div class="stt">${i + 1}. ${esc(t(`setup_${k}`))}${req ? `<span class="sreq">${esc(t('required'))}</span>` : ''}</div>
        ${k === 'ai' && st && st.ai ? aiDesc(st.ai)
          : k === 'speech' && st && st.speech && st.speech.model ? `<div class="sds">${esc(speechName(st.speech.model))}</div>`
          : desc(k) && st && st[k] && st[k].state !== 'done' ? `<div class="sds">${esc(desc(k))}</div>` : ''}
        ${k === 'login' && st && st.login && st.login.email ? `<div class="sds">${esc(st.login.email)}</div>` : ''}</div>
      <div class="sside">${st ? setupSide(k, t(`setup_${k}_btn`)) : `<span class="slock">${esc(t('checking'))}</span>`}</div></div>`).join('')}</div>
    <div class="sfoot"><span class="scount">${esc(t('done_count', done, SETUP.length))}</span><button class="btn ghost" id="closeS">${esc(t('close'))}</button></div>
  </div></div>`;
  $('#closeS').addEventListener('click', () => { clearTimeout(S.setupTimer); closeSheet(); });
  el.querySelectorAll('.sbtn, .slink').forEach((b) => b.addEventListener('click', () => setupAct(b.dataset.k, b.dataset.act)));
  el.querySelectorAll('.langseg button').forEach((b) => b.addEventListener('click', () => pickLang(b.dataset.lang)));
}

// English or 中文, at the top of the list: the app keeps the choice and then sends 'language' as well
async function pickLang(lang) {
  if (lang === LANG) return;
  try {
    await call('setLanguage', { lang });
    setLang(lang);
  } catch (e) { showAlert(e.message); }
}

async function setupAct(key, act) {
  const st = (S.setup || {})[key] || {};
  S.setupSeq++;
  try {
    if (key === 'mic' || key === 'notify') await call(key === 'mic' ? 'setupMic' : 'setupNotify');
    else if (act === 'aiguide') { S.setupGuide = 'ai'; return renderSetup(); }
    else if (act === 'change') { S.setupGuide = 'speech'; return renderSetup(); }
    else if (act === 'ailogin') { await call('setupAILogin', { ai: st.ai }); aiWaitLogin(st); }
    else if (act === 'open') await call('setupOpen', { url: st.url });
    else if (act === 'glogin' || key === 'login') await call('setupRun', { what: 'login' });
    else if (key === 'speech' || key === 'voice') await call('setupRun', { what: key });
    else if (key === 'client') { S.setupGuide = 'google'; return renderSetup(); }
  } catch (e) { showAlert(e.message); }
  refreshSetup();
}

async function chooseAi(key) {
  if (!S.setup || (S.setup.ai && S.setup.ai.ai === key)) return;
  const before = S.setup.ai;
  S.setupSeq++;
  S.aiTest = null; S.aiLoginWait = 0;
  S.setup.ai = { ...before, state: '', ai: key, tested: false };
  renderSetup();
  try {
    const r = await call('setupAI', { ai: key });
    S.setup.ai = r.ai;
    showAi(key);
  } catch (e) { S.setup.ai = before; showAlert(e.message); }
  renderSetup();
}

// --- item 5, step by step (the prototype Vin approved on 2026-10-19): choose the AI, Vinutes installs it, the
// user signs in, and one short answer shows the account can write the minutes. Each row is a name, a state and
// at most one button.

const AI_WHO = { claude: 'Claude', codex: 'ChatGPT', antigravity: 'Google' };   // the account each one signs in to
const aiFullName = (key) => (AIS.find(([k]) => k === key) || [key, key])[1];   // Claude Code, Codex…

// the checklist's row: what it says under its name, and its button
// --- item 3's model page: Whisper (every language, on every Mac) or Qwen3-ASR (Chinese meetings, 4 GB more) ---
// [key, name, t() key of the one-line note, t() key of the size]
const SPEECH_MODELS = [
  ['whisper', 'Whisper', 'speech_whisper_note', 'speech_whisper_size'],
  ['qwen3-asr', 'Qwen3-ASR', 'speech_qwen_note', 'speech_qwen_size'],
];
function speechModel(key) { return SPEECH_MODELS.find(([k]) => k === key) || SPEECH_MODELS[0]; }
function speechName(key) { return speechModel(key)[1]; }

// step 1 picks the model (kept at once), step 2 downloads it: the same download as item 3's button
function renderSpeechGuide(el) {
  const sp = (S.setup || {}).speech || {};
  const [model, name, , size] = speechModel(sp.model);
  const have = sp.have || {};
  const dlDone = sp.state === 'done';
  const num = (i, ok) => `<div class="sico snum${ok ? ' ok' : ''}">${ok ? '✓' : i}</div>`;
  let side;
  if (sp.state === 'loading') side = `<span class="swait">${esc(t('downloading', sp.pct || 0))}</span><div class="sbar"><i style="width:${sp.pct || 0}%"></i></div>`;
  else if (dlDone) side = `<span class="sok">${esc(t('s_downloaded'))}</span>`;
  else if (!sp.state) side = `<span class="slock">${esc(t('checking'))}</span>`;
  else if (model === 'qwen3-asr' && sp.package === false) side = `<span class="slock">${esc(t('speech_no_package'))}</span>`;  // installed before v0.4.17
  else side = (sp.failed ? `<span class="sbad">${esc(t('dl_failed'))}</span>` : '')
    + `<button class="btn primary sbtn" data-k="speech" data-act="do">${esc(t(sp.failed ? 'redownload' : 'setup_speech_btn'))}</button>`;
  const done = 1 + (dlDone ? 1 : 0);
  el.innerHTML = `<div class="veil"><div class="sheet setup" role="dialog" aria-label="${esc(t('speech_title'))}">
    <div class="shead"><h3>${esc(t('speech_title'))}</h3></div>
    <div class="slist">
      <div class="srow">${num(1, true)}<div class="stxt"><div class="stt">${esc(t('speech_pick'))}</div>
        <div class="aicards" role="radiogroup" aria-label="${esc(t('speech_pick'))}">${SPEECH_MODELS.map(([k, n, note, sz]) =>
          `<button class="aicard${k === model ? ' on' : ''}" role="radio" aria-checked="${k === model}" data-model="${k}"${sp.state === 'loading' ? ' disabled' : ''}>
            <b>${esc(n)}</b><span>${esc(t(note))}・${esc(t(sz))}</span>${have[k] ? `<em>${esc(t('s_downloaded'))}</em>` : ''}</button>`).join('')}</div></div></div>
      <div class="srow">${num(2, dlDone)}<div class="stxt"><div class="stt">${esc(t('speech_dl', name))}</div><div class="sds">${esc(t(size))}</div></div>
        <div class="sside">${side}</div></div>
    </div>
    <div class="sfoot"><span class="scount">${esc(t('done_count', done, 2))}</span><button class="btn ${done === 2 ? 'primary' : 'ghost'}" id="backS">${esc(t('back_list'))}</button></div>
  </div></div>`;
  $('#backS').addEventListener('click', () => { S.setupGuide = false; renderSetup(); });
  el.querySelectorAll('.aicard').forEach((b) => b.addEventListener('click', () => chooseSpeech(b.dataset.model)));
  el.querySelectorAll('.sbtn').forEach((b) => b.addEventListener('click', () => setupAct('speech', 'do')));
}

async function chooseSpeech(key) {
  const sp = (S.setup || {}).speech || {};
  if (sp.model === key || sp.state === 'loading') return;
  S.setupSeq++;
  try {
    const r = await call('setupSpeechModel', { model: key });
    if (S.setup && r && r.speech) S.setup.speech = r.speech;
  } catch (e) { showAlert(e.message); }
  renderSetup();
  refreshSetup();
}

function aiDesc(ai) {
  if (ai.state === 'done') return `<div class="sds">${esc(aiFullName(ai.ai))}</div>`;
  if (ai.state === 'login' && ai.was_signed) return `<div class="sds bad">${esc(t('ai_signed_out', aiFullName(ai.ai)))}</div>`;
  return `<div class="sds">${esc(t('setup_ai_desc'))}</div>`;
}

function aiSide(ai) {
  const btn = (text, act) => `<button class="btn primary sbtn" data-k="ai" data-act="${act}">${esc(text)}</button>`;
  if (ai.state === 'done') return `<span class="sok">${esc(t('s_done'))}</span>`;
  if (ai.state === 'unknown') return btn(t('recheck'), 'recheck');
  if (ai.state === 'login' && ai.was_signed) {
    return S.aiLoginWait ? `<span class="swait">${esc(t('browser_login'))}</span>` : btn(t('sign_in_again'), 'ailogin');
  }
  if (!ai.state) return `<span class="slock">${esc(t('checking'))}</span>`;
  return btn(t('setup_ai_btn'), 'aiguide');
}

// the four steps' states: 'done', 'todo', 'locked', 'loading', or what went wrong
function aiSteps(ai) {
  const test = S.aiTest && S.aiTest.ai === ai.ai ? S.aiTest.state : ai.tested ? 'done' : '';
  const installed = !!ai.state && ai.state !== 'install' && ai.state !== 'installing';
  const plan = test === 'plan' || (ai.state === 'plan' && !(S.aiTest && S.aiTest.ai === ai.ai));
  const signed = (ai.state === 'done' || ai.state === 'plan') && test !== 'login';
  return {
    test,
    install: ai.state === 'installing' ? 'loading' : installed ? 'done' : ai.failed ? 'failed' : ai.state ? 'todo' : 'locked',
    login: !installed ? 'locked' : S.aiLoginWait ? 'loading' : plan ? 'plan' : signed ? 'done' : 'todo',
    check: S.aiLoginWait || !signed || plan ? 'locked' : test === 'running' ? 'loading' : test || 'todo',
  };
}

// the sign-in window is open: the steps wait for it (see refreshSetup for when the wait ends)
function aiWaitLogin(ai) {
  S.aiLoginWait = Date.now();
  S.aiLoginWasDone = ai.state === 'done' || ai.state === 'plan';
  S.aiTest = null;
}

// from the prompt box's menu: the steps of an AI that is not installed or not signed in yet
async function setupAi(key) {
  try {
    await call('setupAI', { ai: key });
    showAi(key);
  } catch (e) { return showAlert(e.message); }
  openSetup();
  S.setupGuide = 'ai';
  renderSetup();
}

function renderAiGuide(el) {
  const ai = (S.setup || {}).ai || { ai: 'claude' };
  const key = ai.ai;
  const steps = aiSteps(ai);
  const btn = (text, act) => `<button class="btn primary" data-aiact="${act}">${esc(text)}</button>`;
  const ok = (text) => `<span class="sok">${esc(text)}</span>`;
  const bad = (text) => `<span class="sbad">${esc(text)}</span>`;
  const wait = (text, bar) => `<span class="swait">${esc(text)}</span>${bar ? '<div class="sbar sbusy"><i></i></div>' : ''}`;
  const lock = (text) => `<span class="slock">${esc(text)}</span>`;
  const side = {
    install: { todo: btn(t('ai_install'), 'install'), loading: wait(t('ai_installing'), true), done: ok(t('ai_installed')),
               failed: bad(t('ai_install_failed')) + btn(t('ai_reinstall'), 'install'), locked: lock(t('checking')) },
    login: { locked: lock(t('lock_install')), todo: btn(t('sign_in'), 'login'), loading: wait(t('browser_login')),
             done: ok(t('ai_signed_in')), plan: bad(t(`ai_plan_${key}`)) + btn(t('sign_in_again'), 'login') },
    check: { locked: lock(t('lock_sign_in')), todo: lock(t('ai_testing')), loading: wait(t('ai_testing'), true),
             done: ok(t('ai_test_ok')), quota: bad(t('ai_quota')) + btn(t('ai_retest'), 'test'),
             error: bad(t('ai_test_failed')) + btn(t('ai_retest'), 'test'), login: lock(t('lock_sign_in')) },
  };
  const num = (i, done) => `<div class="sico snum${done ? ' ok' : ''}">${done ? '✓' : i}</div>`;
  const row = (i, title, step, extra = '') => `<div class="srow">${num(i, steps[step] === 'done')}
    <div class="stxt"><div class="stt">${esc(title)}</div>${extra}</div>
    <div class="sside">${side[step][steps[step]] || ''}</div></div>`;
  const done = 1 + ['install', 'login', 'check'].filter((k) => steps[k] === 'done').length;
  const installed = ai.installed || [];
  el.innerHTML = `<div class="veil"><div class="sheet setup" role="dialog" aria-label="${esc(t('setup_ai'))}">
    <div class="shead"><h3>${esc(t('setup_ai'))}</h3></div>
    <div class="slist">
      <div class="srow">${num(1, true)}<div class="stxt"><div class="stt">${esc(t('ai_choose'))}</div>
        <div class="aicards">${AIS.map(([k, n]) => `<button class="aicard${k === key ? ' on' : ''}" data-ai="${k}">
          <b>${esc(n)}</b><span>${esc(t(`ai_acct_${k}`))}</span>${installed.includes(k) ? `<em>${esc(t('ai_installed'))}</em>` : ''}</button>`).join('')}</div></div></div>
      ${row(2, t('ai_install_step', aiFullName(key)), 'install')}
      ${row(3, t('ai_login_step', AI_WHO[key] || aiFullName(key)), 'login', steps.login === 'done' && ai.email ? `<div class="sds">${esc(ai.email)}</div>` : '')}
      ${row(4, t('ai_test_step'), 'check')}
    </div>
    <div class="sfoot"><span class="scount">${esc(t('done_count', done, 4))}</span>
      <button class="btn ${done === 4 ? 'primary' : 'ghost'}" id="backS">${esc(t('back_list'))}</button></div>
  </div></div>`;
  $('#backS').addEventListener('click', () => { S.setupGuide = false; renderSetup(); });
  el.querySelectorAll('.aicard').forEach((b) => b.addEventListener('click', () => chooseAi(b.dataset.ai)));
  el.querySelectorAll('[data-aiact]').forEach((b) => b.addEventListener('click', () => aiAct(b.dataset.aiact)));
  // signed in and not tested yet: the test starts by itself
  if (steps.check === 'todo' && !(S.aiTest && S.aiTest.ai === key)) aiTest();
}

async function aiAct(act) {
  const ai = (S.setup || {}).ai || {};
  if (S.aiBusy) return;                             // one click at a time: a second install would race the first
  if (act === 'test') return aiTest();
  S.aiBusy = true;
  S.setupSeq++;
  try {
    if (act === 'install') {
      const r = await call('setupAIInstall', { ai: ai.ai });
      if (r && r.ai) S.setup.ai = r.ai;
      S.aiTest = null;
    } else if (act === 'login') {
      await call('setupAILogin', { ai: ai.ai });
      aiWaitLogin(ai);
    }
  } catch (e) { showAlert(e.message); }
  S.aiBusy = false;
  refreshSetup();
}

// step 4: the AI answers one word, the way it will write the minutes
async function aiTest() {
  const key = ((S.setup || {}).ai || {}).ai;
  S.aiTest = { ai: key, state: 'running' };
  renderSetup();
  let r = null;
  try { r = await call('setupAITest'); } catch (e) { r = null; }
  const now = ((S.setup || {}).ai || {}).ai;
  if (now !== key) {                               // another AI was picked meanwhile: this answer is not its
    if (S.aiTest && S.aiTest.ai === key) S.aiTest = null;
    return refreshSetup();
  }
  S.aiTest = { ai: key, state: (r && r.test) || 'error' };
  refreshSetup();
}

// item 6, step by step: each step opens its Google Cloud page; the last one takes the downloaded file
function renderGoogleGuide(el) {
  el.innerHTML = `<div class="veil"><div class="sheet setup" role="dialog" aria-label="${esc(t('setup_client'))}">
    <div class="shead"><h3>${esc(t('setup_client'))}</h3><div class="ssub">${esc(t('g_sub'))}</div></div>
    <div class="slist">${GOOGLE_STEPS.map((url, i) => `<div class="srow">
      <div class="sico snum">${i + 1}</div>
      <div class="stxt"><div class="stt">${esc(t(`g${i + 1}`))}</div><div class="sds">${esc(t(`g${i + 1}_desc`))}</div></div>
      <div class="sside"><button class="btn ghost sopen" data-i="${i}">${esc(t('open_page'))}</button></div></div>`).join('')}
      <div class="srow"><div class="sico snum">5</div>
        <div class="stxt"><div class="stt">${esc(t('g5'))}</div><div class="sds">${esc(t('g5_desc'))}</div></div>
        <div class="sside"><button class="btn primary" id="pickClient">${esc(t('pick_file'))}</button></div></div></div>
    <div class="sfoot"><span></span><button class="btn ghost" id="backS">${esc(t('back_list'))}</button></div>
  </div></div>`;
  el.querySelectorAll('.sopen').forEach((b) => b.addEventListener('click', () => {
    call('setupOpen', { url: GOOGLE_STEPS[Number(b.dataset.i)] }).catch((e) => showAlert(e.message));
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

applyLang();
(async () => {
  await loadList();
  renderMain();
  loadAiStates();
  loadVersion();
  setInterval(loadVersion, 3600 * 1000);
  try {
    const r = await call('ready');
    if (r.setup) openSetup();
    if (r.usage) return openUsage();              // 用量統計 from the menu bar panel
    if (r.select) return select(r.select);
  } catch (e) { /* no meeting asked for */ }
  if (!S.sel && S.jobs.length) select(S.jobs[0].id);
})();
