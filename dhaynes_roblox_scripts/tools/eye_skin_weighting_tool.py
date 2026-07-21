import re

import bpy


# --- FEATURE CONFIGURATION ---
# Each feature builds an ordered list of weighting steps. The first step always
# records the "source loop" (a plain HLP-* group). Every subsequent entry in
# "order" is either:
#   fixed    - a single named DEF-* group (corners, and the side-less lip center).
#              An 'optional' fixed step is only shown when that group already
#              exists on the mesh.
#   numbered - a family of DEF-*<n><suffix> groups, discovered on the mesh and
#              expanded in ascending order (inner->outer for eyelids,
#              corner->center for lips).
FEATURES = {
    'Eyelid': {
        'source_group': "HLP-EyeLoop.L",
        'source_select': "Set Source Eye Loop",
        'source_button': "Set Source Eye Loop (.L)",
        'order': [
            {'kind': 'fixed', 'group': "DEF-Eyelid-Corner-Inner.L", 'select': "Select Left Inner Corner Loop", 'button': "Assign Inner Corner (.L)", 'section': "Corners"},
            {'kind': 'fixed', 'group': "DEF-Eyelid-Corner-Outer.L", 'select': "Select Left Outer Corner Loop", 'button': "Assign Outer Corner (.L)", 'section': "Corners"},
            {'kind': 'numbered', 'prefix': "DEF-Eyelid-Upper", 'suffix': ".L", 'section': "Upper Loops", 'select_fmt': "Select Upper Loop {n} (inner\u2192outer)", 'button_fmt': "Assign Upper Loop {n} (.L)"},
            {'kind': 'numbered', 'prefix': "DEF-Eyelid-Lower", 'suffix': ".L", 'section': "Lower Loops", 'select_fmt': "Select Lower Loop {n} (inner\u2192outer)", 'button_fmt': "Assign Lower Loop {n} (.L)"},
        ],
    },
    'Lip': {
        'source_group': "HLP-LipLoop",
        'source_select': "Set Source Lip Loop",
        'source_button': "Set Source Lip Loop",
        'order': [
            {'kind': 'fixed', 'group': "DEF-Lip-Corner.L", 'select': "Select Left Corner Loop", 'button': "Assign Left Corner", 'section': "Corners"},
            {'kind': 'fixed', 'group': "DEF-Lip-Corner.R", 'select': "Select Right Corner Loop", 'button': "Assign Right Corner", 'section': "Corners"},
            {'kind': 'fixed', 'group': "DEF-Lip-Upper", 'select': "Select Upper Center Loop", 'button': "Assign Upper Center", 'section': "Upper Loops", 'optional': True},
            {'kind': 'numbered', 'prefix': "DEF-Lip-Upper", 'suffix': ".R", 'section': "Upper Loops", 'select_fmt': "Select Upper Loop {n} .R (corner\u2192center)", 'button_fmt': "Assign Upper Loop {n} (.R)"},
            {'kind': 'numbered', 'prefix': "DEF-Lip-Upper", 'suffix': ".L", 'section': "Upper Loops", 'select_fmt': "Select Upper Loop {n} .L (corner\u2192center)", 'button_fmt': "Assign Upper Loop {n} (.L)"},
            {'kind': 'fixed', 'group': "DEF-Lip-Lower", 'select': "Select Lower Center Loop", 'button': "Assign Lower Center", 'section': "Lower Loops", 'optional': True},
            {'kind': 'numbered', 'prefix': "DEF-Lip-Lower", 'suffix': ".R", 'section': "Lower Loops", 'select_fmt': "Select Lower Loop {n} .R (corner\u2192center)", 'button_fmt': "Assign Lower Loop {n} (.R)"},
            {'kind': 'numbered', 'prefix': "DEF-Lip-Lower", 'suffix': ".L", 'section': "Lower Loops", 'select_fmt': "Select Lower Loop {n} .L (corner\u2192center)", 'button_fmt': "Assign Lower Loop {n} (.L)"},
        ],
    },
}

# Generous upper bound for the "Jump to Step" field; real range is clamped to
# the dynamic step count at runtime.
_MAX_STEPS = 100


def _collect_numbered_groups(obj, prefix, suffix):
    """Return ``[(number, group_name), ...]`` for groups like ``<prefix><n><suffix>``,
    sorted ascending by number."""
    pattern = re.compile(r'^' + re.escape(prefix) + r'(\d+)' + re.escape(suffix) + r'$')
    found = []
    for vg in obj.vertex_groups:
        match = pattern.match(vg.name)
        if match:
            found.append((int(match.group(1)), vg.name))
    found.sort(key=lambda item: item[0])
    return found


def build_eye_skin_steps(obj, feature):
    """Build the ordered step list for the given feature: source loop, then each
    fixed/numbered group defined by the feature config."""
    cfg = FEATURES.get(feature, FEATURES['Eyelid'])

    steps = [{
        "select": cfg['source_select'],
        "group": cfg['source_group'],
        "button": cfg['source_button'],
        "section": "Source",
        "action": "source_loop",
    }]

    is_mesh = bool(obj and obj.type == 'MESH')

    for item in cfg['order']:
        if item['kind'] == 'fixed':
            if item.get('optional') and not (is_mesh and obj.vertex_groups.get(item['group'])):
                continue
            steps.append({
                "select": item['select'],
                "group": item['group'],
                "button": item['button'],
                "section": item['section'],
                "action": "weight",
            })
        elif item['kind'] == 'numbered':
            if not is_mesh:
                continue
            for num, name in _collect_numbered_groups(obj, item['prefix'], item['suffix']):
                steps.append({
                    "select": item['select_fmt'].format(n=num),
                    "group": name,
                    "button": item['button_fmt'].format(n=num),
                    "section": item['section'],
                    "action": "weight",
                })

    return steps


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


def get_eye_mesh(context):
    """The mesh being weighted: the active mesh if present, else the stored Object."""
    obj = context.object
    if obj and obj.type == 'MESH':
        return obj
    stored = context.scene.eye_skin_object
    if stored and stored.type == 'MESH':
        return stored
    return None


def get_eye_armature_bones(self, context):
    scene = context.scene
    arm_obj = scene.eye_skin_armature
    if arm_obj and arm_obj.type == 'ARMATURE':
        return [(b.name, b.name, f"Lock {b.name} while assigning") for b in arm_obj.data.bones]
    return [("NONE", "No Armature Selected", "Select an armature object first")]


class MESH_OT_eye_skin_wizard(bpy.types.Operator):
    """Assign the selected loop to the current step's vertex group, mimicking the
    by-hand UI behavior: Auto-Normalize on with every group locked except the
    Source Template mask and the DEF-<feature> groups, so assigning weight 1.0
    subtracts from the Source Template mask"""
    bl_idname = "mesh.eye_skin_wizard"
    bl_label = "Eye Skin Weighting Step"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        obj = context.object

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Active object must be a Mesh.")
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "You must be in Edit Mode on the Mesh.")
            return {'CANCELLED'}

        steps = build_eye_skin_steps(obj, scene.eye_skin_feature)
        step = min(scene.eye_skin_step, len(steps))
        scene.eye_skin_step = step

        step_data = steps[step - 1]
        target_name = step_data["group"]
        action = step_data.get("action", "weight")

        obj.update_from_editmode()
        selected = [v.index for v in obj.data.vertices if v.select]
        if not selected:
            self.report({'WARNING'}, f"Step {step} Failed: No vertices selected!")
            return {'CANCELLED'}

        scene.eye_skin_object = obj

        if action == "source_loop":
            self.assign_source_loop(context, obj, target_name, selected)
        else:
            source_bone = scene.eye_skin_source_bone
            if source_bone == "NONE" or not source_bone:
                self.report({'ERROR'}, "Please choose a valid Source Template Bone.")
                return {'CANCELLED'}
            self.assign_locked_weight(context, obj, target_name, source_bone)

        if step < len(steps):
            scene.eye_skin_step = step + 1
            next_label = steps[step]["select"]
            self.report({'INFO'}, f"Assigned {len(selected)} verts to '{target_name}'. Next: {next_label}.")
        else:
            scene.eye_skin_step = 1
            self.report({'INFO'}, f"Assigned {len(selected)} verts to '{target_name}'. All steps complete.")

        return {'FINISHED'}

    def assign_source_loop(self, context, obj, target_name, indices):
        """Add the selected verts to the ``HLP-*`` group and record it as the
        Source Loop. This is a plain group assignment, not a weighting step."""
        target_vg = obj.vertex_groups.get(target_name) or obj.vertex_groups.new(name=target_name)

        bpy.ops.object.mode_set(mode='OBJECT')
        target_vg.add(indices, 1.0, 'REPLACE')
        bpy.ops.object.mode_set(mode='EDIT')

        context.scene.eye_skin_source_loop = target_name

    def assign_locked_weight(self, context, obj, target_name, source_name):
        """Set weight 1.0 on the selected verts for ``target_name``. Every vertex
        group is locked EXCEPT the Source Template group and the DEF-<feature>
        groups, so Auto-Normalize (via weight-paint "Set Weight") pulls the
        assigned weight out of the Source Template mask."""
        ts = context.scene.tool_settings
        def_prefix = f"DEF-{context.scene.eye_skin_feature}"

        target_vg = obj.vertex_groups.get(target_name) or obj.vertex_groups.new(name=target_name)

        # Recompute all lock flags from scratch each step: unlock the source mask
        # and every DEF-<feature> group, lock everything else.
        for vg in obj.vertex_groups:
            keep_unlocked = (vg.name == source_name) or vg.name.startswith(def_prefix)
            vg.lock_weight = not keep_unlocked

        obj.vertex_groups.active_index = target_vg.index
        ts.vertex_group_weight = 1.0
        ts.use_auto_normalize = True

        obj.data.use_paint_mask_vertex = True

        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        bpy.ops.paint.weight_set()
        bpy.ops.object.mode_set(mode='EDIT')


class MESH_OT_reset_eye_skin_wizard(bpy.types.Operator):
    """Reset the eye skin weighting wizard back to Step 1"""
    bl_idname = "mesh.reset_eye_skin_wizard"
    bl_label = "Reset Wizard"

    def execute(self, context):
        context.scene.eye_skin_step = 1
        self.report({'INFO'}, "Skin weighting wizard reset to Step 1.")
        return {'FINISHED'}


class VIEW3D_PT_eye_skin_weighting_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Roblox'
    bl_label = 'Eye/Lip Skin Weighting'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.object

        box = layout.box()
        box.label(text="Skin Weighting Tool", icon='MOD_VERTEX_WEIGHT')
        _draw_info(box, "Step 4: Select successive loops for your facial feature "
                        "and set the weighting to zero, subtracting from a base "
                        "mask vertex group.")
        box.separator()
        box.prop(scene, "eye_skin_feature", text="Feature")
        box.prop(scene, "eye_skin_object")
        box.prop(scene, "eye_skin_armature")

        if scene.eye_skin_armature and scene.eye_skin_armature.type == 'ARMATURE':
            box.prop(scene, "eye_skin_source_bone", text="Source Template Bone")

        mesh_obj = scene.eye_skin_object
        if mesh_obj and mesh_obj.type == 'MESH':
            box.prop_search(
                scene, "eye_skin_source_loop",
                mesh_obj, "vertex_groups",
                text="Source Loop",
            )
        else:
            box.prop(scene, "eye_skin_source_loop", text="Source Loop")

        box.separator()

        if not obj or context.mode != 'EDIT_MESH':
            box.label(text="Please enter Mesh Edit Mode", icon='EDITMODE_HLT')
            box.prop(scene, "eye_skin_step")
            return

        steps = build_eye_skin_steps(get_eye_mesh(context), scene.eye_skin_feature)
        current_step = min(scene.eye_skin_step, len(steps))

        box.label(text=f"Weighting Steps ({current_step}/{len(steps)}):", icon='CHECKBOX_DEHLT')

        last_section = None
        for i, step_data in enumerate(steps):
            step_num = i + 1

            section = step_data.get("section")
            if section != last_section:
                box.label(text=section, icon='DOT')
                last_section = section

            text = f"{step_num}. {step_data['select']}"
            row = box.row()
            if current_step == step_num:
                row.label(text=f"\u25b6 {text}", icon='FORWARD')
            elif current_step > step_num:
                row.label(text=text, icon='CHECKMARK')
            else:
                row.label(text=text, icon='BLANK1')

        btn_text = steps[current_step - 1]["button"]

        box.separator()
        col = box.column(align=True)
        col.scale_y = 1.2
        col.operator("mesh.eye_skin_wizard", text=btn_text, icon='PLAY')

        box.prop(scene, "eye_skin_step")
        box.separator()
        box.operator("mesh.reset_eye_skin_wizard", text="Reset to Beginning", icon='FILE_REFRESH')


classes = (
    MESH_OT_eye_skin_wizard,
    MESH_OT_reset_eye_skin_wizard,
    VIEW3D_PT_eye_skin_weighting_panel,
)


def register():
    bpy.types.Scene.eye_skin_feature = bpy.props.EnumProperty(
        name="Feature",
        description="Which ribbon is being weighted; controls the DEF-* group naming and step order",
        items=[
            ('Eyelid', 'Eyelid', 'Weight eyelid loops to DEF-Eyelid-*.L groups'),
            ('Lip', 'Lip', 'Weight lip loops to DEF-Lip-* groups (L/R corners, center, per-side loops)'),
        ],
        default='Eyelid',
    )
    bpy.types.Scene.eye_skin_object = bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
        description="The mesh to be skinned",
        poll=lambda self, obj: obj.type == 'MESH',
    )
    bpy.types.Scene.eye_skin_armature = bpy.props.PointerProperty(
        name="Armature",
        type=bpy.types.Object,
        description="The armature the mesh will be bound to",
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )
    bpy.types.Scene.eye_skin_source_bone = bpy.props.EnumProperty(
        name="Source Template Bone",
        description="The bone whose vertex group is locked while assigning weights",
        items=get_eye_armature_bones,
    )
    bpy.types.Scene.eye_skin_source_loop = bpy.props.StringProperty(
        name="Source Loop",
        description="Vertex group on the mesh that defines the source loop",
    )
    bpy.types.Scene.eye_skin_step = bpy.props.IntProperty(
        name="Jump to Step",
        description="Click the arrows to quickly shift active workflow steps",
        default=1,
        min=1,
        max=_MAX_STEPS,
    )

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.eye_skin_feature
    del bpy.types.Scene.eye_skin_object
    del bpy.types.Scene.eye_skin_armature
    del bpy.types.Scene.eye_skin_source_bone
    del bpy.types.Scene.eye_skin_source_loop
    del bpy.types.Scene.eye_skin_step
