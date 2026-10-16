"""When the proxy's HTTPS certificate runs out, read from a TLS handshake.

Only the validity dates are read, straight from the certificate's DER bytes, so no X.509
library is needed. The certificate isn't trusted or checked for anything else.
"""

import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Validity:
    not_before: datetime
    not_after: datetime


def _element(der: bytes, at: int) -> tuple[int, int, int]:
    """The DER element at `at`: its tag, where its content starts and where it ends."""
    tag, first = der[at], der[at + 1]
    if first < 0x80:
        start, length = at + 2, first
    else:
        count = first & 0x7F
        start, length = at + 2 + count, int.from_bytes(der[at + 2 : at + 2 + count])
    if start + length > len(der):
        raise ValueError("the certificate is cut short")
    return tag, start, start + length


def _time(der: bytes, at: int) -> tuple[datetime, int]:
    tag, start, end = _element(der, at)
    raw = der[start:end].decode("ascii")
    if tag == 0x17:  # UTCTime, two-digit year: 50 to 99 is 19xx (RFC 5280 §4.1.2.5.1)
        year = int(raw[:2])
        raw = f"{19 if year >= 50 else 20}{raw}"
    elif tag != 0x18:  # GeneralizedTime
        raise ValueError("the certificate's validity isn't a time")
    return datetime.strptime(raw, "%Y%m%d%H%M%SZ").replace(tzinfo=UTC), end


def validity(der: bytes) -> Validity:
    """notBefore and notAfter from a DER certificate."""
    try:
        _, at, _ = _element(der, 0)  # Certificate
        _, at, end = _element(der, at)  # TBSCertificate
        fields = []
        while at < end and len(fields) < 5:
            tag, _, next_at = _element(der, at)
            if not fields and tag == 0xA0:  # the optional [0] version comes first
                at = next_at
                continue
            fields.append(at)
            at = next_at
        # serialNumber, signature, issuer, validity
        _, at, _ = _element(der, fields[3])
        not_before, at = _time(der, at)
        not_after, _ = _time(der, at)
    except (IndexError, UnicodeDecodeError) as e:
        raise ValueError("not a certificate") from e
    return Validity(not_before, not_after)


def fetch_validity(address: str, server_name: str | None, timeout: float = 3.0) -> Validity:
    """Connect to `host[:port]` (port 443 by default) and read its certificate's dates."""
    host, colon, port = address.rpartition(":")
    if not colon or not port.isdigit():
        host, port = address, "443"
    context = ssl.create_default_context()
    # Reading the dates only: a certificate signed by the proxy's own CA must still be read.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with (
        socket.create_connection((host, int(port)), timeout=timeout) as raw,
        context.wrap_socket(raw, server_hostname=server_name or host) as tls,
    ):
        der = tls.getpeercert(binary_form=True)
    if not der:
        raise ValueError("the server sent no certificate")
    return validity(der)
