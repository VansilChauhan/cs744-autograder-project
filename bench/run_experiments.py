"""Driver for all four experiments. Run as:

    python3 run_experiments.py A
    python3 run_experiments.py B
    python3 run_experiments.py CD
    python3 run_experiments.py all

Writes per-experiment CSVs to ../results/raw/ and prints a progress line per
data point so long runs can be monitored.
"""
import csv
import os
import random
import re
import sys
import time

from harness import Server, run_load, summarize, find_free_port

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_RAW = os.path.join(REPO_ROOT, "results", "raw")
os.makedirs(RESULTS_RAW, exist_ok=True)

FILES = [os.path.join(REPO_ROOT, f"program_{i}.c") for i in range(1, 5)]

CSV_FIELDS = [
    "config_value", "thread_count", "concurrency", "test_case_count",
    "n_total", "n_ok", "n_fail", "wall_clock_s", "throughput_rps",
    "latency_avg_ms", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
    "latency_max_ms", "server_cpu_pct",
]


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {path}")


def run_one_config(thread_count, test_cases_file, concurrency, total_requests,
                    label, stderr_log=None):
    port = find_free_port()
    stderr_path = os.path.join(RESULTS_RAW, stderr_log) if stderr_log else None
    with Server(port, thread_count, test_cases_file=test_cases_file,
                stderr_path=stderr_path) as server:
        cpu_proc = server.cpu_percent_sample_start()
        t0 = time.time()
        records, wall_s, cpu_pct = run_load(
            "127.0.0.1", port, FILES, total_requests, concurrency, cpu_proc)
        summary = summarize(records, wall_s)
        summary["server_cpu_pct"] = cpu_pct
        print(f"  [{label}] threads={thread_count} conc={concurrency} "
              f"reqs={total_requests} -> throughput={summary['throughput_rps']:.2f} rps, "
              f"p50={summary['latency_p50_ms']:.1f}ms p95={summary['latency_p95_ms']:.1f}ms "
              f"fail={summary['n_fail']} cpu={cpu_pct}% ({time.time()-t0:.1f}s)")
        return summary


def experiment_a():
    """Thread pool size vs throughput/latency, fixed concurrency."""
    print("=== Experiment A: thread_count vs throughput/latency ===")
    concurrency = 50
    total_requests = 200
    thread_counts = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
    rows = []
    for tc in thread_counts:
        s = run_one_config(tc, "test_cases.txt", concurrency, total_requests, "A")
        rows.append({"config_value": tc, "thread_count": tc, "concurrency": concurrency,
                      "test_case_count": 11, **s})
    write_csv(os.path.join(RESULTS_RAW, "experiment_a_threads.csv"), rows)


def experiment_b():
    """Offered load (concurrency) vs throughput/latency, fixed thread pool."""
    print("=== Experiment B: concurrency vs throughput/latency ===")
    thread_count = 256
    total_requests = 200
    concurrencies = [1, 5, 10, 20, 50, 100, 200, 400]
    rows = []
    for c in concurrencies:
        s = run_one_config(thread_count, "test_cases.txt", c, total_requests, "B")
        rows.append({"config_value": c, "thread_count": thread_count, "concurrency": c,
                      "test_case_count": 11, **s})
    write_csv(os.path.join(RESULTS_RAW, "experiment_b_concurrency.csv"), rows)


def gen_test_cases(n, path):
    random.seed(42 + n)
    with open(path, "w") as f:
        for _ in range(n):
            f.write(f"{random.randint(1, 500)}\n")


TIMING_RE = re.compile(
    r"TIMING client=(\d+) compile_ms=([\d.]+) exec_ms=([\d.]+) total_ms=([\d.]+) test_cases=(\d+)")


def parse_timing_log(path):
    out = []
    with open(path) as f:
        for line in f:
            m = TIMING_RE.search(line)
            if m:
                out.append({
                    "client": int(m.group(1)),
                    "compile_ms": float(m.group(2)),
                    "exec_ms": float(m.group(3)),
                    "total_ms": float(m.group(4)),
                    "test_cases": int(m.group(5)),
                })
    return out


def experiment_c_and_d():
    """C: test-case count vs per-submission latency (client-observed).
    D: reuses the same runs' server-side stderr TIMING logs to split
    each submission's time into compile vs execution phases."""
    print("=== Experiment C+D: test_case_count vs latency, and compile/exec split ===")
    thread_count = 64
    concurrency = 20
    total_requests = 100
    counts = [5, 10, 20, 50, 100]
    rows_c = []
    rows_d = []
    tc_dir = os.path.join(RESULTS_RAW, "tc_files")
    os.makedirs(tc_dir, exist_ok=True)
    for n in counts:
        tc_path = os.path.join(tc_dir, f"test_cases_{n}.txt")
        gen_test_cases(n, tc_path)
        stderr_log = f"server_stderr_c_{n}.log"
        s = run_one_config(thread_count, tc_path, concurrency, total_requests,
                            "C", stderr_log=stderr_log)
        rows_c.append({"config_value": n, "thread_count": thread_count,
                        "concurrency": concurrency, "test_case_count": n, **s})

        timings = parse_timing_log(os.path.join(RESULTS_RAW, stderr_log))
        if timings:
            avg_compile = sum(t["compile_ms"] for t in timings) / len(timings)
            avg_exec = sum(t["exec_ms"] for t in timings) / len(timings)
            avg_total = sum(t["total_ms"] for t in timings) / len(timings)
            rows_d.append({"test_case_count": n, "n_samples": len(timings),
                            "avg_compile_ms": avg_compile, "avg_exec_ms": avg_exec,
                            "avg_total_ms": avg_total})
            print(f"  [D] test_cases={n} avg_compile_ms={avg_compile:.2f} "
                  f"avg_exec_ms={avg_exec:.2f} (n={len(timings)})")

    write_csv(os.path.join(RESULTS_RAW, "experiment_c_testcases.csv"), rows_c)

    d_path = os.path.join(RESULTS_RAW, "experiment_d_compile_vs_exec.csv")
    with open(d_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["test_case_count", "n_samples", "avg_compile_ms",
                                           "avg_exec_ms", "avg_total_ms"])
        w.writeheader()
        for r in rows_d:
            w.writerow(r)
    print(f"wrote {d_path}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("A", "all"):
        experiment_a()
    if which in ("B", "all"):
        experiment_b()
    if which in ("CD", "all"):
        experiment_c_and_d()
    print("done")
