import re

import bpy


SOURCE_LOOP_GROUP = "HLP-EyeLoop.L"

# Step 1 captures the source eye loop; the next two steps are the corners.
# Upper/lower loop steps are appended dynamically from the mesh's existing
# DEF-Eyelid-Upper#/Lower# groups.
BASE_STEPS = [
    {
        "select": "Set Source Eye Loop",
        "group": SOURCE_LOOP_GROUP,
        "button": "Set Source Eye Loop (.L)",
        "section": "Source",
        "action": "source_loop",
    },
    {
        "select": "Select Left Inner Corner Loop",
        "group": "DEF-Eyelid-Corner-Inner.L",
        "button": "Assign Inner Corner (.L)",
        "section": "Corners",
        "action": "weight",
    },
    {
        "select": "Select Left Outer Corner Loop",
        "group": "DEF-Eyelid-Corner-Outer.L",
        "button": "Assign Outer Corner (.L)",
        "section": "Corners",
        "action": "weight",
    },
]

UPPER_PREFIX = "DEF-Eyelid-Upper"
LOWER_PREFIX = "DEF-Eyelid-Lower"
SIDE_SUFFIX = ".L"

# Generous upper bound for the "Jump to Step" field; real range is clamped to
# the dynamic step count at runtime.
_MAX_STEPS = 100


def _collect_numbered_groups(obj, prefix, suffix):
    """Return ``[(number, group_name), ...]`` for groups like ``<prefix><n><suffix>``,
    sorted ascending by number (inner corner -> outer corner in world space)."""
    pattern = re.compile(r'^' + re.escape(prefix) + r'(\d+)' + re.escape(suffix) + r'$')
    found = []
    for vg in obj.vertex_groups:
        match = pattern.match(vg.name)
        if match:
            found.append((int(match.group(1)), vg.name))
    found.sort(key=lambda item: item[0])
    return found


def build_eye_skin_steps(obj):
    """Build the ordered step list: source loop, corners, upper loops, lower loops."""
    steps = [dict(step) for step in BASE_STEPS]

    if obj and obj.type == 'MESH':
        for num, name in _collect_numbered_groups(obj, UPPER_PREFIX, SIDE_SUFFIX):
            steps.append({
                "select": f"Select Upper Loop {num} (inner\u2192outer)",
                "group": name,
                "button": f"Assign Upper Loop {num} (.L)",
                "section": "Upper Loops",
                "action": "weight",
            })
        for num, name in _collect_numbered_groups(obj, LOWER_PREFIX, SIDE_SUFFIX):
            steps.append({
                "select": f"Select Lower Loop {num} (inner\u2192outer)",
                "group": name,
                "button": f"Assign Lower Loop {num} (.L)",
                "section": "Lower Loops",
                "action": "weight",
            })

    return steps


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
    by-hand UI behavior: Auto-Normalize on with the Source Template Bone group
    locked so its weights are preserved"""
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

        steps = build_eye_skin_steps(obj)
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
        """Add the selected verts to the ``HLP-EyeLoop`` group and record it as the
        Source Eye Loop. This is a plain group assignment, not a weighting step."""
        target_vg = obj.vertex_groups.get(target_name) or obj.vertex_groups.new(name=target_name)

        bpy.ops.object.mode_set(mode='OBJECT')
        target_vg.add(indices, 1.0, 'REPLACE')
        bpy.ops.object.mode_set(mode='EDIT')

        context.scene.eye_skin_source_loop = target_name

    def assign_locked_weight(self, context, obj, target_name, source_name):
        """Set weight 1.0 on the selected verts for ``target_name`` while keeping
        the ``source_name`` group locked, driven through Blender's own weight
        paint "Set Weight" so Auto-Normalize and lock behavior match the UI."""
        ts = context.scene.tool_settings

        target_vg = obj.vertex_groups.get(target_name) or obj.vertex_groups.new(name=target_name)

        for vg in obj.vertex_groups:
            if vg.name == source_name:
                vg.lock_weight = True
        target_vg.lock_weight = False

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
        self.report({'INFO'}, "Eye skin wizard reset to Step 1.")
        return {'FINISHED'}


class VIEW3D_PT_eye_skin_weighting_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Roblox'
    bl_label = 'Eye Skin Weighting'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.object

        box = layout.box()
        box.label(text="Eye Skin Weighting Tool", icon='MOD_VERTEX_WEIGHT')
        box.prop(scene, "eye_skin_object")
        box.prop(scene, "eye_skin_armature")

        if scene.eye_skin_armature and scene.eye_skin_armature.type == 'ARMATURE':
            box.prop(scene, "eye_skin_source_bone", text="Source Template Bone")

        mesh_obj = scene.eye_skin_object
        if mesh_obj and mesh_obj.type == 'MESH':
            box.prop_search(
                scene, "eye_skin_source_loop",
                mesh_obj, "vertex_groups",
                text="Source Eye Loop",
            )
        else:
            box.prop(scene, "eye_skin_source_loop", text="Source Eye Loop")

        box.separator()

        if not obj or context.mode != 'EDIT_MESH':
            box.label(text="Please enter Mesh Edit Mode", icon='EDITMODE_HLT')
            box.prop(scene, "eye_skin_step")
            return

        steps = build_eye_skin_steps(get_eye_mesh(context))
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
    bpy.types.Scene.eye_skin_object = bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
        description="The eye mesh to be skinned",
        poll=lambda self, obj: obj.type == 'MESH',
    )
    bpy.types.Scene.eye_skin_armature = bpy.props.PointerProperty(
        name="Armature",
        type=bpy.types.Object,
        description="The armature the eye mesh will be bound to",
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )
    bpy.types.Scene.eye_skin_source_bone = bpy.props.EnumProperty(
        name="Source Template Bone",
        description="The bone whose vertex group is locked while assigning weights",
        items=get_eye_armature_bones,
    )
    bpy.types.Scene.eye_skin_source_loop = bpy.props.StringProperty(
        name="Source Eye Loop",
        description="Vertex group on the eye mesh that defines the source eye loop",
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

    del bpy.types.Scene.eye_skin_object
    del bpy.types.Scene.eye_skin_armature
    del bpy.types.Scene.eye_skin_source_bone
    del bpy.types.Scene.eye_skin_source_loop
    del bpy.types.Scene.eye_skin_step
