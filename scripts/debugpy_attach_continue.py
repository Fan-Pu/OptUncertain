#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import time


def _send(sock: socket.socket, seq: int, command: str, arguments=None) -> int:
    body = {
        "seq": seq,
        "type": "request",
        "command": command,
        "arguments": arguments or {},
    }
    payload = json.dumps(body).encode("utf-8")
    sock.sendall(
        b"Content-Length: "
        + str(len(payload)).encode("ascii")
        + b"\r\n\r\n"
        + payload
    )
    print("sent %s" % command, flush=True)
    return seq + 1


def _read_one(sock: socket.socket, buffer: bytes) -> tuple[dict, bytes]:
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("debugpy socket closed while reading header")
        buffer += chunk
    header, buffer = buffer.split(b"\r\n\r\n", 1)
    length = None
    for line in header.decode("ascii", "replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length is None:
        raise RuntimeError("debugpy message missing Content-Length")

    while len(buffer) < length:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("debugpy socket closed while reading body")
        buffer += chunk
    body, buffer = buffer[:length], buffer[length:]
    text = body.decode("utf-8", "replace")
    print(text, flush=True)
    return json.loads(text), buffer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5678)
    parser.add_argument("--connect-timeout", type=float, default=120.0)
    args = parser.parse_args()

    deadline = time.monotonic() + args.connect_timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            sock = socket.create_connection((args.host, args.port), timeout=10.0)
            break
        except OSError as exc:
            last_error = exc
            time.sleep(1.0)
    else:
        raise RuntimeError("could not connect to debugpy: %s" % last_error)

    with sock:
        sock.settimeout(None)
        print("connected to debugpy", flush=True)
        seq = 1
        buffer = b""
        seq = _send(
            sock,
            seq,
            "initialize",
            {
                "clientID": "codex",
                "clientName": "Codex",
                "adapterID": "python",
                "pathFormat": "path",
                "linesStartAt1": True,
                "columnsStartAt1": True,
                "supportsVariableType": True,
                "supportsVariablePaging": True,
                "supportsRunInTerminalRequest": False,
            },
        )
        while True:
            message, buffer = _read_one(sock, buffer)
            if (
                message.get("type") == "response"
                and message.get("command") == "initialize"
            ):
                break

        seq = _send(
            sock,
            seq,
            "attach",
            {
                "name": "Codex attach",
                "type": "python",
                "request": "attach",
                "connect": {"host": args.host, "port": args.port},
                "justMyCode": False,
            },
        )
        while True:
            message, buffer = _read_one(sock, buffer)
            if message.get("type") == "event" and message.get("event") == "initialized":
                break

        _send(sock, seq, "configurationDone")
        while True:
            _message, buffer = _read_one(sock, buffer)


if __name__ == "__main__":
    raise SystemExit(main())
