"""Can an off-the-shelf human pose detector read the mannequin driver video? (proxy for what Kling / Wan-Animate's
pose front end sees). Compares MediaPipe PoseLandmarker 2D keypoints against the renderer's exact projected joints.

Run with a separate venv that has mediapipe + opencv (never the project .venv):
  D:\\tmp\\posevenv\\Scripts\\python.exe -I pose_check.py TEST_DIR [TEST_DIR ...]
Metrics per test: detection rate, PCK@0.1 (keypoint within 10% of body height), mean error in % of body height,
left/right swap rate (frames where the mirrored assignment fits better), right-wrist path correlation.
"""
import json
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

MODEL = r"D:\tmp\mp_models\pose_landmarker_heavy.task"
# mediapipe index -> our joint name (mediapipe left = subject's left)
PAIRS = {11: "LeftArm", 12: "RightArm", 13: "LeftForeArm", 14: "RightForeArm", 15: "LeftHand", 16: "RightHand",
         23: "LeftLeg", 24: "RightLeg", 25: "LeftShin", 26: "RightShin", 27: "LeftFoot", 28: "RightFoot"}
MIRROR = {11: 12, 12: 11, 13: 14, 14: 13, 15: 16, 16: 15, 23: 24, 24: 23, 25: 26, 26: 25, 27: 28, 28: 27}


def run(test_dir: Path) -> dict:
    gt = json.loads((test_dir / "driver.joints2d.json").read_text())
    names = gt["names"]; uv = np.array(gt["uv"])  # (F,J,2)
    idx = {n: i for i, n in enumerate(names)}
    opts = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=MODEL),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
        min_pose_detection_confidence=0.3, min_tracking_confidence=0.3)
    det = mp.tasks.vision.PoseLandmarker.create_from_options(opts)
    cap = cv2.VideoCapture(str(test_dir / "driver.mp4"))
    f = 0; found = 0; errs = []; pck = []; swaps = 0; rw_pred = []; rw_gt = []
    overlay_frames = []
    while True:
        ok, img = cap.read()
        if not ok or f >= len(uv):
            break
        h, w = img.shape[:2]
        res = det.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)),
                                   int(f * 1000 / 30))
        g = uv[f]
        body_h = max(g[:, 1].max() - g[:, 1].min(), 1.0)
        if res.pose_landmarks:
            found += 1
            lm = res.pose_landmarks[0]
            P = {k: np.array([lm[k].x * w, lm[k].y * h]) for k in PAIRS}
            e = [np.linalg.norm(P[k] - g[idx[n]]) / body_h for k, n in PAIRS.items()]
            em = [np.linalg.norm(P[MIRROR[k]] - g[idx[n]]) / body_h for k, n in PAIRS.items()]
            errs.append(np.mean(e)); pck.append(np.mean(np.array(e) < 0.1))
            if np.mean(em) < np.mean(e) * 0.8:
                swaps += 1
            rw_pred.append(P[16]); rw_gt.append(g[idx["RightHand"]])
            if f % 30 == 0:
                vis = img.copy()
                for k, n in PAIRS.items():
                    gx, gy = g[idx[n]].astype(int); px, py = P[k].astype(int)
                    col = (0, 0, 255) if "Right" in n else (255, 120, 0)
                    cv2.circle(vis, (gx, gy), 7, (0, 200, 0), 2)  # green ring = ground truth
                    cv2.circle(vis, (px, py), 5, col, -1)        # red = detected right, blue = detected left
                overlay_frames.append(cv2.resize(vis, (w // 3, h // 3)))
        f += 1
    det.close()
    if overlay_frames:
        cv2.imwrite(str(test_dir / "pose_check.png"), np.hstack(overlay_frames))
    rw_pred, rw_gt = np.array(rw_pred), np.array(rw_gt)
    corr = None
    if len(rw_pred) > 5:
        corr = float(np.mean([np.corrcoef(rw_pred[:, d], rw_gt[:, d])[0, 1] for d in range(2)]))
    out = {"frames": f, "detect_rate": round(found / max(f, 1), 3),
           "pck@0.1": round(float(np.mean(pck)), 3) if pck else None,
           "mean_err_pct_body_h": round(100 * float(np.mean(errs)), 1) if errs else None,
           "lr_swap_rate": round(swaps / max(found, 1), 3),
           "right_wrist_path_corr": round(corr, 3) if corr is not None else None}
    (test_dir / "pose_check.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(Path(d).name, run(Path(d)), flush=True)
