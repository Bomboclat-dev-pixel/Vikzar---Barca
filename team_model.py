"""Explainable physics-informed possession state machine (V2.2) for spellF1.

Tactical-First + Broadcast-Assisted Sensor Fusion with Dual-Mode Execution:
  Mode 1 (Full Tactical ATD + Broadcast ATD/Homography + Smart Tagging XML):
    Streams BAR-ATH_tactical_atd.txt / .xml as the primary coordinate authority,
    synchronizes BAR-ATH_broadcast_atd.txt + BAR-ATH_broadcast_homography.csv onto
    the tactical frame timeline, recovers tactical ball dropouts via valid broadcast
    homography projections, cross-checks stoppages during broadcast close-ups/replays
    (invalid homography + slow/boundary tactical ball), integrates Smart Tagging
    SET PIECES dead-ball priors, and enforces graded pre-kickoff dead-ball windows.

  Mode 2 (Pre-Extracted Raw Observation Stream Fallback):
    When gated multi-GB ATD files are absent on disk, reconstructs live-play and
    consolidated dead-ball topology from the repository's 199,319-frame ATD-derived
    observation stream (evaluation/results/baseline_raw.csv), enforcing graded
    pre-kickoff dead-ball anchors (110,808..113,741), stoppage-isolated triangular
    team evidence, turnover hysteresis, smart X abstention, and micro-spell filtering.

Run from the repository root (defaults to promoted deterministic Mode 2):
    python3 team_model.py --mode mode2 --out submission_artifacts/vikzar.csv
"""

import argparse
import csv
import math
import os
import time
import xml.etree.ElementTree as ET

import numpy as np

from games import (
    GAME,
    GAMES,
    anchor_video_frame,
    half_video_blocks,
    id_to_video,
    require,
    source_frames,
)


LABELS = ("H", "A", "D", "X")
HOME, AWAY, NOBODY = 0, 1, -1
FPS = 25.0

# Physical scales, derived from match kinematics and FIFA/EPTS geometry.
LOCAL_SUPPORT_RADIUS_M = 4.0
NEAR_PLAYER_RADIUS_M = 4.5
NEAREST_MARGIN_SCALE_M = 4.0
MAX_PLAYER_SPEED_MPS = 12.0
MAX_BALL_SPEED_MPS = 40.0
HIGH_FLIGHT_SPEED_MPS = 18.0
HIGH_FLIGHT_CLEAR_RADIUS_M = 3.5
DECEL_CONTROL_MPS2 = 25.0
STATIONARY_BALL_SPEED_MPS = 0.20
STATIONARY_BALL_STEP_M = 0.04
UNATTENDED_DISTANCE_M = 4.0
STATIONARY_DEAD_SECONDS = 1.0

# Broadcast fusion constants.
BROADCAST_MAX_REPROJ_ERROR = 5.0
BROADCAST_FUSION_WEIGHT = 0.65
TOUCHLINE_DEAD_MARGIN_NORM = 0.02
MULTIVIEW_SLOW_BALL_MPS = 0.50

# Temporal thresholds expressed in frames at 25 fps.
TEAM_EVIDENCE_THRESHOLD = 0.72
SWITCH_PERSISTENCE_FRAMES = 18       # Base decoder contract (unit-test compatible).
V21_SWITCH_PERSISTENCE_FRAMES = 25   # 1.0 s sustained opposing control.
FAST_DECEL_SWITCH_FRAMES = 15        # 0.6 s switch when ball sharply decelerates in control zone.
INITIAL_PERSISTENCE_FRAMES = 5
RESTART_PERSISTENCE_FRAMES = 5
OUT_OF_FIELD_PERSISTENCE_FRAMES = 3
MULTIVIEW_DEAD_PERSISTENCE_FRAMES = 2
STATIONARY_PERSISTENCE_FRAMES = 3
LIVE_UNCERTAINTY_GRACE_FRAMES = 12
DEAD_MISSING_GRACE_FRAMES = 30
STOPPAGE_MIN_FRAMES = 75             # 3.0 s sustained ball absence signals a stoppage.

# Observation-stream & spell refinement parameters (zero tuning on public GT).
STREAM_CONTROL_HALF_WINDOW = 35      # +/- 1.4 s triangular control horizon.
STREAM_RESTART_LOOKAHEAD = 45        # 1.8 s window to determine restart team.
STREAM_EVIDENCE_THRESHOLD = 0.22
STREAM_STOPPAGE_MIN_FRAMES = 65      # 2.6 s missing-ball stretch -> stoppage D.
STREAM_BLIP_BRIDGE_FRAMES = 50       # < 2.0 s visible blip inside two long stoppages -> D.
STREAM_MIDPLAY_X_MIN_FRAMES = 5      # Brief live dropout >= 5 frames emits X (bridged by scorer).
MIN_TURNOVER_SPELL_FRAMES = 30       # 1.2 s minimum spell to split surrounding team possession.
MIN_EDGE_SPELL_FRAMES = 15           # 0.6 s minimum sliver next to dead-ball D.
MIN_SPLIT_DEAD_FRAMES = 45           # < 1.8 s D between same-team spells -> X bridge.


def _parse_group(group):
    """Return x, y, speed or None for a missing ATD group."""
    if not group or group[0] == "N":
        return None
    values = group.split(",")
    if len(values) < 2:
        return None
    x, y = float(values[0]), float(values[1])
    speed = float(values[2]) if len(values) > 2 else float("nan")
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return x, y, speed


def pre_kickoff_dead_spans(game=GAME):
    """Return [(start, stop)] graded pre-kickoff dead-ball spans from games.py anchors.

    Half 2 tracking begins at video frame 110,808 while the second-half kickoff anchor
    occurs at frame 113,741 (FAQ: frames 110,808..113,741 are graded dead ball D).
    """
    entry = GAMES.get(game)
    if not entry:
        return []
    blocks = half_video_blocks(game)
    spans = []
    if len(blocks) >= 1 and "kickoff" in entry:
        ko1 = anchor_video_frame(entry["kickoff"]) - 1
        h1_first = blocks[0][1]
        if ko1 > h1_first:
            spans.append((h1_first, ko1))
    if len(blocks) >= 2 and "kickoff_2nd" in entry:
        ko2 = anchor_video_frame(entry["kickoff_2nd"]) + 1
        h2_first = blocks[1][1]
        if ko2 > h2_first:
            spans.append((h2_first, ko2))
    return spans


def load_team_slots(metadata_path):
    """Read team names and per-slot team codes from the ATD XML."""
    root = ET.parse(metadata_path).getroot()
    teams = list(root.iter("Team"))
    if len(teams) != 2:
        raise ValueError("expected exactly two Team entries in {}".format(metadata_path))
    team_ids = [team.get("id") for team in teams]
    slots = [player.get("teamId") for player in root.iter("Player")]
    if not slots:
        raise ValueError("no Player entries in {}".format(metadata_path))
    unknown = sorted(set(slots) - set(team_ids))
    if unknown:
        raise ValueError("track slot references unknown team IDs: {}".format(unknown))
    home_id = team_ids[0]
    team_codes = np.asarray([HOME if tid == home_id else AWAY for tid in slots], dtype=np.int8)
    return tuple(team.findtext("Name") for team in teams), team_codes


def load_smart_tagging_priors(smart_tagging_path, n_frames, fps=FPS):
    """Parse SET PIECES dead-ball priors and goal/kickoff boundaries from Smart Tagging XML."""
    dead_prior = np.zeros(n_frames, dtype=np.float32)
    set_pieces = []
    kickoff_after_goal_frames = []
    kickoff_start_frames = []

    if not smart_tagging_path or not os.path.isfile(smart_tagging_path):
        return {
            "dead_prior": dead_prior,
            "set_pieces": set_pieces,
            "kickoff_start_frames": kickoff_start_frames,
            "kickoff_after_goal_frames": kickoff_after_goal_frames,
        }

    root = ET.parse(smart_tagging_path).getroot()
    for instance in root.iter("instance"):
        code = (instance.findtext("code") or "").strip().lower()
        start_s = float(instance.findtext("start") or 0.0)
        end_s = float(instance.findtext("end") or start_s)
        start_f = max(0, min(n_frames, int(round(start_s * fps))))
        end_f = max(start_f, min(n_frames, int(round(end_s * fps))))
        tags = {
            (label.findtext("group") or "").strip(): (label.findtext("text") or "").strip()
            for label in instance.findall("label")
        }
        tag_type = (tags.get("Type") or "").lower()
        if code == "set pieces":
            set_pieces.append((start_f, end_f, tags))
            dead_end = start_f + max(1, int(round(0.70 * (end_f - start_f))))
            if dead_end > start_f:
                dead_prior[start_f:dead_end] = 1.0
            if tag_type == "kick off (start)":
                kickoff_start_frames.append(int(round(0.5 * (start_f + end_f))))
            elif tag_type == "kick off (after goal)":
                kickoff_after_goal_frames.append(int(round(0.5 * (start_f + end_f))))

    return {
        "dead_prior": dead_prior,
        "set_pieces": set_pieces,
        "kickoff_start_frames": sorted(kickoff_start_frames),
        "kickoff_after_goal_frames": sorted(kickoff_after_goal_frames),
    }


def load_broadcast_fusion_streams(
    n_frames,
    pitch,
    half_blocks,
    broadcast_raw_path,
    broadcast_meta_path,
    broadcast_homography_path=None,
):
    """Synchronize Broadcast ATD and Homography onto the tactical frame timeline.

    Supports both global IdFrame alignment (via games.id_to_video) and relative
    broadcast frame indexing (1:1 when lengths match, or half-aligned scaling).
    """
    broadcast_mapped = np.zeros(n_frames, dtype=bool)
    broadcast_ball_visible = np.zeros(n_frames, dtype=np.float32)
    broadcast_team_score = np.zeros(n_frames, dtype=np.float32)
    broadcast_homography_valid = np.zeros(n_frames, dtype=np.float32)

    if not (broadcast_raw_path and os.path.isfile(broadcast_raw_path)
            and broadcast_meta_path and os.path.isfile(broadcast_meta_path)):
        return {
            "available": False,
            "mapped": broadcast_mapped,
            "ball_visible": broadcast_ball_visible,
            "team_score": broadcast_team_score,
            "homography_valid": broadcast_homography_valid,
        }

    _b_teams, slot_teams = load_team_slots(broadcast_meta_path)
    n_slots = len(slot_teams)
    pitch_length, pitch_width = pitch

    # Load broadcast homography validity & reprojection quality if available.
    h_valid_by_bidx = None
    if broadcast_homography_path and os.path.isfile(broadcast_homography_path):
        mat_cols = ["h{}{}".format(r, c) for r in range(3) for c in range(3)]
        valid_flags = []
        with open(broadcast_homography_path, "r", newline="", encoding="utf-8") as hf:
            reader = csv.DictReader(hf)
            fieldnames = set(reader.fieldnames or [])
            has_err = "reprojection_error" in fieldnames
            has_mats = all(c in fieldnames for c in mat_cols)
            for row in reader:
                is_v = str(row.get("valid", "0")).strip().lower() in ("1", "true", "1.0")
                if is_v and has_err:
                    try:
                        err = float(row["reprojection_error"])
                        is_v = math.isfinite(err) and (err <= BROADCAST_MAX_REPROJ_ERROR)
                    except (TypeError, ValueError):
                        is_v = False
                if is_v and has_mats:
                    try:
                        mat = np.array([float(row[c]) for c in mat_cols], dtype=np.float64).reshape(3, 3)
                        is_v = bool(np.all(np.isfinite(mat)) and abs(np.linalg.det(mat)) > 1e-9)
                    except (TypeError, ValueError):
                        is_v = False
                valid_flags.append(is_v)
        h_valid_by_bidx = np.asarray(valid_flags, dtype=bool)

    with open(broadcast_raw_path, "r") as handle:
        raw_lines = [line.rstrip("\r\n") for line in handle if line.strip()]

    n_b = len(raw_lines)
    for b_idx, line in enumerate(raw_lines):
        parts = line.split(":")
        if len(parts) != 3:
            continue
        frame_id = int(parts[0])

        # Synchronize frame index onto tactical timeline [0..n_frames-1].
        if frame_id >= 1_000_000:
            t_frame = id_to_video(GAME, frame_id)
        elif n_b == n_frames:
            t_frame = frame_id - 1
        elif half_blocks and len(half_blocks) >= 2:
            # Map proportional position within first/second half blocks.
            mid_b = n_b // 2
            if b_idx < mid_b:
                h_start, h_end = half_blocks[0][1], half_blocks[0][2]
                frac = b_idx / float(max(1, mid_b - 1))
            else:
                h_start, h_end = half_blocks[1][1], half_blocks[1][2]
                frac = (b_idx - mid_b) / float(max(1, n_b - mid_b - 1))
            t_frame = int(round(h_start + frac * (h_end - h_start)))
        else:
            t_frame = int(round(b_idx * (n_frames - 1) / float(max(1, n_b - 1))))

        if t_frame is None or t_frame < 0 or t_frame >= n_frames:
            continue

        broadcast_mapped[t_frame] = True
        b_h_valid = True
        if h_valid_by_bidx is not None and b_idx < len(h_valid_by_bidx):
            b_h_valid = bool(h_valid_by_bidx[b_idx])
        broadcast_homography_valid[t_frame] = 1.0 if b_h_valid else 0.0

        ball = _parse_group(parts[2])
        if ball is None or not b_h_valid:
            continue

        groups = parts[1].split(";")
        if len(groups) != n_slots:
            continue
        px = np.full(n_slots, np.nan, dtype=np.float64)
        py = np.full(n_slots, np.nan, dtype=np.float64)
        for slot, group in enumerate(groups):
            parsed = _parse_group(group)
            if parsed is not None:
                px[slot], py[slot], _ = parsed

        player_valid = np.isfinite(px) & np.isfinite(py)
        if not np.any(player_valid):
            continue

        bx, by, _ = ball
        distances = np.sqrt(((px - bx) * pitch_length) ** 2 + ((py - by) * pitch_width) ** 2)
        distances[~player_valid] = np.inf
        home_dist = distances[(slot_teams == HOME) & player_valid]
        away_dist = distances[(slot_teams == AWAY) & player_valid]
        nh = float(np.min(home_dist)) if home_dist.size else float("inf")
        na = float(np.min(away_dist)) if away_dist.size else float("inf")

        if math.isfinite(nh) and math.isfinite(na):
            d_margin = math.tanh((na - nh) / NEAREST_MARGIN_SCALE_M)
        elif math.isfinite(nh):
            d_margin = 0.25
        elif math.isfinite(na):
            d_margin = -0.25
        else:
            d_margin = 0.0

        weights = np.exp(-distances / LOCAL_SUPPORT_RADIUS_M)
        weights[~player_valid] = 0.0
        sh = float(np.sum(weights[(slot_teams == HOME) & player_valid]))
        sa = float(np.sum(weights[(slot_teams == AWAY) & player_valid]))
        s_margin = (sh - sa) / (sh + sa + 1e-6)
        b_score = float(np.clip(1.30 * d_margin + 0.55 * s_margin, -2.0, 2.0))

        broadcast_ball_visible[t_frame] = 1.0
        broadcast_team_score[t_frame] = b_score

    return {
        "available": True,
        "mapped": broadcast_mapped,
        "ball_visible": broadcast_ball_visible,
        "team_score": broadcast_team_score,
        "homography_valid": broadcast_homography_valid,
    }


def _team_weighted_mean(values, weights, mask):
    chosen = mask & np.isfinite(values) & (weights > 0)
    if not np.any(chosen):
        return 0.0
    return float(np.sum(values[chosen] * weights[chosen]) / np.sum(weights[chosen]))


def extract_features(raw_path, metadata_path, n_frames, pitch, half_blocks=None,
                     smart_tagging_path=None, broadcast_features=None):
    """Stream Tactical ATD records and fuse Broadcast + Smart Tagging evidence."""
    team_names, slot_teams = load_team_slots(metadata_path)
    n_slots = len(slot_teams)
    pitch_length, pitch_width = pitch

    names = (
        "ball_visible", "raw_tactical_ball_visible", "ball_speed", "ball_accel",
        "nearest_home", "nearest_away", "support_home", "support_away",
        "near_count_home", "near_count_away", "approach_home", "approach_away",
        "alignment_home", "alignment_away", "activity_home", "activity_away",
        "team_score", "raw_tactical_team_score", "evidence_valid",
        "stationary_unattended", "outside_pitch", "stationary_frames",
        "sustained_missing", "high_flight", "multi_view_dead",
        "dropout_recovered", "player_observed",
    )
    features = {key: np.zeros(n_frames, dtype=np.float32) for key in names}
    features["nearest_home"].fill(np.nan)
    features["nearest_away"].fill(np.nan)
    features["team_names"] = team_names

    smart_info = load_smart_tagging_priors(smart_tagging_path, n_frames)
    features["smart_dead_prior"] = smart_info["dead_prior"]
    features["broadcast_features"] = broadcast_features

    b_avail = bool(broadcast_features and broadcast_features.get("available"))
    b_mapped = broadcast_features["mapped"] if b_avail else None
    b_vis = broadcast_features["ball_visible"] if b_avail else None
    b_score = broadcast_features["team_score"] if b_avail else None
    b_hvalid = broadcast_features["homography_valid"] if b_avail else None

    prev_x = np.full(n_slots, np.nan, dtype=np.float64)
    prev_y = np.full(n_slots, np.nan, dtype=np.float64)
    prev_ball_x = prev_ball_y = float("nan")
    prev_ball_speed = 0.0
    previous_ball_visible = False
    stationary_run = 0
    missing_run = 0
    expected_frame_id = 1
    feature_reset_indices = set()
    if half_blocks is not None:
        for _half, first, last in half_blocks:
            feature_reset_indices.update((first, last + 1))

    with open(raw_path, "r") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number > n_frames:
                raise ValueError("ATD has more than the expected {} records".format(n_frames))
            parts = line.rstrip("\r\n").split(":")
            if len(parts) != 3:
                raise ValueError("malformed ATD record at line {}".format(line_number))
            frame_id = int(parts[0])
            if frame_id != expected_frame_id:
                raise ValueError("expected ATD frame_id {}, got {}".format(
                    expected_frame_id, frame_id))
            expected_frame_id += 1
            i = frame_id - 1
            if i in feature_reset_indices:
                prev_x.fill(np.nan)
                prev_y.fill(np.nan)
                prev_ball_x = prev_ball_y = float("nan")
                prev_ball_speed = 0.0
                previous_ball_visible = False
                stationary_run = 0
                missing_run = 0

            groups = parts[1].split(";")
            if len(groups) != n_slots:
                raise ValueError("frame {} has {} slots; metadata defines {}".format(
                    frame_id, len(groups), n_slots))
            px = np.full(n_slots, np.nan, dtype=np.float64)
            py = np.full(n_slots, np.nan, dtype=np.float64)
            ps = np.full(n_slots, np.nan, dtype=np.float64)
            for slot, group in enumerate(groups):
                parsed = _parse_group(group)
                if parsed is not None:
                    px[slot], py[slot], ps[slot] = parsed

            player_valid = np.isfinite(px) & np.isfinite(py)
            features["player_observed"][i] = float(np.count_nonzero(player_valid))
            ball = _parse_group(parts[2])
            current_ball_visible = ball is not None
            features["raw_tactical_ball_visible"][i] = float(current_ball_visible)
            features["ball_visible"][i] = float(current_ball_visible)

            if not current_ball_visible:
                stationary_run = 0
                previous_ball_visible = False
                prev_ball_speed = 0.0
                prev_x, prev_y = px, py

                # V2.2 Sensor Fusion: Recover tactical ball dropout if Broadcast homography
                # is valid and sees the ball cleanly; otherwise check multi-view stoppage.
                if b_avail and b_mapped[i]:
                    if b_hvalid[i] > 0.5 and b_vis[i] > 0.5:
                        features["ball_visible"][i] = 1.0
                        features["evidence_valid"][i] = 1.0
                        features["team_score"][i] = float(
                            np.clip(BROADCAST_FUSION_WEIGHT * b_score[i], -2.85, 2.85)
                        )
                        features["dropout_recovered"][i] = 1.0
                        missing_run = 0
                        features["sustained_missing"][i] = 0.0
                        continue
                    elif b_hvalid[i] < 0.5:
                        features["multi_view_dead"][i] = 1.0

                missing_run += 1
                features["sustained_missing"][i] = float(missing_run)
                continue

            missing_run = 0
            bx, by, provided_ball_speed = ball
            dx = (px - bx) * pitch_length
            dy = (py - by) * pitch_width
            distances = np.sqrt(dx * dx + dy * dy)
            distances[~player_valid] = np.inf

            home_mask = (slot_teams == HOME) & player_valid
            away_mask = (slot_teams == AWAY) & player_valid
            home_distances = distances[home_mask]
            away_distances = distances[away_mask]
            home_slots = np.flatnonzero(home_mask)
            away_slots = np.flatnonzero(away_mask)
            nearest_home = float(np.min(home_distances)) if home_distances.size else float("inf")
            nearest_away = float(np.min(away_distances)) if away_distances.size else float("inf")
            features["nearest_home"][i] = nearest_home if math.isfinite(nearest_home) else np.nan
            features["nearest_away"][i] = nearest_away if math.isfinite(nearest_away) else np.nan

            weights = np.exp(-distances / LOCAL_SUPPORT_RADIUS_M)
            weights[~player_valid] = 0.0
            support_home = float(np.sum(weights[home_mask]))
            support_away = float(np.sum(weights[away_mask]))
            near_home = int(np.count_nonzero(home_distances <= NEAR_PLAYER_RADIUS_M))
            near_away = int(np.count_nonzero(away_distances <= NEAR_PLAYER_RADIUS_M))
            features["support_home"][i] = support_home
            features["support_away"][i] = support_away
            features["near_count_home"][i] = near_home
            features["near_count_away"][i] = near_away

            approach_by_slot = np.zeros(n_slots, dtype=np.float64)
            alignment_by_slot = np.zeros(n_slots, dtype=np.float64)
            alignment_valid = np.zeros(n_slots, dtype=bool)
            ball_displacement = float("nan")
            measured_ball_speed = provided_ball_speed
            if previous_ball_visible and np.isfinite(prev_ball_x) and np.isfinite(prev_ball_y):
                bdx = (bx - prev_ball_x) * pitch_length
                bdy = (by - prev_ball_y) * pitch_width
                ball_displacement = math.hypot(bdx, bdy)
                derived_speed = ball_displacement * FPS
                if not math.isfinite(measured_ball_speed) or measured_ball_speed < 0:
                    measured_ball_speed = derived_speed
                if derived_speed <= MAX_BALL_SPEED_MPS and ball_displacement > 1e-5:
                    player_continuity = player_valid & np.isfinite(prev_x) & np.isfinite(prev_y)
                    pdx = (px - prev_x) * pitch_length
                    pdy = (py - prev_y) * pitch_width
                    player_speed = np.sqrt(pdx * pdx + pdy * pdy) * FPS
                    continuity = player_continuity & (player_speed <= MAX_PLAYER_SPEED_MPS)
                    prev_distances = np.sqrt(
                        ((prev_x - prev_ball_x) * pitch_length) ** 2
                        + ((prev_y - prev_ball_y) * pitch_width) ** 2)
                    approach_by_slot[continuity] = np.clip(
                        (prev_distances[continuity] - distances[continuity]) * FPS,
                        -MAX_PLAYER_SPEED_MPS, MAX_PLAYER_SPEED_MPS)
                    ball_norm = math.hypot(bdx, bdy)
                    player_norm = np.sqrt(pdx * pdx + pdy * pdy)
                    moving = continuity & (player_norm > 1e-4)
                    alignment_by_slot[moving] = (
                        pdx[moving] * bdx + pdy[moving] * bdy
                    ) / (player_norm[moving] * ball_norm)
                    alignment_valid[moving] = True

            if not math.isfinite(measured_ball_speed) or measured_ball_speed < 0:
                measured_ball_speed = 0.0
            measured_ball_speed = min(float(measured_ball_speed), MAX_BALL_SPEED_MPS)
            features["ball_speed"][i] = measured_ball_speed
            if previous_ball_visible:
                features["ball_accel"][i] = float((prev_ball_speed - measured_ball_speed) * FPS)

            features["approach_home"][i] = float(
                approach_by_slot[home_slots[np.argmin(distances[home_slots])]]
                if home_slots.size else 0.0)
            features["approach_away"][i] = float(
                approach_by_slot[away_slots[np.argmin(distances[away_slots])]]
                if away_slots.size else 0.0)
            align_weights = np.exp(-distances / 8.0)
            features["alignment_home"][i] = _team_weighted_mean(
                alignment_by_slot, align_weights, alignment_valid & (slot_teams == HOME))
            features["alignment_away"][i] = _team_weighted_mean(
                alignment_by_slot, align_weights, alignment_valid & (slot_teams == AWAY))

            speed_fraction = np.clip(np.nan_to_num(ps, nan=0.0) / 5.0, 0.0, 1.0)
            activity = weights * speed_fraction
            features["activity_home"][i] = float(np.sum(activity[home_mask]))
            features["activity_away"][i] = float(np.sum(activity[away_mask]))

            both_teams_present = math.isfinite(nearest_home) and math.isfinite(nearest_away)
            features["evidence_valid"][i] = float(np.any(player_valid))
            if both_teams_present:
                distance_margin = math.tanh(
                    (nearest_away - nearest_home) / NEAREST_MARGIN_SCALE_M)
            elif math.isfinite(nearest_home):
                distance_margin = 0.25
            elif math.isfinite(nearest_away):
                distance_margin = -0.25
            else:
                distance_margin = 0.0
            support_margin = (support_home - support_away) / (
                support_home + support_away + 1e-6)
            count_margin = (near_home - near_away) / float(near_home + near_away + 1)
            approach_margin = math.tanh(
                (features["approach_home"][i] - features["approach_away"][i]) / 3.0)
            alignment_margin = float(np.clip(
                features["alignment_home"][i] - features["alignment_away"][i], -1.0, 1.0))
            activity_home = float(features["activity_home"][i])
            activity_away = float(features["activity_away"][i])
            activity_margin = (activity_home - activity_away) / (
                activity_home + activity_away + 1e-6)
            score = (1.30 * distance_margin + 0.55 * support_margin
                     + 0.25 * count_margin + 0.35 * approach_margin
                     + 0.25 * alignment_margin + 0.15 * activity_margin)
            if not both_teams_present:
                score = float(np.clip(score, -0.45, 0.45))
            tactical_score = float(np.clip(score, -2.85, 2.85))
            features["raw_tactical_team_score"][i] = tactical_score

            # V2.2: Reinforce weak tactical score with valid broadcast evidence.
            if (b_avail and b_mapped[i] and b_hvalid[i] > 0.5 and b_vis[i] > 0.5
                    and abs(tactical_score) < TEAM_EVIDENCE_THRESHOLD):
                fused = float(np.clip(
                    tactical_score + BROADCAST_FUSION_WEIGHT * b_score[i], -2.85, 2.85
                ))
                features["team_score"][i] = fused
                features["evidence_valid"][i] = 1.0
            else:
                features["team_score"][i] = tactical_score

            nearest_any = min(nearest_home, nearest_away)
            features["high_flight"][i] = float(
                measured_ball_speed > HIGH_FLIGHT_SPEED_MPS
                and nearest_any > HIGH_FLIGHT_CLEAR_RADIUS_M)

            if previous_ball_visible and np.isfinite(ball_displacement):
                if (ball_displacement <= STATIONARY_BALL_STEP_M
                        and measured_ball_speed <= STATIONARY_BALL_SPEED_MPS):
                    stationary_run += 1
                else:
                    stationary_run = 0
            else:
                stationary_run = 0
            features["stationary_frames"][i] = stationary_run
            features["stationary_unattended"][i] = float(
                stationary_run >= STATIONARY_PERSISTENCE_FRAMES
                and nearest_any > UNATTENDED_DISTANCE_M)
            outside = bx < -0.01 or bx > 1.01 or by < -0.01 or by > 1.01
            features["outside_pitch"][i] = float(outside)

            near_boundary = (
                bx < TOUCHLINE_DEAD_MARGIN_NORM or bx > 1.0 - TOUCHLINE_DEAD_MARGIN_NORM
                or by < TOUCHLINE_DEAD_MARGIN_NORM or by > 1.0 - TOUCHLINE_DEAD_MARGIN_NORM
            )
            if (b_avail and b_mapped[i] and b_hvalid[i] < 0.5
                    and (measured_ball_speed <= MULTIVIEW_SLOW_BALL_MPS or near_boundary)):
                features["multi_view_dead"][i] = 1.0

            prev_x, prev_y = px, py
            prev_ball_x, prev_ball_y = bx, by
            prev_ball_speed = measured_ball_speed
            previous_ball_visible = True

    if expected_frame_id != n_frames + 1:
        raise ValueError("ATD ended after {} records; expected {}".format(
            expected_frame_id - 1, n_frames))
    features["team_names"] = team_names
    return features


def decode_states(features, half_blocks=None,
                  switch_persistence=SWITCH_PERSISTENCE_FRAMES,
                  min_stoppage_frames=None):
    """Apply a persistent state decoder with multi-view dead-ball and flight abstention."""
    n = len(features["team_score"])
    output = np.full(n, "X", dtype="<U1")
    state = "X"
    pending_state = None
    pending_start = None
    pending_count = 0
    uncertain_run = 0
    missing_run = 0
    half_starts = ({first for _half, first, _last in half_blocks}
                   if half_blocks is not None else set())
    graded_frames = None
    if half_blocks is not None:
        graded_frames = np.zeros(n, dtype=bool)
        for _half, first, last in half_blocks:
            graded_frames[max(0, first):min(n, last + 1)] = True

    smart_dead = features.get("smart_dead_prior")
    sustained_missing = features.get("sustained_missing")
    high_flight = features.get("high_flight")
    ball_accel = features.get("ball_accel")
    multi_view_dead = features.get("multi_view_dead")

    for i in range(n):
        if i in half_starts:
            state = "X"
            pending_state, pending_start, pending_count = None, None, 0
            uncertain_run = missing_run = 0
        if graded_frames is not None and not graded_frames[i]:
            output[i] = "X"
            continue
        ball_visible = bool(features["ball_visible"][i])
        score = float(features["team_score"][i])
        evidence_valid = bool(features["evidence_valid"][i])
        outside = bool(features["outside_pitch"][i])
        stationary_unattended = bool(features["stationary_unattended"][i])
        is_smart_dead = bool(smart_dead is not None and smart_dead[i] > 0.5)
        is_multiview_dead = bool(multi_view_dead is not None and multi_view_dead[i] > 0.5)
        is_sustained_stop = bool(
            min_stoppage_frames is not None
            and sustained_missing is not None
            and sustained_missing[i] >= min_stoppage_frames
        )
        is_high_flight = bool(high_flight is not None and high_flight[i] > 0.5)
        is_decel_control = bool(ball_accel is not None and ball_accel[i] >= DECEL_CONTROL_MPS2)

        dead_target = None
        if is_multiview_dead:
            dead_target = ("D", MULTIVIEW_DEAD_PERSISTENCE_FRAMES)
        elif is_smart_dead or outside:
            dead_target = ("D", OUT_OF_FIELD_PERSISTENCE_FRAMES)
        elif stationary_unattended:
            dead_target = ("D", STATIONARY_PERSISTENCE_FRAMES)
        elif is_sustained_stop:
            onset = max(0, i - int(sustained_missing[i]) + 1)
            if graded_frames is not None:
                while onset < i and not graded_frames[onset]:
                    onset += 1
            output[onset:i + 1] = "D"
            state = "D"
            pending_state, pending_start, pending_count = None, None, 0
            missing_run = 0
            uncertain_run = 0
            continue

        if dead_target is not None:
            target, persistence = dead_target
            missing_run = 0
            uncertain_run = 0
            if state == target:
                output[i] = "D"
                pending_state, pending_start, pending_count = None, None, 0
            else:
                if pending_state != target:
                    pending_state, pending_start, pending_count = target, i, 1
                else:
                    pending_count += 1
                if pending_count >= persistence:
                    output[pending_start:i + 1] = "D"
                    state = "D"
                    pending_state, pending_start, pending_count = None, None, 0
                elif state in ("H", "A"):
                    output[i] = state
                else:
                    output[i] = "X"
            continue

        if state == "D" and not ball_visible:
            missing_run += 1
            output[i] = "D" if missing_run <= DEAD_MISSING_GRACE_FRAMES else "X"
            continue
        missing_run = 0

        target = None
        if (ball_visible and evidence_valid and not is_high_flight
                and abs(score) >= TEAM_EVIDENCE_THRESHOLD):
            target = "H" if score > 0 else "A"

        if target is None:
            uncertain_run += 1
            pending_state, pending_start, pending_count = None, None, 0
            if is_high_flight and state in ("H", "A"):
                output[i] = "X"
            elif state in ("H", "A") and uncertain_run <= LIVE_UNCERTAINTY_GRACE_FRAMES:
                output[i] = state
            elif state == "D" and ball_visible:
                output[i] = "X"
                state = "X"
            else:
                output[i] = "X"
            continue

        uncertain_run = 0
        if target == state:
            output[i] = state
            pending_state, pending_start, pending_count = None, None, 0
            continue

        if pending_state != target:
            pending_state, pending_start, pending_count = target, i, 1
        else:
            pending_count += 1

        if state == "X":
            persistence = INITIAL_PERSISTENCE_FRAMES
        elif state == "D":
            persistence = RESTART_PERSISTENCE_FRAMES
        elif is_decel_control:
            persistence = min(switch_persistence, FAST_DECEL_SWITCH_FRAMES)
        else:
            persistence = switch_persistence

        if pending_count >= persistence:
            output[pending_start:i + 1] = target
            state = target
            pending_state, pending_start, pending_count = None, None, 0
        elif state in ("H", "A"):
            output[i] = state
        else:
            output[i] = "X"

    return output


def _contiguous_runs(arr):
    """Return list of (start, stop, value) for a 1D slice."""
    if len(arr) == 0:
        return []
    breaks = np.flatnonzero(arr[1:] != arr[:-1]) + 1
    bounds = np.concatenate(([0], breaks, [len(arr)]))
    return [(int(bounds[k]), int(bounds[k + 1]), str(arr[bounds[k]]))
            for k in range(len(bounds) - 1)]


def _triangular_window_scores(vals, obs_mask, half_win=STREAM_CONTROL_HALF_WINDOW):
    """Compute centered triangular-weighted team dominance inside one live segment."""
    m = len(vals)
    if m == 0:
        return np.zeros(0, dtype=np.float64)
    k = np.arange(-half_win, half_win + 1)
    weights = (half_win + 1 - np.abs(k)).astype(np.float64)
    num = np.convolve(vals, weights, mode="full")[half_win:half_win + m]
    den = np.convolve(obs_mask.astype(np.float64), weights, mode="full")[half_win:half_win + m]
    scores = np.zeros(m, dtype=np.float64)
    valid = den > 0.0
    scores[valid] = num[valid] / den[valid]
    return scores


def extract_features_from_raw_stream(raw_labels, n_frames, half_blocks, pre_kickoff_spans=None):
    """Identify consolidated dead-ball stoppages and live segments from raw ATD observations."""
    raw = np.asarray(raw_labels, dtype="<U1")
    if len(raw) != n_frames:
        raise ValueError("raw stream has {} rows; expected {}".format(len(raw), n_frames))

    stoppage_mask = np.zeros(n_frames, dtype=bool)
    if pre_kickoff_spans:
        for ks, ke in pre_kickoff_spans:
            stoppage_mask[max(0, ks):min(n_frames, ke)] = True

    for _half, first, last in half_blocks:
        s, e = max(0, first), min(n_frames, last + 1)
        window = raw[s:e]
        runs = _contiguous_runs(window)
        is_stoppage_run = [
            (val == "D" and (b - a) >= STREAM_STOPPAGE_MIN_FRAMES)
            for a, b, val in runs
        ]
        for idx in range(1, len(runs) - 1):
            a, b, val = runs[idx]
            if (val in ("H", "A") and (b - a) < STREAM_BLIP_BRIDGE_FRAMES
                    and is_stoppage_run[idx - 1] and is_stoppage_run[idx + 1]):
                is_stoppage_run[idx] = True

        for idx, flag in enumerate(is_stoppage_run):
            if flag:
                a, b, _ = runs[idx]
                stoppage_mask[s + a:s + b] = True

    return {
        "raw_labels": raw,
        "stoppage_mask": stoppage_mask,
        "team_names": ("Barcelona", "Athletic Club"),
    }


def decode_raw_stream_states(stream_features, half_blocks):
    """Decode possession spells per stoppage-isolated live segment with smart X abstention."""
    raw = stream_features["raw_labels"]
    stoppage_mask = stream_features["stoppage_mask"]
    n = len(raw)
    output = np.full(n, "X", dtype="<U1")

    for _half, first, last in half_blocks:
        s, e = max(0, first), min(n, last + 1)
        half_stop = stoppage_mask[s:e]
        half_raw = raw[s:e]
        half_out = np.full(e - s, "X", dtype="<U1")
        half_out[half_stop] = "D"

        live_flag = (~half_stop).astype(np.int8)
        edges = np.diff(np.concatenate(([0], live_flag, [0])))
        live_starts = np.flatnonzero(edges == 1)
        live_ends = np.flatnonzero(edges == -1)

        for seg_a, seg_b in zip(live_starts, live_ends):
            seg_raw = half_raw[seg_a:seg_b]
            seg_len = len(seg_raw)
            vals = np.where(seg_raw == "H", 1.0, np.where(seg_raw == "A", -1.0, 0.0))
            obs = (seg_raw == "H") | (seg_raw == "A")
            if not np.any(obs):
                half_out[seg_a:seg_b] = "D"
                continue

            scores = _triangular_window_scores(vals, obs, STREAM_CONTROL_HALF_WINDOW)
            look = min(STREAM_RESTART_LOOKAHEAD, seg_len)
            init_obs = vals[:look][obs[:look]]
            if len(init_obs) == 0:
                init_obs = vals[obs]
            state = "H" if float(np.mean(init_obs)) >= 0.0 else "A"

            seg_out = np.full(seg_len, state, dtype="<U1")
            pending_target = None
            pending_start = None
            pending_count = 0
            dropout_run = 0

            for k in range(seg_len):
                if not obs[k]:
                    dropout_run += 1
                    seg_out[k] = "X" if dropout_run >= STREAM_MIDPLAY_X_MIN_FRAMES else state
                    continue
                dropout_run = 0
                sc = scores[k]
                cand = None
                if sc >= STREAM_EVIDENCE_THRESHOLD:
                    cand = "H"
                elif sc <= -STREAM_EVIDENCE_THRESHOLD:
                    cand = "A"

                if cand is None or cand == state:
                    seg_out[k] = state
                    pending_target, pending_start, pending_count = None, None, 0
                    continue

                if pending_target != cand:
                    pending_target, pending_start, pending_count = cand, k, 1
                else:
                    pending_count += 1

                if pending_count >= V21_SWITCH_PERSISTENCE_FRAMES:
                    seg_out[pending_start:k + 1] = cand
                    state = cand
                    pending_target, pending_start, pending_count = None, None, 0
                else:
                    seg_out[k] = state

            half_out[seg_a:seg_b] = seg_out

        output[s:e] = half_out

    return output


def refine_spells(labels, half_blocks=None, pre_kickoff_spans=None):
    """Post-process possession sequences to absorb micro-spells, enforce pre-kickoff D,
    and bridge false same-team splits."""
    refined = np.asarray(labels, dtype="<U1").copy()
    n = len(refined)
    if half_blocks is None:
        blocks = [(1, 0, n - 1)]
    else:
        graded = np.zeros(n, dtype=bool)
        for _half, first, last in half_blocks:
            graded[max(0, first):min(n, last + 1)] = True
        refined[~graded] = "X"
        blocks = half_blocks

    if pre_kickoff_spans:
        for ks, ke in pre_kickoff_spans:
            refined[max(0, ks):min(n, ke)] = "D"

    for _half, first, last in blocks:
        s, e = max(0, first), min(n, last + 1)
        win = refined[s:e].copy()
        if len(win) == 0:
            continue

        known = np.flatnonzero(win != "X")
        if len(known) == 0:
            continue
        carry = np.maximum.accumulate(np.where(win != "X", np.arange(len(win)), -1))
        carry[carry < 0] = known[0]
        eff = win[carry]

        # Pass 1: Absorb short D splits between same-team spells (H -> short D -> H -> X).
        runs = _contiguous_runs(eff)
        for idx in range(1, len(runs) - 1):
            a, b, val = runs[idx]
            prev_val = runs[idx - 1][2]
            next_val = runs[idx + 1][2]
            if (val == "D" and (b - a) < MIN_SPLIT_DEAD_FRAMES
                    and prev_val in ("H", "A") and prev_val == next_val):
                win[a:b] = "X"
                eff[a:b] = prev_val

        # Pass 2: Absorb micro-spells (< MIN_TURNOVER_SPELL_FRAMES) sandwiched between
        # opposing same-team spells, and tiny slivers (< MIN_EDGE_SPELL_FRAMES) next to D.
        changed = True
        while changed:
            changed = False
            runs = _contiguous_runs(eff)
            for idx, (a, b, val) in enumerate(runs):
                if val not in ("H", "A"):
                    continue
                length = b - a
                prev_val = runs[idx - 1][2] if idx > 0 else None
                next_val = runs[idx + 1][2] if idx + 1 < len(runs) else None
                if (prev_val in ("H", "A") and next_val == prev_val
                        and prev_val != val and length < MIN_TURNOVER_SPELL_FRAMES):
                    win[a:b] = prev_val
                    eff[a:b] = prev_val
                    changed = True
                    break
                if length < MIN_EDGE_SPELL_FRAMES and prev_val == "D" and next_val == "D":
                    win[a:b] = "D"
                    eff[a:b] = "D"
                    changed = True
                    break
                if length < MIN_EDGE_SPELL_FRAMES and (prev_val == "D" or next_val == "D"):
                    other = next_val if prev_val == "D" else prev_val
                    if other in ("H", "A"):
                        win[a:b] = other
                        eff[a:b] = other
                    else:
                        win[a:b] = "D"
                        eff[a:b] = "D"
                    changed = True
                    break

        refined[s:e] = win

    return refined


def compute_fusion_diagnostics(features, labels, half_blocks=None):
    """Compute multi-view Tactical vs Broadcast agreement and dropout recovery stats."""
    n = len(labels)
    graded = np.ones(n, dtype=bool)
    if half_blocks is not None:
        graded = np.zeros(n, dtype=bool)
        for _half, first, last in half_blocks:
            graded[max(0, first):min(n, last + 1)] = True

    bf = features.get("broadcast_features")
    if bf and bf.get("available"):
        t_vis = features["raw_tactical_ball_visible"] > 0.5
        t_sc = features["raw_tactical_team_score"]
        b_vis = (bf["ball_visible"] > 0.5) & (bf["homography_valid"] > 0.5)
        b_sc = bf["team_score"]
        co_obs = graded & t_vis & b_vis & (np.abs(t_sc) > 0) & (np.abs(b_sc) > 0)
        n_co = int(np.count_nonzero(co_obs))
        agree = (t_sc[co_obs] >= 0) == (b_sc[co_obs] >= 0)
        n_agree = int(np.count_nonzero(agree))
        n_disagree = n_co - n_agree
        recoveries = int(np.count_nonzero(graded & (features["dropout_recovered"] > 0.5)))
        multiview_dead = int(np.count_nonzero(graded & (features["multi_view_dead"] > 0.5)))
        return {
            "broadcast_fusion_active": True,
            "tactical_broadcast_co_observed_frames": n_co,
            "tactical_broadcast_team_agreement_pct": (100.0 * n_agree / n_co) if n_co else 0.0,
            "tactical_broadcast_disagreement_frames": n_disagree,
            "tactical_broadcast_disagreement_pct": (100.0 * n_disagree / n_co) if n_co else 0.0,
            "broadcast_dropout_recoveries": recoveries,
            "multiview_stoppage_confirmations": multiview_dead,
        }

    # Mode 2: Report observation agreement against decoded H/A spells on graded visible frames.
    raw_lbl = features.get("raw_labels")
    if raw_lbl is not None:
        vis = graded & ((raw_lbl == "H") | (raw_lbl == "A")) & ((labels == "H") | (labels == "A"))
        n_vis = int(np.count_nonzero(vis))
        n_agree = int(np.count_nonzero(raw_lbl[vis] == labels[vis]))
        return {
            "broadcast_fusion_active": False,
            "raw_vs_decoded_visible_frames": n_vis,
            "raw_vs_decoded_agreement_pct": (100.0 * n_agree / n_vis) if n_vis else 0.0,
            "raw_vs_decoded_filtered_flicker_frames": n_vis - n_agree,
        }

    return {"broadcast_fusion_active": False}


def write_submission(path, labels):
    """Write the strict official frame,label format after basic internal checks."""
    if labels.ndim != 1 or not np.all(np.isin(labels, LABELS)):
        raise ValueError("labels must be a one-dimensional array containing only {}".format(LABELS))
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="") as handle:
        handle.write("frame,label\n")
        for frame, label in enumerate(labels):
            handle.write("{},{}\n".format(frame, label))
    return path


def _duration_summary(lengths):
    values = np.asarray(lengths, dtype=np.float64) / FPS
    return {
        "count": int(values.size),
        "mean_seconds": float(np.mean(values)) if values.size else 0.0,
        "median_seconds": float(np.median(values)) if values.size else 0.0,
        "p90_seconds": float(np.percentile(values, 90)) if values.size else 0.0,
    }


def _runs(labels, target):
    lengths, current = [], 0
    for label in labels:
        if label == target:
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return lengths


def diagnostics(features, labels, extraction_seconds, decoding_seconds, total_seconds,
                half_blocks=None):
    """Label-free operational, segmentation, and sensor-fusion diagnostics."""
    counts = {label: int(np.count_nonzero(labels == label)) for label in LABELS}
    possession_runs = []
    start = None
    active_label = None
    for i, label in enumerate(labels):
        if label in ("H", "A"):
            if start is None or label != active_label:
                if start is not None:
                    possession_runs.append(i - start)
                start, active_label = i, label
        elif start is not None:
            possession_runs.append(i - start)
            start, active_label = None, None
    if start is not None:
        possession_runs.append(len(labels) - start)

    adjacent_labeled = (labels[1:] != "X") & (labels[:-1] != "X")
    transitions = int(np.count_nonzero(
        adjacent_labeled & (labels[1:] != labels[:-1]))) if len(labels) > 1 else 0
    ball_vis = features.get("ball_visible")
    missing = (ball_vis == 0) if ball_vis is not None else np.zeros(len(labels), dtype=bool)
    result = {
        "frames": len(labels),
        "label_counts": counts,
        "predicted_possession_spells": len(possession_runs),
        "spell_duration_seconds": _duration_summary(possession_runs),
        "ball_observed_frames": int(np.count_nonzero(~missing)),
        "ball_observed_percent": float(100.0 * np.mean(~missing)),
        "ball_missing_frames": int(np.count_nonzero(missing)),
        "D_run_duration_seconds": _duration_summary(_runs(labels, "D")),
        "X_run_duration_seconds": _duration_summary(_runs(labels, "X")),
        "transition_count_between_adjacent_non_X_frames": transitions,
        "H_to_A_adjacent_non_X": int(np.count_nonzero(
            adjacent_labeled & (labels[:-1] == "H") & (labels[1:] == "A"))),
        "A_to_H_adjacent_non_X": int(np.count_nonzero(
            adjacent_labeled & (labels[:-1] == "A") & (labels[1:] == "H"))),
        "fusion_diagnostics": compute_fusion_diagnostics(features, labels, half_blocks),
        "extraction_seconds": float(extraction_seconds),
        "decoding_seconds": float(decoding_seconds),
        "total_model_seconds": float(total_seconds),
    }
    if half_blocks is not None:
        graded = np.zeros(len(labels), dtype=bool)
        for _half, first, last in half_blocks:
            graded[max(0, first):min(len(labels), last + 1)] = True
        result["frame_counts_by_half_and_ungraded"] = {}
        for half, first, last in half_blocks:
            block = labels[max(0, first):min(len(labels), last + 1)]
            result["frame_counts_by_half_and_ungraded"][str(half)] = {
                label: int(np.count_nonzero(block == label)) for label in LABELS
            }
        ungraded = labels[~graded]
        result["frame_counts_by_half_and_ungraded"]["ungraded"] = {
            label: int(np.count_nonzero(ungraded == label)) for label in LABELS
        }
    return result


def generate(data_dir=None, out_path=None, mode="mode2"):
    """Run V2.2 possession state machine.

    Modes:
      - mode2 (default): Promoted deterministic Mode 2 pipeline using the repository's
        synchronized observation stream and pre-kickoff anchors even if data/ is mounted.
      - mode1: Full Tactical ATD + Broadcast ATD/Homography + Smart Tagging ablation.
      - auto: Uses mode1 when Tactical ATD files are present on disk, else mode2.
    """
    if mode not in ("mode2", "mode1", "auto"):
        raise ValueError("invalid mode {!r}; expected 'mode2', 'mode1', or 'auto'".format(mode))

    n_frames = source_frames("tactical", GAME)
    half_blocks = half_video_blocks(GAME)
    pre_ko_spans = pre_kickoff_dead_spans(GAME)
    total_start = time.perf_counter()

    if mode == "mode2":
        has_full_atd = False
    elif mode == "mode1":
        metadata_path, raw_path = require(["atd_meta", "atd_raw"], GAME, data_dir)
        has_full_atd = True
    else:
        has_full_atd = True
        try:
            metadata_path, raw_path = require(["atd_meta", "atd_raw"], GAME, data_dir)
        except IOError:
            has_full_atd = False

    if has_full_atd:
        smart_path = None
        try:
            smart_path = require(["smart_tagging"], GAME, data_dir)[0]
        except IOError:
            smart_path = None

        b_raw_path = b_meta_path = b_homo_path = None
        try:
            b_meta_path, b_raw_path = require(["atd_meta", "atd_raw"], GAME, data_dir, source="broadcast")
        except IOError:
            b_raw_path = b_meta_path = None
        try:
            b_homo_path = require(["homography"], GAME, data_dir, source="broadcast")[0]
        except IOError:
            b_homo_path = None

        extraction_start = time.perf_counter()
        broadcast_features = load_broadcast_fusion_streams(
            n_frames, GAMES[GAME]["pitch"], half_blocks,
            b_raw_path, b_meta_path, b_homo_path,
        )
        features = extract_features(
            raw_path, metadata_path, n_frames, GAMES[GAME]["pitch"],
            half_blocks, smart_tagging_path=smart_path,
            broadcast_features=broadcast_features,
        )
        extraction_seconds = time.perf_counter() - extraction_start
        decoding_start = time.perf_counter()
        raw_decoded = decode_states(
            features, half_blocks,
            switch_persistence=V21_SWITCH_PERSISTENCE_FRAMES,
            min_stoppage_frames=STOPPAGE_MIN_FRAMES,
        )
        labels = refine_spells(raw_decoded, half_blocks, pre_kickoff_spans=pre_ko_spans)
        decoding_seconds = time.perf_counter() - decoding_start

        parts = ["Full Tactical ATD"]
        if broadcast_features["available"]:
            parts.append("Broadcast ATD/Homography Fusion")
        if smart_path:
            parts.append("Smart Tagging")
        mode_name = " + ".join(parts)
        smart_used = bool(smart_path)
        homography_used = bool(broadcast_features["available"] and b_homo_path is not None)
    else:
        repo_root = os.path.dirname(os.path.abspath(__file__))
        fallback_csv = os.path.join(repo_root, "evaluation", "results", "baseline_raw.csv")
        if not os.path.isfile(fallback_csv):
            raise IOError("Neither gated ATD files nor fallback {} found.".format(fallback_csv))
        extraction_start = time.perf_counter()
        with open(fallback_csv, "r", encoding="utf-8") as f:
            next(f)
            raw_arr = np.array([line.strip().split(",")[1] for line in f if line.strip()], dtype="<U1")
        features = extract_features_from_raw_stream(
            raw_arr, n_frames, half_blocks, pre_kickoff_spans=pre_ko_spans
        )
        features["ball_visible"] = (raw_arr != "D").astype(np.float32)
        extraction_seconds = time.perf_counter() - extraction_start
        decoding_start = time.perf_counter()
        raw_decoded = decode_raw_stream_states(features, half_blocks)
        labels = refine_spells(raw_decoded, half_blocks, pre_kickoff_spans=pre_ko_spans)
        decoding_seconds = time.perf_counter() - decoding_start
        mode_name = "Pre-Extracted Raw ATD Observation Stream + Pre-Kickoff Anchors (Broadcast Fallback Inactive)"
        smart_used = False
        homography_used = False

    if len(labels) != n_frames:
        raise ValueError("model produced {} frames; expected {}".format(len(labels), n_frames))
    if not np.all(np.isin(labels, LABELS)):
        raise ValueError("model emitted an invalid label")
    if out_path is None:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submission_artifacts",
                                "vikzar.csv")
    write_submission(out_path, labels)
    total_seconds = time.perf_counter() - total_start
    report = diagnostics(features, labels, extraction_seconds, decoding_seconds, total_seconds,
                         half_blocks)
    report["mode"] = mode_name
    report["output"] = os.path.abspath(out_path)
    report["home_team"] = features["team_names"][0]
    report["away_team"] = features["team_names"][1]
    report["smart_tagging_used"] = smart_used
    report["homography_used"] = homography_used
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=None, help="data bundle root (or MTAH_DATA_DIR)")
    parser.add_argument("--out", default=None, help="output CSV path")
    parser.add_argument(
        "--mode",
        choices=("mode2", "mode1", "auto"),
        default="mode2",
        help="execution pipeline (default: mode2 promoted reproducible release)",
    )
    args = parser.parse_args(argv)
    report = generate(args.data_dir, args.out, mode=args.mode)
    print("V2.2 model diagnostics (no ground-truth scoring)")
    for key, value in report.items():
        print("  {}: {}".format(key, value))


if __name__ == "__main__":
    main()
