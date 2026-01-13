from pathlib import PurePath
import maya.api.OpenMaya as om
from ..elem import Elem

def simplify(item):
    if isinstance(item, (int, float, str)):
        return item

    if isinstance(item, list):
        return [simplify(member) for member in item]

    if isinstance(item, tuple):
        return tuple([simplify(member) for member in item])

    if isinstance(item, dict):
        return {simplify(k): simplify(v) for k, v in item.items()}

    if isinstance(item, (om.MVector,
                         om.MMatrix,
                         om.MQuaternion,
                         om.MEulerRotation)):
        return list(item)

    if isinstance(item, om.MPoint):
        return list(item)[:-3]

    if isinstance(item, (Elem, PurePath)):
        return str(item)

    if item is None:
        return item

    raise TypeError("can't simplify item of type '{}'".format(type(item)))