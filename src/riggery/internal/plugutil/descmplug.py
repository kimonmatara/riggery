import re

from .parseaac import parseAddAttrCmd
from .descmtype import DATA as DESCS
from .. import api2str as _a2s

import maya.api.OpenMaya as om
import maya.cmds as m

notNone = lambda x: x is not None
IS_NUM_COMPOUND = re.compile(r"^.*?[2-4]$")

__verbose__ = False

def describeMPlug(plug:om.MPlug) -> dict:
    """
    :param plug: the plug to inspect
    :return: A dictionary with one or more of the following keys:
        .. code-block:: python:
            geoType: str # e.g. 'nurbsCurve'
            tensorType: str # e.g. 'matrix'
            tensorShape: int # e.g. 3 for vector
            unitType: Literal['angle', 'distance', 'time']
            otherType: str # e.g. 'enum'
            scalarType: Literal['int', 'float', 'bool']
            isArray:bool # i.e. it's a data array (multis don't count)
    """
    out = {}

    mObject = plug.attribute()
    mFn = om.MFnAttribute(mObject)
    aaInfo = parseAddAttrCmd(mFn.getAddAttrCmd(longFlags=True))

    attrType = aaInfo.get('attributeType')

    if attrType is None:
        try:
            dataType = aaInfo['dataType']
        except KeyError:
            if __verbose__:
                m.warning(f"Can't classify attribute: {plug}")
            return out
        out.update(DESCS.get(dataType, {}))

        if (not out) or (out.get('geoType') == 'nurbsCurve'):
            evaluatedType = m.getAttr(_a2s.fromMPlug(plug), type=True)
            out.update(DESCS.get(evaluatedType, {}))
    elif attrType == 'typed':
        if __verbose__:
            m.warning(f"Can't classify attribute: {plug}")
        return out

    if plug.isCompound:
        shape = plug.numChildren()
        if shape:
            # Won't be able to get children if this is an array
            if plug.isArray:
                parent = plug.elementByLogicalIndex(0)
            else:
                parent = plug

            children = [parent.child(x) for x in range(shape)]
            childInfos = [describeMPlug(child) for child in children]
            scalarTypes = list(
                filter(notNone,
                       [x.get('scalarType') for x in childInfos])
            )
            # We don't want to treat compounds-of-tensors as tensors themselves
            if scalarTypes and not any(('tensorShape' in child
                            or 'tensorType' in child for child in childInfos)):
                if len(scalarTypes) == shape:
                    out['tensorShape'] = shape
                    if len(set(scalarTypes)) == 1:
                        out['scalarType'] = scalarType = scalarTypes[0]

                        if scalarType == 'float':
                            unitTypes = list(
                                filter(
                                    notNone,
                                    [x.get('unitType') for x in childInfos]
                                )
                            )
                            unitType = None

                            if len(unitTypes) == shape:
                                if len(set(unitTypes)) == 1:
                                    out['unitType'] \
                                        = unitType = unitTypes[0]
    else:
        out.update(DESCS.get(attrType, {}))

    return out