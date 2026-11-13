# 06: Claude integration

## Why not "log in with your Claude subscription"
Anthropic's terms say third-party developers may not offer claude.ai login, or route requests through Free, Pro, Max or
Ultra plan credentials on behalf of their users, without prior approval. Products should use API keys.
See https://code.claude.com/docs/en/legal-and-compliance. Recheck this before shipping, because the policy and
Agent SDK billing changed during 2026.

Also, an LLM isn't the right tool for generating the motion itself (see 01-landscape.md).

## Design: Claude as director, Kimodo as animator
The plugin runs a **local MCP server**. The user connects it to *their own* Claude Code or Claude Desktop, so usage
comes out of their own plan and the plugin never handles their credentials.

Example: *"Guard patrols between these two pillars, hears a noise, turns, draws sword."*
Claude:
1. reads the scene (`list_humanoids`, `get_scene_objects`) to find the guard and pillar positions,
2. plans segments, each with a Kimodo prompt, duration, root waypoints (from the pillar transforms) and end-effector
   targets (hand to the sword hilt),
3. calls `generate_motion`, places the result on a Timeline, reviews it, and regenerates segments if needed.

## Candidate MCP tools
- `list_humanoids()`, `get_scene_objects(filter)`
- `generate_motion(target, segments[{prompt, duration}], constraints{root_path, keyframes, effectors}, seed, loop)`
- `place_on_timeline(clip, director, track, start)`
- `preview(clip, character)`: screenshot or frame strip so Claude can check the result visually

Existing Unity MCP projects could provide the general scene and editor tools, so this plugin would only need to add
the motion tools. Survey them before building.

## Optional: API key mode
For in-editor chat without an external client, allow a user-supplied Anthropic API key (billed through the API, which
is allowed). This is secondary to the MCP route.
