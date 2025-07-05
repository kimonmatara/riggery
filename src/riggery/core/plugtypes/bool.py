import maya.api.OpenMaya as om

from riggery.general.functions import short
from ..plugtypes import __pool__
from ..nodetypes import __pool__ as _nodes


class Bool(__pool__['Number']):

    #-----------------------------------------|    Logic

    def __or__(self, other):
        node = _nodes['Or'].createNode()
        self >> node.attr('input1')
        node.attr('input2').put(other)
        return node.attr('output')

    def __ror__(self, other):
        node = _nodes['Or'].createNode()
        node.attr('input1').put(other)
        self >> node.attr('input2')
        return node.attr('output')

    def __and__(self, other):
        node = _nodes['And'].createNode()
        self >> node.attr('input1')
        node.attr('input2').put(other)
        return node.attr('output')

    def __rand__(self, other):
        node = _nodes['And'].createNode()
        node.attr('input1').put(other)
        self >> node.attr('input2')
        return node.attr('output')

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
        return plug.asBool(**kwargs)

    #-----------------------------------------|    Set

    def _setValue(self, value, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)
        plug.setBool(value)