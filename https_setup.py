"""Create and serve Align's private LAN HTTPS certificates.

The root CA stays on this PC. A fresh server certificate is issued each time
Wi-Fi mode starts, so DHCP address changes do not require a new root profile.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import os
from pathlib import Path
import socket
import sys
import uuid

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
except ImportError as error:  # pragma: no cover - friendly launcher path
    raise SystemExit(
        "Align HTTPS support is not installed. Run 'Install Align HTTPS Support.bat' first."
    ) from error

ROOT = Path(__file__).resolve().parent
CERT_DIR = ROOT / ".align_https"
CA_KEY = CERT_DIR / "align-local-ca-key.pem"
CA_CERT = CERT_DIR / "align-local-ca.crt"
SERVER_KEY = CERT_DIR / "align-server-key.pem"
SERVER_CERT = CERT_DIR / "align-server.crt"
PROFILE = CERT_DIR / "Align Local Root CA.mobileconfig"


def _write_private(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def lan_ipv4_addresses() -> list[str]:
    """Return usable non-loopback IPv4 addresses, preferred route first."""
    found: list[str] = []

    # A UDP connect picks a local interface without needing a successful remote
    # connection or transmitting application data.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.0.2.1", 9))
        found.append(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            found.append(info[4][0])
    except OSError:
        pass

    result: list[str] = []
    for value in found:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.is_loopback or address.is_link_local or address.is_unspecified:
            continue
        if value not in result:
            result.append(value)
    return result


def preferred_lan_ip() -> str:
    addresses = lan_ipv4_addresses()
    if not addresses:
        raise RuntimeError(
            "No Wi-Fi/LAN IPv4 address was found. Connect the PC to the same network as the iPhone and try again."
        )
    return addresses[0]


def ensure_ca() -> tuple[object, x509.Certificate]:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if CA_KEY.exists() and CA_CERT.exists():
        key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
        cert = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
        return key, cert

    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = datetime.now(timezone.utc)
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Align Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Align Local Root CA"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private(
        CA_KEY,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    CA_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def issue_server_certificate() -> tuple[Path, Path, str]:
    ca_key, ca_cert = ensure_ca()
    addresses = lan_ipv4_addresses()
    preferred = preferred_lan_ip()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    hostname = socket.gethostname()
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Align Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Align Local Server"),
    ])
    sans: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    if hostname and hostname.casefold() != "localhost":
        sans.append(x509.DNSName(hostname))
    for value in addresses:
        if value != "127.0.0.1":
            sans.append(x509.IPAddress(ipaddress.ip_address(value)))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_private(
        SERVER_KEY,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    SERVER_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    write_mobileconfig(ca_cert)
    return SERVER_CERT, SERVER_KEY, preferred


def write_mobileconfig(ca_cert: x509.Certificate) -> Path:
    cert_b64 = base64.b64encode(ca_cert.public_bytes(serialization.Encoding.DER)).decode("ascii")
    profile_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "align.local.profile" )).upper()
    cert_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "align.local.root-ca" )).upper()
    profile = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>PayloadContent</key>
  <array>
    <dict>
      <key>PayloadCertificateFileName</key><string>Align Local Root CA.cer</string>
      <key>PayloadContent</key><data>{cert_b64}</data>
      <key>PayloadDescription</key><string>Trusts only HTTPS certificates issued by this Align installation.</string>
      <key>PayloadDisplayName</key><string>Align Local Root CA</string>
      <key>PayloadIdentifier</key><string>local.align.root-ca</string>
      <key>PayloadType</key><string>com.apple.security.root</string>
      <key>PayloadUUID</key><string>{cert_uuid}</string>
      <key>PayloadVersion</key><integer>1</integer>
    </dict>
  </array>
  <key>PayloadDescription</key><string>Local HTTPS trust profile for Align on your home/work Wi-Fi.</string>
  <key>PayloadDisplayName</key><string>Align Local HTTPS</string>
  <key>PayloadIdentifier</key><string>local.align.profile</string>
  <key>PayloadOrganization</key><string>Align Local</string>
  <key>PayloadRemovalDisallowed</key><false/>
  <key>PayloadType</key><string>Configuration</string>
  <key>PayloadUUID</key><string>{profile_uuid}</string>
  <key>PayloadVersion</key><integer>1</integer>
</dict>
</plist>
'''
    PROFILE.write_text(profile, encoding="utf-8")
    return PROFILE


class CertificateHandler(BaseHTTPRequestHandler):
    profile_bytes: bytes = b""
    cert_bytes: bytes = b""
    https_url: str = ""

    def log_message(self, fmt, *args):
        print(f"{self.log_date_time_string()}  {fmt % args}")

    def do_GET(self):
        if self.path in {"/align-ca.mobileconfig", "/Align%20Local%20Root%20CA.mobileconfig"}:
            body = self.profile_bytes
            self.send_response(200)
            self.send_header("Content-Type", "application/x-apple-aspen-config")
            self.send_header("Content-Disposition", 'attachment; filename="Align Local Root CA.mobileconfig"')
        elif self.path == "/align-local-ca.crt":
            body = self.cert_bytes
            self.send_response(200)
            self.send_header("Content-Type", "application/x-x509-ca-cert")
            self.send_header("Content-Disposition", 'attachment; filename="align-local-ca.crt"')
        else:
            body = f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Align HTTPS Setup</title></head><body style="font-family:-apple-system,system-ui;padding:24px;max-width:680px;margin:auto">
<h1>Align HTTPS setup</h1>
<p><strong>Step 1:</strong> Tap <a href="/align-ca.mobileconfig">Install Align certificate profile</a>.</p>
<p><strong>Step 2:</strong> Open Settings &gt; General &gt; VPN &amp; Device Management, open the downloaded Align profile and install it.</p>
<p><strong>Step 3:</strong> Open Settings &gt; General &gt; About &gt; Certificate Trust Settings and enable full trust for <strong>Align Local Root CA</strong>.</p>
<p><strong>Step 4:</strong> Return to the PC, stop this certificate server, then start <strong>Start Align on Wi-Fi.bat</strong>.</p>
<p>Your Align HTTPS address will be <code>{self.https_url}</code>.</p>
</body></html>'''.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve_profile(port: int = 8002) -> None:
    cert_path, _, ip = issue_server_certificate()
    del cert_path
    CertificateHandler.profile_bytes = PROFILE.read_bytes()
    CertificateHandler.cert_bytes = CA_CERT.read_bytes()
    app_port = int(os.environ.get("ALIGN_PORT", "8001"))
    CertificateHandler.https_url = f"https://{ip}:{app_port}/"
    server = ThreadingHTTPServer(("0.0.0.0", port), CertificateHandler)
    print("\nALIGN IPHONE HTTPS SETUP")
    print("========================")
    print(f"On your iPhone Safari, open: http://{ip}:{port}/")
    print("Keep this window open until the profile is installed, then press Ctrl+C.")
    print("The root private key stays on this PC and is never sent to the phone.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCertificate setup server stopped.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve-ca", action="store_true", help="Serve the iPhone trust profile over temporary HTTP.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("ALIGN_CERT_PORT", "8002")))
    args = parser.parse_args()
    if args.serve_ca:
        serve_profile(args.port)
        return
    cert, key, ip = issue_server_certificate()
    print(f"Certificate: {cert}")
    print(f"Private key: {key}")
    print(f"LAN IP: {ip}")


if __name__ == "__main__":
    main()
