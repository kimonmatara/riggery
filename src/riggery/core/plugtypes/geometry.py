from typing import Union, Optional

import maya.api.OpenMaya as om
import maya.cmds as m

from ..lib import names as _nm
from riggery.general.functions import short, resolve_flags
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from riggery.internal.nodeinfo import UNCAPMAP

uncap = lambda x: x[0].lower()+x[1:]


Attribute = plugs['Attribute']

class GeometryMeta(type(Attribute)):

    def __new__(meta, clsname, bases, dct):
        dct.setdefault('__shape_class_name__', clsname)
        return super().__new__(meta, clsname, bases, dct)


class Geometry(Attribute, metaclass=GeometryMeta):

    __shape_class_name__ = 'GeometryShape'

    #--------------------------------------|    Data sampling

    def _getSamplingPlug(self) -> om.MPlug:
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)
        return plug

    def _getData(self) -> om.MObject:
        return self._getSamplingPlug().asMDataHandle().data()

    #--------------------------------------|    Shape interops

    @classmethod
    def getShapeClass(cls) -> type:
        """
        :return: The associated :class:`~riggery.nodetypes.GeometryShape`
            subclass for this geometry type.
        """
        n = cls.__shape_class_name__
        if not n:
            n = cls.__name__
        return nodes[n]

    @short(create='c')
    def getOrigShape(self, create=False):
        """
        Looks for an 'orig shape' of the same type as this plug.
        :param create/c: attempt to create an 'orig shape' if one doesn't
            exist
        """
        nearestShape = self.findShape(past=True)

        if nearestShape is not None:
            if nearestShape.hasHistory() or \
                    not nearestShape.attr('intermediateObject').get():
                return nearestShape.getOrigShape(create=create)
            return nearestShape

    @short(includeThisNode='itn')
    def findShape(self, *,
                  past=None,
                  future=None,
                  includeThisNode=True):
        """
        Looks for a shape node matching this plug type. The *past* / *future*
        arguments are evaluated by omission. If both are on, past is searched
        first.

        :param includeThisNode/itn: include this plug's owner node in the
            search; defaults to ``True``
        """
        shapeClass = nodes[self.__shape_class_name__]
        nodeType = shapeClass.__melnode__

        if includeThisNode:
            thisNode = self.node()
            if nodeType in thisNode.nodeType(i=1):
                return thisNode

        past, future = resolve_flags(past, future)

        _self = str(self)
        for item in m.listHistory(_self)[1:]:
            if nodeType in m.nodeType(item, i=True):
                return nodes['Shape'](item)

        for item in m.listHistory(_self, future=True)[1:]:
            if nodeType in m.nodeType(item, i=True):
                return nodes['Shape'](item)

    def findParent(self):
        """
        Attempts to detect the nearest transform parent. Traverses past history
        first, then future history. If no parent can be detected, None is
        returned.
        """
        _self = str(self)
        thisNode = _self.split('.')[0]

        if 'shape' in m.nodeType(thisNode, i=True):
            return nodes['DagNode'](
                m.listRelatives(thisNode, path=True, parent=True)[0]
            )

        for item in m.listHistory(_self)[1:]:
            if 'shape' in m.nodeType(item, i=True):
                return nodes['DagNode'](
                    m.listRelatives(item, path=True, parent=True)[0]
                )

        for item in m.listHistory(_self, future=True)[1:]:
            if 'shape' in m.nodeType(item, i=True):
                return nodes['DagNode'](
                    m.listRelatives(item, path=True, parent=True)[0]
                )

    @short(name='n',
           parent='p',
           intermediate='i')
    def createShape(self,
                    name:Optional[str]=None,
                    parent=None,
                    pop=False,
                    intermediate=False):
        """
        Creates a shape of the matching geometry type and sets this plug as its
        input.

        :param name/n: an optional name override; defaults to block naming
        :param parent/p: an optional destination parent; defaults to the nearest
            detect parent, unless *pop* is True, in which case a new parent is
            created; defaults to None
        :param pop: if no *parent* is specified, create a new transform at scene
            level; defaults to False
        :param intermediate/i: make it an intermediate shape; defaults to False
        :return: The shape.
        """
        if parent is None and not pop:
            parent = self.findParent()

        shape = self.getShapeClass().createNode(name=name, parent=parent)
        self >> shape.input
        if intermediate:
            shape.attr('intermediateObject').set(True)
        else:
            shape.assignDefaultShader()

        return shape

    #--------------------------------------|    Deformations

    def __mul__(self, other):
        """
        Multiplies this geometry stream with a matrix.
        """
        node = nodes['TransformGeometry'].createNode()
        self >> node.attr('inputGeometry')
        other >> node.attr('transform')
        return node.attr('outputGeometry')