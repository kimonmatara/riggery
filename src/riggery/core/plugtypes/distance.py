from typing import Optional, Union

from ..plugtypes import __pool__
import riggery.internal.niceunit as _nic

import maya.api.OpenMaya as om


class Distance(__pool__['Unit']):

    __apiunittype__ = om.MDistance

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

        apiValue = plug.asMDistance(**kwargs)

        if unit is None:
            if ui:
                unit = om.MDistance.uiUnit()
            else:
                unit = om.MDistance.kCentimeters
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
                unit = om.MDistance.uiUnit()
            else:
                unit = om.MDistance.kCentimeters
        else:
            unit = self._conformUnit(unit)

        plug.setMDistance(om.MDistance(value, unit=unit))

    #-----------------------------------------|    Unit wrangling

    @classmethod
    def _conformUnit(cls, unit):
        if isinstance(unit, int):
            return unit
        return _nic.DISTANCE_KEY_TO_VAL[unit.lower()]

    def unitEnums(self) -> dict:
        return _nic.DISTANCE_ENUMS.copy()