#!/bin/sh
# Usage: demo/retargetcheck.sh [variant] [clip1,clip2]  -> runs RetargetCheck headless, prints a table
cd /d/unity-text-to-anim
export TEMP='D:\tmp' TMP='D:\tmp'
V=${1:-current}
"/d/Unity/Editors/6000.0.34f1/Editor/Unity.exe" -batchmode -nographics -projectPath 'D:\unity-text-to-anim\unity\DemoStudio' \
  -executeMethod RetargetCheck.Run -logFile "D:\unity-text-to-anim\logs\retarget_$V.log" -variant "$V" ${2:+-clips "$2"}
echo "unity exit=$?"
grep -E "TTA_RT_SUMMARY|TTA_RT_ERROR|error CS|Exception" logs/retarget_$V.log | head -8
.venv/Scripts/python demo/retarget_table.py demo/retarget_report_$V.json
