// Run by the app inside the Google Doc shown in the meeting window (callAsyncJavaScript): every [__] blinks three
// times. Google draws the pages on canvases, so a blank is no element to find; it is painted red on a pale red
// ground (doc_sync.blank_requests), and a filter laid over the pages turns that ground bright red and its
// letters white, then comes off again. Answers 'blinked', or 'no pages' when the Doc has not drawn any yet.
const NS = 'http://www.w3.org/2000/svg';
// built node by node: the Doc's page refuses HTML put in as text (Trusted Types)
const el = (tag, attrs, kids = []) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  kids.forEach((c) => e.appendChild(c));
  return e;
};
if (!document.getElementById('vin-blink')) {
  // alpha from the colour alone. The pale red ground (#FDE0DC) is reddish (R > B), light (B high) and not
  // yellowish (G about B): the pale yellow of a comment, white, grey, navy headings and blue links fail one of the
  // three. The red letters (#C5221F) are reddish and dark.
  const mask = (values, result) => el('feColorMatrix', { in: 'SourceGraphic', type: 'matrix', values, result });
  const alpha = (r, g, b, k) => `0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  ${r} ${g} ${b} 0 ${k}`;
  document.body.appendChild(el('svg', { id: 'vin-blink', width: '0', height: '0', style: 'position:absolute' }, [
    el('filter', { id: 'vinBlink', 'color-interpolation-filters': 'sRGB', x: '0', y: '0', width: '100%', height: '100%' }, [
      mask(alpha(20, 0, -20, -1.2), 'reddish'),
      mask(alpha(0, 0, 15, -11.7), 'light'),
      mask(alpha(0, -30, 30, 1.5), 'notYellow'),
      el('feComposite', { in: 'reddish', in2: 'light', operator: 'in', result: 'pale' }),
      el('feComposite', { in: 'pale', in2: 'notYellow', operator: 'in', result: 'ground' }),
      mask(alpha(6, -6, -6, -1), 'redLetters'),
      // only letters on a blank's ground turn white: red text elsewhere on the page stays as it is
      el('feMorphology', { in: 'ground', operator: 'dilate', radius: '4', result: 'near' }),
      el('feComposite', { in: 'redLetters', in2: 'near', operator: 'in', result: 'letters' }),
      el('feFlood', { 'flood-color': '#ff2d20', result: 'red' }),
      el('feComposite', { in: 'red', in2: 'ground', operator: 'in', result: 'redOver' }),
      el('feFlood', { 'flood-color': '#ffffff', result: 'white' }),
      el('feComposite', { in: 'white', in2: 'letters', operator: 'in', result: 'whiteOver' }),
      el('feMerge', {}, [el('feMergeNode', { in: 'SourceGraphic' }), el('feMergeNode', { in: 'redOver' }),
                         el('feMergeNode', { in: 'whiteOver' })]),
    ]),
  ]));
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const pages = () => [...document.querySelectorAll('.kix-canvas-tile-content')];
for (let i = 0; i < 60 && !pages().length; i++) await wait(250);     // a Doc just opened draws within seconds
if (!pages().length) return 'no pages';
await wait(400);                                                       // the pages around the place it moved to
const token = (window.vinBlinkToken || 0) + 1;                         // a newer blink takes over from this one
window.vinBlinkToken = token;
try {
  for (let n = 0; n < 3 && window.vinBlinkToken === token; n++) {
    pages().forEach((p) => { p.style.filter = 'url(#vinBlink)'; });
    await wait(350);
    pages().forEach((p) => { p.style.filter = ''; });
    await wait(300);
  }
} finally {
  if (window.vinBlinkToken === token) pages().forEach((p) => { p.style.filter = ''; });
}
return 'blinked';
