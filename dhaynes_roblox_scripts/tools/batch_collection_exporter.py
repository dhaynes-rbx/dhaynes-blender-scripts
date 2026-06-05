import bpy
import os
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty
from bpy.types import Operator, Panel


def roblox_fbx_export_kwargs():
    """Match File > Export > FBX preset export_to_roblox (shared by batch + active-collection export)."""
    return {
        "use_selection": True,
        "use_visible": False,
        "use_active_collection": False,
        "global_scale": 0.01,
        "apply_unit_scale": True,
        "apply_scale_options": "FBX_SCALE_NONE",
        "use_space_transform": True,
        "bake_space_transform": False,
        "object_types": {"MESH", "ARMATURE"},
        "use_mesh_modifiers": True,
        "use_mesh_modifiers_render": True,
        "mesh_smooth_type": "OFF",
        "colors_type": "SRGB",
        "prioritize_active_color": False,
        "use_subsurf": False,
        "use_mesh_edges": False,
        "use_tspace": False,
        "use_triangles": False,
        "use_custom_props": False,
        "add_leaf_bones": False,
        "primary_bone_axis": "Y",
        "secondary_bone_axis": "X",
        "use_armature_deform_only": False,
        "armature_nodetype": "NULL",
        "bake_anim": True,
        "bake_anim_use_all_bones": True,
        "bake_anim_use_nla_strips": False,
        "bake_anim_use_all_actions": False,
        "bake_anim_force_startend_keying": True,
        "bake_anim_step": 1.0,
        "bake_anim_simplify_factor": 1.0,
        "path_mode": "AUTO",
        "embed_textures": False,
        "batch_mode": "OFF",
        "use_batch_own_dir": True,
        "axis_forward": "-Z",
        "axis_up": "Y",
    }


class ROBLOX_OT_BatchExportCollections(Operator, ExportHelper):
    """Export top-level collections (Meshes & Armatures) as individual FBX files"""

    bl_idname = "roblox.batch_export_collections"
    bl_label = "Export Collections to FBX"

    filename_ext = ""
    directory: StringProperty(subtype="DIR_PATH")

    def execute(self, context):
        if not self.directory:
            self.report({"ERROR"}, "No folder selected.")
            return {"CANCELLED"}

        view_layer = context.view_layer
        scene_collection = context.scene.collection

        original_selection = context.selected_objects
        original_active = context.view_layer.objects.active

        for coll in scene_collection.children:
            layer_coll = view_layer.layer_collection.children.get(coll.name)
            if layer_coll and layer_coll.exclude:
                continue
            if coll.hide_viewport:
                continue

            export_objs = [obj for obj in coll.all_objects if obj.type in {"MESH", "ARMATURE"}]

            if not export_objs:
                continue

            bpy.ops.object.select_all(action="DESELECT")
            for obj in export_objs:
                obj.select_set(True)

            view_layer.objects.active = export_objs[0]
            file_path = os.path.join(self.directory, f"{coll.name}.fbx")

            bpy.ops.export_scene.fbx(filepath=file_path, **roblox_fbx_export_kwargs())

            self.report({"INFO"}, f"Exported: {coll.name}.fbx")

        bpy.ops.object.select_all(action="DESELECT")
        for obj in original_selection:
            try:
                obj.select_set(True)
            except ReferenceError:
                pass
        context.view_layer.objects.active = original_active

        return {"FINISHED"}


class ROBLOX_OT_ExportActiveCollection(Operator, ExportHelper):
    """Export the Outliner-active collection as one FBX (meshes & armatures under that collection)."""

    bl_idname = "roblox.export_active_collection"
    bl_label = "Export Active Collection to FBX"

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def invoke(self, context, _event):
        view_layer = context.view_layer
        scene = context.scene
        alc = view_layer.active_layer_collection
        if alc is None:
            self.report({"ERROR"}, "No active collection.")
            return {"CANCELLED"}

        coll = alc.collection
        if coll == scene.collection:
            self.report(
                {"ERROR"},
                "Cannot export Scene Collection. Click a collection under it in the Outliner, then try again.",
            )
            return {"CANCELLED"}

        export_objs = [obj for obj in coll.all_objects if obj.type in {"MESH", "ARMATURE"}]
        if not export_objs:
            self.report({"ERROR"}, "Active collection has no mesh or armature objects to export.")
            return {"CANCELLED"}

        safe_name = bpy.path.clean_name(coll.name) or "collection"
        self.filepath = bpy.path.ensure_ext(safe_name, self.filename_ext)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "No file path.")
            return {"CANCELLED"}

        view_layer = context.view_layer
        scene = context.scene
        alc = view_layer.active_layer_collection
        if alc is None:
            self.report({"ERROR"}, "No active collection.")
            return {"CANCELLED"}

        coll = alc.collection
        if coll == scene.collection:
            self.report(
                {"ERROR"},
                "Cannot export Scene Collection. Click a collection under it in the Outliner, then try again.",
            )
            return {"CANCELLED"}

        export_objs = [obj for obj in coll.all_objects if obj.type in {"MESH", "ARMATURE"}]
        if not export_objs:
            self.report({"ERROR"}, "Active collection has no mesh or armature objects to export.")
            return {"CANCELLED"}

        original_selection = context.selected_objects
        original_active = view_layer.objects.active

        bpy.ops.object.select_all(action="DESELECT")
        for obj in export_objs:
            obj.select_set(True)
        view_layer.objects.active = export_objs[0]

        file_path = bpy.path.abspath(self.filepath)
        bpy.ops.export_scene.fbx(filepath=file_path, **roblox_fbx_export_kwargs())

        self.report({"INFO"}, f"Exported: {os.path.basename(file_path)}")

        bpy.ops.object.select_all(action="DESELECT")
        for obj in original_selection:
            try:
                obj.select_set(True)
            except ReferenceError:
                pass
        view_layer.objects.active = original_active

        return {"FINISHED"}


class ROBLOX_PT_ExportPanel(Panel):
    bl_label = "Roblox Tools"
    bl_idname = "ROBLOX_PT_export_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Roblox"

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Batch Export", icon="EXPORT")
        box.operator("roblox.batch_export_collections", text="Export Collections to FBX")
        box = layout.box()
        box.label(text="Active Collection", icon="OUTLINER_COLLECTION")
        box.operator("roblox.export_active_collection", text="Export Active Collection")


classes = (
    ROBLOX_OT_BatchExportCollections,
    ROBLOX_OT_ExportActiveCollection,
    ROBLOX_PT_ExportPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
