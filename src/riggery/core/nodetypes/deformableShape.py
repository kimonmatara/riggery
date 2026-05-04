import re
from typing import Iterator, Optional, Union, Iterable, Literal

import maya.cmds as m
import maya.api.OpenMaya as om

from riggery.general.functions import short, resolve_flags
from riggery.general.iterables import without_duplicates, expand_tuples_lists
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as data
from ..lib import names as _nm
from ..elem import Elem


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

    @short(worldSpace='ws')
    def iterPoints(self,
                   api:bool=False,
                   worldSpace:bool=False
                   ) -> Iterator[Union['data.Point', om.MPoint]]:
        """
        Iterates across this geometry's 'point' positions.

        :param api: yield :class:`~maya.api.OpenMaya.MPoint` instead of
            :class:`~riggery.core.datatypes.point.Point`; defaults to False
        :param worldSpace/ws: yield world-space points; defaults to False
        """
        dagPath = self.__apimdagpath__()
        itr = om.MItGeometry(dagPath)

        out = (x.position() for x in itr)

        if worldSpace:
            worldMatrix = dagPath.inclusiveMatrix()
            out = (x * worldMatrix for x in out)

        if not api:
            T = data['Point']
            out = (T.fromApi(x) for x in out)

        yield from out

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

    @short(worldSpace='ws')
    def getOutput(self, worldSpace:bool=False):
        """
        Convenience method. Returns ``.worldOutput`` if *worldSpace* is True,
        otherwise ``.localOutput``.

        Alias: ``asPlug``.
        """
        return self.worldOutput if worldSpace else self.localOutput

    toPlug = getOutput

    def hasHistory(self) -> bool:
        """
        :return: ``True`` if there's an input on this shape node.
        """
        return next(self.input.iterInputs(), None) is not None

    @short(create='c')
    def getHistoryInput(self, create=False):
        """
        :param create/c: if there's no history input, create an 'orig' shape,
            connect it, and return its output; defaults to False
        """
        inputs = self.input.inputs(plugs=True)

        if inputs:
            return inputs[0].asType(type(self.input))

        if create:
            return plugs['Attribute'].fromStr(
                m.deformableShape(str(self), cog=True)[0]
            ).asType(type(self.input))

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

    def getDeformerInputs(self) -> tuple['DeformableShape', 'DeformableShape']:
        """
        :return: A tuple of originalGeometry, deformedGeometry. The two may flow
            from the same original shape (local / world, respectively) if called
            on a shape with no history.
        """
        historyInput = self.getHistoryInput()
        origShape = self.getOrigShape(create=True)

        if historyInput is None:
            historyInput = origShape.worldOutput

        return origShape.localOutput, historyInput

    #-------------------------------------|
    #-------------------------------------|    COMPONENT TAGS
    #-------------------------------------|

    COMPTAGPAT = re.compile(r"^(.*?)\.?(e|f|vtx|cv)\[(.*?)\]$")

    def _parseTagComponentArgs(self,
                               *args,
                               short:bool=False) -> list[str]:
        """
        Takes a mixed 'components' argument passed by the user and cleans it up.
        Where mixed mesh components are encountered, they are conformed to
        vertices.
        """
        _self = str(self)

        items = without_duplicates(map(str, expand_tuples_lists(*args)))
        history = m.geometryAttrInfo(str(self.localOutput),
                                     componentTagHistory=True)
        historyNodes = [entry['node'] for entry in history] + [_self]

        outComponents = []
        compExtensions = set()

        for item in items:
            mt = re.match(self.COMPTAGPAT, item)

            if mt:
                thisNode, thisCompExtension, thisCompIndex = mt.groups()

                if thisNode:
                    if m.objectType(thisNode, isAType='transform'):
                        thisNode = str(nodes['DagNode'](thisNode).shape)

                    if thisNode not in historyNodes:
                        raise ValueError(
                            "node not in shape history: {}".format(thisNode)
                        )
                else:
                    thisNode = _self

                compExtensions.add(thisCompExtension)
                outComponents.append(
                    f"{thisNode}.{thisCompExtension}[{thisCompIndex}]"
                )
            else:
                raise ValueError("invalid component reference: {}".format(item))

        if len(compExtensions) != 1:
            if compExtensions.issubset({'vtx', 'f', 'e'}):
                _outComponents = []

                for x in outComponents:
                    _, compType, _ = re.match(self.COMPTAGPAT, x).groups()

                    if compType == 'vtx':
                        _outComponents.append(x)
                    else:
                        kwargs = {'toVertex': True}
                        kwargs[{'f': 'fromFace',
                                'e': 'fromEdge'}[compType]] = True

                        _outComponents += m.polyListComponentConversion(
                            x,
                            **kwargs
                        )
                outComponents = _outComponents

        if short:
            outComponents = [x.split('.', 1)[1] for x in outComponents]

        return outComponents

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

    def clearComponentTags(self):
        for name in self.getComponentTagNames():
            self.deleteComponentTag(name)
        return self

    #---------------------------|   Query tag contents

    # Not implementing setComponentTagContents() yet, as wrangling component
    # list mObjects is a massive pain in the proverbial, and I have no need for
    # it right now

    def getComponentTagCompType(self, tagName:str) -> str:
        """:return: The type of component stored in the tag, e.g. 'vtx'."""

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
            out = self._parseTagComponentArgs(out, short=not long)

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

        components = self._parseTagComponentArgs(*components)

        if not components:
            components = ['{}.{}[:]'.format(self, self.__point_comp_ext__)]

        kwargs = {}

        if uniqueTagName:
            kwargs['uniqueTagName'] = True

        return m.componentTag(components,
                              create=True,
                              newTagName=tagName,
                              **kwargs)

    #---------------------------|    Live surfaces

    @classmethod
    def getLive(cls) -> Optional['DeformableShape']:
        try:
            out = m.makeLive(q=True, registry=0)
        except:
            return

        if out:
            return cls(out[0])

    @classmethod
    def makeNoneLive(cls):
        m.makeLive(none=True)

    def makeLive(self):
        m.makeLive(str(self))
        return self

    def makeDead(self):
        m.makeLive(removeObjects=str(self))
        return self

    #---------------------------|    Generic deformers

    def shrinkWrapTo(self, other:'nodes.DagNode', **swAttrs):
        """
        Configures a shrink wrap deformer.

        :param other: the 'target' geometry, as a plug or shape
        :param \*\*swAttrs: values or plugs to configure the shrinkWrap node
            attributes
        """
        origInput, deformedInput = self.getDeformerInputs()

        kwargs = {}

        if _nm.Name.__elems__:
            kwargs['name'] = _nm.Name.evaluate(nodeType='shrinkWrap')

        deformer = Elem(m.deformer(self, type='shrinkWrap', **kwargs)[0])
        other = Elem(other).toPlug(worldSpace=True)
        other >> deformer.attr('targetGeom')

        for k, v in swAttrs.items():
            deformer.attr(k).put(v)

        return deformer

    #---------------------------|   Duplicate-and-connect

    @short(newTransform='nt',
           connectTransform='ct')
    def clone(self, *, newTransform:bool=True, connectTransform:bool=True):
        """
        Similar to ``polyDuplicateAndConnect``, but works with any geo type.

        :param newTransform/nt: create a new transform for the cloned shape;
            defaults to True
        :param connectTransform/ct: ignored if *newTransform* is False; drive
            the new transform to match the current one; defaults to True
        """
        curParent = self.parent

        if newTransform:
            parent = nodes['Transform'].create(parent=curParent.parent)

            if connectTransform:
                curParent.attr('dagLocalMatrix') >> parent.attr('opm')

            parent.setMatrix(curParent.getMatrix())

        else:
            parent = curParent

        outShape = self.duplicate(parent=parent)[0]
        outShape.conformShapeName()

        self.localOutput >> outShape.input

        return outShape