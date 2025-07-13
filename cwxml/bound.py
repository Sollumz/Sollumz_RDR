from abc import ABC as AbstractClass, abstractmethod
from collections import defaultdict
from ..sollumz_properties import SollumzGame, import_export_current_game as current_game, set_import_export_current_game
from mathutils import Vector
from xml.etree import ElementTree as ET
from .element import (
    AttributeProperty,
    ElementTree,
    ElementProperty,
    FlagsProperty,
    ListProperty,
    MatrixProperty,
    ValueProperty,
    VectorProperty,
    TextProperty
)
from bpy import context


class YBN:

    file_extension = ".ybn.xml"

    @staticmethod
    def from_xml_file(filepath):
        tree = ET.parse(filepath)
        gameTag = tree.getroot().tag
        
        if "RDR2" in gameTag:
            set_import_export_current_game(SollumzGame.RDR)
            return RDRBoundFile("RDR2Bounds").from_xml_file(filepath)
        else:
            set_import_export_current_game(SollumzGame.GTA)
            return BoundFile.from_xml_file(filepath)

    @staticmethod
    def write_xml(bound_file, filepath):
        return bound_file.write_xml(filepath)


class BoundFile(ElementTree):
    tag_name = "BoundsFile"

    def __init__(self):
        super().__init__()
        set_import_export_current_game(SollumzGame.GTA)
        self.game = current_game()
        self.composite = BoundComposite()


class RDRBoundFile(ElementTree):
    tag_name = "Bounds"

    def __init__(self, tag_name: str = "Bounds"):
        self.tag_name = tag_name
        super().__init__()
        set_import_export_current_game(SollumzGame.RDR)
        self.game = current_game()
        self.type = AttributeProperty("type", "Composite")
        self.version = AttributeProperty("version", 1)
        self.box_min = VectorProperty("BoxMin")
        self.box_max = VectorProperty("BoxMax")
        self.box_center = VectorProperty("BoxCenter")
        self.sphere_center = VectorProperty("SphereCenter")
        self.sphere_radius = ValueProperty("SphereRadius", 0.0)
        self.mass = ValueProperty("Mass", 0)
        self.inertia = VectorProperty("Inertia")
        self.children = BoundList()


class Bound(ElementTree, AbstractClass):
    tag_name = "Bounds"

    def __init__(self):
        super().__init__()
        self.box_min = VectorProperty("BoxMin")
        self.box_max = VectorProperty("BoxMax")
        self.box_center = VectorProperty("BoxCenter")
        self.sphere_center = VectorProperty("SphereCenter")
        self.sphere_radius = ValueProperty("SphereRadius", 0.0)
        self.margin = ValueProperty("Margin", 0)
        self.inertia = VectorProperty("Inertia")
        if current_game() == SollumzGame.GTA:
            self.volume = ValueProperty("Volume", 0)
            self.material_index = ValueProperty("MaterialIndex", 0)
            self.material_color_index = ValueProperty("MaterialColourIndex", 0)
            self.procedural_id = ValueProperty("ProceduralID", 0)
            self.room_id = ValueProperty("RoomID", 0)
            self.ped_density = ValueProperty("PedDensity", 0)
            self.unk_flags = ValueProperty("UnkFlags", 0)
            self.poly_flags = ValueProperty("PolyFlags", 0)
            self.ref_count = ValueProperty("UnkType", 1)
        elif current_game() == SollumzGame.RDR:
            self.mass = ValueProperty("Mass", 0)
            self.unk_11h = ValueProperty("Unknown_11h", 0)


class BoundComposite(Bound):
    def __init__(self):
        super().__init__()
        self.type = AttributeProperty("type", "Composite")
        self.children = BoundList()


class BoundChild(Bound, AbstractClass):
    tag_name = "Item"

    @property
    @abstractmethod
    def type(self) -> str:
        raise NotImplementedError

    def __init__(self):
        super().__init__()
        self.type = AttributeProperty("type", self.type)

        if current_game() == SollumzGame.GTA:
            self.composite_transform = MatrixProperty("CompositeTransform")
            self.composite_flags1 = FlagsProperty("CompositeFlags1")
            self.composite_flags2 = FlagsProperty("CompositeFlags2")
        elif current_game() == SollumzGame.RDR:
            self.material_name = TextProperty("MaterialName", "")
            self.material_flags = FlagsProperty("MaterialFlags")
            self.composite_transform = MatrixProperty("Transform")
            self.type_flags = FlagsProperty("TypeFlags")
            self.include_flags = FlagsProperty("IncludeFlags")


class BoundBox(BoundChild):
    type = "Box"


class BoundSphere(BoundChild):
    type = "Sphere"


class BoundCapsule(BoundChild):
    type = "Capsule"


class BoundCylinder(BoundChild):
    type = "Cylinder"


class BoundDisc(BoundChild):
    type = "Disc"


class BoundPlane(BoundChild):
    type = "Cloth"

    @property
    def normal(self) -> Vector:
        return self.sphere_center

    @normal.setter
    def normal(self, value: Vector):
        self.sphere_center = Vector(value)


class RDRBoundBox(BoundChild):
    type = "Box"

    def __init__(self):
        set_import_export_current_game(SollumzGame.RDR)
        super().__init__()


class RDRBoundSphere(BoundChild):
    type = "Sphere"
    
    def __init__(self):
        set_import_export_current_game(SollumzGame.RDR)
        super().__init__()


class RDRBoundCapsule(BoundChild):
    type = "Capsule"

    def __init__(self):
        set_import_export_current_game(SollumzGame.RDR)
        super().__init__()


class RDRBoundCylinder(BoundChild):
    type = "Cylinder"

    def __init__(self):
        set_import_export_current_game(SollumzGame.RDR)
        super().__init__()


class RDRBoundDisc(BoundChild):
    type = "Disc"

    def __init__(self):
        set_import_export_current_game(SollumzGame.RDR)
        super().__init__()

class VerticesProperty(ElementProperty):
    value_types = (list)

    def __init__(self, tag_name: str = "Vertices", value=None):
        super().__init__(tag_name, value or [])

    @staticmethod
    def from_xml(element: ET.Element):
        new = VerticesProperty(element.tag, [])
        text = element.text.strip().split("\n")
        if len(text) > 0:
            for line in text:
                coords = line.strip().split(",")
                if not len(coords) == 3:
                    return VerticesProperty.read_value_error(element)

                new.value.append(
                    Vector((float(coords[0]), float(coords[1]), float(coords[2]))))

        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)
        text = ["\n"]

        if not self.value:
            return

        for vertex in self.value:
            if not isinstance(vertex, Vector):
                raise TypeError(
                    f"VerticesProperty can only contain Vector objects, not '{type(self.value)}'!")
            for index, component in enumerate(vertex):
                text.append(str(component))
                if index < len(vertex) - 1:
                    text.append(", ")
            text.append("\n")

        element.text = "".join(text)

        return element


class BoundGeometry(BoundChild):
    type = "Geometry"

    def __init__(self):
        super().__init__()
        if current_game() == SollumzGame.GTA:
            self.geometry_center = VectorProperty("GeometryCenter")
        # These unks are just padding, we can ignore them
        # self.unk_float_1 = ValueProperty("UnkFloat1")
        # self.unk_float_2 = ValueProperty("UnkFloat2")
        self.materials = MaterialsList()
        self.vertices = VerticesProperty("Vertices")
        # self.vertices_shrunk = VerticesProperty("VerticesShrunk") # not in official CW, for debugging with custom CW
        self.vertex_colors = VertexColorProperty("VertexColours")
        if current_game() == SollumzGame.GTA:
            self.polygons = Polygons()
        elif current_game() == SollumzGame.RDR:
            self.version = AttributeProperty("version", 1)
            self.polygons = PolygonListProperty()


class BoundGeometryBVH(BoundGeometry):
    type = "GeometryBVH"

    def __init__(self):
        super().__init__()


class BoundList(ListProperty):
    list_type = BoundChild
    tag_name = "Children"
    item_tag_name = "Item"
    allow_none_items = True

    def __init__(self):
        if current_game() == SollumzGame.RDR:
            self.tag_name = "Bounds"
            self.version = AttributeProperty("version", 1)
        super().__init__(self.tag_name)

    @staticmethod
    def from_xml(element: ET.Element):
        new = BoundList()

        for child in element.iter():
            if "type" in child.attrib:
                bound_type = child.get("type")
                if bound_type == "Box":
                    new.value.append(BoundBox.from_xml(child))
                elif bound_type == "Sphere":
                    new.value.append(BoundSphere.from_xml(child))
                elif bound_type == "Capsule":
                    new.value.append(BoundCapsule.from_xml(child))
                elif bound_type == "Cylinder":
                    new.value.append(BoundCylinder.from_xml(child))
                elif bound_type == "Disc":
                    new.value.append(BoundDisc.from_xml(child))
                elif bound_type == "Cloth":
                    new.value.append(BoundPlane.from_xml(child))
                elif bound_type == "Geometry":
                    new.value.append(BoundGeometry.from_xml(child))
                elif bound_type == "GeometryBVH":
                    new.value.append(BoundGeometryBVH.from_xml(child))
                elif bound_type == "None":
                    # For fragments it is important to keep the null entries in the composite children array
                    new.value.append(None)

        return new

    def create_element_for_none_item(self) -> ET.Element:
        return ET.Element(self.item_tag_name, attrib={"type": "None"})


class Material(ElementTree):
    tag_name = "Item"

    def __init__(self):
        super().__init__()
        self.room_id = ValueProperty("RoomID", 0)
        self.flags = FlagsProperty()
        self.unk = ValueProperty("Unk", 0)
        if current_game() == SollumzGame.GTA:
            self.type = ValueProperty("Type", 0)
            self.procedural_id = ValueProperty("ProceduralID", 0)
            self.ped_density = ValueProperty("PedDensity", 0)
            self.material_color_index = ValueProperty("MaterialColourIndex", 0)
        if current_game() == SollumzGame.RDR:
            self.name = TextProperty("Name")
            self.procedural_id = ValueProperty("ProcID", 0)


class MaterialsList(ListProperty):
    list_type = Material
    tag_name = "Materials"


class VertexColorProperty(ElementProperty):
    value_types = (list[tuple[int, int, int, int]])

    def __init__(self, tag_name: str = "VertexColours", value=None):
        super().__init__(tag_name, value or [])

    @staticmethod
    def from_xml(element: ET.Element):
        new = VertexColorProperty(element.tag, [])
        text = element.text.strip().split("\n")
        if len(text) > 0:
            for line in text:
                colors = line.strip().split(",")
                if len(colors) != 4:
                    return VertexColorProperty.read_value_error(element)

                new.value.append((int(colors[0]), int(colors[1]), int(colors[2]), int(colors[3])))

        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)
        element.text = "\n"

        if len(self.value) == 0:
            return None

        for color in self.value:
            for index, component in enumerate(color):
                element.text += str(int(component))
                if index < len(color) - 1:
                    element.text += ", "
            element.text += "\n"

        return element


class Polygon(ElementTree, AbstractClass):
    def __init__(self):
        super().__init__()
        self.material_index = AttributeProperty("m", 0)


class Polygons(ListProperty):
    list_type = Polygon
    tag_name = "Polygons"

    @staticmethod
    def from_xml(element: ET.Element):
        new = Polygons()

        for child in element.iter():
            if child.tag == "Box":
                new.value.append(PolyBox.from_xml(child))
            elif child.tag == "Sphere":
                new.value.append(PolySphere.from_xml(child))
            elif child.tag == "Capsule":
                new.value.append(PolyCapsule.from_xml(child))
            elif child.tag == "Cylinder":
                new.value.append(PolyCylinder.from_xml(child))
            elif child.tag == "Triangle":
                new.value.append(PolyTriangle.from_xml(child))

        return new


class PolyTriangle(Polygon):
    tag_name = "Triangle"

    def __init__(self):
        super().__init__()
        self.v1 = AttributeProperty("v1", 0)
        self.v2 = AttributeProperty("v2", 0)
        self.v3 = AttributeProperty("v3", 0)
        self.f1 = AttributeProperty("f1", 0)
        self.f2 = AttributeProperty("f2", 0)
        self.f3 = AttributeProperty("f3", 0)


class PolySphere(Polygon):
    tag_name = "Sphere"

    def __init__(self):
        super().__init__()
        self.v = AttributeProperty("v", 0)
        self.radius = AttributeProperty("radius", 0)


class PolyCapsule(Polygon):
    tag_name = "Capsule"

    def __init__(self):
        super().__init__()
        self.v1 = AttributeProperty("v1", 0)
        self.v2 = AttributeProperty("v2", 1)
        self.radius = AttributeProperty("radius", 0)


class PolyBox(Polygon):
    tag_name = "Box"

    def __init__(self):
        super().__init__()
        self.v1 = AttributeProperty("v1", 0)
        self.v2 = AttributeProperty("v2", 1)
        self.v3 = AttributeProperty("v3", 2)
        self.v4 = AttributeProperty("v4", 3)


class PolyCylinder(Polygon):
    tag_name = "Cylinder"

    def __init__(self):
        super().__init__()
        self.v1 = AttributeProperty("v1", 0)
        self.v2 = AttributeProperty("v2", 1)
        self.radius = AttributeProperty("radius", 0)


class PolygonListProperty(ElementProperty):
    value_types = (list)

    def __init__(self, tag_name: str = "Polygons", value=None):
        super().__init__(tag_name, value or [])

    @staticmethod
    def from_xml(element: ET.Element):
        new = PolygonListProperty(element.tag, [])
        text = element.text.strip().split("\n")
        if len(text) > 0:
            for line in text:
                line = line.strip().split(" ")
                if len(line) > 0:
                    poly = [line[0]]
                    for item in line[1:]:
                        if (poly[0] == 'Cyl' and len(poly) == 4) or \
                          (poly[0] == 'Sph' and len(poly) == 3) or \
                          (poly[0] == 'Cap' and len(poly) == 4) or \
                          (poly[0] == "Cyl" and len(poly) == 4):
                            poly.append(float(item))
                        else:
                            poly.append(int(item))
                    new.value.append(poly)
        return new
    
    def to_xml(self):
        element = ET.Element(self.tag_name)
        element.text = "\n"

        if len(self.value) == 0:
            return None

        for poly in self.value:
            element.text += (poly + "\n")

        return element
