import bpy
import bmesh


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
                scene.facial_wizard_step = 5
                bpy.ops.object.mode_set(mode='OBJECT')

            return {'FINISHED'}

        # --- STEP 5: ARMATURE & BONE GENERATION ---
        elif current_step == 5:
            mesh_obj = scene.facial_wizard_mesh
            arm_obj = scene.facial_wizard_armature
            parent_bone_name = scene.facial_wizard_source_bone

            if not mesh_obj or mesh_obj.type != 'MESH':
                self.report({'ERROR'}, "Please specify a valid Target Mesh in the wizard controls block.")
                return {'CANCELLED'}
            if not arm_obj or arm_obj.type != 'ARMATURE':
                self.report({'ERROR'}, "Please specify a valid Target Armature in the wizard controls block.")
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

            parent_matrix = template_bone.matrix.copy()
            parent_head = template_bone.head.copy()
            parent_tail = template_bone.tail.copy()
            parent_roll = template_bone.roll

            feature = scene.facial_wizard_feature
            side = scene.facial_wizard_side
            hk_prefix = f"HK-{feature}"

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

            # Swap to Pose Mode to assign constraints
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

            self.report({'INFO'}, f"Successfully initialized {len(created_bone_names)} constraint tracking nodes.")
            scene.facial_wizard_step = 1
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

        # --- 1. WIZARD CONTROLS & PICKERS BLOCK ---
        config_box = layout.box()
        config_box.label(text="Wizard Controls:", icon='SETTINGS')
        config_box.prop(scene, "facial_wizard_step")
        config_box.separator()

        row_feat = config_box.row(align=True)
        row_feat.prop(scene, "facial_wizard_feature", expand=True)
        row_side = config_box.row(align=True)
        row_side.prop(scene, "facial_wizard_side", expand=True)

        config_box.separator()
        config_box.label(text="Source/Target Linking Setup:", icon='LINKED')
        config_box.prop(scene, "facial_wizard_mesh")
        config_box.prop(scene, "facial_wizard_armature")

        if scene.facial_wizard_armature and scene.facial_wizard_armature.type == 'ARMATURE':
            config_box.prop(scene, "facial_wizard_source_bone", text="Source Template Bone")

        layout.separator()

        if current_step in (1, 2, 3, 4) and (not obj or context.mode != 'EDIT_MESH'):
            layout.label(text="Please enter Mesh Edit Mode", icon='EDITMODE_HLT')
            return

        # --- 2. WORKFLOW STEPS CHECKLIST ---
        box = layout.box()
        box.label(text=f"Steps ({feature}.{side}):", icon='CHECKBOX_DEHLT')

        def draw_step_line(step_num, text, icon_str='BLANK1'):
            row = box.row()
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
        draw_step_line(5, "5. Build Rig Assets via Pickers", 'ARMATURE_DATA')

        layout.separator()

        # --- 3. DYNAMIC EXECUTION BUTTONS ---
        if current_step == 1:
            btn_text = "Assign Inner Corner"
        elif current_step == 2:
            btn_text = "Assign Outer Corner"
        elif current_step == 3:
            btn_text = "Assign Upper Loop"
        elif current_step == 4:
            btn_text = "Assign Lower Loop"
        elif current_step == 5:
            btn_text = "Generate MCH Bones & Constraints"
        else:
            btn_text = "Run"

        col = layout.column(align=True)
        col.scale_y = 1.2
        col.operator("mesh.facial_wizard", text=f"{btn_text}", icon='PLAY')

        col.separator()
        col.operator("mesh.reset_facial_wizard", text="Reset to Beginning", icon='FILE_REFRESH')


classes = (
    MESH_OT_facial_wizard,
    MESH_OT_reset_facial_wizard,
    VIEW3D_PT_facial_wizard_panel,
)


def register():
    bpy.types.Scene.facial_wizard_step = bpy.props.IntProperty(
        name="Jump to Step",
        description="Click the arrows to quickly shift active workflow steps",
        default=1,
        min=1,
        max=5,
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
            ('Lips', 'Lips', 'Generate HK-Lips naming strings'),
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
