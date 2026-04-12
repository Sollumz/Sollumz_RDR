import bpy
import random
from ...sollumz_operators import SOLLUMZ_OT_base
from ...sollumz_properties import ArchetypeType
from ...tools.meshhelper import get_min_vector_list, get_max_vector_list
from ...tools.blenderhelper import get_selected_vertices
from ..utils import get_selected_archetype, get_selected_room


class SOLLUMZ_OT_create_reflection_probe(SOLLUMZ_OT_base, bpy.types.Operator):
    """Add a reflection probe to the selected room"""
    bl_idname = "sollumz.createreflectionprobe"
    bl_label = "Create Reflection Probe"

    @classmethod
    def poll(cls, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype and selected_archetype.type == ArchetypeType.MLO

    def run(self, context):
        selected_archetype = get_selected_archetype(context)
        if not selected_archetype or not selected_archetype.selected_room:
            return False
        
        room = selected_archetype.selected_room
        probe = room.reflection_probes.add()
        probe.name = f"Probe.{len(room.reflection_probes)}"
        # Generate a random 64-bit hex GUID
        probe.guid = f"0x{random.getrandbits(64):X}"
        return True


class SOLLUMZ_OT_delete_reflection_probe(SOLLUMZ_OT_base, bpy.types.Operator):
    """Delete selected reflection probe(s) from the current room"""
    bl_idname = "sollumz.deletereflectionprobe"
    bl_label = "Delete Reflection Probe"

    @classmethod
    def poll(cls, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype and selected_archetype.selected_room and len(selected_archetype.selected_room.reflection_probes) > 0

    def run(self, context):
        selected_archetype = get_selected_archetype(context)
        if not selected_archetype or not selected_archetype.selected_room:
            return False

        room = selected_archetype.selected_room
        if len(room.reflection_probes) == 0:
            return False

        # Get the current active index
        current_index = room.reflection_probes_active_index
        if current_index < 0 or current_index >= len(room.reflection_probes):
            return False
        
        # Remove the probe
        room.reflection_probes.remove(current_index)
        
        # Set the new active index (go to the previous one, or stay at 0 if it was the first)
        new_index = max(current_index - 1, 0)
        if len(room.reflection_probes) > 0:
            room.reflection_probes_active_index = min(new_index, len(room.reflection_probes) - 1)
        
        return True


class SOLLUMZ_OT_set_reflection_probe_extents_from_selection(SOLLUMZ_OT_base, bpy.types.Operator):
    """Set reflection probe extents from selected vertices"""
    bl_idname = "sollumz.setreflectionprobeextentsfromselection"
    bl_label = "Set Extents From Selection"

    @classmethod
    def poll(cls, context):
        selected_archetype = get_selected_archetype(context)
        selected_room = get_selected_room(context)
        return (
            selected_archetype and selected_archetype.type == ArchetypeType.MLO and
            selected_room and len(selected_room.reflection_probes) > 0 and
            context.active_object and
            context.active_object.mode == "EDIT"
        )

    def run(self, context):
        selected_archetype = get_selected_archetype(context)
        selected_room = get_selected_room(context)
        
        if selected_room.reflection_probes_active_index >= len(selected_room.reflection_probes):
            self.message("No active reflection probe!")
            return False
        
        selected_probe = selected_room.reflection_probes[selected_room.reflection_probes_active_index]
        
        selected_verts = []
        for obj in context.objects_in_mode:
            selected_verts.extend(get_selected_vertices(obj))
        
        if len(selected_verts) < 2:
            self.message("You must select at least 2 vertices!")
            return False
        
        if not selected_archetype.asset:
            self.message("You must set an asset for the archetype.")
            return False

        pos = selected_archetype.asset.location

        selected_probe.max_extents = get_max_vector_list(selected_verts) - pos
        selected_probe.min_extents = get_min_vector_list(selected_verts) - pos

        return True


class SOLLUMZ_OT_set_reflection_probe_influence_from_selection(SOLLUMZ_OT_base, bpy.types.Operator):
    """Set reflection probe influence extents from selected vertices"""
    bl_idname = "sollumz.setreflectionprobeinfluencefromselection"
    bl_label = "Set Influence From Selection"

    @classmethod
    def poll(cls, context):
        selected_archetype = get_selected_archetype(context)
        selected_room = get_selected_room(context)
        return (
            selected_archetype and selected_archetype.type == ArchetypeType.MLO and
            selected_room and len(selected_room.reflection_probes) > 0 and
            context.active_object and
            context.active_object.mode == "EDIT"
        )

    def run(self, context):
        selected_archetype = get_selected_archetype(context)
        selected_room = get_selected_room(context)
        
        if selected_room.reflection_probes_active_index >= len(selected_room.reflection_probes):
            self.message("No active reflection probe!")
            return False
        
        selected_probe = selected_room.reflection_probes[selected_room.reflection_probes_active_index]
        
        selected_verts = []
        for obj in context.objects_in_mode:
            selected_verts.extend(get_selected_vertices(obj))
        
        if len(selected_verts) < 2:
            self.message("You must select at least 2 vertices!")
            return False
        
        if not selected_archetype.asset:
            self.message("You must set an asset for the archetype.")
            return False

        # Calculate the influence extents from the bounding box of selected vertices
        min_vert = get_min_vector_list(selected_verts)
        max_vert = get_max_vector_list(selected_verts)
        
        # Store as a symmetric box (size in each dimension)
        influence = max_vert - min_vert
        selected_probe.influence_extents = influence

        return True
