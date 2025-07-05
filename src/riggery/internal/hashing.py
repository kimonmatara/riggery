"""
Note that none of the routines in this module perform object validation.
You should ensure :class:`~maya.api.OpenMaya.MObject` instances and the like
are valid *before* passing them in here.
"""

from typing import Optional
import maya.api.OpenMaya as om
from .str2api import getArrayContext

def forNode(mObject:om.MObject) -> int:
    """
    Note that this doesn't disambiguate between DAG node instances. This is
    intentional, since you may want to use equality to detect instances.

    Direct string comparisons can be used for DAG paths.

    :param mObject: the node :class:`~maya.api.OpenMaya.MObject`.
    :return: A hash code that can be used for instance comparisons.
    """
    return om.MObjectHandle(mObject).hashCode()

def forMPlug(mPlug:om.MPlug) -> int:
    """
    :param mPlug: the plug to inspect
    :return: A hash code that can be used for instance comparisons.
    """
    nodeHash = forNode(mPlug.node())
    attrHash = om.MObjectHandle(mPlug.attribute()).hashCode()

    elems = [nodeHash, attrHash]

    # Look for multi context
    ctx = getArrayContext(mPlug)

    if ctx is not None:
        index, array = ctx
        elems.append(index)
        elems.append(om.MObjectHandle(array).hashCode())

    return hash(tuple(elems))