import re
import matplotlib.pyplot as plt
import numpy as np
import tarfile
import tempfile
import yaml
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def artifacts_from_archive(archive: Path):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp)
        artifacts = next(tmp.rglob("artifacts"))
        yield artifacts

COLOR_SCHEME = [ "#2171b5", "#6baed6", "#9ecae1", "#fb6a4a", "#fcae91", "#ba381a" ]
LABEL_PP = {
    "spdk_bdevperf": "bdevperf (SPDK)",
    "spdk_nvme_perf": "nvmeperf (SPDK)",
    "xnvmeperf_spdk": "xnvmeperf (SPDK)",
    "xnvmeperf_upcie": "xnvmeperf (uPCIe, CPU-initiated)",
    "xnvmeperf_upcie_cuda": "xnvmeperf (uPCIe, P2P)",
    "xnvmeperf_cuda": "xnvmeperf (uPCIe, dev-initiated)",
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def mathtt(s: str):
    """Replace backticks with the latex version of monospace formatting"""
    s = s.split("`")
    if len(s) % 2 != 1:
        # if there is not an uneven length, there has not been an even amount of "`" in the original string
        return s

    latex = [r"$\mathtt{", "}$"]
    out = [s[0]]
    for idx in range(1, len(s)):
        out.append(latex[(idx-1) % 2])
        if idx % 2 == 1:
            out.append(s[idx].replace("_", r"\_"))
        else:
            out.append(s[idx])
    return "".join(out)


def setup_figure(cfg):
    labels = [LABEL_PP.get(b["label"], b["label"]) for b in cfg["bars"]]
    fig, ax = plt.subplots(figsize=(8, 5))

    # Subtle horizontal grid
    ax.yaxis.grid(True, color="#e0e0e0", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)

    ax.set_xlabel(cfg["xlabel"], fontsize=10)
    ax.set_ylabel(cfg["ylabel"], fontsize=10)
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.tick_params(axis="y", labelsize=9)

    ax.set_xlim(-0.55, len(labels) - 0.45)

    title_lines = cfg["title"].strip().split("\n")
    main_title = mathtt(title_lines[0])
    subtitle = mathtt("\n".join(title_lines[1:]))

    fig.suptitle(main_title, fontsize=11, fontweight="bold", y=0.97)
    if subtitle.strip():
        fig.text(0.5, 0.92, subtitle, ha="center", va="top", fontsize=9, color="#555555")

    if cfg.get("footnote"):
        footnote = mathtt(cfg["footnote"])
        fig.text(0.99, 0.01, footnote,
                 ha="right", va="bottom", fontsize=7, fontstyle="italic", color="#999999")

    return fig, ax


def barplot_tool(artifacts, output):
    in_file = Path(artifacts) / "barplot-tool.yaml"
    out_file = Path(output) / "barplot-tool.png"

    with open(in_file) as file:
        cfg = yaml.safe_load(file)

    bars = cfg["bars"]
    tools = cfg["tools"]

    scale = 1e6

    n_tools     = len(tools)
    group_width = 0.8
    bar_width   = group_width / n_tools
    offsets     = np.linspace(-group_width / 2 + bar_width / 2,
                               group_width / 2 - bar_width / 2, n_tools)

    fig, ax = setup_figure(cfg)
    x = np.arange(len(bars))
    ax.set_xticks(x)

    # Bars
    for (key, label), offset, color in zip(LABEL_PP.items(), offsets, COLOR_SCHEME):
        values = np.array(
            [b[key] / scale if b.get(key) is not None else float("nan")
             for b in bars]
        )
        rects = ax.bar(x + offset, values, bar_width, label=label,
                       color=color, edgecolor="none", zorder=3)

        # Value labels on each stack segment
        for rect, val in zip(rects, values):
            if not np.isnan(val):
                ax.text(rect.get_x() + rect.get_width() / 2, val / 2,
                        f"{val:.1f}",
                        ha="center", va="center", fontsize=7, color="white", fontweight="bold")

    ax.legend(fontsize=9, framealpha=0.9, edgecolor="#cccccc")

    plt.tight_layout()
    fig.subplots_adjust(top=0.86)
    plt.savefig(out_file, dpi=150)
    plt.close(fig)


def barplot_sat(artifacts, output, unit="GB/s"):
    in_file = Path(artifacts) / "barplot-sat.yaml"
    out_file = Path(output) / "barplot-sat.png"

    scale = 1e9 if unit == "GB/s" else 1024**3

    with open(in_file) as file:
        cfg = yaml.safe_load(file)

    cfg["ylabel"] = cfg["ylabel"].format(bw_unit=unit)
    cfg["title"] = cfg["title"].strip().format(bw_unit=unit)

    # Parse bars
    bars = cfg["bars"]
    labels = [b["label"] for b in bars]
    payload = np.array([b["payload_nbytes"] for b in bars]) / scale
    total = np.array([b["total_nbytes"] for b in bars]) / scale
    overhead = total - payload

    x = np.arange(len(labels))
    width = 0.9

    fig, ax = setup_figure(cfg)

    # Bars
    ax.bar(x, payload, width, label="NVMe Data Payload",
           color=COLOR_SCHEME[0], edgecolor="none", zorder=3)
    ax.bar(x, overhead, width, bottom=payload, label="Observed PCIe BW",
           color=COLOR_SCHEME[1], edgecolor="none", zorder=3)

    # Value labels on each stack segment
    for i in range(len(x)):
        ax.text(x[i], payload[i] / 2, f"{payload[i]:.1f}",
                ha="center", va="center", fontsize=13, color="white", fontweight="bold")
        ax.text(x[i], payload[i] + overhead[i] / 2, f"{overhead[i]:.1f}",
                ha="center", va="center", fontsize=13, color="#08519c", fontweight="bold")
        ax.text(x[i], total[i], f"{total[i]:.1f}",
                ha="center", va="bottom", fontsize=10, fontweight="normal", color="#333333")

    # Rooflines
    ymax = 0
    for r in cfg.get("rooflines", []):
        val = r["value_nbytes"] / scale
        ax.axhline(y=val, color=r["color"], linestyle=r["style"], linewidth=1.5,
                   label=f"{r['name']} ({val:.1f} {unit})", zorder=1)
        ymax = max(ymax, val)
    ax.set_ylim(0, ymax * 1.20)

    # Legends
    handles, labels_ = ax.get_legend_handles_labels()
    line_labels = [r["name"] for r in cfg.get("rooflines", [])]
    line_idx = [i for i, l in enumerate(labels_) if any(l.startswith(n) for n in line_labels)]
    stack_idx = [i for i in range(len(labels_)) if i not in line_idx]

    leg1 = ax.legend([handles[i] for i in line_idx], [labels_[i] for i in line_idx],
                     loc="upper left", fontsize=8, framealpha=0.9, edgecolor="#cccccc")
    ax.add_artist(leg1)

    ax.legend([handles[i] for i in reversed(stack_idx)], [labels_[i] for i in reversed(stack_idx)],
              loc="upper right", fontsize=8, framealpha=0.9, edgecolor="#cccccc")

    plt.tight_layout()
    fig.subplots_adjust(top=0.86)
    plt.savefig(out_file, dpi=150)
    plt.close(fig)


def _sort_groups_numeric(groups):
    """Sort groups by trailing integer if every group name has one."""
    if all(re.search(r'\d+$', g) for g in groups):
        return sorted(groups, key=lambda g: int(re.search(r'(\d+)$', g).group(1)))
    return groups


def _line_colors(n):
    """Return n colors: use COLOR_SCHEME for small n, plasma for larger sets."""
    if n <= len(COLOR_SCHEME):
        return COLOR_SCHEME[:n]
    cmap = plt.cm.plasma
    return [cmap(0.1 + 0.8 * i / (n - 1)) for i in range(n)]


def _fmt_bytes(val):
    n = int(val)
    if n >= 1024 * 1024:
        return f"{n // (1024 * 1024)} MiB"
    elif n >= 1024:
        return f"{n // 1024} KiB"
    return f"{n} B"


def lineplot(artifacts, output, driver, xaxis="ncpus", colormap=None):
    in_file = Path(artifacts) / f"lineplot-{driver}-{xaxis}.yaml"
    out_file = Path(output) / f"lineplot-{driver}-{xaxis}.png"

    with open(in_file) as file:
        cfg = yaml.safe_load(file)

    bars = cfg["bars"]
    if not bars:
        return

    rooflines = cfg.get("rooflines", [])
    if rooflines and "value_nbytes" in rooflines[0]:
        scale = 1e9
        roofline_key = "value_nbytes"
        roofline_label = lambda val: f"{val:.1f} GB/s"
    else:
        scale = 1e6
        roofline_key = "value_iops"
        roofline_label = lambda val: f"{val:.0f}M"

    groups = _sort_groups_numeric(
        [key for key in bars[0].keys() if key != "label" and "_std" not in key]
    )
    if colormap:
        cmap = plt.cm.get_cmap(colormap)
        n = len(groups)
        colors = [cmap(0.1 + 0.8 * i / (n - 1)) for i in range(n)]
    else:
        colors = _line_colors(len(groups))

    fig, ax = setup_figure(cfg)

    x = np.arange(len(bars))
    ax.set_xticks(x)
    ax.set_xlim(x[0] - 0.5, x[-1] + 0.5)

    if "size" in cfg.get("xlabel", "").lower():
        try:
            ax.set_xticklabels([_fmt_bytes(b["label"]) for b in bars], fontsize=9)
        except (ValueError, TypeError):
            pass

    for group, color in zip(groups, colors):
        data = np.array([b[group] for b in bars], dtype=float) / scale
        std = np.array([b[f"{group}_std"] for b in bars], dtype=float) / scale
        label = group.replace("_", " ")

        ax.fill_between(x, data - std, data + std, alpha=0.15, color=color)
        ax.plot(x, data, color=color, linewidth=2, marker="o", markersize=4,
                label=label)

    # Rooflines
    ymax = 0
    for r in rooflines:
        val = r[roofline_key] / scale
        ax.axhline(y=val, color=r["color"], linestyle=r["style"], linewidth=1.5,
                label=f"{r['name']} ({roofline_label(val)})", zorder=1)
        ymax = max(ymax, val)
    ax.set_ylim(0, ymax * 1.15)

    # Legends
    handles, labels_ = ax.get_legend_handles_labels()
    line_labels = [r["name"] for r in cfg.get("rooflines", [])]
    line_idx = [i for i, l in enumerate(labels_) if any(l.startswith(n) for n in line_labels)]
    stack_idx = [i for i in range(len(labels_)) if i not in line_idx]

    leg1 = ax.legend([handles[i] for i in line_idx], [labels_[i] for i in line_idx],
                     loc="lower left", fontsize=8, framealpha=0.9, edgecolor="#cccccc")
    ax.add_artist(leg1)

    ax.legend([handles[i] for i in reversed(stack_idx)], [labels_[i] for i in reversed(stack_idx)],
              loc="lower right", fontsize=8, framealpha=0.9, edgecolor="#cccccc")

    plt.tight_layout()
    fig.subplots_adjust(top=0.83)
    plt.savefig(out_file, dpi=150)
    plt.close(fig)
