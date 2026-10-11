import bpy
from ...sollumz_properties import FlagPropertyGroup


class YtypFlags(FlagPropertyGroup):
    def update_flag(self, context):
        # Unknown upper bits from imported files must survive checkbox edits.
        mask = (1 << self.size) - 1
        value = int(self.total) & ~mask
        for index, name in enumerate(self.get_flag_names()):
            if index >= self.size:
                break
            if getattr(self, name):
                value |= 1 << index
        self.total = str(value)


# RDR3 b1491.50 parser enums; keep the GTA labels on the RNA properties.
RDR_FLAG_LABELS = {
    'PortalFlags': {
        'flag5': 'Unused',
        'flag14': 'Unused',
        'flag15': 'Unknown 0x0FA9A39D',
    },
    'MloFlags': {
        **{f'flag{i}': f'Unknown Bit {i - 1}' for i in range(1, 9)},
        'flag15': 'Unknown 0x4D0239D6',
        'flag17': 'Unknown 0x77A1E9E4',
    },
    'EntityFlags': {'flag17': 'Underwater'},
}


class RoomFlags(YtypFlags, bpy.types.PropertyGroup):
    size = 10

    flag1: bpy.props.BoolProperty(
        name="Freeze Vehicles", update=YtypFlags.update_flag)
    flag2: bpy.props.BoolProperty(
        name="Freeze Peds", update=YtypFlags.update_flag)
    flag3: bpy.props.BoolProperty(
        name="No Directional Light", update=YtypFlags.update_flag)
    flag4: bpy.props.BoolProperty(
        name="No Exterior Lights", update=YtypFlags.update_flag)
    flag5: bpy.props.BoolProperty(
        name="Force Freeze", update=YtypFlags.update_flag)
    flag6: bpy.props.BoolProperty(
        name="Reduce Cars", update=YtypFlags.update_flag)
    flag7: bpy.props.BoolProperty(
        name="Reduce Peds", update=YtypFlags.update_flag)
    flag8: bpy.props.BoolProperty(
        name="Force Directional Light On", update=YtypFlags.update_flag)
    flag9: bpy.props.BoolProperty(
        name="Dont Render Exterior", update=YtypFlags.update_flag)
    flag10: bpy.props.BoolProperty(
        name="Mirror Potentially Visible", update=YtypFlags.update_flag)


class PortalFlags(YtypFlags, bpy.types.PropertyGroup):
    size = 15

    flag1: bpy.props.BoolProperty(
        name="One Way", update=YtypFlags.update_flag)
    flag2: bpy.props.BoolProperty(
        name="Link Interiors Together", update=YtypFlags.update_flag)
    flag3: bpy.props.BoolProperty(
        name="Mirror", update=YtypFlags.update_flag)
    flag4: bpy.props.BoolProperty(
        name="Disable Timecycle Modifier", update=YtypFlags.update_flag)
    flag5: bpy.props.BoolProperty(
        name="Mirror Using Expensive Shaders", update=YtypFlags.update_flag)
    flag6: bpy.props.BoolProperty(
        name="Low LOD Only", update=YtypFlags.update_flag)
    flag7: bpy.props.BoolProperty(
        name="Hide when door closed", update=YtypFlags.update_flag)
    flag8: bpy.props.BoolProperty(
        name="Mirror Can See Directional", update=YtypFlags.update_flag)
    flag9: bpy.props.BoolProperty(
        name="Mirror Using Portal Traversal", update=YtypFlags.update_flag)
    flag10: bpy.props.BoolProperty(
        name="Mirror Floor", update=YtypFlags.update_flag)
    flag11: bpy.props.BoolProperty(
        name="Mirror Can See Exterior View", update=YtypFlags.update_flag)
    flag12: bpy.props.BoolProperty(
        name="Water Surface", update=YtypFlags.update_flag)
    flag13: bpy.props.BoolProperty(
        name="Water Surface Extend To Horizon", update=YtypFlags.update_flag)
    flag14: bpy.props.BoolProperty(
        name="Use Light Bleed", update=YtypFlags.update_flag)
    flag15: bpy.props.BoolProperty(
        name="Unknown 0x0FA9A39D", update=YtypFlags.update_flag)


class EntityFlags(YtypFlags, bpy.types.PropertyGroup):
    flag1: bpy.props.BoolProperty(
        name="Allow full rotation", update=YtypFlags.update_flag)
    flag2: bpy.props.BoolProperty(
        name="Stream Low Priority", update=YtypFlags.update_flag)
    flag3: bpy.props.BoolProperty(
        name="Disable embedded collisions", update=YtypFlags.update_flag)
    flag4: bpy.props.BoolProperty(
        name="LOD in Parented YMAP", update=YtypFlags.update_flag)
    flag5: bpy.props.BoolProperty(
        name="LOD Adopt Me", update=YtypFlags.update_flag)
    flag6: bpy.props.BoolProperty(
        name="Static entity", update=YtypFlags.update_flag)
    flag7: bpy.props.BoolProperty(
        name="Interior LOD", update=YtypFlags.update_flag)
    flag8: bpy.props.BoolProperty(
        name="Unknown 8", update=YtypFlags.update_flag)
    flag9: bpy.props.BoolProperty(
        name="Unknown 9", update=YtypFlags.update_flag)
    flag10: bpy.props.BoolProperty(
        name="Unknown 10", update=YtypFlags.update_flag)
    flag11: bpy.props.BoolProperty(
        name="Unknown 11", update=YtypFlags.update_flag)
    flag12: bpy.props.BoolProperty(
        name="Unknown 12", update=YtypFlags.update_flag)
    flag13: bpy.props.BoolProperty(
        name="Unknown 13", update=YtypFlags.update_flag)
    flag14: bpy.props.BoolProperty(
        name="Unknown 14", update=YtypFlags.update_flag)
    flag15: bpy.props.BoolProperty(
        name="Unknown 15", update=YtypFlags.update_flag)
    flag16: bpy.props.BoolProperty(
        name="LOD Use Alt Fade", update=YtypFlags.update_flag)
    flag17: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag18: bpy.props.BoolProperty(
        name="Does Not Touch Water", update=YtypFlags.update_flag)
    flag19: bpy.props.BoolProperty(name="Does Not Spawn Peds",
                                   update=YtypFlags.update_flag)
    flag20: bpy.props.BoolProperty(
        name="Cast Static Shadows", update=YtypFlags.update_flag)
    flag21: bpy.props.BoolProperty(
        name="Cast Dynamic Shadows", update=YtypFlags.update_flag)
    flag22: bpy.props.BoolProperty(
        name="Ignore Day Night Settings", update=YtypFlags.update_flag)
    flag23: bpy.props.BoolProperty(
        name="Disable shadow for entity", update=YtypFlags.update_flag)
    flag24: bpy.props.BoolProperty(
        name="Disable entity, shadow casted", update=YtypFlags.update_flag)
    flag25: bpy.props.BoolProperty(
        name="Dont Render In Reflections", update=YtypFlags.update_flag)
    flag26: bpy.props.BoolProperty(
        name="Only Render In Reflections", update=YtypFlags.update_flag)
    flag27: bpy.props.BoolProperty(
        name="Dont Render In Water Reflections", update=YtypFlags.update_flag)
    flag28: bpy.props.BoolProperty(
        name="Only Render In Water Reflections", update=YtypFlags.update_flag)
    flag29: bpy.props.BoolProperty(
        name="Dont Render In Mirror Reflections", update=YtypFlags.update_flag)
    flag30: bpy.props.BoolProperty(
        name="Only Render In Mirror Reflections", update=YtypFlags.update_flag)
    flag31: bpy.props.BoolProperty(
        name="Unknown 31", update=YtypFlags.update_flag)
    flag32: bpy.props.BoolProperty(
        name="Unknown 32", update=YtypFlags.update_flag)


class ArchetypeFlags(YtypFlags, bpy.types.PropertyGroup):
    flag1: bpy.props.BoolProperty(
        name="Wet Road Reflection", update=YtypFlags.update_flag)
    flag2: bpy.props.BoolProperty(
        name="Dont Fade", update=YtypFlags.update_flag)
    flag3: bpy.props.BoolProperty(
        name="Draw Last", update=YtypFlags.update_flag)
    flag4: bpy.props.BoolProperty(
        name="Climbable By AI", update=YtypFlags.update_flag)
    flag5: bpy.props.BoolProperty(
        name="Suppress HD TXDs", update=YtypFlags.update_flag)
    flag6: bpy.props.BoolProperty(
        name="Static", update=YtypFlags.update_flag)
    flag7: bpy.props.BoolProperty(
        name="Disable alpha sorting", update=YtypFlags.update_flag)
    flag8: bpy.props.BoolProperty(
        name="Tough For Bullets", update=YtypFlags.update_flag)
    flag9: bpy.props.BoolProperty(
        name="Is Generic", update=YtypFlags.update_flag)
    flag10: bpy.props.BoolProperty(
        name="Has Anim (YCD)", update=YtypFlags.update_flag)
    flag11: bpy.props.BoolProperty(
        name="UV anims (YCD)", update=YtypFlags.update_flag)
    flag12: bpy.props.BoolProperty(
        name="Shadow Only", update=YtypFlags.update_flag)
    flag13: bpy.props.BoolProperty(
        name="Damage Model", update=YtypFlags.update_flag)
    flag14: bpy.props.BoolProperty(
        name="Dont Cast Shadows", update=YtypFlags.update_flag)
    flag15: bpy.props.BoolProperty(
        name="Cast Texture Shadows", update=YtypFlags.update_flag)
    flag16: bpy.props.BoolProperty(
        name="Dont Collide With Flyer", update=YtypFlags.update_flag)
    flag17: bpy.props.BoolProperty(
        name="Double-sided rendering", update=YtypFlags.update_flag)
    flag18: bpy.props.BoolProperty(
        name="Dynamic", update=YtypFlags.update_flag)
    flag19: bpy.props.BoolProperty(
        name="Override Physics Bounds", update=YtypFlags.update_flag)
    flag20: bpy.props.BoolProperty(
        name="Auto Start Anim", update=YtypFlags.update_flag)
    flag21: bpy.props.BoolProperty(
        name="Has Pre Reflected Water Proxy", update=YtypFlags.update_flag)
    flag22: bpy.props.BoolProperty(
        name="Has Drawable Proxy For Water Reflections", update=YtypFlags.update_flag)
    flag23: bpy.props.BoolProperty(
        name="Does Not Provide AI Cover", update=YtypFlags.update_flag)
    flag24: bpy.props.BoolProperty(
        name="Does Not Provide Player Cover", update=YtypFlags.update_flag)
    flag25: bpy.props.BoolProperty(
        name="Is Ladder Deprecated", update=YtypFlags.update_flag)
    flag26: bpy.props.BoolProperty(
        name="Has Cloth", update=YtypFlags.update_flag)
    flag27: bpy.props.BoolProperty(
        name="Enable Door Physics", update=YtypFlags.update_flag)
    flag28: bpy.props.BoolProperty(
        name="Is Fixed For Navigation", update=YtypFlags.update_flag)
    flag29: bpy.props.BoolProperty(
        name="Dont Avoid By Peds", update=YtypFlags.update_flag)
    flag30: bpy.props.BoolProperty(
        name="Use Ambient Scale", update=YtypFlags.update_flag)
    flag31: bpy.props.BoolProperty(
        name="Is Debug", update=YtypFlags.update_flag)
    flag32: bpy.props.BoolProperty(
        name="Has Alpha Shadow", update=YtypFlags.update_flag)


class MloFlags(YtypFlags, bpy.types.PropertyGroup):
    size = 17

    flag1: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag2: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag3: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag4: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag5: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag6: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag7: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag8: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag9: bpy.props.BoolProperty(
        name="Subway", update=YtypFlags.update_flag)
    flag10: bpy.props.BoolProperty(
        name="Office", update=YtypFlags.update_flag)
    flag11: bpy.props.BoolProperty(
        name="Allow Run", update=YtypFlags.update_flag)
    flag12: bpy.props.BoolProperty(
        name="Cutscene Only", update=YtypFlags.update_flag)
    flag13: bpy.props.BoolProperty(
        name="LOD When Locked", update=YtypFlags.update_flag)
    flag14: bpy.props.BoolProperty(
        name="No Water Reflection", update=YtypFlags.update_flag)
    flag15: bpy.props.BoolProperty(
        name="Unused", update=YtypFlags.update_flag)
    flag16: bpy.props.BoolProperty(
        name="Has Low LOD Portals", update=YtypFlags.update_flag)
    flag17: bpy.props.BoolProperty(
        name="Unknown 0x77A1E9E4", update=YtypFlags.update_flag)
