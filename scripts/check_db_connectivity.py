"""
Find out why the platform cannot reach its database, and say which layer failed.

Run it with no arguments:

    python scripts/check_db_connectivity.py

It walks the connection outwards -- DNS, TCP, the PostgreSQL TLS negotiation,
then a real login -- and stops at the first step that fails, naming that step.
The point is to tell a network problem apart from a credentials problem, because
the two produce similar-looking errors and are fixed in completely different
places.

Why this exists
---------------
On the development machine every step passed except the TLS handshake: the
server answered the SSLRequest with 'S', meaning it was willing to encrypt, and
the connection was then reset the instant the TLS ClientHello went out. TLS to
the same machine on ports 443, 993 and 465 worked, and Supabase's own logs
recorded no failed handshakes, so nothing was wrong at either end -- something
between them was resetting encrypted traffic on the database port.

That is not fixable in this repository. The useful next step is to run this on a
different network -- a phone hotspot is the quickest -- because a pass there
identifies the network as the cause beyond argument.

Never "fix" a failure here by removing sslmode from DATABASE_URL. That does not
repair the connection, it removes the encryption, and the password and every
patient-derived record would then cross the network in clear text.
"""

from __future__ import annotations

import os
import socket
import ssl
import struct
import sys
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import settings  # noqa: E402

#: The PostgreSQL SSLRequest: an 8-byte packet carrying the magic 80877103.
#: The server replies with a single byte -- 'S' to proceed with TLS, 'N' to
#: refuse. TLS starts only after that exchange, which is why pointing a plain
#: TLS client at port 5432 reports a version error rather than anything useful.
SSL_REQUEST = struct.pack("!ii", 8, 80877103)

OK, FAIL, WARN = "  ok  ", " FAIL ", " warn "


def _say(status: str, step: str, detail: str = "") -> None:
    print(f"[{status}] {step}" + (f" -- {detail}" if detail else ""))


def main() -> int:
    url = settings.get_setting("DATABASE_URL")
    if not url:
        _say(FAIL, "configuration",
             "DATABASE_URL is not set. Put it in .env at the project root.")
        return 1

    parsed = urlparse(url)
    host, port = parsed.hostname, parsed.port or 5432
    if not host:
        _say(FAIL, "configuration", "DATABASE_URL has no host in it.")
        return 1
    print(f"Target: {host}:{port}\n")

    # -- 1. DNS ------------------------------------------------------------
    try:
        addresses = sorted({i[4][0] for i in socket.getaddrinfo(
            host, port, proto=socket.IPPROTO_TCP)})
        _say(OK, "DNS", ", ".join(addresses))
    except Exception as exc:
        _say(FAIL, "DNS", f"{host} does not resolve ({exc}). Check the "
                          "hostname, or that you have a working connection.")
        return 1

    # -- 2. TCP ------------------------------------------------------------
    reachable = []
    for address in addresses:
        sock = socket.socket()
        sock.settimeout(15)
        try:
            sock.connect((address, port))
            reachable.append(address)
        except Exception as exc:
            _say(WARN, f"TCP {address}:{port}", str(exc)[:80])
        finally:
            sock.close()
    if not reachable:
        _say(FAIL, "TCP", "nothing accepted a connection on this port. The "
                          "port is blocked outbound, or the host is down.")
        return 1
    _say(OK, "TCP", f"{len(reachable)} of {len(addresses)} address(es) accepted")

    # -- 3. TLS negotiation ------------------------------------------------
    address = reachable[0]
    sock = socket.socket()
    sock.settimeout(20)
    try:
        sock.connect((address, port))
        sock.sendall(SSL_REQUEST)
        reply = sock.recv(1)
    except Exception as exc:
        _say(FAIL, "SSLRequest", str(exc)[:100])
        sock.close()
        return 1

    if reply == b"N":
        _say(FAIL, "SSLRequest",
             "the server refused encryption. Supabase always supports TLS, so "
             "something is answering on its behalf. Do not disable sslmode.")
        sock.close()
        return 1
    if reply != b"S":
        _say(FAIL, "SSLRequest", f"unexpected reply {reply!r}")
        sock.close()
        return 1
    _say(OK, "SSLRequest", "server is willing to encrypt")

    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        wrapped = context.wrap_socket(sock, server_hostname=host)
        _say(OK, "TLS handshake", f"{wrapped.version()}, {wrapped.cipher()[0]}")
        wrapped.close()
    except ConnectionResetError:
        _say(FAIL, "TLS handshake",
             "reset while negotiating. The server offered TLS and the "
             "connection died as encryption began -- the signature of a "
             "firewall, antivirus or ISP resetting encrypted traffic on this "
             "port. Re-run on a phone hotspot: if it passes there, the network "
             "is the cause.")
        return 1
    except Exception as exc:
        _say(FAIL, "TLS handshake", f"{type(exc).__name__}: {str(exc)[:90]}")
        return 1
    finally:
        sock.close()

    # -- 4. A real login ---------------------------------------------------
    try:
        from src import db
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT current_database(), current_user")
        row = cursor.fetchone()
        connection.close()
        _say(OK, "login", str(dict(row) if hasattr(row, "keys") else row))
    except Exception as exc:
        _say(FAIL, "login",
             f"the network is fine but the database refused the session: "
             f"{str(exc)[:120]}")
        return 1

    print("\nEvery step passed. The platform can reach its database from here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
