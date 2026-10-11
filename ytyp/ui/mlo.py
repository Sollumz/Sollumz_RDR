import bpy
from .ytyp import YtypFlagsPanel
from ...tools.blenderhelper import tag_redraw
from ...tabbed_panels import TabbedPanelHelper, TabPanel
from ..properties.ytyp import ArchetypeType
from ...sollumz_properties import SollumzGame
from ..properties.mlo import RoomProperties
from ..utils import get_selected_archetype, get_selected_room, get_selected_portal, get_selected_ytyp
from .archetype import ArchetypeChildPanel
from ...shared.multiselection import (
    MultiSelectUIListMixin,
    multiselect_ui_draw_list,
)
from ..operators import ytyp as ytyp_ops


class SOLLUMZ_PT_MLO_PANEL(ArchetypeChildPanel, TabbedPanelHelper, bpy.types.Panel):
    bl_label = "MLO"
    bl_idname = "SOLLUMZ_PT_MLO_PANEL"
    bl_options = {"HIDE_HEADER"}

    default_tab = "SOLLUMZ_PT_ROOM_PANEL"

    bl_order = 3

    @classmethod
    def poll(cls, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype is not None and selected_archetype.type == ArchetypeType.MLO

    def draw_before(self, context: bpy.types.Context):
        self.layout.label(text="MLO")


class MloChildTabPanel(TabPanel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"HIDE_HEADER"}
    bl_parent_id = SOLLUMZ_PT_MLO_PANEL.bl_idname
    bl_category = SOLLUMZ_PT_MLO_PANEL.bl_category

    parent_tab_panel = SOLLUMZ_PT_MLO_PANEL

    @classmethod
    def _set_active_tab(cls, tab_id: str):
        super()._set_active_tab(tab_id)
        bpy.context.scene['_sollumz_ytyp_geometry_tab'] = tab_id
        tag_redraw(bpy.context, space_type='VIEW_3D', region_type='WINDOW')
        tag_redraw(bpy.context, space_type='VIEW_3D', region_type='UI')


class SOLLUMZ_UL_ROOM_LIST(MultiSelectUIListMixin, bpy.types.UIList):
    bl_idname = "SOLLUMZ_UL_ROOM_LIST"
    default_item_icon = "CUBE"
    multiselect_operator = ytyp_ops.SOLLUMZ_OT_archetype_select_mlo_room.bl_idname


class SOLLUMZ_PT_ROOM_PANEL(MloChildTabPanel, bpy.types.Panel):
    bl_label = "Rooms"
    bl_idname = "SOLLUMZ_PT_ROOM_PANEL"

    icon = "CUBE"

    bl_order = 0

    @classmethod
    def poll_tab(cls, context):
        selected_archetype = get_selected_archetype(context)

        return selected_archetype.type == ArchetypeType.MLO

    def draw(self, context):
        # TODO(multiselect): think how we should manage disabling panels when multiple selection enabled
        self.layout.enabled = not get_selected_ytyp(context).archetypes.has_multiple_selection
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        selected_archetype = get_selected_archetype(context)

        list_col, _ = multiselect_ui_draw_list(
            self.layout, selected_archetype.rooms,
            "sollumz.createroom", "sollumz.deleteroom",
            SOLLUMZ_UL_ROOM_LIST, SOLLUMZ_MT_rooms_list_context_menu,
            "tool_panel"
        )

        list_col.operator("sollumz.createlimboroom")

        row = layout.row()
        row.use_property_split = False
        row.prop(context.scene, "show_room_gizmo")

        if not selected_archetype.asset and context.scene.show_room_gizmo:
            row = layout.row()
            row.label(
                text="Handles use local coordinates until an object is linked.")

        if len(selected_archetype.rooms) == 0:
            return

        # has_multiple_selection = selected_archetype.rooms.has_multiple_selection
        selection = selected_archetype.rooms.selection
        # active = selected_archetype.rooms.active_item

        layout.separator()
        for prop_name in RoomProperties.__annotations__:
            # Room-local probes are edited in the RDR Volumes and Probes panel,
            # rather than through the scalar multi-selection property proxies.
            if prop_name in ["flags", "id", "uuid", "reflection_probes", "reflection_probe_index"]:
                continue
            layout.prop(selection.owner, getattr(selection.propnames, prop_name))

        list_col.operator(
            "sollumz.setroomboundsfromselection", icon="GROUP_VERTEX")


class SOLLUMZ_MT_rooms_list_context_menu(bpy.types.Menu):
    bl_label = "Rooms Specials"
    bl_idname = "SOLLUMZ_MT_rooms_list_context_menu"

    def draw(self, _context):
        layout = self.layout
        op0 = layout.operator(ytyp_ops.SOLLUMZ_OT_archetype_select_all_mlo_room.bl_idname, text="Select All")
        op1 = layout.operator(ytyp_ops.SOLLUMZ_OT_archetype_select_invert_mlo_room.bl_idname, text="Invert")
        if (filter_opts := SOLLUMZ_UL_ROOM_LIST.last_filter_options.get("rooms_tool_panel", None)):
            filter_opts.apply_to_operator(op0)
            filter_opts.apply_to_operator(op1)


class SOLLUMZ_PT_ROOM_FLAGS_PANEL(YtypFlagsPanel, bpy.types.Panel):
    bl_idname = "SOLLUMZ_PT_ROOM_FLAGS_PANEL"
    bl_label = "Room Flags"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = SOLLUMZ_PT_ROOM_PANEL.bl_idname
    bl_category = SOLLUMZ_PT_ROOM_PANEL.bl_category

    @classmethod
    def poll(cls, context):
        return get_selected_room(context) is not None

    def get_flags_active(self, context):
        selected_room = get_selected_room(context)
        return selected_room.flags

    def get_flags_selection(self, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype.rooms.selection.flags

    def draw(self, context):
        # TODO(multiselect): think how we should manage disabling panels when multiple selection enabled
        ytyp = get_selected_ytyp(context)
        self.layout.enabled = not ytyp.archetypes.has_multiple_selection
        super().draw(context)


class SOLLUMZ_UL_PORTAL_LIST(MultiSelectUIListMixin, bpy.types.UIList):
    bl_idname = "SOLLUMZ_UL_PORTAL_LIST"
    default_item_icon = "OUTLINER_OB_LIGHTPROBE"
    name_editable = False
    multiselect_operator = ytyp_ops.SOLLUMZ_OT_archetype_select_mlo_portal.bl_idname

    def filter_items(self, context, data, propname):
        # NOTE: for some unknown reason, the Blender default filter by name does not work with this list. As soon as
        # you type something, all portals disappear. Even though, it works just fine in other lists like rooms or
        # entity sets...
        # So just override the filter but with our implementation of the default filter...
        multiselect_collection_name = propname[:-1]  # remove '_' suffix
        collection = getattr(data, multiselect_collection_name)
        from ...shared.multiselection import _default_filter_items
        return _default_filter_items(collection, self.filter_name, self.use_filter_sort_reverse, self.use_filter_sort_alpha)


class SOLLUMZ_PT_PORTAL_PANEL(MloChildTabPanel, bpy.types.Panel):
    bl_label = "Portals"
    bl_idname = "SOLLUMZ_PT_PORTAL_PANEL"

    icon = "OUTLINER_OB_LIGHTPROBE"

    bl_order = 1

    @classmethod
    def poll_tab(cls, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype.type == ArchetypeType.MLO

    def draw(self, context):
        # TODO(multiselect): think how we should manage disabling panels when multiple selection enabled
        self.layout.enabled = not get_selected_ytyp(context).archetypes.has_multiple_selection
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        selected_archetype = get_selected_archetype(context)

        list_col, _ = multiselect_ui_draw_list(
            self.layout, selected_archetype.portals,
            "sollumz.createportal", "sollumz.deleteportal",
            SOLLUMZ_UL_PORTAL_LIST, SOLLUMZ_MT_portals_list_context_menu,
            "tool_panel"
        )

        row = list_col.row()
        row.operator("sollumz.createportalfromselection",
                     text="Create From Vertices", icon="GROUP_VERTEX")
        row.prop(context.scene, "sollumz_add_portal_room_from",
                 icon="CUBE", text="")

        row.label(text="", icon="FORWARD")

        row.prop(context.scene, "sollumz_add_portal_room_to",
                 icon="CUBE", text="")

        list_col.separator(factor=2)

        row = list_col.row(align=True)
        row.operator("sollumz.updateportalfromselection",
                     text="Update From Vertices", icon="GROUP_VERTEX")
        row.operator("sollumz.flipportal",
                     text="Flip Direction", icon="LOOP_FORWARDS")

        row = layout.row()
        row.use_property_split = False
        row.prop(context.scene, "show_portal_gizmo")

        if not selected_archetype.asset and context.scene.show_portal_gizmo:
            row = layout.row()
            row.label(text="Handles use local coordinates until an object is linked.")

        if len(selected_archetype.portals) == 0:
            return

        # has_multiple_selection = selected_archetype.portals.has_multiple_selection
        selection = selected_archetype.portals.selection
        # active = selected_archetype.portals.active_item

        layout.separator()

        layout.prop(selection.owner, selection.propnames.corner1)
        layout.prop(selection.owner, selection.propnames.corner2)
        layout.prop(selection.owner, selection.propnames.corner3)
        layout.prop(selection.owner, selection.propnames.corner4)

        layout.separator()

        row = layout.row()
        row.prop(selection.owner, selection.propnames.room_from_id)
        row.operator("sollumz.search_portal_room_from",
                     text="", icon="VIEWZOOM")
        row = layout.row()
        row.prop(selection.owner, selection.propnames.room_to_id)
        row.operator("sollumz.search_portal_room_to", text="", icon="VIEWZOOM")

        layout.separator()
        layout.prop(selection.owner, selection.propnames.mirror_priority)
        layout.prop(selection.owner, selection.propnames.opacity)
        layout.prop(selection.owner, selection.propnames.audio_occlusion)
        if get_selected_ytyp(context).game == SollumzGame.RDR:
            for prop in ('rdr_7c096c2e', 'rdr_91171666', 'rdr_96816ddf', 'rdr_0854fdee'):
                layout.prop(get_selected_portal(context), prop)


class SOLLUMZ_MT_portals_list_context_menu(bpy.types.Menu):
    bl_label = "Portals Specials"
    bl_idname = "SOLLUMZ_MT_portals_list_context_menu"

    def draw(self, _context):
        layout = self.layout
        op0 = layout.operator(ytyp_ops.SOLLUMZ_OT_archetype_select_all_mlo_portal.bl_idname, text="Select All")
        op1 = layout.operator(ytyp_ops.SOLLUMZ_OT_archetype_select_invert_mlo_portal.bl_idname, text="Invert")
        if (filter_opts := SOLLUMZ_UL_PORTAL_LIST.last_filter_options.get("portals_tool_panel", None)):
            filter_opts.apply_to_operator(op0)
            filter_opts.apply_to_operator(op1)


class SOLLUMZ_PT_PORTAL_FLAGS_PANEL(YtypFlagsPanel, bpy.types.Panel):
    bl_idname = "SOLLUMZ_PT_PORTAL_FLAGS_PANEL"
    bl_label = "Portal Flags"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = SOLLUMZ_PT_PORTAL_PANEL.bl_idname
    bl_category = SOLLUMZ_PT_PORTAL_PANEL.bl_category

    @classmethod
    def poll(cls, context):
        return get_selected_portal(context) is not None

    def get_flags_active(self, context):
        selected_portal = get_selected_portal(context)
        return selected_portal.flags

    def get_flags_selection(self, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype.portals.selection.flags

    def draw(self, context):
        # TODO(multiselect): think how we should manage disabling panels when multiple selection enabled
        ytyp = get_selected_ytyp(context)
        self.layout.enabled = not ytyp.archetypes.has_multiple_selection
        super().draw(context)


class SOLLUMZ_UL_TIMECYCLE_MODIFIER_LIST(MultiSelectUIListMixin, bpy.types.UIList):
    bl_idname = "SOLLUMZ_UL_TIMECYCLE_MODIFIER_LIST"
    default_item_icon = "MOD_TIME"
    multiselect_operator = ytyp_ops.SOLLUMZ_OT_archetype_select_mlo_tcm.bl_idname


class SOLLUMZ_PT_TIMECYCLE_MODIFIER_PANEL(MloChildTabPanel, bpy.types.Panel):
    bl_label = "Timecycle Modifiers"
    bl_idname = "SOLLUMZ_PT_TIMECYCLE_MODIFIER_PANEL"

    icon = "MOD_TIME"

    bl_order = 3

    @classmethod
    def poll_tab(cls, context):
        selected_archetype = get_selected_archetype(context)

        return (selected_archetype.type == ArchetypeType.MLO
                and get_selected_ytyp(context).game == SollumzGame.GTA)

    def draw(self, context):
        # TODO(multiselect): think how we should manage disabling panels when multiple selection enabled
        self.layout.enabled = not get_selected_ytyp(context).archetypes.has_multiple_selection
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        selected_archetype = get_selected_archetype(context)

        multiselect_ui_draw_list(
            self.layout, selected_archetype.timecycle_modifiers,
            "sollumz.createtimecyclemodifier", "sollumz.deletetimecyclemodifier",
            SOLLUMZ_UL_TIMECYCLE_MODIFIER_LIST, SOLLUMZ_MT_timecycle_modifiers_list_context_menu,
            "tool_panel"
        )

        row = layout.row()
        row.use_property_split = False
        row.prop(context.scene, "show_mlo_tcm_gizmo")

        if not selected_archetype.asset and context.scene.show_mlo_tcm_gizmo:
            row = layout.row()
            row.label(text="Handles use local coordinates until an object is linked.")

        if len(selected_archetype.timecycle_modifiers) == 0:
            return

        # has_multiple_selection = selected_archetype.timecycle_modifiers.has_multiple_selection
        selection = selected_archetype.timecycle_modifiers.selection
        # active = selected_archetype.timecycle_modifiers.active_item

        layout.separator()

        layout.prop(selection.owner, selection.propnames.name)
        layout.prop(selection.owner, selection.propnames.sphere_center)
        layout.prop(selection.owner, selection.propnames.sphere_radius)
        layout.prop(selection.owner, selection.propnames.percentage)
        layout.prop(selection.owner, selection.propnames.range)
        layout.prop(selection.owner, selection.propnames.start_hour)
        layout.prop(selection.owner, selection.propnames.end_hour)


class SOLLUMZ_MT_timecycle_modifiers_list_context_menu(bpy.types.Menu):
    bl_label = "Timecycle Modifiers Specials"
    bl_idname = "SOLLUMZ_MT_timecycle_modifiers_list_context_menu"

    def draw(self, _context):
        layout = self.layout
        op0 = layout.operator(ytyp_ops.SOLLUMZ_OT_archetype_select_all_mlo_tcm.bl_idname, text="Select All")
        op1 = layout.operator(ytyp_ops.SOLLUMZ_OT_archetype_select_invert_mlo_tcm.bl_idname, text="Invert")
        if (filter_opts := SOLLUMZ_UL_TIMECYCLE_MODIFIER_LIST.last_filter_options.get("timecycle_modifiers_tool_panel", None)):
            filter_opts.apply_to_operator(op0)
            filter_opts.apply_to_operator(op1)


class SOLLUMZ_PT_MLO_FLAGS_PANEL(MloChildTabPanel, YtypFlagsPanel, bpy.types.Panel):
    bl_idname = "SOLLUMZ_PT_MLO_FLAGS_PANEL"
    bl_label = "MLO Flags"

    icon = "BOOKMARKS"

    bl_order = 4

    @classmethod
    def poll_tab(cls, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype.type == ArchetypeType.MLO

    def get_flags_active(self, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype.mlo_flags

    def get_flags_selection(self, context):
        selected_ytyp = get_selected_ytyp(context)
        return selected_ytyp.archetypes.selection.mlo_flags


class SOLLUMZ_UL_RDR_MLO_ITEMS(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'name', text='', emboss=False, icon='CUBE')


class RdrMloVolumesPanelHelper:
    @classmethod
    def poll_tab(cls, context):
        ytyp = get_selected_ytyp(context)
        archetype = get_selected_archetype(context)
        return (ytyp is not None and ytyp.game == SollumzGame.RDR
                and archetype is not None and archetype.type == ArchetypeType.MLO)

    def draw_gizmo_toggle(self, layout, context):
        row = layout.row()
        row.use_property_split = False
        row.prop(context.scene, self.gizmo_toggle)

    def draw_collection(self, layout, owner, collection_name, index_name, kind, label, props):
        layout.enabled = not get_selected_ytyp(bpy.context).archetypes.has_multiple_selection
        layout.use_property_split = True
        layout.use_property_decorate = False
        box = layout.box()
        box.label(text=label)
        row = box.row()
        row.template_list('SOLLUMZ_UL_RDR_MLO_ITEMS', collection_name, owner, collection_name,
                          owner, index_name, rows=2)
        col = row.column(align=True)
        col.operator('sollumz.add_rdr_mlo_item', text='', icon='ADD').kind = kind
        col.operator('sollumz.remove_rdr_mlo_item', text='', icon='REMOVE').kind = kind
        collection = getattr(owner, collection_name)
        index = getattr(owner, index_name)
        if index < len(collection):
            item = collection[index]
            for prop in props:
                box.prop(item, prop)


class SOLLUMZ_PT_RDR_MLO_VOLUMES_PANEL(RdrMloVolumesPanelHelper, MloChildTabPanel, bpy.types.Panel):
    bl_label = 'Main Activation'
    bl_idname = 'SOLLUMZ_PT_RDR_MLO_VOLUMES_PANEL'
    gizmo_toggle = 'show_main_activation_gizmo'
    icon = 'SPHERE'
    bl_order = 6

    def draw(self, context):
        self.draw_gizmo_toggle(self.layout, context)
        layout = self.layout
        layout.enabled = not get_selected_ytyp(context).archetypes.has_multiple_selection
        layout.use_property_split = True
        layout.use_property_decorate = False
        archetype = get_selected_archetype(context)
        layout.prop(archetype, 'uses_activation_volumes')
        for prop in ('center', 'radius', 'flags'):
            layout.prop(archetype.main_activation_volume, prop)


class SOLLUMZ_PT_RDR_MLO_EXTRA_VOLUMES_PANEL(RdrMloVolumesPanelHelper, MloChildTabPanel, bpy.types.Panel):
    bl_label = 'Extra Activation'
    bl_idname = 'SOLLUMZ_PT_RDR_MLO_EXTRA_VOLUMES_PANEL'
    gizmo_toggle = 'show_extra_activation_gizmo'
    icon = 'SPHERE'
    bl_order = 7

    def draw(self, context):
        self.draw_gizmo_toggle(self.layout, context)
        archetype = get_selected_archetype(context)
        self.draw_collection(self.layout, archetype, 'extra_activation_volumes', 'extra_activation_volume_index',
                             'EXTRA', 'Extra Activation Spheres', ('center', 'radius', 'flags'))


class SOLLUMZ_PT_RDR_MLO_TIMECYCLE_VOLUMES_PANEL(RdrMloVolumesPanelHelper, MloChildTabPanel, bpy.types.Panel):
    bl_label = 'Timecycle Volumes'
    bl_idname = 'SOLLUMZ_PT_RDR_MLO_TIMECYCLE_VOLUMES_PANEL'
    gizmo_toggle = 'show_timecycle_volume_gizmo'
    icon = 'MOD_TIME'
    bl_order = 8

    def draw(self, context):
        self.draw_gizmo_toggle(self.layout, context)
        archetype = get_selected_archetype(context)
        self.draw_collection(self.layout, archetype, 'timecycle_volumes', 'timecycle_volume_index', 'TCV',
                             'Timecycle Volumes', ('center', 'orientation', 'scale', 'vol_type',
                                                  'percentage', 'range', 'start_hour', 'end_hour'))


class SOLLUMZ_PT_RDR_MLO_PROBES_PANEL(RdrMloVolumesPanelHelper, MloChildTabPanel, bpy.types.Panel):
    bl_label = 'Reflection Probes'
    bl_idname = 'SOLLUMZ_PT_RDR_MLO_PROBES_PANEL'
    gizmo_toggle = 'show_reflection_probe_gizmo'
    icon = 'OUTLINER_OB_LIGHTPROBE'
    bl_order = 9

    def draw(self, context):
        self.draw_gizmo_toggle(self.layout, context)
        room = get_selected_room(context)
        if room is None:
            self.layout.label(text='Select a room to edit its reflection probes.')
            return
        self.draw_collection(self.layout, room, 'reflection_probes', 'reflection_probe_index', 'PROBE',
                             f'Reflection Probes: {room.name}', ('min_extents', 'max_extents', 'rotation',
                                 'center_offset', 'influence_extents', 'probe_priority', 'guid'))
        if room.reflection_probes:
            self.layout.operator('sollumz.generate_rdr_guid', icon='FILE_REFRESH').kind = 'PROBE'
