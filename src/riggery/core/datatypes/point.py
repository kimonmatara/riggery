import maya.api.OpenMaya as om

from riggery.general.functions import short
from ..datatypes import __pool__
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..lib import mixedmode as _mm

Vector = __pool__['Vector']

class Point(Vector):

    __apicls__ = om.MPoint
    __ispoint__ = True


    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').set(self)
                for dest in node.attr('input2').children:
                    other >> dest
                    dest.put(other, True)
                return node.attr('output')

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').set(self)
                node.attr('input2').put(other, True)
                return node.attr('output')

            if shape == 16:
                node = nodes.PointMatrixMult.createNode()
                node.attr('inPoint').set(self)
                node.attr('inMatrix').put(other, True)
                return node.attr('output')

            if shape == 4:
                matrix = other.asMatrix()
                node = nodes.PointMatrixMult.createNode()
                node.attr('inPoint').set(self)
                node.attr('inMatrix').put(matrix, True)
                return node.attr('output')

        if shape == 16:
            return Point(self.api * om.MMatrix(other))

        if shape == 4:
            other = om.MQuaternion(other).asMatrix()
            return Point(self.api * other)

        return super().__mul__(other)

    #--------------|    This is here just to ensure point-point = vector

    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape == 3:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('operation').set(2)
                node.attr('input3D')[0].set(self)
                node.attr('input3D')[1].put(other, True)
                return node.attr('output3D').asType(Vector.plugClass())
            return NotImplemented
        return Vector(super().__sub__(other))

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 3:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('operation').set(2)
                node.attr('input3D')[0].put(other, True)
                node.attr('input3D')[1].set(self)
                return node.attr('output3D').asType(Vector.plugClass())
            return NotImplemented
        return Vector(super().__rsub__(other))

    #-----------------------------------------|    Conversions

    def asMatrix(self):
        """
        :return: A matrix with the w (position) row set to this point.
        """
        return self.asTranslateMatrix()

    #-----------------------------------------|    Comparisons

    @short(tolerance='tol')
    def isEquivalent(self, other, tolerance:float=1e-10) -> bool:
        """
        :param other: the point to compare to
        :param tolerance/tol: the matching tolerance; defaults to 1e-10
        """
        return self.api.isEquivalent(om.MPoint(other), tolerance=tolerance)

    #-----------------------------------------|    Blending

    def blend(self, other, weight:float=0.5):
        """
        Blends this point towards *other*. When *weight* is at 1.0, *other*
        will have fully taken over.

        :param other: the point towards which to blend
        :param weight: the blending weight; defaults to 0.5
        :return: The blended point.
        """
        other, _, otherIsPlug = _mm.info(other, Point)
        weight, _, weightIsPlug = _mm.info(weight)
        hasPlugs = otherIsPlug or weightIsPlug

        if hasPlugs:
            node = nodes['BlendColors'].createNode()
            node.attr('color2').set(self)
            other >> node.attr('color1')
            weight >> node.attr('blender')
            return node.attr('output').asType(
                type(other) if otherIsPlug else plugs['Point']
            )

        return type(self)([a + ((b-a) * weight) for a, b in zip(self, other)])