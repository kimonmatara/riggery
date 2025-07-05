import maya.api.OpenMaya as om

from riggery.general.functions import short
from ..plugtypes import __pool__


class Int(__pool__['Number']):

    #-----------------------------------------|    Get

    def _getValue(self, *, frame=None, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        kwargs = {}
        if frame is not None:
            kwargs['context'] = om.MDGContext(
                om.MTime(frame, unit=om.MTime.uiUnit())
            )
        return plug.asInt(**kwargs)

    #-----------------------------------------|    Set

    def _setValue(self, value, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)
        plug.setInt(value)