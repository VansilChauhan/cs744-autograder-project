"""Render experiment CSVs (results/raw/*.csv) into labeled PNG charts
(results/plots/*.png) using the validated reference palette."""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO_ROOT, "results", "raw")
PLOTS = os.path.join(REPO_ROOT, "results", "plots")
os.makedirs(PLOTS, exist_ok=True)

# Reference palette (light mode) — see dataviz skill references/palette.md
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": SECONDARY_INK,
    "ytick.color": SECONDARY_INK,
    "grid.color": GRID,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
})


def style_axes(ax):
    ax.grid(True, axis="y", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(MUTED)


def savefig(fig, name):
    path = os.path.join(PLOTS, name)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print(f"wrote {path}")


def plot_a():
    df = pd.read_csv(os.path.join(RAW, "experiment_a_threads.csv")).sort_values("thread_count")
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(df["thread_count"], df["throughput_rps"], marker="o", color=BLUE, linewidth=2,
            markersize=6, label="Throughput")
    ax.set_xscale("log", base=2)
    ax.set_xticks(df["thread_count"])
    ax.get_xaxis().set_major_formatter(mticker.ScalarFormatter())
    ax.axvline(8, color=MUTED, linestyle="--", linewidth=1)
    ax.text(8, ax.get_ylim()[1]*0.02, " 8 cores", color=MUTED, fontsize=9, va="bottom")
    ax.set_xlabel("Server thread pool size (threads, log2 scale)")
    ax.set_ylabel("Throughput (submissions/sec)")
    ax.set_title("Experiment A — Throughput vs. thread pool size\n(fixed 50 concurrent clients, 200 submissions/config)")
    style_axes(ax)
    savefig(fig, "experiment_a_throughput.png")

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(df["thread_count"], df["latency_p50_ms"], marker="o", color=BLUE, linewidth=2, label="p50")
    ax.plot(df["thread_count"], df["latency_p95_ms"], marker="s", color=ORANGE, linewidth=2, label="p95")
    ax.plot(df["thread_count"], df["latency_p99_ms"], marker="^", color=AQUA, linewidth=2, label="p99")
    ax.set_xscale("log", base=2)
    ax.set_xticks(df["thread_count"])
    ax.get_xaxis().set_major_formatter(mticker.ScalarFormatter())
    ax.axvline(8, color=MUTED, linestyle="--", linewidth=1)
    ax.set_xlabel("Server thread pool size (threads, log2 scale)")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Experiment A — Submission latency vs. thread pool size\n(fixed 50 concurrent clients, 200 submissions/config)")
    ax.legend(frameon=False)
    style_axes(ax)
    savefig(fig, "experiment_a_latency.png")


def plot_b():
    df = pd.read_csv(os.path.join(RAW, "experiment_b_concurrency.csv")).sort_values("concurrency")
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(df["concurrency"], df["throughput_rps"], marker="o", color=BLUE, linewidth=2, markersize=6)
    ax.set_xscale("log", base=2)
    ax.set_xticks(df["concurrency"])
    ax.get_xaxis().set_major_formatter(mticker.ScalarFormatter())
    ax.set_xlabel("Concurrent clients (offered load, log2 scale)")
    ax.set_ylabel("Throughput (submissions/sec)")
    ax.set_title("Experiment B — Throughput vs. offered load\n(fixed 256-thread pool, 200 submissions/config)")
    style_axes(ax)
    savefig(fig, "experiment_b_throughput.png")

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(df["concurrency"], df["latency_p50_ms"], marker="o", color=BLUE, linewidth=2, label="p50")
    ax.plot(df["concurrency"], df["latency_p95_ms"], marker="s", color=ORANGE, linewidth=2, label="p95")
    ax.plot(df["concurrency"], df["latency_p99_ms"], marker="^", color=AQUA, linewidth=2, label="p99")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(df["concurrency"])
    ax.get_xaxis().set_major_formatter(mticker.ScalarFormatter())
    ax.set_xlabel("Concurrent clients (offered load, log2 scale)")
    ax.set_ylabel("Latency (ms, log scale)")
    ax.set_title("Experiment B — Submission latency vs. offered load\n(fixed 256-thread pool, 200 submissions/config)")
    ax.legend(frameon=False)
    style_axes(ax)
    savefig(fig, "experiment_b_latency.png")


def plot_c():
    df = pd.read_csv(os.path.join(RAW, "experiment_c_testcases.csv")).sort_values("test_case_count")
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(df["test_case_count"], df["latency_avg_ms"], marker="o", color=BLUE, linewidth=2, label="avg")
    ax.plot(df["test_case_count"], df["latency_p95_ms"], marker="s", color=ORANGE, linewidth=2, label="p95")
    ax.set_xlabel("Test cases per submission (count)")
    ax.set_ylabel("Per-submission latency (ms)")
    ax.set_title("Experiment C — Latency vs. number of test cases\n(64 threads, 20 concurrent clients, 100 submissions/config)")
    ax.legend(frameon=False)
    style_axes(ax)
    savefig(fig, "experiment_c_latency.png")


def plot_d():
    df = pd.read_csv(os.path.join(RAW, "experiment_d_compile_vs_exec.csv")).sort_values("test_case_count")
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    width = 0.6
    x = df["test_case_count"].astype(str)
    ax.bar(x, df["avg_compile_ms"], width, color=BLUE, label="Compile (gcc)")
    ax.bar(x, df["avg_exec_ms"], width, bottom=df["avg_compile_ms"], color=ORANGE, label="Execute test cases")
    ax.set_xlabel("Test cases per submission (count)")
    ax.set_ylabel("Server-side time per submission (ms)")
    ax.set_title("Experiment D — Compile vs. execution time breakdown\n(server-side timing, same runs as Experiment C)")
    ax.legend(frameon=False)
    style_axes(ax)
    savefig(fig, "experiment_d_breakdown.png")


if __name__ == "__main__":
    plot_a()
    plot_b()
    plot_c()
    plot_d()
