import ssl
import threading
import urllib.request

import pytest

pytest.importorskip("cryptography")

from werkzeug.serving import make_server

from certs import _cert_ips, ensure_certificate, lan_ips


def test_certificate_created_reused_and_refreshed(tmp_path):
    cert, key = ensure_certificate(str(tmp_path), ips=["192.168.1.20"])
    assert {"127.0.0.1", "192.168.1.20"} <= _cert_ips(cert)
    first = open(cert, "rb").read()

    ensure_certificate(str(tmp_path), ips=["192.168.1.20"])
    assert open(cert, "rb").read() == first  # reused -> phone warning only once

    ensure_certificate(str(tmp_path), ips=["10.0.0.7"])  # Wi-Fi address changed
    assert "10.0.0.7" in _cert_ips(cert)


def test_lan_ips_returns_list():
    assert isinstance(lan_ips(), list)


def test_app_serves_over_https(tmp_path):
    from flask import Flask
    app = Flask(__name__)
    app.add_url_rule("/ping", "ping", lambda: "pong")
    cert, key = ensure_certificate(str(tmp_path), ips=[])
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server = make_server("127.0.0.1", 0, app, ssl_context=ctx)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client_ctx = ssl.create_default_context(cafile=cert)  # trust our own cert
        url = f"https://localhost:{server.port}/ping"
        assert urllib.request.urlopen(url, context=client_ctx, timeout=5).read() == b"pong"
    finally:
        server.shutdown()
