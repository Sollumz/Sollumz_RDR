# from .element import *
from abc import ABC as AbstractClass, abstractmethod
from enum import Enum
from mathutils import Vector
from .element import (
    AttributeProperty,
    ElementTree,
    ElementProperty,
    ListProperty,
    ListPropertyRequired,
    QuaternionProperty,
    TextProperty,
    ValueProperty,
    VectorProperty,
    Vector4Property
)
from xml.etree import ElementTree as ET
from inspect import isclass
from math import sqrt
from copy import deepcopy
from ..sollumz_properties import SollumzGame, set_import_export_current_game
from .. import logger


class YCD:

    file_extension = ".ycd.xml"

    @staticmethod
    def from_xml_file(filepath):
        root = ET.parse(filepath).getroot()
        if root.tag == "RDR2ClipDictionary":
            set_import_export_current_game(SollumzGame.RDR)
            return RDRClipDictionary.from_xml(root)
        set_import_export_current_game(SollumzGame.GTA)
        return ClipDictionary.from_xml(root)

    @staticmethod
    def write_xml(clips_dict, filepath):
        return clips_dict.write_xml(filepath)


class ItemTypeList(ListProperty, AbstractClass):
    class Item(ElementTree, AbstractClass):
        tag_name = "Item"

        @property
        @abstractmethod
        def type(self) -> str:
            raise NotImplementedError

    list_type = Item

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        type_map = {}
        for key, item_class in vars(cls).items():
            if isclass(item_class) and issubclass(item_class, ItemTypeList.Item) and key == item_class.__name__:
                type_map[item_class.type] = item_class
        for child in element:
            type_elem = child.find("Type")
            if type_elem is not None:
                type = type_elem.get("value")
                if type in type_map:
                    new.value.append(type_map[type].from_xml(child))
        return new


class AttributesList(ItemTypeList):
    class Attribute(ItemTypeList.Item, AbstractClass):
        tag_name = "Item"

        @property
        @abstractmethod
        def type(self) -> str:
            raise NotImplementedError

        def __init__(self):
            super().__init__()
            self.name_hash = TextProperty("NameHash", "")
            self.type = ValueProperty("Type", self.type)

    class FloatAttribute(Attribute):
        type = "Float"

        def __init__(self):
            super().__init__()
            self.value = ValueProperty("Value", 0.0)

    class IntAttribute(Attribute):
        type = "Int"

        def __init__(self):
            super().__init__()
            self.value = ValueProperty("Value", 0)

    class BoolAttribute(Attribute):
        type = "Bool"

        def __init__(self):
            super().__init__()
            self.value = ValueProperty("Value", 0)

    class Vector3Attribute(Attribute):
        type = "Vector3"

        def __init__(self):
            super().__init__()
            self.value = VectorProperty("Value")
            self.unknown2c = ValueProperty("Unknown2C", 1)

    class Vector4Attribute(Attribute):
        type = "Vector4"

        def __init__(self):
            super().__init__()
            self.value = Vector4Property("Value")

    class StringAttribute(Attribute):
        type = "String"

        def __init__(self):
            super().__init__()
            self.value = TextProperty("Value", "")

    class HashStringAttribute(Attribute):
        type = "HashString"

        def __init__(self):
            super().__init__()
            self.value = TextProperty("Value", "")

    list_type = Attribute
    tag_name = "Attributes"


class ValuesBuffer(ElementProperty):
    value_types = (list)

    def __init__(self):
        super().__init__(tag_name="Values", value=[])

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        text = element.text.strip().split("\n")
        if len(text) > 0:
            for line in text:
                items = line.strip().split(" ")
                for item in items:
                    new.value.append(float(item))

        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)
        columns = 10
        text = []

        for index, value in enumerate(self.value):
            text.append(str(value))
            if index < len(self.value) - 1:
                text.append(" ")
            if (index + 1) % columns == 0:
                text.append("\n")

        element.text = "".join(text)

        return element


class FramesBuffer(ElementProperty):
    value_types = (list)

    def __init__(self):
        super().__init__(tag_name="Frames", value=[])

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        text = element.text.strip().split("\n")
        if len(text) > 0:
            for line in text:
                items = line.strip().split(" ")
                for item in items:
                    new.value.append(int(item))

        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)
        columns = 10
        text = []

        for index, value in enumerate(self.value):
            text.append(str(value))
            if index < len(self.value) - 1:
                text.append(" ")
            if (index + 1) % columns == 0:
                text.append("\n")

        element.text = "".join(text)

        return element


class ChannelsList(ItemTypeList):
    class Channel(ItemTypeList.Item, AbstractClass):
        tag_name = "Item"

        @property
        @abstractmethod
        def type(self) -> str:
            raise NotImplementedError

        def __init__(self):
            super().__init__()
            self.type = ValueProperty("Type", "")

        def get_value(self, frame_id, channel_values):
            raise NotImplementedError

    class StaticQuaternion(Channel):
        type = "StaticQuaternion"

        def __init__(self):
            super().__init__()
            self.value = QuaternionProperty("Value")
            self.type = "StaticQuaternion"

        def get_value(self, frame_id, channel_values):
            return self.value

    class StaticVector3(Channel):
        type = "StaticVector3"

        def __init__(self):
            super().__init__()
            self.value = VectorProperty("Value")
            self.type = "StaticVector3"

        def get_value(self, frame_id, channel_values):
            return self.value

    class StaticFloat(Channel):
        type = "StaticFloat"

        def __init__(self):
            super().__init__()
            self.value = ValueProperty("Value", 0.0)
            self.type = "StaticFloat"

        def get_value(self, frame_id, channel_values):
            return self.value

    class RawFloat(Channel):
        type = "RawFloat"

        def __init__(self):
            super().__init__()
            self.values = ValuesBuffer()
            self.type = "RawFloat"

        def get_value(self, frame_id, channel_values):
            return self.values[frame_id % len(self.values)]

    class QuantizeFloat(Channel):
        type = "QuantizeFloat"

        def __init__(self):
            super().__init__()
            self.quantum = ValueProperty("Quantum", 0.0)
            self.offset = ValueProperty("Offset", 0.0)
            self.values = ValuesBuffer()
            self.type = "QuantizeFloat"

        def get_value(self, frame_id, channel_values):
            return self.values[frame_id % len(self.values)]

    class IndirectQuantizeFloat(QuantizeFloat):
        type = "IndirectQuantizeFloat"

        def __init__(self):
            super().__init__()
            self.frames = FramesBuffer()
            self.type = "IndirectQuantizeFloat"

        def get_value(self, frame_id, channel_values):
            return self.values[(self.frames[frame_id % len(self.frames)]) % len(self.values)]

    class LinearFloat(QuantizeFloat):
        type = "LinearFloat"

        def __init__(self):
            super().__init__()
            self.numints = ValueProperty("NumInts", 0)
            self.counts = ValueProperty("Counts", 0)
            self.type = "LinearFloat"

    class IncrementalFloat(QuantizeFloat):
        type = "IncrementalFloat"

        def __init__(self):
            super().__init__()
            self.type = "IncrementalFloat"

    class CachedQuaternion1(Channel):
        type = "CachedQuaternion1"

        def __init__(self):
            super().__init__()
            self.quat_index = ValueProperty("QuatIndex", 0)
            self.type = "CachedQuaternion1"

        def get_value(self, frame_id, channel_values):
            vec_len = Vector(
                (channel_values[0], channel_values[1], channel_values[2])).length

            return sqrt(max(1.0 - vec_len * vec_len, 0))

    class CachedQuaternion2(CachedQuaternion1):
        type = "CachedQuaternion2"

        def __init__(self):
            super().__init__()
            self.quat_index = ValueProperty("QuatIndex", 0)
            self.type = "CachedQuaternion2"

    list_type = Channel
    tag_name = "Channels"


class Animation(ElementTree):
    class BoneIdList(ListProperty):
        class BoneId(ElementTree):
            tag_name = "Item"

            def __init__(self):
                super().__init__()
                self.bone_id = ValueProperty("BoneId", 0)
                self.track = ValueProperty("Track", 0)
                self.format = ValueProperty("Unk0", 0)

        list_type = BoneId
        tag_name = "BoneIds"

    class SequenceDataList(ListProperty):
        class SequenceData(ElementTree):
            tag_name = "Item"

            def __init__(self):
                super().__init__()
                self.channels = ChannelsList()

        list_type = SequenceData
        tag_name = "SequenceData"

    class SequenceList(ListProperty):

        class Sequence(ElementTree):

            tag_name = "Item"

            def __init__(self):
                super().__init__()
                self.hash = TextProperty("Hash", "")
                self.frame_count = ValueProperty("FrameCount", 0)
                self.sequence_data = Animation.SequenceDataList()

        list_type = Sequence
        tag_name = "Sequences"

    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.hash = TextProperty("Hash", "")
        self.unknown10 = ValueProperty("Unknown10", 0)
        self.frame_count = ValueProperty("FrameCount", 0)
        self.sequence_frame_limit = ValueProperty("SequenceFrameLimit", 0)
        self.duration = ValueProperty("Duration", 0.0)
        self.unknown1C = TextProperty("Unknown1C")
        self.bone_ids = Animation.BoneIdList()
        self.sequences = Animation.SequenceList()


class Property(ElementTree):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.name_hash = TextProperty("NameHash", "")
        self.unk_hash = TextProperty("UnkHash", "")
        self.attributes = AttributesList()


class ClipType(str, Enum):
    ANIMATION = "Animation"
    ANIMATION_LIST = "AnimationList"


class Clip(ItemTypeList.Item, AbstractClass):
    class TagList(ListProperty):
        class Tag(Property):
            tag_name = "Item"

            def __init__(self):
                super().__init__()
                self.start_phase = ValueProperty("StartPhase", 0.0)
                self.end_phase = ValueProperty("EndPhase", 0.0)

        list_type = Tag
        tag_name = "Tags"

    class PropertyList(ListProperty):
        list_type = Property
        tag_name = "Properties"

    def __init__(self):
        super().__init__()
        self.hash = TextProperty("Hash", "")
        self.name = TextProperty("Name", "")
        self.type = ValueProperty("Type", "Animation")
        self.unknown30 = ValueProperty("Unknown30", 0)
        self.tags = Clip.TagList()
        self.properties = Clip.PropertyList()


class ClipAnimationsList(ListProperty):
    class ClipAnimation(ElementTree):

        tag_name = "Item"

        def __init__(self):
            super().__init__()
            self.animation_hash = TextProperty("AnimationHash", "")
            self.start_time = ValueProperty("StartTime", 0.0)
            self.end_time = ValueProperty("EndTime", 0.0)
            self.rate = ValueProperty("Rate", 0.0)

    list_type = ClipAnimation
    tag_name = "Animations"


class ClipsList(ItemTypeList):
    class ClipAnimation(Clip):
        type = ClipType.ANIMATION

        def __init__(self):
            super().__init__()
            self.animation_hash = TextProperty("AnimationHash", "")
            self.start_time = ValueProperty("StartTime", 0.0)
            self.end_time = ValueProperty("EndTime", 0.0)
            self.rate = ValueProperty("Rate", 0.0)

    class ClipAnimationList(Clip):
        type = ClipType.ANIMATION_LIST

        def __init__(self):
            super().__init__()
            self.type = "AnimationList"
            self.duration = ValueProperty("Duration", 0.0)
            self.animations = ClipAnimationsList()

    list_type = Clip
    tag_name = "Clips"


class ClipDictionary(ElementTree):
    class AnimationsList(ListProperty):
        list_type = Animation
        tag_name = "Animations"

    tag_name = "ClipDictionary"

    def __init__(self):
        super().__init__()
        self.clips = ClipsList()
        self.animations = ClipDictionary.AnimationsList()


class RDRChannelsList(ChannelsList):
    @classmethod
    def from_xml(cls, element: ET.Element):
        element = deepcopy(element)
        for item in element:
            ET.SubElement(item, "Type", value=item.get("type", ""))
        channels = ChannelsList.from_xml(element)
        for channel in channels.value:
            if channel.type == "IndirectQuantizeFloat" and not channel.frames:
                raise ValueError("RDR IndirectQuantizeFloat XML is missing Frames; original timing cannot be recovered.")
        result = cls()
        result.value = channels.value
        return result

    def to_xml(self):
        element = super().to_xml()
        if element is None:
            return None
        for item in element:
            channel_type = item.find("Type")
            item.set("type", channel_type.get("value"))
            item.remove(channel_type)
            values = item.find("Values")
            if values is not None:
                # Nine significant digits preserve float32 samples without long decimal expansions.
                values.text = " ".join(format(float(value), ".9g") for value in values.text.split())
        return element


class RDRAttributesList(AttributesList):
    @classmethod
    def from_xml(cls, element: ET.Element):
        element = deepcopy(element)
        for item in element:
            ET.SubElement(item, "Type", value=item.get("type", ""))
            name = item.find("Name")
            if name is not None:
                name.tag = "NameHash"
        attributes = AttributesList.from_xml(element)
        result = cls()
        result.value = attributes.value
        return result

    def to_xml(self):
        element = super().to_xml()
        if element is None:
            return ET.Element(self.tag_name)
        for item in element:
            attribute_type = item.find("Type")
            item.set("type", attribute_type.get("value"))
            item.remove(attribute_type)
            item.find("NameHash").tag = "Name"
            unknown = item.find("Unknown2C")
            if unknown is not None:
                item.remove(unknown)
        return element


class RDRProperty(Property):
    def __init__(self):
        super().__init__()
        self.name_hash = TextProperty("Name", "")
        self.unk_hash = ValueProperty("Signature", 0)
        self.attributes = RDRAttributesList()


class RDRTag(RDRProperty):
    def __init__(self):
        super().__init__()
        self.start_phase = ValueProperty("StartPhase", 0.0)
        self.end_phase = ValueProperty("EndPhase", 0.0)


class RDRAnimation(Animation):
    class BoneIdList(Animation.BoneIdList):
        class BoneId(Animation.BoneIdList.BoneId):
            def __init__(self):
                super().__init__()
                self.track = ValueProperty("TrackId", 0)
                self.format = ValueProperty("TypeId", 0)

        list_type = BoneId

    class SequenceDataList(Animation.SequenceDataList):
        class SequenceData(Animation.SequenceDataList.SequenceData):
            def __init__(self):
                super().__init__()
                self.channels = RDRChannelsList()

        tag_name = "Tracks"
        list_type = SequenceData

    class SequenceList(Animation.SequenceList):
        class Sequence(Animation.SequenceList.Sequence):
            def __init__(self):
                super().__init__()
                self.hash = ValueProperty("Signature", 0)
                self.sequence_data = RDRAnimation.SequenceDataList()

        list_type = Sequence

    def __init__(self):
        super().__init__()
        self.hash = TextProperty("Name", "")
        self.unknown10 = ValueProperty("Flags", 0x100)
        self.dict_index = ValueProperty("DictIndex", 0)
        self.sequence_frame_limit = ValueProperty("SequenceSize", 255)
        self.unknown1C = ValueProperty("Signature", 0)
        self.bone_ids = self.BoneIdList()
        self.sequences = self.SequenceList()

    @classmethod
    def from_xml(cls, element: ET.Element):
        animation = super().from_xml(element)
        animation.hash = animation.hash.removeprefix("pack:/").removesuffix(".anim")
        return animation

    def to_xml(self):
        element = super().to_xml()
        element.find("Name").text = "pack:/" + self.hash + ".anim"
        return element


class RDRClip(ClipsList.ClipAnimation):
    xml_clip_type = "Single"

    class TagList(ListPropertyRequired):
        tag_name = "Tags"
        list_type = RDRTag

    class PropertyList(ListPropertyRequired):
        tag_name = "Properties"
        list_type = RDRProperty

    def __init__(self):
        super().__init__()
        self.hash = TextProperty("Name", "")
        # The common importer uses name for the optional displayed clip name.
        object.__setattr__(self, "name", "")
        self.dictionary = TextProperty("Dict", "")
        self.animation_hash = TextProperty("Animation", "")
        self.rate = ValueProperty("Speed", 1.0)
        self.unknown30 = ValueProperty("Signature", 0)
        self.tags = self.TagList()
        self.properties = self.PropertyList()

    @classmethod
    def from_xml(cls, element: ET.Element):
        if element.get("type") != cls.xml_clip_type:
            raise ValueError("Invalid RDR clip type.")
        clip = super().from_xml(element)
        clip.hash = clip.hash.removeprefix("pack:/").removesuffix(".clip")
        clip.name = clip.hash + ".clip"
        return clip

    def to_xml(self):
        element = super().to_xml()
        element.set("type", self.xml_clip_type)
        element.remove(element.find("Type"))
        element.find("Name").text = "pack:/" + self.hash + ".clip"
        return element


class RDRMultiClipAnimation(ClipAnimationsList.ClipAnimation):
    class Unknown10List(ListProperty):
        tag_name = "Unknown_10"
        item_tag_name = "Item"
        list_type = Vector4Property

    def __init__(self):
        super().__init__()
        self.animation_hash = TextProperty("Animation", "")
        self.rate = ValueProperty("Speed", 1.0)
        self.unknown_10 = self.Unknown10List()


class RDRMultiClipPart(ElementTree):
    class ClipsList(ListPropertyRequired):
        tag_name = "Clips"
        list_type = RDRMultiClipAnimation

    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.duration = ValueProperty("Duration", 0.0)
        self.clips = self.ClipsList()


class RDRMultiClip(RDRClip):
    class PartsList(ListPropertyRequired):
        tag_name = "Parts"
        list_type = RDRMultiClipPart

    xml_clip_type = "Multi"

    def __init__(self):
        super().__init__()
        for name in ("animation_hash", "start_time", "end_time", "rate"):
            delattr(self, name)
        self.type = ClipType.ANIMATION_LIST
        self.parts = self.PartsList()

    @property
    def duration(self):
        return sum(part.duration for part in self.parts)


class RDRClipsList(ClipsList):
    @classmethod
    def from_xml(cls, element: ET.Element):
        result = cls()
        result.value = []
        for item in element:
            clip_type = {"Single": RDRClip, "Multi": RDRMultiClip}.get(item.get("type"))
            if clip_type is None:
                raise ValueError("Unsupported RDR clip type: " + str(item.get("type")))
            result.value.append(clip_type.from_xml(item))
        return result


class RDRAnimationLookup(ElementTree):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.name = TextProperty("Name", "")
        self.dict_index = ValueProperty("DictIndex", 0)


class RDRAnimationDictionary(ElementTree):
    class AnimationsList(ClipDictionary.AnimationsList):
        list_type = RDRAnimation

    tag_name = "AnimDict"

    def __init__(self):
        super().__init__()
        self.version = AttributeProperty("version", 0)
        self.name = TextProperty("Name", "")
        self.animations = self.AnimationsList()


class RDRClipDictionary(ClipDictionary):
    required_empty_tags = ("Tags", "Properties", "Attributes")

    class AnimationLookupList(ListProperty):
        tag_name = "Animations"
        list_type = RDRAnimationLookup

    tag_name = "RDR2ClipDictionary"

    def __init__(self):
        ElementTree.__init__(self)
        self.version = AttributeProperty("version", 0)
        self.name = TextProperty("Name", "")
        self.clips = RDRClipsList()
        self.animation_lookup = self.AnimationLookupList()
        self.anim_dict = RDRAnimationDictionary()

    @property
    def animations(self):
        return self.anim_dict.animations
