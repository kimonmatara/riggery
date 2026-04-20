from typing import Union, Optional
from ..lib import mixedmode as _mm
from ..lib import names as _nm
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes
import riggery.internal.niceunit as _nic
from riggery.general.functions import short

import maya.api.OpenMaya as om


class Point(plugs['Vector']):

    __datacls__ = data['Point']

    # @short(origin='o', asVector='av')
    # def snapToUnitSphere(
    #         self,
    #         origin:Optional[Union['plugs.Point', 'data.Point']]=None,
    #         asVector:bool=False
    # ) -> Union['plugs.Point', 'plugs.Vector']:
    #     """
    #     Projects this point to the surface of a unit sphere. This is intended
    #     for local solving within an arbitrary (possibly skewed) matrix.
    #
    #     If *origin* itself ever exits the unit range, the solution will default
    #     to the local origin instead.
    #
    #     :param origin: the projection origin; if omitted, the return is
    #         equivalent to :meth:`normal`; defaults to None
    #     :param asVector/av: return the vector rather than the point; getting the
    #         vector is useful if you want to chain-up other effects like
    #         :meth:`~riggery.core.lib.plugtypes.Vector.coneClamp` etc.
    #     """
    #     if origin is None:
    #         out = self.normal()
    #         if asVector:
    #             return out.asVector()
    #         return out
    #
    #     origin = _mm.conform(origin,
    #                          (plugs['Point'], data['Point']),
    #                          force=True)
    #
    #     ray = self - origin
    #     a = ray.dot(ray)
    #     b = 2 * origin.dot(ray)
    #     c = origin.dot(origin) - 1.0
    #     discriminant = (b ** 2) - 4 * a * c
    #     isValid = discriminant >= 1e-5
    #
    #     pb = nodes['Network'].createNode()
    #     one = pb.addAttr('one', dv=1.0, l=True)
    #
    #     discriminant = isValid.ifElse(discriminant, one, plugs['Float'])
    #     t = (-b + (discriminant ** 0.5)) / (2 * a)
    #     outVector = t * ray
    #
    #     if asVector:
    #         return isValid.ifElse(outVector, self.normal(), plugs['Vector'])
    #
    #     return isValid.ifElse(origin + outVector, self.normal(), plugs['Point'])

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
        other, shape, isPlug = _mm.info(other, data['Quaternion'])

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
            node = nodes['MultiplyPointByMatrix'].createNode()
            node.attr('input').connectInput(self)
            node.attr('matrix').put(other, isPlug)

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

    def asVector(self) -> 'plugs.Vector':
        """
        This is purely a type change; no DG modifications are performed.
        """
        return self.asType(plugs['Vector'])

    @property
    def asMatrix(self):
        return self.asTranslateMatrix