import math

import bpy
import bmesh
from mathutils import Vector


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
        current_step = scene.facial_wizard_step
        obj = context.object

        # --- STEPS 1 to 4: MESH OPERATIONS ---
        if current_step in (1, 2, 3, 4):
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

            bpy.ops.object.mode_set(mode='OBJECT')
            feature = scene.facial_wizard_feature
            side = scene.facial_wizard_side

            if current_step == 1:
                self.assign_to_group(obj, selected_data, f"HK-{feature}-Corner-Inner.{side}", sequential=False)
                self.report({'INFO'}, "Inner Corner Assigned. Next: Select Outer Corner.")
                scene.facial_wizard_step = 2
                bpy.ops.object.mode_set(mode='EDIT')

            elif current_step == 2:
                self.assign_to_group(obj, selected_data, f"HK-{feature}-Corner-Outer.{side}", sequential=False)
                self.report({'INFO'}, "Outer Corner Assigned. Next: Select Upper loop.")
                scene.facial_wizard_step = 3
                bpy.ops.object.mode_set(mode='EDIT')

            elif current_step == 3:
                self.assign_to_group(obj, selected_data, f"HK-{feature}-Upper.{side}", sequential=True)
                self.report({'INFO'}, "Upper loop Assigned Left-to-Right. Next: Select Lower loop.")
                scene.facial_wizard_step = 4
                bpy.ops.object.mode_set(mode='EDIT')

            elif current_step == 4:
                self.assign_to_group(obj, selected_data, f"HK-{feature}-Lower.{side}", sequential=True)
                self.report({'INFO'}, "Vertex Groups Complete! Targets locked in.")
                scene.facial_wizard_step = 1
                bpy.ops.object.mode_set(mode='OBJECT')

            return {'FINISHED'}

        return {'CANCELLED'}

    def assign_to_group(self, obj, vert_data, base_name, sequential):
        if not sequential:
            indices = [v['index'] for v in vert_data]
            vg = obj.vertex_groups.get(base_name) or obj.vertex_groups.new(name=base_name)
            vg.add(indices, 1.0, 'REPLACE')
        else:
            sorted_data = sorted(vert_data, key=lambda v: v['x_world'])
            name_part, ext = base_name.rsplit('.', 1) if '.' in base_name else (base_name, "")
            suffix = f".{ext}" if ext else ""

            for i, v in enumerate(sorted_data):
                group_name = f"{name_part}{i + 1}{suffix}"
                vg = obj.vertex_groups.get(group_name) or obj.vertex_groups.new(name=group_name)
                vg.add([v['index']], 1.0, 'REPLACE')


class MESH_OT_reset_facial_wizard(bpy.types.Operator):
    """Reset the wizard back to Step 1"""
    bl_idname = "mesh.reset_facial_wizard"
    bl_label = "Reset Wizard"

    def execute(self, context):
        context.scene.facial_wizard_step = 1
        self.report({'INFO'}, "Wizard reset to the beginning (Step 1).")
        return {'FINISHED'}


class MESH_OT_generate_damped_track_bones(bpy.types.Operator):
    """Generate MCH damped-track bones and DEF deformation bones from the established vertex groups"""
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

        context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode='EDIT')

        arm_data = arm_obj.data
        template_bone = arm_data.edit_bones.get(parent_bone_name)

        if not template_bone:
            self.report({'ERROR'}, f"Template bone '{parent_bone_name}' not found inside rig.")
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'CANCELLED'}

        feature = scene.facial_wizard_feature
        side = scene.facial_wizard_side
        hk_prefix = f"HK-{feature}"

        stale_bones = [
            eb for eb in arm_data.edit_bones
            if (eb.name.startswith(f"MCH-{feature}") or eb.name.startswith(f"DEF-{feature}"))
            and eb.name.endswith(f".{side}")
        ]
        for eb in stale_bones:
            arm_data.edit_bones.remove(eb)

        parent_matrix = template_bone.matrix.copy()
        parent_head = template_bone.head.copy()
        parent_tail = template_bone.tail.copy()
        parent_roll = template_bone.roll

        target_groups = [vg.name for vg in mesh_obj.vertex_groups if vg.name.startswith(hk_prefix) and vg.name.endswith(f".{side}")]

        if not target_groups:
            self.report({'WARNING'}, f"No existing '{hk_prefix}*.{side}' groups discovered on '{mesh_obj.name}'.")
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

        # --- Pose Mode: add constraints, evaluate, apply rest pose ---
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
                if mch_bone:
                    eb.parent = mch_bone
                else:
                    eb.parent = template_bone
                def_count += 1

        bpy.ops.object.mode_set(mode='OBJECT')

        self.report({'INFO'}, f"Created {len(created_bone_names)} MCH bones and {def_count} DEF bones.")
        return {'FINISHED'}


# --- UI PANEL ---
class VIEW3D_PT_facial_wizard_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Roblox'
    bl_label = 'Facial Vertex Groups'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scene = context.scene

        current_step = scene.facial_wizard_step
        feature = scene.facial_wizard_feature
        side = scene.facial_wizard_side

        # --- 1. WIZARD CONTROLS & STEPS BLOCK ---
        config_box = layout.box()
        config_box.label(text="Setup Ribbon Mesh Vertex Groups", icon='SETTINGS')

        row_side = config_box.row(align=True)
        row_side.prop(scene, "facial_wizard_side", expand=True)

        config_box.separator()

        if current_step in (1, 2, 3, 4) and (not obj or context.mode != 'EDIT_MESH'):
            config_box.label(text="Please enter Mesh Edit Mode", icon='EDITMODE_HLT')
            config_box.prop(scene, "facial_wizard_step")
        else:
            config_box.label(text=f"Steps ({feature}.{side}):", icon='CHECKBOX_DEHLT')

            def draw_step_line(step_num, text, icon_str='BLANK1'):
                row = config_box.row()
                if current_step == step_num:
                    row.label(text=f"\u25b6 {text}", icon='FORWARD')
                elif current_step > step_num:
                    row.label(text=text, icon='CHECKMARK')
                else:
                    row.label(text=text, icon=icon_str)

            draw_step_line(1, "1. Select Inner Corner vertex")
            draw_step_line(2, "2. Select Outer Corner vertex")
            draw_step_line(3, f"3. {feature} Upper loop")
            draw_step_line(4, f"4. {feature} Lower loop")

            # --- DYNAMIC EXECUTION BUTTONS ---
            if current_step == 1:
                btn_text = "Assign Inner Corner"
            elif current_step == 2:
                btn_text = "Assign Outer Corner"
            elif current_step == 3:
                btn_text = "Assign Upper Loop"
            elif current_step == 4:
                btn_text = "Assign Lower Loop"
            else:
                btn_text = "Run"

            config_box.separator()
            col = config_box.column(align=True)
            col.scale_y = 1.2
            col.operator("mesh.facial_wizard", text=f"{btn_text}", icon='PLAY')

            config_box.prop(scene, "facial_wizard_step")

            config_box.separator()
            config_box.operator("mesh.reset_facial_wizard", text="Reset to Beginning", icon='FILE_REFRESH')

        # --- 2. SOURCE/TARGET LINKING BLOCK ---
        layout.separator()
        link_box = layout.box()
        link_box.label(text="Generate Damped Track Bones", icon='LINKED')
        link_box.prop(scene, "facial_wizard_mesh")
        link_box.prop(scene, "facial_wizard_armature")

        if scene.facial_wizard_armature and scene.facial_wizard_armature.type == 'ARMATURE':
            link_box.prop(scene, "facial_wizard_source_bone", text="Source Template Bone")

        link_box.separator()
        col = link_box.column(align=True)
        col.scale_y = 1.2
        col.operator("mesh.generate_damped_track_bones",
                     text="Generate Damped Track Bones", icon='PLAY')


classes = (
    MESH_OT_facial_wizard,
    MESH_OT_reset_facial_wizard,
    MESH_OT_generate_damped_track_bones,
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
            ('Eyelid', 'Eyelid', 'Generate HK-Eyelid naming strings'),
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
