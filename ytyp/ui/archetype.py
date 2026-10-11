import bpy
from .ytyp import YtypFlagsPanel
from ...tools.blenderhelper import tag_redraw
from ...tabbed_panels import TabbedPanelHelper, TabPanel
from ...sollumz_properties import AssetType, ArchetypeType, SollumzGame
from ..utils import get_selected_archetype, get_selected_ytyp
from .ytyp import YtypToolChildPanel
from ...shared.multiselection import (
    MultiSelectUITimeFlagsPanel,
)


class SOLLUMZ_PT_ARCHETYPE_TABS_PANEL(YtypToolChildPanel, TabbedPanelHelper, bpy.types.Panel):
    bl_label = "Archetype"
    bl_idname = "SOLLUMZ_PT_ARCHETYPE_TABS_PANEL"
    bl_options = {"HIDE_HEADER"}

    default_tab = "SOLLUMZ_PT_ARCHETYPE_PANEL"

    bl_order = 2

    @classmethod
    def poll(cls, context):
        return get_selected_archetype(context) is not None

    def draw_before(self, context: bpy.types.Context):
        self.layout.separator()


class ArchetypeChildTabPanel(TabPanel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"HIDE_HEADER"}
    bl_parent_id = SOLLUMZ_PT_ARCHETYPE_TABS_PANEL.bl_idname
    bl_category = SOLLUMZ_PT_ARCHETYPE_TABS_PANEL.bl_category

    parent_tab_panel = SOLLUMZ_PT_ARCHETYPE_TABS_PANEL

    @classmethod
    def _set_active_tab(cls, tab_id: str):
        super()._set_active_tab(tab_id)
        bpy.context.scene['_sollumz_ytyp_geometry_tab'] = tab_id
        tag_redraw(bpy.context, space_type='VIEW_3D', region_type='WINDOW')
        tag_redraw(bpy.context, space_type='VIEW_3D', region_type='UI')


class ArchetypeChildPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = SOLLUMZ_PT_ARCHETYPE_TABS_PANEL.bl_idname
    bl_category = SOLLUMZ_PT_ARCHETYPE_TABS_PANEL.bl_category


class SOLLUMZ_PT_ARCHETYPE_PANEL(ArchetypeChildTabPanel, bpy.types.Panel):
    bl_label = "Archetype"
    bl_idname = "SOLLUMZ_PT_ARCHETYPE_PANEL"

    icon = "SEQ_STRIP_META"

    bl_order = 0

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        ytyp = get_selected_ytyp(context)
        selection = ytyp.archetypes.selection
        active = ytyp.archetypes.active_item
        layout.prop(selection.owner, selection.propnames.type)
        layout.prop(selection.owner, selection.propnames.name)
        if ytyp.game == SollumzGame.RDR:
             layout.prop(selection.owner, selection.propnames.load_flags)
             layout.prop(selection.owner, selection.propnames.avoidanceflags)
        layout.prop(selection.owner, selection.propnames.special_attribute)
        if ytyp.game == SollumzGame.RDR and active.asset_type == AssetType.ASSETLESS:
            row = layout.row()
            row.enabled = not ytyp.archetypes.has_multiple_selection
            row.prop(active, 'rdr_asset_type_none')

        if active.asset_type != AssetType.ASSETLESS:
            layout.prop(selection.owner, selection.propnames.texture_dictionary)
            layout.prop(selection.owner, selection.propnames.clip_dictionary)
            layout.prop(selection.owner, selection.propnames.drawable_dictionary)
            layout.prop(selection.owner, selection.propnames.physics_dictionary)
            layout.prop(selection.owner, selection.propnames.hd_texture_dist)
            layout.prop(selection.owner, selection.propnames.lod_dist)

        layout.prop(selection.owner, selection.propnames.asset_type)
        layout.prop(selection.owner, selection.propnames.asset_name)
        if ytyp.game == SollumzGame.RDR:
            layout.prop(selection.owner, selection.propnames.guid)
            layout.prop(selection.owner, selection.propnames.unknown_1)

        row = layout.row()
        row.enabled = not ytyp.archetypes.has_multiple_selection
        row.prop(active, "asset", text="Linked Object")


class SOLLUMZ_PT_ARCHETYPE_BOUNDS_PANEL(ArchetypeChildTabPanel, bpy.types.Panel):
    bl_label = 'Bounds and Viewport'
    bl_idname = 'SOLLUMZ_PT_ARCHETYPE_BOUNDS_PANEL'
    icon = 'PIVOT_BOUNDBOX'
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        archetype = get_selected_archetype(context)
        layout.enabled = not get_selected_ytyp(context).archetypes.has_multiple_selection
        layout.use_property_split = True
        layout.use_property_decorate = False
        row = layout.row()
        row.use_property_split = False
        row.prop(context.scene, 'show_archetype_bounds_gizmo')
        layout.prop(archetype, 'bounds_from_asset')
        layout.operator('sollumz.archetype_calculate_bounds')
        col = layout.column()
        col.enabled = not (archetype.asset and archetype.bounds_from_asset)
        for prop in ('bb_min', 'bb_max', 'bs_center', 'bs_radius'):
            col.prop(archetype, prop)
        layout.label(text='Handles use the linked object local space.')


class SOLLUMZ_PT_ARCHETYPE_FLAGS_PANEL(ArchetypeChildTabPanel, YtypFlagsPanel, bpy.types.Panel):
    bl_idname = "SOLLUMZ_PT_ARCHETYPE_FLAGS_PANEL"
    icon = "BOOKMARKS"

    bl_order = 2

    def get_flags_active(self, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype.flags

    def get_flags_selection(self, context):
        selected_ytyp = get_selected_ytyp(context)
        return selected_ytyp.archetypes.selection.flags


class SOLLUMZ_PT_TIME_FlAGS_PANEL(ArchetypeChildPanel, MultiSelectUITimeFlagsPanel, bpy.types.Panel):
    bl_idname = "SOLLUMZ_PT_TIME_FLAGS_PANEL"
    bl_label = "Time Flags"
    select_operator = "sollumz.ytyp_time_flags_select_range"
    clear_operator = "sollumz.ytyp_time_flags_clear"

    bl_order = 3

    @classmethod
    def poll(cls, context):
        archetype = get_selected_archetype(context)
        return archetype and archetype.type == ArchetypeType.TIME

    def draw_header(self, context):
        self.layout.label(text="", icon="TIME")

    def get_flags_active(self, context):
        selected_archetype = get_selected_archetype(context)
        return selected_archetype.time_flags

    def get_flags_selection(self, context):
        selected_ytyp = get_selected_ytyp(context)
        return selected_ytyp.archetypes.selection.time_flags
