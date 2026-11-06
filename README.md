# Assistive Technology – GestureTalk

## 🚀 Overview

GestureTalk is a real-time gesture-to-speech system that converts hand gestures into spoken phrases using computer vision. It helps people with speech impairments communicate in everyday places such as cafes, hospitals, colleges and banks, using nothing more than a webcam.

## ❗ Problem Statement

People with speech or hearing impairments often struggle with real-time communication. Existing solutions are expensive or not intuitive. GestureTalk is a low-cost, offline alternative built on AI hand tracking.

---

## 💡 Features

* **Works out of the box** – six built-in gestures (👍 thumbs up, 👎 thumbs down, ✋ stop, ✌️ peace, ☝️ point, ✊ fist) are recognised without any training.
* **Context-aware phrases** – the same gesture says different things depending on the selected place (e.g. 👍 = "One coffee please" in a cafe, "I am okay" in a hospital).
* **Custom gesture training** – capture your own gesture (several samples after a 3-second countdown), name it and give it a phrase per context. Re-training the same name adds more samples and improves accuracy.
* **Either hand** – left hands are mirrored, so a gesture trained with one hand works with the other.
* **Stable recognition** – a gesture must be held for a few frames before it is spoken, so it does not flicker or babble. A held gesture is repeated every few seconds.
* **Offline speech** (pyttsx3) **plus browser speech** – if the computer has no speaker driver, the page can speak instead, with a choice of voice/language and speed.
* **Listener display** – a full-screen, large-text view of the current phrase for the person you are talking to (useful in noisy places or for deaf listeners). Press `L` or click "Show to listener".
* **SOS button** – speaks an emergency message, sounds an alarm and flashes the screen.
* **Type to speak** – for anything there is no gesture for.
* **Manage everything in the UI** – edit phrases, delete trained gestures, see the history of what was said.
* Everything (gestures + phrases) is saved to `gestures.json` / `phrases.json` and survives restarts.
* Keyboard shortcuts: `1`–`4` switch context, `L` opens the listener view, `Esc` closes it.

---

## 🛠️ Tech Stack

Python · Flask · OpenCV · MediaPipe · NumPy · pyttsx3 · HTML/CSS/JavaScript (Web Speech API)

---

## ⚙️ Setup

> MediaPipe's hand-tracking API used here requires **Python 3.10 – 3.12**
> (newer MediaPipe releases removed it, so the version is pinned).

```bash
python -m venv venv311
venv311\Scripts\activate        # Windows
source venv311/bin/activate     # macOS / Linux
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000>.

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `GESTURETALK_CAMERA` | `0` | Camera index (try `1` for an external/phone webcam) |
| `GESTURETALK_PORT` | `5000` | Web server port |
| `GESTURETALK_HOST` | `0.0.0.0` | Bind address |
| `GESTURETALK_DATA_DIR` | project folder | Where `gestures.json` / `phrases.json` are stored |

Recognition settings (threshold, stability frames, repeat interval, …) live in `config.py`.

### Running the tests

```bash
python -m pytest
```

The tests use a fake camera and fake speech engine, so they don't need a webcam.

---

## 🧭 How to use

1. Pick a context (Cafe / Hospital / College / Bank).
2. Show a built-in gesture – the phrase appears and is spoken.
3. To add your own: **+ Train new gesture** → enter a name and phrases → **Capture** → hold the gesture during the countdown → **Save**.
4. Edit or delete gestures in the **Gestures** table.

---

## 📂 Project Structure

```
app.py          Flask app + API routes, recognition loop, speech decisions
camera.py       Webcam capture, MediaPipe hand tracking, video stream
gestures.py     Landmark normalisation, trained-gesture store, built-in gestures, smoothing
phrases.py      Per-context phrases (with defaults), saved to phrases.json
tts.py          Offline text-to-speech worker (pyttsx3)
config.py       Settings
templates/      index.html
static/         script.js, style.css
tests/          pytest suite
```

### API

| Method | Route | Description |
|---|---|---|
| GET | `/get_state` | Context, gesture, phrase, history, camera/speaker status |
| POST | `/set_context` | `{"context": "hospital"}` |
| POST | `/capture_landmarks?samples=5` | Record samples of the current hand pose |
| POST | `/train` | `{"gesture_name": "water", "messages": {"cafe": "Water please", ...}}` |
| GET | `/gestures` | List gestures with their phrases |
| DELETE | `/gestures/<name>` | Delete a trained gesture |
| PUT | `/phrases/<name>` | Update a gesture's phrases |
| POST | `/speak` | `{"text": "Hello"}` |
| POST | `/set_mute` | `{"muted": true}` |
| GET | `/video_feed` | MJPEG camera stream |

---

## 🎯 Future Improvements

* Mobile application version
* Multi-language phrase sets
* Gesture sequences (combine gestures into sentences)
* Cloud deployment
