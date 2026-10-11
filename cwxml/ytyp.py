from copy import deepcopy
import re
from xml.etree import ElementTree as ET
from .element import (
    AttributeProperty,
    Element,
    ElementTree,
    ElementProperty,
    ListProperty,
    QuaternionProperty,
    TextProperty,
    ValueProperty,
    VectorProperty
)
from .ymap import Entity, EntityList, ExtensionsList, HexColorProperty, LightInstance, LightInstancesList
from numpy import float32
from ..tools.jenkhash import GenerateCaseSensitive
from ..sollumz_properties import SollumzGame, import_export_current_game as current_game, set_import_export_current_game


def tag_key(tag):
    match = re.search(r'(?:_|^)0x([0-9a-fA-F]{8})$', tag)
    return int(match[1], 16) if match else GenerateCaseSensitive(tag)


def merge_source(xml, source, owned_tags):
    """Keep fields we do not edit, original alias spelling and extra attributes.

    Owned arrays are replaced, never merged by index: deletions must stay deleted.
    Unknown extension types are opaque and survive along with editable extensions.
    """
    if not source:
        return xml
    original = ET.fromstring(source)
    for key, value in original.attrib.items():
        if key == 'type' and tag_key(xml.get(key, value)) == tag_key(value):
            xml.set(key, value)
        else:
            xml.attrib.setdefault(key, value)
    owned = {tag_key(tag) for tag in owned_tags}
    emitted = {tag_key(child.tag): child for child in xml}
    for child in original:
        key = tag_key(child.tag)
        if key not in owned:
            xml.append(deepcopy(child))
        elif key in emitted:
            output = emitted[key]
            output.tag = child.tag
            for attr, value in child.attrib.items():
                if attr in ('type', 'itemType') and tag_key(output.get(attr, value)) == tag_key(value):
                    output.set(attr, value)
                else:
                    output.attrib.setdefault(attr, value)
            if key == tag_key('extensions'):
                for extension in child:
                    if ExtensionsList.get_extension_xml_class_from_type(extension.get('type')) is None:
                        output.append(deepcopy(extension))
        elif key == tag_key('extensions') and len(child):
            opaque = [deepcopy(e) for e in child
                      if ExtensionsList.get_extension_xml_class_from_type(e.get('type')) is None]
            if opaque:
                container = ET.SubElement(xml, child.tag, child.attrib)
                container.extend(opaque)
        elif not len(child) and not (child.text or '').strip() and not child.attrib:
            xml.append(deepcopy(child))
    return xml


class RDRYtypElement(ElementTree):
    @classmethod
    def from_xml(cls, element, *args):
        if current_game() != SollumzGame.RDR:
            return super().from_xml(element, *args)
        template = cls(*args)
        tags = {tag_key(v.tag_name): v.tag_name for v in vars(template).values() if isinstance(v, Element)}
        normalized = deepcopy(element)
        for child in normalized:
            child.tag = tags.get(tag_key(child.tag), child.tag)
        new = super().from_xml(normalized, *args)
        new._rdr_xml = ET.tostring(element, encoding='unicode')
        return new

    def to_xml(self):
        xml = super().to_xml()
        opaque = getattr(type(self), 'rdr_opaque_tags', ()) if current_game() == SollumzGame.RDR else ()
        for child in list(xml):
            if child.tag in opaque:
                xml.remove(child)
        return merge_source(xml, self._rdr_xml, [v.tag_name for v in vars(self).values()
                                               if isinstance(v, Element) and v.tag_name not in opaque])


class RDRYtypExtensions(ExtensionsList):
    @classmethod
    def from_xml(cls, element):
        new = cls()
        for child in element:
            ext_class = cls.get_extension_xml_class_from_type(child.get('type'))
            if ext_class is None:
                continue
            normalized = deepcopy(child)
            color = normalized.find('color')
            if color is not None and color.get('value') and not color.get('value').lower().startswith('0x'):
                color.set('value', f'0x{unsigned(color.get("value"), 32):08X}')
            extension = ext_class.from_xml(normalized)
            if extension.get_element('instances') is not None:
                instances = child.find('instances')
                if instances is not None:
                    extension.instances = RDRYtypLightInstances.from_xml(instances).value
            extension._rdr_xml = ET.tostring(child, encoding='unicode')
            new.value.append(extension)
        return new

    def to_xml(self):
        xml = ET.Element(self.tag_name)
        for extension in self.value:
            output = extension.to_xml()
            owned = [v.tag_name for v in vars(extension).values() if isinstance(v, Element)]
            color = extension.get_element('color')
            if isinstance(color, HexColorProperty):
                rgba = color.value
                packed = (round(rgba[3] * 255) << 24 | round(rgba[0] * 255) << 16 |
                          round(rgba[1] * 255) << 8 | round(rgba[2] * 255))
                output.find('color').set('value', str(packed))
            instances = extension.get_element('instances')
            if instances is not None and not instances.value and not getattr(extension, '_rdr_lights_edited', False):
                # Preserve native light instances until replaced by linked lights.
                owned.remove('instances')
            xml.append(merge_source(output, extension._rdr_xml, owned))
        return xml


class RDRYtypLightInstance(RDRYtypElement, LightInstance):
    def __init__(self):
        LightInstance.__init__(self)
        # These GTA padding fields do not exist in CLightAttrDef in RDR.
        del self.padding1
        del self.padding3


class RDRYtypLightInstances(LightInstancesList):
    list_type = RDRYtypLightInstance


class RDRYtypEntity(RDRYtypElement, Entity):
    def __init__(self):
        Entity.__init__(self)
        if current_game() == SollumzGame.RDR:
            self.extensions = RDRYtypExtensions()


class RDRYtypEntities(EntityList):
    list_type = RDRYtypEntity


def remember_xml(xml, properties):
    if current_game() == SollumzGame.RDR and xml._rdr_xml:
        properties['_rdr_xml'] = xml._rdr_xml


def restore_xml(properties, xml):
    if current_game() == SollumzGame.RDR:
        xml._rdr_xml = properties.get('_rdr_xml', '')
        if xml._rdr_xml:
            source = ET.fromstring(xml._rdr_xml)
            children = {tag_key(child.tag): child for child in source}
            for child in vars(xml).values():
                if isinstance(child, RDRYtypElement) and tag_key(child.tag_name) in children:
                    child._rdr_xml = ET.tostring(children[tag_key(child.tag_name)], encoding='unicode')
    return xml


def unsigned(value, bits=64):
    text = str(value).strip()
    result = int(text, 16) if text.lower().startswith('0x') else int(text or '0')
    if not 0 <= result < (1 << bits):
        raise ValueError(f'Value must be an unsigned {bits}-bit integer: {value}')
    return result


class YTYP:

    file_extension = ".ytyp.xml"
    rdr2_file_extension = ".ytyp.rsc.xml"

    @staticmethod
    def from_xml_file(filepath, game=None):
        root = ET.parse(filepath).getroot()
        if root.tag != 'CMapTypes':
            raise ValueError('Expected a CMapTypes YTYP XML document')
        rdr_tags = {tag_key(t) for t in ('loadFlags', 'avoidanceflags', 'mapEntityFactoryType',
                                       'timeCycleVolumes', 'mainActivationVolume')}
        if game is None:
            game = SollumzGame.RDR if ('.rsc' in str(filepath).lower() or
                   any(tag_key(e.tag) in rdr_tags for e in root.iter())) else SollumzGame.GTA
        set_import_export_current_game(game)
        with ElementTree.allow_hash_lookup():
            result = CMapTypes.from_xml(root)
        result.game = game
        return result

    @staticmethod
    def write_xml(cmap_types, filepath):
        return cmap_types.write_xml(filepath)


class BaseArchetype(RDRYtypElement):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.type = AttributeProperty("type", "CBaseArchetypeDef")
        self.lod_dist = ValueProperty("lodDist")
        self.flags = ValueProperty("flags")
        self.special_attribute = ValueProperty("specialAttribute")
        self.bb_min = VectorProperty("bbMin")
        self.bb_max = VectorProperty("bbMax")
        self.bs_center = VectorProperty("bsCentre")
        self.bs_radius = ValueProperty("bsRadius")
        self.hd_texture_dist = ValueProperty("hdTextureDist")
        self.name = TextProperty("name")
        self.texture_dictionary = TextProperty("textureDictionary")
        self.clip_dictionary = TextProperty("clipDictionary")
        self.drawable_dictionary = TextProperty("drawableDictionary")
        self.physics_dictionary = TextProperty("physicsDictionary")
        self.asset_type = TextProperty("assetType")
        self.asset_name = TextProperty("assetName")
        self.extensions = ExtensionsList()

        if current_game() == SollumzGame.RDR:
            self.extensions = RDRYtypExtensions()
            self.load_flags = ValueProperty("loadFlags")
            self.avoidanceflags = ValueProperty("avoidanceflags")
            self.guid = ValueProperty("guid")
            self.unknown_1 = TextProperty("mapEntityFactoryType", "MAP_ENTITY_TYPE_UNINITIALIZED")


class TimeArchetype(BaseArchetype):
    def __init__(self):
        super().__init__()
        self.type = AttributeProperty("type", "CTimeArchetypeDef")
        self.time_flags = ValueProperty("timeFlags")


class Corner(ElementProperty):
    value_types = (tuple)
    tag_name = "Item"

    def __init__(self, tag_name=None, value=None):
        super().__init__("Item", value or tuple())

    @staticmethod
    def from_xml(element):
        value = element.text.split(",")
        value = [float(val) for val in value]
        if len(value) > 3:
            value = value[:3]
        return Corner(value=tuple(value))

    def to_xml(self):
        if not self.value or len(self.value) < 1:
            return None

        elem = ET.Element(self.tag_name)
        elem.text = ",".join([str(float32(val)) for val in self.value])
        return elem


class CornersList(ListProperty):
    list_type = Corner
    tag_name = "corners"


class RDRCorners(ElementProperty):
    value_types = (float)

    def __init__(self):
        super().__init__(tag_name="corners", value=[])

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        if len(element):
            new.value = [Corner(value=tuple(float(item.get(k, '0')) for k in ('x', 'y', 'z')))
                         for item in element]
            return new
        if element.text:
          lines = element.text.strip().splitlines()
          for line in lines:
            corner = line.strip().replace(",", " ").split()
            values = [float(val) for val in corner]
            if len(values) > 3:
                values = values[:3]
            new_value = Corner(value=tuple(values))
            new.value.append(new_value)
                    
        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)
        text = []

        for corner in self.value:
            text.append(", ".join([str(float32(val)) for val in corner.value]))
            text.append(", " + str(float32(corner.value[0])))
            text.append("\n")

        element.text = "".join(text)

        return element


class AttachedObjectsBuffer(ElementProperty):
    value_types = (int)

    def __init__(self):
        super().__init__(tag_name="attachedObjects", value=[])

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        if len(element):
            new.value = [int(item.get('value', item.text or '0')) for item in element]
        elif element.text:
            indices = element.text.split()
            new.value = [int(i) for i in indices]

        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)
        columns = 10
        text = []

        for index, entity_index in enumerate(self.value):
            text.append(str(entity_index))
            if index < len(self.value) - 1:
                text.append(" ")
            if (index + 1) % columns == 0:
                text.append("\n")

        element.text = "".join(text)

        return element


class Portal(RDRYtypElement):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.room_from = ValueProperty("roomFrom")
        self.room_to = ValueProperty("roomTo")
        self.flags = ValueProperty("flags")
        self.mirror_priority = ValueProperty("mirrorPriority")
        self.opacity = ValueProperty("opacity")
        self.audio_occlusion = ValueProperty("audioOcclusion")
        if current_game() == SollumzGame.GTA:
            self.corners = CornersList()
        elif current_game() == SollumzGame.RDR:
            self.corners = RDRCorners()
            for name in ('7C096C2E', '91171666', '96816DDF', '0854FDEE'):
                setattr(self, 'rdr_' + name.lower(), ValueProperty('_0x' + name, 1.0))
        self.attached_objects = AttachedObjectsBuffer()


class PortalsList(ListProperty):
    tag_name = "portals"
    list_type = Portal

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name="portals", value=value or [])
        self.item_type = AttributeProperty("itemType", "CMloPortalDef")


class Room(RDRYtypElement):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.name = TextProperty("name")
        self.bb_min = VectorProperty("bbMin")
        self.bb_max = VectorProperty("bbMax")
        self.blend = ValueProperty("blend", 1)
        self.timecycle_name = TextProperty("timecycleName")
        self.secondary_timecycle_name = TextProperty("secondaryTimecycleName")
        self.flags = ValueProperty("flags")
        self.portal_count = ValueProperty("portalCount")
        self.floor_id = ValueProperty("floorId")
        self.exterior_visibility_depth = ValueProperty(
            "exteriorVisibiltyDepth", -1)
        self.attached_objects = AttachedObjectsBuffer()
        if current_game() == SollumzGame.RDR:
            self.reflection_probes = ReflectionProbes()


class RoomsList(ListProperty):
    tag_name = "rooms"
    list_type = Room

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name="rooms", value=value or [])
        self.item_type = AttributeProperty("itemType", "CMloRoomDef")


class LocationsBuffer(ElementProperty):
    value_types = (int)

    def __init__(self):
        super().__init__(tag_name="locations", value=[])

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        if len(element):
            new.value = [int(item.get('value', item.text or '0')) for item in element]
        elif element.text:
            indices = element.text.split()
            new.value = [int(i) for i in indices]

        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)
        columns = 10
        text = []

        for index, entity_index in enumerate(self.value):
            text.append(str(entity_index))
            if index < len(self.value) - 1:
                text.append(" ")
            if (index + 1) % columns == 0:
                text.append("\n")

        element.text = "".join(text)

        return element


class EntitySet(RDRYtypElement):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.name = TextProperty("name")
        self.locations = LocationsBuffer()
        self.entities = RDRYtypEntities() if current_game() == SollumzGame.RDR else EntityList()


class EntitySetsList(ListProperty):
    tag_name = "entitySets"
    list_type = EntitySet

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name="entitySets", value=value or [])
        self.item_type = AttributeProperty("itemType", "CMloEntitySet")


class TimeCycleModifier(RDRYtypElement):
    tag_name = "Item"

    def __init__(self):
        self.name = TextProperty("name")
        self.sphere = QuaternionProperty("sphere")
        self.percentage = ValueProperty("percentage")
        self.range = ValueProperty("range")
        self.start_hour = ValueProperty("startHour")
        self.end_hour = ValueProperty("endHour")


class TimeCycleModifiersList(ListProperty):
    tag_name = "timeCycleModifiers"
    list_type = TimeCycleModifier

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name="timeCycleModifiers", value=value or [])
        self.item_type = AttributeProperty("itemType", "CMloTimeCycleModifier")


class MloArchetype(BaseArchetype):
    def __init__(self):
        super().__init__()
        self.type = AttributeProperty("type", "CMloArchetypeDef")
        self.mlo_flags = ValueProperty("mloFlags")
        self.entities = RDRYtypEntities() if current_game() == SollumzGame.RDR else EntityList()
        self.rooms = RoomsList()
        self.portals = PortalsList()
        self.entity_sets = EntitySetsList()
        self.timecycle_modifiers = TimeCycleModifiersList()
        if current_game() == SollumzGame.RDR:
            self.timecycle_volumes = TimeCycleVolumes()
            self.extra_activation_volumes = ActivationVolumes()
            self.main_activation_volume = ActivationVolume('mainActivationVolume')
            self.uses_activation_volumes = ValueProperty('bUsesActivationVolumes', False)


class ArchetypesList(ListProperty):
    list_type = BaseArchetype
    tag_name = "archetypes"

    @staticmethod
    def from_xml(element: ET.Element):
        new = ArchetypesList()

        for child in element:
            if "type" in child.attrib:
                arch_type = child.get("type")
                if arch_type == "CBaseArchetypeDef":
                    new.value.append(BaseArchetype.from_xml(child))
                elif arch_type == "CMloArchetypeDef":
                    new.value.append(MloArchetype.from_xml(child))
                elif arch_type == "CTimeArchetypeDef":
                    new.value.append(TimeArchetype.from_xml(child))
                else:
                    raise ValueError(f'Unsupported archetype type {arch_type}; import cancelled to prevent data loss')

        return new


class CompositeEntityType(ElementTree):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.name = TextProperty("Name")
        self.lod_dist = ValueProperty("lodDist")
        self.flags = ValueProperty("flags")
        self.special_attribute = ValueProperty("specialAttribute")
        self.bb_min = VectorProperty("bbMin")
        self.bb_max = VectorProperty("bbMax")
        self.bs_center = VectorProperty("bsCentre")
        self.bs_radius = ValueProperty("bsRadius")
        self.start_model = TextProperty("StartModel")
        self.end_model = TextProperty("EndModel")
        self.start_imap_file = TextProperty("StartImapFile")
        self.end_imap_file = TextProperty("EndImapFile")
        self.ptfx_assetname = TextProperty("PtFxAssetName")
        # TODO
        # self.animations = AnimationsList()


class CompositeEntityTypeList(ListProperty):
    list_type = CompositeEntityType
    tag_name = "compositeEntityTypes"

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name="compositeEntityTypes", value=value or [])
        self.item_type = AttributeProperty("itemType", "CCompositeEntityType")


class CMapTypes(RDRYtypElement):
    tag_name = "CMapTypes"
    rdr_opaque_tags = ('extensions', 'compositeEntityTypes')
    required_empty_tags = ('extensions', 'archetypes', 'dependencies', 'compositeEntityTypes',
                           'txdRelationships', 'entities', 'rooms', 'portals', 'entitySets',
                           'timeCycleModifiers', 'timeCycleVolumes', 'extraActivationVolumes',
                           'attachedObjects', 'locations', 'reflectionProbes', 'assetName',
                           'textureDictionary', 'clipDictionary', 'drawableDictionary', 'physicsDictionary')

    def __init__(self):
        super().__init__()
        self.extensions = ExtensionsList()
        self.archetypes = ArchetypesList()
        self.name = TextProperty("name")
        # TODO: Investigate: Not used in any ytyp file in the game?
        # self.dependencies = DependenciesListProperty()
        self.composite_entity_type = CompositeEntityTypeList()
        if current_game() == SollumzGame.RDR:
            self.extensions = RDRYtypExtensions()
        else:
            self.required_empty_tags = ()

    def to_xml(self):
        xml = super().to_xml()
        if current_game() == SollumzGame.RDR:
            for tag in ('extensions', 'archetypes', 'txdRelationships', 'dependencies', 'compositeEntityTypes'):
                if xml.find(tag) is None:
                    ET.SubElement(xml, tag)
            # Preserve empty arrays and hash-named fields through Element.write_xml.
            self.required_empty_tags = tuple({element.tag for element in xml.iter()})
        return xml


class TimeCycleVolume(RDRYtypElement):
    tag_name = 'Item'

    def __init__(self):
        self.name = TextProperty('name')
        self.center = VectorProperty('center')
        self.orientation = VectorProperty('orientation')
        self.scale = VectorProperty('scale')
        self.vol_type = ValueProperty('volType')
        self.percentage = ValueProperty('percentage')
        self.range = ValueProperty('range')
        self.start_hour = ValueProperty('startHour')
        self.end_hour = ValueProperty('endHour')


class TimeCycleVolumes(ListProperty):
    tag_name = 'timeCycleVolumes'
    list_type = TimeCycleVolume

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name, value)
        self.item_type = AttributeProperty('itemType', 'CMloTimeCycleVolume')


class ActivationBound(RDRYtypElement):
    tag_name = 'bound'

    def __init__(self):
        self.type = AttributeProperty('type', 'rage__spdSphere')
        self.sphere = QuaternionProperty('centerAndRadius')


class ActivationVolume(RDRYtypElement):
    tag_name = 'Item'

    def __init__(self, tag_name=None):
        if tag_name:
            self.tag_name = tag_name
        self.type = AttributeProperty('type', 'CMloActivationVolume')
        self.bound = ActivationBound()
        self.flags = ActivationFlags('flags')


class ActivationFlags(ElementProperty):
    value_types = (int,)

    def __init__(self, tag_name='flags', value=0):
        super().__init__(tag_name, value)

    @classmethod
    def from_xml(cls, element):
        return cls(element.tag, unsigned(element.get('value', element.text or '0'), 32))

    def to_xml(self):
        element = ET.Element(self.tag_name)
        element.text = str(self.value) if self.value else None
        return element


class ActivationVolumes(ListProperty):
    tag_name = 'extraActivationVolumes'
    list_type = ActivationVolume

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name, value)
        self.item_type = AttributeProperty('itemType', 'CMloActivationVolume')


class ReflectionProbe(RDRYtypElement):
    tag_name = 'Item'

    def __init__(self):
        self.min_extents = VectorProperty('minExtents')
        self.max_extents = VectorProperty('maxExtents')
        self.rotation = QuaternionProperty('rotation')
        self.center_offset = VectorProperty('centerOffset')
        self.influence_extents = VectorProperty('influenceExtents')
        self.probe_priority = ValueProperty('probePriority')
        self.guid = ValueProperty('guid')


class ReflectionProbes(ListProperty):
    tag_name = 'reflectionProbes'
    list_type = ReflectionProbe

    def __init__(self, tag_name=None, value=None):
        super().__init__(tag_name, value)
        self.item_type = AttributeProperty('itemType', 'CReflectionProbeData')
