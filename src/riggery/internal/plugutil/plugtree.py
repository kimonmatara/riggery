"""
Generates, or retrieves, an exhaustive list of attribute types used by various
Maya commands such as :func:`~maya.cmds.addAttr`.

The list can be accessed via the global ``DATA`` constant.
"""
import re
import os

from ..typeutil import TypeTree
from .descmtype import DATA as MTYPE_DESCS

import maya.api.OpenMaya as om
import maya.cmds as m

#--------------------------------------------|    CACHE FILE

cap = lambda x: x[0].upper()+x[1:]
uncap = lambda x: x[0].lower()+x[1:]

CACHE_FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    os.path.splitext(os.path.basename(__file__))[0]+'.txt'
)

DATA = None

#--------------------------------------------|    REGENERATE

def _generate():
    out = TypeTree.from_text(
        """
        Elem
            Attribute
                Math
                    Number
                        Float
                            Unit
                                Distance
                                Angle
                                Time
                        Int
                            Enum
                        Bool
                    Tensor
                        Tensor2
                            Tensor2Float
                            Tensor2Int
                        Tensor3
                            Tensor3Float
                                Vector
                                    Point
                                EulerRotation
                            Tensor3Int
                        Tensor4
                            Quaternion
                            Tensor4Int
                        Matrix
                Geometry
                    NurbsCurve
                        BezierCurve
                Array
        """
    )
    # Collapse descriptions
    descs = list(map(dict, set([tuple(sorted(desc.items())) \
                 for desc in MTYPE_DESCS.values()])))

    # Add geo types
    for desc in descs:
        geoType = desc.get('geoType')
        if geoType:
            key = cap(geoType)
            if key not in out:
                out._data[cap(geoType)] = 'Geometry'

    # Add arrays
    for desc in descs:
        if desc.get('isArray'):
            tensorType = desc.get('tensorType')
            if tensorType:
                key = f"{cap(tensorType)}Array"
                out._data[key] = 'Array'
            else:
                scalarType = desc.get('scalarType')
                if scalarType:
                    key = f"{cap(scalarType)}Array"
                    out._data[key] = 'Array'
                else:
                    otherType = desc.get('otherType')
                    if otherType:
                        out._data[cap(otherType)+'Array'] = 'Array'

    # Add other types
    for desc in descs:
        otherType = desc.get('otherType')
        if otherType:
            otherType = cap(otherType)
            if otherType not in out:
                out._data[otherType] = 'Attribute'

    return out

#--------------------------------------------|    INIT

def _start():
    global DATA
    try:
        with open(CACHE_FILE_PATH, 'r') as f:
            text = f.read()
            DATA = TypeTree.from_text(text)
    except FileNotFoundError:
        DATA = _generate()
        try:
            with open(CACHE_FILE_PATH, 'w') as f:
                f.write(str(DATA))
        except OSError:
            m.warning(f"Couldn't write cache file: {CACHE_FILE_PATH}")

_start()