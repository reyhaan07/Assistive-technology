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
config.py         the few values Stage 1 uses
controller.py     wires input events -> state machine -> (confirmed) speech
events.py         InputEvent + simulated-event helper
storage.py        minimal local JSON storage

vision/camera.py      camera abstraction (no hardware on import)
prediction/predictor.py   prediction interface (development stub)
adaptive/policy.py        adaptive policy (stub interface, Stage 6)
aac/state.py              communication state machine + session
aac/fallback.py           conventional AAC boundary (Stage 3)
speech/tts.py             speaks only confirmed messages
research/logging.py       research logging boundary (Stage 8)

templates/, static/   temporary development UI
tests/                foundation tests
```

## Run

```bash
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

The app starts with **no camera**. The development UI runs in
`DEVELOPMENT / SIMULATION MODE` and lets you drive the state machine with
simulated `BLINK / SELECT / CONFIRM / REJECT / CANCEL` events. This is not real
ocular detection — that arrives in Stage 2.

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
| Camera abstraction | implemented (capture only) |
| Speech (confirmed-only) | implemented |
| Local JSON storage | implemented |
| Prediction | stub |
| Adaptive policy | stub interface only |
| Conventional AAC fallback | not implemented (Stage 3) |
| Ocular input / blink / gaze / calibration | not implemented (Stage 2) |
| Confidence / interaction cost | not implemented |
| Research logging / baseline | not implemented (Stage 8) |
