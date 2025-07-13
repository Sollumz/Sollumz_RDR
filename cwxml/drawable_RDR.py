import io
import os
from xml.etree.ElementTree import Element
from ..cwxml.element import Element
from mathutils import Matrix
import numpy as np
from numpy.typing import NDArray
from ..tools.utils import np_arr_to_str
from typing import Optional
from abc import ABC as AbstractClass, abstractmethod
from xml.etree import ElementTree as ET
from .element import (
    AttributeProperty,
    FlagsProperty,
    Element,
    ColorProperty,
    ElementTree,
    ElementProperty,
    ListProperty,
    QuaternionProperty,
    TextProperty,
    ValueProperty,
    VectorProperty,
    Vector4Property,
    MatrixProperty
)
from collections.abc import MutableSequence


VERT_ATTR_DTYPES = {
    "P": ["Position", np.float32, 3],
    "N": ["Normal", np.float32, 4],
    "X": ["Tangent", np.float32, 4],
    "W": ["BlendWeights", np.uint32, 4],
    "I": ["BlendIndices", np.uint32, 4],
    "C": ["Colour", np.uint32, 4],
    "T": ["TexCoord", np.float32, 2],
}

semantic_layout = None


def get_str_type(value: str):
    """Determine if a string is a bool, int, or float"""
    if isinstance(value, str):
        if value.lower() == "true" or value.lower() == "false":
            return bool(value)

        try:
            return int(value)
        except:
            pass
        try:
            return float(value)
        except:
            pass

    return value


class BoneMappingProperty(ElementProperty):
    value_types = (list)

    def __init__(self, tag_name: str = "BoneMapping", value=None):
        super().__init__(tag_name, value or [])

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        if element.text:
            text = element.text.strip().split("\n")
            if len(text) > 0:
                for line in text:
                    items = line.strip().split("   ")
                    for item in items:
                        words = item.strip().split(" ")
                        item = [get_str_type(word) for word in words]
                        new.value.extend(item)
        return new
    
    def to_xml(self):
        element = ET.Element(self.tag_name)

        if not self.value:
            return None

        element.text = " ".join([str(id) for id in self.value])
        return element


class VertexLayout(ElementTree):
    tag_name = "VertexLayout"

    def __init__(self):
        super().__init__()
        self.semantics = None
        self.formats = TextProperty("Formats")
        self.non_interleaved = ValueProperty("NonInterleaved", 0)

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = super().from_xml(element)

        data_elem = element.find("Semantics")
        new._load_data_from_str(data_elem.text)
        return new
    
    def to_xml(self):
        element = super().to_xml()
        if self.semantics is None:
            return element

        data_elem = ET.Element("Semantics")
        data_elem.text = self.semantics
        element.append(data_elem)

        return element
        # self.semantics = semantic_layout
    
    def _load_data_from_str(self, _str: str):
        text = list(_str)
        global semantic_layout
        semantic_layout = text
        self.semantics = text


class VerticesProperty(ElementProperty):
    value_types = (list)

    global VERT_ATTR_DTYPES
    def __init__(self, tag_name: str = "Vertices", value=None):
        super().__init__(tag_name, value or [])

    
    def _load_data_from_str(self, _str: str):
        struct_dtype = np.dtype(self._create_dtype())
        a = np.loadtxt(io.StringIO(_str), dtype=struct_dtype)
        return a

    def _create_dtype(self):
        new_dtype = []
        current_semantic = None
        count = -1
        for this_semantic in semantic_layout:
            if current_semantic is None:
                current_semantic = this_semantic
            elif current_semantic != this_semantic:
                current_semantic = this_semantic
                count = -1
            
            entry = VERT_ATTR_DTYPES[this_semantic].copy()
            if count == -1 and entry[0] in ("Colour", "TexCoord"):
                entry[0] = entry[0] + "0"
            elif count >= 0:
                entry[0] = entry[0] + str(count+1)
            new_dtype.append(tuple(entry))
            count += 1
        return new_dtype

    @classmethod
    def from_xml(cls, element: ET.Element):
        new = cls()
        if element.text.strip():
            a = new._load_data_from_str(element.text)
            new.value = a
        return new

    def to_xml(self):
        element = ET.Element(self.tag_name)

        # if not self.value:
        if hasattr(self, "value") and self.value is None:
            return None
        # element.text = ", ".join([str(id) for id in self.value])
        element.text = self._data_to_str()
        return element
    
    def _data_to_str(self):
        vert_arr = self.value

        FLOAT_FMT = "%.7f"
        INT_FMT = "%.0u"
        # ATTR_SEP = "   "
        ATTR_SEP = "\t"

        formats: list[str] = []
        for field_name in vert_arr.dtype.names:
            attr_dtype = vert_arr.dtype[field_name].base
            column = vert_arr[field_name]

            attr_fmt = INT_FMT if attr_dtype == np.uint32 else FLOAT_FMT
            formats.append(" ".join([attr_fmt] * column.shape[1]))

        fmt = ATTR_SEP.join(formats)
        vert_arr_2d = np.column_stack(
            [vert_arr[name] for name in vert_arr.dtype.names])

        return np_arr_to_str(vert_arr_2d, fmt)
    
    def _write_semantic_layout(self):
        vert_arr = self.value

        for field_name in vert_arr.dtype.names:
            for key, value in VERT_ATTR_DTYPES.items():
                if value[0] in field_name:
                    semantic_layout = ""+key


class IndicesProperty(ElementProperty):
    value_types = [NDArray]

    def __init__(self, tag_name: str = "Indices", value=None):
        super().__init__(tag_name, value or [])

    @staticmethod
    def from_xml(element: ET.Element):
        new = IndicesProperty(element.tag, [])

        if element.text and len(element.text.strip()) > 0:
            new = np.fromstring(element.text, sep=" ", dtype=np.uint32)
        return new
    

    def _inds_to_str(self):
        indices_arr = self.value

        num_inds = len(indices_arr)

        # Get number of rows that can be split into 24 columns
        num_divisble_inds = num_inds - (num_inds % 24)
        num_rows = int(num_divisble_inds / 24)

        indices_arr_2d = indices_arr[:num_divisble_inds].reshape(
            (num_rows, 24))

        index_buffer_str = np_arr_to_str(indices_arr_2d, fmt="%.0u")
        # Add the last row
        last_row_str = np_arr_to_str(
            indices_arr[num_divisble_inds:], fmt="%.0u")

        return f"{index_buffer_str}\n{last_row_str}"

    def to_xml(self):
        if len(self.value) < 1:
            return None

        element = ET.Element(self.tag_name)

        if len(self.value) > 0:
            element.text = self._inds_to_str()
        return element


