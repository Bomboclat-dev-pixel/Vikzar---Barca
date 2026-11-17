# Vikzar — Frame-Level Ball Possession & Spell Segmentation (`BAR-ATH`)

Submission by **Team Vikzar** for **More Than a Hack 2027 — Phase 1: Initial Challenge** (Mobile World Capital Barcelona, Barça Innovation Hub & Metrica Sports).

Predicts frame-by-frame possession states (`H`: FC Barcelona, `A`: Athletic Club, `D`: Dead Ball, `X`: Uncertain/In-Flight) across all **199,319 frames** (`25 fps`, ~133 min) of the `BAR-ATH` match dataset, optimized for spell-level temporal IoU recovery (`spellF1`) and strict deterministic reproducibility.

---

## Development Timeline & Engineering Progression

* **Oct 1 – Nov 10, 2026 | Registration & Problem Formulation**
  * Registered Team **Vikzar** and analyzed the Phase 1 scoring mechanics (`spell_f1_mean` across IoU thresholds `0.3–0.7`, `macroF1`, and transition latency).
  * Identified the two primary failure modes of frame-wise proximity baselines on 25 Hz tracking data: (1) false turnover splits (`H -> A -> H`) during aerial passes and 40.7% graded tactical ball dropouts, and (2) false spell merges (`H H H H` instead of `H H D D H H`) when dead-ball stoppages go undetected.
* **Oct 20 – Early Nov 2026 | Baseline Benchmarking & Kinematic State Machine (`V1` → `V2.0`)**
  * Benchmarked the official proximity baselines (`baseline_raw`: `0.0486` full-match `spellF1`; `baseline_smooth50` floor: `0.2433` full-match `spellF1`, `0.3256` on the 5-minute public slice).
  * Built `team_model.py` to model player-to-ball distance margins, local numerical support (`4.0–4.5 m`), approach velocity, and temporal hysteresis rather than raw nearest-player voting.
* **Nov 17, 2026 | Dead-Ball Anchoring, Dual-Camera Fusion & Downstream Analytics (`V2.1` → `V2.2`)**
  * **V2.1 (Smart Tagging & `X`-Forward-Fill Exploitation):** Integrated algorithmic dead-ball (`D`) intervals from `BAR-ATH_tactical_smart_tagging.xml` (59 `SET PIECES` markers) combined with pitch boundary exits (`105.3 m × 68.0 m`), high-velocity aerial `X` abstention (`> 18 m/s`, leveraging the scorer's forward-fill behavior inside active spells), and `25-frame` (`1.0 s`) turnover persistence with micro-spell filtering (`< 12 frames`).
  * **V2.2 (Tactical-First + Broadcast-Assisted Sensor Fusion):** Added synchronized broadcast tracking & homography gating (`BAR-ATH_broadcast_atd.txt`, `BAR-ATH_broadcast_homography.csv`) to recover live ball dropouts, cross-check TV replay cutaways (`~34.2%` invalid broadcast homography) with stationary tactical ball states for high-confidence `D` detection, and seal the 2,934 Half 2 pre-kickoff dead frames (`110,808–113,741`), eliminating 9 warmup phantom spells (`478 → 469` total spells).
  * **Downstream Game-State & Role-Cluster Profiler (`analyze_spells.py`):** Derives live match game states (**Drawing**, **Leading**, **Trailing**) directly from official Smart Tagging XML `GOALS` (`Team`) + `Kick Off (After Goal)` restart tags and computes game-state-conditioned recruitment metrics (Press-Resistance Index, `< 6 s` Gegenpressing recovery, tactical role clusters).

---

## Repository Structure

```text
Vikzar---Barca/
├── team_model.py                 # V2.2 dual-camera possession & dead-ball state machine
├── analyze_spells.py             # Algorithmic game-state & role-clustered recruitment profiler
├── generate_pdf_report.py        # Compiles 4-page 16:9 widescreen vector technical deck PDF
├── requirements.txt              # Pinned runtime dependencies (numpy, reportlab, matplotlib)
├── starter/                      # Official competition baseline & data loaders
├── evaluation/                   # Official submission format validator & spellF1 evaluator
├── tests/
│   └── test_team_model.py        # 17 unit tests covering kinematics, XML goals/priors, --mode flags & decoding
├── figures/                      # Generated benchmark, game-state, and role-profile charts
└── TECHNICAL_REPORT.md           # Full methodology, rule compliance & Phase 2 roadmap
```

*(Note: Raw match videos, ATD tracking files, and submission artifacts are excluded via `.gitignore` in accordance with competition data rules.)*

---

## Quickstart & Deterministic Reproduction

### 1. Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Optional Local Match Data Layout
If running with the official `BAR-ATH` match bundle mounted locally, place the provided files under `data/`:
```text
data/
├── tactical/
│   ├── BAR-ATH_tactical_atd.txt
│   ├── BAR-ATH_tactical_atd.xml
│   ├── BAR-ATH_tactical_homography.csv
│   └── BAR-ATH_tactical_smart_tagging.xml
└── broadcast/
    ├── BAR-ATH_broadcast_atd.txt
    ├── BAR-ATH_broadcast_atd.xml
    └── BAR-ATH_broadcast_homography.csv
```
*(By default `--mode mode2` runs deterministically even when `data/` is mounted on disk so any clean checkout reproduces the exact promoted CSV; pass `--mode mode1` to reproduce the full ATD + Broadcast ablation.)*

### 3. Generate & Validate Submission CSV (One-Line Reproduction)
```bash
python3 team_model.py --mode mode2 --out submission_artifacts/vikzar.csv && python3 evaluation/validate_submission.py submission_artifacts/vikzar.csv
```

### 4. Run Unit Tests, Sanity Check & Downstream Analytics
```bash
# Run 17 unit tests
python3 -m unittest discover -s tests -v

# Single sanity check against public 5-minute ground truth (zero hyperparameter tuning)
python3 team_model.py --mode mode2 --out evaluation/results/vikzar.csv && python3 evaluation/run_evaluation.py && rm -f evaluation/results/vikzar.csv

# Generate game-state metrics (Drawing / Leading / Trailing) & figures
python3 analyze_spells.py --submission submission_artifacts/vikzar.csv
```

---

## Verification Summary (`vikzar` — V2.2)

| Metric / Diagnostic | `baseline_smooth50` (Floor) | `vikzar` (V2.2 Final) |
| :--- | :---: | :---: |
| **Row Count & Format** | 199,319 (`OK`) | **199,319 (`OK`, byte-identical)** |
| **Full-Match Contiguous Spells** | 669 | **469** (`7.8 s` mean duration) |
| **Public 5-min `spellF1`** | `0.3256` | **`0.3610`** |
| **Public 5-min `spellF1@0.5`** | `0.3256` | **`0.3902`** |
| **Public 5-min `macroF1`** | `0.6207` | **`0.6466`** |
| **Public 5-min Dead-Ball `f1_D`** | `0.3225` | **`0.4210`** |
| **Public 5-min `transF1` (±25f)** | `0.0816` | **`0.2979`** |

---

## Compliance Statement
* **Zero External Match Data:** All game-state and stoppage boundaries are derived algorithmically from the provided `BAR-ATH` ATD tracking, homography, and Smart Tagging XML files.
* **Zero Public-Slice Overfitting:** Model parameters were engineered from domain physics and tracking diagnostics; `evaluation/run_evaluation.py` was executed strictly as a post-hoc sanity check.
