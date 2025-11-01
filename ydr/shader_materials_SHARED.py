from typing import Optional, NamedTuple
import bpy
from ..cwxml.shader import (
    ShaderManager,
    ShaderDef,
    ShaderParameterType,
    ShaderParameterSubtype,
    ShaderParameterFloatDef,
    ShaderParameterFloat2Def,
    ShaderParameterFloat3Def,
    ShaderParameterFloat4Def,
    ShaderParameterFloat4x4Def,
    ShaderParameterSamplerDef,
    ShaderParameterCBufferDef
)

from ..tools.meshhelper import get_uv_map_name, get_color_attr_name
from ..shared.shader_nodes import SzShaderNodeParameter, SzShaderNodeParameterDisplayType


class ShaderBuilder(NamedTuple):
    shader: ShaderDef
    filename: str
    material: bpy.types.Material
    node_tree: bpy.types.ShaderNodeTree
    bsdf: bpy.types.ShaderNodeBsdfPrincipled
    material_output: bpy.types.ShaderNodeOutputMaterial


def try_get_node(node_tree: bpy.types.NodeTree, name: str) -> Optional[bpy.types.Node]:
    """Gets a node by its name. Returns `None` if not found.
    Note, names are localized by Blender or can changed by the user, so
    this should only be used for names that Sollumz sets explicitly.
    """
    return node_tree.nodes.get(name, None)


def try_get_node_by_cls(node_tree: bpy.types.NodeTree, node_cls: type) -> Optional[bpy.types.Node]:
    """Gets a node by its type. Returns `None` if not found."""
    for node in node_tree.nodes:
        if isinstance(node, node_cls):
            return node

    return None


def get_child_nodes(node):
    child_nodes = []
    for input in node.inputs:
        for link in input.links:
            child = link.from_node
            if child in child_nodes:
                continue
            else:
                child_nodes.append(child)
    return child_nodes


def group_image_texture_nodes(node_tree):
    image_texture_nodes = [node for node in node_tree.nodes if node.type == "TEX_IMAGE"]

    if not image_texture_nodes:
        return

    image_texture_nodes.sort(key=lambda node: node.location.y)

    avg_x = min([node.location.x for node in image_texture_nodes])

    # adjust margin to change gap in between img nodes
    margin = 275
    current_y = min([node.location.y for node in image_texture_nodes]) - margin
    for node in image_texture_nodes:
        current_y += margin
        node.location.x = avg_x
        node.location.y = current_y

    # how far to the left the img nodes are
    group_offset = 400
    for node in image_texture_nodes:
        node.location.x -= group_offset
        node.location.y += group_offset


def group_uv_map_nodes(node_tree):
    uv_map_nodes = [node for node in node_tree.nodes if node.type == "UVMAP"]

    if not uv_map_nodes:
        return

    uv_map_nodes.sort(key=lambda node: node.name, reverse=True)

    avg_x = min([node.location.x for node in uv_map_nodes])

    # adjust margin to change gap in between UV map nodes
    margin = 120
    current_y = min([node.location.y for node in uv_map_nodes]) - margin
    for node in uv_map_nodes:
        current_y += margin
        node.location.x = avg_x
        node.location.y = current_y

    # how far to the left the UV map nodes are
    group_offset = 900
    for node in uv_map_nodes:
        node.location.x -= group_offset
        node.location.y += group_offset


def get_loose_nodes(node_tree):
    loose_nodes = []
    for node in node_tree.nodes:
        no = False
        ni = False
        for output in node.outputs:
            for link in output.links:
                if link.to_node is not None and link.from_node is not None:
                    no = True
                    break
        for input in node.inputs:
            for link in input.links:
                if link.to_node is not None and link.from_node is not None:
                    ni = True
                    break
        if no == False and ni == False:
            loose_nodes.append(node)
    return loose_nodes


def organize_node_tree(b: ShaderBuilder):
    mo = b.material_output
    mo.location.x = 0
    mo.location.y = 0
    organize_node(mo)
    organize_loose_nodes(b.node_tree, 1000, 0)
    group_image_texture_nodes(b.node_tree)
    group_uv_map_nodes(b.node_tree)


def organize_node(node):
    child_nodes = get_child_nodes(node)
    if len(child_nodes) < 0:
        return

    level = node.location.y
    for child in child_nodes:
        child.location.x = node.location.x - 300
        child.location.y = level
        level -= 300
        organize_node(child)


def organize_loose_nodes(node_tree, start_x, start_y):
    loose_nodes = get_loose_nodes(node_tree)
    if len(loose_nodes) == 0:
        return

    grid_x = start_x
    grid_y = start_y

    for i, node in enumerate(loose_nodes):
        if i % 4 == 0:
            grid_x = start_x
            grid_y -= 150

        node.location.x = grid_x + node.width / 2
        node.location.y = grid_y - node.height / 2

        grid_x += node.width + 25


def get_tint_sampler_node(mat: bpy.types.Material) -> Optional[bpy.types.ShaderNodeTexImage]:
    nodes = mat.node_tree.nodes
    for node in nodes:
        if (node.name == "TintPaletteSampler" or node.name == "tintpalettetex") and isinstance(node, bpy.types.ShaderNodeTexImage):
            return node

    return None


def create_tinted_shader_graph(obj: bpy.types.Object):
    attribute_to_remove = []
    modifiers_to_remove = []

    for mod in obj.modifiers:
        if mod.type == "NODES":
            for mat in obj.data.materials:
                tint_node = get_tint_sampler_node(mat)
                if tint_node is not None:
                    output_id = mod.node_group.interface.items_tree.get("Tint Color")
                    if output_id:
                        attr_name = mod[output_id.identifier + "_attribute_name"]
                        if attr_name and attr_name in obj.data.attributes:
                            attribute_to_remove.append(attr_name)

                    modifiers_to_remove.append(mod)
                    break

    for attr_name in attribute_to_remove:
        obj.data.attributes.remove(obj.data.attributes[attr_name])

    for mod in modifiers_to_remove:
        obj.modifiers.remove(mod)

    tint_mats = get_tinted_mats(obj)

    if not tint_mats:
        return

    for mat in tint_mats:
        tint_sampler_node = get_tint_sampler_node(mat)
        palette_img = tint_sampler_node.image

        if tint_sampler_node is None:
            continue

        if mat.shader_properties.filename in ShaderManager.tint_colour1_shaders:
            input_color_attr_name = get_color_attr_name(1)
        else:
            input_color_attr_name = get_color_attr_name(0)

        tint_color_attr_name = f"TintColor ({palette_img.name})" if palette_img else "TintColor"
        # Attribute creation fails with names that are too long. Truncate to max name length 64 characters, -4 so
        # Blender still has space to append '.012' in case of duplicated names.
        tint_color_attr_name = tint_color_attr_name[:64-4]

        tint_color_attr = obj.data.attributes.new(name=tint_color_attr_name, type="BYTE_COLOR", domain="CORNER")

        rename_tint_attr_node(mat.node_tree, name=tint_color_attr.name)

        create_tint_geom_modifier(obj, tint_color_attr.name, input_color_attr_name, palette_img, mat.name)


def create_tint_geom_modifier(
    obj: bpy.types.Object,
    tint_color_attr_name: str,
    input_color_attr_name: Optional[str],
    palette_img: Optional[bpy.types.Image],
    shader_name: str,
) -> bpy.types.NodesModifier:
    tnt_ng = create_tinted_geometry_graph()
    mod = obj.modifiers.new("GeometryNodes", "NODES")
    mod.name = shader_name
    mod.node_group = tnt_ng

    # set input / output variables
    input_id = tnt_ng.interface.items_tree["Color Attribute"].identifier
    mod[input_id] = input_color_attr_name if input_color_attr_name is not None else ""

    input_palette_id = tnt_ng.interface.items_tree["Palette Texture"].identifier
    mod[input_palette_id] = palette_img

    output_id = tnt_ng.interface.items_tree["Tint Color"].identifier
    mod[output_id + "_attribute_name"] = tint_color_attr_name
    mod[output_id + "_use_attribute"] = True

    return mod


def rename_tint_attr_node(node_tree: bpy.types.NodeTree, name: str):
    assert name.startswith("TintColor"), "Tint attributes should always be prefixed with 'TintColor'"
    for node in node_tree.nodes:
        if not isinstance(node, bpy.types.ShaderNodeAttribute) or not node.attribute_name.startswith("TintColor"):
            continue

        node.attribute_name = name
        return


def get_tinted_mats(obj: bpy.types.Object) -> list[bpy.types.Material]:
    if obj.data is None or not obj.data.materials:
        return []

    return [mat for mat in obj.data.materials if is_tint_material(mat)]


def obj_has_tint_mats(obj: bpy.types.Object) -> bool:
    if not obj.data.materials:
        return False

    mat = obj.data.materials[0]
    return is_tint_material(mat)


def is_tint_material(mat: bpy.types.Material) -> bool:
    return get_tint_sampler_node(mat) is not None


def link_geos(links, node1, node2):
    links.new(node1.inputs["Geometry"], node2.outputs["Geometry"])


def create_tinted_geometry_graph():  # move to blenderhelper.py?
    gnt = bpy.data.node_groups.new(name="TintGeometry", type="GeometryNodeTree")
    input = gnt.nodes.new("NodeGroupInput")
    output = gnt.nodes.new("NodeGroupOutput")

    # Create the necessary sockets for the node group
    gnt.interface.new_socket("Geometry", socket_type="NodeSocketGeometry", in_out="INPUT")
    gnt.interface.new_socket("Geometry", socket_type="NodeSocketGeometry", in_out="OUTPUT")
    gnt.interface.new_socket("Color Attribute", socket_type="NodeSocketString", in_out="INPUT")
    in_palette = gnt.interface.new_socket("Palette W (Preview)",
                                          description="Index of the tint palette to preview. Has no effect on export",
                                          socket_type="NodeSocketInt", in_out="INPUT")
    in_palette.min_value = 0
    in_palette2 = gnt.interface.new_socket("Palette H (Preview)",
                                          description="Index of the tint palette to preview. Has no effect on export",
                                          socket_type="NodeSocketInt", in_out="INPUT")
    in_palette2.min_value = 0
    gnt.interface.new_socket("Palette Texture", description="Should be the same as 'TintPaletteSampler' of the material",
                             socket_type="NodeSocketImage", in_out="INPUT")
    gnt.interface.new_socket("Tint Color", socket_type="NodeSocketColor", in_out="OUTPUT")

    # link input / output node to create geometry socket
    cptn = gnt.nodes.new("GeometryNodeCaptureAttribute")
    cptn.domain = "CORNER"
    if bpy.app.version >= (4, 2, 0):
        cpt_name = "UV"
        cpt_attr = cptn.capture_items.new("VECTOR", cpt_name)
        cpt_attr.data_type = "FLOAT_VECTOR"
    else:
        cpt_name = "Attribute"
        cptn.data_type = "FLOAT_VECTOR"
    gnt.links.new(input.outputs["Geometry"], cptn.inputs["Geometry"])
    gnt.links.new(cptn.outputs["Geometry"], output.inputs["Geometry"])

    # create and link texture node
    txtn = gnt.nodes.new("GeometryNodeImageTexture")
    txtn.interpolation = "Closest"
    gnt.links.new(input.outputs["Palette Texture"], txtn.inputs["Image"])
    gnt.links.new(cptn.outputs[cpt_name], txtn.inputs["Vector"])
    gnt.links.new(txtn.outputs["Color"], output.inputs["Tint Color"])

    pal_img_info = gnt.nodes.new("GeometryNodeImageInfo")
    gnt.links.new(input.outputs["Palette Texture"], pal_img_info.inputs["Image"])

    # Read color attribute. We check if there is an isolated attribute for the input color attribute. If so, we
    # read from the isolated attribute instead of the input, so the tint updates as the user paints.
    from ..editor_tools.vertex_paint.isolate import ISOLATED_ATTR_FORMAT
    color_attr = gnt.nodes.new("GeometryNodeInputNamedAttribute")
    color_attr.data_type = "FLOAT_COLOR"
    gnt.links.new(input.outputs["Color Attribute"], color_attr.inputs["Name"])
    last_color_output = color_attr.outputs["Attribute"]
    for r, g, b in (
        # All possible isolation states with blue channel. Note: alpha cannot be isolated along with RGB, we can ignore it
        ("", "", "B"),
        ("", "G", "B"),
        ("R", "", "B"),
        ("R", "G", "B"),
    ):
        isolated_attr_prefix = gnt.nodes.new("FunctionNodeInputString")
        isolated_attr_prefix.string = ISOLATED_ATTR_FORMAT.format(r, g, b, "", "")
        str_join = gnt.nodes.new("GeometryNodeStringJoin")
        isolated_attr = gnt.nodes.new("GeometryNodeInputNamedAttribute")
        isolated_attr.data_type = "FLOAT_COLOR"
        switch = gnt.nodes.new("GeometryNodeSwitch")
        switch.input_type = "RGBA"
        gnt.links.new(input.outputs["Color Attribute"], str_join.inputs["Strings"])
        gnt.links.new(isolated_attr_prefix.outputs["String"], str_join.inputs["Strings"])
        gnt.links.new(str_join.outputs["String"], isolated_attr.inputs["Name"])
        gnt.links.new(isolated_attr.outputs["Exists"], switch.inputs["Switch"])
        gnt.links.new(isolated_attr.outputs["Attribute"], switch.inputs["True"])
        gnt.links.new(last_color_output, switch.inputs["False"])
        last_color_output = switch.outputs["Output"]

    # separate colour0
    sepn = gnt.nodes.new("ShaderNodeSeparateXYZ")
    gnt.links.new(last_color_output, sepn.inputs["Vector"])

    # create math nodes
    mathns = []
    for i in range(9):
        mathns.append(gnt.nodes.new("ShaderNodeMath"))

    # Convert color attribute from linear to sRGB
    # Sollumz imports it as sRGB but accessing in the node tree gives you linear color
    # c1
    mathns[0].operation = "LESS_THAN"
    gnt.links.new(sepn.outputs[2], mathns[0].inputs[0])
    # NOTE: the correct constant here should be 0.0031308 but the loss of precision due to the linear->sRGB conversion
    #       causes it not to recover the correct UV.x value on some pixels, sampling neighboring pixels. With 0.004, it
    #       works better in our specific case (UVs for pixels between 0-256) and seems to work for all palette pixels.
    mathns[0].inputs[1].default_value = 0.004
    mathns[1].operation = "SUBTRACT"
    gnt.links.new(mathns[0].outputs[0], mathns[1].inputs[1])
    mathns[1].inputs[0].default_value = 1.0

    # r1
    mathns[2].operation = "MULTIPLY"
    gnt.links.new(sepn.outputs[2], mathns[2].inputs[0])
    mathns[2].inputs[1].default_value = 12.920
    mathns[3].operation = "MULTIPLY"
    gnt.links.new(mathns[2].outputs[0], mathns[3].inputs[0])
    gnt.links.new(mathns[0].outputs[0], mathns[3].inputs[1])

    # r2
    mathns[4].operation = "POWER"
    gnt.links.new(sepn.outputs[2], mathns[4].inputs[0])
    mathns[4].inputs[1].default_value = 0.417
    mathns[5].operation = "MULTIPLY"
    gnt.links.new(mathns[4].outputs[0], mathns[5].inputs[0])
    mathns[5].inputs[1].default_value = 1.055
    mathns[6].operation = "SUBTRACT"
    gnt.links.new(mathns[5].outputs[0], mathns[6].inputs[0])
    mathns[6].inputs[1].default_value = 0.055
    mathns[7].operation = "MULTIPLY"
    gnt.links.new(mathns[6].outputs[0], mathns[7].inputs[0])
    gnt.links.new(mathns[1].outputs[0], mathns[7].inputs[1])

    # add r1 and r2
    mathns[8].operation = "ADD"
    gnt.links.new(mathns[3].outputs[0], mathns[8].inputs[0])
    gnt.links.new(mathns[7].outputs[0], mathns[8].inputs[1])

    # Select palette row
    # uv.y = (palette_preview_index + 0.5) / img.height
    # uv.y = ((uv.y - 1) * -1)   ; flip_uv
    pal_add = gnt.nodes.new("ShaderNodeMath")
    pal_add.operation = "ADD"
    pal_add.inputs[1].default_value = 0.5
    pal_div = gnt.nodes.new("ShaderNodeMath")
    pal_div.operation = "DIVIDE"
    pal_flip_uv_sub = gnt.nodes.new("ShaderNodeMath")
    pal_flip_uv_sub.operation = "SUBTRACT"
    pal_flip_uv_sub.inputs[1].default_value = 1.0
    pal_flip_uv_mult = gnt.nodes.new("ShaderNodeMath")
    pal_flip_uv_mult.operation = "MULTIPLY"
    pal_flip_uv_mult.inputs[1].default_value = -1.0

    gnt.links.new(input.outputs["Palette H (Preview)"], pal_add.inputs[1])
    gnt.links.new(pal_add.outputs[0], pal_div.inputs[0])
    gnt.links.new(pal_img_info.outputs["Height"], pal_div.inputs[1])
    gnt.links.new(pal_div.outputs[0], pal_flip_uv_sub.inputs[0])
    gnt.links.new(pal_flip_uv_sub.outputs[0], pal_flip_uv_mult.inputs[0])

    preview = gnt.nodes.new("ShaderNodeMath")
    preview.operation = "DIVIDE"
    gnt.links.new(input.outputs["Palette W (Preview)"], preview.inputs[0])
    preview.inputs[1].default_value = 256

    compare = gnt.nodes.new("FunctionNodeCompare")
    compare.data_type = "FLOAT"
    gnt.links.new(preview.outputs[0], compare.inputs[0])

    switch = gnt.nodes.new("GeometryNodeSwitch")
    switch.input_type = "FLOAT"
    gnt.links.new(compare.outputs[0], switch.inputs["Switch"])
    gnt.links.new(preview.outputs[0], switch.inputs["True"])
    gnt.links.new(mathns[8].outputs[0], switch.inputs["False"])

    # create and link vector
    comb = gnt.nodes.new("ShaderNodeCombineRGB")
    gnt.links.new(switch.outputs[0], comb.inputs[0])
    gnt.links.new(pal_flip_uv_mult.outputs[0], comb.inputs[1])
    gnt.links.new(comb.outputs[0], cptn.inputs["Value"])

    return gnt


def create_image_node(node_tree, param) -> bpy.types.ShaderNodeTexImage:
    imgnode = node_tree.nodes.new("ShaderNodeTexImage")
    imgnode.name = param.name
    imgnode.label = param.name
    imgnode.is_sollumz = True
    return imgnode


def create_parameter_node(
    node_tree: bpy.types.NodeTree,
    param: (
        ShaderParameterFloatDef | ShaderParameterFloat2Def | ShaderParameterFloat3Def | ShaderParameterFloat4Def |
        ShaderParameterFloat4x4Def | ShaderParameterSamplerDef | ShaderParameterCBufferDef
    )
) -> SzShaderNodeParameter:
    node: SzShaderNodeParameter = node_tree.nodes.new(SzShaderNodeParameter.bl_idname)
    node.name = param.name
    node.label = node.name

    display_type = SzShaderNodeParameterDisplayType.DEFAULT
    match param.type:
        case ShaderParameterType.FLOAT:
            cols, rows = 1, max(1, param.count)
            if param.count == 0 and param.subtype == ShaderParameterSubtype.BOOL:
                display_type = SzShaderNodeParameterDisplayType.BOOL
        case ShaderParameterType.FLOAT2:
            cols, rows = 2, max(1, param.count)
        case ShaderParameterType.FLOAT3:
            cols, rows = 3, max(1, param.count)
            if param.count == 0 and param.subtype == ShaderParameterSubtype.RGB:
                display_type = SzShaderNodeParameterDisplayType.RGB
        case ShaderParameterType.FLOAT4:
            cols, rows = 4, max(1, param.count)
            if param.count == 0 and param.subtype == ShaderParameterSubtype.RGBA:
                display_type = SzShaderNodeParameterDisplayType.RGBA
        case ShaderParameterType.FLOAT4X4:
            cols, rows = 4, 4
        case ShaderParameterType.SAMPLER:
            cols, rows = 1, 1
            display_type = SzShaderNodeParameterDisplayType.DEFAULT
        case ShaderParameterType.CBUFFER:
            match param.value_type:
                case ShaderParameterType.FLOAT:
                    cols, rows = 1, 1
                case ShaderParameterType.FLOAT2:
                    cols, rows = 2, 1
                case ShaderParameterType.FLOAT3:
                    cols, rows = 3, 1
                case ShaderParameterType.FLOAT4:
                    cols, rows = 4, max(1, param.count)

    if param.hidden:
        display_type = SzShaderNodeParameterDisplayType.HIDDEN_IN_UI
    node.set_size(cols, rows)
    node.set_display_type(display_type)

    if rows == 1 and param.type in {ShaderParameterType.FLOAT, ShaderParameterType.FLOAT2, ShaderParameterType.FLOAT3, 
                                    ShaderParameterType.FLOAT4, ShaderParameterType.CBUFFER, ShaderParameterType.SAMPLER}:
        node.set("X", param.x)
        if cols > 1:
            node.set("Y", param.y)
        if cols > 2:
            node.set("Z", param.z)
        if cols > 3:
            node.set("W", param.w)

        if param.type == ShaderParameterType.CBUFFER:
            node.extra_property.buffer = param.buffer
            node.extra_property.offset = param.offset
        elif param.type == ShaderParameterType.SAMPLER:
            node.extra_property.index = param.index

    return node


def link_diffuse(b: ShaderBuilder, imgnode):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    links.new(imgnode.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(imgnode.outputs["Alpha"], bsdf.inputs["Alpha"])


def link_normal(b: ShaderBuilder, nrmtex):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    normalmap = node_tree.nodes.new("ShaderNodeNormalMap")

    rgb_curves = create_normal_invert_node(node_tree)

    links.new(nrmtex.outputs["Color"], rgb_curves.inputs["Color"])
    links.new(rgb_curves.outputs["Color"], normalmap.inputs["Color"])
    links.new(normalmap.outputs["Normal"], bsdf.inputs["Normal"])


def create_normal_invert_node(node_tree: bpy.types.NodeTree):
    """Create RGB curves node that inverts that green channel of normal maps"""
    rgb_curves: bpy.types.ShaderNodeRGBCurve = node_tree.nodes.new(
        "ShaderNodeRGBCurve")

    green_curves = rgb_curves.mapping.curves[1]
    green_curves.points[0].location = (0, 1)
    green_curves.points[1].location = (1, 0)

    return rgb_curves


def create_decal_nodes(b: ShaderBuilder, texture, decalflag):
    node_tree = b.node_tree
    output = b.material_output
    bsdf = b.bsdf
    links = node_tree.links
    mix = node_tree.nodes.new("ShaderNodeMixShader")
    trans = node_tree.nodes.new("ShaderNodeBsdfTransparent")
    links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])

    if decalflag == 0:  # cutout
        # Handle alpha test logic for cutout shaders.
        # TODO: alpha test nodes specific to cutout shaders without HardAlphaBlend
        # - trees shaders have AlphaTest and AlphaScale parameters
        # - grass_batch has gAlphaTest parameter
        # - ped_fur? has cutout render bucket but no alpha test-related parameter afaict
        if (
            (hard_alpha_blend := try_get_node(node_tree, "HardAlphaBlend")) and
            isinstance(hard_alpha_blend, SzShaderNodeParameter)
        ):
            # The HardAlphaBlend parameter is used to slightly smooth out the cutout edges.
            # 1.0 = hard edges, 0.0 = softer edges (some transparency in the edges)
            # Negative values invert the cutout but I don't think that's the intended use.
            ALPHA_REF = 90.0 / 255.0
            MIN_ALPHA_REF = 1.0 / 255.0
            sub = node_tree.nodes.new("ShaderNodeMath")
            sub.operation = "SUBTRACT"
            sub.inputs[1].default_value = ALPHA_REF
            div = node_tree.nodes.new("ShaderNodeMath")
            div.operation = "DIVIDE"
            div.inputs[1].default_value = (1.0 - ALPHA_REF) * 0.1
            map_alpha_blend = node_tree.nodes.new("ShaderNodeMapRange")
            map_alpha_blend.clamp = False
            map_alpha_blend.inputs["From Min"].default_value = 0.0
            map_alpha_blend.inputs["From Max"].default_value = 1.0
            alpha_gt = node_tree.nodes.new("ShaderNodeMath")
            alpha_gt.operation = "GREATER_THAN"
            alpha_gt.inputs[1].default_value = MIN_ALPHA_REF
            mul_alpha_test = node_tree.nodes.new("ShaderNodeMath")
            mul_alpha_test.operation = "MULTIPLY"

            links.new(texture.outputs["Alpha"], sub.inputs[0])
            links.new(sub.outputs["Value"], div.inputs[0])
            links.new(hard_alpha_blend.outputs["X"], map_alpha_blend.inputs["Value"])
            links.new(texture.outputs["Alpha"], map_alpha_blend.inputs["To Min"])
            links.new(div.outputs["Value"], map_alpha_blend.inputs["To Max"])
            links.new(map_alpha_blend.outputs["Result"], alpha_gt.inputs[0])
            links.new(map_alpha_blend.outputs["Result"], mul_alpha_test.inputs[0])
            links.new(alpha_gt.outputs["Value"], mul_alpha_test.inputs[1])
            links.new(mul_alpha_test.outputs["Value"], mix.inputs["Fac"])
        else:
            # Fallback to simple alpha test
            # discard if alpha <= 0.5, else opaque
            alpha_gt = node_tree.nodes.new("ShaderNodeMath")
            alpha_gt.operation = "GREATER_THAN"
            alpha_gt.inputs[1].default_value = 0.5
            links.new(texture.outputs["Alpha"], alpha_gt.inputs[0])
            links.new(alpha_gt.outputs["Value"], mix.inputs["Fac"])
    elif decalflag == 1:
        vcs = node_tree.nodes.new("ShaderNodeVertexColor")
        vcs.layer_name = get_color_attr_name(0)
        multi = node_tree.nodes.new("ShaderNodeMath")
        multi.operation = "MULTIPLY"
        links.new(vcs.outputs["Alpha"], multi.inputs[0])
        links.new(texture.outputs["Alpha"], multi.inputs[1])
        links.new(multi.outputs["Value"], mix.inputs["Fac"])
    elif decalflag == 2:  # decal_dirt.sps
        # Here, the diffuse sampler represents an alpha map. DirtDecalMask indicates which channels to consider. Actual
        # color stored in the color0 attribute.
        #   alpha = dot(diffuseColor, DirtDecalMask)
        #   alpha *= color0.a
        #   baseColor = color0.rgb
        dirt_decal_mask_xyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
        dirt_decal_mask = node_tree.nodes["DirtDecalMask"]
        dot_diffuse_mask = node_tree.nodes.new("ShaderNodeVectorMath")
        dot_diffuse_mask.operation = "DOT_PRODUCT"
        mult_alpha_color0a = node_tree.nodes.new("ShaderNodeMath")
        mult_alpha_color0a.operation = "MULTIPLY"
        color0_attr = node_tree.nodes.new("ShaderNodeVertexColor")
        color0_attr.layer_name = get_color_attr_name(0)

        links.new(dirt_decal_mask.outputs["X"], dirt_decal_mask_xyz.inputs["X"])
        links.new(dirt_decal_mask.outputs["Y"], dirt_decal_mask_xyz.inputs["Y"])
        links.new(dirt_decal_mask.outputs["Z"], dirt_decal_mask_xyz.inputs["Z"])

        links.new(texture.outputs["Color"], dot_diffuse_mask.inputs[0])
        links.new(dirt_decal_mask_xyz.outputs["Vector"], dot_diffuse_mask.inputs[1])

        links.new(dot_diffuse_mask.outputs["Value"], mult_alpha_color0a.inputs[0])
        links.new(color0_attr.outputs["Alpha"], mult_alpha_color0a.inputs[1])

        links.new(mult_alpha_color0a.outputs["Value"], mix.inputs["Fac"])

        links.new(color0_attr.outputs["Color"], bsdf.inputs["Base Color"])
    elif decalflag == 5:  # decal_amb_only.sps
        ambient_decal_mask_xyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
        ambient_decal_mask = node_tree.nodes["AmbientDecalMask"]
        dot_diffuse_mask = node_tree.nodes.new("ShaderNodeVectorMath")
        dot_diffuse_mask.operation = "DOT_PRODUCT"
        mult_alpha_color0a = node_tree.nodes.new("ShaderNodeMath")
        mult_alpha_color0a.operation = "MULTIPLY"
        color0_attr = node_tree.nodes.new("ShaderNodeVertexColor")
        invert_color = node_tree.nodes.new("ShaderNodeInvert")
        color0_attr.layer_name = get_color_attr_name(0)

        links.new(ambient_decal_mask.outputs["X"], ambient_decal_mask_xyz.inputs["X"])
        links.new(ambient_decal_mask.outputs["Y"], ambient_decal_mask_xyz.inputs["Y"])
        links.new(ambient_decal_mask.outputs["Z"], ambient_decal_mask_xyz.inputs["Z"])

        links.new(texture.outputs["Color"], invert_color.inputs[1])
        links.new(invert_color.outputs["Color"], dot_diffuse_mask.inputs[0])
        links.new(ambient_decal_mask_xyz.outputs["Vector"], dot_diffuse_mask.inputs[1])

        links.new(dot_diffuse_mask.outputs["Value"], mult_alpha_color0a.inputs[0])
        links.new(color0_attr.outputs["Alpha"], mult_alpha_color0a.inputs[1])

        links.new(mult_alpha_color0a.outputs["Value"], mix.inputs["Fac"])

        links.new(color0_attr.outputs["Color"], bsdf.inputs["Base Color"])

    links.new(trans.outputs["BSDF"], mix.inputs[1])
    links.remove(bsdf.outputs["BSDF"].links[0])
    links.new(bsdf.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])


def link_value_shader_parameters(b: ShaderBuilder):
    shader = b.shader
    node_tree = b.node_tree
    links = node_tree.links

    bsdf = b.bsdf
    bmp = None
    spec_im = None
    spec_fm = None
    em_m = None
    spec_m = None
    lyr0tint = None
    lyr1tint = None

    for param in shader.parameters:
        if param.name == "bumpiness":
            bmp = node_tree.nodes["bumpiness"]
        elif param.name == "specularIntensityMult":
            spec_im = node_tree.nodes["specularIntensityMult"]
        elif param.name == "specularFalloffMult":
            spec_fm = node_tree.nodes["specularFalloffMult"]
        elif param.name == "emissiveMultiplier":
            em_m = node_tree.nodes["emissiveMultiplier"]
        elif param.name == "specMapIntMask":
            spec_m = node_tree.nodes["specMapIntMask"]
        elif param.name == "lyr0tint":
            lyr0tint = node_tree.nodes["lyr0tint"]
        elif param.name == "lyr1tint":
            lyr1tint = node_tree.nodes["lyr1tint"]

    if bmp:
        nm = try_get_node_by_cls(node_tree, bpy.types.ShaderNodeNormalMap)
        if nm:
            links.new(bmp.outputs["X"], nm.inputs[0])
    if spec_im:
        spec = try_get_node(node_tree, "SpecSampler")
        if spec:
            map = node_tree.nodes.new("ShaderNodeMapRange")
            map.inputs[2].default_value = 1
            map.inputs[4].default_value = 1
            map.clamp = True
            mult = node_tree.nodes.new("ShaderNodeMath")
            mult.operation = "MULTIPLY"
            if spec_m:
                dot_prod = node_tree.nodes.new("ShaderNodeVectorMath")
                dot_prod.operation = "DOT_PRODUCT"
                links.new(dot_prod.inputs[0], spec.outputs[0])
                combine_xyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
                spec_mask = try_get_node(node_tree, "specMapIntMask")
                links.new(spec_mask.outputs["X"], combine_xyz.inputs["X"])
                links.new(spec_mask.outputs["Y"], combine_xyz.inputs["Y"])
                links.new(spec_mask.outputs["Z"], combine_xyz.inputs["Z"])
                links.new(combine_xyz.outputs[0], dot_prod.inputs[1])
                links.new(dot_prod.outputs["Value"], mult.inputs[0])
                links.new(map.outputs[0], mult.inputs[1])
                links.new(spec_im.outputs["X"], map.inputs[0])
                links.new(mult.outputs[0], bsdf.inputs["Specular IOR Level"])
            else:
                links.new(spec.outputs[0], mult.inputs[0])
                links.new(map.outputs[0], mult.inputs[1])
                links.new(spec_im.outputs["X"], map.inputs[0])
                links.new(mult.outputs[0], bsdf.inputs["Specular IOR Level"])

    if spec_fm:
        map = node_tree.nodes.new("ShaderNodeMapRange")
        map.inputs[2].default_value = 512
        map.inputs[3].default_value = 1
        map.inputs[4].default_value = 0
        map.clamp = True
        links.new(spec_fm.outputs["X"], map.inputs[0])
        links.new(map.outputs[0], bsdf.inputs["Roughness"])
    if em_m:
        em = try_get_node_by_cls(node_tree, bpy.types.ShaderNodeEmission)
        if em:
            links.new(em_m.outputs["X"], em.inputs[1])

    if lyr0tint:
        tint_mix_node0 = try_get_node(node_tree, "tint_mix_node0")
        if tint_mix_node0:
            tint0_multiply = node_tree.nodes.new("ShaderNodeMath")
            tint0_multiply.name = "tint_multiply_node0"
            tint0_multiply.operation = "MULTIPLY"        
            tint0_multiply.inputs[1].default_value = 0.95
            links.new(lyr0tint.outputs["X"], tint0_multiply.inputs[0])
            links.new(tint0_multiply.outputs[0], tint_mix_node0.inputs["Fac"])
    if lyr1tint:
        tint_mix_node1 = try_get_node(node_tree, "tint_mix_node1")
        if tint_mix_node1:
            tint1_multiply = node_tree.nodes.new("ShaderNodeMath")
            tint1_multiply.name = "tint_multiply_node1"
            tint1_multiply.operation = "MULTIPLY"        
            tint1_multiply.inputs[1].default_value = 0.95
            links.new(lyr1tint.outputs["X"], tint1_multiply.inputs[0])
            links.new(tint1_multiply.outputs[0], tint_mix_node1.inputs["Fac"])



def create_uv_map_nodes(b: ShaderBuilder):
    """Creates a ``ShaderNodeUVMap`` node for each UV map used in the shader."""
    shader = b.shader
    node_tree = b.node_tree

    used_uv_maps = set(shader.uv_maps.values())
    for uv_map_index in used_uv_maps:
        uv_map = get_uv_map_name(uv_map_index)
        node = node_tree.nodes.new("ShaderNodeUVMap")
        node.name = uv_map
        node.label = uv_map
        node.uv_map = uv_map


def link_uv_map_nodes_to_textures(b: ShaderBuilder):
    """For each texture node, links the corresponding UV map to its input UV if it hasn't been linked already."""
    shader = b.shader
    node_tree = b.node_tree


    for tex_name, uv_map_index in shader.uv_maps.items():
        tex_node = node_tree.nodes[tex_name]
        uv_map_node = node_tree.nodes[get_uv_map_name(uv_map_index)]

        if tex_node.inputs[0].is_linked:
            # texture already linked when creating the node tree, skip it
            continue

        if tex_name in ("diffusetexture_layer0", "diffusetexture_layer1", "diffusetexture_layer2", "diffusetexture_layer3", "bumptexture_layer0", "bumptexture_layer1", "bumptexture_layer2", "bumptexture_layer3"):
            vector_math = node_tree.nodes.new("ShaderNodeVectorMath")
            vector_math.operation = 'MULTIPLY'
            vector_math.name = 'Multiply'
            vector_math.inputs[1].default_value = (128,128,128)

            node_tree.links.new(uv_map_node.outputs[0], vector_math.inputs[0])
            node_tree.links.new(vector_math.outputs[0], tex_node.inputs[0])

        else:
            node_tree.links.new(uv_map_node.outputs[0], tex_node.inputs[0])
