"""Jail for the detonation child: network, processes and secret files (stdlib, PEP 578).

- DNS: only the allowed hosts resolve. Connections: only to IPs those lookups returned.
- No new processes. No reads of `.env` or `secrets/`.
Every blocked attempt calls `on_block(kind, target)` (it becomes evidence) and raises.
shortcut: audit hooks stop Python code, not hostile native code. Our agents run no code (their
only actions are tool calls), so this is enough here; an agent that runs code needs a container.
"""

import socket
import sys
from pathlib import Path

PROCESS_EVENTS = {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "os.exec",
                  "os.startfile"}


def install(allowed_hosts, on_block):
    allowed_ips = set()
    real_getaddrinfo = socket.getaddrinfo

    def blocked(kind, target):
        on_block(kind, target)
        raise PermissionError(f"Mirage sandbox: {kind} to {target} is blocked")

    def getaddrinfo(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else str(host)
        if name not in allowed_hosts:
            blocked("dns", name)
        found = real_getaddrinfo(host, *args, **kwargs)
        allowed_ips.update(info[4][0] for info in found)
        return found

    def hook(event, args):
        if event == "socket.connect":
            address = args[1]
            ip = address[0] if isinstance(address, tuple) else str(address)
            if ip not in allowed_ips:
                blocked("connect", ip)
        elif event in PROCESS_EVENTS:
            blocked("process", str(args[0])[:200])
        elif event == "open" and isinstance(args[0], (str, bytes, Path)):
            path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0])
            if path.name == ".env" or "secrets" in path.parts:
                blocked("file", str(path))

    socket.getaddrinfo = getaddrinfo
    sys.addaudithook(hook)  # cannot be removed for the life of the process
