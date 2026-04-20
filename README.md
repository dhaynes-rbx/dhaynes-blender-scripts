# dhaynes-blender-scripts

Blender add-ons and utilities for game-art workflows.

## Roblox Batch Collection Exporter

Add-on that exports each **top-level collection** under the scene root as its own **FBX** file, aimed at a Roblox-style pipeline (meshes and armatures per collection).

### Install

1. In Blender: **Edit → Preferences → Add-ons → Install…**
2. Choose `roblox_batch_collection_exporter.py`.
3. Enable **Import-Export: Roblox Batch Collection Exporter**.

### Use

Open the **Sidebar** in the 3D View (**N**), **Roblox** tab, pick an output folder, and run **Export Collections to FBX**.

Collections that are hidden in the viewport or excluded in the view layer are skipped.

### Requirements

Blender **3.0+** (see `bl_info` in the script for the declared minimum).
