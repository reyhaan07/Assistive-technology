/* Browser camera mode: hand + face tracking run on this device with MediaPipe
 * Tasks (WebAssembly). Only landmark coordinates are sent to the server –
 * the video never leaves the device. */
const cfg = document.getElementById('visionConfig').dataset;
const video = document.getElementById('camVideo');
const canvas = document.getElementById('camOverlay');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('camStatus');
const labelEl = document.getElementById('camLabel');

// Face Mesh indices for the eye-aspect-ratio: left eye p1..p6, then right eye p1..p6.
const EYE_IDX = [33, 160, 158, 133, 153, 144, 362, 385, 387, 263, 373, 380];
const HAND_LINKS = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10],
  [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
const FRAME_MS = 66; // ~15 frames per second is plenty and keeps laptops cool

let vision; let handLandmarker; let faceLandmarker = null; let faceLoading = false;
let lastFrame = 0; let inflight = false;

function setStatus(text, isError = false) {
  statusEl.hidden = !text;
  statusEl.textContent = text || '';
  statusEl.classList.toggle('error', isError);
}

async function createLandmarker(Cls, modelPath, extra) {
  for (const delegate of ['GPU', 'CPU']) {
    try {
      return await Cls.createFromOptions(vision, {
        baseOptions: { modelAssetPath: modelPath, delegate }, runningMode: 'VIDEO', ...extra,
      });
    } catch (err) {
      if (delegate === 'CPU') throw err;
    }
  }
  return null;
}

async function ensureFace(FaceLandmarker) {
  if (faceLandmarker || faceLoading) return;
  faceLoading = true;
  try {
    faceLandmarker = await createLandmarker(FaceLandmarker, cfg.faceModel, { numFaces: 1 });
  } catch (err) {
    setStatus(`Eye tracking failed to load: ${err.message}`, true);
  } finally {
    faceLoading = false;
  }
}

function draw(hand, face, eyeClosed) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const W = canvas.width; const H = canvas.height;
  if (hand) {
    ctx.strokeStyle = '#22c55e'; ctx.lineWidth = Math.max(2, W / 240);
    HAND_LINKS.forEach(([a, b]) => {
      ctx.beginPath(); ctx.moveTo(hand[a].x * W, hand[a].y * H); ctx.lineTo(hand[b].x * W, hand[b].y * H); ctx.stroke();
    });
    ctx.fillStyle = '#f8fafc';
    hand.forEach((p) => { ctx.beginPath(); ctx.arc(p.x * W, p.y * H, Math.max(2.5, W / 200), 0, 2 * Math.PI); ctx.fill(); });
  }
  if (face) {
    ctx.fillStyle = eyeClosed ? '#fb7185' : '#38bdf8';
    EYE_IDX.forEach((i) => { ctx.beginPath(); ctx.arc(face[i].x * W, face[i].y * H, Math.max(2, W / 260), 0, 2 * Math.PI); ctx.fill(); });
  }
}

function send(payload) {
  if (inflight) return; // drop frames rather than queue them
  inflight = true;
  fetch('/landmarks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    .catch(() => {})
    .finally(() => { inflight = false; });
}

function loop(FaceLandmarker) {
  const now = performance.now();
  if (video.readyState >= 2 && now - lastFrame >= FRAME_MS) {
    lastFrame = now;
    const shared = window.gestureTalk || {};
    const W = video.videoWidth; const H = video.videoHeight;
    if (canvas.width !== W) { canvas.width = W; canvas.height = H; }

    let handPts = null; let handedness = null; let handRaw = null;
    const hr = handLandmarker.detectForVideo(video, now);
    if (hr.landmarks && hr.landmarks.length) {
      handRaw = hr.landmarks[0];
      // Mirror x so coordinates match the selfie view the server-camera mode uses,
      // and swap handedness for the same reason (MediaPipe assumes mirrored input).
      handPts = handRaw.map((p) => [1 - p.x, p.y, p.z]);
      const cats = (hr.handednesses || hr.handedness || [])[0];
      if (cats && cats[0]) handedness = cats[0].categoryName === 'Left' ? 'Right' : 'Left';
    }

    let eye = null; let faceRaw = null;
    if (shared.eyeMode && shared.eyeMode !== 'off') {
      if (!faceLandmarker) ensureFace(FaceLandmarker);
      else {
        const fr = faceLandmarker.detectForVideo(video, now);
        if (fr.faceLandmarks && fr.faceLandmarks.length) {
          faceRaw = fr.faceLandmarks[0];
          eye = EYE_IDX.map((i) => [faceRaw[i].x * W, faceRaw[i].y * H]); // pixels keep the eye's shape
        }
      }
    }

    draw(handRaw, faceRaw, shared.eyeClosed);
    const g = shared.gesture;
    labelEl.hidden = !g || g === 'none';
    labelEl.textContent = g ? g.replace(/_/g, ' ') : '';
    send({ hand: handPts, handedness, eye });
  }
  requestAnimationFrame(() => loop(FaceLandmarker));
}

async function start() {
  if (!window.isSecureContext) {
    setStatus('The camera needs https:// or http://localhost. Start with “python app.py --https”.', true);
    return;
  }
  try {
    setStatus('Asking for camera permission…');
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false,
    });
    video.srcObject = stream;
    await video.play().catch(() => {});
  } catch (err) {
    const msg = err.name === 'NotAllowedError'
      ? 'Camera permission was denied. Allow the camera for this site (address bar → camera icon) and reload.'
      : err.name === 'NotFoundError' ? 'No camera found on this device.' : `Camera error: ${err.message}`;
    setStatus(msg, true);
    return;
  }
  try {
    setStatus('Loading hand tracking (first time can take ~10 s)…');
    const mod = await import(`${cfg.base}/vision_bundle.mjs`);
    vision = await mod.FilesetResolver.forVisionTasks(`${cfg.base}/wasm`);
    handLandmarker = await createLandmarker(mod.HandLandmarker, cfg.handModel, { numHands: 1 });
    setStatus('');
    loop(mod.FaceLandmarker);
  } catch (err) {
    setStatus(`Could not load hand tracking: ${err.message}`, true);
  }
}

start();
