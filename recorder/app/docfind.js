// Run by the app inside the Google Doc shown in the meeting window (callAsyncJavaScript, `words` given): moves the
// Doc to the first place that holds `words` and selects it, the way 編輯 > 尋找並取代 does, without showing the
// menu or the dialog. Answers 'found', 'not found', or why it could not (Google changed its page).
const hide = document.createElement('style');
// the 編輯 menu and the find card (a box Google floats over the Doc, classes named after 尋找並取代)
hide.textContent = '.goog-menu, [class*="Findandreplace"], [class*="findandreplace"] { opacity: 0 !important; }';
document.head.appendChild(hide);
// the small 加上註解／加上表情符號 buttons Google floats beside a selection: not for the words the app selected; they
// come back with the user's next click in the Doc (a click left over from an earlier jump must not end this one)
let quiet = document.getElementById('vin-quiet-fab');
if (!quiet) {
  quiet = document.createElement('style');
  quiet.id = 'vin-quiet-fab';
  quiet.textContent = '.inlineFabBubbleContainer { display: none !important; }';
  document.head.appendChild(quiet);
}
if (window.vinQuietEnd) document.removeEventListener('mousedown', window.vinQuietEnd, true);
const fire = (el, types) => {
  const r = el.getBoundingClientRect();
  for (const t of types) {
    el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window, button: 0,
                                         clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 }));
  }
};
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const shown = (e) => {
  const s = getComputedStyle(e);
  const r = e.getBoundingClientRect();
  return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
};
const dialog = () => [...document.querySelectorAll('[role=dialog]')]
  .find((d) => d.getClientRects().length && getComputedStyle(d).visibility !== 'hidden'
               && d.querySelector('input[type=text], input:not([type])'));
try {
  let dlg = dialog();
  if (!dlg) {
    const menu = document.querySelector('#docs-edit-menu');
    if (!menu) return 'no menu';
    fire(menu, ['mousedown', 'mouseup']);
    await wait(250);
    const item = [...document.querySelectorAll('.goog-menuitem')]
      .find((e) => shown(e) && /尋找並取代|尋找和取代|Find and replace/i.test(e.textContent));
    if (!item) { fire(menu, ['mousedown', 'mouseup']); return 'no menu item'; }
    fire(item, ['mouseover', 'mousedown', 'mouseup', 'click']);
    for (let i = 0; i < 30 && !(dlg = dialog()); i++) await wait(100);
    if (!dlg) return 'no dialog';
  }
  const input = dlg.querySelector('input[type=text], input:not([type])');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(input, words);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(700);
  const none = [...dlg.querySelectorAll('*')].some((e) => !e.childElementCount && /^0\b|找不到|No results/i.test(e.textContent.trim()));
  set.call(input, '');                               // the next 尋找並取代 the user opens starts empty
  const close = [...dlg.querySelectorAll('[role=button], button')]
    .find((b) => /關閉|Close/i.test(b.getAttribute('aria-label') || ''));
  if (close) fire(close, ['mouseover', 'mousedown', 'mouseup', 'click']);
  await wait(300);
  return none ? 'not found' : 'found';
} finally {
  await wait(200);                                   // the card's closing animation, still out of sight
  hide.remove();
  window.vinQuietEnd = () => {
    document.removeEventListener('mousedown', window.vinQuietEnd, true);
    window.vinQuietEnd = null;
    quiet.remove();
  };
  document.addEventListener('mousedown', window.vinQuietEnd, true);
}
