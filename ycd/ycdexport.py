import bpy
from mathutils import Vector, Quaternion, Matrix
import math
import json
import re
from contextlib import contextmanager
from collections.abc import Iterator
import struct
from typing import Optional
from pathlib import Path
from xml.etree.ElementTree import tostring
from ..cwxml import clipdictionary as ycdxml
from .rdr_channels import build_scalar_channel, build_quaternion_channels
from ..sollumz_properties import SollumType, SollumzGame, import_export_current_game
from ..tools import jenkhash
from ..tools.blenderhelper import build_name_bone_map, build_bone_map
from ..tools.animationhelper import (
    Track,
    TrackFormat,
    TrackFormatMap,
    RDRTrackToXmlMap,
    rdr_track_to_xml,
    AnimationFlag,
    get_quantum_and_min_val,
    get_id_and_track_from_track_data_path,
    calculate_bone_space_transform_matrix,
    get_target_from_id,
    get_action_duration_frames,
    get_action_duration_secs,
    get_action_export_frame_count,
    action_fcurves,
)
from .properties import ClipAttribute, ClipTag, calculate_final_uv_transform_matrix

from .. import logger


def parse_uv_transform_data_path(data_path: str) -> tuple[int, str]:
    # data_path = '...uv_transforms[123].property'

    # trim up to 'uv_transforms'
    data_path = data_path[data_path.index("uv_transforms") + len("uv_transforms"):]

    # extract transform index
    index_start = data_path.index("[") + 1
    index_end = data_path.index("]", index_start)
    index = int(data_path[index_start:index_end])

    # extract property name
    prop_start = data_path.index(".", index_end) + 1
    prop = data_path[prop_start:]

    return index, prop


TrackFramesData = list[Vector] | list[Quaternion] | list[float]
SequenceItems = dict[int, dict[Track, TrackFramesData]]


@contextmanager
def animation_export_context(
    context: bpy.types.Context,
    rig: bpy.types.Object,
    action: bpy.types.Action,
) -> Iterator[None]:
    """Evaluate only the assigned Action and restore the target and scene afterward."""
    existed = rig.animation_data is not None
    data = rig.animation_data_create()
    old_action, old_slot, old_nla = data.action, getattr(data, "action_slot", None), data.use_nla
    frame, subframe = context.scene.frame_current, context.scene.frame_subframe
    poses = [(bone, bone.matrix_basis.copy()) for bone in rig.pose.bones]
    object_basis = rig.matrix_basis.copy()
    try:
        data.use_nla = False
        data.action = action
        if hasattr(data, "action_slot") and len(action.slots):
            data.action_slot = action.slots[0]
        for bone, _ in poses:
            bone.matrix_basis = Matrix.Identity(4)
        yield
    finally:
        data.action = old_action
        if old_action and old_slot:
            data.action_slot = old_slot
        data.use_nla = old_nla
        rig.matrix_basis = object_basis
        for bone, basis in poses:
            bone.matrix_basis = basis
        context.scene.frame_set(frame, subframe=subframe)
        if not existed:
            rig.animation_data_clear()


def validate_rdr_animation_name(name: str) -> None:
    if not re.fullmatch(r"[a-z0-9_@+\-]{1,200}", name):
        raise ValueError("Names require lowercase letters, digits, _, @, + or - (max 200).")


def get_rdr_bone_tag(bone: bpy.types.Bone) -> int:
    # Sollumz stores the original game tag here. Blender bone indices are not game tags.
    if "rdr2_bone_tag" in bone:
        tag = bone["rdr2_bone_tag"]
    elif hasattr(bone, "bone_properties"):
        tag = bone.bone_properties.tag
    else:
        raise ValueError(f"Bone '{bone.name}' has no RDR2 tag. Import an RDR armature with Sollumz.")
    if not isinstance(tag, int) or not 0 <= tag <= 65535:
        raise ValueError(f"Bone '{bone.name}' has an invalid tag.")
    return tag


def decompose_animation_transform(matrix: Matrix, label: str) -> tuple[Vector, Quaternion, Vector]:
    position, rotation, scale = matrix.decompose()
    rotation.normalize()
    rebuilt = Matrix.LocRotScale(position, rotation, scale)
    if max(abs(matrix[r][c] - rebuilt[r][c]) for r in range(4) for c in range(4)) > 1e-4:
        raise ValueError(f"{label}: shear cannot be represented by game animation tracks.")
    if matrix.determinant() <= 0:
        raise ValueError(f"{label}: mirrored or singular transforms are unsupported.")
    values = position, rotation, scale
    if not all(math.isfinite(v) for row in values for v in row):
        raise ValueError(f"{label}: transform contains non-finite values.")
    return values


def sequence_items_from_armature(
    context: bpy.types.Context,
    armature: bpy.types.Object,
    frame_start: float,
    frame_end: float,
    sample_step: float = 1.0,
    allow_empty: bool = False,
) -> SequenceItems:
    """Bake the assigned skeleton into native Sollumz bone/track sequence items."""
    if armature is None or armature.type != "ARMATURE":
        raise ValueError("Assign an RDR armature target to the Animation.")
    if armature.mode == "EDIT" or armature.data.pose_position != "POSE":
        raise ValueError("Use Object/Pose mode and the armature's Pose Position.")
    if not math.isfinite(sample_step) or sample_step <= 0:
        raise ValueError("Sample interval must be finite and positive.")
    intervals = (frame_end - frame_start) / sample_step
    if abs(intervals - round(intervals)) > 1e-4:
        raise ValueError("Frame range must contain a whole number of sample intervals.")
    frame_count = round(intervals) + 1
    if not 2 <= frame_count <= 65535:
        raise ValueError("Export range must contain 2..65535 frames, including the final sample.")
    fps = context.scene.render.fps / context.scene.render.fps_base / sample_step
    if not math.isfinite(fps) or not 0 < fps <= 1000:
        raise ValueError("Scene FPS must be finite and between 0 and 1000.")

    # The Animation target owns the exported skeleton, regardless of bone collections.
    tagged = sorted((get_rdr_bone_tag(bone), bone.name) for bone in armature.data.bones)
    if not tagged or len({tag for tag, _ in tagged}) != len(tagged):
        raise ValueError("The Animation target skeleton must contain bones with unique RDR2 tags.")
    bone_tracks = (Track.BonePosition, Track.BoneRotation, Track.BoneScale)
    tracks = {(tag, track): [] for tag, _ in tagged for track in bone_tracks}
    mover_positions = []
    mover_rotations = []
    has_root_motion = False
    identity = Matrix.Identity(4)
    scene = context.scene
    original_frame, original_subframe = scene.frame_current, scene.frame_subframe
    try:
        initial_world = None
        for index in range(frame_count):
            frame = frame_start + index * sample_step
            whole_frame = math.floor(frame)
            scene.frame_set(whole_frame, subframe=frame - whole_frame)
            evaluated = armature.evaluated_get(context.evaluated_depsgraph_get())
            if initial_world is None:
                initial_world = evaluated.matrix_world.copy()
                if abs(initial_world.determinant()) < 1e-12:
                    raise ValueError("Armature object transform is singular.")
            for tag, name in tagged:
                bone = evaluated.pose.bones[name]
                # RDR's SKEL_ROOT bind orientation is not an animation orientation: the supplied
                # male YFT binds it at 180 degrees around Z, while native clips use identity.
                # Export its animated delta; other bones use absolute parent-local transforms.
                if tag == 0 and bone.parent is None:
                    local = bone.bone.matrix_local.inverted() @ bone.matrix
                else:
                    local = bone.parent.matrix.inverted() @ bone.matrix if bone.parent else bone.matrix.copy()
                components = decompose_animation_transform(local, f"Bone '{name}', frame {frame}")
                for track, component in zip(bone_tracks, components):
                    tracks[(tag, track)].append(component)
            world_delta = initial_world.inverted() @ evaluated.matrix_world
            position, rotation, scale = decompose_animation_transform(world_delta, f"Object, frame {frame}")
            if max(abs(v - 1) for v in scale) > 1e-5:
                raise ValueError("Animated armature object scale is unsupported. Animate bones instead.")
            mover_positions.append(position)
            mover_rotations.append(rotation)
            if max(abs(world_delta[r][c] - identity[r][c]) for r in range(4) for c in range(4)) > 1e-5:
                has_root_motion = True
    finally:
        scene.frame_set(original_frame, subframe=original_subframe)

    # Detect evaluated object motion, including constraints and drivers, relative to the first sample.
    if has_root_motion:
        tracks[(0, Track.MoverPosition)] = mover_positions
        tracks[(0, Track.MoverRotation)] = mover_rotations

    # Keep keyed bones and evaluated motion from constraints/drivers; omit static unkeyed bones.
    action = armature.animation_data.action if armature.animation_data else None
    keyed_paths = set()
    if action is not None:
        for fcurve in action_fcurves(action):
            if not fcurve.keyframe_points and not fcurve.sampled_points:
                continue
            match = re.match(r'^pose\.bones\["(?:\\.|[^"\\])*"\]', fcurve.data_path)
            if match:
                keyed_paths.add(match.group())
    exported_bones = set()
    for tag, name in tagged:
        if armature.pose.bones[name].path_from_id() in keyed_paths:
            exported_bones.add(tag)
            continue
        for track in bone_tracks:
            values = tracks[(tag, track)]
            first = values[0]
            if track == Track.BoneRotation:
                changed = any(min(max(abs(a - b) for a, b in zip(first, value)),
                                  max(abs(a + b) for a, b in zip(first, value))) > 1e-5 for value in values[1:])
            else:
                changed = any(max(abs(a - b) for a, b in zip(first, value)) > 1e-5 for value in values[1:])
            if changed:
                exported_bones.add(tag)
                break
    tracks = {key: values for key, values in tracks.items()
              if key[1] in (Track.MoverPosition, Track.MoverRotation) or key[0] in exported_bones}
    if not tracks and not allow_empty:
        raise ValueError("Animation has no keyed bones, evaluated bone motion or object root motion.")

    # Maintain quaternion hemisphere continuity before compression or interpolation.
    for key, values in tracks.items():
        if key[1] not in (Track.BoneRotation, Track.MoverRotation):
            continue
        previous = None
        for value in values:
            if previous is not None and previous.dot(value) < 0:
                value.negate()
            previous = value
    sequence_items: SequenceItems = {}
    for (bone_id, track), frames_data in tracks.items():
        sequence_items.setdefault(bone_id, {})[track] = frames_data
    return sequence_items


def rdr_auxiliary_sequence_items(action, target_id, target, frame_count):
    """Sample editable auxiliary F-curves without treating them as pose TRS.

    Canonical #tag paths also retain channels whose tag has no physical bone.
    Quaternion RNA/F-curves are WXYZ; the existing RDR encoder writes XYZW.
    """
    bone_name_map = build_name_bone_map(target)
    grouped = {}
    for curve in action_fcurves(action):
        pair = get_id_and_track_from_track_data_path(curve.data_path, target_id, bone_name_map)
        if pair is None or pair[1] not in RDRTrackToXmlMap:
            continue
        if not curve.keyframe_points and not curve.sampled_points:
            continue
        components = grouped.setdefault(pair, {})
        if curve.array_index in components:
            raise ValueError(f"Duplicate RDR auxiliary component: {pair}, {curve.array_index}.")
        components[curve.array_index] = curve
    result = {}
    start, end = action.frame_range
    sample_times = [start + index * (end - start) / (frame_count - 1) for index in range(frame_count)]
    for (tag, track), curves in grouped.items():
        fmt = TrackFormatMap[track]
        count = {TrackFormat.Vector3: 3, TrackFormat.Quaternion: 4, TrackFormat.Float: 1}[fmt]
        if set(curves) != set(range(count)):
            raise ValueError(f"RDR track {rdr_track_to_xml(track)}, tag {tag}: requires {count} components.")
        # Imported keys store frame times as float32. Recomputing the uniform
        # grid in double precision can sample just beside a sharp key change.
        # Snap only complete matching grids; evaluate() still applies modifiers.
        times = {}
        for axis, curve in curves.items():
            keys = curve.keyframe_points
            aligned = len(keys) == frame_count and all(
                abs(key.co.x - frame) <= max(1e-6, abs(frame) * 1e-7)
                for key, frame in zip(keys, sample_times))
            times[axis] = [key.co.x for key in keys] if aligned else sample_times
        values = []
        for index in range(frame_count):
            components = [curves[axis].evaluate(times[axis][index]) for axis in range(count)]
            if not all(math.isfinite(value) for value in components):
                raise ValueError(f"RDR track {rdr_track_to_xml(track)}, tag {tag}: non-finite sample.")
            value = (Vector(components) if fmt == TrackFormat.Vector3 else
                     Quaternion(components) if fmt == TrackFormat.Quaternion else components[0])
            values.append(value)
        result.setdefault(tag, {})[track] = values
    return result


def sequence_items_from_action(
        action: bpy.types.Action,
        target_id: bpy.types.ID
) -> SequenceItems:
    action_frame_range = action.frame_range
    export_frame_count = get_action_export_frame_count(action)
    if import_export_current_game() == SollumzGame.RDR:
        target = get_target_from_id(target_id)
        if not isinstance(target_id, bpy.types.Armature) or target is None:
            raise ValueError("RDR YCD requires an armature target and Action for each Animation.")
        if export_frame_count < 2:
            raise ValueError("Animation needs at least two keyed frames.")
        sample_step = (action_frame_range[1] - action_frame_range[0]) / (export_frame_count - 1)
        auxiliary = rdr_auxiliary_sequence_items(action, target_id, target, export_frame_count)
        with animation_export_context(bpy.context, target, action):
            items = sequence_items_from_armature(bpy.context, target, *action_frame_range,
                                                sample_step=sample_step, allow_empty=bool(auxiliary))
        for tag, tracks in auxiliary.items():
            items.setdefault(tag, {}).update(tracks)
        return items

    def _export_frame_to_action_frame(frame_index: int) -> float:
        export_last_frame_index = export_frame_count - 1
        return action_frame_range[0] + (frame_index / export_last_frame_index) * (action_frame_range[1] - action_frame_range[0])

    target = get_target_from_id(target_id)
    target_is_armature = isinstance(target_id, bpy.types.Armature)
    target_is_camera = isinstance(target_id, bpy.types.Camera)
    if target_is_armature:
        bone_name_map = build_name_bone_map(target)
        bone_map = build_bone_map(target)
    else:
        bone_name_map = None
        bone_map = None

    uv_transforms_fcurves = {}

    sequence_items: SequenceItems = {}
    for fcurve in action_fcurves(action):
        data_path = fcurve.data_path
        bone_id_track_pair = get_id_and_track_from_track_data_path(data_path, target_id, bone_name_map)
        if bone_id_track_pair is None:
            logger.warning(f"Channel '{data_path}' in action '{action.name}' is unsupported, skipping...")
            continue

        bone_id, track = bone_id_track_pair
        if track in RDRTrackToXmlMap:
            logger.warning(f"RDR auxiliary channel '{data_path}' cannot be exported as GTA, skipping...")
            continue
        if track == Track.UVTransforms:
            if bone_id not in uv_transforms_fcurves:
                uv_transforms_fcurves[bone_id] = []
            uv_transforms_fcurves[bone_id].append(fcurve)
            continue  # UV transforms are handled later

        comp_index = fcurve.array_index
        track_format = TrackFormatMap[track]

        if bone_id not in sequence_items:
            sequence_items[bone_id] = {}

        bone_sequences = sequence_items[bone_id]

        if track not in bone_sequences:
            if track_format == TrackFormat.Vector3:
                # TODO: defaults should be kept in-sync with the properties defaults in AnimationTracks, refactor this
                #  once we add more defaults to avoid duplication
                if track == Track.UV0:
                    default_vec = (1.0, 0.0, 0.0)
                elif track == Track.UV1:
                    default_vec = (0.0, 1.0, 0.0)
                else:
                    default_vec = (0.0, 0.0, 0.0)
                bone_sequences[track] = [Vector(default_vec) for _ in range(export_frame_count)]
            elif track_format == TrackFormat.Quaternion:
                bone_sequences[track] = [Quaternion((1.0, 0.0, 0.0, 0.0)) for _ in range(export_frame_count)]
            elif track_format == TrackFormat.Float:
                bone_sequences[track] = [0.0] * export_frame_count

        track_sequence = bone_sequences[track]
        for frame_id in range(export_frame_count):
            value = fcurve.evaluate(_export_frame_to_action_frame(frame_id))
            if track_format == TrackFormat.Float:
                track_sequence[frame_id] = value
            else:
                track_sequence[frame_id][comp_index] = value

    if target_is_armature:
        # transform bones from pose space to local space
        for bone_id, bone_sequences in sequence_items.items():
            transform_mat = calculate_bone_space_transform_matrix(bone_map.get(bone_id, None), None)

            if Track.BonePosition in bone_sequences:
                vecs = bone_sequences[Track.BonePosition]
                for i in range(export_frame_count):
                    vecs[i] = transform_mat @ vecs[i]

            if Track.BoneRotation in bone_sequences:
                quats = bone_sequences[Track.BoneRotation]
                for i in range(export_frame_count):
                    quats[i].rotate(transform_mat)

    if target_is_camera:
        # see animationhelper.transform_camera_rotation_quaternion
        angle_delta = math.radians(-90.0)
        x_axis = Vector((1.0, 0.0, 0.0))
        for bone_id, bone_sequences in sequence_items.items():
            if Track.CameraRotation in bone_sequences:
                quats = bone_sequences[Track.CameraRotation]
                for i in range(export_frame_count):
                    x_axis_local = quats[i] @ x_axis
                    quats[i].rotate(Quaternion(x_axis_local, angle_delta))

    if target_id is not None and len(uv_transforms_fcurves) > 0:
        # copy the UV transforms defined by the user to apply f-curves on them without modifying the original ones
        uv_transforms = target.export_uv_transforms
        uv_transforms.clear()
        for uv_transform in target.animation_tracks.uv_transforms:
            uv_transform_copy = uv_transforms.add()
            uv_transform_copy.update_uv_transform_matrix_on_change = False
            uv_transform_copy.copy_from(uv_transform)

        for bone_id, fcurves in uv_transforms_fcurves.items():
            if bone_id not in sequence_items:
                sequence_items[bone_id] = {}

            bone_sequences = sequence_items[bone_id]

            # compute uv0/uv1 from uv_transform
            bone_sequences[Track.UV0] = [Vector((0.0, 0.0, 0.0)) for _ in range(export_frame_count)]
            bone_sequences[Track.UV1] = [Vector((0.0, 0.0, 0.0)) for _ in range(export_frame_count)]
            uv0_sequence = bone_sequences[Track.UV0]
            uv1_sequence = bone_sequences[Track.UV1]
            for frame_id in range(export_frame_count):
                # apply f-curves to UV transforms
                for fcurve in fcurves:
                    value = fcurve.evaluate(_export_frame_to_action_frame(frame_id))
                    transform_index, prop_name = parse_uv_transform_data_path(fcurve.data_path)

                    prop = getattr(uv_transforms[transform_index], prop_name)
                    if isinstance(prop, float):
                        setattr(uv_transforms[transform_index], prop_name, value)
                    else:  # Vector
                        comp_index = fcurve.array_index
                        prop[comp_index] = value

                mat = calculate_final_uv_transform_matrix(uv_transforms)
                uv0_sequence[frame_id][0] = mat[0][0]
                uv0_sequence[frame_id][1] = mat[0][1]
                uv0_sequence[frame_id][2] = mat[0][2]
                uv1_sequence[frame_id][0] = mat[1][0]
                uv1_sequence[frame_id][1] = mat[1][1]
                uv1_sequence[frame_id][2] = mat[1][2]

        uv_transforms.clear()

    # "Flickering bug" fix - killso:
    # This bug is caused by interpolation algorithm used in GTA
    # which is not slerp, but straight interpolation of every value
    # and this leads to incorrect results in cases if dot(this, next) < 0
    # This is correct "Quaternion Lerp" algorithm:
    # if (Dot(start, end) >= 0f)
    # {
    #   result.X = (1 - amount) * start.X + amount * end.X
    #   ...
    # }
    # else
    # {
    #   result.X = (1 - amount) * start.X - amount * end.X
    #   ...
    # }
    # (Statement difference is only substracting instead of adding)
    # But GTA algorithm doesn't have Dot check,
    # resulting all values that are not passing this statement to "lag" in game.
    # (because of incorrect interpolation direction)
    # So what we do is make all values to pass Dot(start, end) >= 0f statement
    quaternion_tracks = list(map(lambda kvp: kvp[0],
                                 filter(lambda kvp: kvp[1] == TrackFormat.Quaternion,
                                        TrackFormatMap.items())))
    for bone_id, bone_sequences in sequence_items.items():
        for track in quaternion_tracks:
            quats = bone_sequences.get(track, None)
            if quats is None:
                continue

            for i in range(1, export_frame_count):
                if quats[i - 1].dot(quats[i]) < 0:
                    quats[i] *= -1
    # WARNING: ANY OPERATION WITH ROTATION WILL CAUSE SIGN CHANGE. PROCEED ANYTHING BEFORE FIX.

    return sequence_items


def build_values_channel(
    values: list[float],
    uniq_values: list[float],
    indirect_percentage: float = 0.1
) -> ycdxml.ChannelsList.Channel:
    if import_export_current_game() == SollumzGame.RDR:
        return build_scalar_channel(values, indirect_percentage)

    values_len_percentage = len(uniq_values) / len(values)

    if len(uniq_values) == 1:
        channel = ycdxml.ChannelsList.StaticFloat()

        channel.value = uniq_values[0]
    elif values_len_percentage <= indirect_percentage:
        channel = ycdxml.ChannelsList.IndirectQuantizeFloat()

        min_value, quantum = get_quantum_and_min_val(uniq_values)

        channel.values = uniq_values
        channel.offset = min_value
        channel.quantum = quantum

        for value in values:
            channel.frames.append(uniq_values.index(value))
    else:
        channel = ycdxml.ChannelsList.QuantizeFloat()

        min_value, quantum = get_quantum_and_min_val(values)

        channel.values = values
        channel.offset = min_value
        channel.quantum = quantum

    # TODO: decide when RawFloat is needed (quantizefloat may compress values too much)
    # else:
    #     channel = ycdxml.ChannelsList.RawFloat()
    #     channel.values = values

    return channel


def sequence_data_from_frames_data(
    track: Track,
    frames_data: TrackFramesData
) -> ycdxml.Animation.SequenceDataList.SequenceData:
    is_rdr = import_export_current_game() == SollumzGame.RDR
    sequence_data_type = ycdxml.RDRAnimation.SequenceDataList if is_rdr else ycdxml.Animation.SequenceDataList
    sequence_data = sequence_data_type.SequenceData()

    track_format = TrackFormatMap[track]

    if track_format == TrackFormat.Vector3:
        values_x = []
        values_y = []
        values_z = []

        for vector in frames_data:
            values_x.append(vector.x)
            values_y.append(vector.y)
            values_z.append(vector.z)

        uniq_x = list(set(values_x))
        len_uniq_x = len(uniq_x)

        uniq_y = list(set(values_y))
        len_uniq_y = len(uniq_y)

        uniq_z = list(set(values_z))
        len_uniq_z = len(uniq_z)

        if len_uniq_x == 1 and len_uniq_y == 1 and len_uniq_z == 1:
            channel = ycdxml.ChannelsList.StaticVector3()
            channel.value = frames_data[0]

            sequence_data.channels.append(channel)
        else:
            sequence_data.channels.append(build_values_channel(values_x, uniq_x))
            sequence_data.channels.append(build_values_channel(values_y, uniq_y))
            sequence_data.channels.append(build_values_channel(values_z, uniq_z))
    elif track_format == TrackFormat.Quaternion:
        if is_rdr:
            sequence_data.channels.extend(build_quaternion_channels(frames_data))
            return sequence_data
        values_x = []
        values_y = []
        values_z = []
        values_w = []

        for quat in frames_data:
            values_x.append(quat.x)
            values_y.append(quat.y)
            values_z.append(quat.z)
            values_w.append(quat.w)

        uniq_x = list(set(values_x))
        len_uniq_x = len(uniq_x)

        uniq_y = list(set(values_y))
        len_uniq_y = len(uniq_y)

        uniq_z = list(set(values_z))
        len_uniq_z = len(uniq_z)

        uniq_w = list(set(values_w))
        len_uniq_w = len(uniq_w)

        static_rotation = len_uniq_x == 1 and len_uniq_y == 1 and len_uniq_z == 1 and len_uniq_w == 1
        if is_rdr:
            quat = frames_data[0]
            reconstructed_w = math.sqrt(max(0, 1 - quat.x * quat.x - quat.y * quat.y - quat.z * quat.z))
            static_rotation = static_rotation and quat.w >= 0.25 and abs(reconstructed_w - quat.w) < 1e-6
        if static_rotation:
            channel = ycdxml.ChannelsList.StaticQuaternion()
            channel.value = frames_data[0]

            sequence_data.channels.append(channel)
        else:
            sequence_data.channels.append(build_values_channel(values_x, uniq_x))
            sequence_data.channels.append(build_values_channel(values_y, uniq_y))
            sequence_data.channels.append(build_values_channel(values_z, uniq_z))
            sequence_data.channels.append(build_values_channel(values_w, uniq_w))
    elif track_format == TrackFormat.Float:
        values = frames_data
        uniq = list(set(values))
        sequence_data.channels.append(build_values_channel(values, uniq))

    return sequence_data


def animation_from_object(animation_obj: bpy.types.Object, preserve_dict_index: bool = False) -> Optional[ycdxml.Animation]:
    animation_properties = animation_obj.animation_properties
    action = animation_properties.action
    is_rdr = import_export_current_game() == SollumzGame.RDR
    if action is None:
        raise ValueError(f"Animation '{animation_obj.name}' has no assigned Action.")
    export_frame_count = get_action_export_frame_count(action)
    if export_frame_count == 0:
        logger.error(f"Action '{action.name}' has no keyframes. Used by animation '{animation_obj.name}'. Cannot export empty action.")
        return None

    animation_type = ycdxml.RDRAnimation if is_rdr else ycdxml.Animation
    animation = animation_type()
    if is_rdr and preserve_dict_index:
        animation.dict_index = animation_properties.rdr_dict_index
    animation.hash = animation_properties.hash
    if is_rdr:
        animation.hash = animation.hash.removeprefix("pack:/").removesuffix(".anim")
        validate_rdr_animation_name(animation.hash)
    animation.frame_count = export_frame_count
    animation.sequence_frame_limit = 255 if is_rdr else export_frame_count + 30
    animation.duration = get_action_duration_secs(action)
    animation.unknown10 = AnimationFlag.Default

    # signature: this value must be unique (used internally for animation caching)
    # TODO: CW should calculate this on import with the proper hash function
    animation.unknown1C = 0 if is_rdr else f"hash_{jenkhash.Generate(animation_properties.hash) + 1:08X}"

    target_id = animation_properties.target_id
    sequence_items = sequence_items_from_action(action, target_id)

    sequence_datas = [(bone_id, track, frames_data)
                      for bone_id, bones_data in sequence_items.items()
                      for track, frames_data in bones_data.items()]
    sequence_datas.sort(key=lambda x: x[0] | ((rdr_track_to_xml(x[1]) if is_rdr else x[1].value) << 16))
    for bone_id, track, frames_data in sequence_datas:
        if track == Track.MoverPosition or track == Track.MoverRotation:
            animation.unknown10 |= AnimationFlag.RootMotion

        seq_bone_id = animation_type.BoneIdList.BoneId()
        seq_bone_id.bone_id = bone_id
        seq_bone_id.track = rdr_track_to_xml(track) if is_rdr else track.value
        seq_bone_id.format = TrackFormatMap[track].value
        animation.bone_ids.append(seq_bone_id)

    sequence_starts = range(0, export_frame_count - 1, 255) if is_rdr else (0,)
    for start in sequence_starts:
        sequence = animation_type.SequenceList.Sequence()
        sequence.frame_count = min(256, export_frame_count - start) if is_rdr else export_frame_count
        for bone_id, track, frames_data in sequence_datas:
            sequence.sequence_data.append(sequence_data_from_frames_data(
                track, frames_data[start:start + sequence.frame_count]
            ))
        sequence.hash = (jenkhash.GenerateData(tostring(sequence.to_xml())) or 1) if is_rdr else "hash_00000000"
        animation.sequences.append(sequence)

    # Get int value from enum, a bit junky...
    animation.unknown10 = animation.unknown10.value | (0x100 if is_rdr else 0)
    if is_rdr:
        animation.unknown1C = jenkhash.GenerateData(tostring(animation.to_xml())) or 1

    return animation


def clip_attribute_to_xml(attr: ClipAttribute) -> ycdxml.AttributesList.Attribute:
    if attr.type == "Float":
        xml_attr = ycdxml.AttributesList.FloatAttribute()
        xml_attr.value = attr.value_float
    elif attr.type == "Int":
        xml_attr = ycdxml.AttributesList.IntAttribute()
        xml_attr.value = attr.value_int
    elif attr.type == "Bool":
        xml_attr = ycdxml.AttributesList.BoolAttribute()
        xml_attr.value = 1 if attr.value_bool else 0
    elif attr.type == "Vector3":
        xml_attr = ycdxml.AttributesList.Vector3Attribute()
        xml_attr.value = Vector(attr.value_vec3)
    elif attr.type == "Vector4":
        xml_attr = ycdxml.AttributesList.Vector4Attribute()
        xml_attr.value = Vector(attr.value_vec4)
    elif attr.type == "String":
        xml_attr = ycdxml.AttributesList.StringAttribute()
        xml_attr.value = attr.value_string
    elif attr.type == "HashString":
        xml_attr = ycdxml.AttributesList.HashStringAttribute()
        xml_attr.value = attr.value_string
    else:
        assert False, f"Unknown attribute type: {attr.type}"
    xml_attr.name_hash = attr.name
    return xml_attr


def clip_attribute_calc_signature(attr: ClipAttribute) -> int:
    signature = jenkhash.name_to_hash(attr.name)
    if attr.type == "Float":
        signature = jenkhash.GenerateData(struct.pack("f", attr.value_float), seed=signature)
    elif attr.type == "Int":
        signature = jenkhash.GenerateData(struct.pack("i", attr.value_int), seed=signature)
    elif attr.type == "Bool":
        signature = jenkhash.GenerateData(struct.pack("?", attr.value_bool), seed=signature)
    elif attr.type == "Vector3":
        vec3 = attr.value_vec3
        signature = jenkhash.GenerateData(struct.pack("3f", vec3[0], vec3[1], vec3[2]), seed=signature)
    elif attr.type == "Vector4":
        vec4 = attr.value_vec4
        signature = jenkhash.GenerateData(struct.pack("4f", vec4[0], vec4[1], vec4[2], vec4[3]), seed=signature)
    elif attr.type == "String":
        signature = jenkhash.Generate(attr.value_string, seed=signature)
    elif attr.type == "HashString":
        signature = jenkhash.name_to_hash(attr.value_string)
    else:
        assert False, f"Unknown attribute type: {attr.type}"

    return signature


# TODO: these calc_signature functions try to reproduce the original
#  calculations but currently do not match the expected results, investigate.
#  Should be good enough for now
def clip_property_calc_signature(prop: ClipAttribute) -> int:
    signature = jenkhash.name_to_hash(prop.name)
    for attr in prop.attributes:
        attr_signature = clip_attribute_calc_signature(attr)
        signature = jenkhash.GenerateData(struct.pack("I", attr_signature), seed=signature)

    return signature


def clip_tag_calc_signature(tag: ClipTag) -> int:
    import zlib

    signature = jenkhash.name_to_hash(tag.name)
    for attr in tag.attributes:
        attr_signature = clip_attribute_calc_signature(attr)
        signature = jenkhash.GenerateData(struct.pack("I", attr_signature), seed=signature)

    signature = zlib.crc32(struct.pack("f", tag.start_phase), jenkhash.name_to_hash(tag.name) ^ signature)
    signature = zlib.crc32(struct.pack("f", tag.end_phase), signature)
    return signature


def clip_from_object(clip_obj: bpy.types.Object) -> ycdxml.Clip:
    clip_properties = clip_obj.clip_properties
    is_rdr = import_export_current_game() == SollumzGame.RDR
    if is_rdr and not clip_properties.animations:
        raise ValueError("RDR clip requires at least one Animation link.")

    if is_rdr and (not math.isfinite(clip_properties.duration) or clip_properties.duration <= 0):
        raise ValueError("Clip duration must be positive.")

    is_single_animation = len(clip_properties.animations) == 1
    if is_rdr and clip_properties.rdr_multi:
        is_single_animation = False

    if is_single_animation:
        xml_clip = ycdxml.RDRClip() if is_rdr else ycdxml.ClipsList.ClipAnimation()
        clip_animation_property = clip_properties.animations[0]
        animation_properties = clip_animation_property.animation.animation_properties
        duration_frames = get_action_duration_frames(animation_properties.action)
        duration_secs = get_action_duration_secs(animation_properties.action)

        xml_clip.animation_hash = animation_properties.hash
        xml_clip.start_time = (clip_animation_property.start_frame / duration_frames) * duration_secs
        xml_clip.end_time = (clip_animation_property.end_frame / duration_frames) * duration_secs
        if is_rdr:
            first, last = animation_properties.action.frame_range
            if (clip_animation_property.start_frame < first - 1e-4
                    or clip_animation_property.end_frame > last + 1e-4
                    or clip_animation_property.end_frame <= clip_animation_property.start_frame):
                raise ValueError("Clip frame range must lie inside its Action keyed range.")
            if not math.isfinite(clip_properties.duration) or clip_properties.duration <= 0:
                raise ValueError("Clip duration must be positive.")
            xml_clip.animation_hash = animation_properties.hash.removeprefix("pack:/").removesuffix(".anim")
            xml_clip.start_time -= first * duration_secs / duration_frames
            xml_clip.end_time -= first * duration_secs / duration_frames

        clip_animation_duration = xml_clip.end_time - xml_clip.start_time
        xml_clip.rate =  clip_animation_duration / clip_properties.duration
    else:
        xml_clip = ycdxml.RDRMultiClip() if is_rdr else ycdxml.ClipsList.ClipAnimationList()
        if not is_rdr:
            xml_clip.duration = clip_properties.duration
        parts = {}

        for clip_animation_property in clip_properties.animations:
            clip_animation = ycdxml.RDRMultiClipAnimation() if is_rdr else ycdxml.ClipAnimationsList.ClipAnimation()

            animation_properties = clip_animation_property.animation.animation_properties
            duration_frames = get_action_duration_frames(animation_properties.action)
            duration_secs = get_action_duration_secs(animation_properties.action)

            clip_animation.animation_hash = animation_properties.hash
            clip_animation.start_time = (clip_animation_property.start_frame / duration_frames) * duration_secs
            clip_animation.end_time = (clip_animation_property.end_frame / duration_frames) * duration_secs

            clip_animation_duration = clip_animation.end_time - clip_animation.start_time
            clip_animation.rate = clip_animation_duration / clip_properties.duration

            if is_rdr:
                first, last = animation_properties.action.frame_range
                if (clip_animation_property.start_frame < first - 1e-4
                        or clip_animation_property.end_frame > last + 1e-4
                        or clip_animation_property.end_frame <= clip_animation_property.start_frame):
                    raise ValueError("Clip frame range must lie inside its Action keyed range.")
                clip_animation.animation_hash = animation_properties.hash.removeprefix("pack:/").removesuffix(".anim")
                clip_animation.start_time -= first * duration_secs / duration_frames
                clip_animation.end_time -= first * duration_secs / duration_frames
                part_index = clip_animation_property.rdr_part_index
                part_duration = clip_animation_property.rdr_part_duration or clip_properties.duration
                if not math.isfinite(part_duration) or part_duration <= 0:
                    raise ValueError("RDR multi-clip part duration must be positive.")
                if part_index not in parts:
                    part = ycdxml.RDRMultiClipPart()
                    part.duration = part_duration
                    parts[part_index] = part
                elif not math.isclose(parts[part_index].duration, part_duration, abs_tol=1e-4):
                    raise ValueError("Links in the same RDR part must have the same duration.")
                clip_animation.rate = (clip_animation_property.rdr_speed
                                       or (clip_animation.end_time - clip_animation.start_time) / part_duration)
                for value in json.loads(clip_animation_property.rdr_unknown_10 or "[]"):
                    if len(value) != 4 or not all(math.isfinite(component) for component in value):
                        raise ValueError("RDR Unknown_10 entries require four finite components.")
                    clip_animation.unknown_10.append(ycdxml.Vector4Property("Item", Vector(value)))
                parts[part_index].clips.append(clip_animation)
            else:
                xml_clip.animations.append(clip_animation)
        if is_rdr:
            if sorted(parts) != list(range(len(parts))):
                raise ValueError("RDR part indices must be consecutive, starting at zero.")
            for part_index in sorted(parts):
                xml_clip.parts.append(parts[part_index])
            if not math.isclose(xml_clip.duration, clip_properties.duration, abs_tol=1e-4):
                raise ValueError("RDR clip duration must equal the sum of its part durations.")

    xml_clip.hash = clip_properties.hash
    xml_clip.name = "pack:/" + clip_properties.name
    xml_clip.unknown30 = 0
    if is_rdr:
        xml_clip.hash = xml_clip.hash.removeprefix("pack:/").removesuffix(".clip")
        validate_rdr_animation_name(xml_clip.hash)

    for tag in clip_properties.tags:
        xml_tag = ycdxml.RDRTag() if is_rdr else ycdxml.Clip.TagList.Tag()
        xml_tag.name_hash = tag.name
        xml_tag.unk_hash = f"hash_{clip_tag_calc_signature(tag):08X}"
        if is_rdr:
            xml_tag.unk_hash = clip_tag_calc_signature(tag) or 1
        xml_tag.start_phase = tag.start_phase
        xml_tag.end_phase = tag.end_phase
        for attr in tag.attributes:
            xml_tag.attributes.append(clip_attribute_to_xml(attr))
        xml_clip.tags.append(xml_tag)
    xml_clip.tags.sort(key=lambda t: t.start_phase)

    for prop in clip_properties.properties:
        xml_prop = ycdxml.RDRProperty() if is_rdr else ycdxml.Property()
        xml_prop.name_hash = prop.name
        xml_prop.unk_hash = f"hash_{clip_property_calc_signature(prop):08X}"
        if is_rdr:
            xml_prop.unk_hash = clip_property_calc_signature(prop) or 1
        for attr in prop.attributes:
            xml_prop.attributes.append(clip_attribute_to_xml(attr))
        xml_clip.properties.append(xml_prop)

    return xml_clip


def clip_dictionary_from_object(obj: bpy.types.Object, include_clips: bool = True) -> Optional[ycdxml.ClipDictionary]:
    is_rdr = import_export_current_game() == SollumzGame.RDR
    if is_rdr and include_clips and obj.rdr_external_animations:
        return external_clip_dictionary_from_object(obj)
    clip_dictionary = ycdxml.RDRClipDictionary() if is_rdr else ycdxml.ClipDictionary()
    if is_rdr:
        clip_dictionary.name = obj.name
        clip_dictionary.anim_dict.name = obj.name

    animations_obj = None
    clips_obj = None

    for child_obj in obj.children:
        if child_obj.sollum_type == SollumType.ANIMATIONS:
            animations_obj = child_obj
        elif child_obj.sollum_type == SollumType.CLIPS:
            clips_obj = child_obj

    any_animation_export_failed = False
    if animations_obj is None or (include_clips and clips_obj is None):
        raise ValueError("Clip dictionary requires Animations and Clips containers.")
    animation_objects = set(animations_obj.children)
    if is_rdr and include_clips:
        for clip_obj in clips_obj.children:
            for link in clip_obj.clip_properties.animations:
                if link.animation not in animation_objects:
                    raise ValueError("Clip must link an Animation in this dictionary's Animations container.")
    for animation_obj in animations_obj.children:
        animation = animation_from_object(animation_obj, preserve_dict_index=not include_clips)
        if animation is None:
            any_animation_export_failed = True
            continue

        clip_dictionary.animations.append(animation)
        if is_rdr:
            if sum(existing.hash == animation.hash for existing in clip_dictionary.animations) > 1:
                raise ValueError("Duplicate Animation hash/name.")
            entry = ycdxml.RDRAnimationLookup()
            entry.name = animation.hash
            clip_dictionary.animation_lookup.append(entry)

    if any_animation_export_failed:
        # If any animation had some error, it's not safe to continue exporting the clips
        return None

    for clip_obj in clips_obj.children if include_clips else ():
        clip = clip_from_object(clip_obj)

        clip_dictionary.clips.append(clip)
        if is_rdr:
            if sum(existing.hash == clip.hash for existing in clip_dictionary.clips) > 1:
                raise ValueError("Duplicate Clip name.")
            clip.dictionary = clip_dictionary.name
            clip.unknown30 = jenkhash.GenerateData(tostring(clip.to_xml())) or 1

    if is_rdr and not clip_dictionary.animations:
        raise ValueError("Dictionary has no Actions.")

    return clip_dictionary


def external_clip_dictionary_from_object(obj):
    from .yadlink import dictionary_animations, dictionary_links, resource_name
    from .ycdimport import rdr_animation_name_hash
    if dictionary_animations(obj):
        raise ValueError("External YCD animations must belong to linked YAD dictionaries.")
    entries = sorted(obj.rdr_animation_dictionaries, key=lambda entry: entry.dict_index)
    if not entries or [entry.dict_index for entry in entries] != list(range(len(entries))):
        raise ValueError("External dictionary indices must be consecutive, starting at zero.")
    dictionary = ycdxml.RDRClipDictionary()
    dictionary.name = obj.name
    owners = {}
    for entry in entries:
        yad = entry.yad
        if (yad is None or yad.animation_dictionary_format != "YAD" or yad.rdr_ycd_target != obj):
            raise ValueError(f"Dictionary {entry.dict_index} needs a linked YAD before export.")
        name = resource_name(yad)
        validate_rdr_animation_name(name)
        dictionary.animation_imports.append(dictionary.AnimationImportsList.Import("Item", name))
        for animation in dictionary_animations(yad):
            owners[animation] = entry.dict_index
    links = dictionary_links(obj)
    if not links:
        raise ValueError("External YCD has no clip animation links.")
    seen = {}
    for link in links:
        if link.rdr_pending or link.animation not in owners:
            raise ValueError("Clip contains an unresolved or unlinked YAD animation.")
        animation = link.animation
        name = animation.animation_properties.hash.removeprefix("pack:/").removesuffix(".anim")
        key = rdr_animation_name_hash(name)
        index = owners[animation]
        if key in seen and seen[key] != index:
            raise ValueError("Animation hash is ambiguous across linked YADs.")
        if key not in seen:
            entry = ycdxml.RDRAnimationLookup()
            entry.name, entry.dict_index = name, index
            dictionary.animation_lookup.append(entry)
            seen[key] = index
    for container in obj.children:
        if container.sollum_type == SollumType.CLIPS:
            for clip_obj in container.children:
                clip = clip_from_object(clip_obj)
                clip.dictionary = dictionary.name
                dictionary.clips.append(clip)
    return dictionary


def export_ycd(obj: bpy.types.Object, filepath: str) -> bool:
    clip_dict = clip_dictionary_from_object(obj)
    if clip_dict is None:
        return False
    if isinstance(clip_dict, ycdxml.RDRClipDictionary):
        path = Path(filepath)
        if not path.name.lower().endswith(".ycd.xml"):
            raise ValueError("Output must end in .ycd.xml.")
        clip_dict.name = path.name[:-8]
        validate_rdr_animation_name(clip_dict.name)
        clip_dict.anim_dict.name = clip_dict.name
        for clip in clip_dict.clips:
            clip.dictionary = clip_dict.name
            clip.unknown30 = jenkhash.GenerateData(tostring(clip.to_xml())) or 1

    clip_dict.write_xml(filepath)
    return True


def export_yad(obj: bpy.types.Object, filepath: str) -> bool:
    if obj.sollum_game_type != SollumzGame.RDR:
        raise ValueError("YAD export requires an RDR animation dictionary.")
    path = Path(filepath)
    if not path.name.lower().endswith(ycdxml.YAD.file_extension):
        raise ValueError("Output must end in .yad.xml.")
    name = path.name[:-len(ycdxml.YAD.file_extension)]
    validate_rdr_animation_name(name)
    if obj.rdr_ycd_target is not None:
        from .yadlink import resource_name
        if name != resource_name(obj):
            raise ValueError("Linked YAD output basename must match its dictionary object's export name.")
    from ..sollumz_properties import set_import_export_current_game
    previous_game = import_export_current_game()
    try:
        set_import_export_current_game(SollumzGame.RDR)
        clip_dict = clip_dictionary_from_object(obj, include_clips=False)
    finally:
        set_import_export_current_game(previous_game)
    if clip_dict is None:
        return False
    dictionary = ycdxml.RDRStandaloneAnimationDictionary()
    dictionary.name = name
    dictionary.animations = clip_dict.animations
    ycdxml.YAD.write_xml(dictionary, filepath)
    return True
