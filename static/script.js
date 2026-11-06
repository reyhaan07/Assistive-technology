const $ = (id) => document.getElementById(id);
const contextButtons = [...document.querySelectorAll('.btn-context')];
const CONTEXTS = contextButtons.map((b) => b.dataset.context);

const els = {
  context: $('contextValue'), gesture: $('gestureValue'), phrase: $('phraseValue'),
  message: $('messageBox'), history: $('historyList'),
  cameraBadge: $('cameraBadge'), ttsBadge: $('ttsBadge'),
  mute: $('muteToggle'), browserVoice: $('browserVoiceToggle'),
  gestureHead: $('gestureHead'), gestureBody: $('gestureBody'), gestureCount: $('gestureCount'),
  dialog: $('trainDialog'), form: $('trainForm'), dialogTitle: $('dialogTitle'),
  name: $('gestureName'), dialogMessage: $('dialogMessage'), captureHint: $('captureHint'),
  captureBtn: $('captureBtn'), saveBtn: $('saveBtn'), cancelBtn: $('cancelBtn'),
  countdown: $('countdown'),
};

let lastSpeechId = null;
let dialogMode = 'train';
let captured = false;

// ---------- helpers ----------
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
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, v) { try { localStorage.setItem(key, v); } catch { /* ignore */ } },
};

// ---------- browser voice ----------
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

// ---------- listener display ----------
const listener = { view: $('listenerView'), phrase: $('listenerPhrase'), context: $('listenerContext') };
let lastListenerPhrase = '';

function updateListener(phrase, context) {
  listener.context.textContent = context;
  if (phrase === lastListenerPhrase) return;
  lastListenerPhrase = phrase;
  listener.phrase.textContent = phrase;
  listener.phrase.classList.remove('pulse');
  void listener.phrase.offsetWidth; // restart animation
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

// ---------- SOS ----------
function alarm() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    for (let i = 0; i < 6; i += 1) {
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
  const text = 'Emergency! I need help. Please call someone.';
  document.body.classList.remove('sos-flash');
  void document.body.offsetWidth;
  document.body.classList.add('sos-flash');
  alarm();
  speakInBrowser(text, true);
  try {
    await api('/speak', { method: 'POST', body: { text, source: 'sos' } });
  } catch (err) {
    show(els.message, err.message, 'error');
  }
  updateListener(text, 'Emergency');
}

// ---------- live state ----------
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
  els.history.replaceChildren(...history.map((h) => {
    const li = document.createElement('li');
    const meta = document.createElement('span');
    meta.className = 'muted small';
    meta.textContent = `${h.time} · ${pretty(h.gesture)} · ${h.context}`;
    const text = document.createElement('div');
    text.textContent = h.phrase;
    li.append(text, meta);
    return li;
  }));
}

function setBadge(el, ok, okText, badText) {
  el.textContent = ok ? okText : badText;
  el.classList.toggle('ok', ok);
  el.classList.toggle('bad', !ok);
}

async function refreshState() {
  try {
    const data = await api('/get_state');
    els.context.textContent = data.context;
    els.gesture.textContent = pretty(data.gesture);
    els.phrase.textContent = data.phrase;
    setActiveContext(data.context);
    renderHistory(data.history);
    setBadge(els.cameraBadge, data.camera_ok, 'Camera on', 'No camera');
    setBadge(els.ttsBadge, data.tts_available && !data.muted, 'Speaker on',
      data.tts_available ? 'Speaker muted' : 'No speaker');
    els.mute.checked = data.muted;

    // Server has no audio? Default to speaking in the browser.
    if (storage.get('browserVoice') === null && !data.tts_available) {
      els.browserVoice.checked = true;
    }

    const latest = data.history[0];
    if (lastSpeechId !== null && data.speech_id > lastSpeechId && latest && latest.source !== 'sos') {
      speakInBrowser(latest.phrase);
    }
    if (data.gesture !== 'none') updateListener(data.phrase, data.context);
    else if (latest && data.speech_id > (lastSpeechId ?? data.speech_id)) updateListener(latest.phrase, data.context);
    lastSpeechId = data.speech_id;
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

// ---------- gestures table ----------
async function loadGestures() {
  try {
    const data = await api('/gestures');
    els.gestureHead.innerHTML = '';
    const head = document.createElement('tr');
    ['Gesture', ...data.contexts.map((c) => c[0].toUpperCase() + c.slice(1)), ''].forEach((t) => {
      const th = document.createElement('th');
      th.textContent = t;
      head.append(th);
    });
    els.gestureHead.append(head);

    const trained = data.gestures.filter((g) => g.samples > 0).length;
    els.gestureCount.textContent = `${data.gestures.length} gestures · ${trained} trained`;

    els.gestureBody.replaceChildren(...data.gestures.map((g) => {
      const tr = document.createElement('tr');
      const nameTd = document.createElement('td');
      nameTd.innerHTML = '<strong></strong><br><span class="muted small"></span>';
      nameTd.querySelector('strong').textContent = pretty(g.name);
      const tags = [];
      if (g.builtin) tags.push('built-in');
      if (g.samples) tags.push(`${g.samples} samples`);
      nameTd.querySelector('span').textContent = tags.join(' · ');
      tr.append(nameTd);

      data.contexts.forEach((c) => {
        const td = document.createElement('td');
        td.textContent = g.messages[c] || '—';
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

// ---------- train / edit dialog ----------
function messageInputs() {
  return [...els.form.querySelectorAll('input[data-context]')];
}

function openDialog(mode, gesture = null) {
  dialogMode = mode;
  captured = false;
  els.form.reset();
  show(els.dialogMessage);
  els.name.readOnly = mode === 'edit';
  els.dialogTitle.textContent = mode === 'edit' ? `Edit “${pretty(gesture.name)}”` : 'Train a gesture';
  els.captureBtn.hidden = mode === 'edit';
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
    captured = true;
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
    if (dialogMode === 'edit') {
      await api(`/phrases/${encodeURIComponent(name)}`, { method: 'PUT', body: { messages } });
      show(els.message, `Updated phrases for ${pretty(name)}`, 'ok');
    } else {
      if (!captured) { show(els.dialogMessage, 'Capture the gesture first', 'error'); return; }
      const data = await api('/train', { method: 'POST', body: { gesture_name: name, messages } });
      show(els.message, `Trained “${pretty(data.gesture_name)}” (+${data.samples_added} samples)`, 'ok');
    }
    els.dialog.close();
    loadGestures();
  } catch (err) {
    show(els.dialogMessage, err.message, 'error');
  }
}

// ---------- typed speech ----------
async function speakTyped(event) {
  event.preventDefault();
  const input = $('speakInput');
  const text = input.value.trim();
  if (!text) return;
  try {
    await api('/speak', { method: 'POST', body: { text } });
    input.value = '';
    refreshState();
  } catch (err) {
    show(els.message, err.message, 'error');
  }
}

// ---------- wiring ----------
$('trainBtn').addEventListener('click', () => openDialog('train'));
els.captureBtn.addEventListener('click', captureGesture);
els.cancelBtn.addEventListener('click', () => els.dialog.close());
els.form.addEventListener('submit', saveDialog);
$('speakForm').addEventListener('submit', speakTyped);
contextButtons.forEach((btn) => btn.addEventListener('click', () => setContext(btn.dataset.context)));

els.mute.addEventListener('change', async () => {
  try { await api('/set_mute', { method: 'POST', body: { muted: els.mute.checked } }); refreshState(); }
  catch (err) { show(els.message, err.message, 'error'); }
});

const savedVoice = storage.get('browserVoice');
if (savedVoice !== null) els.browserVoice.checked = savedVoice === '1';
els.browserVoice.addEventListener('change', () => storage.set('browserVoice', els.browserVoice.checked ? '1' : '0'));

$('sosBtn').addEventListener('click', sos);
$('displayBtn').addEventListener('click', openListener);
$('closeListener').addEventListener('click', closeListener);
document.addEventListener('fullscreenchange', () => {
  if (!document.fullscreenElement && !listener.view.hidden) listener.view.hidden = true;
});
voiceSelect.addEventListener('change', () => storage.set('voice', voiceSelect.value));
rateInput.addEventListener('change', () => storage.set('rate', rateInput.value));
rateInput.value = storage.get('rate') || '1';
loadVoices();
if ('speechSynthesis' in window) window.speechSynthesis.addEventListener('voiceschanged', loadVoices);

// Keyboard shortcuts: 1-9 switch context, L = listener view, Esc closes it
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !listener.view.hidden) { closeListener(); return; }
  if (e.target.matches('input, textarea, select') || els.dialog.open) return;
  if (e.key.toLowerCase() === 'l') { openListener(); return; }
  const n = Number(e.key);
  if (n >= 1 && n <= CONTEXTS.length) setContext(CONTEXTS[n - 1]);
});

refreshState();
loadGestures();
setInterval(refreshState, 500);
