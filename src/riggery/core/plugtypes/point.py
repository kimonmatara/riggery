from typing import Union, Optional
from ..lib import mixedmode as _mm
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes
import riggery.internal.niceunit as _nic

import maya.api.OpenMaya as om


class Point(plugs['Vector']):

    __datacls__ = _data['Point']

    #-----------------------------------------|    Set

    def _setValue(self, value, /, unit=None, ui=False, **_):
        plug = self.__apimplug__()

        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        if unit is None:
            if ui:
                unit = om.MDistance.uiUnit()
            else:
                unit = om.MDistance.kCentimeters
        elif not isinstance(unit, int):
            unit = _nic.DISTANCE_KEY_TO_VAL[unit]

        if unit != om.MDistance.kCentimeters:
            value = [
                om.MDistance(x, unit=unit).asUnits(om.MDistance.kCentimeters
                                                   ) for x in value
            ]
        super()._setValue(value)

    #-----------------------------------------|    Get

    def _getValue(self, *,
                  unit=None,
                  ui=False,
                  frame=None,
                  rotateOrder=None,
                  **_):
        out = super()._getValue(frame=frame)

        if unit is None:
            if ui:
                unit = om.MDistance.uiUnit()
            else:
                unit = om.MDistance.kCentimeters
        else:
            if not isinstance(unit, int):
                unit = _nic.DISTANCE_KEY_TO_VAL[unit]

        if unit != om.MDistance.kCentimeters:
            out[:] = [om.MDistance(value).asUnits(unit) for value in out]
        return out

    #-----------------------------------------|    Unit utils

    def unitEnums(self) -> dict:
        """
        :return: Accepted unit enums, in a dict.
        """
        return _nic.DISTANCE_ENUMS.copy()

    #-----------------------------------------|    Multiply

    def __mul__(self, other):
        """
        If *other* is a matrix, defaults to point-matrix mult.
        """
        other, shape, isPlug = _mm.info(other, _data['Quaternion'])

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            self >> node.attr('input1')
            for child in node.attr('input2').children:
                child.put(other, isPlug)
            return node.attr('output')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            self >> node.attr('input1')
            node.attr('input2').put(other, isPlug)
            return node.attr('output')

        if shape == 16:
            node = nodes.PointMatrixMult.createNode()
            self >> node.attr('inPoint')
            node.attr('inMatrix').put(other, isPlug)
            return node.attr('output')

        if shape == 4: # vector * quaternion
            return self * other.asRotateMatrix()

        return NotImplemented

    #-----------------------------------------|    Misc

    def blend(self, other, weight=0.5):
        """
        :param other: the point towards which to blend
        :param weight: the blend weight
        :return: The blended point.
        """
        # Skips over the vector implementation, since we don't want angle-based
        # blending on points
        return plugs['Tensor3'].blend(self, other, weight).asType(Point)

    #-----------------------------------------|    Conversions

    @property
    def asMatrix(self):
        return self.asTranslateMatrix