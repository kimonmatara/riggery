from typing import Optional, Union
import math
from ..plugtypes import __pool__
plugs = __pool__
from ..nodetypes import __pool__ as nodes

import riggery.internal.niceunit as _nic
from riggery.core.lib import names as _nm
import riggery.core.lib.mixedmode as _mm
from riggery.general.functions import short

import maya.api.OpenMaya as om


class Angle(__pool__['Unit']):

    __apiunittype__ = om.MAngle

    #-----------------------------------------|    Get

    def _getValue(self, *,
                  frame=None,
                  unit=None,
                  ui=False, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        kwargs = {}
        if frame is not None:
            kwargs['context'] = om.MDGContext(
                om.MTime(frame, unit=om.MTime.uiUnit())
            )

        apiValue = plug.asMAngle(**kwargs)

        if unit is None:
            if ui:
                unit = om.MAngle.uiUnit()
            else:
                unit = om.MAngle.kRadians
        else:
            unit = self._conformUnit(unit)

        if apiValue.unit != unit:
            return apiValue.asUnits(unit)
        return apiValue.value

    #-----------------------------------------|    Set

    def _setValue(self, value, *, unit=None, ui=False, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        if unit is None:
            if ui:
                unit = om.MAngle.uiUnit()
            else:
                unit = om.MAngle.kRadians
        else:
            unit = self._conformUnit(unit)

        plug.setMAngle(om.MAngle(value, unit=unit))

    #-----------------------------------------|    Units

    @classmethod
    def _conformUnit(cls, unit):
        if isinstance(unit, int):
            return unit
        return _nic.ANGLE_KEY_TO_VAL[unit.lower()]

    def unitEnums(self) -> dict:
        return _nic.ANGLE_ENUMS.copy()

    #-----------------------------------------|    Misc

    @short(keepZero='kz')
    def reverseDirection(self, keepZero:bool=False) -> 'Angle':
        out = self.isNegative().ifElse(self + math.radians(360),
                                       self - math.radians(360),
                                       Angle)
        if keepZero:
            out = self.isZero().ifElse(self, out, Angle)

        return out

    def unwind(self) -> 'Angle':
        """
        Keeps this angle within the -360 -> 360 range.
        """
        return self.isNegative().ifElse(self % -math.radians(360),
                                        self % math.radians(360),
                                        Angle)

    def wind(self, numTurns:_mm.MixedScalar, *, unwind:bool=True) -> 'Angle':
        """
        This will only really make sense if *numTurns* (whether a value or plug)
        is always positive, since the direction is taken from the current angle.

        :param unwind: only set this to False if you know that this angle is
            already unwound; defaults to True
        """
        if unwind:
            self = self.unwind()

        pb = nodes['Network'].createNode()

        bulk = pb.addAttr('bulk',
                          at='doubleAngle').put(math.radians(360) * numTurns)

        return self + self.isNegative().ifElse(-bulk, bulk, Angle)

    def turns(self,
              trunc:bool=True,
              abs:bool=True) -> Union['plugs.Float', 'plugs.Int']:
        """
        :param abs: return a positive number of turns, even the input angle is
            negative; defaults to True
        :param trunc: return a whole number of turns; defaults to True
        :return: The number of 360 turns in this angle.
        """
        isNegative = self.isNegative()
        angle = isNegative.ifElse(-self, self, Angle)

        winds = angle / math.radians(360.0)

        if trunc:
            winds = winds.trunc()

        if not abs:
            winds = isNegative.ifElse(-winds, winds, type(winds))

        return winds