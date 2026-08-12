import vision.camera as camera_module


def test_import_and_construct_touch_no_hardware():
    # Importing the module and constructing Camera must not open a camera.
    cam = camera_module.Camera()
    assert cam.status() == "NOT INITIALIZED"
    assert cam.frame() is None


def test_status_reported_cleanly_without_opencv(monkeypatch):
    # With no opencv available, start() reports an error instead of raising.
    monkeypatch.setattr(camera_module, "cv2", None)
    cam = camera_module.Camera()
    assert cam.start() is False
    assert "ERROR" in cam.status()
