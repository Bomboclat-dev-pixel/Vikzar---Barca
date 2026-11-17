"""Algorithmic Game-State & Role-Clustered Recruitment Engine (analyze_spells.py).

Combines 25 Hz predicted possession spells (submission_artifacts/vikzar.csv) with
the instantaneous raw proximity signal (evaluation/results/baseline_raw.csv) and,
when locally mounted, BAR-ATH ATD + Smart Tagging XML to generate:
  1. Algorithmic Game-State Phase Segmentation (no hardcoded match minutes)
  2. Possession & Stoppage Architecture per Game State
  3. Press-Resistance Index (PRI) & Counter-Pressing Recovery Metrics
  4. Role-Clustered Recruitment Profiles (Build-Up Pivot / Progression / Box-Entry)
  5. Publication-ready figures in figures/ and JSON/CSV tables for vikzar.pdf.

Run from the repository root:
    python analyze_spells.py
"""

import argparse
import json
import os
import xml.etree.ElementTree as ET

import numpy as np

from games import GAME, GAMES, half_video_blocks, require
import team_model as tm


FPS = 25.0
HIGH_PRESSURE_MIN_FRAMES = 3
PRI_RETENTION_MIN_FRAMES = 125       # 5.0 s retained possession under pressure
COUNTERPRESS_WINDOW_FRAMES = 75      # 3.0 s counter-pressing compression window
RECOVERY_HORIZON_FRAMES = 150        # 6.0 s rapid recovery horizon


def _fill_x_within_blocks(labels, half_blocks):
    """Forward-fill (and back-fill leading edge) X within each half, matching scorer."""
    out = labels.copy()
    for _half, first, last in half_blocks:
        s, e = max(0, first), min(len(out), last + 1)
        win = out[s:e]
        known = np.flatnonzero(win != "X")
        if len(known) == 0:
            continue
        carry = np.maximum.accumulate(np.where(win != "X", np.arange(len(win)), -1))
        carry[carry < 0] = known[0]
        out[s:e] = win[carry]
    return out


def load_goal_restart_events(smart_tagging_path, n_frames, fps=FPS):
    """Extract chronological GOALS (Team) and matching Kick Off (After Goal) frames."""
    if not smart_tagging_path or not os.path.isfile(smart_tagging_path):
        return []

    root = ET.parse(smart_tagging_path).getroot()
    goals = []
    kickoffs = []
    for instance in root.iter("instance"):
        code = (instance.findtext("code") or "").strip().upper()
        start_s = float(instance.findtext("start") or 0.0)
        end_s = float(instance.findtext("end") or start_s)
        start_f = max(0, min(n_frames, int(round(start_s * fps))))
        end_f = max(start_f, min(n_frames, int(round(end_s * fps))))
        tags = {
            (label.findtext("group") or "").strip(): (label.findtext("text") or "").strip()
            for label in instance.findall("label")
        }
        if code == "GOALS":
            raw_team = (tags.get("Team") or "").strip().lower()
            if raw_team == "barcelona":
                team = "Barcelona"
            elif raw_team in ("atletic club", "athletic club"):
                team = "Athletic Club"
            else:
                continue
            goals.append({"goal_start": start_f, "goal_end": end_f, "team": team})
        elif code == "SET PIECES" and (tags.get("Type") or "").strip().lower() == "kick off (after goal)":
            kickoffs.append(int(round(0.5 * (start_f + end_f))))

    goals.sort(key=lambda g: g["goal_end"])
    kickoffs.sort()
    used_ko = set()
    events = []
    for goal in goals:
        best_idx = None
        best_dist = None
        for idx, ko in enumerate(kickoffs):
            if idx in used_ko:
                continue
            dist = abs(ko - goal["goal_end"])
            if dist <= int(10 * fps) and (best_dist is None or dist < best_dist):
                best_idx, best_dist = idx, dist
        if best_idx is not None:
            used_ko.add(best_idx)
            restart_f = kickoffs[best_idx]
        else:
            restart_f = goal["goal_end"]
        events.append({
            "goal_start": goal["goal_start"],
            "goal_end": goal["goal_end"],
            "restart_frame": restart_f,
            "team": goal["team"],
        })
    return events


def _slice_half_blocks_at_boundaries(half_blocks, cut_frames):
    """Partition graded half blocks sequentially at sorted restart frames without halftime mixing."""
    base_windows = [(first, last + 1) for _half, first, last in half_blocks]
    segments = []
    cur_pos = base_windows[0][0]

    def _collect_until(target_end):
        nonlocal cur_pos
        spans = []
        for w_start, w_end in base_windows:
            seg_a = max(cur_pos, w_start)
            seg_b = min(target_end, w_end)
            if seg_b > seg_a:
                spans.append((seg_a, seg_b))
        cur_pos = max(cur_pos, target_end)
        return spans

    for cut in sorted(cut_frames):
        segments.append(_collect_until(cut))
    segments.append(_collect_until(base_windows[-1][1]))
    return segments


def _score_state_label(goals_for, goals_against):
    if goals_for == goals_against:
        return "Drawing"
    return "Leading" if goals_for > goals_against else "Trailing"


def detect_game_state_phases(filled_labels, half_blocks, smart_tagging_path=None):
    """Derive match phases and Drawing/Leading/Trailing labels from GOALS + Kick Off XML tags."""
    goal_events = load_goal_restart_events(smart_tagging_path, len(filled_labels), FPS)
    if goal_events:
        cut_frames = [ev["restart_frame"] for ev in goal_events]
        span_groups = _slice_half_blocks_at_boundaries(half_blocks, cut_frames)
        phases = []
        h_goals, a_goals = 0, 0
        for idx, spans in enumerate(span_groups):
            home_st = _score_state_label(h_goals, a_goals)
            away_st = _score_state_label(a_goals, h_goals)
            score_txt = f"{h_goals}-{a_goals}"
            if home_st == "Drawing":
                short = f"P{idx + 1} · Drawing\n({score_txt})"
            else:
                short = f"P{idx + 1} · Barça {home_st}\n({score_txt})"
            if spans:
                phases.append({
                    "phase_id": idx + 1,
                    "name": f"Phase {idx + 1} ({score_txt}): Barça {home_st} / Athletic {away_st}",
                    "short_name": short,
                    "home_state": home_st,
                    "away_state": away_st,
                    "score_label": score_txt,
                    "spans": spans,
                })
            if idx < len(goal_events):
                if goal_events[idx]["team"] == "Barcelona":
                    h_goals += 1
                else:
                    a_goals += 1
        return phases, "Smart Tagging XML (GOALS + Kick Off After Goal)"

    # Algorithmic stoppage-clustering fallback when Smart Tagging XML is unmounted locally.
    h1_start, h1_end = half_blocks[0][1], half_blocks[0][2]
    h2_start, h2_end = half_blocks[1][1], half_blocks[1][2]
    h1_limit = h1_end - int(3 * 60 * FPS)
    h1_runs = tm._contiguous_runs(filled_labels[h1_start:h1_limit + 1])
    h1_long = [(b - a, h1_start + a, h1_start + b)
               for a, b, val in h1_runs if val == "D" and (b - a) >= int(60 * FPS)]
    if len(h1_long) >= 2:
        t1 = h1_long[0][2]
        later = [r for r in h1_long if r[1] >= t1 + int(12 * 60 * FPS)]
        t2 = max(later, key=lambda r: r[0])[2] if later else h1_long[-1][2]
    else:
        t1 = h1_start + (h1_end - h1_start) // 3
        t2 = h1_start + (2 * (h1_end - h1_start)) // 3
    h2_limit = h2_end - int(3 * 60 * FPS)
    h2_runs = tm._contiguous_runs(filled_labels[h2_start:h2_limit + 1])
    h2_long = [(b - a, h2_start + a, h2_start + b) for a, b, val in h2_runs if val == "D"]
    t3 = max(h2_long, key=lambda r: r[0])[2] if h2_long else (h2_start + h2_end) // 2

    phases = [
        {"phase_id": 1, "name": "Phase 1: Drawing (Pre-Stoppage)", "short_name": "P1 · Drawing",
         "home_state": "Drawing", "away_state": "Drawing", "score_label": "0-0",
         "spans": [(h1_start, t1)]},
        {"phase_id": 2, "name": "Phase 2: Inferred Leading/Shift", "short_name": "P2 · Leading",
         "home_state": "Leading", "away_state": "Trailing", "score_label": "N/A",
         "spans": [(t1, t2)]},
        {"phase_id": 3, "name": "Phase 3: Inferred Drawing/Reset", "short_name": "P3 · Drawing",
         "home_state": "Drawing", "away_state": "Drawing", "score_label": "N/A",
         "spans": [(t2, h1_end + 1), (h2_start, t3)]},
        {"phase_id": 4, "name": "Phase 4: Inferred Trailing/Closing", "short_name": "P4 · Trailing",
         "home_state": "Trailing", "away_state": "Leading", "score_label": "N/A",
         "spans": [(t3, h2_end + 1)]},
    ]
    return phases, "Algorithmic Stoppage Clustering (Smart Tagging Unmounted)"


def _extract_spells_and_turnovers(filled_labels, raw_labels, span_start, span_end):
    """Extract H/A spells, Press-Resistance Index, and Counter-Press Recovery inside a span."""
    win_pred = filled_labels[span_start:span_end]
    win_raw = raw_labels[span_start:span_end]
    runs = tm._contiguous_runs(win_pred)

    team_stats = {}
    for team_code, team_name in (("H", "Barcelona"), ("A", "Athletic Club")):
        opp_code = "A" if team_code == "H" else "H"
        spells = [(a, b) for a, b, val in runs if val == team_code]
        durations_s = [(b - a) / FPS for a, b in spells]
        total_team_frames = sum(b - a for a, b in spells)

        # Press-Resistance Index (PRI):
        # High-pressure spell = >=3 frames where raw proximity flips to opponent.
        high_press_count = 0
        high_press_retained = 0
        for a, b in spells:
            contested = int(np.count_nonzero(win_raw[a:b] == opp_code))
            if contested >= HIGH_PRESSURE_MIN_FRAMES:
                high_press_count += 1
                if (b - a) >= PRI_RETENTION_MIN_FRAMES:
                    high_press_retained += 1
        pri = (100.0 * high_press_retained / high_press_count) if high_press_count else 0.0

        # Counter-Pressing Compression & Rapid Recovery (<6s):
        # Inspect open-play turnovers (team_code -> opp_code) and recovery within 150 frames.
        turnovers = 0
        cp_challenge_rates = []
        rapid_recoveries = 0
        for idx in range(len(runs) - 1):
            a, b, val = runs[idx]
            na, nb, nval = runs[idx + 1]
            if val == team_code and nval == opp_code:
                turnovers += 1
                w_end = min(len(win_raw), b + COUNTERPRESS_WINDOW_FRAMES)
                if w_end > b:
                    cp_rate = float(np.mean(win_raw[b:w_end] == team_code)) * 100.0
                    cp_challenge_rates.append(cp_rate)
                # Did losing team win possession back within 6.0 s (150 frames)?
                h_end = min(len(win_pred), b + RECOVERY_HORIZON_FRAMES)
                if np.any(win_pred[b:h_end] == team_code):
                    rapid_recoveries += 1

        rapid_rec_pct = (100.0 * rapid_recoveries / turnovers) if turnovers else 0.0
        cp_density = float(np.mean(cp_challenge_rates)) if cp_challenge_rates else 0.0

        # Role-Cluster Spell Regimes:
        #   Cluster 1 (Deep Build-Up / Pivot): > 15s
        #   Cluster 2 (Central Progression): 6s - 15s
        #   Cluster 3 (Direct / Box-Entry Transition): < 6s
        c1 = sum(1 for d in durations_s if d > 15.0)
        c2 = sum(1 for d in durations_s if 6.0 <= d <= 15.0)
        c3 = sum(1 for d in durations_s if d < 6.0)
        n_sp = len(spells)

        team_stats[team_name] = {
            "team_code": team_code,
            "frames": int(total_team_frames),
            "n_spells": int(n_sp),
            "mean_spell_s": float(np.mean(durations_s)) if durations_s else 0.0,
            "median_spell_s": float(np.median(durations_s)) if durations_s else 0.0,
            "p90_spell_s": float(np.percentile(durations_s, 90)) if durations_s else 0.0,
            "high_pressure_spells": int(high_press_count),
            "press_resistance_index": float(pri),
            "open_turnovers": int(turnovers),
            "counterpress_density_pct": float(cp_density),
            "rapid_recovery_6s_pct": float(rapid_rec_pct),
            "cluster_buildup_pct": (100.0 * c1 / n_sp) if n_sp else 0.0,
            "cluster_progression_pct": (100.0 * c2 / n_sp) if n_sp else 0.0,
            "cluster_transition_pct": (100.0 * c3 / n_sp) if n_sp else 0.0,
        }

    dead_frames = int(np.count_nonzero(win_pred == "D"))
    alive_frames = team_stats["Barcelona"]["frames"] + team_stats["Athletic Club"]["frames"]
    for tname in ("Barcelona", "Athletic Club"):
        team_stats[tname]["possession_share_pct"] = (
            100.0 * team_stats[tname]["frames"] / alive_frames if alive_frames else 0.0
        )

    return {
        "total_frames": int(span_end - span_start),
        "alive_frames": int(alive_frames),
        "dead_frames": int(dead_frames),
        "dead_ratio_pct": (100.0 * dead_frames / (span_end - span_start)) if span_end > span_start else 0.0,
        "teams": team_stats,
    }


def _combine_phase_metrics(filled_labels, raw_labels, phase):
    """Aggregate metrics across one or more spans belonging to a game-state phase."""
    total_frames = 0
    dead_frames = 0
    all_runs = []
    # For each span, extract spell stats accurately without merging across halftime.
    span_results = []
    for a, b in phase["spans"]:
        total_frames += (b - a)
        span_results.append(_extract_spells_and_turnovers(filled_labels, raw_labels, a, b))

    combined_teams = {}
    for tname in ("Barcelona", "Athletic Club"):
        frames = sum(r["teams"][tname]["frames"] for r in span_results)
        n_sp = sum(r["teams"][tname]["n_spells"] for r in span_results)
        hp_sp = sum(r["teams"][tname]["high_pressure_spells"] for r in span_results)
        turns = sum(r["teams"][tname]["open_turnovers"] for r in span_results)

        def w_avg(key, weight_key):
            tot_w = sum(r["teams"][tname][weight_key] for r in span_results)
            if tot_w == 0:
                return 0.0
            return sum(r["teams"][tname][key] * r["teams"][tname][weight_key]
                       for r in span_results) / tot_w

        combined_teams[tname] = {
            "frames": frames,
            "n_spells": n_sp,
            "mean_spell_s": w_avg("mean_spell_s", "n_spells"),
            "median_spell_s": w_avg("median_spell_s", "n_spells"),
            "p90_spell_s": w_avg("p90_spell_s", "n_spells"),
            "high_pressure_spells": hp_sp,
            "press_resistance_index": w_avg("press_resistance_index", "high_pressure_spells"),
            "open_turnovers": turns,
            "counterpress_density_pct": w_avg("counterpress_density_pct", "open_turnovers"),
            "rapid_recovery_6s_pct": w_avg("rapid_recovery_6s_pct", "open_turnovers"),
            "cluster_buildup_pct": w_avg("cluster_buildup_pct", "n_spells"),
            "cluster_progression_pct": w_avg("cluster_progression_pct", "n_spells"),
            "cluster_transition_pct": w_avg("cluster_transition_pct", "n_spells"),
        }

    alive_frames = combined_teams["Barcelona"]["frames"] + combined_teams["Athletic Club"]["frames"]
    dead_frames = sum(r["dead_frames"] for r in span_results)
    for tname in ("Barcelona", "Athletic Club"):
        combined_teams[tname]["possession_share_pct"] = (
            100.0 * combined_teams[tname]["frames"] / alive_frames if alive_frames else 0.0
        )

    return {
        "phase_id": phase["phase_id"],
        "name": phase["name"],
        "short_name": phase["short_name"],
        "home_state": phase["home_state"],
        "away_state": phase.get("away_state", phase["home_state"]),
        "score_label": phase.get("score_label", ""),
        "duration_min": total_frames / (FPS * 60.0),
        "alive_frames": alive_frames,
        "dead_frames": dead_frames,
        "dead_ratio_pct": (100.0 * dead_frames / total_frames) if total_frames else 0.0,
        "teams": combined_teams,
    }


def _plot_figures(phase_rows, state_summary, scoreboard_df, out_dir):
    """Generate 3 high-resolution Vikzar editorial telemetry figures (300 DPI)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)
    PAGE_BG = "#F2E9E7"       # Warm Ivory canvas
    STONE_BG = "#E5DAD7"      # Subtle Warm Ivory card/legend surface
    GRID_COL = "#D6C9C5"      # Hairline grid / divider
    BORDER_COL = "#D6C9C5"
    INK = "#17191D"           # Graphite Ink
    MUTED = "#5A5255"         # Muted Graphite/Plum copy
    OXIDE_ROSE = "#9E5C55"    # Vikzar final model / FC Barcelona (H)
    OXIDE_ROSE_SUB = "#B67C76"
    MINERAL_BLUE = "#597C80"  # Athletic Club (A) / secondary series
    TAUPE = "#8E8684"         # Warm Taupe baselines
    PEWTER = "#5F5858"        # Baseline Floor & Stoppage curve

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "figure.facecolor": PAGE_BG,
        "axes.facecolor": PAGE_BG,
        "savefig.facecolor": PAGE_BG,
        "axes.edgecolor": BORDER_COL,
        "axes.linewidth": 0.75,
        "grid.color": GRID_COL,
        "grid.linestyle": "-",
        "grid.linewidth": 0.6,
        "text.color": INK,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
    })

    def _style_legend(leg):
        leg.get_frame().set_facecolor(STONE_BG)
        leg.get_frame().set_edgecolor(BORDER_COL)
        leg.get_frame().set_linewidth(0.75)
        for txt in leg.get_texts():
            txt.set_color(INK)

    def _despine(ax, keep_right=False):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(keep_right)
        ax.spines["left"].set_color(BORDER_COL)
        ax.spines["bottom"].set_color(BORDER_COL)
        if keep_right:
            ax.spines["right"].set_color(BORDER_COL)

    # ── Figure 1: Scoreboard Comparison (spellF1, macroF1, f1_D) ─────────────
    if scoreboard_df is not None and len(scoreboard_df) > 0:
        candidate_order = [
            ("baseline_raw", "Raw\n(Base)", TAUPE),
            ("baseline_smooth25", "Smooth\n±25f", TAUPE),
            ("baseline_smooth50", "Floor\n±50f", PEWTER),
            ("baseline_smooth125", "Smooth\n±125f", TAUPE),
            ("vikzar_v2_1", "Vikzar\nV2.1", OXIDE_ROSE_SUB),
            ("vikzar_v2_2", "Vikzar\nV2.2", OXIDE_ROSE),
            ("vikzar", "Vikzar\nFinal", OXIDE_ROSE),
        ]
        present = [(k, lbl, col) for k, lbl, col in candidate_order
                   if k in scoreboard_df["submission"].values]
        present_keys = {p[0] for p in present}
        if "vikzar_v2_2" in present_keys:
            present = [p for p in present if p[0] != "vikzar"]
        sub_df = scoreboard_df.set_index("submission").reindex([p[0] for p in present])
        labels_x = [p[1] for p in present]
        colors = [p[2] for p in present]

        fig, axes = plt.subplots(1, 3, figsize=(13.8, 4.3), dpi=300, facecolor=PAGE_BG)

        metrics = [
            ("spell_f1_mean", "Possession Spell F1 (spellF1)"),
            ("macro_f1", "Framewise Macro-F1 (macroF1)"),
            ("f1_D", "Dead-Ball F1 (f1_D)"),
        ]
        for ax, (col, title) in zip(axes, metrics):
            ax.set_facecolor(PAGE_BG)
            vals = sub_df[col].to_numpy(dtype=float)
            bars = ax.bar(range(len(vals)), vals, color=colors, width=0.58, zorder=3,
                          edgecolor=PAGE_BG, linewidth=0.5)
            ax.set_title(title, fontsize=10.6, fontweight="bold", pad=12, color=INK)
            ax.set_xticks(range(len(vals)))
            ax.set_xticklabels(labels_x, fontsize=8.2, color=MUTED)
            ax.tick_params(axis="y", colors=MUTED, labelsize=8.4)
            ax.set_ylim(0, max(vals) * 1.24)
            ax.grid(axis="y", zorder=0)
            _despine(ax)
            for idx_b, (bar, v) in enumerate(zip(bars, vals)):
                lbl_col = OXIDE_ROSE if idx_b == len(bars) - 1 else INK
                ax.text(bar.get_x() + bar.get_width() / 2.0, v + max(vals) * 0.025, f"{v:.3f}",
                        ha="center", va="bottom", fontsize=8.2, fontweight="bold", color=lbl_col)

        fig.suptitle("03 / PUBLIC BENCHMARK — VIKZAR vs OFFICIAL BASELINES (ZERO PUBLIC TUNING)",
                     fontsize=11.0, fontweight="bold", y=1.02, color=INK)
        fig.tight_layout(pad=1.6)
        fig.savefig(os.path.join(out_dir, "fig1_scoreboard_comparison.png"),
                    dpi=300, bbox_inches="tight", facecolor=PAGE_BG)
        plt.close(fig)

    # ── Figure 2: Live Match Game-State Dynamics (Drawing / Leading / Trailing) ─
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 4.6), dpi=300, facecolor=PAGE_BG)
    x = np.arange(len(phase_rows))
    p_labels = [p["short_name"] for p in phase_rows]
    barca_poss = [p["teams"]["Barcelona"]["possession_share_pct"] for p in phase_rows]
    ath_poss = [p["teams"]["Athletic Club"]["possession_share_pct"] for p in phase_rows]
    barca_dur = [p["teams"]["Barcelona"]["mean_spell_s"] for p in phase_rows]
    ath_dur = [p["teams"]["Athletic Club"]["mean_spell_s"] for p in phase_rows]
    dead_pct = [p["dead_ratio_pct"] for p in phase_rows]

    w = 0.34
    ax1.set_facecolor(PAGE_BG)
    b1 = ax1.bar(x - w/2, barca_poss, width=w, label="Barcelona (H)", color=OXIDE_ROSE, zorder=3)
    b2 = ax1.bar(x + w/2, ath_poss, width=w, label="Athletic Club (A)", color=MINERAL_BLUE, zorder=3)
    ax1_t = ax1.twinx()
    ax1_t.plot(x, dead_pct, color=PEWTER, marker="o", markersize=5.0, linewidth=1.8,
               linestyle="--", label="Stoppage % (D)", zorder=4)
    ax1.set_title("Possession Share & Dead-Ball Ratio by Game State", fontsize=10.5, fontweight="bold", pad=12, color=INK)
    ax1.set_xticks(x)
    ax1.set_xticklabels(p_labels, fontsize=7.6, color=MUTED)
    ax1.set_ylabel("Live Possession Share (%)", fontsize=8.8, color=MUTED)
    ax1_t.set_ylabel("Stoppage Ratio (% of Phase)", fontsize=8.8, color=PEWTER)
    ax1.tick_params(axis="y", colors=MUTED, labelsize=8.2)
    ax1_t.tick_params(axis="y", colors=PEWTER, labelsize=8.2)
    ax1.set_ylim(0, 86)
    ax1_t.set_ylim(0, 82)
    ax1.grid(axis="y", zorder=0)
    _despine(ax1, keep_right=False)
    _despine(ax1_t, keep_right=True)
    ax1_t.spines["left"].set_visible(False)
    scale_t = 82.0 / 86.0
    for bar in b1:
        ax1_t.text(bar.get_x() + bar.get_width()/2, (bar.get_height() + 1.5) * scale_t,
                   f"{bar.get_height():.1f}%", ha="center", va="bottom",
                   fontsize=7.3, fontweight="bold", color=OXIDE_ROSE, zorder=10,
                   bbox=dict(boxstyle="round,pad=0.12", facecolor=PAGE_BG, edgecolor="none", alpha=0.92))
    for bar in b2:
        ax1_t.text(bar.get_x() + bar.get_width()/2, (bar.get_height() + 1.5) * scale_t,
                   f"{bar.get_height():.1f}%", ha="center", va="bottom",
                   fontsize=7.3, fontweight="bold", color=MINERAL_BLUE, zorder=10,
                   bbox=dict(boxstyle="round,pad=0.12", facecolor=PAGE_BG, edgecolor="none", alpha=0.92))
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1_t.get_legend_handles_labels()
    _style_legend(ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=7.5))

    ax2.set_facecolor(PAGE_BG)
    d1 = ax2.bar(x - w/2, barca_dur, width=w, label="Barcelona (H)", color=OXIDE_ROSE, zorder=3)
    d2 = ax2.bar(x + w/2, ath_dur, width=w, label="Athletic Club (A)", color=MINERAL_BLUE, zorder=3)
    ax2.set_title("Mean Possession Spell Duration by Game State", fontsize=10.5, fontweight="bold", pad=12, color=INK)
    ax2.set_xticks(x)
    ax2.set_xticklabels(p_labels, fontsize=7.6, color=MUTED)
    ax2.set_ylabel("Mean Spell Duration (seconds)", fontsize=8.8, color=MUTED)
    ax2.tick_params(axis="y", colors=MUTED, labelsize=8.2)
    ax2.set_ylim(0, max(max(barca_dur), max(ath_dur)) * 1.28)
    ax2.grid(axis="y", zorder=0)
    _despine(ax2)
    for bar in d1:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.25, f"{bar.get_height():.1f}s",
                 ha="center", fontsize=7.5, fontweight="bold", color=OXIDE_ROSE)
    for bar in d2:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.25, f"{bar.get_height():.1f}s",
                 ha="center", fontsize=7.5, fontweight="bold", color=MINERAL_BLUE)
    _style_legend(ax2.legend(loc="upper right", fontsize=7.8))

    fig.suptitle("04 / GAME-STATE PHASES (DRAWING / LEADING / TRAILING) — SMART TAGGING GOALS + RESTARTS",
                 fontsize=10.8, fontweight="bold", y=1.02, color=INK)
    fig.tight_layout(pad=1.6)
    fig.savefig(os.path.join(out_dir, "fig2_gamestate_dynamics.png"),
                dpi=300, bbox_inches="tight", facecolor=PAGE_BG)
    plt.close(fig)

    # ── Figure 3: Role-Clustered Recruitment Profiles (Drawing/Leading/Trailing) ─
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 4.65), dpi=300, facecolor=PAGE_BG)
    states = ["Drawing", "Leading", "Trailing"]
    x_s = np.arange(len(states)) * 1.18
    bw = 0.215

    b_pri = [state_summary[s]["Barcelona"]["press_resistance_index"] for s in states]
    a_pri = [state_summary[s]["Athletic Club"]["press_resistance_index"] for s in states]
    b_rec = [state_summary[s]["Barcelona"]["rapid_recovery_6s_pct"] for s in states]
    a_rec = [state_summary[s]["Athletic Club"]["rapid_recovery_6s_pct"] for s in states]

    ax1.set_facecolor(PAGE_BG)
    bars_p1 = ax1.bar(x_s - 1.56 * bw, b_pri, width=bw * 0.92, label="Barça PRI (%)", color=OXIDE_ROSE, zorder=3)
    bars_p2 = ax1.bar(x_s - 0.52 * bw, a_pri, width=bw * 0.92, label="Athletic PRI (%)", color=MINERAL_BLUE, zorder=3)
    bars_p3 = ax1.bar(x_s + 0.52 * bw, b_rec, width=bw * 0.92, label="Barça Recovery <6s (%)",
                      color=OXIDE_ROSE_SUB, hatch="//", edgecolor=PAGE_BG, linewidth=0.6, zorder=3)
    bars_p4 = ax1.bar(x_s + 1.56 * bw, a_rec, width=bw * 0.92, label="Athletic Recovery <6s (%)",
                      color=TAUPE, hatch="//", edgecolor=PAGE_BG, linewidth=0.6, zorder=3)
    for bar_group in (bars_p1, bars_p2, bars_p3, bars_p4):
        for bar in bar_group:
            v = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2, v + 1.4, f"{v:.1f}%",
                     ha="center", va="bottom", fontsize=6.7, fontweight="bold", color=INK)
    ax1.set_xticks(x_s)
    ax1.set_xticklabels(["Drawing\n(Score Tied)", "Leading\n(Team Ahead)", "Trailing\n(Team Behind)"],
                        fontsize=8.3, color=MUTED)
    ax1.set_ylabel("Percentage (%)", fontsize=8.8, color=MUTED)
    ax1.tick_params(axis="y", colors=MUTED, labelsize=8.2)
    ax1.set_ylim(0, max(max(b_pri), max(a_pri), max(b_rec), max(a_rec), 60) * 1.28)
    ax1.set_title("Press-Resistance (PRI) & <6s Recovery by Game State", fontsize=10.3, fontweight="bold", pad=12, color=INK)
    ax1.grid(axis="y", zorder=0)
    _despine(ax1)
    _style_legend(ax1.legend(loc="upper right", fontsize=7.3, ncol=2))

    c_build = [state_summary[s]["Barcelona"]["cluster_buildup_pct"] for s in states]
    c_prog = [state_summary[s]["Barcelona"]["cluster_progression_pct"] for s in states]
    c_trans = [state_summary[s]["Barcelona"]["cluster_transition_pct"] for s in states]

    ax2.set_facecolor(PAGE_BG)
    x_r = np.arange(len(states))
    ax2.bar(x_r, c_build, width=0.46, label="Cluster 1: Deep Build-Up / Pivot (>15s)", color=OXIDE_ROSE, zorder=3)
    ax2.bar(x_r, c_prog, width=0.46, bottom=c_build, label="Cluster 2: Central Progression (6–15s)", color=MINERAL_BLUE, zorder=3)
    bottom2 = [b + p for b, p in zip(c_build, c_prog)]
    ax2.bar(x_r, c_trans, width=0.46, bottom=bottom2, label="Cluster 3: Direct / Box-Entry (<6s)", color=TAUPE, zorder=3)
    ax2.set_xticks(x_r)
    ax2.set_xticklabels(["Drawing\n(Score Tied)", "Leading\n(Team Ahead)", "Trailing\n(Team Behind)"],
                        fontsize=8.3, color=MUTED)
    ax2.set_ylabel("Share of Possession Spells (%)", fontsize=8.8, color=MUTED)
    ax2.tick_params(axis="y", colors=MUTED, labelsize=8.2)
    ax2.set_ylim(0, 132)
    ax2.set_title("Barcelona Role-Cluster Shift: Drawing / Leading / Trailing", fontsize=10.3, fontweight="bold", pad=12, color=INK)
    ax2.grid(axis="y", zorder=0)
    _despine(ax2)
    _style_legend(ax2.legend(loc="upper right", fontsize=7.4))

    for i in range(len(states)):
        if c_build[i] >= 6.0:
            ax2.text(x_r[i], c_build[i]/2, f"{c_build[i]:.1f}%", ha="center", va="center", color=PAGE_BG, fontweight="bold", fontsize=8.4)
        if c_prog[i] >= 6.0:
            ax2.text(x_r[i], c_build[i] + c_prog[i]/2, f"{c_prog[i]:.1f}%", ha="center", va="center", color=PAGE_BG, fontweight="bold", fontsize=8.4)
        if c_trans[i] >= 6.0:
            ax2.text(x_r[i], bottom2[i] + c_trans[i]/2, f"{c_trans[i]:.1f}%", ha="center", va="center", color=INK, fontweight="bold", fontsize=8.4)

    fig.suptitle("05 / RECRUITMENT PROFILING BY LIVE GAME STATE — DRAWING vs. LEADING vs. TRAILING",
                 fontsize=10.8, fontweight="bold", y=1.02, color=INK)
    fig.tight_layout(pad=1.6)
    fig.savefig(os.path.join(out_dir, "fig3_recruitment_profiles.png"),
                dpi=300, bbox_inches="tight", facecolor=PAGE_BG)
    plt.close(fig)


def run_analysis(submission_csv, raw_csv, out_dir):
    import pandas as pd

    pred_df = pd.read_csv(submission_csv)
    raw_df = pd.read_csv(raw_csv)
    pred_labels = pred_df["label"].astype(str).to_numpy()
    raw_labels = raw_df["label"].astype(str).to_numpy()
    half_blocks = half_video_blocks(GAME)
    filled_labels = _fill_x_within_blocks(pred_labels, half_blocks)

    smart_path = None
    try:
        smart_path = require(["smart_tagging"], GAME)[0]
    except IOError:
        smart_path = None

    phases, phase_source = detect_game_state_phases(filled_labels, half_blocks, smart_path)
    phase_rows = [_combine_phase_metrics(filled_labels, raw_labels, p) for p in phases]

    # Aggregate into consolidated team-perspective Game States (Drawing / Leading / Trailing)
    state_summary = {}
    for st_name in ("Drawing", "Leading", "Trailing"):
        state_summary[st_name] = {}
        for tname, state_key in (("Barcelona", "home_state"), ("Athletic Club", "away_state")):
            merged_spans = []
            for p in phases:
                if p.get(state_key) == st_name:
                    merged_spans.extend(p["spans"])
            if merged_spans:
                merged_phase = {
                    "phase_id": 0,
                    "name": f"{tname} ({st_name})",
                    "short_name": st_name,
                    "home_state": st_name,
                    "away_state": st_name,
                    "score_label": "",
                    "spans": merged_spans,
                }
                agg = _combine_phase_metrics(filled_labels, raw_labels, merged_phase)
                team_dict = dict(agg["teams"][tname])
                team_dict["duration_min"] = agg["duration_min"]
                team_dict["dead_ratio_pct"] = agg["dead_ratio_pct"]
                state_summary[st_name][tname] = team_dict
            else:
                state_summary[st_name][tname] = {
                    "frames": 0, "n_spells": 0, "mean_spell_s": 0.0, "median_spell_s": 0.0,
                    "p90_spell_s": 0.0, "high_pressure_spells": 0, "press_resistance_index": 0.0,
                    "open_turnovers": 0, "counterpress_density_pct": 0.0, "rapid_recovery_6s_pct": 0.0,
                    "cluster_buildup_pct": 0.0, "cluster_progression_pct": 0.0,
                    "cluster_transition_pct": 0.0, "possession_share_pct": 0.0,
                    "duration_min": 0.0, "dead_ratio_pct": 0.0,
                }

    os.makedirs(out_dir, exist_ok=True)
    flat_rows = []
    for pr in phase_rows:
        for tname in ("Barcelona", "Athletic Club"):
            row = {
                "phase_id": pr["phase_id"],
                "phase": pr["short_name"],
                "score": pr.get("score_label", ""),
                "home_game_state": pr["home_state"],
                "away_game_state": pr.get("away_state", pr["home_state"]),
                "duration_min": round(pr["duration_min"], 2),
                "dead_ratio_pct": round(pr["dead_ratio_pct"], 2),
                "team": tname,
                "team_game_state": pr["home_state"] if tname == "Barcelona" else pr.get("away_state", pr["home_state"]),
            }
            for k, v in pr["teams"][tname].items():
                row[k] = round(v, 2) if isinstance(v, float) else v
            flat_rows.append(row)

    metrics_df = pd.DataFrame(flat_rows)
    metrics_df.to_csv(os.path.join(out_dir, "gamestate_metrics.csv"), index=False)

    payload = {
        "phase_detection_source": phase_source,
        "phases": phase_rows,
        "consolidated_states": state_summary,
    }
    with open(os.path.join(out_dir, "gamestate_summary.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    repo_root = os.path.dirname(os.path.abspath(__file__))
    sb_path = os.path.join(repo_root, "evaluation", "scoreboard.csv")
    sb_df = pd.read_csv(sb_path) if os.path.isfile(sb_path) else None
    _plot_figures(phase_rows, state_summary, sb_df, out_dir)
    return payload, metrics_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run game-state and recruitment analysis.")
    parser.add_argument("--submission", default="submission_artifacts/vikzar.csv")
    parser.add_argument("--raw", default="evaluation/results/baseline_raw.csv")
    parser.add_argument("--out-dir", default="figures")
    args = parser.parse_args()
    payload, df = run_analysis(args.submission, args.raw, args.out_dir)
    print("Phase detection source:", payload["phase_detection_source"])
    print(df[["phase", "team", "possession_share_pct", "n_spells", "mean_spell_s",
              "press_resistance_index", "rapid_recovery_6s_pct"]].to_string(index=False))
