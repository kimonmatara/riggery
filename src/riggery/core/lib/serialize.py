from pathlib import PurePath
import maya.api.OpenMaya as om
from ..elem import Elem
from ...general import serialize as _ser

def handler(x):
    if isinstance(item, (om.MVector,
                         om.MMatrix,
                         om.MQuaternion,
                         om.MEulerRotation)):
        return list(item)

    if isinstance(item, om.MPoint):
        return list(item)[:-3]

    if isinstance(item, Elem):
        return str(item)

    raise TypeError

def simplify(item):
    return _ser.simplify(item, handler)