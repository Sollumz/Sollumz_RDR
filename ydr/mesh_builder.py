from ..sollumz_properties import SollumzGame
import bpy
import numpy as np
from numpy.typing import NDArray
from traceback import format_exc
from ..tools.meshhelper import (
    create_uv_attr,
    create_color_attr,
    flip_uvs,
)
from mathutils import Vector
from .. import logger


class MeshBuilder:
    """Builds a bpy mesh from a structured numpy vertex array"""

    def __init__(self, name: str, vertex_arr: NDArray, ind_arr: NDArray[np.uint], mat_inds: NDArray[np.uint], drawable_mats: list[bpy.types.Material]):
        if "Position" not in vertex_arr.dtype.names:
            raise ValueError("Vertex array have a 'Position' field!")

        if ind_arr.ndim > 1 or ind_arr.size % 3 != 0:
            raise ValueError(
                "Indices array should be a 1D array in triangle order and it's size should be divisble by 3!")

        # Triangles using the same vertex 2+ times are not valid topology for Blender and can potentially crash/hang
        # Blender before we have a chance to call `Mesh.validate()`. Some vanilla models and, often, modded models have
        # some of these degenerate triangles, so remove them.
        faces = ind_arr.reshape((int(ind_arr.size / 3), 3))
        invalid_faces_mask = (faces[:,0] == faces[:,1]) | (faces[:,0] == faces[:,2]) | (faces[:,1] == faces[:,2])
        ind_arr = faces[~invalid_faces_mask].reshape((-1,))
        mat_inds = mat_inds[~invalid_faces_mask]

        self.vertex_arr = vertex_arr
        self.ind_arr = ind_arr
        self.mat_inds = mat_inds

        self.name = name
        self.materials = drawable_mats

        self._has_normals = "Normal" in vertex_arr.dtype.names
        self._has_uvs = any("TexCoord" in name for name in vertex_arr.dtype.names)
        self._has_colors = any("Colour" in name for name in vertex_arr.dtype.names)

    def build(self, game: str):
        mesh = bpy.data.meshes.new(self.name)
        vert_pos = self.vertex_arr["Position"]
        faces = self.ind_arr.reshape((int(self.ind_arr.size / 3), 3))

        try:
            mesh.from_pydata(vert_pos, [], faces)
        except Exception:
            logger.error(
                f"Error during creation of fragment {self.name}:\n{format_exc()}\nEnsure the mesh data is not malformed.")
            return mesh

        self.create_mesh_materials(mesh)

        if self._has_normals:
            self.set_mesh_normals(mesh)

        if self._has_uvs:
            self.set_mesh_uvs(mesh)

        if self._has_colors:
            self.set_mesh_vertex_colors(mesh)

        mesh.validate()

        return mesh

    def create_mesh_materials(self, mesh: bpy.types.Mesh):
        drawable_mat_inds = np.unique(self.mat_inds)
        # Map drawable material indices to model material indices
        model_mat_inds = np.zeros(
            np.max(drawable_mat_inds) + 1, dtype=np.uint32)

        for mat_ind in drawable_mat_inds:
            mesh.materials.append(self.materials[mat_ind])
            model_mat_inds[mat_ind] = len(mesh.materials) - 1

        # Set material indices via attributes
        mesh.attributes.new("material_index", type="INT", domain="FACE")
        mesh.attributes["material_index"].data.foreach_set(
            "value", model_mat_inds[self.mat_inds])

    def set_mesh_normals(self, mesh: bpy.types.Mesh):
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))

        normals_normalized = [Vector(n[:3]).normalized() for n in self.vertex_arr["Normal"]]
        mesh.normals_split_custom_set_from_vertices(normals_normalized)

        if bpy.app.version < (4, 1, 0):
            # needed to use custom split normals pre-4.1
            mesh.use_auto_smooth = True

    def set_mesh_uvs(self, mesh: bpy.types.Mesh):
        uv_attrs = [name for name in self.vertex_arr.dtype.names if name.startswith("TexCoord")]

        for attr_name in uv_attrs:
            uvmap_idx = int(attr_name[8:])
            uvs = self.vertex_arr[attr_name]
            flip_uvs(uvs)

            create_uv_attr(mesh, uvmap_idx, initial_values=uvs[self.ind_arr])

    def set_mesh_vertex_colors(self, mesh: bpy.types.Mesh):
        color_attrs = [name for name in self.vertex_arr.dtype.names if name.startswith("Colour")]

        for attr_name in color_attrs:
            color_idx = int(attr_name[6:])
            colors = self.vertex_arr[attr_name] / 255

            create_color_attr(mesh, color_idx, initial_values=colors[self.ind_arr])

    def create_vertex_groups(self, obj: bpy.types.Object, bones: list[bpy.types.Bone], game: SollumzGame = SollumzGame.GTA, bone_mapping = None):
        vertex_groups: dict[int, bpy.types.VertexGroup] = {}

        def _try_get_bone_by_tag(tag: int) -> bpy.types.Bone | None:
            for bone in bones:
                bone_tag = bone.bone_properties.tag
                if bone_tag == tag:
                    return bone

            return None


        def create_group(bone_index: int):
            bone_name = f"UNKNOWN_BONE.{bone_index}"

            if game == SollumzGame.GTA:
                if bone_index == 99999:
                    from .cloth_char import CLOTH_CHAR_VERTEX_GROUP_NAME
                    bone_name = CLOTH_CHAR_VERTEX_GROUP_NAME
                elif bones and bone_index < len(bones):
                    bone_name = bones[bone_index].name
            elif game == SollumzGame.RDR:
                if bone_mapping:
                    if bone_index > len(bone_mapping):
                        raise Exception(f"Unable to get bone mapping as index {bone_index} is out of range in {bone_mapping}")
                    tag = bone_mapping[bone_index]
                    bone = _try_get_bone_by_tag(tag)
                    if bone:
                        bone_name = bone.name
                    else:
                        bone_name = f"BONE.#{tag}"
                else:
                    if bones and bone_index < len(bones):
                        bone_name = bones[bone_index].name

            vgroup = obj.vertex_groups.get(bone_name, None)
            if vgroup:
                return vgroup
            else:
                return obj.vertex_groups.new(name=bone_name)

        def create_weights(weights, indices):
            for vert_ind, bone_inds in enumerate(indices):
                for i, bone_ind in enumerate(bone_inds):
                    weight = weights[vert_ind][i]

                    if weight == 0 and bone_ind == 0:
                        continue

                    if bone_ind not in vertex_groups:
                        vertex_groups[bone_ind] = create_group(bone_ind)

                    vgroup = vertex_groups[bone_ind]

                    vgroup.add((vert_ind,), weight, "ADD")
    
        weights = self.vertex_arr["BlendWeights"] / 255
        indices = self.vertex_arr["BlendIndices"]
        create_weights(weights, indices)

        if game == SollumzGame.RDR:
            weights2 = self.vertex_arr["BlendWeights1"] / 255
            indices2 = self.vertex_arr["BlendIndices1"]
            create_weights(weights2, indices2)
