<p align="center">
  <img src="assets/title.png" alt="Sparklehoof" width="640"/>
</p>

# Sparklehoof

A Python desktop application for building image- and video-processing
workflows using a node-based visual editor.

> The repo is still named `image-inquest` while the rebrand to
> **Sparklehoof** lands piece by piece. `APP_NAME` in
> `src/constants.py` remains `Image-Inquest` for now so log paths and
> the user config dir (`~/.image-inquest/`) stay stable.

## Status

Early-stage development.  The application ships:

- A **page-based UI**: a start page, a node editor, and (coming soon,
  see [CHANGELOG](CHANGELOG.md)) a read-only Log page.
- A **node-based flow editor** with a dockable node palette, a canvas
  with a zoom-and-pan graphics view, a selectable viewer dock, and a
  status bar.
- **Dynamic node discovery** — built-in nodes under `src/nodes/` and
  user nodes under `~/.image-inquest/user_nodes/` are scanned at
  startup via the Python AST (no import needed to appear in the
  palette).
- **Flow persistence** — `*.flowjs` JSON files under `flow/`.
- **Live coding** — image-backed source nodes auto-re-run the flow
  300 ms after any parameter change so changes are reflected in the
  viewer in near real time.
- **Numba-JIT dither kernels** for interactive-speed error diffusion.

### Built-in nodes

Organised by palette section:

| Section | Nodes |
|---|---|
| Sources | File Source, Image Source, Video Source |
| Sinks | File Sink |
| Color Spaces | Grayscale, RGB Split, RGB Join |
| Transform | Scale, Shift |
| Processing | Adaptive Gaussian Threshold, Dither, Median, Normalize |

See [`CHANGELOG.md`](CHANGELOG.md) for a running list of notable changes.

## Requirements

- Python 3.10+
- [PySide6](https://doc.qt.io/qtforpython-6/)
- NumPy, OpenCV, numba
- FastAPI + uvicorn (for the local web mode)

```bash
pip install -r requirements.txt
```

## Running

### Desktop (PySide6)

```bash
python src/main.py
```

Optional arguments:

| Argument | Default | Description |
|---|---|---|
| `--no-splash` | — | Skip the startup splash screen |
| `--flow FILE` | — | Load a flow at startup and open it directly in the editor. Accepts a path to a `.flowjs` file or a bare flow name (looked up in `flow/`). |

### Local web mode

The same flow engine is also available as a browser-based editor that
runs entirely on your machine. It binds to `127.0.0.1` only and has no
network exposure.

```bash
python src/web/launch.py
```

Optional arguments:

| Argument | Default | Description |
|---|---|---|
| `--port N` | `8765` | Port to bind on `127.0.0.1` |
| `--no-browser` | — | Don't auto-open the browser (useful with remote port-forwarding) |

The browser opens at `http://127.0.0.1:8765/`. Flows are saved to the
same `flow/` directory as the desktop app, so files round-trip between
both modes.

**Current limitations of web mode** (good to know up front):

- No "live coding" auto-re-run yet — press **Run** after edits.
- Node canvas is a minimal vanilla-JS editor (not the polished Qt one): no
  zoom, no multi-select, no undo/redo.
- Previews are capped to 512 px on the long edge to keep responses small.
- No authentication — do not expose the port on your network.

## Usage

1. The app opens on the **start page**.
2. Enter a name and click **Create** to open the node editor with a
   new empty flow, or click **Open** to load an existing `*.flowjs`
   file.
3. In the editor, drag nodes from the **palette** onto the canvas.
4. Drag between node ports to create links; drag an existing link to
   remove it.
5. Click **Run** to execute the flow, or **Save** to persist it to
   `flow/`.  Reactive sources (still-image inputs) re-run the flow
   automatically as you edit parameters.

## Project layout

```
src/
  main.py               Entry point + CLI parsing + splash screen
  constants.py          Paths (FLOW_DIR, USER_CONFIG_DIR, …) and app metadata
  log.py                Rotating-file logging setup
  core/                 Non-UI: node base classes, ports, data, registry
  nodes/                Built-in nodes (sources, sinks, filters)
  ui/                   PySide6 views, pages, widgets
  web/                  FastAPI backend + vanilla-JS frontend (local-only)
tests/                  Pytest suite
flow/                   Sample + saved flows (*.flowjs)
assets/                 Splash image and bundled fonts
```

User-specific state (logs, recent flows, user-defined nodes) lives
under `~/.image-inquest/`.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## License

MIT — see [LICENSE](LICENSE).
