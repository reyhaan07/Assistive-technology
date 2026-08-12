const fields = {
  state: document.getElementById('state'),
  camera: document.getElementById('camera'),
  input: document.getElementById('input'),
  speech: document.getElementById('speech'),
  candidates: document.getElementById('candidates'),
  final: document.getElementById('final'),
};

function render(data) {
  fields.state.textContent = data.state;
  fields.camera.textContent = data.camera;
  fields.input.textContent = data.input;
  fields.speech.textContent = data.speech_available ? 'available' : 'unavailable';
  fields.candidates.textContent = data.candidates.length ? data.candidates.join(', ') : '-';
  fields.final.textContent = data.final_message || '-';
}

async function refresh() {
  const res = await fetch('/state');
  render(await res.json());
}

async function sendEvent(name) {
  const res = await fetch('/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: name }),
  });
  render(await res.json());
}

document.querySelectorAll('button[data-event]').forEach((btn) => {
  btn.addEventListener('click', () => sendEvent(btn.dataset.event));
});

refresh();
setInterval(refresh, 1000);
