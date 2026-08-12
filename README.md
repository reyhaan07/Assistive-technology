# ADAPT-AAC

Adaptive, Confidence- and Effort-Aware Augmentative Communication.

The research idea is **confidence- and interaction-cost-aware adaptive selection
between predictive communication and conventional AAC**: instead of forcing every
message through one interaction method, the system routes high-confidence
predictions to a quick confirmation, medium-confidence ones to a short list of
choices, and low-confidence ones to a conventional AAC fallback — and the user
always confirms before anything is spoken.

This repository is being built in stages. **Stage 1 is the foundation only** — it
sets up the architecture and the safety boundary so later stages can add ocular
input, prediction, confidence, and the adaptive policy cleanly.

## Safety invariant

`prediction != confirmation` and `unconfirmed prediction != speech`.

This is enforced in the architecture, not just the UI:

- The predictor, camera and input modules never import the speaker, so they
  cannot reach speech.
- `Speaker.speak()` accepts only a `ConfirmedMessage`, never raw text.
- A `ConfirmedMessage` can only be produced by `CommunicationSession.confirm()`,
  which requires a confirm-capable state (guarded by a private key).
- The state machine forbids reaching `SPEAKING` except through
  `CONFIRM/CHOICE/FALLBACK -> READY_TO_SPEAK -> SPEAKING`.

## Structure

```
app.py            Flask app (thin routes)
config.py         thresholds and the few values used
controller.py     wires input events -> state machine -> (confirmed) speech
events.py         InputEvent + simulated-event helper (sources: simulation, ocular)
storage.py        minimal local JSON storage

vision/camera.py       camera abstraction (no hardware on import)
vision/face.py         MediaPipe Face Mesh adapter (only mediapipe-dependent file)
vision/eyes.py         Eye Aspect Ratio (pure geometry)
vision/blink.py        temporal blink detector (natural vs intentional)
vision/reliability.py  input reliability (GOOD / UNCERTAIN / UNRELIABLE)
vision/calibration.py  per-user calibration
vision/gaze.py         experimental gaze (LEFT/CENTER/RIGHT), not wired in
vision/ocular.py       ocular source: frames -> blink -> InputEvent(source="ocular")

prediction/predictor.py   prediction interface (development stub)
adaptive/policy.py        adaptive policy (stub interface, Stage 6)
aac/state.py              communication state machine + session
aac/fallback.py           conventional AAC boundary (Stage 3)
speech/tts.py             speaks only confirmed messages
research/logging.py       research logging boundary (Stage 8)

templates/, static/   temporary development UI
tests/                unit tests
```

## Run

```bash
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

The app starts with **no camera**. The UI has two input sources that feed the
same controller:

- **Simulation** (default): buttons for `BLINK / SELECT / CONFIRM / REJECT / CANCEL`.
- **Ocular** (webcam): real blink detection. Switch with the *Ocular* button; if
  no camera is available the app stays in simulation and reports it.

Both produce the same `InputEvent`; the rest of the app cannot tell them apart.

## Ocular input (Stage 2)

Pipeline: `camera -> face landmarks -> eye EAR -> temporal blink detector -> reliability -> InputEvent(BLINK, source="ocular")`.

- **EAR** (Eye Aspect Ratio) is the eye-opening metric, averaged over both eyes.
- **Blink** is temporal: eyes must go open -> closed -> open, with the closure
  lasting a sensible time. A single low-EAR frame is never a blink. A **longer**
  deliberate closure is classified **intentional**; only intentional blinks are
  forwarded as commands, so ordinary blinking does not drive the system. This is
  a heuristic prototype, not a solved or clinically validated distinction.
- **Calibration** learns per-user thresholds (one threshold does not fit
  everyone). Guided steps: look normally, blink normally ×5, intentional blinks
  ×5. Bad calibration is rejected with a reason, not silently stored.
- **Reliability** reports `GOOD / UNCERTAIN / UNRELIABLE` from recent tracking
  quality. It is not medical/fatigue monitoring.
- **Debug mode** (toggle) overlays EAR, blink phase, reliability and face state
  on the camera preview. Off by default.

A real blink still cannot speak: it becomes an `InputEvent`, goes to the
controller, and stops there — the Stage 1 confirmation boundary is unchanged.

## Privacy

Raw video is never stored. Only calibration **parameters** (thresholds and
durations) are saved, under `data/`. No face images or recordings are written.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Component status

| Component | Status |
|-----------|--------|
| Communication state machine | implemented |
| Simulated input + events | implemented |
| Camera abstraction | implemented |
| Ocular input: EAR + temporal blink detection | implemented |
| Per-user calibration | implemented |
| Input reliability | implemented |
| Speech (confirmed-only) | implemented |
| Local JSON storage | implemented |
| Gaze direction | experimental, not wired in |
| Prediction | stub |
| Adaptive policy | stub interface only |
| Prediction confidence / interaction cost | not implemented |
| Conventional AAC fallback | not implemented (Stage 3) |
| Research logging / baseline | not implemented (Stage 8) |

**Input confidence vs prediction confidence** are different things. Stage 2
implements only *input* reliability ("how good is the blink signal?"). Prediction
confidence ("how likely is the predicted message right?") is a later stage.
