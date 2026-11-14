#!/bin/sh
# Real headless Claude Code session driving the local MCP server; full event stream saved for the video.
cd /d/unity-text-to-anim/demo/claude_run
export TEMP='D:\tmp' TMP='D:\tmp'
claude -p "$(cat prompt.txt)" --mcp-config mcp.json --strict-mcp-config \
  --allowedTools "mcp__kimodo-motion__generate_motion,mcp__kimodo-motion__get_motion_preview,mcp__kimodo-motion__list_motions,mcp__kimodo-motion__validate_in_unity,mcp__kimodo-motion__worker_status" \
  --output-format stream-json --verbose > session.jsonl 2> session.err
echo "exit=$?"
