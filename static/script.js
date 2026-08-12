const $ = (id) => document.getElementById(id);

function render(data) {
  $('modeLabel').textContent = data.input;
  $('state').textContent = data.state;
  $('input').textContent = data.input;
  $('camera').textContent = data.camera;
  $('speech').textContent = data.speech_available ? 'available' : 'unavailable';
  $('candidates').textContent = data.candidates.length ? data.candidates.join(', ') : '-';
  $('final').textContent = data.final_message || '-';

  const ocular = data.input === 'OCULAR';
  $('ocularPanel').classList.toggle('hidden', !ocular);
  if (ocular && !$('videoFeed').src) $('videoFeed').src = '/video_feed';
  if (!ocular) $('videoFeed').src = '';

  $('debugToggle').checked = data.debug;
  $('debugPanel').classList.toggle('hidden', !data.debug);

  const o = data.ocular || {};
  $('oFace').textContent = o.face || '-';
  $('oEar').textContent = o.ear ?? '-';
  $('oPhase').textContent = o.blink_phase || '-';
  $('oRel').textContent = o.reliability || '-';
  $('oGaze').textContent = o.gaze || '-';
  $('oCounts').textContent = `${o.natural_blinks ?? 0} / ${o.intentional_blinks ?? 0}`;
  $('oCal').textContent = o.calibrated ? 'yes' : 'no';
}

async function refresh() {
  render(await (await fetch('/state')).json());
}

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  return { ok: res.ok, data: await res.json() };
}

document.querySelectorAll('button[data-mode]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    $('modeError').textContent = '';
    const { ok, data } = await post('/input_mode', { mode: btn.dataset.mode });
    if (!ok) $('modeError').textContent = data.error || 'failed';
    render(data);
  });
});

$('debugToggle').addEventListener('change', async (e) => {
  render((await post('/debug', { on: e.target.checked })).data);
});

document.querySelectorAll('button[data-phase]').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const { ok, data } = await post('/calibration/start', { phase: btn.dataset.phase });
    $('calResult').textContent = ok ? `collecting: ${btn.dataset.phase}` : (data.error || 'failed');
  });
});

$('calFinish').addEventListener('click', async () => {
  const { data } = await post('/calibration/finish', {});
  $('calResult').textContent = data.ok ? 'Calibration complete' : `Calibration failed: ${data.reason || data.error}`;
  refresh();
});

document.querySelectorAll('button[data-event]').forEach((btn) => {
  btn.addEventListener('click', async () => render((await post('/simulate', { event: btn.dataset.event })).data));
});

refresh();
setInterval(refresh, 1000);
