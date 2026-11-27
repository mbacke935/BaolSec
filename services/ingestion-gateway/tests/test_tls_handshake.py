"""Tests réels de handshake TLS/mTLS pour le Syslog (A-13, C26, F-4).

Contexte (audit C26, constat F-4 du rapport de clôture) : les tests existants (A-01,
A-06 dans test_syslog.py) simulent le certificat client via un objet _FakeSSLObject
qui renvoie un DER arbitraire sans jamais faire passer de poignée de main TLS réelle.
Aucun test ne vérifiait donc que ``gateway.syslog.tls_context()`` (ssl.SSLContext réel,
``verify_mode = ssl.CERT_REQUIRED``, ``load_verify_locations(client_ca)``) rejette
effectivement un certificat non signé par l'AC de confiance, ou une connexion sans
certificat — par opposition au simple enregistrement déclaratif d'une empreinte en
base. L'audit a explicitement rappelé : « Ne considère pas l'enregistrement d'une
empreinte comme une preuve de fonctionnement mTLS. »

Portée de ces tests : ils ouvrent une vraie connexion TCP/TLS en localhost entre un
serveur construit avec ``tls_context()`` (le code réel de production) et un client
``ssl.SSLContext(PROTOCOL_TLS_CLIENT)``, avec de vrais certificats générés en mémoire
via la bibliothèque ``cryptography`` (aucune clé du dépôt n'est utilisée). Ils
démontrent que :
  1. un certificat client signé par l'AC de confiance est accepté, et son empreinte
     SHA-256 réelle (calculée côté serveur via ``getpeercert(binary_form=True)``) est
     bien celle du certificat présenté ;
  2. un certificat client signé par une AC différente (non chargée dans
     ``client_ca``) fait échouer le handshake ;
  3. une connexion sans certificat client fait échouer le handshake.

Caveat explicite (rappelé par l'utilisateur lors de la planification de F-4) : ces
tests valident le comportement du code ACTUEL (vérification cryptographique réelle à
la poignée de main TLS) ; ils ne valident et ne tranchent en rien le modèle de
confiance A-13 encore en attente d'arbitrage (F-2 : AC dédiée BaolSec vs. certificats
auto-signés approuvés individuellement). Que l'AC de confiance soit, demain, une AC
dédiée ou un faisceau de certificats individuels ne change pas le mécanisme testé ici :
``load_verify_locations`` accepte un fichier contenant un ou plusieurs certificats
PEM, donc ces tests restent valables quel que soit le modèle retenu pour construire ce
fichier.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes as crypto_hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from gateway.syslog import tls_context

pytestmark = pytest.mark.asyncio


# ── Génération de certificats en mémoire (aucune clé du dépôt n'est utilisée) ──────

def _generate_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_pem_cert(cert: x509.Certificate, path) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _write_pem_key(key, path) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


def _make_ca(cn: str):
    key = _generate_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, crypto_hashes.SHA256())
    )
    return key, cert


def _make_leaf(cn: str, signer_key, signer_cert):
    """Certificat feuille signé par (signer_key, signer_cert) — AC ou auto-signature."""
    key = _generate_key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(signer_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(signer_key, crypto_hashes.SHA256())
    )
    return key, cert


def _der_fingerprint(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


# ── Harnais : serveur TLS réel construit avec le code de production ───────────────

async def _try_handshake(server_cert_path, server_key_path, client_ca_path,
                          client_cert_path=None, client_key_path=None):
    """Monte un vrai serveur TCP/TLS avec ``gateway.syslog.tls_context`` (code de
    production, inchangé), tente une connexion client réelle, et renvoie un résumé :
    {"accepted": bool, "fingerprint": str|None, "error": str|None}.
    ``accepted`` reflète qu'une poignée de main TLS complète a eu lieu ET que le
    serveur a bien reçu une requête post-handshake (pas seulement un TCP connect)."""
    server_ctx = tls_context(server_cert_path, server_key_path, client_ca_path)
    accepted = asyncio.Event()
    fingerprint: dict[str, str | None] = {"value": None}

    async def handle(reader, writer):
        ssl_obj = writer.get_extra_info("ssl_object")
        der = ssl_obj.getpeercert(binary_form=True) if ssl_obj else None
        fingerprint["value"] = hashlib.sha256(der).hexdigest() if der else None
        accepted.set()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_ctx)
    port = server.sockets[0].getsockname()[1]

    client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE   # seule la vérification du certificat CLIENT est testée ici
    if client_cert_path is not None:
        client_ctx.load_cert_chain(client_cert_path, client_key_path)

    error: str | None = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port, ssl=client_ctx), timeout=5.0,
        )
        try:
            # Le rejet d'un certificat client (ou son absence) par le serveur peut ne se
            # manifester, selon la version TLS et le comportement d'asyncio, qu'au premier
            # échange applicatif après la poignée de main plutôt que sur open_connection()
            # lui-même : on force donc un aller-retour avant de conclure à une acceptation.
            writer.write(b"test\n")
            await asyncio.wait_for(writer.drain(), timeout=2.0)
            await asyncio.wait_for(accepted.wait(), timeout=2.0)
        except (ssl.SSLError, ConnectionError, OSError, asyncio.TimeoutError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    except (ssl.SSLError, ConnectionError, OSError, asyncio.TimeoutError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        server.close()
        await server.wait_closed()

    return {"accepted": accepted.is_set(), "fingerprint": fingerprint["value"], "error": error}


# ── Tests ──────────────────────────────────────────────────────────────────────────

async def test_handshake_accepte_certificat_signe_par_ac_de_confiance(tmp_path):
    """Cas nominal : un certificat client signé par l'AC chargée dans ``client_ca``
    est accepté, et l'empreinte SHA-256 vue côté serveur (calculée depuis le DER réel
    obtenu par ``getpeercert(binary_form=True)``, exactement comme le fait
    ``peer_fingerprint()`` en production) correspond bien à celle du certificat
    présenté — et non à une valeur arbitraire comme dans les tests existants basés
    sur _FakeSSLObject."""
    ca_key, ca_cert = _make_ca("AC de confiance (test)")
    server_key, server_cert = _make_leaf("gateway-test", ca_key, ca_cert)   # auto-signature acceptable : non vérifiée côté client
    client_key, client_cert = _make_leaf("source-legitime", ca_key, ca_cert)

    ca_path = tmp_path / "client-ca.pem"
    _write_pem_cert(ca_cert, ca_path)
    server_cert_path = tmp_path / "server.pem"
    _write_pem_cert(server_cert, server_cert_path)
    server_key_path = tmp_path / "server.key"
    _write_pem_key(server_key, server_key_path)
    client_cert_path = tmp_path / "client.pem"
    _write_pem_cert(client_cert, client_cert_path)
    client_key_path = tmp_path / "client.key"
    _write_pem_key(client_key, client_key_path)

    result = await _try_handshake(
        server_cert_path, server_key_path, ca_path,
        client_cert_path=client_cert_path, client_key_path=client_key_path,
    )

    assert result["error"] is None, f"le handshake aurait dû réussir : {result['error']}"
    assert result["accepted"] is True
    assert result["fingerprint"] == _der_fingerprint(client_cert), (
        "l'empreinte vue côté serveur doit être celle, réelle, du certificat client présenté"
    )


async def test_handshake_rejette_certificat_non_signe_par_ac_de_confiance(tmp_path):
    """Un certificat client cryptographiquement valide mais signé par une AUTRE AC
    (non chargée dans ``client_ca``) doit faire échouer le handshake TLS lui-même —
    pas seulement produire une empreinte absente du référentiel applicatif. C'est la
    vérification que l'audit a explicitement demandé de ne pas supposer acquise."""
    ca_key, ca_cert = _make_ca("AC de confiance (test)")
    rogue_ca_key, rogue_ca_cert = _make_ca("AC usurpatrice (hors confiance)")
    server_key, server_cert = _make_leaf("gateway-test", ca_key, ca_cert)
    rogue_key, rogue_cert = _make_leaf("source-usurpatrice", rogue_ca_key, rogue_ca_cert)

    ca_path = tmp_path / "client-ca.pem"
    _write_pem_cert(ca_cert, ca_path)       # seule l'AC légitime est chargée comme AC de confiance
    server_cert_path = tmp_path / "server.pem"
    _write_pem_cert(server_cert, server_cert_path)
    server_key_path = tmp_path / "server.key"
    _write_pem_key(server_key, server_key_path)
    rogue_cert_path = tmp_path / "rogue.pem"
    _write_pem_cert(rogue_cert, rogue_cert_path)
    rogue_key_path = tmp_path / "rogue.key"
    _write_pem_key(rogue_key, rogue_key_path)

    result = await _try_handshake(
        server_cert_path, server_key_path, ca_path,
        client_cert_path=rogue_cert_path, client_key_path=rogue_key_path,
    )

    assert result["accepted"] is False, (
        "un certificat signé par une AC non approuvée ne doit jamais compléter le handshake"
    )
    assert result["error"] is not None


async def test_handshake_rejette_absence_de_certificat_client(tmp_path):
    """``ssl.CERT_REQUIRED`` côté serveur (tls_context) doit refuser toute connexion
    où le client ne présente aucun certificat — cas d'un émetteur mal configuré ou
    d'une tentative de connexion directe sans authentification mTLS."""
    ca_key, ca_cert = _make_ca("AC de confiance (test)")
    server_key, server_cert = _make_leaf("gateway-test", ca_key, ca_cert)

    ca_path = tmp_path / "client-ca.pem"
    _write_pem_cert(ca_cert, ca_path)
    server_cert_path = tmp_path / "server.pem"
    _write_pem_cert(server_cert, server_cert_path)
    server_key_path = tmp_path / "server.key"
    _write_pem_key(server_key, server_key_path)

    result = await _try_handshake(server_cert_path, server_key_path, ca_path)   # pas de certificat client

    assert result["accepted"] is False
    assert result["error"] is not None
