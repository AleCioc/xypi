# XYPI map agents v13

v13 keeps the v11/v12 live language and musical engine, but changes the browser presentation to a Hydra/Atom-style live-coding surface.

## Main visual change

The map is now the editor background itself.

- The map canvas is fixed to the viewport.
- Syntax-highlighted `live.py` is drawn directly over the map.
- There is no floating editor panel, border, drag handle, or resizable widget.
- Scrolling moves only the code. The map remains fixed underneath.
- `Cmd+Enter` / `Ctrl+Enter` applies the current browser code.
- `Reload` reloads `live.py` from disk.

A light darkening veil and text shadow keep Python syntax readable while preserving the map underneath.

## Map-loading fix

v12 repeatedly requested `/runtime/map.json` while waiting for the map to become ready. Those `200` terminal lines were successful HTTP requests rather than errors, but the polling was noisy and unnecessary.

v13 does this instead:

1. Poll only the small `/runtime/state.json` file while the map is loading.
2. When the engine reports `map ready`, request `/runtime/map.json` once.
3. Keep the map graph in browser memory afterwards.

The HTTP server also suppresses routine access-log lines for both `state.json` and `map.json`.

## Run

```bash
python run.py --map trento --zoom 16
```

Then open:

```text
http://127.0.0.1:8001/interface.html
```

Other examples:

```bash
python run_v13.py --map taranto --zoom 16
python run_v13.py --map antwerp --zoom 15
```

## Live syntax

```python
l1 = agent("area", [(0.15,0.15), (0.75,0.15), (0.82,0.72), (0.22,0.82)], speed=5, behaviour=random_walk, sound="bass")
l2 = agent("line", [(0.08,0.75), (0.45,0.45), (0.90,0.68)], speed=7, behaviour=straightish, sound="hh")
l3 = agent("points", [(0.22,0.25), (0.68,0.76), (0.84,0.30)], speed=6, sound="harmonic")
```

Point agents still default to `point_attract`; line agents to `straightish`; area agents to `random_walk`.
