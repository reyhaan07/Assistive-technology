# Assistive Technology – GestureTalk

## 🚀 Overview

GestureTalk is a real-time gesture-to-speech system that converts hand gestures into spoken phrases using computer vision. It helps people with speech impairments communicate in everyday places such as cafes, hospitals, colleges and banks, using nothing more than a webcam.

## ❗ Problem Statement

People with speech or hearing impairments often struggle with real-time communication. Existing solutions are expensive or not intuitive. GestureTalk is a low-cost, offline alternative built on AI hand tracking.

---

## 💡 Features

### 👁 Eye-blink communication – for people who cannot move
* **Yes / No blinks** – 2 quick blinks = "Yes", 3 quick blinks = "No", a long blink (~1 s) = "I need help" (at a hospital: "Please call the nurse"). All editable per context.
* **Blink board** – a scanning board where tiles light up one after another and a **long blink selects**. It has quick phrases, the current context's phrases (most-used first), an emergency button, "My usual", "Medical info", switching place, and letter groups to **spell any message**, with **word suggestions** learned from what the user says.
* A **very long blink (~2 s)** opens the board, so the user can get there without help.
* No calibration: the "eyes closed" level adapts to each person's eyes automatically.
* The caregiver picks the mode once – it is remembered and restored after a restart.

### 📍 GPS places, "my usual" and the medical card
* Save the places you visit (your café, hospital, college, bank…) with your GPS position. When you **arrive, the context switches automatically**.
* **Café → your regular order.** Each place stores "my usual", e.g. *"Large oat latte, no sugar"*. Thumbs-up at your café says it.
* **Hospital → your medical card.** Name, conditions, allergies, medications, blood type and emergency contact are spoken with "Medical info" (or `{medical}` in any phrase).
* **SOS includes your location** (place name or coordinates) and shows a map link and the emergency phone number.
* Places learn: every accurate visit refines the saved position.
* Readings worse than ±500 m (typical Wi-Fi guesses on a laptop, or indoors) are **never** used to arrive at or leave a place, and a place can't be saved from one – so a bad fix can't switch you to the wrong context. They are still used for SOS ("my approximate location…").
* Browsers only allow GPS on `https://` or `http://localhost` – see **Using your phone's GPS** below.

### 🧠 Gets more accurate the more you use it
* Confident recognitions are stored as new samples of **your** hand (old ones roll off, max 40 per gesture).
* The **"Wrong?"** button teaches the correct gesture for the last pose.
* Phrases you use most move to the front of the blink board; words you use are suggested first when spelling or typing.

### ✋ Hand gestures

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
* Everything is saved locally (`gestures.json`, `phrases.json`, `places.json`, `profile.json`, `usage.json`) and survives restarts. These files are git-ignored – your medical data never leaves the computer.
* Keyboard shortcuts: `1`–`4` switch context, `L` listener view, `B` blink board, `Space` selects on the board, `Esc` closes overlays.

Phrases can contain placeholders: `{usual|fallback}`, `{medical}`, `{place}`, `{name}`.

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

### 📱 Using your phone's GPS

Laptops usually have no GPS chip, so the best location comes from a phone. Browsers only give a page the location over HTTPS, so start GestureTalk with:

```bash
python app.py --https
```

It prints an address such as `https://192.168.1.20:5000`. Open that on your phone (connected to the same Wi-Fi). The phone warns that the certificate is not trusted – it is your own computer's self-signed certificate, so choose **Advanced → Proceed**. This is only needed once; the certificate is saved in `certs/` and reused (it is regenerated automatically if your Wi-Fi address changes). Then tick **Use GPS** on the phone.

Other options: `--port 8443`, `--host 0.0.0.0`, `--camera 1`.

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

**Eyes only:** in the *Eye blink communication* panel choose *Blink board* (or *Yes / No blinks*). Sit facing the camera. Items light up in turn – hold your eyes closed for about a second to choose.

**Places:** tick *Use GPS*, then at your café type its name and your usual order and press *Save this place*.

**Hands:**
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
eyes.py         Eye-aspect-ratio blink detection and blink-pattern decoding
places.py       GPS places, "my usual", medical card, phrase placeholders
learning.py     Phrase / word usage learning for suggestions
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
| POST | `/set_eye_mode` | `{"mode": "off" \| "patterns" \| "board"}` |
| POST | `/correct` | `{"gesture_name": "water"}` – learn the last pose as this gesture |
| POST | `/set_auto_learn` | `{"enabled": true}` |
| GET | `/suggest?prefix=wa` | Learned word suggestions and most-used phrases |
| POST | `/location` | `{"lat": .., "lon": .., "accuracy": ..}` – may switch context |
| POST | `/set_auto_context` | `{"enabled": true}` |
| GET/POST | `/places` | List / add places (`name`, `context`, `lat`, `lon`, `radius`, `usual`) |
| PUT/DELETE | `/places/<id>` | Update / delete a place |
| GET/PUT | `/profile` | Medical card |
| GET | `/video_feed` | MJPEG camera stream |

---

## 🎯 Future Improvements

* Mobile application version
* Multi-language phrase sets
* Gesture sequences (combine gestures into sentences)
* Send SOS as an SMS / message to the emergency contact
* Gaze direction (look left / right) as a second switch for the blink board
* Cloud deployment
