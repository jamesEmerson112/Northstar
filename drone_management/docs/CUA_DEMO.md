# CUA Demo (Northstar)

Run a CUA agent that drives the drone dashboard like a human would. Annotated screenshots stream live to a "Northstar (CUA)" panel inside the dashboard.

## One-time setup (your Mac)

```bash
cd /Users/mrbam/Github/GitHub/Northstar/drone_management
source .venv/bin/activate
pip install -e ".[cua,dev]"
```

The Lightcone API key is read from (in order):
1. Environment variable `LIGHTCONE_API_KEY`
2. Environment variable `lightcone_API`
3. `Northstar/.env` (anywhere up the tree) with either name

You don't need to pass the key on the command line.

## Run a demo

The dashboard must already be running and reachable at the public URL (`https://un5nmdhn7f29dw-8000.proxy.runpod.net/`).

### Pre-canned tasks

```bash
python -m cua --demo takeoff-land
python -m cua --demo sf-tour
python -m cua --demo street-view
```

### Custom task

```bash
python -m cua "Open the drone dashboard, click Arm, then click Takeoff (20 m), wait until altitude is 20 meters, click Land. Call done when finished."
```

### Options

```
python -m cua [--demo NAME | GOAL] \
              [--dashboard-url URL] \
              [--max-steps N]      \
              [--output-dir DIR]
```

Annotated PNGs land in `cua_runs/<timestamp>/step-NN-<action>.png`.

## What you'll see

Open `https://un5nmdhn7f29dw-8000.proxy.runpod.net/` in any browser. The right panel now has a **Northstar (CUA)** section showing:

- **Status** — `IDLE`, `START`, `STEP`, `DONE`, or `ERROR`
- **Task** — the goal you handed Northstar
- **Action** — the most recent action taken (e.g. `[3] click @ (1340, 280) Arm`)
- **Thumbnails** — the last 3 annotated screenshots (newest is biggest, blue border)

Every CUA step pushes a fresh screenshot through the same WebSocket as drone telemetry.

## Demo rehearsal checklist

- [ ] All three `--demo` tasks complete cleanly end-to-end at least once.
- [ ] The Northstar panel updates within ~1 s of each action.
- [ ] `cua_runs/<timestamp>/` has a clean PNG per step.
- [ ] You have a backup MP4 of one good run (record with QuickTime / OBS) saved somewhere offline.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `LIGHTCONE_API_KEY not set` | Key isn't in env or `.env` | `export LIGHTCONE_API_KEY=...` or add to `Northstar/.env` |
| `pip install tzafon` fails | Private index needed | Check Lightcone docs for the correct install command |
| Northstar opens dashboard but never clicks | Buttons may be off-screen at smaller display dimensions | Try `--display-width 1440 --display-height 900` in runner.py if needed |
| Panel shows steps but no thumbnails | Screenshot encoding too large | The runner already resizes to 640px; if still slow, lower in `annotate.py` |
| Status pill stays on `start` forever | Lightcone session is hung | Ctrl-C the CLI, retry. Check Lightcone status |
| Dashboard doesn't show any CUA panel updates | Backend not redeployed | Push, `git pull` on pod, `bash scripts/restart.sh` |

## Architecture quick reference

```
[Mac CLI: python -m cua "<goal>"]
        |
        v
[runner.py — Lightcone client + tzafon.northstar-cua-fast]
        |--- get screenshot → call model → execute action
        |--- annotate.py draws on screenshot (PIL)
        |--- streamer.py POSTs to /api/cua/step on the public dashboard
        v
[FastAPI on pod] /api/cua/step → bus.broadcast({"type":"cua_step", ...})
        |
        v
[browser dashboard] ws/telemetry → applyCuaStep(msg) → Northstar panel updates
```

The CUA itself runs in a Lightcone-hosted virtual desktop. It opens the public dashboard URL, sees the same UI you do, and clicks/types its way through the goal. Nothing on your Mac is exposed to the model.
