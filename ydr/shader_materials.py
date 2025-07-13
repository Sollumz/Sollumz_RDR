from typing import Optional, NamedTuple
import bpy
from ..cwxml.shader import (
    ShaderManager,
    ShaderParameterType,
)
from ..sollumz_properties import MaterialType, SollumzGame, MIN_VEHICLE_LIGHT_ID, MAX_VEHICLE_LIGHT_ID
from ..tools.blenderhelper import find_bsdf_and_material_output
from ..tools.animationhelper import add_global_anim_uv_nodes
from ..tools.meshhelper import get_uv_map_name, get_color_attr_name
from ..shared.shader_nodes import SzShaderNodeParameter, SzShaderNodeParameterDisplayType
from ..shared.shader_expr import expr, compile_expr
from .render_bucket import RenderBucket

from .shader_materials_SHARED import *
from .shader_materials_RDR import RDR_create_basic_shader_nodes, RDR_create_2lyr_shader, RDR_create_terrain_shader


class ShaderMaterial(NamedTuple):
    name: str
    ui_name: str
    value: str


shadermats = []

for shader in ShaderManager._shaders.values():
    name = shader.filename.replace(".sps", "").upper()

    shadermats.append(ShaderMaterial(name, name.replace("_", " "), shader.filename))

shadermats_by_filename = {s.value: s for s in shadermats}

rdr_shadermats = []

for shader in ShaderManager._rdr_shaders.values():
    name = shader.filename.replace(".sps", "").upper()

    rdr_shadermats.append(ShaderMaterial(name, name.replace("_", " "), shader.filename))

rdr_shadermats_by_filename = {s.value: s for s in rdr_shadermats}


def get_detail_extra_sampler(mat):  # move to blenderhelper.py?
    nodes = mat.node_tree.nodes
    for node in nodes:
        if node.name == "Extra":
            return node
    return None


def link_diffuses(b: ShaderBuilder, tex1, tex2):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    rgb = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(tex1.outputs["Color"], rgb.inputs["Color1"])
    links.new(tex2.outputs["Color"], rgb.inputs["Color2"])
    links.new(tex2.outputs["Alpha"], rgb.inputs["Fac"])
    links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])
    return rgb


def link_detailed_normal(b: ShaderBuilder, bumptex, dtltex, spectex):
    node_tree = b.node_tree
    bsdf = b.bsdf
    dtltex2 = node_tree.nodes.new("ShaderNodeTexImage")
    dtltex2.name = "Extra"
    dtltex2.label = dtltex2.name
    ds = node_tree.nodes["detailSettings"]
    links = node_tree.links
    uv_map0 = node_tree.nodes[get_uv_map_name(0)]
    comxyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
    mathns = []
    for _ in range(9):
        math = node_tree.nodes.new("ShaderNodeVectorMath")
        mathns.append(math)
    nrm = node_tree.nodes.new("ShaderNodeNormalMap")

    links.new(uv_map0.outputs[0], mathns[0].inputs[0])

    links.new(ds.outputs["Z"], comxyz.inputs[0])
    links.new(ds.outputs["W"], comxyz.inputs[1])

    mathns[0].operation = "MULTIPLY"
    links.new(comxyz.outputs[0], mathns[0].inputs[1])
    links.new(mathns[0].outputs[0], dtltex2.inputs[0])

    mathns[1].operation = "MULTIPLY"
    mathns[1].inputs[1].default_value[0] = 3.17
    mathns[1].inputs[1].default_value[1] = 3.17
    links.new(mathns[0].outputs[0], mathns[1].inputs[0])
    links.new(mathns[1].outputs[0], dtltex.inputs[0])

    mathns[2].operation = "SUBTRACT"
    mathns[2].inputs[1].default_value[0] = 0.5
    mathns[2].inputs[1].default_value[1] = 0.5
    links.new(dtltex.outputs[0], mathns[2].inputs[0])

    mathns[3].operation = "SUBTRACT"
    mathns[3].inputs[1].default_value[0] = 0.5
    mathns[3].inputs[1].default_value[1] = 0.5
    links.new(dtltex2.outputs[0], mathns[3].inputs[0])

    mathns[4].operation = "ADD"
    links.new(mathns[2].outputs[0], mathns[4].inputs[0])
    links.new(mathns[3].outputs[0], mathns[4].inputs[1])

    mathns[5].operation = "MULTIPLY"
    links.new(mathns[4].outputs[0], mathns[5].inputs[0])
    links.new(ds.outputs["Y"], mathns[5].inputs[1])

    mathns[6].operation = "MULTIPLY"
    if spectex:
        links.new(spectex.outputs[1], mathns[6].inputs[0])
    links.new(mathns[5].outputs[0], mathns[6].inputs[1])

    mathns[7].operation = "MULTIPLY"
    mathns[7].inputs[1].default_value[0] = 1
    mathns[7].inputs[1].default_value[1] = 1
    links.new(mathns[6].outputs[0], mathns[7].inputs[0])

    mathns[8].operation = "ADD"
    links.new(mathns[7].outputs[0], mathns[8].inputs[0])
    links.new(bumptex.outputs[0], mathns[8].inputs[1])

    links.new(mathns[8].outputs[0], nrm.inputs[1])
    links.new(nrm.outputs[0], bsdf.inputs["Normal"])


def link_specular(b: ShaderBuilder, spctex):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    links.new(spctex.outputs["Color"], bsdf.inputs["Specular IOR Level"])


def create_diff_palette_nodes(
    b: ShaderBuilder,
    palette_tex: bpy.types.ShaderNodeTexImage,
    diffuse_tex: bpy.types.ShaderNodeTexImage
):
    palette_tex.interpolation = "Closest"
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    mathns = []
    locx = 0
    locy = 50
    for _ in range(6):
        math = node_tree.nodes.new("ShaderNodeMath")
        math.location.x = locx
        math.location.y = locy
        mathns.append(math)
        locx += 150
    comxyz = node_tree.nodes.new("ShaderNodeCombineXYZ")

    mathns[0].operation = "MULTIPLY"
    links.new(diffuse_tex.outputs["Alpha"], mathns[0].inputs[0])
    mathns[0].inputs[1].default_value = 255.009995

    mathns[1].operation = "ROUND"
    links.new(mathns[0].outputs[0], mathns[1].inputs[0])

    mathns[2].operation = "SUBTRACT"
    links.new(mathns[1].outputs[0], mathns[2].inputs[0])
    mathns[2].inputs[1].default_value = 32.0

    mathns[3].operation = "MULTIPLY"
    links.new(mathns[2].outputs[0], mathns[3].inputs[0])
    mathns[3].inputs[1].default_value = 0.007813
    links.new(mathns[3].outputs[0], comxyz.inputs[0])

    mathns[4].operation = "MULTIPLY"
    mathns[4].inputs[0].default_value = 0.03125
    mathns[4].inputs[1].default_value = 0.5

    mathns[5].operation = "SUBTRACT"
    mathns[5].inputs[0].default_value = 1
    links.new(mathns[4].outputs[0], mathns[5].inputs[1])
    links.new(mathns[5].outputs[0], comxyz.inputs[1])

    links.new(comxyz.outputs[0], palette_tex.inputs[0])
    links.new(palette_tex.outputs[0], bsdf.inputs["Base Color"])


def create_distance_map_nodes(b: ShaderBuilder, distance_map_texture: bpy.types.ShaderNodeTexImage):
    node_tree = b.node_tree
    output = b.material_output
    bsdf = b.bsdf
    links = node_tree.links
    mix = node_tree.nodes.new("ShaderNodeMixShader")
    trans = node_tree.nodes.new("ShaderNodeBsdfTransparent")
    multiply_color = node_tree.nodes.new("ShaderNodeVectorMath")
    multiply_color.operation = "MULTIPLY"
    multiply_alpha = node_tree.nodes.new("ShaderNodeMath")
    multiply_alpha.operation = "MULTIPLY"
    multiply_alpha.inputs[1].default_value = 1.0  # alpha value
    distance_greater_than = node_tree.nodes.new("ShaderNodeMath")
    distance_greater_than.operation = "GREATER_THAN"
    distance_greater_than.inputs[1].default_value = 0.5  # distance threshold
    distance_separate_x = node_tree.nodes.new("ShaderNodeSeparateXYZ")
    fill_color_combine = node_tree.nodes.new("ShaderNodeCombineXYZ")
    fill_color = node_tree.nodes["fillColor"]

    # combine fillColor into a vector
    links.new(fill_color.outputs["X"], fill_color_combine.inputs["X"])
    links.new(fill_color.outputs["Y"], fill_color_combine.inputs["Y"])
    links.new(fill_color.outputs["Z"], fill_color_combine.inputs["Z"])

    # extract distance value from texture and check > 0.5
    links.new(distance_map_texture.outputs["Color"], distance_separate_x.inputs["Vector"])
    links.remove(distance_map_texture.outputs["Alpha"].links[0])
    links.new(distance_separate_x.outputs["X"], distance_greater_than.inputs["Value"])

    # multiply color and alpha by distance check result
    links.new(distance_greater_than.outputs["Value"], multiply_alpha.inputs[0])
    links.new(distance_greater_than.outputs["Value"], multiply_color.inputs[0])
    links.new(fill_color_combine.outputs["Vector"], multiply_color.inputs[1])

    # connect output color and alpha
    links.new(multiply_alpha.outputs["Value"], mix.inputs["Fac"])
    links.new(multiply_color.outputs["Vector"], bsdf.inputs["Base Color"])

    # connect BSDFs and material output
    links.new(trans.outputs["BSDF"], mix.inputs[1])
    links.remove(bsdf.outputs["BSDF"].links[0])
    links.new(bsdf.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])


def create_emissive_nodes(b: ShaderBuilder):
    node_tree = b.node_tree
    links = node_tree.links
    output = b.material_output
    tmpn = output.inputs[0].links[0].from_node
    mix = node_tree.nodes.new("ShaderNodeMixShader")
    if tmpn == b.bsdf:
        em = node_tree.nodes.new("ShaderNodeEmission")
        diff = node_tree.nodes["DiffuseSampler"]
        links.new(diff.outputs[0], em.inputs[0])
        links.new(em.outputs[0], mix.inputs[1])
        links.new(tmpn.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs[0])


def create_water_nodes(b: ShaderBuilder):
    node_tree = b.node_tree
    links = node_tree.links
    bsdf = b.bsdf
    output = b.material_output

    bsdf.inputs["Base Color"].default_value = (0.602416, 0.894181, 1.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = 1.444
    bsdf.inputs["Transmission Weight"].default_value = 1.0

    nm = node_tree.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.2
    noise = node_tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 2.0
    layer_weight = node_tree.nodes.new("ShaderNodeLayerWeight")
    layer_weight.inputs["Blend"].default_value = 0.94

    links.new(layer_weight.outputs["Fresnel"], bsdf.inputs["Alpha"])
    links.new(noise.outputs["Color"], nm.inputs["Color"])
    links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

def create_tint_nodes(
    b: ShaderBuilder,
    diffuse_tex: bpy.types.ShaderNodeTexImage
):
    # create shader attribute node
    # TintColor attribute is filled by tint geometry nodes
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    attr = node_tree.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "TintColor"
    mix = node_tree.nodes.new("ShaderNodeMixRGB")
    mix.inputs["Fac"].default_value = 0.95
    mix.blend_type = "MULTIPLY"
    links.new(attr.outputs["Color"], mix.inputs[2])
    links.new(diffuse_tex.outputs[0], mix.inputs[1])
    links.new(mix.outputs[0], bsdf.inputs["Base Color"])

def create_basic_shader_nodes(b: ShaderBuilder):
    shader = b.shader
    filename = b.filename
    mat = b.material
    node_tree = b.node_tree
    bsdf = b.bsdf

    texture = None
    texture2 = None
    tintpal = None
    diffpal = None
    bumptex = None
    spectex = None
    detltex = None
    is_distance_map = False

    for param in shader.parameters:
        match param.type:
            case ShaderParameterType.TEXTURE:
                imgnode = create_image_node(node_tree, param)
                if param.name in ("DiffuseSampler", "PlateBgSampler", "diffusetex"):
                    texture = imgnode
                elif param.name in ("BumpSampler", "PlateBgBumpSampler", "normaltex", "bumptex"):
                    bumptex = imgnode
                elif param.name in ("SpecSampler", "speculartex"):
                    spectex = imgnode
                elif param.name == "DetailSampler":
                    detltex = imgnode
                elif param.name == "TintPaletteSampler":
                    tintpal = imgnode
                elif param.name == "TextureSamplerDiffPal":
                    diffpal = imgnode
                elif param.name == "distanceMapSampler":
                    texture = imgnode
                    is_distance_map = True
                elif param.name in ("DiffuseSampler2", "DiffuseExtraSampler"):
                    texture2 = imgnode
                else:
                    if not texture:
                        texture = imgnode
            case (ShaderParameterType.FLOAT |
                  ShaderParameterType.FLOAT2 |
                  ShaderParameterType.FLOAT3 |
                  ShaderParameterType.FLOAT4 |
                  ShaderParameterType.FLOAT4X4 |
                  ShaderParameterType.SAMPLER |
                  ShaderParameterType.CBUFFER):
                create_parameter_node(node_tree, param)
            case ShaderParameterType.UNKNOWN:
                continue
            case _:
                raise Exception(f"Unknown shader parameter! {param.type=} {param.name=}")

    use_diff = True if texture else False
    use_diff2 = True if texture2 else False
    use_bump = True if bumptex else False
    use_spec = True if spectex else False
    use_detl = True if detltex else False
    use_tint = True if tintpal else False

    # Some shaders have TextureSamplerDiffPal but don't actually use it, so we only create palette
    # shader nodes on the specific shaders that use it
    use_palette = diffpal is not None and filename in ShaderManager.palette_shaders

    use_decal = shader.is_alpha or shader.is_decal or shader.is_cutout
    decalflag = 0
    blend_mode = "OPAQUE"
    if use_decal:
        # set blend mode
        if shader.is_cutout:
            blend_mode = "CLIP"
        else:
            blend_mode = "BLEND"
            decalflag = 1
        # set flags
        if filename == "decal_dirt.sps":
            decalflag = 2
        elif filename in {"decal_normal_only.sps", "mirror_decal.sps", "reflect_decal.sps"}:
            decalflag = 3
        elif filename in {"decal_spec_only.sps", "spec_decal.sps"}:
            decalflag = 4
        elif filename == "decal_amb_only.sps":
            decalflag = 5
        elif filename in {"vehicle_badges.sps", "vehicle_decal.sps"}:
            decalflag = 1  # badges and decals need to multiply the texture alpha by the Color 1 Alpha component
        elif filename.startswith("vehicle_"):
            # Don't treat any other alpha vehicle shaders as decals (e.g. lightsemissive or vehglass).
            # Particularly problematic with lightsemissive as Color 1 Alpha component contains the light ID,
            # which previously was being incorrectly used to multiply the texture alpha.
            use_decal = False

    is_emissive = True if filename in ShaderManager.em_shaders else False

    if not use_decal:
        if use_diff:
            if use_diff2:
                link_diffuses(b, texture, texture2)
            else:
                link_diffuse(b, texture)
    else:
        create_decal_nodes(b, texture, decalflag)

    if use_bump:
        if use_detl:
            link_detailed_normal(b, bumptex, detltex, spectex)
        else:
            link_normal(b, bumptex)
    if use_spec:
        link_specular(b, spectex)
    else:
        bsdf.inputs["Specular IOR Level"].default_value = 0

    if use_tint:
        create_tint_nodes(b, texture)

    if use_palette:
        create_diff_palette_nodes(b, diffpal, texture)

    if is_emissive:
        create_emissive_nodes(b)

    is_water = filename in ShaderManager.water_shaders
    if is_water:
        create_water_nodes(b)

    if is_distance_map:
        blend_mode = "BLEND"
        create_distance_map_nodes(b, texture)

    is_veh_shader = filename in ShaderManager.veh_paints
    if is_veh_shader:
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Coat Weight"].default_value = 1.0

    # link value parameters
    link_value_shader_parameters(b)

    if bpy.app.version < (4, 2, 0):
        mat.blend_method = blend_mode
    else:
        mat.surface_render_method = "BLENDED" if blend_mode != "OPAQUE" else "DITHERED"


def create_terrain_shader(b: ShaderBuilder):
    shader = b.shader
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links

    ts1 = None
    ts2 = None
    ts3 = None
    ts4 = None
    bs1 = None
    bs2 = None
    bs3 = None
    bs4 = None
    tm = None

    for param in shader.parameters:
        match param.type:
            case ShaderParameterType.TEXTURE:
                imgnode = create_image_node(node_tree, param)
                if param.name == "TextureSampler_layer0":
                    ts1 = imgnode
                elif param.name == "TextureSampler_layer1":
                    ts2 = imgnode
                elif param.name == "TextureSampler_layer2":
                    ts3 = imgnode
                elif param.name == "TextureSampler_layer3":
                    ts4 = imgnode
                elif param.name == "BumpSampler_layer0":
                    bs1 = imgnode
                elif param.name == "BumpSampler_layer1":
                    bs2 = imgnode
                elif param.name == "BumpSampler_layer2":
                    bs3 = imgnode
                elif param.name == "BumpSampler_layer3":
                    bs4 = imgnode
                elif param.name == "lookupSampler":
                    tm = imgnode
            case (ShaderParameterType.FLOAT |
                  ShaderParameterType.FLOAT2 |
                  ShaderParameterType.FLOAT3 |
                  ShaderParameterType.FLOAT4 |
                  ShaderParameterType.FLOAT4X4):
                create_parameter_node(node_tree, param)
            case _:
                raise Exception(f"Unknown shader parameter! {param.type=} {param.name=}")

    mixns = []
    for _ in range(8 if tm else 7):
        mix = node_tree.nodes.new("ShaderNodeMixRGB")
        mixns.append(mix)

    seprgb = node_tree.nodes.new("ShaderNodeSeparateRGB")
    if shader.is_terrain_mask_only:
        links.new(tm.outputs[0], seprgb.inputs[0])
    else:
        attr_c1 = node_tree.nodes.new("ShaderNodeAttribute")
        attr_c1.attribute_name = get_color_attr_name(1)
        links.new(attr_c1.outputs[0], mixns[0].inputs[1])
        links.new(attr_c1.outputs[0], mixns[0].inputs[2])

        attr_c0 = node_tree.nodes.new("ShaderNodeAttribute")
        attr_c0.attribute_name = get_color_attr_name(0)
        links.new(attr_c0.outputs[3], mixns[0].inputs[0])
        links.new(mixns[0].outputs[0], seprgb.inputs[0])

    # t1 / t2
    links.new(seprgb.outputs[2], mixns[1].inputs[0])
    links.new(ts1.outputs[0], mixns[1].inputs[1])
    links.new(ts2.outputs[0], mixns[1].inputs[2])

    # t3 / t4
    links.new(seprgb.outputs[2], mixns[2].inputs[0])
    links.new(ts3.outputs[0], mixns[2].inputs[1])
    links.new(ts4.outputs[0], mixns[2].inputs[2])

    links.new(seprgb.outputs[1], mixns[3].inputs[0])
    links.new(mixns[1].outputs[0], mixns[3].inputs[1])
    links.new(mixns[2].outputs[0], mixns[3].inputs[2])

    links.new(mixns[3].outputs[0], bsdf.inputs["Base Color"])

    if bs1:
        links.new(seprgb.outputs[2], mixns[4].inputs[0])
        links.new(bs1.outputs[0], mixns[4].inputs[1])
        links.new(bs2.outputs[0], mixns[4].inputs[2])

        links.new(seprgb.outputs[2], mixns[5].inputs[0])
        links.new(bs3.outputs[0], mixns[5].inputs[1])
        links.new(bs4.outputs[0], mixns[5].inputs[2])

        links.new(seprgb.outputs[1], mixns[6].inputs[0])
        links.new(mixns[4].outputs[0], mixns[6].inputs[1])
        links.new(mixns[5].outputs[0], mixns[6].inputs[2])

        nrm = node_tree.nodes.new("ShaderNodeNormalMap")
        links.new(mixns[6].outputs[0], nrm.inputs[1])
        links.new(nrm.outputs[0], bsdf.inputs["Normal"])

    # assign lookup sampler last so that it overwrites any socket connections
    if tm:
        uv_map1 = node_tree.nodes[get_uv_map_name(1)]
        links.new(uv_map1.outputs[0], tm.inputs[0])
        links.new(tm.outputs[0], mixns[0].inputs[1])

    # link value parameters
    bsdf.inputs["Specular IOR Level"].default_value = 0
    link_value_shader_parameters(b)


def create_shader(filename: str, game: SollumzGame = SollumzGame.GTA, in_place_material: Optional[bpy.types.Material] = None) -> bpy.types.Material:
    # from ..sollumz_preferences import get_addon_preferences
    # preferences = get_addon_preferences(bpy.context)
    # if preferences.experimental_shader_expressions:
    #     from .shader_materials_v2 import create_shader
    #     return create_shader(filename)

    shader = ShaderManager.find_shader(filename, game)
    if shader is None:
        raise AttributeError(f"Shader '{filename}' does not exist!")

    filename = shader.filename  # in case `filename` was hashed initially
    base_name = shader.base_name
    material_name = filename.replace(".sps", "")

    if in_place_material and in_place_material.use_nodes:
        # If creating the shader in an existing material, setup the node tree to its default state
        current_node_tree = in_place_material.node_tree
        current_node_tree.nodes.clear()
        material_ouput = current_node_tree.nodes.new("ShaderNodeOutputMaterial")
        bsdf = current_node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        current_node_tree.links.new(bsdf.outputs["BSDF"], material_ouput.inputs["Surface"])

        # If the material had a default name based on its current shader, replace it with the new shader name
        import re
        current_filename = in_place_material.shader_properties.filename
        if (
            in_place_material.sollum_type == MaterialType.SHADER and
            current_filename and
            re.match(rf"{current_filename.replace('.sps', '')}(\.\d\d\d)?", in_place_material.name)
        ):
            in_place_material.name = material_name

    mat = in_place_material or bpy.data.materials.new(material_name)
    mat.sollum_type = MaterialType.SHADER
    mat.sollum_game_type = game
    mat.use_nodes = True
    mat.shader_properties.name = base_name
    mat.shader_properties.filename = filename
    if game == SollumzGame.GTA:
        mat.shader_properties.renderbucket = RenderBucket(shader.render_bucket).name
    elif game == SollumzGame.RDR:
        if isinstance(shader.render_bucket, int):
            render_bucket = shader.render_bucket
        else:
            render_bucket = shader.render_bucket[0]
        render_bucket = int(str(render_bucket), 16) & 0x7F
        mat.shader_properties.renderbucket = RenderBucket(render_bucket).name

    bsdf, material_output = find_bsdf_and_material_output(mat)
    assert material_output is not None, "ShaderNodeOutputMaterial not found in default node_tree!"
    assert bsdf is not None, "ShaderNodeBsdfPrincipled not found in default node_tree!"

    builder = ShaderBuilder(shader=shader,
                            filename=filename,
                            material=mat,
                            node_tree=mat.node_tree,
                            material_output=material_output,
                            bsdf=bsdf)

    create_uv_map_nodes(builder)

    if shader.is_terrain:
        if game == SollumzGame.GTA:
            create_terrain_shader(builder)
        elif game == SollumzGame.RDR:
             RDR_create_terrain_shader(builder)
    elif filename in ShaderManager.rdr_standard_2lyr:
         RDR_create_2lyr_shader(builder)
    else:
        if game == SollumzGame.GTA:
            create_basic_shader_nodes(builder)
        elif game == SollumzGame.RDR:
            RDR_create_basic_shader_nodes(builder)

    if shader.is_uv_animation_supported:
        add_global_anim_uv_nodes(mat)

    if game == SollumzGame.GTA and shader.filename.startswith("vehicle_"):
        # Add additionals node to support vehicle render preview features
        if shader.filename == "vehicle_lightsemissive.sps":
            add_vehicle_lights_emissive_toggle_nodes(builder)

        if "matDiffuseColor" in shader.parameter_map:
            add_vehicle_body_color_nodes(builder)

        if "DirtSampler" in shader.parameter_map:
            add_vehicle_dirt_nodes(builder)

    link_uv_map_nodes_to_textures(builder)

    organize_node_tree(builder)

    return mat


VEHICLE_PREVIEW_NODE_LIGHT_EMISSIVE_TOGGLE = [
    f"PreviewLightID{light_id}Toggle" for light_id in range(MIN_VEHICLE_LIGHT_ID, MAX_VEHICLE_LIGHT_ID+1)
]
VEHICLE_PREVIEW_NODE_BODY_COLOR = [
    f"PreviewBodyColor{paint_layer_id}" for paint_layer_id in range(8)
]
VEHICLE_PREVIEW_NODE_DIRT_LEVEL = "PreviewDirtLevel"
VEHICLE_PREVIEW_NODE_DIRT_WETNESS = "PreviewDirtWetness"
VEHICLE_PREVIEW_NODE_DIRT_COLOR = "PreviewDirtColor"


def add_vehicle_lights_emissive_toggle_nodes(builder: ShaderBuilder):
    em = try_get_node_by_cls(builder.node_tree, bpy.types.ShaderNodeEmission)
    if not em:
        return

    shader_expr = vehicle_lights_emissive_toggles()
    compiled_shader_expr = compile_expr(builder.material.node_tree, shader_expr)

    builder.node_tree.links.new(compiled_shader_expr.output, em.inputs["Strength"])


def vehicle_lights_emissive_toggles() -> expr.ShaderExpr:
    from ..shared.shader_expr.builtins import (
        color_attribute,
        float_param,
        value,
    )

    attr_c0 = color_attribute(get_color_attr_name(0))
    emissive_mult = float_param("emissiveMultiplier")

    eps = 0.001
    final_flag = 0.0
    for light_id in range(MIN_VEHICLE_LIGHT_ID, MAX_VEHICLE_LIGHT_ID+1):
        light_id_normalized = light_id / 255
        flag_toggle = value(VEHICLE_PREVIEW_NODE_LIGHT_EMISSIVE_TOGGLE[light_id], default_value=1.0)
        flag_lower_bound = attr_c0.alpha > (light_id_normalized - eps)
        flag_upper_bound = attr_c0.alpha < (light_id_normalized + eps)
        flag = flag_toggle * flag_lower_bound * flag_upper_bound
        final_flag += flag

    final_mult = emissive_mult * final_flag
    return final_mult


def add_vehicle_dirt_nodes(builder: ShaderBuilder):
    shader_expr = vehicle_dirt_overlay()
    compiled_shader_expr = compile_expr(builder.material.node_tree, shader_expr)

    orig_base_color = builder.bsdf.inputs["Base Color"].links[0].from_socket
    builder.node_tree.links.new(orig_base_color, compiled_shader_expr.node.inputs["A"])
    builder.node_tree.links.new(compiled_shader_expr.output, builder.bsdf.inputs["Base Color"])


def vehicle_dirt_overlay() -> expr.ShaderExpr:
    from ..shared.shader_expr.builtins import (
        tex,
        value,
        vec,
        vec_value,
        mix_color,
        map_range,
    )

    # Shader parameters 'dirtLevelMod' and 'dirtColor' are set at runtime. So ignore them and instead use our own values
    dirt_color = vec_value(VEHICLE_PREVIEW_NODE_DIRT_COLOR, default_value=(70/255, 60/255, 50/255))
    dirt_level = value(VEHICLE_PREVIEW_NODE_DIRT_LEVEL, default_value=0.0)
    dirt_wetness = value(VEHICLE_PREVIEW_NODE_DIRT_WETNESS, default_value=0.0)

    dirt_tex = tex("DirtSampler", None)  # will be linked to the correct UV map by `link_uv_map_nodes_to_textures`

    dirt_level = dirt_level * map_range(
        dirt_wetness,
        0.0, 1.0,
        dirt_tex.color.r, dirt_tex.color.g
    )

    dirt_mod = map_range(dirt_wetness, 0.0, 1.0, 1.0, 0.6)

    dirt_color = dirt_color * dirt_mod

    # this vec(0) will be replaced by the shader base color
    final_color = mix_color(vec(0.0, 0.0, 0.0), dirt_color, dirt_level)

    # TODO: increase alpha on vehglass

    return final_color


def add_vehicle_body_color_nodes(builder: ShaderBuilder):
    shader_expr = vehicle_body_color()
    compiled_shader_expr = compile_expr(builder.material.node_tree, shader_expr)

    orig_base_color = builder.bsdf.inputs["Base Color"].links[0].from_socket
    builder.node_tree.links.new(orig_base_color, compiled_shader_expr.node.inputs[0])
    builder.node_tree.links.new(compiled_shader_expr.output, builder.bsdf.inputs["Base Color"])


def vehicle_body_color() -> expr.ShaderExpr:
    from ..shared.shader_expr.builtins import (
        param,
        vec,
        vec_value,
    )

    mat_diffuse_color = param("matDiffuseColor").vec

    final_paint_layer_color = vec(0.0, 0.0, 0.0)
    eps = 0.0001
    enable_paint_layer = (mat_diffuse_color.x > (2.0 - eps)) * (mat_diffuse_color.x < (2.0 + eps))
    for paint_layer_id in range(1, 7+1):
        default_color = (1.0, 1.0, 1.0)
        if paint_layer_id == 5:
            default_color = (0.5, 0.5, 0.5)
        body_color = vec_value(VEHICLE_PREVIEW_NODE_BODY_COLOR[paint_layer_id], default_value=default_color)

        use_this_paint_layer = (mat_diffuse_color.y > (paint_layer_id - eps)) * \
            (mat_diffuse_color.y < (paint_layer_id + eps))

        final_paint_layer_color += body_color * use_this_paint_layer

    final_body_color = final_paint_layer_color * enable_paint_layer + mat_diffuse_color * (1.0 - enable_paint_layer)

    return vec(1.0, 1.0, 1.0) * final_body_color  # this vec(1) will be replaced by the shader base color
