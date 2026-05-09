# cua/ — Northstar on the drone dashboard

Standalone CUA orchestrator. Drives the public drone dashboard URL (`https://un5nmdhn7f29dw-8000.proxy.runpod.net/`) using the `tzafon.northstar-cua-fast` model in a Lightcone-hosted virtual desktop. **Does not modify drone_management/** in any way — it just opens the URL like a human would.

## Install (one-time)

```bash
cd /Users/mrbam/Github/GitHub/Northstar
pip install tzafon httpx Pillow
```

API key is read from `$LIGHTCONE_API_KEY`, `$TZAFON_API_KEY`, the legacy `$lightcone_API`, or `Northstar/.env` (in that order).

## Run

From the `Northstar/` directory:

```bash
# Pre-canned demos
python -m cua --demo takeoff-land
python -m cua --demo sf-tour
python -m cua --demo street-view

# Custom goal
python -m cua "click Arm, click Takeoff, wait until 20m altitude, click Land"

# Override the dashboard URL or step cap
python -m cua --demo sf-tour --dashboard-url https://example.proxy.runpod.net --max-steps 40
```

Annotated PNGs land in `Northstar/cua_runs/<timestamp>/step-NN-<action>.png`. The terminal prints each step and any text Northstar produces.

## How it works

```
[your terminal: python -m cua "<goal>"]
        |
        v
[runner.py] reuses Northstar/_cua.py utilities (DONE_TOOL, get_computer_calls, etc.)
        |
        v
client = Lightcone(); client.computer.create(kind="desktop")
        |
        v
loop until done (max ~30 steps):
  - client.responses.create(model="tzafon.northstar-cua-fast", input=[...])
  - extract computer calls (click / type / scroll / navigate)
  - annotate the screenshot (PIL: red circle on click, banner on type/key, etc.)
  - save annotated PNG locally
  - computer.batch(calls)   ← actually executes the actions on the cloud desktop
  - take next screenshot
```

The CUA's browser is in Lightcone's cloud — your Mac just orchestrates and saves PNGs. Nothing on your machine is exposed to the model.

## Files

| File | Purpose |
|---|---|
| `__main__.py` | CLI entry point |
| `runner.py` | The CUA loop + screenshot annotation |
| `tasks.py` | Three pre-canned demo task strings |
| `__init__.py` | Empty package marker |

## Adding new demo tasks

Edit `tasks.py`:

```python
ALL["my-demo"] = "Click Arm. Click Takeoff (20 m). ... call the done function."
```

Then `python -m cua --demo my-demo`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `error: no LIGHTCONE_API_KEY found` | Key missing | `export LIGHTCONE_API_KEY=...` or add to `Northstar/.env` |
| `from _cua import ...` fails | Running from wrong directory | Must run from `Northstar/`, not from `cua/` or anywhere else |
| `pip install tzafon` fails | Private index needed | See Lightcone docs for the correct install command |
| Northstar opens dashboard but never clicks | Buttons off-screen at the default 1280×720 | Run with a wider display (edit `display_width=` in `runner.py`) |
| Loop hits `max_steps` without `done` | Task too complex or model stuck | Either simplify the task or pass `--max-steps 50` |
