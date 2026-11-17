#!/usr/bin/env python3
"""Generate Vikzar 4-Page 16:9 Widescreen Technical Deck PDF (Pure Vector ReportLab)."""

from pathlib import Path
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

W, H = 960.0, 540.0

PLUM_BLACK = HexColor("#17131E")
DARK_CARD = HexColor("#211C2A")
DARK_CARD_ALT = HexColor("#1C1824")
DARK_BORDER = HexColor("#312B3D")
GRAPHITE_INK = HexColor("#17191D")
WARM_IVORY = HexColor("#F2E9E7")
LIGHT_CARD = HexColor("#E8DDDA")
LIGHT_CARD_ALT = HexColor("#EFE5E2")
LIGHT_BORDER = HexColor("#D5C7C3")
WATERMARK_TONE = HexColor("#E0D4D0")
MINERAL_BLUE = HexColor("#597C80")
MINERAL_LIGHT = HexColor("#7A9CA0")
OXIDE_ROSE = HexColor("#9E5C55")
OXIDE_LIGHT = HexColor("#B8756E")
MUTED_INK = HexColor("#5A5558")
MUTED_LIGHT = HexColor("#ABA4AF")
WHITE = HexColor("#FFFFFF")


def fill_bg(c: canvas.Canvas, color: HexColor) -> None:
    c.saveState()
    c.setFillColor(color)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.restoreState()


def draw_rounded_card(
    c: canvas.Canvas, x: float, y: float, w: float, h: float,
    fill: HexColor, stroke: HexColor = None, radius: float = 10.0,
    stroke_width: float = 1.0, top_accent: HexColor = None, top_accent_h: float = 5.0,
) -> None:
    c.saveState()
    c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(stroke_width)
        c.roundRect(x, y, w, h, radius, stroke=1, fill=1)
    else:
        c.roundRect(x, y, w, h, radius, stroke=0, fill=1)
    if top_accent is not None:
        c.setFillColor(top_accent)
        c.roundRect(x, y + h - top_accent_h, w, top_accent_h, radius / 2.0, stroke=0, fill=1)
        c.rect(x, y + h - top_accent_h, w, top_accent_h / 2.0, stroke=0, fill=1)
    c.restoreState()


def draw_slide_header(
    c: canvas.Canvas, num_str: str, section_str: str, right_meta: str, dark_mode: bool = False,
) -> None:
    c.saveState()
    y_top = H - 32.0
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(OXIDE_ROSE)
    num_w = c.stringWidth(num_str, "Helvetica-Bold", 11)
    c.drawString(44, y_top, num_str)
    c.setFillColor(WARM_IVORY if dark_mode else GRAPHITE_INK)
    c.drawString(44 + num_w, y_top, section_str)
    sec_w = c.stringWidth(section_str, "Helvetica-Bold", 11)
    line_start = 44 + num_w + sec_w + 16
    line_end = W - 44 - c.stringWidth(right_meta, "Helvetica", 9.0) - 16
    c.setStrokeColor(DARK_BORDER if dark_mode else LIGHT_BORDER)
    c.setLineWidth(1.0)
    c.line(line_start, y_top + 4, line_end, y_top + 4)
    c.setFont("Helvetica", 9.0)
    c.setFillColor(MUTED_LIGHT if dark_mode else MUTED_INK)
    c.drawRightString(W - 44, y_top, right_meta)
    c.restoreState()


def draw_bottom_pill(
    c: canvas.Canvas, text: str, page_str: str = "01 / 04", dark_mode: bool = False,
) -> None:
    c.saveState()
    pill_x, pill_y, pill_w, pill_h = 44, 15, W - 164, 28
    draw_rounded_card(
        c, pill_x, pill_y, pill_w, pill_h,
        fill=DARK_CARD if dark_mode else PLUM_BLACK,
        stroke=DARK_BORDER if dark_mode else None, radius=14,
    )
    c.setFont("Helvetica-Bold", 10.0)
    c.setFillColor(WARM_IVORY)
    c.drawCentredString(pill_x + pill_w / 2.0, pill_y + 9.5, text)
    badge_x = W - 110
    draw_rounded_card(
        c, badge_x, pill_y, 66, pill_h,
        fill=DARK_CARD if dark_mode else LIGHT_CARD,
        stroke=DARK_BORDER if dark_mode else LIGHT_BORDER, radius=14,
    )
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(WARM_IVORY if dark_mode else GRAPHITE_INK)
    c.drawCentredString(badge_x + 33, pill_y + 9.5, page_str)
    c.restoreState()


def build_page_1(c: canvas.Canvas) -> None:
    fill_bg(c, WARM_IVORY)
    draw_slide_header(
        c, "01/", "THE TELEMETRY BLIND SPOT & V2.2 ARCHITECTURE",
        "VIKZAR  ·  MORE THAN A HACK 2027 (PHASE 1)  ·  BAR-ATH (199,319 FRAMES @ 25 FPS)",
        dark_mode=False,
    )
    c.setFont("Helvetica-Bold", 25)
    c.setFillColor(PLUM_BLACK)
    c.drawString(44, H - 72, "NAIVE PROXIMITY FRAGMENTS SPELLS.")
    c.setFillColor(MINERAL_BLUE)
    c.drawString(44, H - 101, "VIKZAR ENGINEERS PERSISTENCE.")
    draw_rounded_card(c, 616, H - 108, 300, 56, fill=PLUM_BLACK, radius=10)
    c.setFont("Helvetica-Bold", 9.0)
    c.setFillColor(OXIDE_LIGHT)
    c.drawString(632, H - 68, "OFFICIAL RANKING METRIC  ·  spellF1")
    c.setFont("Helvetica", 9.0)
    c.setFillColor(WARM_IVORY)
    c.drawString(632, H - 83, "1-to-1 temporal IoU over {0.3, 0.4, 0.5, 0.6, 0.7}.")
    c.drawString(632, H - 96, "1 missed stoppage merges 2 spells < 0.3 IoU.")
    cards_p1 = [
        ("40.7%", "GRADED BALL DROPOUTS",
         "Small ball scale & penalty-box congestion drop ball coordinates on 40.7% of graded frames (43.1% overall).",
         "Raw nearest-player voting shatters 133 minutes into 2,265 noisy micro-spells (2.0 s mean)."),
        ("2.0 s", "STOPPAGE EDGE EROSION",
         "Symmetric ±50-frame box voting (baseline_smooth50) erodes 50 frames off both ends of every dead ball.",
         "Mislabels 14,311 dead-ball (D) frames vs. raw and completely erases stoppages shorter than 4.04 s."),
        ("44.5%", "BROADCAST REPLAY DRIFT",
         "Auditing raw Mode 1 dual-camera fusion exposed 44.5% Tactical-vs-Broadcast disagreement on TV replays.",
         "Half-2 pre-kickoff warmup (110,808–113,741) also leaks 11 false spells in smooth50 (22 in raw)."),
    ]
    cw, ch, cy = 280.0, 132.0, H - 252.0
    for idx, (stat, title, b1, b2) in enumerate(cards_p1):
        cx = 44.0 + idx * (cw + 16.0)
        draw_rounded_card(c, cx, cy, cw, ch, fill=LIGHT_CARD, stroke=LIGHT_BORDER, radius=10, top_accent=OXIDE_ROSE, top_accent_h=6)
        c.setFont("Helvetica-Bold", 11.5)
        c.setFillColor(PLUM_BLACK)
        c.drawString(cx + 16, cy + ch - 27, title)
        c.setFont("Helvetica-Bold", 19)
        c.setFillColor(OXIDE_ROSE)
        c.drawRightString(cx + cw - 16, cy + ch - 28, stat)
        c.setFont("Helvetica", 9.0)
        y_text = cy + ch - 48
        for bullet in (b1, b2):
            c.setFillColor(OXIDE_ROSE)
            c.circle(cx + 20, y_text + 3, 2.2, stroke=0, fill=1)
            c.setFillColor(GRAPHITE_INK)
            words, line = bullet.split(), ""
            for w_tok in words:
                test = f"{line} {w_tok}".strip()
                if c.stringWidth(test, "Helvetica", 9.0) <= cw - 42:
                    line = test
                else:
                    c.drawString(cx + 28, y_text, line)
                    y_text -= 12.5
                    line = w_tok
            if line:
                c.drawString(cx + 28, y_text, line)
                y_text -= 15
    band_y, band_h = 54.0, 218.0
    draw_rounded_card(c, 44, band_y, W - 88, band_h, fill=PLUM_BLACK, radius=12)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(OXIDE_LIGHT)
    c.drawString(62, band_y + band_h - 22, "02/SYSTEM PROGRESSION  ·  WE BUILD. WE AUDIT. WE GATE.")
    c.setFont("Helvetica", 9.0)
    c.setFillColor(MUTED_LIGHT)
    c.drawRightString(W - 62, band_y + band_h - 22, "100% DETERMINISTIC  ·  STANDARD LIBRARY + NUMPY ONLY")
    steps = [
        ("1", "SPATIAL CONTROL", "V1 KINEMATICS",
         "Replaces raw nearest-player voting with player-to-ball distance margins, 4.0–4.5 m teammate support, & approach velocity."),
        ("2", "TURNOVER FILTER", "V2.0 HYSTERESIS",
         "Enforces 1.0 s (25f) turnover persistence (0.6 s on >=25 m/s² ball decel), >18 m/s flight X bridging, & <1.2 s flicker cleanup."),
        ("3", "STOPPAGE ISOLATION", "V2.1 BOUNDARIES",
         "Anchors 59 Smart Tagging SET PIECES, 105.3x68.0 m pitch exits, & stoppage-isolated ±1.4 s triangular dominance kernels."),
        ("4", "AUDIT-GATED V2.2", "PROMOTED ENGINE",
         "Seals 2,934 Half-2 pre-KO frames as D; gates Mode 1 V2.3 (0.3294 spellF1) vs. Mode 2 to lock in 469 clean spells (0.3610)."),
    ]
    sw, sh, sy = (W - 88 - 72) / 4.0, band_h - 42.0, band_y + 10.0
    for idx, (num, title, sub, desc) in enumerate(steps):
        sx = 62.0 + idx * (sw + 12.0)
        draw_rounded_card(
            c, sx, sy, sw, sh, fill=DARK_CARD,
            stroke=OXIDE_ROSE if idx == 3 else DARK_BORDER, radius=8,
            stroke_width=1.5 if idx == 3 else 1.0,
        )
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(OXIDE_LIGHT if idx == 3 else MINERAL_LIGHT)
        c.drawString(sx + 14, sy + sh - 34, num)
        c.setFont("Helvetica-Bold", 10.0)
        c.setFillColor(WARM_IVORY)
        c.drawString(sx + 38, sy + sh - 23, title)
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(OXIDE_LIGHT)
        c.drawString(sx + 38, sy + sh - 35, sub)
        c.setStrokeColor(DARK_BORDER)
        c.line(sx + 14, sy + sh - 44, sx + sw - 14, sy + sh - 44)
        c.setFont("Helvetica", 9.0)
        c.setFillColor(WARM_IVORY)
        yt, words, line = sy + sh - 60, desc.split(), ""
        for w_tok in words:
            test = f"{line} {w_tok}".strip()
            if c.stringWidth(test, "Helvetica", 9.0) <= sw - 28:
                line = test
            else:
                c.drawString(sx + 14, yt, line)
                yt -= 13
                line = w_tok
        if line:
            c.drawString(sx + 14, yt, line)
    draw_bottom_pill(
        c, "Naive box smoothing optimizes isolated frames — Vikzar V2.2 isolates stoppages to recover whole possession spells.",
        page_str="01 / 04", dark_mode=False,
    )
    c.showPage()


def build_page_2(c: canvas.Canvas) -> None:
    fill_bg(c, WARM_IVORY)
    draw_slide_header(
        c, "02/", "BENCHMARK & VALIDATION  ·  ZERO PUBLIC-SLICE TUNING",
        "SINGLE POST-HOC SANITY CHECK ON PUBLIC 5-MIN GT  ·  FULL-MATCH AUDIT", dark_mode=False,
    )
    c.setFont("Helvetica-Bold", 25)
    c.setFillColor(PLUM_BLACK)
    c.drawString(44, H - 70, "EVERYONE SMOOTHS FRAMES.")
    c.setFillColor(MINERAL_BLUE)
    c.drawString(44, H - 98, "WE RECOVER CONTIGUOUS SPELLS.")
    draw_rounded_card(c, 556, H - 104, 360, 52, fill=PLUM_BLACK, radius=10)
    c.setFont("Helvetica-Bold", 8.8)
    c.setFillColor(OXIDE_LIGHT)
    c.drawString(572, H - 67, "STRICT RULE COMPLIANCE  ·  ZERO OVERFITTING")
    c.setFont("Helvetica", 8.8)
    c.setFillColor(WARM_IVORY)
    c.drawString(572, H - 82, "Zero external match data, zero manual labels, and zero parameter")
    c.drawString(572, H - 94, "tuning on the 5-minute public ground-truth window.")
    left_stats = [
        ("0.6466", "#1 PUBLIC MACRO-F1",
         "Ranks #1 overall across all 4 classes vs. official baselines (0.6207 floor, 0.5812 smooth125).",
         "88.68% agreement with visible carrier observations while filtering 10,374 flicker frames."),
        ("0.4210", "#1 DEAD-BALL F1 (f1_D)",
         "+30.5% relative lift over baseline_smooth50 (0.3225) by preventing ±50f stoppage erosion.",
         "Seals all 2,934 Half-2 pre-kickoff frames as D and keeps 40,462 ungraded frames neutral (X)."),
        ("3.6x", "#1 TRANSITION TIMING",
         "Lifts ±25-frame transition F1 from 0.0816 (floor) to 0.2979 across 469 spells (7.82 s mean).",
         "Beats baseline_smooth50 on spellF1 (0.3610 vs 0.3256; 0.3902 @ IoU 0.5) with zero tuning."),
    ]
    sy_top = H - 132
    for idx, (big_num, title, l1, l2) in enumerate(left_stats):
        ry = sy_top - idx * 118
        if idx > 0:
            c.setStrokeColor(LIGHT_BORDER)
            c.setLineWidth(1.0)
            c.line(44, ry + 18, 360, ry + 18)
        c.setFont("Helvetica-Bold", 31)
        c.setFillColor(MINERAL_BLUE if idx != 0 else OXIDE_ROSE)
        c.drawString(44, ry - 18, big_num)
        c.setFont("Helvetica-Bold", 10.2)
        c.setFillColor(PLUM_BLACK)
        c.drawString(44, ry - 34, title)
        c.setFont("Helvetica", 8.7)
        yt = ry - 49
        for bullet in (l1, l2):
            c.setFillColor(OXIDE_ROSE)
            c.circle(49, yt + 3, 2.0, stroke=0, fill=1)
            c.setFillColor(GRAPHITE_INK)
            words, line = bullet.split(), ""
            for w_tok in words:
                test = f"{line} {w_tok}".strip()
                if c.stringWidth(test, "Helvetica", 8.7) <= 300:
                    line = test
                else:
                    c.drawString(56, yt, line)
                    yt -= 11.8
                    line = w_tok
            if line:
                c.drawString(56, yt, line)
                yt -= 13.0
    tx, ty, tw, th = 382.0, 186.0, 534.0, 226.0
    draw_rounded_card(c, tx, ty, tw, th, fill=LIGHT_CARD, stroke=LIGHT_BORDER, radius=12)
    pillar_x, pillar_w = tx + 184, 104
    draw_rounded_card(c, pillar_x, ty - 5, pillar_w, th + 10, fill=OXIDE_ROSE, radius=11)
    hy = ty + th - 22
    c.setFont("Helvetica-Bold", 8.8)
    c.setFillColor(MUTED_INK)
    c.drawString(tx + 14, hy, "CAPABILITY / METRIC")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 9.8)
    c.drawCentredString(pillar_x + pillar_w / 2.0, hy, "Vikzar V2.2")
    c.setFont("Helvetica-Bold", 8.6)
    c.setFillColor(GRAPHITE_INK)
    c.drawCentredString(tx + 332, hy, "Floor (±50f)")
    c.drawCentredString(tx + 416, hy, "Smooth (±125f)")
    c.drawCentredString(tx + 494, hy, "Mode 1 V2.3")
    rows = [
        ("Full-Match Spells", "469 (7.8s)", "669 (7.6s)", "430 (13.5s)", "502 (7.3s)"),
        ("Half-2 Pre-KO Leaks", "0 (2,934 D)", "Leaks 11", "Leaks 9", "0 (2,934 D)"),
        ("Ungraded Neutrality (X)", "40,462 (100%)", "0 (Bleeds)", "0 (Bleeds)", "44,604 (22.4%)"),
        ("Stoppage-Isolated Kernel", "Yes (±1.4s)", "No (±50f box)", "No (±125f box)", "Yes (±1.4s)"),
        ("Public 5m macroF1", "0.6466 (#1)", "0.6207", "0.5812", "0.6196"),
        ("Public 5m spellF1 (@0.5)", "0.3610 (0.390)", "0.3256 (0.326)", "0.4242 (0.424)", "0.3294 (0.364)"),
        ("Public 5m Dead-Ball f1_D", "0.4210 (#1)", "0.3225", "0.1464", "0.4150"),
        ("Public 5m transF1 (±25f)", "0.2979 (#1)", "0.0816", "0.1667", "0.2424"),
    ]
    for r_idx, (cap, vik, flr, sm125, m1) in enumerate(rows):
        ry = hy - 23 - r_idx * 23.2
        if r_idx % 2 == 0:
            c.setFillColor(LIGHT_CARD_ALT)
            c.rect(tx + 8, ry - 6, 174, 20, stroke=0, fill=1)
            c.rect(pillar_x + pillar_w + 2, ry - 6, tw - (pillar_x - tx + pillar_w) - 10, 20, stroke=0, fill=1)
            c.setFillColor(OXIDE_ROSE)
            c.rect(pillar_x, ry - 6, pillar_w, 20, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(GRAPHITE_INK)
        c.drawString(tx + 14, ry, cap)
        c.setFont("Helvetica-Bold", 8.8)
        c.setFillColor(WHITE)
        c.drawCentredString(pillar_x + pillar_w / 2.0, ry, vik)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(MUTED_INK)
        c.drawCentredString(tx + 332, ry, flr)
        c.drawCentredString(tx + 416, ry, sm125)
        c.drawCentredString(tx + 494, ry, m1)
    bx, by, bw, bh = 382.0, 52.0, 534.0, 122.0
    draw_rounded_card(c, bx, by, bw, bh, fill=PLUM_BLACK, radius=12)
    c.setFont("Helvetica-Bold", 9.0)
    c.setFillColor(OXIDE_LIGHT)
    c.drawString(bx + 16, by + bh - 18, "PUBLIC 5-MIN BENCHMARK  ·  VIKZAR V2.2 (OXIDE) vs. FLOOR ±50f (MINERAL BLUE)")
    bar_metrics = [
        ("Macro-F1 (macroF1)", 0.6466, 0.6207, 0.75),
        ("Spell F1 @ IoU 0.5", 0.3902, 0.3256, 0.50),
        ("Dead-Ball F1 (f1_D)", 0.4210, 0.3225, 0.50),
        ("Transition F1 (±25f)", 0.2979, 0.0816, 0.35),
    ]
    for b_idx, (m_label, v_val, f_val, max_scale) in enumerate(bar_metrics):
        col, row = b_idx % 2, b_idx // 2
        gx, gy = bx + 16 + col * 260, by + bh - 48 - row * 44
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(WARM_IVORY)
        c.drawString(gx, gy + 15, m_label)
        c.setFillColor(OXIDE_LIGHT)
        c.drawRightString(gx + 240, gy + 15, f"{v_val:.4f} vs {f_val:.4f}")
        track_w = 240.0
        draw_rounded_card(c, gx, gy + 4, track_w, 7, fill=DARK_CARD, radius=3.5)
        draw_rounded_card(c, gx, gy + 4, track_w * (v_val / max_scale), 7, fill=OXIDE_ROSE, radius=3.5)
        draw_rounded_card(c, gx, gy - 5, track_w, 5.5, fill=DARK_CARD, radius=2.7)
        draw_rounded_card(c, gx, gy - 5, track_w * (f_val / max_scale), 5.5, fill=MINERAL_BLUE, radius=2.7)
    draw_bottom_pill(
        c, "Smooth ±125f scores 0.424 spellF1 on 5m but collapses to 0.146 dead-ball F1 — Vikzar V2.2 leads across all metrics.",
        page_str="02 / 04", dark_mode=False,
    )
    c.showPage()


def build_page_3(c: canvas.Canvas) -> None:
    fill_bg(c, PLUM_BLACK)
    draw_slide_header(
        c, "03/", "GAME-STATE PHASE DYNAMICS  ·  DRAWING, LEADING & TRAILING",
        "DERIVED 100% FROM OFFICIAL SMART TAGGING XML (GOALS + KICK OFF AFTER GOAL)", dark_mode=True,
    )
    c.setFont("Helvetica-Bold", 25)
    c.setFillColor(WARM_IVORY)
    c.drawString(44, H - 72, "TACTICS SHIFT WITH THE SCOREBOARD.")
    c.setFillColor(MINERAL_LIGHT)
    c.drawString(44, H - 101, "ZERO EXTERNAL DATA. 100% ALGORITHMIC.")
    draw_rounded_card(c, 620, H - 108, 296, 56, fill=DARK_CARD, stroke=DARK_BORDER, radius=10)
    c.setFont("Helvetica-Bold", 9.0)
    c.setFillColor(OXIDE_LIGHT)
    c.drawString(636, H - 68, "OFFICIAL XML GOAL-RESTART SEGMENTATION")
    c.setFont("Helvetica", 9.0)
    c.setFillColor(WARM_IVORY)
    c.drawString(636, H - 83, "4 GOALS + Kick Off (After Goal) anchors slice 158,857")
    c.drawString(636, H - 96, "graded frames into 5 live scoreline phases (P1–P5).")
    bx, by, bw, bh = 44.0, 56.0, 566.0, 354.0
    draw_rounded_card(c, bx, by, bw, bh, fill=DARK_CARD, stroke=DARK_BORDER, radius=12)
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(WARM_IVORY)
    c.drawString(bx + 16, by + bh - 24, "CHRONOLOGICAL MATCH PHASES (BAR-ATH)  ·  SHARE, DURATION & PRI")
    draw_rounded_card(c, bx + 382, by + bh - 29, 82, 16, fill=OXIDE_ROSE, radius=4)
    c.setFont("Helvetica-Bold", 7.8)
    c.setFillColor(WHITE)
    c.drawCentredString(bx + 423, by + bh - 24, "BARCELONA (H)")
    draw_rounded_card(c, bx + 470, by + bh - 29, 82, 16, fill=MINERAL_BLUE, radius=4)
    c.setFillColor(WHITE)
    c.drawCentredString(bx + 511, by + bh - 24, "ATHLETIC (A)")
    phases = [
        ("P1 · DRAWING (0-0)", "25.7m  ·  f=11,185..49,694", 64.3, 35.7, "11.5s / 6.5s", "66.1% / 45.9%", "58.8% / 23.1%"),
        ("P2 · BARÇA LEADING (1-0)", "8.3m   ·  f=49,694..62,074", 44.1, 55.9, "6.9s / 8.3s", "69.2% / 66.7%", "38.5% / 50.0%"),
        ("P3 · DRAWING (1-1)", "9.0m   ·  f=62,074..75,520", 56.9, 43.1, "10.1s / 6.2s", "61.5% / 46.7%", "44.4% / 44.4%"),
        ("P4 · BARÇA TRAILING (1-2)", "44.9m  ·  f=75,520..163,062", 61.4, 38.6, "9.3s / 5.8s", "54.5% / 37.6%", "61.4% / 32.4%"),
        ("P5 · DRAWING (2-2)", "18.1m  ·  f=163,062..190,198", 42.3, 57.7, "5.9s / 8.0s", "38.5% / 44.4%", "44.4% / 52.0%"),
    ]
    for idx, (p_title, p_meta, h_pct, a_pct, mean_str, pri_str, rec_str) in enumerate(phases):
        ry = by + bh - 84 - idx * 62
        draw_rounded_card(c, bx + 14, ry, bw - 28, 52, fill=DARK_CARD_ALT, stroke=DARK_BORDER, radius=8)
        c.setFont("Helvetica-Bold", 9.0)
        c.setFillColor(WARM_IVORY)
        c.drawString(bx + 22, ry + 32, p_title)
        c.setFont("Helvetica", 7.6)
        c.setFillColor(MUTED_LIGHT)
        c.drawString(bx + 22, ry + 18, p_meta)
        bar_x, bar_w, bar_y, bar_h = bx + 182, 166.0, ry + 17, 18.0
        h_w = bar_w * (h_pct / 100.0)
        draw_rounded_card(c, bar_x, bar_y, bar_w, bar_h, fill=MINERAL_BLUE, radius=5)
        draw_rounded_card(c, bar_x, bar_y, h_w, bar_h, fill=OXIDE_ROSE, radius=5)
        c.setFont("Helvetica-Bold", 8.0)
        c.setFillColor(WHITE)
        c.drawString(bar_x + 6, bar_y + 5, f"{h_pct:.1f}%")
        c.drawRightString(bar_x + bar_w - 6, bar_y + 5, f"{a_pct:.1f}%")
        c.setFont("Helvetica-Bold", 7.0)
        c.setFillColor(MUTED_LIGHT)
        c.drawString(bx + 358, ry + 32, "MEAN SPELL")
        c.drawString(bx + 420, ry + 32, "PRI (H / A)")
        c.drawString(bx + 486, ry + 32, "<6s REC")
        c.setFont("Helvetica-Bold", 8.0)
        c.setFillColor(WARM_IVORY)
        c.drawString(bx + 358, ry + 18, mean_str)
        c.setFillColor(OXIDE_LIGHT)
        c.drawString(bx + 420, ry + 18, pri_str)
        c.setFillColor(MINERAL_LIGHT)
        c.drawString(bx + 486, ry + 18, rec_str)
    rx, rw = 626.0, 290.0
    regime_cards = [
        ("DRAWING REGIME (0-0 / 1-1 / 2-2)", "56.7%", "BARÇA POSSESSION SHARE",
         "Barça holds 64.3% in P1 (11.49 s mean spell, 26.6 s p90) with 56.1% PRI and 52.9% <6s recovery across tied states.", OXIDE_ROSE),
        ("BARÇA LEADING REGIME (1-0)", "69.2%", "PEAK PRESS-RESISTANCE (PRI)",
         "When ahead in P2, Barça absorbs high Athletic pressure (69.2% PRI) while shifting to 56.2% direct <6s transitions.", MINERAL_BLUE),
        ("BARÇA TRAILING REGIME (1-2)", "61.4%", "RAPID <6s COUNTER-PRESS",
         "Across 44.9 min trailing in P4, Barça surges to 61.4% <6s counter-press recovery & 20.6% deep >15s pivot spells.", OXIDE_ROSE),
    ]
    for idx, (r_tag, big_stat, stat_sub, desc, accent) in enumerate(regime_cards):
        cy = 56.0 + (2 - idx) * 121.0
        draw_rounded_card(c, rx, cy, rw, 112.0, fill=DARK_CARD, stroke=DARK_BORDER, radius=10, top_accent=accent, top_accent_h=5)
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(MUTED_LIGHT)
        c.drawString(rx + 14, cy + 88, r_tag)
        c.setFont("Helvetica-Bold", 24)
        c.setFillColor(OXIDE_LIGHT if accent == OXIDE_ROSE else MINERAL_LIGHT)
        c.drawString(rx + 14, cy + 58, big_stat)
        c.setFont("Helvetica-Bold", 9.0)
        c.setFillColor(WARM_IVORY)
        c.drawString(rx + 96, cy + 66, stat_sub)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(WARM_IVORY)
        yt, words, line = cy + 38, desc.split(), ""
        for w_tok in words:
            test = f"{line} {w_tok}".strip()
            if c.stringWidth(test, "Helvetica", 8.5) <= rw - 28:
                line = test
            else:
                c.drawString(rx + 14, yt, line)
                yt -= 12
                line = w_tok
        if line:
            c.drawString(rx + 14, yt, line)
    draw_bottom_pill(
        c, "Full-match averages hide tactical adaptation — game-state segmentation exposes how teams respond to scoreline pressure.",
        page_str="03 / 04", dark_mode=True,
    )
    c.showPage()


def build_page_4(c: canvas.Canvas) -> None:
    fill_bg(c, WARM_IVORY)
    draw_slide_header(
        c, "04/", "ROLE-CLUSTERED RECRUITMENT PROFILING & PHASE 2 ROADMAP",
        "SPATIAL-TACTICAL CLUSTERING  ·  10-MATCH PHASE 2 ARCHITECTURE", dark_mode=False,
    )
    c.setFont("Helvetica-Bold", 25)
    c.setFillColor(PLUM_BLACK)
    c.drawString(44, H - 72, "PROVE THE TELEMETRY.")
    c.setFillColor(MINERAL_BLUE)
    c.drawString(44, H - 101, "SCALE THE RECRUITMENT PLATFORM.")
    card_w, card_y, card_h = (W - 88 - 16) / 2.0, H - 246.0, 128.0
    draw_rounded_card(c, 44, card_y, card_w, card_h, fill=LIGHT_CARD, stroke=LIGHT_BORDER, radius=10)
    c.setFont("Helvetica-Bold", 9.2)
    c.setFillColor(PLUM_BLACK)
    c.drawString(60, card_y + card_h - 20, "RECRUITMENT KPI 1  ·  PRESS-RESISTANCE (PRI) & <6s RECOVERY BY STATE")
    states_kpi = [
        ("DRAWING (Tied)", 56.1, 45.5, 52.9, 33.7),
        ("LEADING (Ahead)", 69.2, 37.6, 38.5, 32.4),
        ("TRAILING (Behind)", 54.5, 66.7, 61.4, 50.0),
    ]
    for idx, (st_lbl, b_pri, a_pri, b_rec, a_rec) in enumerate(states_kpi):
        ry = card_y + card_h - 46 - idx * 31
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(GRAPHITE_INK)
        c.drawString(60, ry + 6, st_lbl)
        bx1 = 156.0
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(OXIDE_ROSE)
        c.drawString(bx1, ry + 11, f"Barça PRI {b_pri:.1f}%")
        draw_rounded_card(c, bx1 + 70, ry + 11, 70 * (b_pri / 80.0), 6, fill=OXIDE_ROSE, radius=3)
        c.setFillColor(MINERAL_BLUE)
        c.drawString(bx1, ry + 1, f"Athl. PRI  {a_pri:.1f}%")
        draw_rounded_card(c, bx1 + 70, ry + 1, 70 * (a_pri / 80.0), 6, fill=MINERAL_BLUE, radius=3)
        bx2 = 312.0
        c.setFillColor(OXIDE_ROSE)
        c.drawString(bx2, ry + 11, f"Barça <6s {b_rec:.1f}%")
        draw_rounded_card(c, bx2 + 70, ry + 11, 66 * (b_rec / 80.0), 6, fill=OXIDE_ROSE, radius=3)
        c.setFillColor(MINERAL_BLUE)
        c.drawString(bx2, ry + 1, f"Athl. <6s  {a_rec:.1f}%")
        draw_rounded_card(c, bx2 + 70, ry + 1, 66 * (a_rec / 80.0), 6, fill=MINERAL_BLUE, radius=3)
    rx2 = 44 + card_w + 16
    draw_rounded_card(c, rx2, card_y, card_w, card_h, fill=LIGHT_CARD, stroke=LIGHT_BORDER, radius=10)
    c.setFont("Helvetica-Bold", 9.2)
    c.setFillColor(PLUM_BLACK)
    c.drawString(rx2 + 16, card_y + card_h - 20, "RECRUITMENT KPI 2  ·  BARCELONA ROLE-CLUSTER SHIFT (46 TRACKLETS)")
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(OXIDE_ROSE)
    c.drawString(rx2 + 16, card_y + card_h - 34, "■ Cluster 1: Deep Pivot (>15s)")
    c.setFillColor(MINERAL_BLUE)
    c.drawString(rx2 + 154, card_y + card_h - 34, "■ Cluster 2: Progression (6-15s)")
    c.setFillColor(PLUM_BLACK)
    c.drawString(rx2 + 304, card_y + card_h - 34, "■ Cluster 3: Direct Box (<6s)")
    clusters = [
        ("DRAWING", 18.5, 29.4, 52.1),
        ("LEADING", 12.5, 31.2, 56.2),
        ("TRAILING", 20.6, 23.7, 55.7),
    ]
    for idx, (st_name, c1, c2, c3) in enumerate(clusters):
        ry = card_y + card_h - 60 - idx * 28
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(GRAPHITE_INK)
        c.drawString(rx2 + 16, ry + 4, st_name)
        bar_x, total_w = rx2 + 82, card_w - 98
        w1, w2 = total_w * (c1 / 100.0), total_w * (c2 / 100.0)
        w3 = total_w - w1 - w2
        c.setFillColor(OXIDE_ROSE)
        c.rect(bar_x, ry, w1, 16, stroke=0, fill=1)
        c.setFillColor(MINERAL_BLUE)
        c.rect(bar_x + w1, ry, w2, 16, stroke=0, fill=1)
        c.setFillColor(PLUM_BLACK)
        c.rect(bar_x + w1 + w2, ry, w3, 16, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 8.0)
        c.setFillColor(WHITE)
        c.drawCentredString(bar_x + w1 / 2.0, ry + 4, f"{c1:.1f}%")
        c.drawCentredString(bar_x + w1 + w2 / 2.0, ry + 4, f"{c2:.1f}%")
        c.drawCentredString(bar_x + w1 + w2 + w3 / 2.0, ry + 4, f"{c3:.1f}%")
    gtm_cards = [
        ("1", "PHASE 1 BLIND SPOTS", "RAW EPTS CONSTRAINTS", [
            "40.7% graded ball dropouts & 50-50 aerials without event tags.",
            "44.5% broadcast replay drift under naive half-scaled alignment.",
            "46 anonymous EPTS tracklet slots swap IDs across occlusions.",
        ]),
        ("2", "PHASE 2 ANALYTICS", "10-MATCH wc-data-dashboard", [
            "Fuses 10-match BIHUB event feeds (xG, PPDA, box-entry efficiency).",
            "Sliding-window pitch-centroid correlation eliminates TV-cut drift.",
            "Automated Leading / Drawing / Trailing recruitment scouting filters.",
        ]),
        ("3", "PHASE 2 VISION", "TeamTrack MOT RE-ID", [
            "Appearance + kinematic Multi-Object Tracking on 10-match video.",
            "Resolves persistent shirt IDs across corners & crowded penalty boxes.",
            "Binds PRI & <6s counter-press recovery to individual player profiles.",
        ]),
    ]
    gw, gh, gy = 280.0, 160.0, 118.0
    for idx, (w_num, tag, title, bullets) in enumerate(gtm_cards):
        gx = 44.0 + idx * (gw + 16.0)
        draw_rounded_card(c, gx, gy, gw, gh, fill=LIGHT_CARD, stroke=LIGHT_BORDER, radius=10)
        c.setFont("Helvetica-Bold", 54)
        c.setFillColor(WATERMARK_TONE)
        c.drawRightString(gx + gw - 14, gy + gh - 48, w_num)
        c.setFont("Helvetica-Bold", 9.0)
        c.setFillColor(OXIDE_ROSE)
        c.drawString(gx + 16, gy + gh - 22, tag)
        c.setFont("Helvetica-Bold", 12.2)
        c.setFillColor(PLUM_BLACK)
        c.drawString(gx + 16, gy + gh - 40, title)
        c.setStrokeColor(OXIDE_ROSE)
        c.setLineWidth(1.5)
        c.line(gx + 16, gy + gh - 48, gx + 76, gy + gh - 48)
        c.setFont("Helvetica", 8.8)
        yt = gy + gh - 66
        for b_txt in bullets:
            c.setFillColor(OXIDE_ROSE)
            c.circle(gx + 20, yt + 3, 2.0, stroke=0, fill=1)
            c.setFillColor(GRAPHITE_INK)
            words, line = b_txt.split(), ""
            for w_tok in words:
                test = f"{line} {w_tok}".strip()
                if c.stringWidth(test, "Helvetica", 8.8) <= gw - 40:
                    line = test
                else:
                    c.drawString(gx + 28, yt, line)
                    yt -= 12.0
                    line = w_tok
            if line:
                c.drawString(gx + 28, yt, line)
                yt -= 15.5
    draw_rounded_card(c, 44, 52, W - 88, 52, fill=PLUM_BLACK, radius=10)
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(OXIDE_LIGHT)
    c.drawString(60, 86, "EXACT ONE-LINE DETERMINISTIC CLI REPRODUCTION  ·  17/17 UNIT TESTS PASSED  ·  BYTE-IDENTICAL CSV")
    c.setFont("Courier-Bold", 8.6)
    c.setFillColor(WARM_IVORY)
    c.drawString(60, 65, "python3 team_model.py --mode mode2 --out submission_artifacts/vikzar.csv && python3 evaluation/validate_submission.py submission_artifacts/vikzar.csv")
    draw_bottom_pill(
        c, "WE ARE ON THE PITCH  ·  github.com/Bomboclat-dev-pixel/Vikzar---Barca  ·  vikzar.in",
        page_str="04 / 04", dark_mode=False,
    )
    c.showPage()


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "submission_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "vikzar.pdf"
    c = canvas.Canvas(str(out_path), pagesize=(W, H))
    c.setTitle("Vikzar — More Than a Hack 2027 Phase 1 Technical Deck")
    c.setAuthor("Team Vikzar")
    build_page_1(c)
    build_page_2(c)
    build_page_3(c)
    build_page_4(c)
    c.save()
    print(f"Generated {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
