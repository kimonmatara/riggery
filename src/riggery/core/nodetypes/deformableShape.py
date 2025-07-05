import maya.cmds as m
import maya.api.OpenMaya as om

from riggery.general.functions import short
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs


class DeformableShape(nodes['GeometryShape']):

    @property
    def input(self):
        """
        :return: The object-space input of this shape node.
        """
        attrName = m.deformableShape(
            str(self),
            localShapeInAttr=True
        )[0]
        return self.attr(attrName)

    @property
    def localOutput(self):
        """
        :return: The object-space output of this shape node.
        """
        attrName = m.deformableShape(
            str(self),
            localShapeOutAttr=True
        )[0]
        return self.attr(attrName)

    @property
    def worldOutput(self):
        """
        :return: The world-space output of this shape node.
        """
        attrName = m.deformableShape(
            str(self),
            worldShapeOutAttr=True
        )[0]
        return self.attr(attrName)

    def hasHistory(self) -> bool:
        """
        :return: ``True`` if there's an input on this shape node.
        """
        return self.input.hasInput()

    @short(create='c')
    def getHistoryInput(self, create=False):
        """
        :param create/c: if there's no history input, create an 'orig' shape,
            connect it, and return its output; defaults to False
        """
        inputs = self.input.inputs(plugs=True)

        if inputs:
            return inputs[0]

        if create:
            return plugs['Attribute'].fromStr(m.deformableShape(str(self),
                                                                cog=True)[0])

    def newInput(self):
        """
        If this shape has an incoming input, inserts a new 'orig' shape
        between that input and this shape. Otherwise, creates a default
        'orig' shape. The shape's output is returned in all cases.
        """
        existingInput = self.input.inputs(plugs=True)
        if existingInput:
            existingInput = existingInput[0]
            existingInput // self.input
        newInput = plugs['Attribute'](
            m.deformableShape(str(self),
                              originalGeometry=True,
                              createOriginalGeometry=True)[0]
        )
        if existingInput:
            existingInput >> newInput.node().input
        return newInput

    @short(create='c')
    def getOrigShape(self, create=False):
        """
        :param create/c: create an 'orig' shape if one doesn't already exist;
            defaults to False
        """
        result = m.deformableShape(str(self),
                                   originalGeometry=True,
                                   createOriginalGeometry=create)[0]
        if (not create) and result == '':
            return None
        return plugs['Attribute'](result).node()