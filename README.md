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
    ├── bone_mirror_subtargets.py
    ├── export_deform_rig.py
    ├── eye_skin_weighting_tool.py
    └── facial_rigging_tools.py
```

## Tools

All panels live under a single **View3D > Roblox** sidebar tab.

- **Batch Collection Exporter** — exports each top-level collection under the
  scene root as its own FBX (meshes + armatures), Roblox-style. Also exports the
  Outliner-active collection on its own.
- **Ribbon Vertex Group Setup** ("Ribbon Vertex Group Setup" panel) —
  step-through wizard for assigning `HK-*` ribbon vertex groups and generating
  constraint bones plus `DEF-*` deform bones. A **Feature** dropdown switches
  between two ribbon layouts:
  - **Eyelid** — pick a **Side** (`.L`/`.R`), then step through: inner corner,
    outer corner, upper loop, lower loop. The upper/lower loops are numbered
    `1..n` left-to-right by world X, producing `HK-Eyelid-*.{side}` groups.
  - **Lip** — no manual side; side is auto-detected per vertex by world X
    (`+X = .L`, `−X = .R`). Steps: left corner (`HK-Lip-Corner.L`), right corner
    (`HK-Lip-Corner.R`), upper loop, lower loop. For each loop the single center
    vertex (nearest `X=0`) becomes the side-less `HK-Lip-Upper` / `HK-Lip-Lower`,
    and the remaining verts are split by side and numbered from the corner inward
    (lower number = closer to the corner), e.g. `HK-Lip-Upper1.R`,
    `HK-Lip-Upper2.R`, … / `HK-Lip-Upper1.L`, … Corner verts already assigned are
    excluded from the loop steps automatically.

  **Generate Helper Empties** creates one `HLP-*` Empty per `HK-*` hook vertex
  (name mirrors the group, `HK-` → `HLP-`), vertex-parents it to that vertex on
  the ribbon, snaps it onto the vertex in world space, and applies all transforms
  to deltas. It's idempotent — re-running reuses existing empties by name.

  **Generate Damped Track Bones / Generate Stretch Bones** (the button/label
  follows the feature) then builds the bones and a parented `DEF-*` deform bone at
  each vertex:
  - **Eyelid** — clones the chosen Source Template Bone for each `HK-*` group,
    adds a **Damped Track** constraint aimed at that group's mesh vertices,
    applies the pose as rest, and names the trackers `MCH-*`.
  - **Lip** — creates one `STR-*` bone per **helper empty** (running from the
    Source Template Bone to the empty) with a **Stretch To** constraint targeting
    that empty (no rest bake). Requires the helper empties from Step 2 to exist.
- **Skin Weighting Tool** ("Eye/Lip Skin Weighting" panel) — step-through wizard for
  weighting the character mesh loops to the generated `DEF-*` groups. A
  **Feature** dropdown selects **Eyelid** or **Lip**. Pick the **Object**,
  **Armature**, and **Source Template Bone**, then step through selecting each
  loop:
  - **Eyelid** — Source Eye Loop (`HLP-EyeLoop.L`), inner/outer corners, then one
    step per `DEF-Eyelid-Upper#.L` / `DEF-Eyelid-Lower#.L` group (inner→outer).
  - **Lip** — Source Lip Loop (`HLP-LipLoop`), left/right corners, then for each
    of upper/lower: the center group (if present) followed by the `.R` then `.L`
    numbered loops (corner→center).

  The upper/lower step counts are derived automatically from the existing `DEF-*`
  groups on the mesh. Each step sets weight `1.0` on the selection via
  weight-paint *Set Weight* with Auto-Normalize on; every group is locked except
  the Source Template mask and the `DEF-<feature>` groups, so assigning a loop
  subtracts from the mask.
- **Bone Mirror Subtargets** ("Bone Mirror Subtargets" panel) — in Pose Mode,
  flips the trailing `.L`/`.R` on every constraint subtarget of the selected pose
  bones (e.g. retarget mirrored bones from `*.L` groups to `*.R`).
- **Export Deform Rig** ("Export Deform Rig" panel) — builds a flat, deform-only
  armature for clean Roblox export. Pick the **Source Armature** (control rig), a
  **Root Bone** name, and an optional **Export Name**, then Build. It creates a new
  collection under the Scene Collection containing: an armature with one root and
  every `use_deform` bone copied in flat (same names, same rest transforms) with a
  **Copy Transforms** constraint back to the source bone; plus a linked duplicate
  of each skinned mesh, retargeted to the new armature. Animate on the control
  rig, then bake the export armature (Visual Keying, Clear Constraints) and export
  just that collection. Non-destructive and re-runnable — it regenerates the
  export collection each time.

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
