import re
from typing import Iterator, Optional, Union, Iterable, Literal

import maya.cmds as m
import maya.api.OpenMaya as om

from riggery.general.functions import short, resolve_flags
from riggery.general.iterables import without_duplicates, expand_tuples_lists
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs


# class ComponentTags:
#
#     #-----------------------------------|    Init
#
#     def __init__(self, shape):
#         self._node = shape
#
#     #-----------------------------------|    Props
#
#     def node(self) -> 'DeformableShape':
#         return self._node
#
#     #-----------------------------------|    Get
#
#     def keys(self) -> Iterator[str]:
#         yield from iter(self._node.localOutput.getComponentTagNames())
#
#     def values(self) -> Iterator[list[str]]:
#         plug = self._node.localOutput
#
#         for name in plug.getComponentTagNames():
#             yield plug.evalComponentTagExpression(name)
#
#     def items(self) -> Iterator[tuple[str, list[str]]]:
#         plug = self._node.localOutput
#
#         for key in plug.getComponentTagNames():
#             yield key, plug.evalComponentTagExpression(key)
#
#     def __getitem__(self, tagName:str):
#         return self._node.localOutput.evalComponentTagExpression(tagName)
#
#     def __len__(self) -> int:
#         return len(self._node.localOutput.getComponentTagNames())
#
#     #-----------------------------------|    Remove
#
#     def __delitem__(self, tagName:str):
#         self._node.deleteComponentTag(tagName)
#
#     #-----------------------------------|    Repr
#
#     def __repr__(self):
#         return "{}({})".format(self.__class__.__name__, repr(self._node))


class DeformableShape(nodes['GeometryShape']):

    __point_comp_ext__ = None # e.g. 'vtx'

    # @property
    # def componentTags(self):
    #     return ComponentTags(self)

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

    #-------------------------------------|
    #-------------------------------------|    COMPONENT TAGS
    #-------------------------------------|

    COMPTAGPAT = re.compile(r"^(.*?)\.?(e|f|vtx|cv)\[(.*?)\]$")

    def _parseTagComponentArgs(self, *args, short:bool=False
                               ) -> tuple[str, list[str]]:
        """
        :param \*args: user-provided component references, e.g. 'pCube1.vtx[0]',
            or short-form, e.g. 'vtx[0]', or lists thereof
        :param short: don't include the node name in the returned component
            strings; defaults to False
        :return: Tuple of <component extension (e.g. 'vtx')>, list of components
        """
        _self = str(self)

        items = without_duplicates(map(str, expand_tuples_lists(*args)))
        history = m.geometryAttrInfo(str(self.localOutput),
                                     componentTagHistory=True)
        historyNodes = [entry['node'] for entry in history]

        components = []
        compExtension = None

        for item in items:
            mt = re.match(self.COMPTAGPAT, item)

            if mt:
                thisNode, thisCompExtension, thisCompIndex = mt.groups()

                if compExtension is None:
                    compExtension = thisCompExtension
                else:
                    if compExtension != thisCompExtension:
                        raise ValueError(
                            "only one component type may be specified"
                        )

                if thisNode:
                    if thisNode not in historyNodes:
                        raise ValueError(
                            "node not in shape history: {}".format(thisNode)
                        )
                    if short:
                        components.append(
                            f"{thisCompExtension}[{thisCompIndex}]"
                        )
                    else:
                        components.append(
                            f"{thisNode}.{thisCompExtension}[{thisCompIndex}]"
                        )
                else:
                    if short:
                        components.append(
                            f"{thisCompExtension}[{thisCompIndex}]"
                        )
                    else:
                        components.append(
                            f"{_self}.{thisCompExtension}[{thisCompIndex}]"
                        )
            else:
                raise ValueError("invalid component reference: {}".format(item))

        return compExtension, components

    #---------------------------|    Query tags

    def getComponentTagNames(self) -> list[str]:
        """:return: The names of component tags on this node."""
        return m.geometryAttrInfo(str(self.localOutput), componentTagNames=True)

    def hasComponentTag(self, tagName:str) -> bool:
        """
        :return: True if the specified tag exists on this shape, otherwise
            False.
        """
        return tagName in self.getComponentTagNames()

    def _iterComponentTagHistory(self) -> Iterator[tuple[str, dict]]:
        for entry in m.geometryAttrInfo(str(self.localOutput),
                                        componentTagHistory=True):
            key = entry.pop('key')
            yield key, entry

    def _getComponentTagSlot(self, tagName:str) -> str:
        for k, v in self._iterComponentTagHistory():
            if k == tagName:
                node = v['node']
                _arr = f"{node}.componentTags"
                indices = m.getAttr(_arr, mi=True)

                if indices:
                    for index in indices:
                        _slot = f"{_arr}[{index}]"
                        name = m.getAttr(f"{_slot}.componentTagName")

                        if name == tagName:
                            return _slot

        raise KeyError(f"no match for tag name '{tagName}'")

    def getComponentTagSlot(self, tagName:str) -> 'plugs.Attribute':
        return plugs['Attribute'](self._getComponentTagSlot(tagName))

    #---------------------------|    Rename tags

    def renameComponentTag(self, tagName:str, newTagName:str):
        """
        :param tagName: the name of the tag to rename
        :param newTagName: the new name for the tag
        """
        if tagName != newTagName:
            if not m.componentTag(str(self),
                                  tagName=tagName,
                                  newTagName=newTagName,
                                  rename=True):
                names = self.getComponentTagNames()

                if tagName not in names:
                    raise KeyError(f"no match for tag name '{tagName}'")

                if newTagName in names:
                    raise KeyError(f"tag name '{newTagName}' is in use")

        return self

    #---------------------------|    Remove tags

    def deleteComponentTag(self, tagName:str):
        """
        Banishes the specified component tag, whether it's 'final' (existing) or
        pending.

        :raises KeyError: couldn't find the specified tag
        """
        if not m.componentTag(str(self), tagName=True, delete=True):
            m.removeMultiInstance(self._getComponentTagSlot(tagName), b=True)

        return self

    #---------------------------|   Query tag contents

    # Not implementing setComponentTagContents() yet, as wrangling component
    # list mObjects is a massive pain in the proverbial, and I have no need for
    # it right now

    def getComponentTagCompType(self, tagName:str) -> str:
        """
        :return: The type of component stored in the tag, e.g. 'vtx'.
        """
        slot = self._getComponentTagSlot(tagName)
        contents = m.getAttr(f"{slot}.componentTagContents")

        for x in contents:
            return re.match(self.COMPTAGPAT, x).groups()[1]

    def getComponentTagContents(self,
                                tagName:str,
                                long:bool=False) -> list[str]:
        slot = plugs['Attribute'](self._getComponentTagSlot(tagName))
        out = slot.attr('componentTagContents')()

        if long:
            _, out = self._parseTagComponentArgs(out, short=not long)

        return out

    #---------------------------|    Create tags

    @short(uniqueTagName='utn',
           replace='r')
    def createComponentTag(self,
                           tagName:str,
                           *components,
                           uniqueTagName:bool=False,
                           replace:bool=False) -> str:
        """
        :param uniqueTagName/utn: force a unique tag name; defaults to False
        :param replace/r: remove any tag with the same name; defaults to False
        :raises KeyError: the specified tag name is in use
        :return: The resolved tag name.
        """
        if not uniqueTagName:
            if tagName in self.getComponentTagNames():
                if replace:
                    self.deleteComponentTag(tagName)
                else:
                    raise KeyError("tag name '{}' is in use".format(tagName))

        _, components = self._parseTagComponentArgs(*components)

        if not components:
            components = ['{}.{}[:]'.format(self, self.__point_comp_ext__)]

        kwargs = {}

        if uniqueTagName:
            kwargs['uniqueTagName'] = True

        return m.componentTag(components,
                              create=True,
                              newTagName=tagName,
                              **kwargs)