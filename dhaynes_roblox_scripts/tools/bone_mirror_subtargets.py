import bpy


def mirror_name(name):
    """Flip the trailing ``.L`` <-> ``.R`` in a bone / vertex-group name."""
    if name.endswith(".L"):
        return name[:-2] + ".R"
    if name.endswith(".R"):
        return name[:-2] + ".L"
    return name


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


class POSE_OT_mirror_bone_subtargets(bpy.types.Operator):
    """Flip the .L/.R suffix of every constraint subtarget on the selected pose bones"""
    bl_idname = "pose.mirror_bone_subtargets"
    bl_label = "Mirror Bone Subtargets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return bool(obj and obj.type == 'ARMATURE' and context.mode == 'POSE')

    def execute(self, context):
        selected = context.selected_pose_bones or []
        if not selected:
            self.report({'WARNING'}, "No pose bones selected.")
            return {'CANCELLED'}

        changed = 0
        for bone in selected:
            for constraint in bone.constraints:
                subtarget = getattr(constraint, "subtarget", "")
                if not subtarget:
                    continue
                new_name = mirror_name(subtarget)
                if new_name != subtarget:
                    constraint.subtarget = new_name
                    changed += 1

        if changed:
            self.report({'INFO'}, f"Mirrored {changed} constraint subtarget(s).")
        else:
            self.report({'INFO'}, "No .L/.R subtargets to mirror on the selection.")
        return {'FINISHED'}


class VIEW3D_PT_bone_mirror_subtargets_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Roblox'
    bl_label = 'Bone Mirror Subtargets'

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Bone Mirror Subtargets", icon='MOD_MIRROR')
        _draw_info(box, "Flip the .L/.R suffix of every constraint subtarget on the "
                        "selected pose bones.")
        box.separator()

        obj = context.object
        if not (obj and obj.type == 'ARMATURE' and context.mode == 'POSE'):
            box.label(text="Enter Pose Mode on an armature", icon='INFO')

        col = box.column(align=True)
        col.scale_y = 1.2
        col.operator("pose.mirror_bone_subtargets", icon='ARROW_LEFTRIGHT')


classes = (
    POSE_OT_mirror_bone_subtargets,
    VIEW3D_PT_bone_mirror_subtargets_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
