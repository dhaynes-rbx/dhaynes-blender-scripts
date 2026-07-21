import math

import bpy
import bmesh
from mathutils import Vector


# --- FEATURE CONFIGURATION ---
# Each feature defines its ordered wizard steps. A step's "mode" controls how the
# selected vertices become HK-* vertex groups:
#   single       - all selected verts -> one group, using the manual Side selector
#   sequential   - one group per vert, numbered 1..n left-to-right (world X), manual Side
#   single_side  - all selected verts -> one group with a fixed side baked into the step
#   midline      - lip loop: the center vert (min |x|) is unnumbered/side-less; the rest
#                  are split by X sign (+X=.L, -X=.R) and numbered from the corner inward
#                  (lower number = closer to the corner)
FEATURES = {
    'Eyelid': {
        'uses_manual_side': True,
        'steps': [
            {'label': "Select Inner Corner vertex", 'button': "Assign Inner Corner", 'group': "Corner-Inner", 'mode': 'single'},
            {'label': "Select Outer Corner vertex", 'button': "Assign Outer Corner", 'group': "Corner-Outer", 'mode': 'single'},
            {'label': "Upper loop", 'button': "Assign Upper Loop", 'group': "Upper", 'mode': 'sequential'},
            {'label': "Lower loop", 'button': "Assign Lower Loop", 'group': "Lower", 'mode': 'sequential'},
        ],
    },
    'Lip': {
        'uses_manual_side': False,
        'steps': [
            {'label': "Select Left Corner vertex", 'button': "Assign Left Corner", 'group': "Corner", 'mode': 'single_side', 'side': 'L'},
            {'label': "Select Right Corner vertex", 'button': "Assign Right Corner", 'group': "Corner", 'mode': 'single_side', 'side': 'R'},
            {'label': "Upper loop (corner\u2192center, both sides)", 'button': "Assign Upper Loop", 'group': "Upper", 'mode': 'midline'},
            {'label': "Lower loop (corner\u2192center, both sides)", 'button': "Assign Lower Loop", 'group': "Lower", 'mode': 'midline'},
        ],
    },
}


def get_feature_config(feature):
    return FEATURES.get(feature, FEATURES['Eyelid'])


def get_feature_steps(feature):
    return get_feature_config(feature)['steps']


def collect_helper_targets(mesh_obj, feature, side):
    """Return ``[(hlp_name, vert_index, world_co), ...]`` for every vertex assigned
    to an ``HK-<feature>`` group (respecting the side filter for side-based
    features). Names mirror the DEF convention: ``HK-`` becomes ``HLP-``, and any
    group holding more than one vertex gets a ``.N`` index inserted before the
    side suffix."""
    uses_side = get_feature_config(feature)['uses_manual_side']
    hk_prefix = f"HK-{feature}"
    mesh_world = mesh_obj.matrix_world

    def matches(name):
        if not name.startswith(hk_prefix):
            return False
        return name.endswith(f".{side}") if uses_side else True

    targets = []
    seen = set()
    for vg in mesh_obj.vertex_groups:
        if not matches(vg.name):
            continue
        members = [v for v in mesh_obj.data.vertices
                   if any(g.group == vg.index for g in v.groups)]
        multi = len(members) > 1
        for vi, v in enumerate(members):
            if v.index in seen:
                continue
            seen.add(v.index)

            hlp_base = vg.name.replace("HK-", "HLP-")
            if multi and '.' in hlp_base:
                name_part, ext = hlp_base.rsplit('.', 1)
                hlp_name = f"{name_part}.{vi + 1}.{ext}"
            elif multi:
                hlp_name = f"{hlp_base}.{vi + 1}"
            else:
                hlp_name = hlp_base

            targets.append((hlp_name, v.index, mesh_world @ v.co))
    return targets


def get_armature_bones(self, context):
    scene = context.scene
    arm_obj = scene.facial_wizard_armature
    if arm_obj and arm_obj.type == 'ARMATURE':
        return [(b.name, b.name, f"Use {b.name} as template") for b in arm_obj.data.bones]
    return [("NONE", "No Armature Selected", "Select an armature object first")]


class MESH_OT_facial_wizard(bpy.types.Operator):
    bl_idname = "mesh.facial_wizard"
    bl_label = "Facial Group & Bone Wizard"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        obj = context.object

        feature = scene.facial_wizard_feature
        steps = get_feature_steps(feature)
        current_step = min(scene.facial_wizard_step, len(steps))
        scene.facial_wizard_step = current_step

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a Mesh.")
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "You must be in Edit Mode on the Mesh.")
            return {'CANCELLED'}

        scene.facial_wizard_mesh = obj

        bm = bmesh.from_edit_mesh(obj.data)
        matrix_world = obj.matrix_world.copy()
        selected_data = []
        for v in bm.verts:
            if v.select:
                world_co = matrix_world @ v.co
                selected_data.append({'index': v.index, 'x_world': world_co.x})

        if not selected_data:
            self.report({'WARNING'}, f"Step {current_step} Failed: No vertices selected!")
            return {'CANCELLED'}

        step_data = steps[current_step - 1]
        side = scene.facial_wizard_side

        bpy.ops.object.mode_set(mode='OBJECT')

        self.assign_step(obj, selected_data, feature, side, step_data)

        if current_step < len(steps):
            scene.facial_wizard_step = current_step + 1
            self.report({'INFO'}, f"Assigned '{step_data['group']}'. Next: {steps[current_step]['label']}.")
            bpy.ops.object.mode_set(mode='EDIT')
        else:
            scene.facial_wizard_step = 1
            self.report({'INFO'}, "Vertex Groups Complete! Targets locked in.")
            bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}

    def assign_step(self, obj, vert_data, feature, manual_side, step_data):
        mode = step_data['mode']
        base = f"HK-{feature}-{step_data['group']}"

        if mode == 'single':
            self._assign_group(obj, [v['index'] for v in vert_data], f"{base}.{manual_side}")

        elif mode == 'single_side':
            self._assign_group(obj, [v['index'] for v in vert_data], f"{base}.{step_data['side']}")

        elif mode == 'sequential':
            sorted_data = sorted(vert_data, key=lambda v: v['x_world'])
            for i, v in enumerate(sorted_data):
                self._assign_group(obj, [v['index']], f"{base}{i + 1}.{manual_side}")

        elif mode == 'midline':
            self._assign_midline(obj, vert_data, feature, base)

    def _assign_group(self, obj, indices, group_name):
        vg = obj.vertex_groups.get(group_name) or obj.vertex_groups.new(name=group_name)
        vg.add(indices, 1.0, 'REPLACE')

    def _assign_midline(self, obj, vert_data, feature, base):
        # Exclude any verts already assigned to the corner groups, so the loop
        # selection is robust whether or not it includes the corners.
        corner_indices = set()
        for suffix in ('L', 'R'):
            vg = obj.vertex_groups.get(f"HK-{feature}-Corner.{suffix}")
            if not vg:
                continue
            for v in obj.data.vertices:
                if any(g.group == vg.index for g in v.groups):
                    corner_indices.add(v.index)

        loop = [v for v in vert_data if v['index'] not in corner_indices]
        if not loop:
            return

        # Center vertex = smallest |x|; unnumbered and side-less.
        center = min(loop, key=lambda v: abs(v['x_world']))
        self._assign_group(obj, [center['index']], base)

        left = [v for v in loop if v['index'] != center['index'] and v['x_world'] > 0]
        right = [v for v in loop if v['index'] != center['index'] and v['x_world'] < 0]

        # Lower number = closer to the corner => sort by |x| descending.
        for side, verts in (('L', left), ('R', right)):
            verts_sorted = sorted(verts, key=lambda v: abs(v['x_world']), reverse=True)
            for i, v in enumerate(verts_sorted):
                self._assign_group(obj, [v['index']], f"{base}{i + 1}.{side}")


class MESH_OT_reset_facial_wizard(bpy.types.Operator):
    """Reset the wizard back to Step 1"""
    bl_idname = "mesh.reset_facial_wizard"
    bl_label = "Reset Wizard"

    def execute(self, context):
        context.scene.facial_wizard_step = 1
        self.report({'INFO'}, "Wizard reset to the beginning (Step 1).")
        return {'FINISHED'}


class MESH_OT_generate_damped_track_bones(bpy.types.Operator):
    """Generate constraint bones and DEF deformation bones from the ribbon vertex
    groups. Eyelids use MCH- Damped Track bones aimed at the mesh vertex groups;
    Lips use STR- Stretch To bones targeting the helper empties"""
    bl_idname = "mesh.generate_damped_track_bones"
    bl_label = "Generate Damped Track Bones"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        mesh_obj = scene.facial_wizard_mesh
        arm_obj = scene.facial_wizard_armature
        parent_bone_name = scene.facial_wizard_source_bone

        if not mesh_obj or mesh_obj.type != 'MESH':
            self.report({'ERROR'}, "Please specify a valid Target Mesh.")
            return {'CANCELLED'}
        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please specify a valid Target Armature.")
            return {'CANCELLED'}
        if parent_bone_name == "NONE" or not parent_bone_name:
            self.report({'ERROR'}, "Please choose a valid Source Bone template.")
            return {'CANCELLED'}

        feature = scene.facial_wizard_feature
        side = scene.facial_wizard_side
        uses_side = get_feature_config(feature)['uses_manual_side']
        hk_prefix = f"HK-{feature}"

        def is_target(name):
            if not name.startswith(hk_prefix):
                return False
            return name.endswith(f".{side}") if uses_side else True

        target_group_names = [vg.name for vg in mesh_obj.vertex_groups if is_target(vg.name)]

        # Each hook group must hold exactly one vertex. If any holds more, abort
        # without touching the scene so the user can fix the ribbon groups first.
        multi = self._multi_vertex_groups(mesh_obj, target_group_names)
        if multi:
            self.report({'WARNING'},
                        "Aborted: expected exactly one vertex per group, but these "
                        f"have more than one: {', '.join(sorted(multi))}.")
            return {'CANCELLED'}

        context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode='EDIT')

        template_bone = arm_obj.data.edit_bones.get(parent_bone_name)
        if not template_bone:
            self.report({'ERROR'}, f"Template bone '{parent_bone_name}' not found inside rig.")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

        if feature == 'Lip':
            return self._generate_lip_bones(context, mesh_obj, arm_obj, parent_bone_name)
        return self._generate_eyelid_bones(context, mesh_obj, arm_obj, parent_bone_name)

    def _multi_vertex_groups(self, mesh_obj, group_names):
        """Return the subset of ``group_names`` whose vertex group contains more
        than one vertex."""
        name_set = set(group_names)
        idx_to_name = {vg.index: vg.name for vg in mesh_obj.vertex_groups if vg.name in name_set}
        wanted_idx = set(idx_to_name)

        counts = {}
        for v in mesh_obj.data.vertices:
            for g in v.groups:
                if g.group in wanted_idx:
                    counts[g.group] = counts.get(g.group, 0) + 1

        return [idx_to_name[i] for i in wanted_idx if counts.get(i, 0) > 1]

    def _generate_eyelid_bones(self, context, mesh_obj, arm_obj, parent_bone_name):
        """Eyelid rig: MCH- bones cloned from the template bone, each Damped Track
        aimed at its HK- vertex group; pose applied as rest; DEF- bones per vertex
        parented to their MCH-."""
        scene = context.scene
        feature = scene.facial_wizard_feature
        side = scene.facial_wizard_side
        uses_side = get_feature_config(feature)['uses_manual_side']
        hk_prefix = f"HK-{feature}"

        bpy.ops.object.mode_set(mode='EDIT')
        arm_data = arm_obj.data
        template_bone = arm_data.edit_bones.get(parent_bone_name)

        def matches(name, prefix):
            if not name.startswith(prefix):
                return False
            # Side-based features (Eyelid) are filtered to the active side; features
            # with per-vertex sides (Lip) match every side plus the side-less center.
            return name.endswith(f".{side}") if uses_side else True

        stale_bones = [
            eb for eb in arm_data.edit_bones
            if matches(eb.name, f"MCH-{feature}") or matches(eb.name, f"DEF-{feature}")
        ]
        for eb in stale_bones:
            arm_data.edit_bones.remove(eb)

        parent_matrix = template_bone.matrix.copy()
        parent_head = template_bone.head.copy()
        parent_tail = template_bone.tail.copy()
        parent_roll = template_bone.roll

        target_groups = [vg.name for vg in mesh_obj.vertex_groups if matches(vg.name, hk_prefix)]

        if not target_groups:
            scope = f"'{hk_prefix}*.{side}'" if uses_side else f"'{hk_prefix}*'"
            self.report({'WARNING'}, f"No existing {scope} groups discovered on '{mesh_obj.name}'.")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

        created_bone_names = []

        for vg_name in target_groups:
            mch_name = vg_name.replace("HK-", "MCH-")
            eb = arm_data.edit_bones.get(mch_name) or arm_data.edit_bones.new(name=mch_name)
            eb.head = parent_head
            eb.tail = parent_tail
            eb.matrix = parent_matrix
            eb.roll = parent_roll
            eb.parent = template_bone
            created_bone_names.append((mch_name, vg_name))

        # --- Pose Mode: Damped Track, evaluate, apply rest pose ---
        bpy.ops.object.mode_set(mode='POSE')

        for mch_name, vg_name in created_bone_names:
            pb = arm_obj.pose.bones.get(mch_name)
            if pb:
                for const in reversed(pb.constraints):
                    pb.constraints.remove(const)

                dt_constraint = pb.constraints.new(type='DAMPED_TRACK')
                dt_constraint.target = mesh_obj
                dt_constraint.subtarget = vg_name
                dt_constraint.track_axis = 'TRACK_Y'

            bone_data = arm_obj.data.bones.get(mch_name)
            if bone_data:
                bone_data.display_type = 'STICK'

        context.view_layer.update()

        bpy.ops.pose.select_all(action='DESELECT')
        for mch_name, _ in created_bone_names:
            pb = arm_obj.pose.bones.get(mch_name)
            if pb:
                pb.select = True
        bpy.ops.pose.armature_apply(selected=True)

        # --- Back to Edit Mode: create DEF bones parented to MCH ---
        bpy.ops.object.mode_set(mode='EDIT')
        arm_data = arm_obj.data
        template_bone = arm_data.edit_bones.get(parent_bone_name)

        mesh_world = mesh_obj.matrix_world
        arm_world_inv = arm_obj.matrix_world.inverted()
        seen_verts = set()
        def_count = 0

        for vg_name in target_groups:
            vg = mesh_obj.vertex_groups.get(vg_name)
            if not vg:
                continue
            vg_index = vg.index
            mch_name = vg_name.replace("HK-", "MCH-")
            mch_bone = arm_data.edit_bones.get(mch_name)

            member_verts = []
            for v in mesh_obj.data.vertices:
                for g in v.groups:
                    if g.group == vg_index:
                        member_verts.append(v)
                        break

            for vi, v in enumerate(member_verts):
                if v.index in seen_verts:
                    continue
                seen_verts.add(v.index)

                if len(member_verts) > 1:
                    name_part, ext = vg_name.replace("HK-", "DEF-").rsplit('.', 1)
                    def_name = f"{name_part}.{vi + 1}.{ext}"
                else:
                    def_name = vg_name.replace("HK-", "DEF-")

                eb = arm_data.edit_bones.get(def_name) or arm_data.edit_bones.new(name=def_name)
                local_head = arm_world_inv @ (mesh_world @ v.co)
                eb.head = local_head
                eb.tail = local_head + Vector((0, 0, 0.01))
                eb.roll = math.radians(90)
                eb.use_deform = True
                eb.bbone_x = eb.bbone_x * 0.08
                eb.bbone_z = eb.bbone_z * 0.08
                eb.parent = mch_bone if mch_bone else template_bone
                def_count += 1

        bpy.ops.object.mode_set(mode='OBJECT')

        self.report({'INFO'}, f"Created {len(created_bone_names)} MCH bones and {def_count} DEF bones.")
        return {'FINISHED'}

    def _generate_lip_bones(self, context, mesh_obj, arm_obj, parent_bone_name):
        """Lip rig: one STR- bone per helper empty, running from the template bone
        to the empty with a Stretch To constraint targeting that empty; DEF- bones
        per vertex parented to their STR-. The pose is NOT baked as rest."""
        scene = context.scene
        feature = scene.facial_wizard_feature
        side = scene.facial_wizard_side

        targets = collect_helper_targets(mesh_obj, feature, side)
        if not targets:
            self.report({'WARNING'}, f"No 'HK-{feature}*' groups discovered on '{mesh_obj.name}'.")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

        resolved = []
        missing = []
        for hlp_name, _vert_index, world_co in targets:
            empty = bpy.data.objects.get(hlp_name)
            if empty is None or empty.type != 'EMPTY':
                missing.append(hlp_name)
                continue
            resolved.append((hlp_name, world_co, empty.name))

        if not resolved:
            self.report({'ERROR'}, "No helper empties found. Run 'Generate Helper Empties' (Step 2) first.")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='EDIT')
        arm_data = arm_obj.data
        template_bone = arm_data.edit_bones.get(parent_bone_name)

        stale_bones = [
            eb for eb in arm_data.edit_bones
            if eb.name.startswith(f"STR-{feature}") or eb.name.startswith(f"DEF-{feature}")
        ]
        for eb in stale_bones:
            arm_data.edit_bones.remove(eb)

        template_head = template_bone.head.copy()
        template_roll = template_bone.roll
        arm_world_inv = arm_obj.matrix_world.inverted()

        created = []
        for hlp_name, world_co, empty_name in resolved:
            str_name = hlp_name.replace("HLP-", "STR-")
            eb = arm_data.edit_bones.get(str_name) or arm_data.edit_bones.new(name=str_name)
            eb.head = template_head
            eb.tail = arm_world_inv @ world_co
            eb.roll = template_roll
            eb.use_deform = False
            eb.parent = template_bone
            created.append((str_name, empty_name))

        # --- Pose Mode: Stretch To each helper empty (no rest bake) ---
        bpy.ops.object.mode_set(mode='POSE')

        for str_name, empty_name in created:
            pb = arm_obj.pose.bones.get(str_name)
            if pb:
                for const in reversed(pb.constraints):
                    pb.constraints.remove(const)

                st_constraint = pb.constraints.new(type='STRETCH_TO')
                st_constraint.target = bpy.data.objects.get(empty_name)

            bone_data = arm_obj.data.bones.get(str_name)
            if bone_data:
                bone_data.display_type = 'STICK'

        context.view_layer.update()

        # --- Back to Edit Mode: DEF bones per vertex parented to STR ---
        bpy.ops.object.mode_set(mode='EDIT')
        arm_data = arm_obj.data
        template_bone = arm_data.edit_bones.get(parent_bone_name)
        arm_world_inv = arm_obj.matrix_world.inverted()
        def_count = 0

        for hlp_name, world_co, empty_name in resolved:
            str_bone = arm_data.edit_bones.get(hlp_name.replace("HLP-", "STR-"))
            def_name = hlp_name.replace("HLP-", "DEF-")

            eb = arm_data.edit_bones.get(def_name) or arm_data.edit_bones.new(name=def_name)
            local_head = arm_world_inv @ world_co
            eb.head = local_head
            eb.tail = local_head + Vector((0, 0, 0.01))
            eb.roll = math.radians(90)
            eb.use_deform = True
            eb.bbone_x = eb.bbone_x * 0.08
            eb.bbone_z = eb.bbone_z * 0.08
            eb.parent = str_bone if str_bone else template_bone
            def_count += 1

        bpy.ops.object.mode_set(mode='OBJECT')

        msg = f"Created {len(created)} STR bones and {def_count} DEF bones."
        if missing:
            msg += f" Skipped {len(missing)} vertex(es) with no helper empty."
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class MESH_OT_generate_helper_empties(bpy.types.Operator):
    """Create an HLP-* Empty for each HK-* hook vertex on the ribbon: vertex-parent
    it to that vertex, snap it onto the vertex in world space, then apply all
    transforms to deltas. Re-running reuses existing empties of the same name"""
    bl_idname = "mesh.generate_helper_empties"
    bl_label = "Generate Helper Empties"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        mesh_obj = scene.facial_wizard_mesh
        feature = scene.facial_wizard_feature
        side = scene.facial_wizard_side

        if not mesh_obj or mesh_obj.type != 'MESH':
            self.report({'ERROR'}, "Please specify a valid Target Mesh.")
            return {'CANCELLED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        targets = collect_helper_targets(mesh_obj, feature, side)
        if not targets:
            uses_side = get_feature_config(feature)['uses_manual_side']
            scope = f"'HK-{feature}*.{side}'" if uses_side else f"'HK-{feature}*'"
            self.report({'WARNING'}, f"No {scope} groups found on '{mesh_obj.name}'.")
            return {'CANCELLED'}

        collections = list(mesh_obj.users_collection) or [scene.collection]
        created = []

        for hlp_name, vert_index, world_co in targets:
            empty = bpy.data.objects.get(hlp_name)
            if empty is not None and empty.type != 'EMPTY':
                empty = None
            if empty is None:
                empty = bpy.data.objects.new(hlp_name, None)

            for coll in collections:
                if empty.name not in coll.objects:
                    coll.objects.link(empty)

            # Reset to a clean, unparented state so re-runs are deterministic.
            empty.parent = None
            empty.matrix_parent_inverse.identity()
            empty.delta_location = (0.0, 0.0, 0.0)
            empty.delta_rotation_euler = (0.0, 0.0, 0.0)
            empty.delta_scale = (1.0, 1.0, 1.0)
            empty.rotation_euler = (0.0, 0.0, 0.0)
            empty.scale = (1.0, 1.0, 1.0)
            empty.location = world_co

            empty.empty_display_type = 'PLAIN_AXES'
            empty.empty_display_size = 0.01

            # Vertex-parent to the ribbon mesh (equivalent to Ctrl+P > Vertex).
            context.view_layer.update()
            bpy.ops.object.select_all(action='DESELECT')
            for v in mesh_obj.data.vertices:
                v.select = (v.index == vert_index)
            empty.select_set(True)
            mesh_obj.select_set(True)
            context.view_layer.objects.active = mesh_obj
            bpy.ops.object.parent_set(type='VERTEX', keep_transform=True)

            created.append(empty)

        # Apply all transforms to deltas across the whole batch.
        bpy.ops.object.select_all(action='DESELECT')
        for empty in created:
            empty.select_set(True)
        context.view_layer.objects.active = created[0]
        bpy.ops.object.transforms_to_deltas(mode='ALL')

        self.report({'INFO'}, f"Generated {len(created)} helper empties for {feature}.")
        return {'FINISHED'}


def _draw_info(layout, text, max_chars=40):
    """Draw a paragraph of description as wrapped, dimmed label lines."""
    col = layout.column(align=True)
    col.scale_y = 0.7
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and len(candidate) > max_chars:
            col.label(text=line)
            line = word
        else:
            line = candidate
    if line:
        col.label(text=line)


# --- UI PANEL ---
class VIEW3D_PT_facial_wizard_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Roblox'
    bl_label = 'Ribbon Vertex Group Setup'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene

        feature = scene.facial_wizard_feature
        steps = get_feature_steps(feature)
        current_step = min(scene.facial_wizard_step, len(steps))
        side = scene.facial_wizard_side
        uses_side = get_feature_config(feature)['uses_manual_side']

        # --- 1. WIZARD CONTROLS & STEPS BLOCK ---
        config_box = layout.box()
        config_box.label(text="Setup Ribbon Vertex Groups", icon='SETTINGS')
        _draw_info(config_box, "Step 1: Setup the helper ribbon mesh for your eye "
                               "or mouth with vertex groups and helper empties.")
        config_box.separator()

        config_box.prop(scene, "facial_wizard_feature", text="Feature")

        if uses_side:
            row_side = config_box.row(align=True)
            row_side.prop(scene, "facial_wizard_side", expand=True)

        config_box.separator()

        if not obj or context.mode != 'EDIT_MESH':
            config_box.label(text="Please enter Mesh Edit Mode", icon='EDITMODE_HLT')
            config_box.prop(scene, "facial_wizard_step")
        else:
            title = f"Steps ({feature}.{side}):" if uses_side else f"Steps ({feature}):"
            config_box.label(text=title, icon='CHECKBOX_DEHLT')

            for i, step in enumerate(steps):
                step_num = i + 1
                row = config_box.row()
                text = f"{step_num}. {step['label']}"
                if current_step == step_num:
                    row.label(text=f"\u25b6 {text}", icon='FORWARD')
                elif current_step > step_num:
                    row.label(text=text, icon='CHECKMARK')
                else:
                    row.label(text=text, icon='BLANK1')

            btn_text = steps[current_step - 1]['button']

            config_box.separator()
            col = config_box.column(align=True)
            col.scale_y = 1.2
            col.operator("mesh.facial_wizard", text=btn_text, icon='PLAY')

            config_box.prop(scene, "facial_wizard_step")

            config_box.separator()
            config_box.operator("mesh.reset_facial_wizard", text="Reset to Beginning", icon='FILE_REFRESH')

        # --- 2. HELPER EMPTIES BLOCK ---
        layout.separator()
        empties_box = layout.box()
        empties_box.label(text="Generate Helper Empties", icon='EMPTY_AXIS')
        _draw_info(empties_box, "Step 2: After setting up your ribbon mesh, create "
                                "and parent helper empties to each ribbon vertex.")
        empties_box.separator()
        target_mesh = scene.facial_wizard_mesh
        empties_box.label(text=f"Target: {target_mesh.name if target_mesh else '(run wizard or set below)'}")
        col = empties_box.column(align=True)
        col.scale_y = 1.2
        col.operator("mesh.generate_helper_empties", text="Generate Helper Empties", icon='PLAY')

        # --- 3. SOURCE/TARGET LINKING BLOCK ---
        layout.separator()
        link_box = layout.box()
        is_lip = feature == 'Lip'
        bones_title = "Generate Stretch Bones" if is_lip else "Generate Damped Track Bones"
        link_box.label(text=bones_title, icon='LINKED')
        if is_lip:
            _draw_info(link_box, "Step 3: Create STR- stretch-to bones targeting the "
                                 "helper empties, plus deformation bones, for your "
                                 "ribbon mesh.")
        else:
            _draw_info(link_box, "Step 3: Create damped track bones and deformation "
                                 "bones for your ribbon mesh.")
        link_box.separator()
        link_box.prop(scene, "facial_wizard_mesh")
        link_box.prop(scene, "facial_wizard_armature")

        if scene.facial_wizard_armature and scene.facial_wizard_armature.type == 'ARMATURE':
            link_box.prop(scene, "facial_wizard_source_bone", text="Source Template Bone")

        link_box.separator()
        col = link_box.column(align=True)
        col.scale_y = 1.2
        col.operator("mesh.generate_damped_track_bones", text=bones_title, icon='PLAY')


classes = (
    MESH_OT_facial_wizard,
    MESH_OT_reset_facial_wizard,
    MESH_OT_generate_damped_track_bones,
    MESH_OT_generate_helper_empties,
    VIEW3D_PT_facial_wizard_panel,
)


def register():
    bpy.types.Scene.facial_wizard_step = bpy.props.IntProperty(
        name="Jump to Step",
        description="Click the arrows to quickly shift active workflow steps",
        default=1,
        min=1,
        max=4,
    )
    bpy.types.Scene.facial_wizard_mesh = bpy.props.PointerProperty(
        name="Target Mesh",
        type=bpy.types.Object,
        description="The mesh containing the vertex groups",
    )
    bpy.types.Scene.facial_wizard_armature = bpy.props.PointerProperty(
        name="Target Armature",
        type=bpy.types.Object,
        description="The rig where new bones will be generated",
    )
    bpy.types.Scene.facial_wizard_source_bone = bpy.props.EnumProperty(
        name="Source Bone",
        description="The template bone to clone position, orientation, and parent from",
        items=get_armature_bones,
    )
    bpy.types.Scene.facial_wizard_feature = bpy.props.EnumProperty(
        items=[
            ('Eyelid', 'Eyelid', 'Eyelid ribbon: manual L/R side, inner/outer corners, single loop numbering'),
            ('Lip', 'Lip', 'Lip ribbon: auto side by world X, L/R corners, center vertex, per-side numbering'),
        ],
        name="Feature",
        default='Eyelid',
    )
    bpy.types.Scene.facial_wizard_side = bpy.props.EnumProperty(
        items=[
            ('L', 'Left (.L)', 'Generate Left-sided names'),
            ('R', 'Right (.R)', 'Generate Right-sided names'),
        ],
        name="Side",
        default='L',
    )

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.facial_wizard_step
    del bpy.types.Scene.facial_wizard_mesh
    del bpy.types.Scene.facial_wizard_armature
    del bpy.types.Scene.facial_wizard_source_bone
    del bpy.types.Scene.facial_wizard_feature
    del bpy.types.Scene.facial_wizard_side
