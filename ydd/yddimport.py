import bpy
from bpy.types import (
    Object,
)
import os
import numpy as np
from typing import Optional
from ..cwxml.drawable import YDD, DrawableDictionary, Skeleton, Bone
from ..cwxml.fragment import YFT, Fragment
from ..cwxml.cloth import YLD, ClothDictionary, CharacterCloth
from ..ydr.ydrimport import create_drawable_obj, create_drawable_skel, apply_rotation_limits, set_bone_properties, create_bpy_bone
from ..ybn.ybnimport import create_bound_composite
from ..sollumz_properties import SollumType, SollumzGame, import_export_current_game as current_game, set_import_export_current_game
from ..sollumz_preferences import get_import_settings
from ..tools.blenderhelper import create_empty_object, create_blender_object, add_child_of_bone_constraint
from ..tools.utils import get_filename
from mathutils import Matrix

from .. import logger


def import_ydd(filepath: str):
    import_settings = get_import_settings()

    ydd_xml = YDD.from_xml_file(filepath)
    set_import_export_current_game(ydd_xml.game)

    # Import the cloth .yld.xml if it exists
    if current_game() == SollumzGame.GTA:
        yld_filepath = make_yld_filepath(filepath)
        yld_xml = YLD.from_xml_file(yld_filepath) if os.path.exists(yld_filepath) else None
    else:
        yld_xml = None

    if import_settings.import_ext_skeleton:
        skel_yft = load_external_skeleton(filepath)

        if skel_yft is not None and skel_yft.drawable.skeleton is not None:
            if current_game() == SollumzGame.GTA:
                return create_ydd_obj(ydd_xml, filepath, yld_xml, skel_yft)
            elif current_game() == SollumzGame.RDR:
                return RDR_create_ydd_obj_ext_skel(ydd_xml, filepath, skel_yft)

    return create_ydd_obj(ydd_xml, filepath, yld_xml, None)


def load_external_skeleton(ydd_filepath: str) -> Optional[Fragment]:
    """Read first yft at ydd_filepath into a Fragment"""
    directory = os.path.dirname(ydd_filepath)

    yft_filepath = get_first_yft_path(directory)

    if yft_filepath is None:
        logger.warning(f"Could not find external skeleton yft in directory '{directory}'.")
        return None

    logger.info(f"Using '{yft_filepath}' as external skeleton...")

    return YFT.from_xml_file(yft_filepath)


def get_first_yft_path(directory: str) -> Optional[str]:
    for filepath in os.listdir(directory):
        if filepath.endswith(".yft.xml"):
            return os.path.join(directory, filepath)

    return None


def RDR_create_ydd_obj_ext_skel(ydd_xml: DrawableDictionary, filepath: str, external_skel: Fragment):
    """Create ydd object with an external and extra skeleton."""
    name = get_filename(filepath)
    external_armature = None
    
    ydd_xml = ydd_xml.drawables

    # Create armatures parented to external armature which will be used on export
    skeletons_collection_empty = create_empty_object(SollumType.SKELETON, "ArmatureList", SollumzGame.RDR)
    for drawable_index, drawable_xml in enumerate(ydd_xml):
        if drawable_xml.skeleton.bones:
            armature = bpy.data.armatures.new(f"drawable_skeleton_{drawable_index}.skel")
            ydd_armature_obj = create_blender_object(
                SollumType.DRAWABLE_DICTIONARY, f"drawable_skeleton_{drawable_index}", armature, SollumzGame.RDR)

            create_drawable_skel(drawable_xml.skeleton, ydd_armature_obj)
            ydd_armature_obj.parent = skeletons_collection_empty

        for index, extra_skeleton_xml in enumerate(drawable_xml.extra_skeletons):
            external_armature = create_extra_skeleton_armature(f"extra_skeleton_{drawable_index}_{index}", extra_skeleton_xml)
            external_armature.parent = skeletons_collection_empty

    all_armatures = {}
    
    #add YFT armature
    all_armatures["external_skeleton"] = external_skel.drawable.skeleton
    
    # add all YDD drawable armatures
    for index, drawable_xml in enumerate(ydd_xml):
        print(drawable_xml.skeleton)
        if drawable_xml.skeleton.bones:
            all_armatures[f"drawable_skeleton_{index}"] = drawable_xml.skeleton

    # add all YDD ExtraSkeleton
    for drawable_xml in ydd_xml:
        for index, extra_skeleton in enumerate(drawable_xml.extra_skeletons):
            all_armatures[f"extra_skeleton_{index}"] = extra_skeleton

    external_armature = create_merged_armature(name, all_armatures)
    skeletons_collection_empty.parent = external_armature

    for drawable_xml in ydd_xml:
        external_bones = None

        if not drawable_xml.skeleton.bones:
            external_bones = external_skel.drawable.skeleton.bones

        drawable_obj = create_drawable_obj(
            drawable_xml, filepath, name=drawable_xml.hash, external_armature=external_armature, external_bones=external_bones, game=current_game())
        drawable_obj.parent = external_armature

    return external_armature


def create_merged_armature(name, skeleton_arr):
    def _get_bone_index_by_tag(tag, bones):
            bone_by_tag = None

            for bone in bones:
                bone_tag = bone.bone_properties.tag
                if bone_tag == tag:
                    bone_by_tag = bone.name
                    break
            if bone_by_tag is None:
                raise Exception(f"Unable to find bone with tag {tag} to get bone index")
            return bones.keys().index(bone_by_tag)
        
    armature = bpy.data.armatures.new(f"{name}.skel")
    armature_obj = create_blender_object(
        SollumType.DRAWABLE_DICTIONARY, name, armature, SollumzGame.RDR)
    
    ydd_bones_collection = armature_obj.data.collections.new('ydd_bones')
    yft_bones_collection = armature_obj.data.collections.new('yft_bones')
    extra_skel_bones_collection = armature_obj.data.collections.new('extra_skel_bones')
    scale_bones_collection = armature_obj.data.collections.new('SCALE_bones')
    ph_bones_collection = armature_obj.data.collections.new('PH_bones')
    mh_bones_collection = armature_obj.data.collections.new('MH_bones')

    bpy.context.view_layer.objects.active = armature_obj

    for skeleton_name, skeleton in skeleton_arr.items():
        bpy.ops.object.mode_set(mode="EDIT")
        if "extra_skeleton" not in skeleton_name:
            is_skel_drawable = False
            # Set parent bone for the very first bone in armature
            if "drawable_skeleton" in skeleton_name:
                index = _get_bone_index_by_tag(skeleton.parent_bone_tag, armature_obj.data.bones)
                skeleton.bones[0].parent_index = index
                is_skel_drawable = True

            for bone_xml in skeleton.bones:
                create_bpy_bone(bone_xml, armature_obj.data)
            # Toggle back to object mode to update armature data
            bpy.ops.object.mode_set(mode="OBJECT")
            for bone_xml in skeleton.bones:
                set_bone_properties(bone_xml, armature_obj.data)
                bone_name = bone_xml.name
                bone = armature_obj.data.bones[bone_name]
                

                if "SCALE_" in bone_name:
                    scale_bones_collection.assign(bone)
                    bone.color.palette = 'THEME07'
                elif "PH_" in bone_name:
                    ph_bones_collection.assign(bone)
                    bone.color.palette = 'THEME09'
                elif "MH_" in bone_name:
                    mh_bones_collection.assign(bone)
                    bone.color.palette = 'THEME11'
                else:
                    if is_skel_drawable:
                        ydd_bones_collection.assign(bone)
                        bone.color.palette = 'THEME01'
                    else:
                        yft_bones_collection.assign(bone)
                        bone.color.palette = 'THEME03'
        else:
            # Set parent bone for the very first bone in armature
            index = _get_bone_index_by_tag(skeleton.parent_bone_tag, armature_obj.data.bones)
            skeleton.bones[0].parent_index = index
            for bone_xml in skeleton.bones:
                # Convert parent bone index of this bone from current extra_armature list to global armature list
                if bone_xml.parent_index != -1 and bone_xml.index != 0:
                    tag = 0
                    for this_bone in skeleton.bones:
                        if this_bone.index == bone_xml.parent_index:
                            tag = this_bone.tag
                            break
                    bone_xml.parent_index = _get_bone_index_by_tag(tag, armature_obj.data.bones)
                create_bpy_bone(bone_xml, armature_obj.data)
                bpy.ops.object.mode_set(mode="OBJECT")
                set_bone_properties(bone_xml, armature_obj.data)
                bpy.ops.object.mode_set(mode="EDIT")

                bone_name = bone_xml.name
                bone = armature_obj.data.edit_bones[bone_name]
                
                if "SCALE_" in bone_name:
                    scale_bones_collection.assign(bone)
                    bone.color.palette = 'THEME07'
                elif "PH_" in bone_name:
                    ph_bones_collection.assign(bone)
                    bone.color.palette = 'THEME09'
                elif "MH_" in bone_name:
                    mh_bones_collection.assign(bone)
                    bone.color.palette = 'THEME11'
                else:
                    extra_skel_bones_collection.assign(bone)
                    bone.color.palette = 'THEME04'

    bpy.ops.object.mode_set(mode="OBJECT")
    return armature_obj



# def create_merged_extra_armature(name: str, drawable_skel, skel_yft):
#     def get_bone_index_by_tag(tag, bones):
#             bone_by_tag = None

#             for bone in bones:
#                 bone_tag = bone.bone_properties.tag
#                 if bone_tag == tag:
#                     bone_by_tag = bone.name
#                     break
#             if bone_by_tag is None:
#                 raise Exception(f"Unable to find bone with tag {tag} to get bone index")
#             return bones.keys().index(bone_by_tag)
    
#     def _create_bpy_bone(bone_xml, armature: bpy.types.Armature, all_bone_xmls=None):
#         # bpy.context.view_layer.objects.active = armature
#         # print("Starting bone creation:", bone_xml.name)
#         edit_bone = armature.edit_bones.get(bone_xml.name)
#         if edit_bone is None:
#             edit_bone = armature.edit_bones.new(bone_xml.name)
#         if bone_xml.parent_index != -1:
#             if bone_xml.extra_skel_bone and not bone_xml.root:
#                 tag = None
#                 for this_bone in all_bone_xmls:
#                     if this_bone.index == bone_xml.parent_index:
#                         tag = this_bone.tag
#                         break
#                 # print("Parent index find",bone_xml.name, tag, all_bone_xmls[bone_xml.parent_index].tag)
#                 index = get_bone_index_by_tag(tag, armature.bones)
#                 # print("Parent index bone relative to this armature is", index)
#                 edit_bone.parent = armature.edit_bones[index]
#             else:
#                 edit_bone.parent = armature.edit_bones[bone_xml.parent_index]

#         # https://github.com/LendoK/Blender_GTA_V_model_importer/blob/master/importer.py
#         mat_rot = bone_xml.rotation.to_matrix().to_4x4()
#         mat_loc = Matrix.Translation(bone_xml.translation)
#         mat_sca = Matrix.Scale(1, 4, bone_xml.scale)            

#         edit_bone.head = (0, 0, 0)
#         edit_bone.tail = (0, 0.05, 0)
#         # if bone_xml.extra_skel_bone:
#         #     edit_bone.matrix = mat_loc @ mat_rot @ mat_sca
#         #     # edit_bone.matrix.invert()
#         # else:
#         edit_bone.matrix = mat_loc @ mat_rot @ mat_sca

#         if edit_bone.parent is not None:
#             edit_bone.matrix = edit_bone.parent.matrix @ edit_bone.matrix

#         return bone_xml.name

    
#     def _create_skel(drawable_skel, extra_skel, skel_yft, armature_obj: bpy.types.Object):
#         bpy.context.view_layer.objects.active = armature_obj
#         # bones = []
#         # for bone in drawable_skel:
#         #     bones.append(bone)
        
#         # for bone in skel_yft:
#         #     bones.append(bone)
        
#         # print("Bones before adding extra:", len(bones))
#         # print("Bones in extraskel:", len(bones))
        
#         # for skel in extra_skel:
#         #     first_bone = True
#         #     for bone in skel.bones:
#         #         if first_bone:
#         #             bone.parent_index = get_bone_by_tag(extra_skel.parent_bone_tag, )
#         #         setattr(bone, "extra_skel_bone", True)
#         #         bones.append(bone)

#         # print("Bones after adding extra:", len(bones), skel_yft[0], skel_yft[0].extra_skel_bone)
#         ydd_bones_collection = armature_obj.data.collections.new('ydd_bones')
#         yft_bones_collection = armature_obj.data.collections.new('yft_bones')
#         ydd_extra_bones_collection = armature_obj.data.collections.new('ydd_extra_bones')
        
#         bpy.ops.object.mode_set(mode="EDIT")

#         for bone_xml in skel_yft:
#             _create_bpy_bone(bone_xml, armature_obj.data)

#         bpy.ops.object.mode_set(mode="OBJECT")

#         for bone_xml in skel_yft:
#             set_bone_properties(bone_xml, armature_obj.data)
#         for bone in armature_obj.pose.bones:
#             yft_bones_collection.assign(bone)
#             bone.color.palette = 'THEME01'


#         bpy.ops.object.mode_set(mode="EDIT")

#         for bone_xml in drawable_skel:
#             _create_bpy_bone(bone_xml, armature_obj.data)

#         bpy.ops.object.mode_set(mode="OBJECT")

#         for bone_xml in drawable_skel:
#             set_bone_properties(bone_xml, armature_obj.data)
#         for bone in armature_obj.data.bones:
#             if bone.collections.get('yft_bones') is None:
#                 ydd_bones_collection.assign(armature_obj.pose.bones[bone.name])
#                 bone.color.palette = 'THEME07'
        
#         # Set back edit mode and create extraskeleton bones so that we can get existing bones
#         bpy.ops.object.mode_set(mode="EDIT")
#         # print("Starting extra bone creation")
#         extra_bone_names = []
#         for skel in extra_skel:
#             index = get_bone_index_by_tag(skel.parent_bone_tag, armature_obj.data.bones)
#             # print(f"Parent bone index for armature {skel} is {index}")
#             skel.bones[0].parent_index = index
#             setattr(skel.bones[0], "root", True)
#             for bone_xml in skel.bones:
#                 extra_bone_names.append(bone_xml.name)
#                 setattr(bone_xml, "extra_skel_bone", True)
#                 _create_bpy_bone(bone_xml, armature_obj.data, skel.bones)
#                 bpy.ops.object.mode_set(mode="OBJECT")
#                 set_bone_properties(bone_xml, armature_obj.data)
#                 bpy.ops.object.mode_set(mode="EDIT")

#         bpy.ops.object.mode_set(mode="OBJECT")

#         # for bone_xml in drawable_skel:
#         #     set_bone_properties(bone_xml, armature_obj.data)
#         for bone in armature_obj.data.bones:
#             if bone.name in extra_bone_names:
#                 ydd_extra_bones_collection.assign(armature_obj.pose.bones[bone.name])
#                 bone.color.palette = 'THEME12'

#         return armature_obj

#     armature = bpy.data.armatures.new(f"{name}.skel")
#     dict_obj = create_blender_object(
#         SollumType.DRAWABLE_DICTIONARY, name, armature, SollumzGame.RDR)
#     # print("Extradebug", drawable_skel.extra_skeletons, dir(drawable_skel.extra_skeletons))
#     _create_skel(drawable_skel.skeleton.bones, drawable_skel.extra_skeletons, skel_yft.bones, dict_obj)

#     if current_game() == SollumzGame.GTA:
#         rot_limits = skel_yft.drawable.joints.rotation_limits
#         if rot_limits:
#             apply_rotation_limits(rot_limits, dict_obj)

#     return dict_obj



def create_ydd_obj(ydd_xml: DrawableDictionary, filepath: str, yld_xml: Optional[ClothDictionary], external_skel: Optional[Fragment]):
    name = get_filename(filepath)
    if external_skel is not None:
        dict_obj = create_armature_parent(name, external_skel, current_game())
    else:
        dict_obj = create_empty_object(SollumType.DRAWABLE_DICTIONARY, name, current_game())

    ydd_xml_list = ydd_xml
    if current_game() == SollumzGame.RDR:
        ydd_xml_list = ydd_xml.drawables

    ydd_skel = find_first_skel(ydd_xml_list)

    for drawable_xml in ydd_xml_list:
        external_armature = None
        external_bones = None
        if external_skel is not None:
            if not drawable_xml.skeleton.bones:
                external_bones = external_skel.drawable.skeleton.bones

            if not drawable_xml.skeleton.bones:
                external_armature = dict_obj
        else:
            if not drawable_xml.skeleton.bones and ydd_skel is not None:
                external_bones = ydd_skel.bones

        drawable_obj = create_drawable_obj(
            drawable_xml,
            filepath,
            external_armature=external_armature,
            external_bones=external_bones,
            name=drawable_xml.hash,
            game=current_game(),
        )
        drawable_obj.parent = dict_obj

        if yld_xml is not None:
            cloth = next((c for c in yld_xml if c.name == drawable_xml.name), None)
            if cloth is not None:
                cloth_obj = create_character_cloth_mesh(cloth, drawable_obj, drawable_xml.skeleton.bones or external_bones)
                bounds_obj = create_character_cloth_bounds(cloth, external_armature or drawable_obj, drawable_xml.skeleton.bones or external_bones)
                bounds_obj.parent = cloth_obj
                cloth_obj.parent = drawable_obj

    return dict_obj


def create_armature_parent(name: str, skel_yft: Fragment, game: SollumzGame = SollumzGame.GTA):
    armature = bpy.data.armatures.new(f"{name}.skel")
    dict_obj = create_blender_object(SollumType.DRAWABLE_DICTIONARY, name, armature, game)

    create_drawable_skel(skel_yft.drawable.skeleton, dict_obj)

    if current_game() == SollumzGame.GTA:
        rot_limits = skel_yft.drawable.joints.rotation_limits
        if rot_limits:
            apply_rotation_limits(rot_limits, dict_obj)

    return dict_obj


def create_extra_skeleton_armature(name: str, extra_skel):
    armature = bpy.data.armatures.new(f"{name}.skel")
    dict_obj = create_blender_object(
        SollumType.DRAWABLE_DICTIONARY, name, armature, SollumzGame.RDR)
    
    bpy.context.view_layer.objects.active = dict_obj
    bpy.ops.object.mode_set(mode="EDIT")
    
    for bone_xml in extra_skel.bones:
        create_bpy_bone(bone_xml, dict_obj.data)

    bpy.ops.object.mode_set(mode="OBJECT")

    for bone_xml in extra_skel.bones:
        set_bone_properties(bone_xml, dict_obj.data)

    return dict_obj


def find_first_skel(ydd_xml: DrawableDictionary) -> Optional[Skeleton]:
    """Find first skeleton in ``ydd_xml``"""
    for drawable_xml in ydd_xml:
        if drawable_xml.skeleton.bones:
            return drawable_xml.skeleton



def make_yld_filepath(ydd_filepath: str) -> str:
    """Get the .yld.xml filepath at the provided ydd filepath."""
    ydd_dir = os.path.dirname(ydd_filepath)
    ydd_name = get_filename(ydd_filepath)

    path = os.path.join(ydd_dir, f"{ydd_name}.yld.xml")
    return path


def create_character_cloth_mesh(cloth: CharacterCloth, drawable_obj: Object, bones: list[Bone]) -> Object:
    controller = cloth.controller
    vertices = controller.vertices
    indices = controller.indices

    vertices = np.array(vertices)
    indices = np.array(indices).reshape((-1, 3))

    mesh = bpy.data.meshes.new(f"{cloth.name}.cloth")
    mesh.from_pydata(vertices, [], indices)
    obj = create_blender_object(SollumType.CHARACTER_CLOTH_MESH, f"{cloth.name}.cloth", mesh)

    pin_radius = controller.bridge.pin_radius_high
    weights = controller.bridge.vertex_weights_high
    inflation_scale = controller.bridge.inflation_scale_high
    mesh_to_cloth_map = np.array(controller.bridge.display_map_high)
    cloth_to_mesh_map = np.empty_like(mesh_to_cloth_map)
    cloth_to_mesh_map[mesh_to_cloth_map] = np.arange(len(mesh_to_cloth_map))
    pinned_vertices_count = controller.cloth_high.pinned_vertices_count
    vertices_count = len(controller.cloth_high.vertex_positions)

    has_pinned = pinned_vertices_count > 0
    has_pin_radius = len(pin_radius) > 0
    num_pin_radius_sets = len(pin_radius) // vertices_count
    has_weights = len(weights) > 0
    has_inflation_scale = len(inflation_scale) > 0

    char_cloth_props = drawable_obj.drawable_properties.char_cloth
    char_cloth_props.pin_radius_scale = controller.pin_radius_scale
    char_cloth_props.pin_radius_threshold = controller.pin_radius_threshold
    char_cloth_props.wind_scale = controller.wind_scale
    char_cloth_props.weight = controller.cloth_high.cloth_weight

    from ..ydr.cloth import ClothAttr, mesh_add_cloth_attribute

    if has_pinned:
        mesh_add_cloth_attribute(mesh, ClothAttr.PINNED)
    if has_pin_radius:
        mesh_add_cloth_attribute(mesh, ClothAttr.PIN_RADIUS)
        if num_pin_radius_sets > 4:
            logger.warning(f"Found {num_pin_radius_sets} pin radius sets, only up to 4 sets are supported!")
            num_pin_radius_sets = 4
        char_cloth_props.num_pin_radius_sets = num_pin_radius_sets
    if has_weights:
        mesh_add_cloth_attribute(mesh, ClothAttr.VERTEX_WEIGHT)
    if has_inflation_scale:
        mesh_add_cloth_attribute(mesh, ClothAttr.INFLATION_SCALE)

    for mesh_vert_index, cloth_vert_index in enumerate(mesh_to_cloth_map):
        mesh_vert_index = cloth_vert_index # NOTE: in character cloths both are the same?

        if has_pinned:
            pinned = cloth_vert_index < pinned_vertices_count
            mesh.attributes[ClothAttr.PINNED].data[mesh_vert_index].value = 1 if pinned else 0

        if has_pin_radius:
            pin_radii = [
                pin_radius[cloth_vert_index + (set_idx * vertices_count)]
                if set_idx < num_pin_radius_sets else 0.0
                for set_idx in range(4)
            ]
            mesh.attributes[ClothAttr.PIN_RADIUS].data[mesh_vert_index].color = pin_radii

        if has_weights:
            mesh.attributes[ClothAttr.VERTEX_WEIGHT].data[mesh_vert_index].value = weights[cloth_vert_index]

        if has_inflation_scale:
            mesh.attributes[ClothAttr.INFLATION_SCALE].data[mesh_vert_index].value = inflation_scale[cloth_vert_index]

    custom_edges = [e for e in (cloth.controller.cloth_high.custom_edges or []) if e.vertex0 != e.vertex1]
    if custom_edges:
        next_edge = len(mesh.edges)
        mesh.edges.add(len(custom_edges))
        for custom_edge in custom_edges:
            v0 = custom_edge.vertex0
            v1 = custom_edge.vertex1
            mesh.edges[next_edge].vertices = v0, v1
            next_edge += 1


    def _create_group(bone_index: int):
        if bones and bone_index < len(bones):
            bone_name = bones[bone_index].name
        else:
            bone_name = f"UNKNOWN_BONE.{bone_index}"

        return obj.vertex_groups.new(name=bone_name)

    vertex_groups_by_bone_idx = {}
    for vert_idx, binding in enumerate(controller.bindings):
        for weight, idx in zip(binding.weights, binding.indices):
            if weight == 0.0:
                continue

            bone_idx = controller.bone_indices[idx]
            if bone_idx not in vertex_groups_by_bone_idx:
                vertex_groups_by_bone_idx[bone_idx] = _create_group(bone_idx)

            vgroup = vertex_groups_by_bone_idx[bone_idx]
            vgroup.add((vert_idx,), weight, "ADD")

    if cloth.poses:
        # TODO(cloth): export poses
        num_poses = len(cloth.poses) // 2 // vertices_count
        poses = np.array(cloth.poses)[::2,:3]
        obj.show_only_shape_key = True
        obj.shape_key_add(name="Basis")
        for pose_idx in range(num_poses):
            sk = obj.shape_key_add(name=f"Pose#{pose_idx+1}")
            sk.points.foreach_set("co", poses[pose_idx*vertices_count:(pose_idx+1)*vertices_count].ravel())
        mesh.shape_keys.use_relative = False


    return obj

def create_character_cloth_bounds(cloth: CharacterCloth, armature_obj: Object, bones: list[Bone]) -> Object:
    bounds_obj = create_bound_composite(cloth.bounds)
    bounds_obj.name = f"{cloth.name}.cloth.bounds"

    for bound_obj, bone_id in zip(bounds_obj.children, cloth.bounds_bone_ids):
        bone_name = next((b.name for b in bones if b.tag == bone_id), None)
        assert bone_name is not None, "Cloth bound attached to non-existing bone."

        add_child_of_bone_constraint(bound_obj, armature_obj, bone_name)

    return bounds_obj
