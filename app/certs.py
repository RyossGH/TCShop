"""Certificats HTTPS locaux pour l'appli iPhone (Safari exige HTTPS pour l'appareil photo et le mode hors ligne).

- Une autorité de certification « TCShop » propre à ce PC (valable 10 ans) : installée une seule fois sur l'iPhone.
- Un certificat serveur signé par elle pour les adresses IP actuelles du PC, régénéré automatiquement si elles changent.
  Règles Apple respectées : SAN, usage « serverAuth », RSA 2048, SHA-256, validité ≤ 825 jours.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .db import DATA_DIR

CERT_DIR = DATA_DIR / "certs"
CA_KEY, CA_CRT = CERT_DIR / "tcshop-ca.key", CERT_DIR / "tcshop-ca.crt"
SRV_KEY, SRV_CRT, SRV_META = CERT_DIR / "server.key", CERT_DIR / "server.crt", CERT_DIR / "server.json"


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_key(path, key):
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                       serialization.NoEncryption()))


def ensure_ca():
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if CA_KEY.exists() and CA_CRT.exists():
        key = serialization.load_pem_private_key(CA_KEY.read_bytes(), None)
        return key, x509.load_pem_x509_certificate(CA_CRT.read_bytes())
    key = _key()
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"TCShop — {socket.gethostname()}"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TCShop (boutique locale)"),
    ])
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - dt.timedelta(days=1))
            .not_valid_after(_now() + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    _write_key(CA_KEY, key)
    CA_CRT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def ca_der() -> bytes:
    """Certificat de l'autorité au format DER (.crt) : iOS le propose à l'installation comme profil."""
    _key_, cert = ensure_ca()
    return cert.public_bytes(serialization.Encoding.DER)


def ensure_server_cert(ips: list[str]) -> tuple[str, str]:
    """Renvoie (chemin certificat, chemin clé) valides pour ces adresses IP."""
    ca_key, ca_cert = ensure_ca()
    host = socket.gethostname()
    wanted = dict(ips=sorted(set(ips + ["127.0.0.1"])), host=host)
    try:
        meta = json.loads(SRV_META.read_text(encoding="utf-8"))
        cert = x509.load_pem_x509_certificate(SRV_CRT.read_bytes())
        still_valid = cert.not_valid_after_utc - _now() > dt.timedelta(days=30)
        if meta == wanted and still_valid and SRV_KEY.exists():
            return str(SRV_CRT), str(SRV_KEY)
    except (OSError, ValueError):
        pass
    key = _key()
    san = [x509.DNSName(host), x509.DNSName(f"{host}.local"), x509.DNSName("localhost")]
    san += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in wanted["ips"]]
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"TCShop {host}")]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - dt.timedelta(days=1))
            .not_valid_after(_now() + dt.timedelta(days=800))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, content_commitment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _write_key(SRV_KEY, key)
    # chaîne complète : certificat serveur + autorité
    SRV_CRT.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM))
    SRV_META.write_text(json.dumps(wanted), encoding="utf-8")
    return str(SRV_CRT), str(SRV_KEY)
