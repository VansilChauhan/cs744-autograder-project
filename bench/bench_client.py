"""Socket-level client that mimics client.c's wire protocol, with timing.

Deliberately reimplements the protocol (connect -> stream file bytes ->
shutdown(SHUT_WR) -> recv result) instead of shelling out to client.o, so
that experiment concurrency/timing isn't confounded by process-spawn
overhead on the measuring side.
"""
import socket
import time

BUF_SIZE = 1024
RECV_TIMEOUT_S = 30.0


def submit(host, port, filepath):
    """Submit one file to the grading server. Returns a dict record."""
    t_start = time.perf_counter()
    ok = False
    result = None
    error = None
    try:
        with socket.create_connection((host, port), timeout=RECV_TIMEOUT_S) as sock:
            sock.settimeout(RECV_TIMEOUT_S)
            with open(filepath, "rb") as f:
                data = f.read()
            sock.sendall(data)
            sock.shutdown(socket.SHUT_WR)

            chunks = []
            while True:
                chunk = sock.recv(BUF_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
            result = b"".join(chunks).decode(errors="replace")
            ok = True
    except Exception as e:  # noqa: BLE001 - benchmark harness, record and move on
        error = str(e)
    t_end = time.perf_counter()
    return {
        "latency_ms": (t_end - t_start) * 1000.0,
        "success": ok,
        "result": result,
        "error": error,
        "t_start": t_start,
        "t_end": t_end,
    }
