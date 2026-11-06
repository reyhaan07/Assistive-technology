"""Self-signed HTTPS certificate so phones on the same Wi-Fi can use GPS.

Browsers only share location with pages served over https:// (or localhost).
The certificate is created once and reused, so the phone's "not secure"
warning only has to be accepted once. It is regenerated automatically if the
computer's Wi-Fi address changes.
"""
import datetime
import ipaddress
import os
import socket
from typing import List, Tuple


def lan_ips() -> List[str]:
    """Best-effort list of this computer's LAN IPv4 addresses."""
    ips = set()
    try:
        # No packets are sent: connecting a UDP socket only selects the outgoing interface.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def _cert_ips(cert_path: str) -> set:
    from cryptography import x509
    with open(cert_path, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return set()
    return {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}


def ensure_certificate(cert_dir: str, ips: List[str] = None) -> Tuple[str, str]:
    """Return (cert_path, key_path), creating or refreshing a self-signed cert."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:
        raise RuntimeError("HTTPS needs the 'cryptography' package: pip install -r requirements.txt") from exc

    ips = lan_ips() if ips is None else ips
    cert_path = os.path.join(cert_dir, "gesturetalk-cert.pem")
    key_path = os.path.join(cert_dir, "gesturetalk-key.pem")
    wanted = set(ips) | {"127.0.0.1"}
    if os.path.exists(cert_path) and os.path.exists(key_path) and wanted <= _cert_ips(cert_path):
        return cert_path, key_path

    os.makedirs(cert_dir, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "GestureTalk (local)")])
    alt_names = [x509.DNSName("localhost"), x509.DNSName(socket.gethostname() or "localhost")]
    alt_names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in sorted(wanted)]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    os.chmod(key_path, 0o600)
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
