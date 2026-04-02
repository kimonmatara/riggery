import re
from typing import Union, Optional, Iterator

import maya.api.OpenMaya as om
import maya.cmds as m

from ..lib import names as _nm
from riggery.general.functions import short, resolve_flags
from riggery.core.elem import Elem
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data
from riggery.internal.nodeinfo import UNCAPMAP
from riggery.general.strings import uncap

uncap = lambda x: x[0].lower()+x[1:]


Attribute = plugs['Attribute']

class GeometryMeta(type(Attribute)):

    def __new__(meta, clsname, bases, dct):
        dct.setdefault('__shape_class_name__', clsname)
        return super().__new__(meta, clsname, bases, dct)


class Geometry(Attribute, metaclass=GeometryMeta):

    __shape_class_name__ = 'GeometryShape'
    __data_mfn_type__:om.MFnBase = None

    #--------------------------------------|    Data sampling

    def _getSamplingPlug(self) -> om.MPlug:
        plug = self.__apimplug__()

        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        return plug

    def _getData(self) -> om.MObject:
        plug = self._getSamplingPlug()
        handle = plug.asMDataHandle()
        out = handle.data()
        plug.destructHandle(handle)
        return out

    def geoType(self, apiType:bool=False) -> Optional[str]:
        """
        :param apiType: return the raw API type string
        :return: the geometry type, detected from the plug data
        """
        out = self._getData().apiTypeStr

        if apiType:
            return out

        out = uncap(out[1:])
        mt = re.match(r"^(.*)Data$", out)

        if mt:
            out =  mt.group(1)

        if out != 'invalid':
            return out

    #--------------------------------------|    Inspections (geometryAttrInfo)

    def getPoints(self) -> list['data.Point']:
        """:return: A list of points for the geometry."""
        return [data['Point'](x) for x in m.geometryAttrInfo(str(self),
                                                             points=True)]

    def getMatrix(self) -> 'data.Matrix':
        """
        :return: The matrix associated with this geometry.
        """
        return data['Matrix'](m.geometryAttrInfo(str(self), matrix=True))

    def getPointIndices(self) -> list[int]:
        """:return: The indices of the geometry."""
        return m.geometryAttrInfo(str(self), pointIndices=True)

    def getPointCount(self) -> int:
        """:return: The point count of the geometry."""
        return m.geometryAttrInfo(str(self), pointCount=True)

    def getElementCount(self) -> int:
        """:return: The element count of the components."""
        return m.geometryAttrInfo(str(self), elementCount=True)

    def getComponentTagNames(self) -> list[str]:
        """
        :return: The names of the component tags being carried by this geometry
            stream.
        """
        return m.geometryAttrInfo(str(self), componentTagNames=True)

    def getBoundingBox(self) -> 'data.BoundingBox':
        """
        Static query. Returns the bounding box of the geometry.
        """
        result = m.geometryAttrInfo(str(self), boundingBox=True)
        return data['BoundingBox'](result)

    @short(castToEdges='cte',
           castToFaces='ctf',
           castToVerts='ctv')
    def evalComponentTagExpression(self,
                                   componentTagExpression:str,
                                   castToEdges:bool=False,
                                   castToFaces:bool=False,
                                   castToVerts:bool=False) -> list[str]:
        """
        Evaluates the given component tag expression (as would be entered into
        deformers, e.g. 'left_vertices', '*' etc.) and returns the components
        being referenced in their short form, e.g. ``['f[5]']``.

        :param castToEdges/cte: convert to edges; defaults to False
        :param castToFaces/ctf: convert to faces; defaults to False
        :param castToVerts/ctv: convert to vertices; defaults to False
        """
        kwargs = {}

        if castToEdges:
            kwargs['castToEdges'] = True
        elif castToFaces:
            kwargs['castToFaces'] = True
        elif castToVerts:
            kwargs['castToVerts'] = True

        return m.geometryAttrInfo(str(self),
                                  componentTagExpression=componentTagExpression,
                                  components=True,
                                  **kwargs)

    def iterDeformerChain(self) -> Iterator['nodes.GeometryFilter']:
        """
        Yields deformers through which the geometry in this plug has travelled.
        """
        out = m.geometryAttrInfo(str(self), deformerChain=True)
        if out:
            for deformer in out:
                yield nodes['DependNode'](deformer)

    def getDeformerChain(self) -> list['nodes.GeometryFilter']:
        """
        List version of :meth:`iterDeformerChain`.
        """
        return list(self.iterDeformerChain())

    def iterNodeChain(self) -> Iterator['nodes.DependNode']:
        """
        Yields nodes through which the geometry in this plug has travelled.
        """
        out = m.geometryAttrInfo(str(self), nodeChain=True)

        if out:
            for node in out:
                yield nodes['DependNode'](node)
                    
    def getNodeChain(self) -> list['nodes.GeometryFilter']:
        """
        List version of :meth:`iterNodeChain`.
        """
        return list(self.iterNodeChain())

    @short(outputsOnly='oo')
    def iterPlugChain(self, outputsOnly:bool=False) -> Iterator['Geometry']:
        """
        Yields plugs through which the geometry in this plug has travelled.

        :param outputsOnly/oo: only include output plugs (the default is both
            input and output plugs); defaults to False
        """
        if outputsOnly:
            k = 'outputPlugChain'
        else:
            k = 'plugChain'

        kwargs = {k: True}

        out = m.geometryAttrInfo(str(self), **kwargs)

        for x in out:
            yield plugs[x]

    @short(outputsOnly='oo')
    def getPlugChain(self, outputsOnly:bool=False) -> list['Geometry']:
        """
        List version of :meth:`iterPlugChain`.
        """
        return list(self.iterPlugChain(oo=outputsOnly))

    #--------------------------------------|    Shape interops

    @classmethod
    def conformToOutput(cls, geo):
        """
        Utility node. Conforms *geo* to a geometry output plug.

        :param geo: a transform, shape node or plug for a deformable shape
        :return: A local-space output plug or, if *geo* was a plug to begin
            with, the original plug.
        """
        geo = Elem(geo)

        if isinstance(geo, Geometry):
            return geo

        if isinstance(geo, nodes['DagNode']):
            if isinstance(geo, nodes['Transform']):
                shape = geo.getShape()
                if shape:
                    if isinstance(shape, nodes['DeformableShape']):
                        return shape.localOutput
            else:
                if isinstance(geo, nodes['DeformableShape']):
                    return geo.localOutput

        raise TypeError(f"Can't conform {geo} to a geometry output.")

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
           intermediate='i',
           connect='c')
    def createShape(self,
                    name:Optional[str]=None,
                    intermediate:Optional[bool]=False,
                    parent=None,
                    connect:bool=True):
        """
        Creates a shape of the matching geometry type and sets this plug as its
        input.

        :param name/n: an optional name override; defaults to block naming
        :param parent/p: an optional destination parent; if omitted, a new
            transform will be created; defaults to None
        :param intermediate/i: make it an intermediate shape; defaults to False
        :return: The shape.
        """
        shape = self.getShapeClass().createNode(name=name, parent=parent)
        self >> shape.input

        if intermediate:
            shape.attr('intermediateObject').set(True)
        else:
            shape.assignDefaultShader()

        if not connect:
            shape.localOutput.evaluate()
            self // shape.input

        return shape

    #--------------------------------------|    Deformations

    def __mul__(self, other):
        """
        Multiplies this geometry stream with a matrix.
        """
        node = nodes['TransformGeometry'].createNode()
        self >> node.attr('inputGeometry')
        other >> node.attr('transform')
        out = node.attr('outputGeometry')
        out.__class__ = type(self)
        return out