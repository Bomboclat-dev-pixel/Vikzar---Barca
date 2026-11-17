import os
import tempfile
import unittest

import numpy as np

import analyze_spells
import team_model as model


def _features(scores, visible=None, valid=None, outside=None, stationary=None,
              smart_dead=None, sustained_missing=None, high_flight=None, ball_accel=None):
    n = len(scores)
    out = {
        "team_score": np.asarray(scores, dtype=np.float32),
        "ball_visible": np.asarray(visible if visible is not None else [1] * n,
                                    dtype=np.float32),
        "evidence_valid": np.asarray(valid if valid is not None else [1] * n,
                                      dtype=np.float32),
        "outside_pitch": np.asarray(outside if outside is not None else [0] * n,
                                    dtype=np.float32),
        "stationary_unattended": np.asarray(
            stationary if stationary is not None else [0] * n, dtype=np.float32),
    }
    if smart_dead is not None:
        out["smart_dead_prior"] = np.asarray(smart_dead, dtype=np.float32)
    if sustained_missing is not None:
        out["sustained_missing"] = np.asarray(sustained_missing, dtype=np.float32)
    if high_flight is not None:
        out["high_flight"] = np.asarray(high_flight, dtype=np.float32)
    if ball_accel is not None:
        out["ball_accel"] = np.asarray(ball_accel, dtype=np.float32)
    return out


class TeamModelTests(unittest.TestCase):
    def test_missing_ball_is_not_dead_ball(self):
        labels = model.decode_states(_features(
            [0] * 20, visible=[0] * 20, valid=[0] * 20))
        self.assertTrue(np.all(labels == "X"))
        self.assertFalse(np.any(labels == "D"))

    def test_hysteresis_rejects_short_opponent_burst_and_accepts_persistent_switch(self):
        scores = ([1.2] * 10) + ([-1.2] * 17) + ([1.2] * 5) + ([-1.2] * 20)
        labels = model.decode_states(_features(scores))
        self.assertTrue(np.all(labels[:32] == "H"))
        self.assertTrue(np.all(labels[32:] == "A"))

    def test_dead_ball_requires_persistent_positive_evidence(self):
        outside = [0, 0, 0, 1, 1, 1, 0, 0]
        labels = model.decode_states(_features(
            [0] * len(outside), outside=outside))
        self.assertEqual(list(labels), ["X", "X", "X", "D", "D", "D", "X", "X"])

    def test_atd_feature_extraction_handles_missing_observations(self):
        xml = """<main><Teams>
          <Team id="H"><Name>Home</Name></Team><Team id="A"><Name>Away</Name></Team>
          </Teams><Players><Player teamId="H"/><Player teamId="A"/></Players></main>"""
        rows = [
            "1:0.50,0.50,1.0;0.80,0.50,2.0:0.51,0.50,0.5",
            "2:0.50,0.50,1.0;NaN,NaN,NaN:NaN,NaN,NaN",
            "3:0.52,0.50,1.0;0.80,0.50,2.0:0.53,0.50,0.5",
        ]
        with tempfile.TemporaryDirectory() as folder:
            xml_path = os.path.join(folder, "meta.xml")
            raw_path = os.path.join(folder, "tracking.txt")
            with open(xml_path, "w", encoding="utf-8") as handle:
                handle.write(xml)
            with open(raw_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(rows) + "\n")
            features = model.extract_features(raw_path, xml_path, 3, (105.3, 68.0))

        self.assertEqual(features["team_names"], ("Home", "Away"))
        self.assertEqual(features["ball_visible"].tolist(), [1.0, 0.0, 1.0])
        self.assertGreater(features["nearest_home"][0], 0.0)
        self.assertGreater(features["nearest_away"][0], features["nearest_home"][0])
        self.assertEqual(features["player_observed"][1], 1.0)
        self.assertEqual(features["ball_speed"][1], 0.0)

    def test_nonfinite_ball_coordinates_are_missing(self):
        xml = """<main><Teams><Team id='H'><Name>Home</Name></Team>
          <Team id='A'><Name>Away</Name></Team></Teams>
          <Players><Player teamId='H'/><Player teamId='A'/></Players></main>"""
        row = "1:0.50,0.50,1.0;0.80,0.50,2.0:NaN,NaN,NaN"
        with tempfile.TemporaryDirectory() as folder:
            xml_path = os.path.join(folder, "meta.xml")
            raw_path = os.path.join(folder, "tracking.txt")
            with open(xml_path, "w", encoding="utf-8") as handle:
                handle.write(xml)
            with open(raw_path, "w", encoding="utf-8") as handle:
                handle.write(row + "\n")
            features = model.extract_features(raw_path, xml_path, 1, (105.3, 68.0))
        self.assertEqual(features["ball_visible"].tolist(), [0.0])
        self.assertTrue(np.isnan(features["nearest_home"][0]))

    def test_feature_motion_history_resets_at_half_boundary(self):
        xml = """<main><Teams><Team id='H'><Name>Home</Name></Team>
          <Team id='A'><Name>Away</Name></Team></Teams>
          <Players><Player teamId='H'/><Player teamId='A'/></Players></main>"""
        rows = [f"{i}:0.50,0.50,0.0;0.80,0.50,0.0:0.51,0.50,0.0"
                for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as folder:
            xml_path = os.path.join(folder, "meta.xml")
            raw_path = os.path.join(folder, "tracking.txt")
            with open(xml_path, "w", encoding="utf-8") as handle:
                handle.write(xml)
            with open(raw_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(rows) + "\n")
            features = model.extract_features(
                raw_path, xml_path, 4, (105.3, 68.0), [(1, 0, 2), (2, 3, 3)])
        self.assertEqual(features["stationary_frames"][3], 0.0)

    def test_decoder_resets_across_ungraded_gap_and_second_half(self):
        features = _features([1.2] * 20 + [0.0] * 4 + [-1.2] * 16)
        labels = model.decode_states(features, half_blocks=[(1, 0, 9), (2, 20, 39)])
        self.assertTrue(np.all(labels[:10] == "H"))
        self.assertTrue(np.all(labels[10:20] == "X"))
        self.assertTrue(np.all(labels[20:24] == "X"))
        self.assertTrue(np.all(labels[24:] == "A"))

    def test_submission_writer_emits_exact_frame_labels(self):
        labels = np.asarray(["H", "D", "X", "A"])
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, "candidate.csv")
            model.write_submission(output, labels)
            with open(output, "r", encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        self.assertEqual(lines, ["frame,label", "0,H", "1,D", "2,X", "3,A"])

    def test_smart_tagging_priors_parse_set_pieces_and_goal_kickoffs(self):
        xml = """<file><ALL_INSTANCES>
          <instance>
            <code>SET PIECES</code><start>10.0</start><end>14.0</end>
            <label><group>Type</group><text>Kick Off (Start)</text></label>
          </instance>
          <instance>
            <code>SET PIECES</code><start>40.0</start><end>46.0</end>
            <label><group>Type</group><text>Kick Off (After Goal)</text></label>
          </instance>
        </ALL_INSTANCES></file>"""
        with tempfile.TemporaryDirectory() as folder:
            st_path = os.path.join(folder, "smart_tagging.xml")
            with open(st_path, "w", encoding="utf-8") as handle:
                handle.write(xml)
            info = model.load_smart_tagging_priors(st_path, n_frames=1500, fps=25.0)
        self.assertEqual(len(info["set_pieces"]), 2)
        self.assertEqual(info["kickoff_start_frames"], [300])
        self.assertEqual(info["kickoff_after_goal_frames"], [1075])
        self.assertTrue(np.all(info["dead_prior"][250:320] == 1.0))

    def test_high_flight_emits_x_and_sustained_stoppage_seals_d(self):
        scores = [1.2] * 50 + [0.0] * 80
        visible = [1] * 50 + [0] * 80
        high_flight = [0] * 20 + [1] * 10 + [0] * 100
        sustained = [0] * 50 + list(range(1, 81))
        labels = model.decode_states(
            _features(scores, visible=visible, high_flight=high_flight,
                      sustained_missing=sustained),
            min_stoppage_frames=75,
        )
        self.assertTrue(np.all(labels[:20] == "H"))
        self.assertTrue(np.all(labels[20:30] == "X"))
        self.assertTrue(np.all(labels[30:50] == "H"))
        self.assertTrue(np.all(labels[50:] == "D"))

    def test_refine_spells_absorbs_micro_turnover_and_bridges_short_same_team_d(self):
        seq = (
            ["H"] * 40 + ["A"] * 10 + ["H"] * 40 +
            ["D"] * 20 + ["H"] * 40 + ["D"] * 50 + ["A"] * 40
        )
        refined = model.refine_spells(np.array(seq), half_blocks=[(1, 0, len(seq) - 1)])
        self.assertTrue(np.all(refined[:90] == "H"))
        self.assertTrue(np.all(refined[90:110] == "X"))
        self.assertTrue(np.all(refined[110:150] == "H"))
        self.assertTrue(np.all(refined[150:200] == "D"))
        self.assertTrue(np.all(refined[200:240] == "A"))

    def test_raw_stream_fallback_isolates_stoppages_and_bridges_dropouts(self):
        raw = (["H"] * 60) + (["D"] * 10) + (["H"] * 60) + (["D"] * 80) + (["A"] * 70)
        half_blocks = [(1, 0, len(raw) - 1)]
        feats = model.extract_features_from_raw_stream(raw, len(raw), half_blocks)
        decoded = model.decode_raw_stream_states(feats, half_blocks)
        refined = model.refine_spells(decoded, half_blocks)
        self.assertTrue(np.all(refined[:60] == "H"))
        self.assertTrue(np.any(refined[60:70] == "X"))
        self.assertFalse(np.any(refined[60:70] == "D"))
        self.assertTrue(np.all(refined[70:130] == "H"))
        self.assertTrue(np.all(refined[130:210] == "D"))
        self.assertTrue(np.all(refined[210:] == "A"))

    def test_broadcast_fusion_recovers_ball_dropout_and_flags_invalid_homography_stoppage(self):
        xml = """<main><Teams><Team id='H'><Name>Home</Name></Team>
          <Team id='A'><Name>Away</Name></Team></Teams>
          <Players><Player teamId='H'/><Player teamId='A'/></Players></main>"""
        t_rows = []
        b_rows = []
        h_rows = ["frame,h00,h01,h02,h10,h11,h12,h20,h21,h22,reprojection_error,valid"]
        for k in range(12):
            fid = k + 1
            if k < 5:
                t_rows.append(f"{fid}:0.50,0.50,1.0;0.85,0.50,1.0:0.51,0.50,1.0")
                b_rows.append(f"{fid}:0.50,0.50,1.0;0.85,0.50,1.0:0.51,0.50,1.0")
                h_rows.append(f"{k},1,0,0,0,1,0,0,0,1,0.3,1")
            elif k < 9:
                t_rows.append(f"{fid}:0.50,0.50,1.0;0.85,0.50,1.0:NaN,NaN,NaN")
                b_rows.append(f"{fid}:0.50,0.50,1.0;0.85,0.50,1.0:0.51,0.50,1.0")
                h_rows.append(f"{k},1,0,0,0,1,0,0,0,1,0.3,1")
            else:
                t_rows.append(f"{fid}:0.50,0.50,0.0;0.85,0.50,0.0:NaN,NaN,NaN")
                b_rows.append(f"{fid}:0.50,0.50,0.0;0.85,0.50,0.0:NaN,NaN,NaN")
                h_rows.append(f"{k},NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaN,99.0,0")

        with tempfile.TemporaryDirectory() as folder:
            meta_p = os.path.join(folder, "meta.xml")
            t_raw_p = os.path.join(folder, "t_raw.txt")
            b_raw_p = os.path.join(folder, "b_raw.txt")
            b_hom_p = os.path.join(folder, "b_hom.csv")
            with open(meta_p, "w", encoding="utf-8") as h:
                h.write(xml)
            with open(t_raw_p, "w", encoding="utf-8") as h:
                h.write("\n".join(t_rows) + "\n")
            with open(b_raw_p, "w", encoding="utf-8") as h:
                h.write("\n".join(b_rows) + "\n")
            with open(b_hom_p, "w", encoding="utf-8") as h:
                h.write("\n".join(h_rows) + "\n")

            half_blocks = [(1, 0, 11)]
            bf = model.load_broadcast_fusion_streams(
                12, (105.3, 68.0), half_blocks, b_raw_p, meta_p, b_hom_p
            )
            feats = model.extract_features(
                t_raw_p, meta_p, 12, (105.3, 68.0), half_blocks, broadcast_features=bf
            )
            labels = model.decode_states(feats, half_blocks)
            fdiag = model.compute_fusion_diagnostics(feats, labels, half_blocks)

        self.assertEqual(fdiag["broadcast_dropout_recoveries"], 4)
        self.assertEqual(fdiag["multiview_stoppage_confirmations"], 3)
        self.assertEqual(fdiag["tactical_broadcast_co_observed_frames"], 5)
        self.assertEqual(fdiag["tactical_broadcast_team_agreement_pct"], 100.0)
        self.assertTrue(np.all(labels[:9] == "H"))
        self.assertTrue(np.all(labels[9:] == "D"))

    def test_pre_kickoff_dead_spans_enforces_second_half_warmup_d(self):
        spans = model.pre_kickoff_dead_spans("BAR-ATH")
        self.assertEqual(spans, [(110808, 113742)])
        seq = np.full(200, "H", dtype="<U1")
        refined = model.refine_spells(seq, half_blocks=[(1, 0, 199)], pre_kickoff_spans=[(0, 30)])
        self.assertTrue(np.all(refined[:30] == "D"))
        self.assertTrue(np.all(refined[30:] == "H"))

    def test_compute_fusion_diagnostics_logs_disagreements(self):
        xml = """<main><Teams><Team id='H'><Name>Home</Name></Team>
          <Team id='A'><Name>Away</Name></Team></Teams>
          <Players><Player teamId='H'/><Player teamId='A'/></Players></main>"""
        t_rows = [
            "1:0.50,0.50,1.0;0.85,0.50,1.0:0.51,0.50,1.0",
            "2:0.50,0.50,1.0;0.85,0.50,1.0:0.51,0.50,1.0",
        ]
        b_rows = [
            "1:0.50,0.50,1.0;0.85,0.50,1.0:0.51,0.50,1.0",
            "2:0.50,0.50,1.0;0.85,0.50,1.0:0.84,0.50,1.0",
        ]
        with tempfile.TemporaryDirectory() as folder:
            meta_p = os.path.join(folder, "meta.xml")
            t_raw_p = os.path.join(folder, "t_raw.txt")
            b_raw_p = os.path.join(folder, "b_raw.txt")
            with open(meta_p, "w", encoding="utf-8") as h:
                h.write(xml)
            with open(t_raw_p, "w", encoding="utf-8") as h:
                h.write("\n".join(t_rows) + "\n")
            with open(b_raw_p, "w", encoding="utf-8") as h:
                h.write("\n".join(b_rows) + "\n")

            bf = model.load_broadcast_fusion_streams(
                2, (105.3, 68.0), [(1, 0, 1)], b_raw_p, meta_p, None
            )
            feats = model.extract_features(
                t_raw_p, meta_p, 2, (105.3, 68.0), [(1, 0, 1)], broadcast_features=bf
            )
            fdiag = model.compute_fusion_diagnostics(feats, np.array(["H", "H"]), [(1, 0, 1)])

        self.assertEqual(fdiag["tactical_broadcast_co_observed_frames"], 2)
        self.assertEqual(fdiag["tactical_broadcast_disagreement_frames"], 1)
        self.assertEqual(fdiag["tactical_broadcast_team_agreement_pct"], 50.0)

    def test_analyze_spells_derives_drawing_leading_trailing_from_goals_xml(self):
        xml = """<file><ALL_INSTANCES>
          <instance><code>GOALS</code><start>1.0</start><end>2.0</end>
            <label><group>Team</group><text>Barcelona</text></label></instance>
          <instance><code>SET PIECES</code><start>2.0</start><end>2.4</end>
            <label><group>Type</group><text>Kick Off (After Goal)</text></label></instance>
          <instance><code>GOALS</code><start>4.0</start><end>5.0</end>
            <label><group>Team</group><text>Atletic Club</text></label></instance>
          <instance><code>SET PIECES</code><start>5.0</start><end>5.4</end>
            <label><group>Type</group><text>Kick Off (After Goal)</text></label></instance>
          <instance><code>GOALS</code><start>6.0</start><end>7.0</end>
            <label><group>Team</group><text>Atletic Club</text></label></instance>
          <instance><code>SET PIECES</code><start>7.0</start><end>7.4</end>
            <label><group>Type</group><text>Kick Off (After Goal)</text></label></instance>
        </ALL_INSTANCES></file>"""
        with tempfile.TemporaryDirectory() as folder:
            xml_path = os.path.join(folder, "smart.xml")
            with open(xml_path, "w", encoding="utf-8") as h:
                h.write(xml)
            events = analyze_spells.load_goal_restart_events(xml_path, 250, fps=25.0)
            labels = np.full(250, "H", dtype="<U1")
            phases, source = analyze_spells.detect_game_state_phases(
                labels, [(1, 0, 149), (2, 160, 249)], xml_path
            )

        self.assertEqual(len(events), 3)
        self.assertIn("GOALS", source)
        self.assertEqual([(p["score_label"], p["home_state"], p["away_state"]) for p in phases], [
            ("0-0", "Drawing", "Drawing"),
            ("1-0", "Leading", "Trailing"),
            ("1-1", "Drawing", "Drawing"),
            ("1-2", "Trailing", "Leading"),
        ])

    def test_default_cli_mode_uses_mode2_even_when_tactical_files_exist(self):
        xml = """<main><Teams><Team id='H'><Name>Barcelona</Name></Team>
          <Team id='A'><Name>Athletic Club</Name></Team></Teams>
          <Players><Player teamId='H'/><Player teamId='A'/></Players></main>"""
        with tempfile.TemporaryDirectory() as folder:
            tactical_dir = os.path.join(folder, "tactical")
            os.makedirs(tactical_dir, exist_ok=True)
            with open(os.path.join(tactical_dir, "BAR-ATH_tactical_atd.xml"), "w", encoding="utf-8") as h:
                h.write(xml)
            # Deliberately invalid full-length raw file: mode2 must ignore it when default mode runs.
            with open(os.path.join(tactical_dir, "BAR-ATH_tactical_atd.txt"), "w", encoding="utf-8") as h:
                h.write("1:0.50,0.50,0.0;0.80,0.50,0.0:0.51,0.50,0.0\n")
            out_default = os.path.join(folder, "default_out.csv")
            out_explicit = os.path.join(folder, "explicit_mode2_out.csv")

            model.main(["--data-dir", folder, "--out", out_default])
            model.main(["--data-dir", folder, "--mode", "mode2", "--out", out_explicit])

            with open(out_default, "rb") as f1, open(out_explicit, "rb") as f2:
                b1 = f1.read()
                b2 = f2.read()
            self.assertEqual(b1, b2)
            self.assertGreater(len(b1), 1_000_000)


if __name__ == "__main__":
    unittest.main()
