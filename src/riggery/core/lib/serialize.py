from typing import Any

from ..elem import Elem

import maya.api.OpenMaya as om


def simplify(item:Any):
    """
    Tensor subtypes from riggery.datatypes don't have to be simplified, they're
    already subclassed from `list`.

    :raises TypeError: can't simplify *item*
    """
    if isinstance(item, (str, int, float)):
        return item

    if isinstance(item, list):
        return [simplify(member) for member in item]

    if isinstance(item, tuple):
        return tuple([simplify(member) for member in item])

    if isinstance(item, dict):
        return {simplify(k): simplify(v) for k, v in item.items()}

    if  isinstance(item, Elem):
        return str(item)

    elif isinstance(item,
                    (om.MVector,
                     om.MQuaternion,
                     om.MMatrix,
                     om.MEulerRotation)):
        return list(item)

    if isinstance(item, om.MPoint):
        return list(item)[:3]

    raise TypeError("Can't simplify '{}' item".format(type(item)))