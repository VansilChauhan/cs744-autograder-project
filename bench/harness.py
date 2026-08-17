"""Server lifecycle management + concurrent load generation for experiments."""
import os
import socket
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import psutil

from bench_client import submit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_BIN = os.path.join(REPO_ROOT, "server.o")


class Server:
    def __init__(self, port, thread_count, solution_file="solution.c",
                 test_cases_file="test_cases.txt", stderr_path=None):
        self.port = port
        self.thread_count = thread_count
        self.solution_file = solution_file
        self.test_cases_file = test_cases_file
        self.stderr_path = stderr_path
        self.proc = None
        self._stderr_f = None

    def __enter__(self):
        self._stderr_f = open(self.stderr_path, "w") if self.stderr_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            [SERVER_BIN, str(self.port), str(self.thread_count),
             self.solution_file, self.test_cases_file],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=self._stderr_f,
        )
        self._wait_ready()
        return self

    def _wait_ready(self, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError(f"server did not come up on port {self.port} within {timeout}s")

    def cpu_percent_sample_start(self):
        """Return a psutil.Process handle with cpu_percent() primed (call before load)."""
        p = psutil.Process(self.proc.pid)
        p.cpu_percent(interval=None)  # prime
        return p

    def __exit__(self, exc_type, exc, tb):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self._stderr_f not in (None, subprocess.DEVNULL):
            self._stderr_f.close()
        # clean up any leftover per-submission temp files
        for fn in os.listdir(REPO_ROOT):
            if fn.startswith("student_program_"):
                try:
                    os.remove(os.path.join(REPO_ROOT, fn))
                except OSError:
                    pass


def run_load(host, port, files, total_requests, concurrency, cpu_process=None):
    """Fire total_requests submissions (cycling through `files`) at `concurrency`
    concurrent in-flight requests. Returns (records, wall_clock_s, cpu_percent)."""
    records = [None] * total_requests
    wall_start = time.perf_counter()

    def _one(i):
        f = files[i % len(files)]
        records[i] = submit(host, port, f)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(_one, range(total_requests)))

    wall_end = time.perf_counter()
    cpu_pct = cpu_process.cpu_percent(interval=None) if cpu_process else None
    return records, (wall_end - wall_start), cpu_pct


def summarize(records, wall_clock_s):
    lat = sorted(r["latency_ms"] for r in records if r["success"])
    n_ok = len(lat)
    n_total = len(records)
    def pct(p):
        if not lat:
            return float("nan")
        idx = min(len(lat) - 1, int(len(lat) * p))
        return lat[idx]
    return {
        "n_total": n_total,
        "n_ok": n_ok,
        "n_fail": n_total - n_ok,
        "wall_clock_s": wall_clock_s,
        "throughput_rps": n_total / wall_clock_s if wall_clock_s > 0 else float("nan"),
        "latency_avg_ms": sum(lat) / len(lat) if lat else float("nan"),
        "latency_p50_ms": pct(0.50),
        "latency_p95_ms": pct(0.95),
        "latency_p99_ms": pct(0.99),
        "latency_max_ms": lat[-1] if lat else float("nan"),
    }


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
