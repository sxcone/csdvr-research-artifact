from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.colors import LinearSegmentedColormap


BASE = Path(__file__).resolve().parent
FIG_DIR = BASE / "figures"
FIG_DIR.mkdir(exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.7,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "figure.dpi": 160,
        "savefig.dpi": 400,
    }
)

PALETTE = {
    "NoCheck": "#8C8C8C",
    "FinalVerifier": "#6C8EBF",
    "StepVerifier": "#9E77B5",
    "ReflectionRetry": "#D99A5B",
    "C-SDVR-NoRollback": "#75A478",
    "C-SDVR-NoSeverity": "#C75D68",
    "C-SDVR": "#1F8A70",
    "dark": "#303030",
    "light": "#F3F1EC",
    "line": "#B8B8B8",
    "warn": "#D9A441",
    "bad": "#B95F5F",
    "blue": "#4A7CA8",
}

ORDER = [
    "NoCheck",
    "FinalVerifier",
    "StepVerifier",
    "ReflectionRetry",
    "C-SDVR-NoRollback",
    "C-SDVR-NoSeverity",
    "C-SDVR",
]


def save_all(fig, stem):
    for ext in ("pdf", "svg", "png", "tiff"):
        fig.savefig(FIG_DIR / f"{stem}.{ext}", bbox_inches="tight")


def panel_label(ax, label):
    ax.text(
        -0.16,
        1.10,
        label,
        transform=ax.transAxes,
        fontsize=11,
        fontweight="bold",
        va="top",
        ha="left",
    )


def clean_method(name):
    mapping = {
        "ReflectionRetry": "Reflection retry",
        "C-SDVR-NoRollback": "No rollback",
        "C-SDVR-NoSeverity": "No severity",
    }
    return mapping.get(name, name)


def load_data():
    main = pd.read_csv(BASE / "summary_metrics_executable_v3.csv")
    domain = pd.read_csv(BASE / "summary_by_domain_executable_v3.csv")
    severity = pd.read_csv(BASE / "summary_by_severity_executable_v3.csv")
    sensitivity = pd.read_csv(BASE / "sensitivity_results_v3.csv")
    live = pd.read_csv(BASE / "live_validation_summary_v3.csv")
    return main, domain, severity, sensitivity, live


def draw_figure_1(main, sensitivity, live):
    main = main.set_index("method").loc[ORDER].reset_index()
    fig, (ax0, ax1, ax2) = plt.subplots(
        1,
        3,
        figsize=(7.2, 2.8),
        gridspec_kw={"width_ratios": [1.35, 1.0, 1.0]},
    )
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.26, top=0.80, wspace=0.48)

    # A: success-cost-residue trade-off
    for _, row in main.iterrows():
        method = row["method"]
        residue = row["side_effect_residue_rate"]
        size = 90 + 700 * residue
        edge = PALETTE["dark"] if method == "C-SDVR" else "white"
        lw = 1.4 if method == "C-SDVR" else 0.7
        ax0.scatter(
            row["mean_token_cost"],
            row["task_success_rate"],
            s=size,
            color=PALETTE[method],
            edgecolor=edge,
            linewidth=lw,
            alpha=0.92,
            zorder=3,
        )
        label_offsets = {
            "NoCheck": (20, 0.050),
            "FinalVerifier": (70, 0.020),
            "StepVerifier": (100, 0.020),
            "ReflectionRetry": (-250, 0.032),
            "C-SDVR-NoRollback": (-420, -0.020),
            "C-SDVR-NoSeverity": (120, 0.030),
            "C-SDVR": (-380, -0.075),
        }
        dx, dy = label_offsets[method]
        ax0.text(
            row["mean_token_cost"] + dx,
            row["task_success_rate"] + dy,
            clean_method(method),
            color=PALETTE["dark"],
            fontsize=7.5,
        )
    ax0.set_xlabel("Mean token-cost proxy per run")
    ax0.set_ylabel("Task success")
    ax0.set_ylim(0.08, 0.83)
    ax0.set_xlim(820, 3330)
    ax0.grid(axis="both", color="#E6E2D8", linewidth=0.5)
    panel_label(ax0, "a")

    # B: residue vs unnecessary repair
    key_methods = ["NoCheck", "FinalVerifier", "ReflectionRetry", "C-SDVR-NoSeverity", "C-SDVR"]
    bdf = main.set_index("method").loc[key_methods]
    x = np.arange(len(key_methods))
    width = 0.36
    ax1.bar(
        x - width / 2,
        bdf["side_effect_residue_rate"],
        width,
        color="#B95F5F",
        label="Residual side effects",
    )
    ax1.bar(
        x + width / 2,
        bdf["unnecessary_repair_rate"],
        width,
        color="#D9A441",
        label="Unnecessary repair",
    )
    ax1.set_xticks(x)
    ax1.set_xticklabels([clean_method(m) for m in key_methods], rotation=35, ha="right")
    ax1.set_ylabel("Rate")
    ax1.set_ylim(0, 0.82)
    ax1.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.04))
    ax1.grid(axis="y", color="#E6E2D8", linewidth=0.5)
    panel_label(ax1, "b")

    # C: cost-normalized success
    cdf = main.set_index("method").loc[key_methods]
    colors = [PALETTE[m] for m in key_methods]
    ax2.bar(np.arange(len(key_methods)), cdf["cost_norm_success"], color=colors)
    ax2.set_xticks(np.arange(len(key_methods)))
    ax2.set_xticklabels([clean_method(m) for m in key_methods], rotation=35, ha="right")
    ax2.set_ylabel("Cost-normalized success")
    ax2.set_ylim(0, 0.50)
    ax2.grid(axis="y", color="#E6E2D8", linewidth=0.5)
    panel_label(ax2, "c")

    fig.suptitle(
        "C-SDVR prioritizes residue control and scoped recovery cost",
        x=0.02,
        ha="left",
        fontsize=10.5,
        fontweight="bold",
    )
    save_all(fig, "nature_fig1_tradeoff_composite")
    plt.close(fig)


def draw_box(ax, xy, wh, text, fc, ec="#555555", lw=0.9, fontsize=8):
    box = patches.FancyBboxPatch(
        xy,
        wh[0],
        wh[1],
        boxstyle="round,pad=0.018,rounding_size=0.025",
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
    )
    ax.add_patch(box)
    ax.text(
        xy[0] + wh[0] / 2,
        xy[1] + wh[1] / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=PALETTE["dark"],
    )
    return box


def arrow(ax, start, end, color="#555555"):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops=dict(arrowstyle="-|>", lw=0.9, color=color, shrinkA=4, shrinkB=4),
    )


def draw_figure_2(main):
    fig = plt.figure(figsize=(7.2, 4.8))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.2, 1.0], width_ratios=[1, 1, 1], hspace=0.45, wspace=0.38)
    ax0 = fig.add_subplot(gs[0, :])
    ax1 = fig.add_subplot(gs[1, 0])
    ax2 = fig.add_subplot(gs[1, 1])
    ax3 = fig.add_subplot(gs[1, 2])

    ax0.set_xlim(0, 1)
    ax0.set_ylim(0, 1)
    ax0.axis("off")
    panel_label(ax0, "a")
    ax0.text(0.0, 1.05, "State-difference verification converts step deviations into bounded recovery decisions", fontsize=9, fontweight="bold")

    boxes = [
        ((0.02, 0.54), (0.13, 0.25), "Agent\nstep", "#E9ECE6"),
        ((0.19, 0.54), (0.15, 0.25), "Pre/post\nsnapshots", "#EAF2F0"),
        ((0.39, 0.54), (0.15, 0.25), "State diff\n+ verifier", "#DDEFE8"),
        ((0.59, 0.54), (0.15, 0.25), "Severity\nand cost gate", "#F3E8C8"),
        ((0.80, 0.56), (0.16, 0.22), "Decision\npolicy", "#E8EDF5"),
    ]
    for xy, wh, text, fc in boxes:
        draw_box(ax0, xy, wh, text, fc)
    for x0, x1 in [(0.15, 0.19), (0.34, 0.39), (0.54, 0.59), (0.74, 0.80)]:
        arrow(ax0, (x0, 0.665), (x1, 0.665))

    decisions = [
        (0.42, "continue", "#DDEFE8"),
        (0.31, "repair", "#E8EDF5"),
        (0.20, "rollback", "#F4D7D7"),
        (0.09, "stop / confirm", "#EFEFEF"),
    ]
    for y, text, fc in decisions:
        draw_box(ax0, (0.80, y - 0.035), (0.16, 0.055), text, fc, fontsize=7)
    for y, _, _ in decisions:
        arrow(ax0, (0.88, 0.56), (0.88, y + 0.028), color="#777777")

    draw_box(ax0, (0.18, 0.16), (0.26, 0.16), "File state\npaths, hashes, content", "#F4F4F4", fontsize=7)
    draw_box(ax0, (0.48, 0.16), (0.26, 0.16), "Form state\nfields, messages, DB rows", "#F4F4F4", fontsize=7)
    arrow(ax0, (0.31, 0.32), (0.265, 0.54), color="#777777")
    arrow(ax0, (0.61, 0.32), (0.265, 0.54), color="#777777")

    m = main.set_index("method")
    methods = ["NoCheck", "FinalVerifier", "StepVerifier", "C-SDVR"]
    ax1.bar(range(len(methods)), m.loc[methods, "critical_recall"], color=[PALETTE[x] for x in methods])
    ax1.set_xticks(range(len(methods)))
    ax1.set_xticklabels([clean_method(x) for x in methods], rotation=35, ha="right")
    ax1.set_ylabel("Critical-error recall")
    ax1.set_ylim(0, 1.0)
    ax1.grid(axis="y", color="#E6E2D8", linewidth=0.5)
    panel_label(ax1, "b")

    ax2.bar(range(len(methods)), m.loc[methods, "side_effect_residue_rate"], color=[PALETTE[x] for x in methods])
    ax2.set_xticks(range(len(methods)))
    ax2.set_xticklabels([clean_method(x) for x in methods], rotation=35, ha="right")
    ax2.set_ylabel("Residual side-effect rate")
    ax2.set_ylim(0, 0.82)
    ax2.grid(axis="y", color="#E6E2D8", linewidth=0.5)
    panel_label(ax2, "c")

    methods2 = ["C-SDVR-NoRollback", "C-SDVR-NoSeverity", "C-SDVR"]
    vals = m.loc[methods2, ["task_success_rate", "unnecessary_repair_rate"]]
    x = np.arange(len(methods2))
    ax3.bar(x - 0.18, vals["task_success_rate"], 0.36, color=[PALETTE[k] for k in methods2], label="Success")
    ax3.bar(x + 0.18, vals["unnecessary_repair_rate"], 0.36, color=PALETTE["warn"], label="Unnecessary repair")
    ax3.set_xticks(x)
    ax3.set_xticklabels([clean_method(x) for x in methods2], rotation=35, ha="right")
    ax3.set_ylim(0, 0.86)
    ax3.set_ylabel("Rate")
    ax3.legend(frameon=False, loc="upper left")
    ax3.grid(axis="y", color="#E6E2D8", linewidth=0.5)
    panel_label(ax3, "d")

    save_all(fig, "nature_fig2_framework_schematic")
    plt.close(fig)


def draw_heatmap(ax, table, title, vmin, vmax, cmap):
    data = table.values.astype(float)
    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(table.shape[1]))
    ax.set_xticklabels(table.columns)
    ax.set_yticks(range(table.shape[0]))
    ax.set_yticklabels([clean_method(x) for x in table.index])
    ax.set_title(title, loc="left", fontweight="bold")
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            ax.text(j, i, f"{data[i, j]:.2f}", ha="center", va="center", fontsize=7, color="#222222")
    ax.tick_params(length=0)
    return im


def draw_figure_3(domain, severity):
    fig = plt.figure(figsize=(7.2, 5.0))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.0], width_ratios=[1.05, 1.0], hspace=0.52, wspace=0.42)
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    methods = ["NoCheck", "FinalVerifier", "ReflectionRetry", "C-SDVR-NoRollback", "C-SDVR-NoSeverity", "C-SDVR"]
    success = (
        domain[domain["method"].isin(methods)]
        .pivot(index="method", columns="domain", values="task_success_rate")
        .loc[methods, ["file", "web_form"]]
    )
    residue = (
        domain[domain["method"].isin(methods)]
        .pivot(index="method", columns="domain", values="side_effect_residue_rate")
        .loc[methods, ["file", "web_form"]]
    )
    cmap_success = LinearSegmentedColormap.from_list("success", ["#F7E9D2", "#C8E0D8", "#1F8A70"])
    cmap_residue = LinearSegmentedColormap.from_list("residue", ["#F7F7F7", "#E9C8C8", "#B95F5F"])
    im0 = draw_heatmap(ax0, success, "Domain success", 0.0, 0.85, cmap_success)
    im1 = draw_heatmap(ax1, residue, "Domain residual side effects", 0.0, 0.90, cmap_residue)
    panel_label(ax0, "a")
    panel_label(ax1, "b")
    fig.colorbar(im0, ax=ax0, fraction=0.046, pad=0.02)
    fig.colorbar(im1, ax=ax1, fraction=0.046, pad=0.02)

    sev_methods = ["C-SDVR-NoRollback", "C-SDVR-NoSeverity", "C-SDVR"]
    critical = (
        severity[(severity["method"].isin(sev_methods)) & (severity["severity"] == "critical")]
        .set_index("method")
        .loc[sev_methods]
    )
    x = np.arange(len(sev_methods))
    ax2.bar(x - 0.22, critical["task_success_rate"], 0.22, color=[PALETTE[m] for m in sev_methods], label="Success")
    ax2.bar(x, critical["side_effect_residue_rate"], 0.22, color=PALETTE["bad"], label="Residue")
    ax2.bar(x + 0.22, critical["rollback_use_rate"], 0.22, color="#8FAAD6", label="Rollback use")
    ax2.set_xticks(x)
    ax2.set_xticklabels([clean_method(m) for m in sev_methods], rotation=30, ha="right")
    ax2.set_ylabel("Rate for critical faults")
    ax2.set_ylim(0, 1.0)
    ax2.legend(frameon=False, ncol=1, loc="upper left")
    ax2.grid(axis="y", color="#E6E2D8", linewidth=0.5)
    panel_label(ax2, "c")

    minor = (
        severity[(severity["method"].isin(sev_methods)) & (severity["severity"] == "minor")]
        .set_index("method")
        .loc[sev_methods]
    )
    ax3.scatter(
        minor["mean_token_cost"],
        minor["task_success_rate"],
        s=90,
        color=[PALETTE[m] for m in sev_methods],
        edgecolor="white",
        linewidth=0.7,
        zorder=3,
    )
    minor_label_offsets = {
        "C-SDVR-NoRollback": (-60, -0.008),
        "C-SDVR-NoSeverity": (18, 0.005),
        "C-SDVR": (18, 0.005),
    }
    for m in sev_methods:
        row = minor.loc[m]
        dx, dy = minor_label_offsets[m]
        ax3.text(row["mean_token_cost"] + dx, row["task_success_rate"] + dy, clean_method(m), fontsize=7)
    ax3.vlines(minor.loc["C-SDVR", "mean_token_cost"], 0.94, minor.loc["C-SDVR", "task_success_rate"], color="#BBBBBB", lw=0.8)
    ax3.set_xlabel("Token-cost proxy for minor faults")
    ax3.set_ylabel("Success for minor faults")
    ax3.set_ylim(0.94, 1.015)
    ax3.set_xlim(1600, 2200)
    ax3.grid(axis="both", color="#E6E2D8", linewidth=0.5)
    ax3.text(
        1800,
        0.970,
        "Semantic success is unchanged;\nrestraint lowers cosmetic-repair cost",
        fontsize=7,
        ha="left",
        va="top",
    )
    panel_label(ax3, "d")

    fig.suptitle("Domain and severity diagnostics show where rollback and restraint matter", x=0.02, ha="left", fontsize=10, fontweight="bold")
    save_all(fig, "nature_fig3_domain_severity")
    plt.close(fig)


if __name__ == "__main__":
    main_df, domain_df, severity_df, sensitivity_df, live_df = load_data()
    draw_figure_1(main_df, sensitivity_df, live_df)
    draw_figure_2(main_df)
    draw_figure_3(domain_df, severity_df)
    print(f"Wrote Nature-style figures to {FIG_DIR}")
