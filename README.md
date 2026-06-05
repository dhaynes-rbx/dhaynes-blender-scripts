# dhaynes-blender-scripts

**DHaynes Roblox Scripts** — a single Blender extension that bundles a growing
collection of Roblox game-art tools. Install it once and every tool comes along
for the ride. Add a new tool by dropping one `.py` file in `tools/`; it's
discovered and registered automatically.

## Layout

```text
dhaynes_roblox_scripts/          # the extension (install this folder)
├── blender_manifest.toml        # extension metadata (Blender 4.2+)
├── __init__.py                  # auto-loader: registers everything in tools/
└── tools/
    ├── batch_collection_exporter.py
    └── facial_rigging_tools.py
```

## Tools

- **Batch Collection Exporter** — exports each top-level collection under the
  scene root as its own FBX (meshes + armatures), Roblox-style. Also exports the
  Outliner-active collection on its own. Sidebar: **View3D > Roblox**.
- **Facial Vertex Group & Bone Constraint Wizard** — step-through wizard for
  assigning `HK-*` facial vertex groups and generating `MCH-*` tracking bones
  with Damped Track constraints. Sidebar: **View3D > Eyelid Setup**.

## Install (Blender 4.2+)

1. Build a zip: from the repo root run `blender --command extension build`
   (run inside `dhaynes_roblox_scripts/`), **or** zip that folder manually.
2. In Blender: **Edit → Preferences → Get Extensions → Install from Disk…** and
   pick the zip.
3. Enable **DHaynes Roblox Scripts**.

## Development workflow

For fast iterate-and-test, link the extension folder into Blender's
`user_default` extensions repo instead of re-installing each time. The
`dev_link.ps1` helper auto-detects **every installed Blender version** (4.2,
5.0, future releases) and creates a junction in each — no hardcoded version
path, and no admin rights needed:

```powershell
# Link into all installed Blender versions
powershell -ExecutionPolicy Bypass -File dev_link.ps1

# ...or target a specific version
powershell -ExecutionPolicy Bypass -File dev_link.ps1 -Version 5.0

# Remove the links
powershell -ExecutionPolicy Bypass -File dev_link.ps1 -Remove
```

Re-run it after upgrading Blender to link the new version folder. Then:

1. **Preferences → Get Extensions → Refresh Local**, enable it once.
2. Edit any file under `tools/`.
3. Press **F3 → Reload Scripts** to load your changes (the auto-loader reloads
   each tool module on register).

## Adding a new tool

Create `tools/my_tool.py` exposing `register()` and `unregister()` (typically
registering/unregistering your operator and panel classes). No edits to
`__init__.py` are needed — it's picked up automatically on the next register.

## Requirements

Blender **4.2+** (extension/`blender_manifest.toml` format).
