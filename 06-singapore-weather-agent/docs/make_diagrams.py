#!/usr/bin/env python3
"""Render the architecture diagrams (PNG + SVG) into docs/.

    ../.venv/bin/python docs/make_diagrams.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent

INK = "#1d2433"
MUTED = "#5b6475"
ARROW = "#3b4252"

# Group (container) styles: fill, border
G_CLIENT = ("#eef4fb", "#7aa7d9")
G_AWS = ("#fff8ee", "#ff9900")
G_BEDROCK = ("#f4efff", "#8c6bd8")
G_AGENTCORE = ("#eaf7f1", "#2f9e6e")
G_NEA = ("#eef7ee", "#4c9a52")
G_CFG = ("#f5f6f8", "#8a94a6")
G_SCORE = ("#fdf2f8", "#c2417f")

# Node border colours
C_CLIENT = "#3b78c3"
C_AGENT = "#1f5fa8"
C_GUARD = "#d13c3c"
C_LLM = "#7a4fd0"
C_GW = "#23845a"
C_LAMBDA = "#e07b00"
C_NEA = "#3f8a46"
C_GREY = "#6b7280"
C_EVAL = "#b4326f"


def new_canvas(w: float, h: float, title: str, subtitle: str):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(0.35, h - 0.35, title, fontsize=21, fontweight="bold", color=INK, va="top")
    ax.text(0.35, h - 0.95, subtitle, fontsize=12, color=MUTED, va="top")
    return fig, ax


def group(ax, x0, y0, x1, y1, label, style, fontsize=13):
    fill, edge = style
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0.02,rounding_size=0.25",
                                fc=fill, ec=edge, lw=1.8, zorder=0))
    ax.text(x0 + 0.2, y1 - 0.15, label, fontsize=fontsize, fontweight="bold", color=edge, va="top", zorder=1)


def node(ax, cx, cy, w, h, title, body="", color=C_GREY, fill="white", title_size=12.5, body_size=10):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fill, ec=color, lw=2.0, zorder=3))
    if body:
        n_body = body.count("\n") + 1
        title_y = cy + h / 2 - 0.22
        ax.text(cx, title_y, title, ha="center", va="top", fontsize=title_size, fontweight="bold", color=INK, zorder=4)
        ax.text(cx, title_y - 0.36 - (0.02 * n_body), body, ha="center", va="top", fontsize=body_size,
                color=MUTED, zorder=4, linespacing=1.35)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=title_size, fontweight="bold", color=INK, zorder=4)
    return {"cx": cx, "cy": cy, "w": w, "h": h}


def side(n, which, offset=0.0):
    cx, cy, w, h = n["cx"], n["cy"], n["w"], n["h"]
    return {
        "l": (cx - w / 2, cy + offset), "r": (cx + w / 2, cy + offset),
        "t": (cx + offset, cy + h / 2), "b": (cx + offset, cy - h / 2),
    }[which]


def arrow(ax, p0, p1, label="", both=False, dashed=False, color=ARROW, label_pos=0.5, label_offset=(0, 0.18),
          rad=0.0, label_size=9.5, lw=1.8):
    style = "<|-|>" if both else "-|>"
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=16, color=color, lw=lw,
                                 linestyle=(0, (5, 4)) if dashed else "solid",
                                 connectionstyle=f"arc3,rad={rad}", zorder=2, shrinkA=2, shrinkB=2))
    if label:
        lx = p0[0] + (p1[0] - p0[0]) * label_pos + label_offset[0]
        ly = p0[1] + (p1[1] - p0[1]) * label_pos + label_offset[1]
        ax.text(lx, ly, label, fontsize=label_size, color=color, ha="center", va="center", zorder=5,
                bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.92), linespacing=1.25)


def polyline(ax, pts, label="", label_at=0, color=ARROW, dashed=False, label_offset=(0, 0.2), lw=1.8):
    ls = (0, (5, 4)) if dashed else "solid"
    for a, b in zip(pts[:-2], pts[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, linestyle=ls, zorder=2, solid_capstyle="round")
    arrow(ax, pts[-2], pts[-1], color=color, dashed=dashed, lw=lw)
    if label:
        a, b = pts[label_at], pts[label_at + 1]
        ax.text((a[0] + b[0]) / 2 + label_offset[0], (a[1] + b[1]) / 2 + label_offset[1], label, fontsize=9.5,
                color=color, ha="center", va="center", zorder=5,
                bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.92))


def step(ax, x, y, n, color=C_AGENT):
    ax.add_patch(plt.Circle((x, y), 0.2, fc=color, ec="white", lw=1.5, zorder=6))
    ax.text(x, y, str(n), ha="center", va="center", fontsize=10, fontweight="bold", color="white", zorder=7)


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=170 if ext == "png" else None, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png", "and .svg")


# --------------------------------------------------------------------------- #
# 1. Runtime architecture
# --------------------------------------------------------------------------- #
def runtime():
    W, H = 20, 12
    fig, ax = new_canvas(W, H, "Singapore Weather Agent: runtime architecture",
                         "How a question is answered (AgentCore Gateway + Bedrock Guardrail mode, with local-tools mode)")

    group(ax, 0.3, 1.9, 5.7, 10.6, "Your machine / Code Editor", G_CLIENT)
    group(ax, 6.3, 1.9, 15.6, 10.6, "AWS account (us-east-1)", G_AWS)
    group(ax, 6.6, 7.3, 15.3, 10.0, "Amazon Bedrock", G_BEDROCK, fontsize=12)
    group(ax, 6.6, 2.3, 10.9, 6.9, "Amazon Bedrock AgentCore", G_AGENTCORE, fontsize=12)
    group(ax, 16.2, 0.95, 19.7, 7.0, "NEA open data", G_NEA)

    user = node(ax, 3.0, 9.65, 2.4, 0.6, "User", color=C_CLIENT)
    cli = node(ax, 1.75, 8.25, 2.3, 1.0, "weather_agent.py", "CLI", color=C_CLIENT)
    web = node(ax, 4.25, 8.25, 2.5, 1.0, "web_app.py", "Browser UI :8501", color=C_CLIENT)
    agent = node(ax, 3.0, 6.05, 4.6, 1.55, "Strands Agent", "open_agent(variant)\nsystem prompt v3 (config/prompts)",
                 color=C_AGENT, fill="#f2f7fd")
    local = node(ax, 1.75, 4.05, 2.5, 1.0, "Local tools", "@tool, in-process", color=C_CLIENT)
    ndl = node(ax, 3.0, 2.65, 5.1, 1.15, "nea_data.py", "parsers · NEA PSI/PM2.5 bands\n60 s cache · rate-limit retry",
               color=C_CLIENT, body_size=9.5)

    guard = node(ax, 8.95, 8.55, 4.1, 2.05, "Bedrock Guardrail v3",
                 "content + prompt-attack filters\ndenied topics: MedicalTreatment,\nPoliticalBlame · PII masking\n(NRIC/FIN, phone, email)",
                 color=C_GUARD, fill="#fff3f2", body_size=9.5)
    llm = node(ax, 13.55, 8.55, 3.2, 1.35, "Claude Sonnet", "global.anthropic.claude-sonnet-5", color=C_LLM,
               fill="#f7f3ff", body_size=9.5)

    gw = node(ax, 8.75, 5.55, 3.7, 1.35, "AgentCore Gateway", "sg-weather-gateway\nMCP · AWS_IAM authorizer (SigV4)",
              color=C_GW, fill="#f0faf5", body_size=9.5)
    tgt = node(ax, 8.75, 3.35, 3.7, 1.15, "Gateway target: WeatherTools", "4 MCP tool schemas", color=C_GW,
               fill="#f0faf5", title_size=11.5)
    lam = node(ax, 13.25, 4.35, 3.6, 1.55, "AWS Lambda", "sg-weather-tools · Python 3.12\nweather_tools_lambda.py + nea_data.py",
               color=C_LAMBDA, fill="#fff6ea", body_size=9.5)
    iam = node(ax, 13.25, 6.25, 3.6, 0.85, "IAM roles", "Gateway → lambda:InvokeFunction", color=C_GREY, body_size=9)
    cw = node(ax, 13.25, 2.65, 3.6, 0.65, "CloudWatch Logs", color=C_GREY, title_size=11)

    dg = node(ax, 17.95, 4.1, 3.1, 3.2, "data.gov.sg",
              "v2 real-time API\n\ntwo-hr-forecast\ntwenty-four-hr-forecast\nfour-day-outlook\npsi · pm25",
              color=C_NEA, fill="#f3faf3", body_size=10)

    # user entry
    arrow(ax, side(user, "b", -0.6), side(cli, "t"))
    arrow(ax, side(user, "b", 0.6), side(web, "t"))
    arrow(ax, side(cli, "b"), side(agent, "t", -1.25))
    arrow(ax, side(web, "b"), side(agent, "t", 1.25))

    # model + guardrail
    arrow(ax, side(agent, "r", 0.45), side(guard, "l", -0.35), both=True, color=C_GUARD)
    ax.text(6.0, 7.2, "Converse API\nin/out screened", fontsize=9.5, color=C_GUARD, ha="center", va="center", zorder=5,
            bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.95))
    arrow(ax, side(guard, "r"), side(llm, "l"), both=True, color=C_LLM)

    # gateway path
    arrow(ax, side(agent, "r", -0.3), side(gw, "l", 0.15), "gateway mode\nMCP / HTTPS · SigV4",
          color=C_GW, label_pos=0.45, label_offset=(0, -0.42))
    arrow(ax, side(gw, "b"), side(tgt, "t"), color=C_GW)
    arrow(ax, side(tgt, "r"), side(lam, "l", -0.35), "invoke\n(IAM role)", color=C_LAMBDA, label_pos=0.5,
          label_offset=(0.05, 0.42))
    arrow(ax, side(lam, "r"), side(dg, "l", 0.25), "HTTPS", color=C_NEA, label_offset=(0, 0.2))
    arrow(ax, side(lam, "b"), side(cw, "t"), dashed=True, color=C_GREY)
    arrow(ax, side(iam, "b"), side(lam, "t"), dashed=True, color=C_GREY)

    # local path
    arrow(ax, side(agent, "b", -1.25), side(local, "t"), "local mode", color=C_CLIENT, label_offset=(0.65, 0.0))
    arrow(ax, side(local, "b"), side(ndl, "t", -1.25), color=C_CLIENT)
    polyline(ax, [side(ndl, "b"), (3.0, 1.15), (17.95, 1.15), side(dg, "b")], "HTTPS (local mode)", label_at=1,
             color=C_NEA, label_offset=(0, 0.2))

    # numbered request flow
    step(ax, 5.15, 7.05, 1)
    step(ax, 6.55, 7.85, 2, C_GUARD)
    step(ax, 11.47, 9.05, 3, C_LLM)
    step(ax, 6.2, 5.7, 4, C_GW)
    step(ax, 15.0, 5.35, 5, C_LAMBDA)
    step(ax, 11.47, 8.05, 6, C_GUARD)

    legend = ("1  Question from the CLI or the browser reaches the Strands agent      "
              "2  Guardrail screens input (injection, dosing, politics; masks PII)      "
              "3  Claude picks tools\n"
              "4  SigV4-signed MCP call to the AgentCore Gateway → Lambda      "
              "5  Lambda fetches NEA feeds; bands and per-region advisory computed in code      "
              "6  Answer screened on output, returned with an NEA source line")
    ax.text(0.35, 0.05, legend, fontsize=10, color=MUTED, va="bottom", linespacing=1.6)
    save(fig, "architecture_runtime")


# --------------------------------------------------------------------------- #
# 2. Evaluation & iteration loop
# --------------------------------------------------------------------------- #
def evaluation():
    W, H = 20.6, 12.6
    fig, ax = new_canvas(W, H, "Singapore Weather Agent: evaluation & iteration loop",
                         "Every prompt or guardrail change is a variant, evaluated live against NEA's own websites")

    # Row 1: versioned config + infra
    group(ax, 0.3, 8.3, 8.9, 10.35, "Versioned behaviour config", G_CFG, fontsize=12)
    cfg_g = node(ax, 1.75, 9.0, 2.7, 0.95, "guardrail.json", "guardrail v1 → v2 → v3", color=C_GUARD, body_size=9.5)
    cfg_p = node(ax, 4.6, 9.0, 2.7, 0.95, "prompts/", "system_v1 → v2 → v3", color=C_GREY, body_size=9.5)
    cfg_v = node(ax, 7.45, 9.0, 2.7, 0.95, "variants.json", "v1 … v5 ladder", color=C_GREY, body_size=9.5)
    infra = node(ax, 11.5, 9.0, 3.2, 0.95, "infra.py", "deploy · smoke · status · destroy", color=C_LAMBDA, body_size=9.5)

    # Row 2: runners, agent, ground truth
    it = node(ax, 1.75, 6.6, 2.9, 1.0, "iterate.py", "runs variants, compares", color=C_EVAL, body_size=9.5)
    ev = node(ax, 5.3, 6.6, 3.3, 1.2, "evaluate.py", "runs every case per variant\nscores + saves results",
              color=C_EVAL, body_size=9.5)
    agentn = node(ax, 11.5, 6.6, 3.9, 1.25, "Weather Agent", "runtime architecture\n(local or Gateway + Guardrail)",
                  color=C_AGENT, fill="#f2f7fd", body_size=9.5)
    group(ax, 14.1, 4.95, 20.0, 8.0, "Independent ground truth", G_NEA, fontsize=12)
    ngt = node(ax, 17.05, 6.95, 3.8, 0.9, "nea_ground_truth.py", "before/after snapshots", color=C_NEA, body_size=9.5)
    neaw = node(ax, 15.65, 5.6, 2.5, 0.95, "nea.gov.sg", "2 h · 24 h · 4-day", color=C_NEA, title_size=11, body_size=9)
    hz = node(ax, 18.45, 5.6, 2.6, 0.95, "haze.gov.sg", "PSI · PM2.5 · 24 h history", color=C_NEA, title_size=11,
              body_size=9)

    # Row 3: datasets + scoring
    group(ax, 0.3, 2.75, 8.6, 4.95, "Datasets", G_CFG, fontsize=12)
    d1 = node(ax, 2.35, 3.65, 3.6, 1.15, "eval_dataset.json", "19 cases: 9 quality + 10 safety", color=C_GREY,
              body_size=9.5)
    d2 = node(ax, 6.45, 3.65, 4.0, 1.15, "eval_dataset_haze_replay.json", "6 cases · synthetic haze day",
              color=C_GREY, title_size=11, body_size=9.5)
    group(ax, 9.2, 2.55, 20.0, 4.75, "Scoring", G_SCORE, fontsize=12)
    dc = node(ax, 12.15, 3.5, 5.3, 1.6, "Deterministic checks",
              "values vs NEA (haze aligned to reading hour)\ntool selection · refusal · no dosage · no leak\nno PII echo · canary · no false block",
              color=C_EVAL, body_size=9.2)
    jd = node(ax, 17.4, 3.5, 4.6, 1.6, "LLM judge × 3", "accuracy · completeness · helpfulness\nmajority-vote hallucination",
              color=C_EVAL, body_size=9.2)

    # Row 4: probe + outputs
    probe = node(ax, 3.6, 1.25, 4.0, 1.2, "scripts/probe_guardrail.py", "ApplyGuardrail on DRAFT\nmust-pass vs must-block",
                 color=C_GUARD, title_size=11.5, body_size=9)
    outn = node(ax, 14.1, 1.25, 7.6, 1.1, "results/ · iterations/log.jsonl · ITERATIONS.md",
                "findings → next prompt / guardrail version", color=C_GREY, title_size=11.5, body_size=9.5)

    # guardrail config → infra (publish) and → probe
    polyline(ax, [side(cfg_g, "t"), (1.75, 10.75), (11.5, 10.75), side(infra, "t")], "publish guardrail version",
             label_at=1, color=C_GUARD, label_offset=(1.6, 0.2))
    polyline(ax, [side(cfg_g, "l"), (0.12, 9.0), (0.12, 1.25), side(probe, "l")], color=C_GUARD)

    # config → iterate
    arrow(ax, side(cfg_p, "b", -1.0), side(it, "t", 0.5), color=C_GREY)
    arrow(ax, side(cfg_v, "b", -0.6), side(it, "t", 1.1), color=C_GREY)
    arrow(ax, side(infra, "b"), side(agentn, "t"), "deploys Lambda · Gateway · Guardrail", color=C_LAMBDA,
          label_pos=0.27, label_offset=(1.9, 0))

    arrow(ax, side(it, "r"), side(ev, "l"), color=C_EVAL)
    arrow(ax, side(ev, "r", 0.15), side(agentn, "l", 0.15), "runs each case", color=C_EVAL, label_offset=(0, 0.25))
    polyline(ax, [side(ev, "t", 1.0), (6.3, 7.75), (13.75, 7.75), (13.75, 6.95), side(ngt, "l")],
             "capture NEA ground truth (before / after)", label_at=1, color=C_NEA, label_offset=(-1.3, 0.2))
    arrow(ax, side(ngt, "b", -1.4), side(neaw, "t"), color=C_NEA)
    arrow(ax, side(ngt, "b", 1.4), side(hz, "t"), color=C_NEA)

    arrow(ax, side(d1, "t", 0.8), side(ev, "b", -0.8), color=C_GREY)
    arrow(ax, side(d2, "t", -0.6), side(ev, "b", 0.6), color=C_GREY)

    arrow(ax, side(agentn, "b", -0.9), side(dc, "t", -1.55), color=C_AGENT)
    arrow(ax, side(agentn, "b", 0.9), side(jd, "t", -1.6), "answers +\ntool outputs", color=C_AGENT,
          label_pos=0.2, label_offset=(0.35, -0.55))
    arrow(ax, side(neaw, "b"), side(dc, "t", 1.6), color=C_NEA)
    arrow(ax, side(hz, "b"), side(jd, "t", 1.05), color=C_NEA)

    arrow(ax, side(dc, "b"), side(outn, "t", -1.95), color=C_EVAL)
    arrow(ax, side(jd, "b"), side(outn, "t", 3.3), color=C_EVAL)
    arrow(ax, side(probe, "r"), side(outn, "l"), "false blocks / misses", color=C_GUARD, label_offset=(0, 0.22))

    polyline(ax, [side(outn, "r"), (20.3, 1.25), (20.3, 11.05), (6.0, 11.05), (6.0, 10.37)],
             "iterate: findings drive the next prompt / guardrail change", label_at=2, color=C_EVAL, dashed=True,
             label_offset=(0, 0.2))

    save(fig, "architecture_evaluation")


if __name__ == "__main__":
    runtime()
    evaluation()
