#!/bin/sh
# Usage: demo/charcheck.sh [clip1,clip2,...]   -> runs CharacterCheck headless, prints a table
cd /d/unity-text-to-anim
export TEMP='D:\tmp' TMP='D:\tmp'
"/d/Unity/Editors/6000.0.34f1/Editor/Unity.exe" -batchmode -nographics -projectPath 'D:\unity-text-to-anim\unity\DemoStudio' \
  -executeMethod CharacterCheck.Run -logFile 'D:\unity-text-to-anim\logs\charcheck.log' ${1:+-clips "$1"}
echo "unity exit=$?"
grep -E "TTA_CHAR_SUMMARY|error CS|Exception:" logs/charcheck.log | head -5
grep "TTA_CHAR " logs/charcheck.log | sed 's/TTA_CHAR //' | .venv/Scripts/python -c "
import sys,json
for l in sys.stdin:
    r=json.loads(l); print(f\"{r['character'][:16]:16} {r['clip'][:24]:24} {'PASS' if r['passed'] else 'FAIL'} face={r['facingErrMaxDeg']:.0f} trav={r['travelErrDeg']:.0f} toes={r['toesForwardRatio']:.2f} hand={r['handednessRatio']:.2f} gnd={r['groundedRatio']:.2f} {r['failures']}\")"
