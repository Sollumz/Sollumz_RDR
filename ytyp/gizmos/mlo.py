import bpy
from ...sollumz_properties import ArchetypeType, SollumzGame
from ...sollumz_preferences import get_theme_settings
from mathutils import Vector, Matrix, Quaternion, Euler
from ..utils import get_selected_archetype, get_selected_ytyp, get_selected_portal, get_selected_tcm, get_selected_room
from ...tools.blenderhelper import find_parent


def can_draw_gizmos(context):
    aobj = context.active_object
    selected_archetype = get_selected_archetype(context)
    if aobj and selected_archetype:
        if not selected_archetype.asset or selected_archetype.type != ArchetypeType.MLO:
            return False
        if not selected_archetype.asset.visible_get():
            return False
        return aobj == selected_archetype.asset or find_parent(aobj, selected_archetype.asset.name)
    return False


class RoomGizmo(bpy.types.Gizmo):
    bl_idname = "OBJECT_GT_room"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linked_room = None

    @staticmethod
    def get_verts(bbmin, bbmax):
        return [
            bbmin,
            Vector((bbmin.x, bbmin.y, bbmax.z)),

            bbmin,
            Vector((bbmax.x, bbmin.y, bbmin.z)),

            bbmin,
            Vector((bbmin.x, bbmax.y, bbmin.z)),

            Vector((bbmax.x, bbmin.y, bbmax.z)),
            Vector((bbmax.x, bbmin.y, bbmin.z)),

            Vector((bbmin.x, bbmin.y, bbmax.z)),
            Vector((bbmin.x, bbmax.y, bbmax.z)),

            Vector((bbmin.x, bbmax.y, bbmin.z)),
            Vector((bbmin.x, bbmax.y, bbmax.z)),

            Vector((bbmax.x, bbmin.y, bbmax.z)),
            Vector((bbmax.x, bbmin.y, bbmax.z)),

            Vector((bbmax.x, bbmin.y, bbmax.z)),
            Vector((bbmin.x, bbmin.y, bbmax.z)),

            Vector((bbmax.x, bbmin.y, bbmin.z)),
            Vector((bbmax.x, bbmax.y, bbmin.z)),

            Vector((bbmin.x, bbmax.y, bbmin.z)),
            Vector((bbmax.x, bbmax.y, bbmin.z)),

            Vector((bbmax.x, bbmin.y, bbmax.z)),
            bbmax,

            Vector((bbmin.x, bbmax.y, bbmax.z)),
            bbmax,

            Vector((bbmax.x, bbmax.y, bbmin.z)),
            bbmax
        ]

    def draw(self, context):
        theme = get_theme_settings(context)
        selected_ytyp = get_selected_ytyp(context)
        selected_archetype = selected_ytyp.selected_archetype
        selected_room = selected_archetype.rooms.active_item
        room = self.linked_room

        self.use_draw_scale = False

        if room == selected_room:
            r, g, b, a = theme.mlo_gizmo_room_selected
        else:
            r, g, b, a = theme.mlo_gizmo_room

        self.color = r, g, b
        self.alpha = a

        asset = selected_archetype.asset
        if asset and room:
            self.custom_shape = self.new_custom_shape(
                "LINES", RoomGizmo.get_verts(room.bb_min, room.bb_max))
            self.draw_custom_shape(
                self.custom_shape, matrix=asset.matrix_world)


class RoomGizmoGroup(bpy.types.GizmoGroup):
    bl_idname = "OBJECT_GGT_Room"
    bl_label = "MLO Room"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}

    @classmethod
    def poll(cls, context):
        if not context.scene.show_room_gizmo:
            return False
        if can_draw_gizmos(context):
            selected_ytyp = get_selected_ytyp(context)
            selected_archetype = selected_ytyp.selected_archetype
            return selected_archetype.rooms.active_index < len(selected_archetype.rooms)
        return False

    def setup(self, context):
        pass

    def draw_prepare(self, context):
        selected_ytyp = get_selected_ytyp(context)
        selected_archetype = selected_ytyp.selected_archetype
        self.gizmos.clear()
        for room in selected_archetype.rooms:
            gz = self.gizmos.new(RoomGizmo.bl_idname)
            gz.linked_room = room


class PortalGizmo(bpy.types.Gizmo):
    bl_idname = "OBJECT_GT_portal"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linked_portal = None

    @staticmethod
    def get_verts(corners):
        return [
            corners[0],
            corners[1],
            corners[3],

            corners[2],
            corners[3],
            corners[1],
        ]

    def draw(self, context):
        self.draw_select(context)

    def draw_select(self, context, select_id=None):
        theme = get_theme_settings(context)
        selected_archetype = get_selected_archetype(context)
        selected_portal = get_selected_portal(context)
        portal = self.linked_portal
        asset = selected_archetype.asset

        if selected_portal == portal:
            r, g, b, a = theme.mlo_gizmo_portal_selected
        else:
            r, g, b, a = theme.mlo_gizmo_portal

        self.color = r, g, b
        self.alpha = a

        self.color_highlight = self.color * 0.9
        self.alpha_highlight = self.alpha

        if portal and asset:
            corners = [portal.corner1, portal.corner2,
                       portal.corner3, portal.corner4]

            self.portal_poly = self.new_custom_shape(
                "TRIS", PortalGizmo.get_verts(corners))

            self.draw_custom_shape(
                self.portal_poly, matrix=asset.matrix_world, select_id=select_id)

    def invoke(self, context, event):
        selected_archetype = get_selected_archetype(context)
        portals = list(selected_archetype.portals)

        if self.linked_portal not in portals:
            return

        selected_archetype.portals.select(portals.index(self.linked_portal))

        return {'PASS_THROUGH'}

    def modal(self, context, event, tweak):
        return {'PASS_THROUGH'}


class PortalNormalGizmo(bpy.types.Gizmo):
    bl_idname = "OBJECT_GT_portal_normal"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linked_portal = None

    def draw(self, context):
        theme = get_theme_settings(context)
        selected_archetype = get_selected_archetype(context)
        selected_portal = get_selected_portal(context)
        portal = self.linked_portal
        asset = selected_archetype.asset

        r, g, b, a = theme.mlo_gizmo_portal_direction
        self.color = r, g, b

        if selected_portal != portal:
            self.alpha = 0

        if selected_portal == portal:
            self.alpha = a

            if portal and asset:
                corners = [portal.corner1, portal.corner2,
                           portal.corner3, portal.corner4]
                x = [p[0] for p in corners]
                y = [p[1] for p in corners]
                z = [p[2] for p in corners]
                centroid = Vector(
                    (sum(x) / len(corners), sum(y) / len(corners), sum(z) / len(corners)))
                normal = -(corners[2] - corners[0]
                           ).cross(corners[1] - corners[0]).normalized()
                default_axis = Vector((0, 0, 1))
                rot = default_axis.rotation_difference(normal)
                scale = theme.mlo_gizmo_portal_direction_size
                arrow_mat = Matrix.LocRotScale(
                    centroid, rot, Vector((scale, scale, scale)))
                self.draw_preset_arrow(
                    matrix=asset.matrix_world @ arrow_mat)


class PortalGizmoGroup(bpy.types.GizmoGroup):
    bl_idname = "OBJECT_GGT_Portal"
    bl_label = "MLO Portal"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT", "SELECT"}

    @classmethod
    def poll(cls, context):
        if not context.scene.show_portal_gizmo:
            return False

        if not can_draw_gizmos(context):
            return False

        selected_archetype = get_selected_archetype(context)

        return selected_archetype.portals.active_index < len(selected_archetype.portals)

    def setup(self, context):
        pass

    def refresh(self, context):
        self.gizmos.clear()
        selected_archetype = get_selected_archetype(context)

        for portal in selected_archetype.portals:
            ngz = self.gizmos.new(PortalNormalGizmo.bl_idname)
            ngz.linked_portal = portal
            gz = self.gizmos.new(PortalGizmo.bl_idname)
            gz.linked_portal = portal


class TimecycleModifierGizmo(bpy.types.Gizmo):
    bl_idname = "OBJECT_GT_timecycle_modifier"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linked_tcm = None

    def draw(self, context):
        self.draw_select(context)

    def draw_select(self, context, select_id=None):
        theme = get_theme_settings(context)
        selected_archetype = get_selected_archetype(context)
        selected_tcm = get_selected_tcm(context)
        tcm = self.linked_tcm
        asset = selected_archetype.asset

        if selected_tcm == tcm:
            r, g, b, a = theme.mlo_gizmo_tcm_selected
        else:
            r, g, b, a = theme.mlo_gizmo_tcm

        self.color = r, g, b
        self.alpha = a

        self.color_highlight = self.color * 0.9
        self.alpha_highlight = self.alpha

        if tcm and asset:
            select_id = select_id if select_id is not None else -1
            t = asset.matrix_world @ Matrix.Translation(tcm.sphere_center)
            m = t @ Matrix.Scale(tcm.sphere_radius, 4)
            self.draw_preset_circle(m, axis="POS_X", select_id=select_id)
            self.draw_preset_circle(m, axis="POS_Y", select_id=select_id)
            self.draw_preset_circle(m, axis="POS_Z", select_id=select_id)
            m = t @ Matrix.Scale(tcm.range, 4)
            self.draw_preset_circle(m, axis="POS_Z", select_id=select_id)

    def invoke(self, context, event):
        selected_archetype = get_selected_archetype(context)
        tcms = list(selected_archetype.timecycle_modifiers)

        if self.linked_tcm not in tcms:
            return

        selected_archetype.timecycle_modifiers.select(tcms.index(self.linked_tcm))

        return {"PASS_THROUGH"}

    def modal(self, context, event, tweak):
        return {"PASS_THROUGH"}


class TimecycleModifierGizmoGroup(bpy.types.GizmoGroup):
    bl_idname = "OBJECT_GGT_timecycle_modifier"
    bl_label = "MLO Timecycle Modifier"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT", "SELECT"}

    @classmethod
    def poll(cls, context):
        if not context.scene.show_mlo_tcm_gizmo:
            return False

        if not can_draw_gizmos(context):
            return False

        selected_archetype = get_selected_archetype(context)

        return selected_archetype.timecycle_modifiers.active_index < len(selected_archetype.timecycle_modifiers)

    def setup(self, context):
        pass

    def refresh(self, context):
        self.gizmos.clear()
        selected_archetype = get_selected_archetype(context)

        for tcm in selected_archetype.timecycle_modifiers:
            gz = self.gizmos.new(TimecycleModifierGizmo.bl_idname)
            gz.linked_tcm = tcm


def get_geometry_mode(context):
    ytyp = get_selected_ytyp(context)
    archetype = get_selected_archetype(context)
    if ytyp is None or archetype is None:
        return 'NONE'
    archetype_tab = getattr(context.scene, 'SOLLUMZ_PT_ARCHETYPE_TABS_PANEL_active', '')
    focus = context.scene.get('_sollumz_ytyp_geometry_tab', '')
    if not focus or focus == 'NONE':
        return 'NONE'
    if archetype_tab == 'SOLLUMZ_PT_ARCHETYPE_BOUNDS_PANEL' and focus == archetype_tab:
        return 'BOUNDS'
    tab = getattr(context.scene, 'SOLLUMZ_PT_MLO_PANEL_active', '')
    modes = {
        'SOLLUMZ_PT_ROOM_PANEL': 'ROOM',
        'SOLLUMZ_PT_PORTAL_PANEL': 'PORTAL',
        'SOLLUMZ_PT_TIMECYCLE_MODIFIER_PANEL': 'TCM',
    }
    if ytyp.game == SollumzGame.RDR:
        modes.update({
            'SOLLUMZ_PT_RDR_MLO_VOLUMES_PANEL': 'MAIN',
            'SOLLUMZ_PT_RDR_MLO_EXTRA_VOLUMES_PANEL': 'EXTRA',
            'SOLLUMZ_PT_RDR_MLO_TIMECYCLE_VOLUMES_PANEL': 'TCV',
            'SOLLUMZ_PT_RDR_MLO_PROBES_PANEL': 'PROBE',
        })
        modes.pop('SOLLUMZ_PT_TIMECYCLE_MODIFIER_PANEL')
    if focus and focus != tab:
        return 'NONE'
    if archetype.type != ArchetypeType.MLO:
        return 'NONE'
    if tab:
        return modes.get(tab, 'NONE')
    return 'NONE'


GEOMETRY_GIZMO_TOGGLES = {
    'BOUNDS': 'show_archetype_bounds_gizmo',
    'ROOM': 'show_room_gizmo',
    'PORTAL': 'show_portal_gizmo',
    'TCM': 'show_mlo_tcm_gizmo',
    'MAIN': 'show_main_activation_gizmo',
    'EXTRA': 'show_extra_activation_gizmo',
    'TCV': 'show_timecycle_volume_gizmo',
    'PROBE': 'show_reflection_probe_gizmo',
}


def get_geometry_gizmo_color(context, mode, selected=True):
    theme = get_theme_settings(context)
    if mode == 'PORTAL':
        return theme.mlo_gizmo_portal_selected if selected else theme.mlo_gizmo_portal
    if mode in {'TCM', 'TCV', 'MAIN', 'EXTRA'}:
        return theme.mlo_gizmo_tcm_selected if selected else theme.mlo_gizmo_tcm
    return theme.mlo_gizmo_room_selected if selected else theme.mlo_gizmo_room


def get_geometry_collection(context, mode):
    archetype = get_selected_archetype(context)
    if archetype is None:
        return None, None, None
    if mode == 'EXTRA':
        return archetype, 'extra_activation_volumes', 'extra_activation_volume_index'
    if mode == 'TCV':
        return archetype, 'timecycle_volumes', 'timecycle_volume_index'
    if mode == 'PROBE':
        return get_selected_room(context), 'reflection_probes', 'reflection_probe_index'
    return None, None, None


def get_geometry_handles(context):
    """(owner, vector property, local-to-world matrix, constraint) for each editable point."""
    archetype = get_selected_archetype(context)
    if archetype is None:
        return []
    if archetype.asset:
        active_object = context.active_object
        if not archetype.asset.visible_get() or active_object is None:
            return []
        if active_object != archetype.asset and not find_parent(active_object, archetype.asset.name):
            return []
    matrix = archetype.asset.matrix_world.copy() if archetype.asset else Matrix.Identity(4)
    mode = get_geometry_mode(context)
    toggle = GEOMETRY_GIZMO_TOGGLES.get(mode)
    if toggle is None or not getattr(context.scene, toggle):
        return []
    if mode == 'BOUNDS':
        if archetype.asset and archetype.bounds_from_asset:
            return []
        return [(archetype, 'bb_min', matrix, 'MIN'), (archetype, 'bb_max', matrix, 'MAX'),
                (archetype, 'bs_center', matrix, None), (archetype, 'bs_center', matrix, 'bs_radius')]
    if mode == 'ROOM':
        room = get_selected_room(context)
        return [(room, 'bb_min', matrix, 'MIN'), (room, 'bb_max', matrix, 'MAX')] if room else []
    if mode == 'PORTAL':
        portal = get_selected_portal(context)
        return [(portal, f'corner{i}', matrix, None) for i in range(1, 5)] if portal else []
    if mode == 'TCM':
        tcm = get_selected_tcm(context)
        return [(tcm, 'sphere_center', matrix, None), (tcm, 'sphere_center', matrix, 'sphere_radius')] if tcm else []
    if mode in {'MAIN', 'EXTRA'}:
        volumes = archetype.extra_activation_volumes
        index = archetype.extra_activation_volume_index
        volume = (archetype.main_activation_volume if mode == 'MAIN'
                  else volumes[index] if index < len(volumes) else None)
        return [(volume, 'center', matrix, None), (volume, 'center', matrix, 'radius')] if volume else []
    if mode == 'TCV':
        volumes = archetype.timecycle_volumes
        index = archetype.timecycle_volume_index
        if index >= len(volumes):
            return []
        volume = volumes[index]
        return [(volume, 'center', matrix, None)] + [(volume, 'center', matrix, f'SCALE{i}') for i in range(3)]
    if mode == 'PROBE':
        room = get_selected_room(context)
        if room is None or room.reflection_probe_index >= len(room.reflection_probes):
            return []
        probe = room.reflection_probes[room.reflection_probe_index]
        probe_matrix = (matrix @ Matrix.Translation(probe.center_offset)
                        @ Quaternion(probe.rotation).to_matrix().to_4x4())
        return [(probe, 'center_offset', matrix, None), (probe, 'min_extents', probe_matrix, 'MIN'),
                (probe, 'max_extents', probe_matrix, 'MAX')]
    return []


def geometry_handle_position(owner, prop, constraint):
    position = Vector(getattr(owner, prop))
    if constraint and constraint.startswith('SCALE'):
        axis = int(constraint[-1])
        offset = Vector((0, 0, 0))
        offset[axis] = owner.scale[axis]
        position += Euler(owner.orientation).to_matrix() @ offset
    elif constraint not in (None, 'MIN', 'MAX'):
        position.x += getattr(owner, constraint)
    return position


def set_geometry_handle_position(owner, prop, matrix, constraint, world_position):
    position = matrix.inverted() @ Vector(world_position)
    if constraint and constraint.startswith('SCALE'):
        axis = int(constraint[-1])
        offset = Euler(owner.orientation).to_matrix().inverted() @ (position - Vector(owner.center))
        owner.scale[axis] = offset[axis]
    elif constraint not in (None, 'MIN', 'MAX'):
        setattr(owner, constraint, max(0.0, position.x - getattr(owner, prop)[0]))
    else:
        if constraint in ('MIN', 'MAX'):
            opposite = prop.replace('min', 'max') if constraint == 'MIN' else prop.replace('max', 'min')
            clamp = min if constraint == 'MIN' else max
            position = Vector(tuple(clamp(position[i], getattr(owner, opposite)[i]) for i in range(3)))
        setattr(owner, prop, position)


class ArchetypeGeometryGizmo(bpy.types.Gizmo):
    bl_idname = 'SOLLUMZ_GT_archetype_geometry'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linked_item = None

    def draw(self, context):
        self.draw_select(context)

    def draw_select(self, context, select_id=None):
        handles = get_geometry_handles(context)
        if not handles:
            return
        owner, prop, matrix, constraint = handles[0]
        mode = get_geometry_mode(context)
        selected = self.linked_item is None or self.linked_item == owner
        if self.linked_item is not None:
            owner = self.linked_item
        r, g, b, a = get_geometry_gizmo_color(context, mode, selected)
        self.color = r, g, b
        self.alpha = a
        self.color_highlight = self.color * 0.9
        self.alpha_highlight = self.alpha
        self.use_draw_scale = False
        if mode in {'BOUNDS', 'ROOM'}:
            verts = RoomGizmo.get_verts(Vector(owner.bb_min), Vector(owner.bb_max))
        elif mode == 'PROBE':
            matrix = (matrix @ Matrix.Translation(owner.center_offset)
                      @ Quaternion(owner.rotation).to_matrix().to_4x4())
            verts = RoomGizmo.get_verts(Vector(owner.min_extents), Vector(owner.max_extents))
        elif mode == 'PORTAL':
            corners = [Vector(getattr(owner, f'corner{i}')) for i in range(1, 5)]
            verts = [corners[i] for edge in ((0, 1), (1, 2), (2, 3), (3, 0)) for i in edge]
        elif mode == 'TCV':
            center = Vector(owner.center)
            rotation = Euler(owner.orientation).to_matrix()
            verts = [center + rotation @ v for v in RoomGizmo.get_verts(-Vector(owner.scale), Vector(owner.scale))]
        else:
            verts = []
        if verts:
            self.draw_custom_shape(self.new_custom_shape('LINES', verts), matrix=matrix, select_id=select_id)
        if mode in {'BOUNDS', 'TCM', 'MAIN', 'EXTRA'}:
            if mode == 'BOUNDS':
                center_prop, radius_prop = 'bs_center', 'bs_radius'
            elif mode == 'TCM':
                center_prop, radius_prop = 'sphere_center', 'sphere_radius'
            else:
                center_prop, radius_prop = 'center', 'radius'
            sphere = (matrix @ Matrix.Translation(getattr(owner, center_prop))
                      @ Matrix.Scale(getattr(owner, radius_prop), 4))
            for axis in ('POS_X', 'POS_Y', 'POS_Z'):
                self.draw_preset_circle(sphere, axis=axis, select_id=select_id if select_id is not None else -1)

    def invoke(self, context, event):
        parent, collection_name, index_name = get_geometry_collection(context, get_geometry_mode(context))
        if parent is not None and self.linked_item is not None:
            items = list(getattr(parent, collection_name))
            if self.linked_item in items:
                setattr(parent, index_name, items.index(self.linked_item))
        return {'PASS_THROUGH'}

    def modal(self, context, event, tweak):
        return {'PASS_THROUGH'}


class ArchetypeGeometryGizmoGroup(bpy.types.GizmoGroup):
    bl_idname = 'SOLLUMZ_GGT_archetype_geometry'
    bl_label = 'Archetype Geometry'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SELECT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        ytyp = get_selected_ytyp(context)
        archetype = get_selected_archetype(context)
        return (ytyp is not None and not ytyp.archetypes.has_multiple_selection
                and archetype is not None)

    def setup(self, context):
        self.outline = self.gizmos.new(ArchetypeGeometryGizmo.bl_idname)
        self.outline.hide_select = True
        self.outline.hide = True
        self.handles = []
        self.handle_key = None
        self.other_outlines = []
        self.outline_key = None

    def refresh(self, context):
        self.draw_prepare(context)

    def draw_prepare(self, context):
        specs = get_geometry_handles(context)
        mode = get_geometry_mode(context)
        self.outline.hide = not bool(specs) or mode in {'ROOM', 'PORTAL', 'TCM'}
        parent, collection_name, index_name = get_geometry_collection(context, mode)
        items = list(getattr(parent, collection_name)) if specs and parent is not None else []
        selected_item = specs[0][0] if specs else None
        self.outline.linked_item = selected_item
        self.outline.hide_select = not bool(items)
        other_items = [item for item in items if item != selected_item]
        outline_key = (mode, tuple(item.as_pointer() for item in other_items))
        if outline_key != self.outline_key:
            for gizmo in self.other_outlines:
                self.gizmos.remove(gizmo)
            self.other_outlines = []
            for item in other_items:
                gizmo = self.gizmos.new(ArchetypeGeometryGizmo.bl_idname)
                gizmo.linked_item = item
                self.other_outlines.append(gizmo)
            self.outline_key = outline_key
        key = tuple((owner.as_pointer(), prop, constraint) for owner, prop, matrix, constraint in specs)
        if key != self.handle_key:
            for gizmo in self.handles:
                self.gizmos.remove(gizmo)
            self.handles = []
            for owner, prop, matrix, constraint in specs:
                gizmo = self.gizmos.new('GIZMO_GT_move_3d')
                gizmo.draw_style = 'CROSS_2D'
                gizmo.scale_basis = 0.12
                gizmo.use_draw_modal = True
                gizmo.use_draw_value = True
                gizmo.matrix_basis = Matrix.Identity(4)
                self.handles.append(gizmo)
            self.handle_key = key
        r, g, b, a = get_geometry_gizmo_color(context, mode)
        for gizmo, (owner, prop, matrix, constraint) in zip(self.handles, specs):
            gizmo.color = r, g, b
            gizmo.color_highlight = tuple(channel * 0.9 for channel in (r, g, b))
            gizmo.alpha = gizmo.alpha_highlight = a
            if gizmo.is_modal:
                continue
            # Freeze this matrix for the drag; every point is stored in archetype local space.
            def getter(owner=owner, prop=prop, matrix=matrix, constraint=constraint):
                return tuple(matrix @ geometry_handle_position(owner, prop, constraint))

            def setter(value, owner=owner, prop=prop, matrix=matrix, constraint=constraint):
                set_geometry_handle_position(owner, prop, matrix, constraint, value)
                if context.area:
                    context.area.tag_redraw()

            gizmo.target_set_handler('offset', get=getter, set=setter)
