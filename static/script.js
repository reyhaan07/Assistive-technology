/* GestureTalk front-end: live status, training, eye/blink board, GPS places, medical card. */
const $ = (id) => document.getElementById(id);
const contextButtons = [...document.querySelectorAll('.btn-context')];
const CONTEXTS = contextButtons.map((b) => b.dataset.context);

const els = {
  context: $('contextValue'), place: $('placeValue'), gesture: $('gestureValue'), phrase: $('phraseValue'),
  message: $('messageBox'), history: $('historyList'), learnInfo: $('learnInfo'),
  cameraBadge: $('cameraBadge'), ttsBadge: $('ttsBadge'), gpsBadge: $('gpsBadge'),
  mute: $('muteToggle'), browserVoice: $('browserVoiceToggle'), autoLearn: $('autoLearnToggle'),
  gestureHead: $('gestureHead'), gestureBody: $('gestureBody'), gestureCount: $('gestureCount'),
  dialog: $('trainDialog'), form: $('trainForm'), dialogTitle: $('dialogTitle'),
  name: $('gestureName'), dialogMessage: $('dialogMessage'), captureHint: $('captureHint'),
  captureBtn: $('captureBtn'), saveBtn: $('saveBtn'), cancelBtn: $('cancelBtn'),
  countdown: $('countdown'),
};

const state = {
  context: CONTEXTS[0], lastSpeechId: null, dialogMode: 'train', captured: false,
  gestures: [], location: null, lastHistoryId: 0,
};

// ---------------------------------------------------------------- helpers
function show(el, text = '', kind = '') {
  el.textContent = text;
  el.className = `message ${kind}`;
}

async function api(url, options = {}) {
  const opts = { ...options };
  if (opts.body && typeof opts.body !== 'string') {
    opts.body = JSON.stringify(opts.body);
    opts.headers = { 'Content-Type': 'application/json' };
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

const pretty = (name) => name.replace(/_/g, ' ');
const TOKEN_LABELS = { usual: 'my usual', medical: 'medical card', place: 'place name', name: 'my name' };
const friendly = (text) => text.replace(/\{(usual|medical|place|name)(?:\|([^}]*))?\}/g,
  (_, t, fb) => `[${TOKEN_LABELS[t]}${fb ? ` – else “${fb}”` : ''}]`);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, v) { try { localStorage.setItem(key, v); } catch { /* ignore */ } },
};
const mapUrl = (loc) => `https://www.google.com/maps?q=${loc.lat},${loc.lon}`;

function setBadge(el, ok, okText, badText) {
  el.textContent = ok ? okText : badText;
  el.classList.toggle('ok', ok);
  el.classList.toggle('bad', !ok);
}

// ---------------------------------------------------------------- browser voice
const voiceSelect = $('voiceSelect');
const rateInput = $('rateInput');
let voices = [];

function loadVoices() {
  if (!('speechSynthesis' in window)) { $('voiceRow').hidden = true; return; }
  voices = window.speechSynthesis.getVoices();
  const saved = storage.get('voice');
  voiceSelect.replaceChildren(new Option('System default', ''),
    ...voices.map((v) => new Option(`${v.name} (${v.lang})`, v.name, false, v.name === saved)));
}

function speakInBrowser(text, force = false) {
  if ((!force && !els.browserVoice.checked) || !('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  const voice = voices.find((v) => v.name === voiceSelect.value);
  if (voice) { u.voice = voice; u.lang = voice.lang; }
  u.rate = Number(rateInput.value) || 1;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

async function say(text, source = 'typed') {
  try {
    return await api('/speak', { method: 'POST', body: { text, source } });
  } catch (err) {
    show(els.message, err.message, 'error');
    return null;
  }
}

// ---------------------------------------------------------------- listener display
const listener = {
  view: $('listenerView'), phrase: $('listenerPhrase'), context: $('listenerContext'), map: $('listenerMap'),
};
let lastListenerPhrase = '';

function updateListener(phrase, context, location = null) {
  listener.context.textContent = context;
  listener.map.hidden = !location;
  if (location) listener.map.href = mapUrl(location);
  if (phrase === lastListenerPhrase) return;
  lastListenerPhrase = phrase;
  listener.phrase.textContent = phrase;
  listener.phrase.classList.remove('pulse');
  void listener.phrase.offsetWidth;
  listener.phrase.classList.add('pulse');
}

function openListener() {
  listener.view.hidden = false;
  if (listener.view.requestFullscreen) listener.view.requestFullscreen().catch(() => {});
}

function closeListener() {
  listener.view.hidden = true;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

// ---------------------------------------------------------------- SOS
function alarm() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    for (let i = 0; i < 8; i += 1) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'square';
      osc.frequency.value = i % 2 ? 660 : 880;
      gain.gain.value = 0.15;
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + i * 0.25);
      osc.stop(ctx.currentTime + i * 0.25 + 0.22);
    }
  } catch { /* audio not available */ }
}

async function sos() {
  document.body.classList.remove('sos-flash');
  void document.body.offsetWidth;
  document.body.classList.add('sos-flash');
  alarm();
  const entry = await say('Emergency! I need help. Please call someone.', 'sos');
  if (!entry) return;
  speakInBrowser(entry.phrase, true);
  let text = entry.phrase;
  if (entry.contact) text += ` Contact: ${entry.contact}`;
  updateListener(text, 'Emergency', entry.location);
  show(els.message, entry.location ? `SOS sent. Location: ${mapUrl(entry.location)}` : 'SOS spoken (turn on GPS to include your location).', 'error');
}

// ---------------------------------------------------------------- live state
function setActiveContext(ctx) {
  contextButtons.forEach((btn) => {
    const active = btn.dataset.context === ctx;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
}

function renderHistory(history) {
  if (!history.length) {
    els.history.innerHTML = '<li class="muted">Nothing spoken yet.</li>';
    return;
  }
  if (history[0].id === state.lastHistoryId) return;
  state.lastHistoryId = history[0].id;
  els.history.replaceChildren(...history.map((h) => {
    const li = document.createElement('li');
    if (h.source === 'sos') li.classList.add('sos');
    const meta = document.createElement('span');
    meta.className = 'muted small';
    meta.textContent = `${h.time} · ${pretty(h.gesture)} · ${h.context}`;
    const text = document.createElement('div');
    text.textContent = h.phrase;
    li.append(text, meta);
    return li;
  }));
}

function renderEye(eye) {
  if (state.eyeModeSynced) storage.set('eyeMode', eye.mode); // server is the source of truth
  const radio = document.querySelector(`input[name="eyeMode"][value="${eye.mode}"]`);
  if (radio && !radio.checked) radio.checked = true;
  const on = eye.mode !== 'off';
  if (eye.error) setBadge($('faceBadge'), false, '', 'Eye tracking unavailable');
  else setBadge($('faceBadge'), on && eye.face, 'Face found', on ? 'No face' : 'Face: off');
  setBadge($('eyeBadge'), on && eye.face && !eye.closed, 'Eyes open', on && eye.closed ? 'Eyes closed' : 'Eyes: -');
  const last = eye.last_blink || {};
  $('blinkBadge').textContent = last.kind ? `Last blink: ${last.kind.replace('_', ' ')}` : 'Last blink: -';
  board.onEye(eye);
}

async function refreshState() {
  try {
    const data = await api('/get_state');
    state.context = data.context;
    els.context.textContent = data.context;
    els.place.textContent = data.place ? `📍 ${data.place.name}` : '';
    els.gesture.textContent = pretty(data.gesture);
    els.phrase.textContent = data.phrase;
    setActiveContext(data.context);
    renderHistory(data.history);
    renderEye(data.eye);
    renderGps(data.gps);
    window.gestureTalk = { eyeMode: data.eye.mode, eyeClosed: !!data.eye.closed, gesture: data.gesture };
    setBadge(els.cameraBadge, data.camera_ok, 'Camera on',
      data.camera_mode === 'browser' ? 'Camera starting…' : 'No camera');
    setBadge(els.ttsBadge, data.tts_available && !data.muted, 'Speaker on',
      data.tts_available ? 'Speaker muted' : 'No speaker');
    els.mute.checked = data.muted;
    els.autoLearn.checked = data.auto_learn;
    $('autoContextToggle').checked = data.auto_context;
    els.learnInfo.textContent = data.learned_samples
      ? `Learned ${data.learned_samples} new hand samples this session – it gets more accurate as you use it.` : '';

    if (storage.get('browserVoice') === null && !data.tts_available) els.browserVoice.checked = true;

    const latest = data.history[0];
    const isNew = state.lastSpeechId !== null && data.speech_id > state.lastSpeechId && latest;
    if (isNew && latest.source !== 'sos') speakInBrowser(latest.phrase);
    if (isNew && latest.source !== 'sos') board.spoken(latest.phrase);
    if (data.gesture !== 'none') updateListener(data.phrase, data.context);
    else if (isNew && latest.source !== 'sos') updateListener(latest.phrase, data.context);
    state.lastSpeechId = data.speech_id;
  } catch (err) {
    setBadge(els.cameraBadge, false, '', 'Server offline');
  }
}

async function setContext(ctx) {
  try {
    await api('/set_context', { method: 'POST', body: { context: ctx } });
    await refreshState();
  } catch (err) {
    show(els.message, err.message, 'error');
  }
}

// ---------------------------------------------------------------- gestures table
async function loadGestures() {
  try {
    const data = await api('/gestures');
    state.gestures = data.gestures;
    $('gestureNames').replaceChildren(...data.gestures.filter((g) => !g.eye).map((g) => new Option(pretty(g.name), g.name)));
    data.gestures.filter((g) => g.eye).forEach((g) => {
      const cell = $(`legend_${g.name}`);
      if (cell) cell.textContent = g.messages[state.context] || pretty(g.name);
    });

    els.gestureHead.innerHTML = '';
    const head = document.createElement('tr');
    ['Gesture', ...data.contexts.map(cap), ''].forEach((t) => {
      const th = document.createElement('th');
      th.textContent = t;
      head.append(th);
    });
    els.gestureHead.append(head);

    const trained = data.gestures.filter((g) => g.samples > 0).length;
    els.gestureCount.textContent = `${data.gestures.length} gestures · ${trained} with samples`;

    els.gestureBody.replaceChildren(...data.gestures.map((g) => {
      const tr = document.createElement('tr');
      const nameTd = document.createElement('td');
      nameTd.innerHTML = '<strong></strong><br><span class="muted small"></span>';
      nameTd.querySelector('strong').textContent = (g.eye ? '👁 ' : '') + pretty(g.name);
      const tags = [];
      if (g.eye) tags.push('eye blink');
      else if (g.builtin) tags.push('built-in');
      if (g.samples) tags.push(`${g.samples} samples`);
      nameTd.querySelector('span').textContent = tags.join(' · ');
      tr.append(nameTd);

      data.contexts.forEach((c) => {
        const td = document.createElement('td');
        td.textContent = g.messages[c] ? friendly(g.messages[c]) : '—';
        tr.append(td);
      });

      const actions = document.createElement('td');
      actions.className = 'actions';
      const edit = document.createElement('button');
      edit.className = 'btn-ghost small';
      edit.textContent = 'Edit';
      edit.addEventListener('click', () => openDialog('edit', g));
      actions.append(edit);
      if (g.samples) {
        const del = document.createElement('button');
        del.className = 'btn-danger small';
        del.textContent = g.builtin ? 'Reset' : 'Delete';
        del.addEventListener('click', () => deleteGesture(g.name));
        actions.append(del);
      }
      tr.append(actions);
      return tr;
    }));
  } catch (err) {
    show(els.message, err.message, 'error');
  }
}

async function deleteGesture(name) {
  if (!confirm(`Delete training data for "${pretty(name)}"?`)) return;
  try {
    await api(`/gestures/${encodeURIComponent(name)}`, { method: 'DELETE' });
    show(els.message, `Deleted ${pretty(name)}`, 'ok');
    loadGestures();
  } catch (err) {
    show(els.message, err.message, 'error');
  }
}

// ---------------------------------------------------------------- train / edit dialog
const messageInputs = () => [...els.form.querySelectorAll('input[data-context]')];

function openDialog(mode, gesture = null) {
  state.dialogMode = mode;
  state.captured = false;
  els.form.reset();
  show(els.dialogMessage);
  els.name.readOnly = mode === 'edit';
  els.dialogTitle.textContent = mode === 'edit' ? `Edit “${pretty(gesture.name)}”` : 'Train a gesture';
  els.captureBtn.hidden = mode === 'edit';
  els.captureBtn.textContent = 'Capture';
  els.captureHint.hidden = mode === 'edit';
  els.saveBtn.disabled = mode !== 'edit';
  if (gesture) {
    els.name.value = gesture.name;
    messageInputs().forEach((i) => { i.value = gesture.messages[i.dataset.context] || ''; });
  }
  els.dialog.showModal();
  (mode === 'edit' ? messageInputs()[0] : els.name).focus();
}

async function countdown(seconds) {
  els.countdown.hidden = false;
  for (let s = seconds; s > 0; s -= 1) {
    els.countdown.textContent = s;
    show(els.dialogMessage, `Get ready… ${s}`);
    await new Promise((r) => setTimeout(r, 1000));
  }
  els.countdown.textContent = 'Hold';
}

async function captureGesture() {
  els.captureBtn.disabled = true;
  els.saveBtn.disabled = true;
  try {
    await countdown(3);
    show(els.dialogMessage, 'Capturing… hold still');
    const data = await api('/capture_landmarks', { method: 'POST' });
    state.captured = true;
    els.saveBtn.disabled = false;
    show(els.dialogMessage, `Captured ${data.samples} samples. Fill in the phrases and save.`, 'ok');
  } catch (err) {
    show(els.dialogMessage, err.message, 'error');
  } finally {
    els.countdown.hidden = true;
    els.captureBtn.disabled = false;
    els.captureBtn.textContent = 'Recapture';
  }
}

async function saveDialog(event) {
  event.preventDefault();
  const name = els.name.value.trim();
  if (!name) { show(els.dialogMessage, 'Gesture name is required', 'error'); return; }
  const messages = Object.fromEntries(messageInputs().map((i) => [i.dataset.context, i.value.trim()]));
  try {
    if (state.dialogMode === 'edit') {
      await api(`/phrases/${encodeURIComponent(name)}`, { method: 'PUT', body: { messages } });
      show(els.message, `Updated phrases for ${pretty(name)}`, 'ok');
    } else {
      if (!state.captured) { show(els.dialogMessage, 'Capture the gesture first', 'error'); return; }
      const data = await api('/train', { method: 'POST', body: { gesture_name: name, messages } });
      show(els.message, `Trained “${pretty(data.gesture_name)}” (+${data.samples_added} samples)`, 'ok');
    }
    els.dialog.close();
    loadGestures();
  } catch (err) {
    show(els.dialogMessage, err.message, 'error');
  }
}

// ---------------------------------------------------------------- correction ("Wrong?")
$('wrongBtn').addEventListener('click', () => {
  $('wrongForm').reset();
  show($('wrongMessage'));
  $('wrongDialog').showModal();
});
$('wrongCancel').addEventListener('click', () => $('wrongDialog').close());
$('wrongForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const data = await api('/correct', { method: 'POST', body: { gesture_name: $('wrongName').value } });
    $('wrongDialog').close();
    show(els.message, data.message, 'ok');
    loadGestures();
  } catch (err) {
    show($('wrongMessage'), err.message, 'error');
  }
});

// ---------------------------------------------------------------- word suggestions (typing)
let suggestTimer = null;
$('speakInput').addEventListener('input', (e) => {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(async () => {
    const words = e.target.value.split(/\s+/);
    const last = words.pop();
    if (!last) return;
    try {
      const data = await api(`/suggest?prefix=${encodeURIComponent(last)}`);
      const base = words.length ? `${words.join(' ')} ` : '';
      $('wordSuggestions').replaceChildren(...data.words.map((w) => new Option(base + w)));
    } catch { /* ignore */ }
  }, 150);
});

// ---------------------------------------------------------------- eye mode
async function setEyeMode(mode) {
  storage.set('eyeMode', mode);
  try {
    const data = await api('/set_eye_mode', { method: 'POST', body: { mode } });
    if (data.error) show(els.message, `Eye tracking unavailable: ${data.error}`, 'error');
    refreshState();
  } catch (err) {
    show(els.message, err.message, 'error');
  }
}
document.querySelectorAll('input[name="eyeMode"]').forEach((r) => r.addEventListener('change', () => setEyeMode(r.value)));

// ---------------------------------------------------------------- blink board (scanning keyboard)
const board = (() => {
  const view = $('board');
  const grid = $('boardGrid');
  const textEl = $('boardText');
  const hint = $('boardHint');
  const spokenEl = $('boardSpoken');
  const speed = $('scanSpeed');
  let text = '';
  let groups = [];
  let level = 0;          // 0 = choosing a group, 1 = choosing an item in a group
  let groupIdx = 0;
  let itemIdx = 0;
  let timer = null;
  let lastBlinkId = null;
  let learned = { words: [], phrases: [] };

  const LETTER_GROUPS = ['ABCDEF', 'GHIJKL', 'MNOPQR', 'STUVWX', 'YZ'];
  const back = { label: '◀ Back', action: () => goTop() };

  function lastWord() { return text.split(' ').pop(); }

  async function fetchLearned() {
    try {
      learned = await api(`/suggest?prefix=${encodeURIComponent(lastWord())}&context=${state.context}`);
    } catch { learned = { words: [], phrases: [] }; }
  }

  function contextPhrases() {
    const seen = new Set();
    const out = [];
    learned.phrases.forEach((p) => { if (!seen.has(p)) { seen.add(p); out.push(p); } });
    state.gestures.forEach((g) => {
      const p = g.messages[state.context];
      if (p && !p.includes('{') && !seen.has(p)) { seen.add(p); out.push(p); }
    });
    return out.slice(0, 11);
  }

  function speakItem(phrase) {
    return { label: phrase, action: () => say(phrase, 'board') };
  }

  function build() {
    const g = [];
    if (text) {
      const words = learned.words.slice(0, 4).map((w) => ({
        label: w,
        action: () => { text = text.slice(0, text.length - lastWord().length) + w + ' '; },
      }));
      if (words.length) g.push({ label: '💡 Words', items: words });
      g.push({
        label: '✏️ Message',
        items: [
          { label: '🔊 Speak message', action: () => { say(text.trim(), 'board'); text = ''; } },
          { label: '␣ Space', action: () => { text += ' '; } },
          { label: '⌫ Delete letter', action: () => { text = text.slice(0, -1); } },
          { label: '✖ Clear', action: () => { text = ''; } },
        ],
      });
    }
    g.push({
      label: '⭐ Quick',
      items: [
        speakItem('Yes'), speakItem('No'),
        { label: '🚨 Emergency', action: () => sos() },
        { label: '☕ My usual', action: () => say('{usual|I would like my usual please}', 'board') },
        { label: '🏥 Medical info', action: () => say('{medical|I do not have a medical card saved}', 'board') },
        speakItem('Thank you'), speakItem('Please wait'), speakItem('I am in pain'),
        speakItem('I am thirsty'), speakItem('I need the bathroom'), speakItem('I am tired'),
      ],
    });
    const phrases = contextPhrases();
    if (phrases.length) g.push({ label: `💬 ${cap(state.context)} phrases`, items: phrases.map(speakItem) });
    LETTER_GROUPS.forEach((letters) => g.push({
      label: letters.split('').join(' '),
      letters: true,
      items: letters.split('').map((ch) => ({ label: ch, action: () => { text += ch.toLowerCase(); } })),
    }));
    g.push({
      label: '📍 Place',
      items: CONTEXTS.map((c) => ({ label: cap(c), action: () => setContext(c) })),
    });
    g.push({
      label: '⚙️ Board',
      items: [
        { label: 'Slower', action: () => setSpeed(Number(speed.value) + 0.2) },
        { label: 'Faster', action: () => setSpeed(Number(speed.value) - 0.2) },
        { label: '✕ Close board', action: () => close(true) },
      ],
    });
    g.forEach((grp) => grp.items.push(back));
    groups = g;
  }

  function render() {
    textEl.innerHTML = '';
    if (text) {
      textEl.textContent = text;
      const caret = document.createElement('span');
      caret.className = 'caret';
      textEl.append(caret);
    } else {
      textEl.innerHTML = '<span class="muted">Spell a message…</span>';
    }

    const list = level === 0 ? groups : groups[groupIdx].items;
    const active = level === 0 ? groupIdx : itemIdx;
    hint.textContent = level === 0
      ? 'Long blink to choose the highlighted group'
      : `${groups[groupIdx].label} – long blink to choose`;
    grid.classList.toggle('items', level === 1);
    grid.replaceChildren(...list.map((it, i) => {
      const tile = document.createElement('button');
      tile.className = 'tile';
      if (i === active) tile.classList.add('lit');
      if (level === 1 && groups[groupIdx].letters && it !== back) tile.classList.add('letter');
      tile.textContent = it.label;
      tile.addEventListener('click', () => {
        if (level === 0) groupIdx = i; else itemIdx = i;
        select();
      });
      return tile;
    }));
  }

  function advance() {
    if (level === 0) groupIdx = (groupIdx + 1) % groups.length;
    else itemIdx = (itemIdx + 1) % groups[groupIdx].items.length;
    render();
  }

  function restartTimer() {
    clearInterval(timer);
    timer = setInterval(advance, Number(speed.value) * 1000);
  }

  function setSpeed(v) {
    speed.value = Math.min(3, Math.max(0.6, v)).toFixed(1);
    $('scanSpeedValue').textContent = `${speed.value}s`;
    storage.set('scanSpeed', speed.value);
    restartTimer();
  }

  async function goTop() {
    level = 0;
    groupIdx = 0;
    await fetchLearned();
    build();
    render();
    restartTimer();
  }

  async function select() {
    if (view.hidden) return;
    if (level === 0) {
      level = 1;
      itemIdx = 0;
      render();
      restartTimer();
      return;
    }
    const item = groups[groupIdx].items[itemIdx];
    if (item === back) { goTop(); return; }
    await item.action();
    if (!view.hidden) goTop();
  }

  async function open() {
    if (!view.hidden) return;
    view.hidden = false;
    await loadGestures();
    goTop();
  }

  function close(switchToPatterns = false) {
    view.hidden = true;
    clearInterval(timer);
    if (switchToPatterns) setEyeMode('patterns');
  }

  function onEye(eye) {
    if (eye.mode === 'board' && view.hidden) open();
    const b = $('boardEye');
    if (eye.mode === 'off') b.textContent = 'Eye tracking off';
    else b.textContent = !eye.face ? 'No face' : eye.closed ? 'Eyes closed' : 'Eyes open';
    b.classList.toggle('bad', eye.mode === 'off' || !eye.face);
    b.classList.toggle('ok', eye.mode !== 'off' && eye.face);

    const last = eye.last_blink || {};
    if (lastBlinkId === null) { lastBlinkId = last.id; return; }
    if (last.id !== lastBlinkId) {
      lastBlinkId = last.id;
      if (!view.hidden && (last.kind === 'long' || last.kind === 'very_long')) select();
    }
  }

  function spoken(phrase) {
    if (view.hidden) return;
    spokenEl.textContent = `🔊 ${phrase}`;
    spokenEl.classList.remove('pulse');
    void spokenEl.offsetWidth;
    spokenEl.classList.add('pulse');
  }

  speed.addEventListener('input', () => setSpeed(Number(speed.value)));
  $('closeBoard').addEventListener('click', () => close(true));
  setSpeed(Number(storage.get('scanSpeed') || speed.value));
  clearInterval(timer);

  return { open, close, select, onEye, spoken, isOpen: () => !view.hidden };
})();

$('boardBtn').addEventListener('click', () => setEyeMode('board'));

// ---------------------------------------------------------------- GPS places
const gps = { watchId: null, lastSentTime: 0 };


const MAX_ACCURACY_M = 100; // fixes worse than this are never used for place decisions

const GPS_STATUS_TEXT = {
  measuring: 'Collecting GPS readings…',
  weak: 'GPS signal too weak to decide places – move near a window or outside.',
  ambiguous: 'Two saved places are too close to tell apart right now – not switching.',
  uncertain: 'Near a saved place, waiting for a more precise position…',
  inside: 'GPS working – you are at a saved place.',
  outside: 'GPS working – not at a saved place.',
};

function renderGps(gpsState) {
  if (!gpsState || !gpsState.status || gps.watchId === null) return;
  const est = gpsState.estimate;
  let text = GPS_STATUS_TEXT[gpsState.status] || '';
  if (gpsState.status === 'confirming' && gpsState.confirming) {
    const c = gpsState.confirming;
    text = c.place ? `Confirming arrival at ${c.place}… ${c.seconds_left}s` : `Confirming you left… ${c.seconds_left}s`;
  }
  if (est) text += ` (±${Math.round(est.accuracy)} m from ${est.fixes} readings)`;
  $('gpsInfo').textContent = text;
}

async function sendLocation(pos) {
  const loc = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy };
  const weak = loc.accuracy > MAX_ACCURACY_M;
  state.location = loc;
  setBadge(els.gpsBadge, !weak, `GPS ±${Math.round(loc.accuracy)} m`, `GPS weak ±${Math.round(loc.accuracy)} m`);

  // Send every fix (max one per 2 s): the server averages them for accuracy.
  const now = Date.now();
  if (now - gps.lastSentTime < 2000) return;
  gps.lastSentTime = now;
  try {
    const data = await api('/location', { method: 'POST', body: loc });
    renderGps(data);
    if (data.arrived && data.place) {
      show(els.message, `📍 Arrived at ${data.place.name} – context set to ${data.place.context}`, 'ok');
      refreshState();
    } else if (data.left) {
      show(els.message, '📍 Left the saved place', 'ok');
      refreshState();
    }
  } catch (err) {
    show(els.message, err.message, 'error');
  }
}

function startGps() {
  if (!('geolocation' in navigator)) {
    setBadge(els.gpsBadge, false, '', 'No GPS');
    $('gpsInfo').textContent = 'This browser has no location support.';
    return;
  }
  if (!window.isSecureContext) {
    setBadge(els.gpsBadge, false, '', 'GPS needs https');
    $('gpsInfo').textContent = 'Browsers block GPS on plain http:// from another device. Start GestureTalk with '
      + '“python app.py --https” and open the https:// address it prints on your phone.';
    show(els.message, 'GPS blocked: this page is not https. Run “python app.py --https”.', 'error');
    $('gpsToggle').checked = false;
    return;
  }
  els.gpsBadge.textContent = 'GPS…';
  els.gpsBadge.classList.remove('ok', 'bad');
  gps.watchId = navigator.geolocation.watchPosition(sendLocation, (err) => {
    setBadge(els.gpsBadge, false, '', 'GPS blocked');
    show(els.message, `GPS: ${err.message}`, 'error');
  }, { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 });
}

function stopGps() {
  if (gps.watchId !== null) navigator.geolocation.clearWatch(gps.watchId);
  gps.watchId = null;
  els.gpsBadge.textContent = 'GPS off';
  els.gpsBadge.classList.remove('ok', 'bad');
}

$('gpsToggle').addEventListener('change', (e) => {
  storage.set('gps', e.target.checked ? '1' : '0');
  if (e.target.checked) startGps(); else stopGps();
});

$('autoContextToggle').addEventListener('change', (e) => {
  api('/set_auto_context', { method: 'POST', body: { enabled: e.target.checked } }).catch(() => {});
});

async function loadPlaces() {
  try {
    const data = await api('/places');
    const list = $('placeList');
    if (!data.places.length) {
      list.innerHTML = '<li class="muted small">No places saved yet.</li>';
      return;
    }
    list.replaceChildren(...data.places.map((p) => {
      const li = document.createElement('li');
      const info = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = p.name;
      const meta = document.createElement('div');
      meta.className = 'muted small';
      meta.textContent = `${cap(p.context)} · ${Math.round(p.radius)} m${p.visits ? ` · ${p.visits} visits` : ''}`;
      const usual = document.createElement('div');
      usual.className = 'small';
      usual.textContent = p.usual ? `My usual: ${p.usual}` : 'No usual order saved';
      info.append(title, meta, usual);

      const actions = document.createElement('div');
      actions.className = 'actions';
      const edit = document.createElement('button');
      edit.className = 'btn-ghost small';
      edit.textContent = 'Edit usual';
      edit.addEventListener('click', async () => {
        const v = prompt(`Your usual at ${p.name}:`, p.usual || '');
        if (v === null) return;
        await api(`/places/${p.id}`, { method: 'PUT', body: { usual: v } }).catch((err) => show(els.message, err.message, 'error'));
        loadPlaces();
      });
      const del = document.createElement('button');
      del.className = 'btn-danger small';
      del.textContent = 'Delete';
      del.addEventListener('click', async () => {
        if (!confirm(`Delete ${p.name}?`)) return;
        await api(`/places/${p.id}`, { method: 'DELETE' }).catch(() => {});
        loadPlaces();
      });
      actions.append(edit, del);
      li.append(info, actions);
      return li;
    }));
  } catch (err) {
    show(els.message, err.message, 'error');
  }
}

let savingPlace = false;
$('placeForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (savingPlace) return;
  if (gps.watchId === null) {
    show(els.message, 'Turn on “Use GPS” first.', 'error');
    return;
  }
  const btn = e.target.querySelector('button[type=submit]');
  savingPlace = true;
  btn.disabled = true;
  const body = { name: $('placeName').value, context: $('placeContext').value, usual: $('placeUsual').value, use_current: true };
  const radius = Number($('placeRadius').value);
  if (radius) body.radius = radius;
  const started = Date.now();
  try {
    // The server only saves once it has a precise, averaged position (can take up to ~1 min).
    while (true) {
      const res = await fetch('/places', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        e.target.reset();
        show(els.message, `Saved ${data.name} (accurate to within ${Math.round(data.radius)} m zone)`, 'ok');
        loadPlaces();
        break;
      }
      if (res.status !== 409) throw new Error(data.error || 'Could not save place');
      const waited = Math.round((Date.now() - started) / 1000);
      if (waited > 90) throw new Error(`${data.error} – gave up after 90 s. Try near a window or outside.`);
      $('placeCoords').textContent = `${data.error} ${waited}s`;
      show(els.message, `📍 Stay still – measuring your exact position… ${waited}s`);
      await new Promise((r) => setTimeout(r, 2000));
    }
  } catch (err) {
    show(els.message, err.message, 'error');
  } finally {
    savingPlace = false;
    btn.disabled = false;
    $('placeCoords').textContent = 'Stand still where you want the place to be';
  }
});

// ---------------------------------------------------------------- medical card
async function loadProfile() {
  try {
    const data = await api('/profile');
    const form = $('profileForm');
    Object.entries(data.profile).forEach(([k, v]) => { if (form.elements[k]) form.elements[k].value = v; });
    $('medicalPreview').textContent = data.medical_text ? `Will say: “${data.medical_text}”` : '';
  } catch { /* ignore */ }
}

$('profileForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target).entries());
  try {
    const data = await api('/profile', { method: 'PUT', body });
    $('medicalPreview').textContent = data.medical_text ? `Will say: “${data.medical_text}”` : '';
    show(els.message, 'Medical card saved', 'ok');
  } catch (err) {
    show(els.message, err.message, 'error');
  }
});

// ---------------------------------------------------------------- typed speech + quick buttons
$('speakForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('speakInput');
  const text = input.value.trim();
  if (!text) return;
  if (await say(text)) { input.value = ''; refreshState(); }
});
$('usualBtn').addEventListener('click', () => say('{usual|I would like my usual please}').then(refreshState));
$('medicalBtn').addEventListener('click', () => say('{medical|I do not have a medical card saved}').then(refreshState));

// ---------------------------------------------------------------- wiring
$('trainBtn').addEventListener('click', () => openDialog('train'));
els.captureBtn.addEventListener('click', captureGesture);
els.cancelBtn.addEventListener('click', () => els.dialog.close());
els.form.addEventListener('submit', saveDialog);
contextButtons.forEach((btn) => btn.addEventListener('click', () => setContext(btn.dataset.context)));
$('sosBtn').addEventListener('click', sos);
$('displayBtn').addEventListener('click', openListener);
$('closeListener').addEventListener('click', closeListener);
document.addEventListener('fullscreenchange', () => {
  if (!document.fullscreenElement && !listener.view.hidden) listener.view.hidden = true;
});

els.mute.addEventListener('change', async () => {
  try { await api('/set_mute', { method: 'POST', body: { muted: els.mute.checked } }); refreshState(); }
  catch (err) { show(els.message, err.message, 'error'); }
});
els.autoLearn.addEventListener('change', () => {
  api('/set_auto_learn', { method: 'POST', body: { enabled: els.autoLearn.checked } }).catch(() => {});
});

const savedVoice = storage.get('browserVoice');
if (savedVoice !== null) els.browserVoice.checked = savedVoice === '1';
els.browserVoice.addEventListener('change', () => storage.set('browserVoice', els.browserVoice.checked ? '1' : '0'));
voiceSelect.addEventListener('change', () => storage.set('voice', voiceSelect.value));
rateInput.addEventListener('change', () => storage.set('rate', rateInput.value));
rateInput.value = storage.get('rate') || '1';
loadVoices();
if ('speechSynthesis' in window) window.speechSynthesis.addEventListener('voiceschanged', loadVoices);

// Keyboard: 1-9 contexts, L listener, B board, Space selects on the board, Esc closes overlays
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (!listener.view.hidden) { closeListener(); return; }
    if (board.isOpen()) { board.close(true); return; }
  }
  if (board.isOpen() && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); board.select(); return; }
  if (e.target.matches('input, textarea, select') || document.querySelector('dialog[open]')) return;
  const key = e.key.toLowerCase();
  if (key === 'l') { openListener(); return; }
  if (key === 'b') { setEyeMode('board'); return; }
  const n = Number(e.key);
  if (n >= 1 && n <= CONTEXTS.length) setContext(CONTEXTS[n - 1]);
});

// ---------------------------------------------------------------- start
(async function start() {
  // Restore the caregiver's eye-mode choice after a server restart, so a user who
  // can only blink never needs someone to touch the mouse.
  const savedMode = storage.get('eyeMode');
  const data = await api('/get_state').catch(() => null);
  if (data && data.eye.mode === 'off' && savedMode && savedMode !== 'off') await setEyeMode(savedMode);
  state.eyeModeSynced = true;
  await refreshState();
  if (storage.get('gps') === '1') { $('gpsToggle').checked = true; startGps(); }
  loadGestures();
  loadPlaces();
  loadProfile();
  setInterval(refreshState, 250);
}());
