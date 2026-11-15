"""Regression checks for postprocess.py on the generated clips in output/*/ (no GPU needed).

Run:  .venv\\Scripts\\python.exe mcp_server\\tests_postprocess.py        (prints a before/after table)
  or: .venv\\Scripts\\python.exe -m pytest mcp_server\\tests_postprocess.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motion  # noqa: E402
import postprocess as pp  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[1] / "output"
LEG_JOINTS = list(range(22, 30))
BONE_LEN = np.linalg.norm(motion.OFFSETS, axis=1)


def clips():
    return sorted(d for d in OUTPUT.iterdir() if (d / "root_positions.f32").exists()
                  and (d / "local_rotations_xyzw.f32").exists()) if OUTPUT.is_dir() else []


def _sane(root, rot):
    assert np.isfinite(root).all() and np.isfinite(rot).all(), "NaN/inf"
    assert np.abs(np.linalg.norm(rot, axis=-1) - 1).max() < 1e-5, "non-unit quaternion"
    pos = motion.fk(root, rot)
    for j, p in enumerate(motion.PARENTS):
        if p >= 0:
            assert np.abs(np.linalg.norm(pos[:, j] - pos[:, p], axis=-1) - BONE_LEN[j]).max() < 1e-4, "bone length"


def _jerk_seam(pos, L):
    """Jerk at each copy boundary of a tiled loop vs the median jerk elsewhere."""
    j = np.linalg.norm(np.diff(pos, n=3, axis=0), axis=-1).mean(1)
    seam = max(j[max(0, b - 3):b + 1].max() for b in (L, 2 * L))
    inner = np.concatenate([j[3:L - 3], j[L + 3:2 * L - 3]])
    ref = max(np.percentile(inner, 90) if len(inner) else 0.0, 2e-4)  # floor: 2e-4 m/frame^3 = 5.4 m/s^3
    return float(seam / ref)


def check_clean(d):
    root, rot = motion.load(d)
    r2, q2, info = pp.clean(root, rot)
    _sane(r2, q2)
    assert r2.dtype == np.float32 and q2.dtype == np.float32
    # root: xz untouched, y moved by one constant (ground offset) only
    assert np.array_equal(r2[:, [0, 2]], root[:, [0, 2]]), "root xz changed"
    dy = r2[:, 1].astype(np.float64) - root[:, 1]
    assert np.ptp(dy) < 1e-6 and abs(dy[0] - info["ground_offset_m"]) < 1e-4, "root y not a constant shift"
    # only leg joints are rotated
    others = [j for j in range(motion.J) if j not in LEG_JOINTS]
    assert np.array_equal(q2[:, others], rot[:, others]), "non-leg rotations changed"
    b, a = info["before"], info["after"]
    # Already-clean inputs (< 3 cm/s, e.g. sitting, where contact detection is ambiguous) may move by a few mm/s.
    tol = 0.05 if b["skate_cms"] > 3.0 else 0.5
    assert a["skate_cms"] <= b["skate_cms"] + tol, ("skate", b, a)
    assert a["pivot_skate_cms"] <= b["pivot_skate_cms"] + 0.05, ("pivot skate", b, a)
    if b["pivot_skate_cms"] > 3.0:  # below that (sitting, idles) contacts are ambiguous; just no regression
        assert a["pivot_skate_cms"] <= 0.5 * b["pivot_skate_cms"], ("skate not halved", b, a)
    assert a["penetration_max_cm"] <= 0.05, ("penetration", a)
    assert a["jerk"] <= 1.10 * b["jerk"] + 0.5, ("jerk", b, a)
    return info


def check_smooth(d):
    root, rot = motion.load(d)
    r2, q2, info = pp.clean(root, rot, foot_lock=False, ground=False, smooth=True)
    _sane(r2, q2)
    assert info["after"]["jerk"] <= info["before"]["jerk"] + 1e-6, ("smoothing raised jerk", info)
    # per-frame corrections bounded (sharp intended motion preserved)
    ang = np.degrees(pp.qangle(pp.qnorm(rot.astype(np.float64)), q2.astype(np.float64)))
    assert ang.max() <= 3.0 + 1e-3, ang.max()
    assert np.abs(r2 - root).max() <= 0.01 + 1e-6
    return info


def check_in_place(d):
    root, rot = motion.load(d)
    r2, q2 = pp.make_in_place(root, rot)
    _sane(r2, q2)
    assert np.array_equal(q2, rot) and np.array_equal(r2[:, 1], root[:, 1]), "in-place must keep rotations/height"
    travel = np.linalg.norm(r2[-1, [0, 2]] - r2[0, [0, 2]])
    assert travel < 0.05, travel
    assert np.abs(r2[:, [0, 2]]).max() < 0.6, "residual sway too large"
    return float(travel)


def check_loop(d):
    root, rot = motion.load(d)
    raw = pp.metrics(root, rot)
    r1, q1, _ = pp.clean(root, rot)
    lr, lq, li = pp.make_loop(r1, q1)
    _sane(lr, lq)
    sb, sa = li["seam_before"], li["seam_after"]
    assert sa["seam_cm"] <= sb["seam_cm"] + 0.05, (sb, sa)
    assert sa["seam_ratio"] <= max(1.6, sb["seam_ratio"]), (sb, sa)
    # foot-locked loop skates less than the raw clip
    assert li["foot_lock"]["after"]["pivot_skate_cms"] <= raw["pivot_skate_cms"] + 0.05, (raw, li["foot_lock"])
    # seam continuity when played back-to-back (root motion applied)
    L = len(lr)
    tr, tq = pp._tile(lr, lq, li["loop_offset_xz_m"], 0.0, copies=3)
    js = _jerk_seam(pp.fk(tr, tq), L)
    assert js < 3.0, ("seam jerk", js)
    return li, js


def test_save_roundtrip():
    d = clips()[0]
    root, rot = motion.load(d)
    with tempfile.TemporaryDirectory() as t:
        pp.save(t, root, rot)
        r2, q2 = motion.load(Path(t))
    assert np.array_equal(r2, root) and np.array_equal(q2, rot)


def test_contacts_idle():
    for d in clips():
        if d.name.startswith("idle"):
            pos = motion.fk(*motion.load(d))
            c = pp.detect_contacts(pos)
            assert (c["left_toe"] | c["left_heel"]).mean() > 0.9 and (c["right_toe"] | c["right_heel"]).mean() > 0.9


def test_model_contacts():
    """Engine-predicted contacts (foot_contacts.f32): union must not skate more than the heuristic, measured
    against every frame either source calls planted; also check the column order (left channels track the left
    foot)."""
    # production-config clips only (30 steps): engine A/B, constraint tests and the pm_s30 benchmark run
    res = OUTPUT.parent / "bench" / "results"
    dirs = sorted(f.parent for sub in ("engine_ab", "constraints", "pm_s30") for f in (res / sub).rglob("foot_contacts.f32")
                  if not f.parent.name.startswith("_") and f.parent.name not in ("warm", "w", "w2"))  # 1-step warm-ups
    results = []
    for d in dirs:
        root, rot = motion.load(d)
        mc = pp.load_contacts(d)
        assert mc is not None and mc.shape == (len(root), 4)
        pos = motion.fk(root, rot)
        heur = pp.detect_contacts(pos)
        mod = pp.contacts_from_model(mc, pos, mode="model")
        # Column order: the given left/right assignment must agree with the heuristic at least as well as the
        # mirrored one (absolute agreement is legitimately low for crawls, falls and sitting).
        agree = np.mean([(mod[k] == heur[k]).mean() for k in pp.CONTACT_KEYS])
        mirror = {k: mod[k.replace("left", "@").replace("right", "left").replace("@", "right")] for k in pp.CONTACT_KEYS}
        agree_m = np.mean([(mirror[k] == heur[k]).mean() for k in pp.CONTACT_KEYS])
        assert agree >= agree_m - 0.02, ("column order?", d.name, round(agree, 3), round(agree_m, 3))
        union = {k: heur[k] | mod[k] for k in heur}
        out = {}
        for mode in ("heuristic", "union"):
            r2, q2, info = pp.clean(root, rot, contacts=mc, contact_mode=mode)
            _sane(r2, q2)
            out[mode] = pp.metrics(r2, q2, contacts=union)["pivot_skate_cms"]
            # seated poses: leg IK sometimes cannot lift the last few mm (knees fully bent); invisible
            assert info["after"]["penetration_max_cm"] <= 2.0, (d.name, mode, info["after"]["penetration_max_cm"])
        assert out["union"] <= out["heuristic"] + (0.05 if out["heuristic"] > 1.0 else 0.3), (d, out)
        results.append((d, out))
    return results


def test_clean_all():
    assert clips(), "no clips in output/"
    for d in clips():
        check_clean(d)


def test_smooth_all():
    for d in clips():
        check_smooth(d)


def test_in_place_all():
    for d in clips():
        check_in_place(d)


LOOP_CLIPS = ("walk_1", "walk_2", "walk_3", "jog", "walk_phone", "zombie_1", "zombie_2", "zombie_3",
              "guard_shot1_patrol_walk", "injured_limp", "idle_talk_1", "dance_1")


def test_loops():
    for d in clips():
        if d.name.startswith(LOOP_CLIPS):
            check_loop(d)


def main():
    rows, fails = [], []
    tot = {"skate": [0, 0], "piv": [0, 0], "pen": [0, 0], "jerk": [0, 0]}
    for d in clips():
        try:
            info = check_clean(d)
            check_smooth(d)
            check_in_place(d)
            status = "ok"
        except AssertionError as e:
            status = f"FAIL {e}"
            fails.append(d.name)
            info = pp.clean(*motion.load(d))[2]
        b, a = info["before"], info["after"]
        for k, key in (("skate", "skate_cms"), ("piv", "pivot_skate_cms"), ("pen", "penetration_max_cm"),
                       ("jerk", "jerk")):
            tot[k][0] += b[key]
            tot[k][1] += a[key]
        rows.append(f"{d.name[:40]:40s} {b['skate_cms']:6.2f} -> {a['skate_cms']:5.2f}  {b['pivot_skate_cms']:6.2f}"
                    f" -> {a['pivot_skate_cms']:5.2f}  {b['penetration_max_cm']:5.2f} -> {a['penetration_max_cm']:4.2f}"
                    f"  {b['jerk']:6.1f} -> {a['jerk']:6.1f}  {info['ground_offset_m']:+.3f}  {status}")
    print(f"{'clip':40s} {'skate cm/s':>15s}  {'pivot skate':>14s}  {'pen max cm':>13s}  {'jerk m/s^3':>16s}  ground")
    print("\n".join(rows))
    n = max(len(rows), 1)
    print(f"{'MEAN over ' + str(n) + ' clips':40s} {tot['skate'][0] / n:6.2f} -> {tot['skate'][1] / n:5.2f}  "
          f"{tot['piv'][0] / n:6.2f} -> {tot['piv'][1] / n:5.2f}  {tot['pen'][0] / n:5.2f} -> {tot['pen'][1] / n:4.2f}"
          f"  {tot['jerk'][0] / n:6.1f} -> {tot['jerk'][1] / n:6.1f}")
    print("\nloops (clean -> make_loop):")
    for d in clips():
        if d.name.startswith(LOOP_CLIPS):
            try:
                li, js = check_loop(d)
                st = "ok"
            except AssertionError as e:
                fails.append("loop:" + d.name)
                st = f"FAIL {e}"
                li, js = pp.make_loop(*pp.clean(*motion.load(d))[:2])[2], float("nan")
            print(f"  {d.name[:34]:34s} window {li['window']} {li['seconds']:4.2f}s  seam {li['seam_before']['seam_cm']:5.2f}"
                  f" -> {li['seam_after']['seam_cm']:4.2f} cm (ratio {li['seam_before']['seam_ratio']:5.2f} -> "
                  f"{li['seam_after']['seam_ratio']:4.2f})  skate {li['foot_lock']['after']['pivot_skate_cms']:4.2f}"
                  f"  seam-jerk x{js:.2f}  {st}")
    test_save_roundtrip()
    test_contacts_idle()
    try:
        res = test_model_contacts()
        print("\nmodel contacts (residual pivot skate vs heuristic|model reference, cm/s):")
        for d, o in res:
            print(f"  {d.parent.name}/{d.name}: heuristic {o['heuristic']:.2f}  union {o['union']:.2f}")
    except AssertionError as e:
        fails.append(f"model_contacts {e}")
    print("\nFAILED: " + ", ".join(fails) if fails else "\nall checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
