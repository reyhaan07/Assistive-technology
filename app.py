"""ADAPT-AAC — Flask app.

Starts with no camera. Two input sources feed the SAME controller: development
simulation (always available) and real ocular input (webcam). Routes stay thin:
validate, call a component, return the result.
"""

from flask import Flask, Response, jsonify, render_template, request

import config
from controller import Controller
from events import sim_event
from speech.tts import Speaker
from vision.camera import Camera
from vision.face import FaceMesh
from vision.ocular import OcularInput

app = Flask(__name__)

controller = Controller(Speaker(cooldown=config.SPEECH_COOLDOWN_SECONDS))
camera = Camera(config.CAMERA_INDEX)  # the one camera abstraction; not started yet
ocular = OcularInput(camera, FaceMesh(), on_event=controller.handle)

input_mode = "simulation"


def status():
    data = controller.snapshot()
    data["input"] = input_mode.upper()
    data["camera"] = camera.status()
    data["speech_available"] = controller.speaker.available
    data["debug"] = ocular.debug
    data["ocular"] = ocular.status()
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


@app.route("/input_mode", methods=["POST"])
def set_input_mode():
    global input_mode
    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode", "")).strip().lower()

    if mode == "ocular":
        if not ocular.running() and not ocular.start():
            return jsonify({"error": "camera/ocular unavailable", **status()}), 503
        input_mode = "ocular"
    elif mode == "simulation":
        if ocular.running():
            ocular.stop()
        input_mode = "simulation"
    else:
        return jsonify({"error": f"unknown mode: {mode}"}), 400

    return jsonify(status())


@app.route("/debug", methods=["POST"])
def set_debug():
    body = request.get_json(silent=True) or {}
    ocular.set_debug(bool(body.get("on", False)))
    return jsonify(status())


@app.route("/video_feed")
def video_feed():
    if not ocular.running():
        return "camera not running", 503
    return Response(ocular.mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/calibration/start", methods=["POST"])
def calibration_start():
    if not ocular.running():
        return jsonify({"error": "start ocular mode first"}), 400
    body = request.get_json(silent=True) or {}
    phase = str(body.get("phase", "")).strip().lower()
    if phase not in ("baseline", "natural", "intentional"):
        return jsonify({"error": f"unknown phase: {phase}"}), 400
    ocular.begin_calibration(phase)
    return jsonify({"phase": phase, "counts": ocular.calibration_counts()})


@app.route("/calibration/finish", methods=["POST"])
def calibration_finish():
    if ocular.calibrator is None:
        return jsonify({"error": "no calibration in progress"}), 400
    result = ocular.finish_calibration()
    return jsonify({"ok": result.ok, "reason": result.reason})


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=False)
