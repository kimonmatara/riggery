import re
from typing import Iterator, Optional, Union, Iterable

import maya.cmds as m
import maya.api.OpenMaya as om

from riggery.general.functions import short, resolve_flags
from riggery.general.iterables import without_duplicates, expand_tuples_lists
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs


class DeformableShape(nodes['GeometryShape']):

    def __apipointiterator__(self) -> om.MItGeometry:
        return om.MItGeometry(self.__apimdagpath__())

    def numPoints(self) -> int:
        return self.__apipointiterator__().count()

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

    #-------------------------------------|    Component tag management

    COMP_TAIL_PAT = re.compile(r"^.*?\.?((?:vtx|e|f|cv)\[.*?\])$")

    def _parseComponents(self, *components):
        out = []
        _self = str(self)

        for component in filter(
                bool,
                without_duplicates(
                    expand_tuples_lists(*components)
                )
        ):
            mt = re.match(self.COMP_TAIL_PAT, component)

            if mt:
                out.append('.'.join((_self, mt.group(1))))
            else:
                raise ValueError(f"can't parse component: {component}")

        return out

    # # use geometryAttrInfo() for more
    # @short(uniqueTagName='utn')
    # def createComponentTag(self,
    #                        newTagName:str,
    #                        *components,
    #                        uniqueTagName:bool=False,
    #                        replace:bool=False) -> str:
    #     """
    #     :param newTagName: the new tag name
    #     :param compType: the type of component indices being passed in; one of
    #         'vtx', 'e', 'f', 'cv'
    #     :param compIndices: the component indices
    #     :param uniqueTagName/utn: make the tag name unique; defaults to False
    #     :param replace: if the component tag already exists, and *uniqueTagName*
    #         if False, replace it instead of throwing RuntimeError; defaults to
    #         False
    #     :return: The resolved component tag name.
    #     """
    #     components = self._parseComponents(*components)
    #
    #     if components:
    #         args = (components,)
    #     else:
    #         args = (str(self),)
    #
    #     kwargs = {'newTagName': newTagName, 'create': True}
    #
    #     if uniqueTagName:
    #         kw['uniqueTagName'] = True
    #
    #     return m.componentTag(*args, **kwargs)
    #
    # def getComponentTagNames(self) -> list[str]:
    #     """
    #     Note that, on shapes with no history, tags are regarded as 'pending' and
    #     not 'final'.
    #
    #     :return: The names of component tags on this node.
    #     """
    #     out = m.geometryAttrInfo(str(self.localOutput), componentTagNames=True)
    #
    #     if out:
    #         return out
    #
    #     return []