# Promptimate benchmark

The automatic scoreboard for measuring engine/config/post-processing changes. Metrics live in
`mcp_server/metrics.py`, the prompt suite in `prompts.json` (18 prompts: locomotion, stop, gesture, full-body,
stylized, 3 multi-segment sequences, each with machine-checkable expectations).

```powershell
$env:TEMP="D:\tmp"; $env:TMP="D:\tmp"
.venv\Scripts\python bench\run_bench.py --name baseline_s30 --steps 30 --seeds 0,1 --postprocess
.venv\Scripts\python bench\run_bench.py --name s20 --steps 20 --prompts walk,jog,wave
.venv\Scripts\python bench\run_bench.py --name cfg3 --engine-dir third_party\kimodo.cpp\build\promptimate --text-cfg 3
.venv\Scripts\python bench\run_bench.py --name x --env KIMODO_SOMETHING=1          # forwarded to the worker
.venv\Scripts\python bench\run_bench.py --name base_rescored --rescore bench\results\baseline_s30 --postprocess  # no GPU
.venv\Scripts\python bench\compare.py baseline_s30 s20 --category --prompt          # --pp: post-processed metrics
```

Output in `results/<name>/`: `clips/<id>_s<seed>/` (raw f32 output, `pp_*.f32` cleaned output, `preview.png`),
`results.jsonl` (one row per clip with all metrics), `summary.json` (means overall, per category, per prompt, timing),
`contact_sheet.png` (one row per prompt, one column per seed), `config.json`.

A 2-step warm-up generation loads the models first, so every timed clip is warm (`gen_seconds` is engine time without
the GPU-lock wait; `wall_seconds` includes it).

## Reading the numbers
| metric | better | meaning |
|---|---|---|
| `expectation_score` | higher | mean soft score (0..1) of the prompt's expectation checks (`exp_*` per check) |
| `expectation_pass_rate` | higher | fraction of checks fully met |
| `skate_speed_cms`, `skate_ratio` | lower | horizontal speed of ankle/toe joints while in contact (low and slow); share of contact frames > 15 cm/s |
| `penetration_max_cm`, `float_ratio` | lower | sole/toe below y=0; share of frames in no-contact runs > 0.7 s (longer than a jump) |
| `jerk_mean`, `jerk_p95` (m/s³) | lower | joint jerk from 3rd finite differences at 30 fps |
| `pop_frames`, `max_joint_acc_ms2` | lower | frames where a joint accelerates > 120 m/s² (glitches) |
| `seam_jerk_ratio`, `seam_vel_jump_ms` | lower | peak jerk around segment boundaries ÷ clip median; velocity change across the seam |
| `root_end_speed_ms` | context | mean root speed over the last 20 % (for "stops" prompts) |

Noise floor on the existing clips: standing idles skate ≈ 0.5–0.7 cm/s and travel < 4 cm; Kimodo walks skate 12–16 cm/s.

## Fast loop (use this while iterating)
- All GPU work goes through the shared daemon `mcp_server/motiond.py` (auto-started, models stay warm across scripts,
  results cached in `.cache/gen` keyed by engine build + request). Changing post-processing, metrics or server logic
  re-runs from cache in seconds; `--no-cache` forces generation, `--direct` uses a private engine (engine A/B only).
- Tiers (`bench/tiers.py`): `--tier smoke` (6 prompts x 1 seed, the failure modes we care about), `standard`
  (18 x 2), `full` (18 x 3, final numbers only).
- `server_eval.py --tier smoke --opt takes=1 ...` runs the real MCP server pipeline (takes, auto-stop, cleanup).
- `compare.py A B` ends with a **paired** table: same prompt+seed deltas with a bootstrap 95% CI and a verdict
  (better / worse / no clear difference). If the CI straddles 0, the change is noise at this sample size.
- `report_run.py RUN --vs BASE [--gifs] [--pp]` writes `results/RUN_vs_BASE.html`: side-by-side clips, worst
  regressions first.
- Engine experiments: `engine_ab.py` (stock vs patched latency/equivalence), `placement_test.py` (VRAM placement),
  `memory_cliff.py` / `env_sweep.py` (slow shapes), `constraint_test.py` (constraints steer the motion).
