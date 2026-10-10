"""Persistent links between independently imported RDR clip and animation dictionaries."""
import math
from ..sollumz_properties import SollumType, SollumzGame
from ..tools.animationhelper import get_action_duration_secs


def dictionary_root(obj):
    while obj is not None:
        if obj.sollum_type == SollumType.CLIP_DICTIONARY:
            return obj
        obj = obj.parent
    return None


def dictionary_animations(root):
    return [a for container in root.children if container.sollum_type == SollumType.ANIMATIONS
            for a in container.children if a.sollum_type == SollumType.ANIMATION]


def dictionary_links(root):
    return [link for container in root.children if container.sollum_type == SollumType.CLIPS
            for clip in container.children for link in clip.clip_properties.animations]


def resource_name(root):
    # Same basename rule as the standard export operator.
    from ..tools.blenderhelper import remove_number_suffix
    return remove_number_suffix(root.name.lower())


def link_yad_to_ycd(yad, ycd, validate_only=False):
    """Validate before linking; retain YAD ownership and armature targets."""
    from .ycdimport import rdr_animation_name_hash
    if (yad is None or ycd is None or yad == ycd or
            yad.sollum_type != SollumType.CLIP_DICTIONARY or
            ycd.sollum_type != SollumType.CLIP_DICTIONARY or
            yad.sollum_game_type != SollumzGame.RDR or ycd.sollum_game_type != SollumzGame.RDR or
            yad.animation_dictionary_format != "YAD" or ycd.animation_dictionary_format != "YCD"):
        raise ValueError("Select an RDR YAD and an RDR YCD target.")
    if dictionary_animations(ycd):
        raise ValueError("External YCD must keep its animations in YAD dictionaries; its Animations container must be empty.")
    animations = dictionary_animations(yad)
    if not animations:
        raise ValueError("YAD has no animations.")
    by_hash = {}
    for animation in animations:
        key = rdr_animation_name_hash(animation.animation_properties.hash)
        if key in by_hash:
            raise ValueError("YAD contains duplicate animation hashes.")
        by_hash[key] = animation
    entries = list(ycd.rdr_animation_dictionaries)
    occupied = {entry.dict_index for entry in entries if entry.yad is not None and entry.yad != yad}
    own = next((entry for entry in entries if entry.yad == yad), None)
    matches = [entry for entry in entries if entry.yad is None and entry.resource_name and
               rdr_animation_name_hash(entry.resource_name) == rdr_animation_name_hash(resource_name(yad))]
    if len(matches) > 1:
        raise ValueError("YAD dictionary identity is ambiguous.")
    pending = dictionary_links(ycd)
    matching_indices = {link.rdr_dict_index for link in pending if link.rdr_pending and
                        rdr_animation_name_hash(link.rdr_animation_hash) in by_hash}
    if own is not None:
        index = own.dict_index
    elif matches:
        index = matches[0].dict_index
    elif matching_indices:
        if len(matching_indices) != 1:
            raise ValueError("YAD matches animations in multiple dictionary indices.")
        index = next(iter(matching_indices))
    else:
        unresolved = [entry for entry in entries if entry.yad is None]
        if unresolved:
            raise ValueError("YAD does not match this YCD's unresolved animation dictionaries.")
        index = next(i for i in range(65536) if i not in occupied)
    if index in occupied:
        raise ValueError("Another YAD already occupies this dictionary index.")
    plan = []
    for link in pending:
        if not link.rdr_pending or link.rdr_dict_index != index:
            continue
        animation = by_hash.get(rdr_animation_name_hash(link.rdr_animation_hash))
        if animation is None:
            raise ValueError(f"YAD is missing animation '{link.rdr_animation_hash}'.")
        action = animation.animation_properties.action
        duration = get_action_duration_secs(action) if action is not None else 0
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("YAD animation must have a keyed Action with positive duration.")
        first, last = action.frame_range
        plan.append((link, animation, first + link.rdr_start_time / duration * (last-first),
                     first + link.rdr_end_time / duration * (last-first)))
    if validate_only:
        return len(plan)
    old = yad.rdr_ycd_target
    if old is not None and old != ycd:
        for link in dictionary_links(old):
            if dictionary_root(link.animation) == yad:
                action = link.animation.animation_properties.action
                first, last = action.frame_range
                duration = get_action_duration_secs(action)
                link.rdr_animation_hash = link.animation.animation_properties.hash
                link.rdr_start_time = (link.start_frame-first) / (last-first) * duration
                link.rdr_end_time = (link.end_frame-first) / (last-first) * duration
                link.rdr_pending = True
                link.animation = None
        for entry in old.rdr_animation_dictionaries:
            if entry.yad == yad:
                entry.yad = None
    entry = next((entry for entry in entries if entry.dict_index == index), None)
    if entry is None:
        entry = ycd.rdr_animation_dictionaries.add()
        entry.dict_index = index
    entry.yad = yad
    entry.resource_name = resource_name(yad)
    for animation in animations:
        animation.animation_properties.rdr_dict_index = index
    for link, animation, start, end in plan:
        link.animation = animation
        link.start_frame, link.end_frame = start, end
        link.rdr_pending = False
    yad.rdr_ycd_target = ycd
    ycd.rdr_external_animations = True
    return len(plan)
