"""Local sandbox for evaluating a CANDIDATE strategy (Day 6 Step 19). Two guarantees, both tested (tests/test_candidate_sandbox.py):
1. scrub_environment(): every environment variable that could carry a credential (Telegram token / chat id, database URLs, sync secrets, API keys,
   passwords) is REMOVED from the process before anything else is imported, so the candidate run has no way to authenticate to Cloud, Neon or Telegram.
   Only the NAMES of removed variables are returned; values are never read into any output.
2. lock_network(): every outgoing connection to a non-loopback address raises SandboxNetworkError (socket.connect, connect_ex, create_connection and
   non-local name lookups), so even a code path that tried to reach Cloud or api.telegram.org would fail instead of sending anything.
The evaluation reads only the local dataset and writes only into its own candidate folder."""
import os
import socket

SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "DATABASE_URL", "DB_URL", "NEON", "CHAT_ID", "CREDENTIAL", "PRIVATE_KEY")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}


class SandboxNetworkError(OSError):
    pass


def scrub_environment(env=None):
    env = os.environ if env is None else env
    removed = sorted(k for k in list(env) if any(m in k.upper() for m in SECRET_MARKERS))
    for k in removed:
        del env[k]
    env["SINDHU_SANDBOX"] = "1"
    env["SINDHU_CLOUD_SYNC_DISABLED"] = "1"
    return removed


def _is_local(host):
    h = str(host or "").strip("[]").lower()
    return h in LOCAL_HOSTS or h.startswith("127.")


def lock_network():
    """Returns an `unlock()` function (used by tests); production runs never unlock."""
    orig = {"connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex, "create_connection": socket.create_connection,
            "getaddrinfo": socket.getaddrinfo}

    def _addr_host(address):
        return address[0] if isinstance(address, tuple) and address else address

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(_addr_host(address)):
            raise SandboxNetworkError(f"sandbox: outgoing connection to {_addr_host(address)!r} is blocked")
        return orig["connect"](self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(_addr_host(address)):
            raise SandboxNetworkError(f"sandbox: outgoing connection to {_addr_host(address)!r} is blocked")
        return orig["connect_ex"](self, address)

    def create_connection(address, *a, **k):
        if not _is_local(_addr_host(address)):
            raise SandboxNetworkError(f"sandbox: outgoing connection to {_addr_host(address)!r} is blocked")
        return orig["create_connection"](address, *a, **k)

    def getaddrinfo(host, *a, **k):
        if not _is_local(host):
            raise SandboxNetworkError(f"sandbox: name lookup of {host!r} is blocked")
        return orig["getaddrinfo"](host, *a, **k)

    socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = connect, connect_ex, create_connection, getaddrinfo

    def unlock():
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = (
            orig["connect"], orig["connect_ex"], orig["create_connection"], orig["getaddrinfo"])
    return unlock


def active():
    return os.environ.get("SINDHU_SANDBOX") == "1"
