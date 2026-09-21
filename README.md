# cli-anything-capcut

[![tests](https://github.com/juliang8507/cli-anything-capcut/actions/workflows/test.yml/badge.svg)](https://github.com/juliang8507/cli-anything-capcut/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Windows only](https://img.shields.io/badge/platform-Windows-0078D4.svg)](#requirements)

English · **[한국어](README.ko.md)**

**A CLI that lets AI agents drive CapCut video editing directly.**
Agents like Claude Code and Cursor can build, validate and render CapCut / JianYing (剪映)
drafts through 50+ commands with `--json` output — no GUI automation required.
Built on top of `pyCapCut`, it manages an event-sourced session and offers both one-shot
commands and an interactive REPL.

▶ **[Demo video — "AI controls CapCut" (2m38s, Korean narration)](https://www.youtube.com/watch?v=pgx5QqAt8Is)**

<details>
<summary><b>Why a CLI instead of an MCP server</b></summary>

When agent tooling is exposed as an MCP server, the tool schema occupies context
permanently. A CLI is invoked only when needed and its output is plain text the agent
can parse directly. That is why every command here takes `--json`, and why agent-facing
commands such as `agent status` return *what to do next*, not just what happened.

There are external benchmarks reporting that CLI-shaped agent tooling is substantially
more token-efficient than MCP (ScaleKit 2026, Jannik Reinhard 2026). Note these compare
the **tool-exposure styles in general — they are not measurements of this project.**

</details>

> **Version 0.5.7** · See [CHANGELOG.md](CHANGELOG.md).

## Requirements

**Windows only.** This is not a portability oversight — the tool resolves fonts by
scanning four Windows locations (CapCut cache, CapCut SystemFont, user Fonts, Windows
Fonts), auto-detects the CapCut draft folder, and drives the CapCut GUI for rendering.
CI runs on a Windows runner for the same reason.

- Python 3.10+
- CapCut (Windows desktop) installed
- `ffmpeg` / `ffprobe` on `PATH` — optional, enables media duration auto-detection
  and headless rendering

## Installation

```bash
# 1) upstream library (pycapcut)
#
# The PyPI build of pycapcut 0.0.3 does NOT have TextSegment(shadow=...).
# Built-in text styles use shadow, so `text add --style ...` fails with the PyPI build.
# It exists upstream (commit b846b95, 2025-08-15) but there has been no release since.
#
# Also, upstream setup.py reads pypi_readme.md, which is not committed to git, so
# `pip install git+https://...` fails with FileNotFoundError. Clone and patch it.
# (reported upstream: GuanYixuan/pyCapCut#16)
git clone https://github.com/GuanYixuan/pyCapCut.git
cd pyCapCut
git checkout 00c223aa246f955d741b17b703e10270b22ec75e
cp README.md pypi_readme.md          # PowerShell: Copy-Item README.md pypi_readme.md
pip install .
cd ..

# 2) this CLI
pip install -e .
```

> If you do not need text styling, `pip install pycapcut` is enough — but
> `text add --style` will not work.

## Quick start

```bash
# check the environment
cli-anything-capcut diagnose

# new project
cli-anything-capcut project new --name my-mv --preset portrait

# tracks
cli-anything-capcut track add -p my-mv.session.json --type video --name V1
cli-anything-capcut track add -p my-mv.session.json --type audio --name A1
cli-anything-capcut track add -p my-mv.session.json --type text  --name title

# media
cli-anything-capcut image add -p my-mv.session.json -f intro.png --start 0s   --duration 3s --track V1
cli-anything-capcut image add -p my-mv.session.json -f main.png  --start auto --duration 5s --track V1
cli-anything-capcut audio add -p my-mv.session.json -f song.wav  --start 0s   --duration 8s --track A1

# text with full styling
cli-anything-capcut text add -p my-mv.session.json -t "Title" \
    --track title --start 0.5s --duration 3s \
    --font roboto --size 12 --bold \
    --color "1.0,1.0,1.0" \
    --border '{"alpha": 1.0, "color": [0,0,0], "width": 0.08}' \
    --shadow '{"alpha": 0.9, "color": [0,0,0], "distance": 5, "angle": 315}' \
    --clip-settings title-top \
    --patch-style

# effects / filters
cli-anything-capcut effect add        -p my-mv.session.json --name vignette --start 0s --duration 8s
cli-anything-capcut effect add-filter -p my-mv.session.json --name warm     --start 0s --duration 8s

# transitions / fades / animations
cli-anything-capcut video add-transition -p my-mv.session.json \
    --track V1 --segment-ref op_3 --name dissolve --duration 500ms
cli-anything-capcut video add-fade -p my-mv.session.json \
    --track V1 --segment-ref op_3 --fade-in 1s --fade-out 1s
cli-anything-capcut video add-animation -p my-mv.session.json \
    --track V1 --segment-ref op_3 --role intro --name zoom_in --duration 800ms

# keyframes (Ken Burns, etc.)
cli-anything-capcut keyframe add -p my-mv.session.json \
    --track V1 --segment-ref op_3 --property uniform_scale --time 0s --value 1.0
cli-anything-capcut keyframe add -p my-mv.session.json \
    --track V1 --segment-ref op_3 --property uniform_scale --time 5s --value 1.2

# analysis
cli-anything-capcut timeline       -p my-mv.session.json
cli-anything-capcut stats          -p my-mv.session.json
cli-anything-capcut gap-detect     -p my-mv.session.json --track V1
cli-anything-capcut overlap-detect -p my-mv.session.json

# save to a CapCut draft
cli-anything-capcut save -p my-mv.session.json
```

## High-level presets (one-shot)

```bash
# image folder -> slideshow
cli-anything-capcut preset slideshow --name ss --folder ./imgs \
    --duration 3s --transition dissolve --audio bgm.wav

# audio + SRT -> lyric video
cli-anything-capcut preset lyric-video --name mv \
    --audio song.wav --srt lyrics.srt --background cover.png

# prepend / append intro & outro to an existing session
cli-anything-capcut preset intro-outro -p session.json \
    --intro in.png --outro out.png --transition dissolve

# picture-in-picture overlay
cli-anything-capcut preset pip -p session.json -f overlay.mp4 \
    --corner top-right --scale 0.35
```

## Assets

```bash
cli-anything-capcut asset bulk-import -p session.json --folder ./media   # auto-classify & import
cli-anything-capcut asset relocate    -p session.json -o ./packaged      # pack referenced media
cli-anything-capcut asset transcode   -i src.mov -o out.mp4 --crf 20     # ffmpeg transcode
cli-anything-capcut asset cover-from-frame -p session.json -f video.mp4 --time 2s
```

## Session utilities

```bash
cli-anything-capcut session compact -p session.json            # dedupe ops + renumber ids
cli-anything-capcut session find-replace-media -p session.json \
    --pattern "D:/old" --replacement "D:/new"                   # bulk path rewrite
cli-anything-capcut session watch -p session.json              # watch & auto-save
cli-anything-capcut import-draft --from <draftFolder> -o out.session.json   # CapCut draft -> session
```

## Rendering

```bash
# ffmpeg only, without opening CapCut — use this
cli-anything-capcut render-headless -p session.json -o output.mp4

# drives the CapCut GUI (see the warning below)
cli-anything-capcut render -p session.json \
    --resolution 1080P --framerate 30 -o output.mp4 --save-first
```

> **`render` only works on the Chinese build (剪映专业版).**
> It delegates to `pycapcut`'s `JianyingController`, which selects the window with
> `control.Name != "剪映专业版"` and then looks for Chinese UI labels such as `导出`.
> The international CapCut names its window `CapCut`, so the match never succeeds —
> verified on CapCut 9.4.0 (reported upstream: GuanYixuan/pyCapCut#17).
> Use `render-headless`, which needs no GUI at all.

## Interactive REPL

```bash
cli-anything-capcut repl
```

Tab completion and history (`~/.capcut_cli/repl_history`).

## Recipes (batch automation)

A recipe is declarative JSON that builds a whole session at once:

```json
{
  "name": "music-video",
  "width": 1080, "height": 1920, "fps": 30,
  "operations": [
    {"op": "add_track", "args": {"type": "video", "name": "V1"}},
    {"op": "add_track", "args": {"type": "audio", "name": "A1"}},
    {"op": "add_image", "args": {"file": "scene1.png", "track": "V1",
                                  "start": "0s", "duration": "5s"}},
    {"op": "add_audio", "args": {"file": "song.wav", "track": "A1",
                                  "start": "0s", "duration": "30s"}}
  ]
}
```

```bash
cli-anything-capcut import-recipe   -p out.session.json -f recipe.json
cli-anything-capcut export-recipe   -p out.session.json -o backup.json
cli-anything-capcut validate-recipe -f recipe.json
```

## Aliases

CapCut / pyCapCut enums are Chinese (`暗角`, `叠化`, …). English aliases are provided.

```bash
cli-anything-capcut alias resolve --class VideoSceneEffectType --name vignette
# -> {"resolved": "暗角"}

cli-anything-capcut alias search --class FilterType -k warm
# -> [{"name": "暖黄", "alias": "warm"}, ...]

cli-anything-capcut alias classes
# -> ["AudioSceneEffectType", "FilterType", ..., "VideoSceneEffectType"]
```

## Agent-facing output

```bash
cli-anything-capcut --json agent status -p my-mv.session.json
# -> validation + gaps/overlaps + suggested next actions
```

Every command accepts `--json`. `agent status` is meant to be the loop an agent runs
between edits: it reports structural problems and what to do about them.

## Fixed upstream/legacy bugs

- **#1** `tim()` returned 0 for `"3000000"` → absorbed by `parse_time_value()`
- **#2/#3/#15** aliases drifted from real enums → exact mapping (`dissolve → 叠化`, …)
- **#4/#9/#14** tracks were not auto-created on replay → every op handler calls `_ensure_track()`
- **#5** hard ffprobe dependency → WAV falls back to the `wave` module
- **#6/#21** clip-settings presets → 8 built-ins (`subtitle-bottom`, `pip-top-right`, …)
- **#10/#22** SIGPIPE loss when piping → sessions never depend on stderr output
- **#17~#20** `text add --font/--border/--shadow/--color` were ignored → `--patch-style`
  or `text style-patch` patches `draft_content.json` after save
- missing `draft_meta_info.json` made drafts invisible in CapCut → `DraftFolder.create_draft`
  is always used

## Project structure

```
cli_anything/capcut/
├── capcut_cli.py            # Click entry point
├── commands/                # subcommand groups (project, track, media, text, style,
│                            #   effect, mask, keyframe, color, asset, preset, plan,
│                            #   preview, render, render_headless, import_draft, review,
│                            #   session_utils, alias, analysis, recipe, agent)
├── core/
│   ├── session.py           # event-sourced Session
│   ├── op_handlers.py       # op -> ScriptFile dispatch
│   ├── op_registry.py       # op classification (CREATION/MODIFIER/STRUCTURE/POSTPROCESS)
│   ├── alias_map.py         # EN->CN aliases, font resolution, fuzzy search
│   ├── style_registry.py    # built-in style definitions
│   ├── media_staging.py     # non-ASCII path staging
│   ├── auto_fix.py          # quarantine failing ops and re-replay
│   ├── postprocess.py       # patches draft_content.json after save
│   └── ...
├── utils/                   # draft folder detection, REPL skin
└── tests/                   # 24 files / 398 tests
```

`scripts/alias_audit.py` audits aliases against the installed pycapcut enums.
`scripts/scan_private.py` is the pre-publish privacy gate wired into CI.

## Claude Code skill (optional)

Copy `claude-skill/` into `~/.claude/skills/capcut-cli/` to drive this CLI from
Claude Code in natural language.

```bash
cp -r claude-skill ~/.claude/skills/capcut-cli
```

## License

MIT. `pyCapCut` (upstream) has its own license.
