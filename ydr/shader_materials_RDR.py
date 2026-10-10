from typing import NamedTuple
import bpy
from ..sollumz_properties import SollumzGame
from ..cwxml.shader import (
    ShaderManager,
    ShaderDef,
    ShaderParameterType,
)

from .shader_materials_SHARED import ShaderBuilder, create_image_node, create_parameter_node, link_value_shader_parameters, try_get_node, get_uv_map_name
from ..shared.shader_nodes import SzShaderNodeParameter


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
    mix.name = "tint_mix_node"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 1.0
    links.new(attr.outputs["Color"], mix.inputs[2])
    links.new(diffuse_tex.outputs[0], mix.inputs[1])
    links.new(mix.outputs[0], bsdf.inputs["Base Color"])


def RDR_create_basic_shader_nodes(b: ShaderBuilder):
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
                imgnode.texture_properties.index = param.index
                imgnode.texture_properties.game_type = SollumzGame.RDR
                if param.name == "diffusetex":
                    texture = imgnode
                elif param.name in {"bumptex", "bumptexture", "lyr0normaltex"}:
                    bumptex = imgnode
                elif param.name in {"speculartex", "speculartexture", "lyr0materialatex"}:
                    spectex = imgnode
                elif param.name == "DetailSampler":
                    detltex = imgnode
                elif param.name == "tintpalettetex":
                    tintpal = imgnode
                elif param.name == "distanceMapSampler":
                    texture = imgnode
                    is_distance_map = True
                elif param.name in {"diffusetex2", "lyr1diffusetex"}:
                    texture2 = imgnode
                elif param.name == "lyr0diffusetex":
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
        # TODO: materials for different types of RDR decal shaders, these are GTA shaders
        #if filename == "decal_dirt.sps":
        #    decalflag = 2
        #elif filename in {"decal_normal_only.sps", "mirror_decal.sps", "reflect_decal.sps"}:
        #    decalflag = 3
        #elif filename in {"decal_spec_only.sps", "spec_decal.sps"}:
        #    decalflag = 4

    # is_emissive = True if filename in ShaderManager.em_shaders else False

    diffuse_texture = texture
    if use_diff:
        if use_diff2:
            texture = link_diffuses(b, texture, texture2)
        else:
            node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    link_alpha(b, diffuse_texture)


    if use_tint and texture:
        create_tint_nodes(b, texture)

    if use_bump:
        link_normal(b, bumptex)
        # if use_detl:
        #     link_detailed_normal(b, bumptex, detltex, spectex)
        # else:
        #     link_normal(b, bumptex)
    if use_spec:
        link_specular(b, spectex)
    else:
        bsdf.inputs["Roughness"].default_value = 1.0

    # if is_emissive:
    #     create_emissive_nodes(b)

    # is_water = filename in ShaderManager.water_shaders
    # if is_water:
    #     create_water_nodes(b)

    # if is_distance_map:
    #     blend_mode = "BLEND"
    #     create_distance_map_nodes(b, texture)

    # is_veh_shader = filename in ShaderManager.veh_paints
    # if is_veh_shader:
    #     bsdf.inputs["Metallic"].default_value = 1.0
    #     bsdf.inputs["Coat Weight"].default_value = 1.0

    # link value parameters
    link_rdr_value_parameters(b)
    link_emission(b, diffuse_texture)

    if bpy.app.version < (4, 2, 0):
        mat.blend_method = blend_mode
    else:
        mat.surface_render_method = "BLENDED" if blend_mode != "OPAQUE" else "DITHERED"


def link_specular(b: ShaderBuilder, spctex):
    link_material_channels(b, spctex.outputs["Color"])


def link_rdr_value_parameters(b: ShaderBuilder):
    link_value_shader_parameters(b)
    # Bumpiness already scales decoded XY in the RDR normal reconstruction.
    for node in b.node_tree.nodes:
        if node.bl_idname == "ShaderNodeNormalMap" and node.name.startswith("RDR Tangent Normal"):
            for link in list(node.inputs["Strength"].links):
                b.node_tree.links.remove(link)
            node.inputs["Strength"].default_value = 1.0


def link_diffuses(b: ShaderBuilder, tex1, tex2):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links

    vertex_color_node = node_tree.nodes.new("ShaderNodeAttribute")
    vertex_color_node.attribute_name = "Color 1"

    dirt_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    dirt_mix.inputs["Fac"].default_value = 1.0
    dirt_mix.blend_type = "MULTIPLY"
    links.new(vertex_color_node.outputs["Alpha"], dirt_mix.inputs["Color1"])
    links.new(tex2.outputs["Alpha"], dirt_mix.inputs["Color2"])

    rgb2 = node_tree.nodes.new("ShaderNodeMixRGB")

    rgb2.blend_type = "OVERLAY"
    links.new(tex1.outputs["Color"], rgb2.inputs["Color1"])
    links.new(tex2.outputs["Color"], rgb2.inputs["Color2"])
    links.new(dirt_mix.outputs["Color"], rgb2.inputs["Fac"])

    links.new(rgb2.outputs["Color"], bsdf.inputs["Base Color"])

    return rgb2


def RDR_create_2lyr_shader(b: ShaderBuilder):
    shader = b.shader
    filename = b.filename
    mat = b.material
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links

    lyr0diffusetex = None
    lyr1diffusetex = None
    lyr0normaltex = None
    lyr1normaltex = None
    lyr0materialatex = None
    lyr1materialatex = None
    lyr0materialbtex = None
    lyr1materialbtex = None
    dirtdiffusetex = None
    controltexturetex = None
    aotexturetex = None
    tintpalettetex = None

    for param in shader.parameters:
        match param.type:
            case ShaderParameterType.TEXTURE:
                imgnode = create_image_node(node_tree, param)
                imgnode.texture_properties.index = param.index
                imgnode.texture_properties.game_type = SollumzGame.RDR
                if param.name == "lyr0diffusetex":
                    lyr0diffusetex = imgnode
                elif param.name == "lyr1diffusetex":
                    lyr1diffusetex = imgnode
                elif param.name == "lyr0normaltex":
                    lyr0normaltex = imgnode
                elif param.name == "lyr1normaltex":
                    lyr1normaltex = imgnode
                elif param.name == "lyr0materialatex":
                    lyr0materialatex = imgnode
                elif param.name == "lyr1materialatex":
                    lyr1materialatex = imgnode
                elif param.name == "lyr0materialbtex":
                    lyr0materialbtex = imgnode
                elif param.name == "lyr1materialbtex":
                    lyr1materialbtex = imgnode
                elif param.name == "dirtdiffusetex":
                    dirtdiffusetex = imgnode
                elif param.name == "controltexturetex":
                    controltexturetex = imgnode
                elif param.name == "aotexturetex": ## in 80% cases blank
                    aotexturetex = imgnode
                elif param.name == "tintpalettetex":
                    tintpalettetex = imgnode
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



    vertex_color2_node = node_tree.nodes.new("ShaderNodeAttribute")
    vertex_color2_node.attribute_name = "Color 2"

    vertex_color1_node = node_tree.nodes.new("ShaderNodeAttribute")
    vertex_color1_node.attribute_name = "Color 1"

    separate_rgb = node_tree.nodes.new("ShaderNodeSeparateColor")
    links.new(vertex_color2_node.outputs["Color"], separate_rgb.inputs["Color"])

    control_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    control_mix.inputs["Fac"].default_value = 1
    links.new(controltexturetex.outputs["Color"], control_mix.inputs["Color1"])
    links.new(separate_rgb.outputs["Red"], control_mix.inputs["Color2"])

    something_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    something_mix.blend_type = "BURN"
    links.new(control_mix.outputs["Color"], something_mix.inputs["Color1"])
    something_mix.inputs["Fac"].default_value = 0.25

    contrast = node_tree.nodes.new("ShaderNodeBrightContrast")
    links.new(something_mix.outputs["Color"], contrast.inputs["Color"])
    contrast.inputs[1].default_value = 1
    contrast.inputs[2].default_value = 2

    # Mix _mb by vertex color
    matb_lyr_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(lyr0materialbtex.outputs["Alpha"], matb_lyr_mix.inputs["Color1"])
    links.new(lyr1materialbtex.outputs["Alpha"], matb_lyr_mix.inputs["Color2"])
    links.new(separate_rgb.outputs["Red"], matb_lyr_mix.inputs["Fac"])

    links.new(matb_lyr_mix.outputs["Color"], something_mix.inputs["Color2"])


    # Apply tint before dirt diffuse
    attr = node_tree.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "TintColor"

    tint_mix0 = node_tree.nodes.new("ShaderNodeMixRGB")
    tint_mix0.name = "tint_mix_node0"
    tint_mix0.blend_type = "MULTIPLY"
    links.new(attr.outputs["Color"], tint_mix0.inputs[2])
    links.new(lyr0diffusetex.outputs["Color"], tint_mix0.inputs[1])

    #Mix tint with not tinted by mb alpha
    matb_lyr_tint_mix0 = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(lyr0diffusetex.outputs["Color"], matb_lyr_tint_mix0.inputs["Color1"])
    links.new(tint_mix0.outputs["Color"], matb_lyr_tint_mix0.inputs["Color2"])
    links.new(lyr0materialbtex.outputs["Alpha"], matb_lyr_tint_mix0.inputs["Fac"])
    

    tint_mix1 = node_tree.nodes.new("ShaderNodeMixRGB")
    tint_mix1.name = "tint_mix_node1"
    tint_mix1.blend_type = "MULTIPLY"
    links.new(attr.outputs["Color"], tint_mix1.inputs[2])
    links.new(lyr1diffusetex.outputs["Color"], tint_mix1.inputs[1])


    #Mix tint with not tinted by mb alpha
    matb_lyr_tint_mix1 = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(lyr1diffusetex.outputs["Color"], matb_lyr_tint_mix1.inputs["Color1"])
    links.new(tint_mix1.outputs["Color"], matb_lyr_tint_mix1.inputs["Color2"])
    links.new(lyr1materialbtex.outputs["Alpha"], matb_lyr_tint_mix1.inputs["Fac"])
    

    # Mix diffuses by vertex color
    diff_lyr_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(matb_lyr_tint_mix0.outputs["Color"], diff_lyr_mix.inputs["Color1"])
    links.new(matb_lyr_tint_mix1.outputs["Color"], diff_lyr_mix.inputs["Color2"])
    links.new(contrast.outputs["Color"], diff_lyr_mix.inputs["Fac"])


    # Mix dirt by vertex alpha
    dirt_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    dirt_mix.inputs["Fac"].default_value = 1.0
    dirt_mix.blend_type = "MULTIPLY"
    links.new(vertex_color1_node.outputs["Alpha"], dirt_mix.inputs["Color1"])
    links.new(dirtdiffusetex.outputs["Alpha"], dirt_mix.inputs["Color2"])

    # Mix tinted diffuse with dirt
    lyr_dirt_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    lyr_dirt_mix.blend_type = "OVERLAY"
    links.new(diff_lyr_mix.outputs["Color"], lyr_dirt_mix.inputs["Color1"])
    links.new(dirtdiffusetex.outputs["Color"], lyr_dirt_mix.inputs["Color2"])
    links.new(dirt_mix.outputs["Color"], lyr_dirt_mix.inputs["Fac"])

    # Mix _ma by vertex color
    mata_lyr_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(lyr0materialatex.outputs["Color"], mata_lyr_mix.inputs["Color1"])
    links.new(lyr1materialatex.outputs["Color"], mata_lyr_mix.inputs["Color2"])
    links.new(contrast.outputs["Color"], mata_lyr_mix.inputs["Fac"])

    link_material_channels(b, mata_lyr_mix.outputs["Color"])
    links.new(lyr_dirt_mix.outputs["Color"], bsdf.inputs["Base Color"])

    # Mix normal by vertex color and link
    normal_lyr_mix = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(lyr0normaltex.outputs["Color"], normal_lyr_mix.inputs["Color1"])
    links.new(lyr1normaltex.outputs["Color"], normal_lyr_mix.inputs["Color2"])
    links.new(contrast.outputs["Color"], normal_lyr_mix.inputs["Fac"])
    link_normal(b, normal_lyr_mix)

    # link value parameters
    link_rdr_value_parameters(b)



def RDR_create_terrain_shader(b: ShaderBuilder):
    shader = b.shader
    filename = b.filename
    mat = b.material
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
                imgnode.texture_properties.index = param.index
                imgnode.texture_properties.game_type = SollumzGame.RDR
                if param.name == "diffusetexture_layer0":
                    ts1 = imgnode
                elif param.name == "diffusetexture_layer1":
                    ts2 = imgnode
                elif param.name == "diffusetexture_layer2":
                    ts3 = imgnode
                elif param.name == "diffusetexture_layer3":
                    ts4 = imgnode
                elif param.name == "bumptexture_layer0":
                    bs1 = imgnode
                elif param.name == "bumptexture_layer1":
                    bs2 = imgnode
                elif param.name == "bumptexture_layer2":
                    bs3 = imgnode
                elif param.name == "bumptexture_layer3":
                    bs4 = imgnode
                elif param.name == "lookuptexture":
                    tm = imgnode
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
    mixns = []
    for _ in range(8 if tm else 7):
        mix = node_tree.nodes.new("ShaderNodeMixRGB")
        mixns.append(mix)

    seprgb = node_tree.nodes.new("ShaderNodeSeparateColor")
    seprgb.mode = "RGB"
    if shader.is_terrain_mask_only:
        links.new(tm.outputs[0], seprgb.inputs["Color"])
    else:
        # attr_c1 = node_tree.nodes.new("ShaderNodeAttribute")
        # attr_c1.attribute_name = "Color 2"
        # links.new(attr_c1.outputs[0], mixns[0].inputs[1])
        # links.new(attr_c1.outputs[0], mixns[0].inputs[2])

        attr_c0 = node_tree.nodes.new("ShaderNodeAttribute")
        attr_c0.attribute_name = "Color 1"
        links.new(attr_c0.outputs[3], mixns[0].inputs[0])
        links.new(attr_c0.outputs[0], mixns[0].inputs[2])
        links.new(mixns[0].outputs[0], seprgb.inputs["Color"])

    # t1 / t2

    invert_red = node_tree.nodes.new("ShaderNodeInvert")
    links.new(seprgb.outputs["Red"], invert_red.inputs[1])

    links.new(invert_red.outputs[0], mixns[1].inputs[0])
    links.new(ts1.outputs[0], mixns[1].inputs[1])
    links.new(ts2.outputs[0], mixns[1].inputs[2])

    # t3 / t4
    links.new(seprgb.outputs["Green"], mixns[2].inputs[0])
    links.new(ts3.outputs[0], mixns[2].inputs[1])
    links.new(ts4.outputs[0], mixns[2].inputs[2])

    links.new(seprgb.outputs["Blue"], mixns[3].inputs[0])
    links.new(mixns[1].outputs[0], mixns[3].inputs[1])
    links.new(mixns[2].outputs[0], mixns[3].inputs[2])

    links.new(mixns[3].outputs[0], bsdf.inputs["Base Color"])

    if bs1:
        links.new(invert_red.outputs[0], mixns[4].inputs[0])
        links.new(bs1.outputs[0], mixns[4].inputs[1])
        links.new(bs2.outputs[0], mixns[4].inputs[2])

        links.new(seprgb.outputs["Green"], mixns[5].inputs[0])
        links.new(bs3.outputs[0], mixns[5].inputs[1])
        links.new(bs4.outputs[0], mixns[5].inputs[2])

        links.new(seprgb.outputs["Blue"], mixns[6].inputs[0])
        links.new(mixns[4].outputs[0], mixns[6].inputs[1])
        links.new(mixns[5].outputs[0], mixns[6].inputs[2])

        link_normal(b, mixns[6])

    # assign lookup sampler last so that it overwrites any socket connections
    if tm:
        uv_map1 = node_tree.nodes[get_uv_map_name(0)]
        links.new(uv_map1.outputs[0], tm.inputs[0])
        links.new(tm.outputs[0], mixns[0].inputs[1])

    # link value parameters
    bsdf.inputs["Roughness"].default_value = 1.0
    link_rdr_value_parameters(b)


PED_SMOOTHNESS_SHADERS = {
    "ped", "ped_standard", "ped_standard_cloth", "ped_standard_hair",
    "ped_standard_hair_lod", "ped_standard_fur", "ped_standard_skin",
    "ped_standard_alpha", "ped_standard_cutout", "ped_standard_eye",
    "ped_standard_eye_emissive", "ped_standard_eye_retroreflect",
    "ped_standard_wrinkle", "ped_standard_eye_cap", "ped_standard_hair_alpha",
    "ped_standard_hair_normal", "ped_standard_hat", "ped_standard_cloth_wrinkle",
    "ped_standard_hair_cloth", "ped_slod_tint", "ped_skin", "ped_hair_cutout_alpha",
    "ped_standard_skin_tattoo_bake", "ped_standard_skin_tint",
    "ped_emissive_additive_alpha_flipbook", "horse_standard",
}


def math_node(b, operation, *values, name=None, clamp=False):
    node = b.node_tree.nodes.new("ShaderNodeMath")
    node.operation = operation
    node.use_clamp = clamp
    if name:
        node.name = node.label = name
    for socket, value in zip(node.inputs, values):
        if isinstance(value, (float, int)):
            socket.default_value = value
        else:
            b.node_tree.links.new(value, socket)
    return node.outputs[0]


def RDR_link_parameter_nodes(b):
    """Custom parameter nodes are export data, not executable Blender shaders.

    Bridge each linked component through a native Value node with a driver,
    keeping imported values and UI edits live in Cycles.
    """
    nodes, links = b.node_tree.nodes, b.node_tree.links
    for parameter in list(nodes):
        if not isinstance(parameter, SzShaderNodeParameter):
            continue
        for index, output in enumerate(parameter.outputs):
            destinations = [link.to_socket for link in output.links]
            if not destinations:
                continue
            value = nodes.new("ShaderNodeValue")
            value.name = value.label = f"RDR Preview {parameter.name} {index}"
            value.outputs[0].default_value = output.default_value
            driver = value.outputs[0].driver_add("default_value").driver
            driver.type = "AVERAGE"
            variable = driver.variables.new()
            variable.name = "parameter"
            variable.type = "SINGLE_PROP"
            variable.targets[0].id_type = "NODETREE"
            variable.targets[0].id = b.node_tree
            variable.targets[0].data_path = f"{parameter.path_from_id()}.outputs[{index}].default_value"
            for destination in destinations:
                links.new(value.outputs[0], destination)


def RDR_link_terrain_uvs(b):
    if not b.shader.is_terrain:
        return
    nodes, links = b.node_tree.nodes, b.node_tree.links
    uv_nodes = []
    for index in range(3):
        name = get_uv_map_name(index)
        uv = nodes.get(name)
        if uv is None:
            uv = nodes.new("ShaderNodeUVMap")
            uv.name = uv.label = uv.uv_map = name
        uv_nodes.append(uv.outputs["UV"])
    scale_bias = nodes.get("uvscalebias")
    scaled = uv_nodes[0]
    if scale_bias:
        scale = nodes.new("ShaderNodeCombineXYZ")
        bias = nodes.new("ShaderNodeCombineXYZ")
        for component, source in (("X", "X"), ("Y", "Y")):
            links.new(scale_bias.outputs[source], scale.inputs[component])
        links.new(scale_bias.outputs["Z"], bias.inputs["X"])
        links.new(scale_bias.outputs["W"], bias.inputs["Y"])
        transform = nodes.new("ShaderNodeVectorMath")
        transform.operation = "MULTIPLY_ADD"
        transform.name = transform.label = "RDR Terrain UV Scale Bias"
        links.new(scaled, transform.inputs[0])
        links.new(scale.outputs[0], transform.inputs[1])
        links.new(bias.outputs[0], transform.inputs[2])
        scaled = transform.outputs[0]
    uvset = nodes.get("uvset")
    for layer, component in enumerate(("X", "Y", "Z", "W")):
        vector = scaled
        if uvset and uvset.outputs.get(component):
            for index in (2, 3):
                selector = nodes.new("ShaderNodeMixRGB")
                is_set = math_node(b, "COMPARE", uvset.outputs[component], float(index), 0.01)
                links.new(is_set, selector.inputs["Fac"])
                links.new(vector, selector.inputs["Color1"])
                links.new(uv_nodes[index - 1], selector.inputs["Color2"])
                vector = selector.outputs[0]
        for prefix in ("diffusetexture", "bumptexture", "materialmapatexture"):
            texture = nodes.get(f"{prefix}_layer{layer}")
            if texture:
                links.new(vector, texture.inputs["Vector"])


def link_material_channels(b, color):
    split = b.node_tree.nodes.new("ShaderNodeSeparateColor")
    split.name = split.label = "RDR Material Channels"
    b.node_tree.links.new(color, split.inputs["Color"])
    if b.shader.base_name.startswith("terrain_lod"):
        roughness = math_node(b, "SUBTRACT", 1.0, split.outputs["Green"],
                              name="RDR Terrain LOD Roughness", clamp=True)
        b.bsdf.inputs["Metallic"].default_value = 0.0
    elif b.shader.base_name == "terrain_slod":
        roughness = split.outputs["Red"]
        b.bsdf.inputs["Metallic"].default_value = 0.0
    elif b.shader.base_name in PED_SMOOTHNESS_SHADERS:
        smoothness = math_node(b, "MULTIPLY", split.outputs["Red"], 0.5,
                               name="RDR Ped Smoothness", clamp=True)
        roughness = math_node(b, "SUBTRACT", 1.0, smoothness,
                              name="RDR Ped Roughness", clamp=True)
        b.bsdf.inputs["Metallic"].default_value = 0.0
    else:
        b.node_tree.links.new(split.outputs["Red"], b.bsdf.inputs["Metallic"])
        roughness = split.outputs["Green"]
    b.node_tree.links.new(roughness, b.bsdf.inputs["Roughness"])


def link_normal(b, texture, strength=None, uv_index=0):
    """ RDR normals store XY, not XYZ. Convert DirectX Y to Blender's convention
    after reconstructing Z, so unused blue/alpha cannot distort the normal.
    """
    nodes, links = b.node_tree.nodes, b.node_tree.links
    if b.shader.base_name.startswith("terrain_lod") or b.shader.base_name == "terrain_slod":
        decode = nodes.new("ShaderNodeVectorMath")
        decode.operation = "MULTIPLY_ADD"
        decode.inputs[1].default_value = (2.0, 2.0, 2.0)
        decode.inputs[2].default_value = (-1.0, -1.0, -1.0)
        links.new(texture.outputs["Color"], decode.inputs[0])
        links.new(decode.outputs[0], b.bsdf.inputs["Normal"])
        return
    split = nodes.new("ShaderNodeSeparateColor")
    links.new(texture.outputs["Color"], split.inputs["Color"])
    x = math_node(b, "MULTIPLY_ADD", split.outputs["Red"], 2.0, -1.0)
    y = math_node(b, "MULTIPLY_ADD", split.outputs["Green"], 2.0, -1.0)
    length2 = math_node(b, "ADD", math_node(b, "MULTIPLY", x, x),
                        math_node(b, "MULTIPLY", y, y))
    z = math_node(b, "SQRT", math_node(b, "ABSOLUTE",
                  math_node(b, "SUBTRACT", 1.0, length2)))
    if strength is None:
        bump = nodes.get("bumpiness")
        strength = bump.outputs["X"] if bump else 1.0
    vector = nodes.new("ShaderNodeCombineXYZ")
    links.new(math_node(b, "MULTIPLY", x, strength), vector.inputs["X"])
    links.new(math_node(b, "MULTIPLY", math_node(b, "MULTIPLY", y, -1.0), strength), vector.inputs["Y"])
    links.new(z, vector.inputs["Z"])
    normalize = nodes.new("ShaderNodeVectorMath")
    normalize.operation = "NORMALIZE"
    links.new(vector.outputs[0], normalize.inputs[0])
    encode = nodes.new("ShaderNodeVectorMath")
    encode.operation = "MULTIPLY_ADD"
    encode.name = encode.label = "RDR Reconstructed Normal"
    encode.inputs[1].default_value = (0.5, 0.5, 0.5)
    encode.inputs[2].default_value = (0.5, 0.5, 0.5)
    links.new(normalize.outputs[0], encode.inputs[0])
    normal = nodes.new("ShaderNodeNormalMap")
    normal.name = normal.label = "RDR Tangent Normal"
    normal.uv_map = get_uv_map_name(uv_index)
    links.new(encode.outputs[0], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], b.bsdf.inputs["Normal"])


def link_emission(b, texture):
    if "emissive" not in b.shader.base_name or texture is None:
        return
    param = b.node_tree.nodes.get("intensity") or b.node_tree.nodes.get("emissivemultiplier")
    if param is None:
        return
    links = b.node_tree.links
    links.new(texture.outputs["Color"], b.bsdf.inputs["Emission Color"])
    strength = math_node(b, "MULTIPLY", param.outputs["X"], 0.025,
                         name="RDR Emission Strength", clamp=True)
    links.new(strength, b.bsdf.inputs["Emission Strength"])


def link_alpha(b, texture):
    """Keep packed diffuse alpha out of opaque materials."""
    if texture is None or not (b.shader.is_alpha or b.shader.is_decal or b.shader.is_cutout):
        b.bsdf.inputs["Alpha"].default_value = 1.0
        return
    alpha = texture.outputs["Alpha"]
    scale = b.node_tree.nodes.get("alphascale")
    if scale:
        alpha = math_node(b, "MULTIPLY", alpha, scale.outputs["X"], clamp=True)
    if b.shader.is_cutout:
        # Blender's default clip reference; native shader-specific alpha tests
        # (including stochastic foliage) require additional shader evidence.
        alpha = math_node(b, "GREATER_THAN", alpha, 0.5, name="RDR Alpha Cutout")
    b.node_tree.links.new(alpha, b.bsdf.inputs["Alpha"])
