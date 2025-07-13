from ..ydr.shader_materials import shadermats, rdr_shadermats
from ..ybn.collision_materials import collisionmats, rdr_collisionmats

SOLLUMZ_SHADERS = list(map(lambda s: s.value, shadermats))
SOLLUMZ_SHADERS_RDR = list(map(lambda s: s.value, rdr_shadermats))
SOLLUMZ_COLLISION_MATERIALS = list(collisionmats)
SOLLUMZ_COLLISION_MATERIALS_RDR = list(rdr_collisionmats)
BLENDER_LANGUAGES = ("en_US", "es")  # bpy.app.translations.locales
