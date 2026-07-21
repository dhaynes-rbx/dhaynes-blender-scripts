import bpy


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


class OBJECT_OT_build_export_deform_rig(bpy.types.Operator):
    """Build a flat, deform-only armature in its own collection. Each bone keeps
    its name and rest transform, is parented to a single root, and Copy Transforms
    the matching bone on the source rig. Skinned meshes are linked-duplicated and
    retargeted. Non-destructive: re-run to regenerate"""
    bl_idname = "object.build_export_deform_rig"
    bl_label = "Build Export Deform Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        source = scene.export_deform_source
        if not source and context.active_object and context.active_object.type == 'ARMATURE':
            source = context.active_object
        if not source or source.type != 'ARMATURE':
            self.report({'ERROR'}, "Please set a valid Source Armature.")
            return {'CANCELLED'}

        root_name = (scene.export_deform_root_name or "").strip() or "Root"
        export_name = (scene.export_deform_name or "").strip() or f"{source.name}_EXPORT"

        deform_bones = [b.name for b in source.data.bones if b.use_deform]
        if not deform_bones:
            self.report({'WARNING'}, "Source armature has no deform bones (use_deform=True).")
            return {'CANCELLED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Regenerate cleanly: drop any previous export collection of this name.
        self._purge_collection(export_name)

        coll = bpy.data.collections.new(export_name)
        scene.collection.children.link(coll)

        # --- Create the export armature ---
        arm_data = bpy.data.armatures.new(export_name)
        export_arm = bpy.data.objects.new(export_name, arm_data)
        coll.objects.link(export_arm)
        export_arm.matrix_world = source.matrix_world.copy()

        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = export_arm
        export_arm.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = arm_data.edit_bones
        root_eb = edit_bones.new(root_name)
        root_eb.head = (0.0, 0.0, 0.0)
        root_eb.tail = (0.0, 0.0, 0.1)
        root_eb.use_deform = False

        src_bones = source.data.bones
        for name in deform_bones:
            b = src_bones.get(name)
            if not b:
                continue
            eb = edit_bones.new(name)
            eb.head = b.head_local
            eb.tail = b.tail_local
            eb.matrix = b.matrix_local.copy()
            eb.use_deform = True
            eb.parent = root_eb

        bpy.ops.object.mode_set(mode='OBJECT')

        # --- Copy Transforms constraints (source -> export) ---
        bpy.ops.object.mode_set(mode='POSE')
        for name in deform_bones:
            pb = export_arm.pose.bones.get(name)
            if not pb:
                continue
            con = pb.constraints.new(type='COPY_TRANSFORMS')
            con.target = source
            con.subtarget = name
        bpy.ops.object.mode_set(mode='OBJECT')

        # --- Linked-duplicate skinned meshes, retargeted to the export rig ---
        mesh_count = self._duplicate_skinned_meshes(context, source, export_arm, coll)

        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = export_arm
        export_arm.select_set(True)

        self.report(
            {'INFO'},
            f"Built '{export_name}': {len(deform_bones)} deform bones, {mesh_count} mesh(es).",
        )
        return {'FINISHED'}

    def _purge_collection(self, name):
        """Delete the named collection and every object inside it (used to make
        re-runs idempotent). Shared mesh data survives with its original owner."""
        coll = bpy.data.collections.get(name)
        if not coll:
            return
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(coll)

    def _duplicate_skinned_meshes(self, context, source, export_arm, coll):
        count = 0
        for obj in list(context.scene.objects):
            if obj.type != 'MESH':
                continue
            if not any(m.type == 'ARMATURE' and m.object == source for m in obj.modifiers):
                continue

            dup = obj.copy()  # shares mesh data (vertex groups included)
            dup.name = f"{obj.name}_EXPORT"
            coll.objects.link(dup)

            for m in dup.modifiers:
                if m.type == 'ARMATURE' and m.object == source:
                    m.object = export_arm

            if dup.parent == source:
                world = dup.matrix_world.copy()
                dup.parent = export_arm
                dup.matrix_world = world

            count += 1
        return count


class VIEW3D_PT_export_deform_rig_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Roblox'
    bl_label = 'Export Deform Rig'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Export Deform Rig", icon='ARMATURE_DATA')
        _draw_info(box, "Build a flat, deform-only armature (Copy Transforms to the "
                        "source rig) in its own collection, ready to bake and export "
                        "to Roblox.")
        box.separator()

        box.prop(scene, "export_deform_source")
        box.prop(scene, "export_deform_root_name")
        box.prop(scene, "export_deform_name")

        box.separator()
        col = box.column(align=True)
        col.scale_y = 1.2
        col.operator("object.build_export_deform_rig", icon='PLAY')


classes = (
    OBJECT_OT_build_export_deform_rig,
    VIEW3D_PT_export_deform_rig_panel,
)


def register():
    bpy.types.Scene.export_deform_source = bpy.props.PointerProperty(
        name="Source Armature",
        type=bpy.types.Object,
        description="The control rig to copy deform bones from",
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )
    bpy.types.Scene.export_deform_root_name = bpy.props.StringProperty(
        name="Root Bone",
        description="Name of the single root bone the flat deform hierarchy hangs under",
        default="Root",
    )
    bpy.types.Scene.export_deform_name = bpy.props.StringProperty(
        name="Export Name",
        description="Name for the export collection and armature (blank = <source>_EXPORT)",
        default="",
    )

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.export_deform_source
    del bpy.types.Scene.export_deform_root_name
    del bpy.types.Scene.export_deform_name
