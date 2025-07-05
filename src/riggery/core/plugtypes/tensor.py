from typing import Optional, Union

import maya.cmds as m
import maya.api.OpenMaya as om

import riggery.internal.mfnmatches as _mfm
from ..plugtypes import __pool__
from ..datatypes import __pool__ as _data


class Tensor(__pool__['Math']):

    __shape__ = None
    __datacls__ = None

    #-----------------------------------------|    API

    def __apimfntype__(self):
        return om.MFnNumericAttribute

    #-----------------------------------------|    Default values

    def getDefaultValue(self):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        attr = plug.attribute()
        if attr.hasFn(om.MFn.kNumericAttribute):
            attrFn = om.MFnNumericAttribute(attr)
            out = attrFn.default
            if self.__datacls__ is not None:
                out = self.__datacls__(out)
            return out

        attrFn = om.MFnTypedAttribute(attr)
        default = attrFn.default
        if default.isNull():
            if self.__datacls__ is None:
                return tuple([0.0] * self.__shape__)
            return self.__datacls__()

        dataFn = om.MFnNumericData(default)
        out = dataFn.getData()
        if self.__datacls__ is not None:
            out = self.__datacls__(out)

        return out

    def setDefaultValue(self, value):
        plug = self.__apimplug__()

        if not plug.isDynamic:
            raise TypeError("can't edit default on non-dynamic attribute")

        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        attr = plug.attribute()
        if attr.hasFn(om.MFn.kNumericAttribute):
            attrFn = om.MFnNumericAttribute(attr)
            attrFn.default = value
        else:
            attrFn = om.MFnTypedAttribute(attr)
            dataFn = om.MFnNumericData()
            numType = getattr(om.MFnNumericData, f'k{self.__shape__}Double')
            dataObj = dataFn.create(numType)
            dataFn.setData(value)
            attrFn.default = dataObj
        return self

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

        mobj = plug.asMObject(**kwargs)
        fn = om.MFnNumericData(mobj)
        out = fn.getData()

        if self.__datacls__ is not None:
            out = self.__datacls__(out)

        return out