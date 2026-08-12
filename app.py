"""ADAPT-AAC — Flask foundation (Stage 1).

Starts with no camera and no hardware access. Routes stay thin: validate the
request, call a component, return the result. All communication logic lives in
the controller and the state machine.
"""

from flask import Flask, jsonify, render_template, request

import config
from controller import Controller
from events import sim_event
from speech.tts import Speaker
from vision.camera import Camera

app = Flask(__name__)

controller = Controller(Speaker(cooldown=config.SPEECH_COOLDOWN_SECONDS))
camera = Camera(config.CAMERA_INDEX)  # created, NOT started (Stage 2 starts it)


def status():
    data = controller.snapshot()
    data["camera"] = camera.status()
    data["input"] = "SIMULATION"
    data["speech_available"] = controller.speaker.available
    return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/state")
def state():
    return jsonify(status())


@app.route("/simulate", methods=["POST"])
def simulate():
    body = request.get_json(silent=True) or {}
    name = str(body.get("event", "")).strip().upper()

    event = sim_event(name)
    if event is None:
        return jsonify({"error": f"unknown event: {name}"}), 400

    controller.handle(event)
    return jsonify(status())


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=False)
