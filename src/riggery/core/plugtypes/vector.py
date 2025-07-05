from typing import Union, Optional
import math

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes
from ..lib import mixedmode as _mm
from ..lib import names as _nm


class Vector(plugs['Tensor3Float']):

    __datacls__ = data['Vector']

    #-----------------------------------------|    Constructors

    @classmethod
    def createAxisVectors(cls, node, attrName, includeNegative:bool=False):
        """
        Creates a multi attribute where each element is a basis axis vector,
        i.e. (1, 0, 0), (0, 1, 0) and so on.

        :param node: the node on which to add the attribute
        :param attrName: the name of the attribute to add
        :param includeNegative: include negative axis vectors
        :return: The attribute
        """
        node = nodes['DependNode'](node)
        attr = node.addVectorAttr(attrName, multi=True, k=True)

        vectors = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]

        if includeNegative:
            vectors += [(-1, 0, 0), (0, -1, 0), (0, 0, -1)]

        for i, vector in enumerate(vectors):
            attr[i].set(vector)
            attr[i].lock(recurse=True)

        return attr

    #-----------------------------------------|    Testing

    @short(name='n', inheritsTransform='it')
    def loc(self, name:Optional[str]=None, *, inheritsTransform:bool=True):
        """
        :param name/n: if omitted, defaults to name blocks
        :param inheritsTransform/it: sets ``inheritsTransform`` on the
            locator; defaults to False
        :return: A locator at this vector / point's position.
        """
        loc = nodes.Locator.createNode(name=name).parent
        self >> loc.attr('t')
        inheritsTransform >> loc.attr('it')
        return loc

    #-----------------------------------------|    Vector ops

    def blend(self,
              other,
              weight=0.5,
              slerp:bool=False, *,
              preserveLength:bool=False,
              blendLength:bool=False):
        """
        Blends this vector towards *other*.

        :param other: the vector towards which to blend
        :param weight: the blending weight towards *other*
        :param slerp: perform quaternion-based slerping; defaults to False
        :param blendLength: blend the vector lengths as well; defaults to False
        :param preserveLength: preserve this vector's length; defaults to False
        :return:
        """
        if slerp:
            quat = self.quatTo(other)
            quat = quat * weight
            out = self * quat
        else:
            out = super().blend(other, weight)

        if blendLength:
            l1 = self.length()
            l2 = _mm.info(other, data['Vector'])[0].length()
            out = out.normal() * l1.blend(l2, weight)
        elif preserveLength:
            out = out.normal() * self.length()

        return out

    def projectOnto(self, otherVector):
        """
        :return: The projection of this vector onto *otherVector*.
        """
        otherVector, _, _ = _mm.info(otherVector, data['Vector'])
        return (self.dot(otherVector)
                / otherVector.dot(otherVector)) * otherVector

    def quatTo(self, otherVector):
        """
        The quaternion to rotate this vector to *otherVector*.
        """
        node = nodes['AngleBetween'].createNode()
        self >> node.attr('vector1')
        otherVector >> node.attr('vector2')
        node2 = nodes['AxisAngleToQuat'].createNode()
        node.attr('axis') >> node2.attr('inputAxis')
        node.attr('angle') >> node2.attr('inputAngle')
        return node2.attr('outputQuat')

    def matrixTo(self, otherVector):
        return self.quatTo(otherVector).asRotateMatrix()

    def angleTo(self, otherVector, normal=None, *, shortest=False):
        """
        :param otherVector: the vector towards which to measure an angle
        :param normal: if this is provided then, if *shortest* is True, the
            angle will be in the -180 -> +180 range; otherwise, it will be
            in the 0 -> 360 range; if omitted, it will be in the 0 -> 180
            range; defaults to None
        :param shortest: ignored if *normal* is omitted
        """
        if normal is None:
            node = nodes.AngleBetween.createNode()
            self >> node.attr('vector1')
            otherVector >> node.attr('vector2')
            return node.attr('angle')
        return self._correctedAngle(otherVector,
                                    normal,
                                    shortest=shortest).asType(plugs['Angle'])

    def _correctedAngle(self, otherVector, normal, shortest:bool=False):
        otherVector, otherVectorShape, otherVectorIsPlug = \
            _mm.info(otherVector, data['Vector'])

        normal, normalShape, normalIsPlug = _mm.info(normal, data['Vector'])

        # Get 180 angle
        node = nodes.AngleBetween.createNode()
        self >> node.attr('vector1')
        otherVector >> node.attr('vector2')
        partialAngle = node.attr('angle')

        # Get cross of this vector and other, detect if zero length
        crossThisOther = self.cross(otherVector)
        crossThisOtherLength = crossThisOther.length()
        crossThisOtherIsZero = crossThisOtherLength.lt(1e-6)

        # If the dot of this and other is 1.0, return 0.0. Otherwise,
        # if the dot is -1.0, return 180.0. Otherwise:
        # Get the (safe) dot of the cross and normal. If it's above 0.0,
        # return the partial angle. Otherwise, return unwound angle.

        dotThisOther = self.dot(otherVector, normalize=True)
        dotThisOtherIsOne = dotThisOther.ge(1.0-1e-7)
        dotThisOtherIsMinusOne = dotThisOther.le(-1.0+1e-7)

        operand = crossThisOtherIsZero.ifElse(normal,
                                              crossThisOther,
                                              plugs.Vector)
        dotCrossNormal = normal.dot(operand, normalize=True)
        doCorrectAngle = dotCrossNormal.lt(0.0)

        if shortest:
            correctedAngle = -partialAngle
        else:
            correctedAngle = math.radians(360.0)-partialAngle

        nw = nodes.Network.createNode()

        zeroAngle = nw.addAttr('zeroAngle',
                               at='doubleAngle',
                               dv=0.0,
                               lock=True,
                               k=True)

        halfAngle = nw.addAttr(
            'halfAngle',
            at='doubleAngle',
            dv=om.MAngle(180, unit=om.MAngle.kDegrees
                         ).asUnits(om.MAngle.uiUnit()),
            lock=True,
            k=True)

        outAngle = dotThisOtherIsOne.ifElse(
            zeroAngle,
            dotThisOtherIsMinusOne.ifElse(
                halfAngle,
                doCorrectAngle.ifElse(
                    correctedAngle,
                    partialAngle
                )
            )
        )

        return outAngle.asType(plugs['Angle'])

    @cache_dg_output
    def length(self):
        """
        :return: The length of this vector.
        """
        node = nodes.DistanceBetween.createNode()
        self >> node.attr('point2')
        return node.attr('distance')

    def withLength(self, length):
        """
        Returns a copy of this normal with its length set to *length*.

        :param length: the target length
        :param guard: creates a more complex network to guard against
            ``basicExpression`` errors in cases where the magnitude of this
            vector dips to 0.0; defaults to False
        :return:
        """
        return self.normal() * length

    def normal(self, quiet:bool=False):
        """
        :param quiet: create a more involved network to avoid zero-length
            errors; defaults to False
        :return: A normalized version of this vector.
        """
        if quiet:
            return self._quietNormal()
        return self._rawNormal()

    @cache_dg_output
    def _rawNormal(self):
        node = nodes['Normalize'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def _quietNormal(self):
        mag = self.length()
        isZero = mag.eq(0.0)
        patchbay = nodes.Network.createNode()
        fallbackMag = patchbay.addAttr('magnitudeOne',
                                       at='double',
                                       dv=1.0).lock()
        fallbackVec = patchbay.addVectorAttr('zeroVector',
                                             k=True).lock()
        mag = isZero.ifElse(fallbackMag, mag, type(mag))
        out = isZero.ifElse(fallbackVec, self / mag)
        return out

    def cross(self, other, normalize:bool=False):
        """
        :param other: the other vector
        :param normalize: normalize the output vector; defaults to False
        :return: The cross product of *self* and *other*.
        """
        node = nodes.VectorProduct.createNode()
        self >> node.attr('input1')
        other >> node.attr('input2')
        node.attr('operation').set(2)
        if normalize:
            node.attr('normalizeOutput').set(True)
        return node.attr('output')

    def dot(self, other, normalize:bool=False):
        """
        :param other: the other vector
        :param normalize: normalize inputs; you'll usually want this to be
            True, but defaults to False for parity with the API
        :return: The cross product of *self* and *other*.
        """
        node = nodes.VectorProduct.createNode()
        node.attr('operation').set(1)
        self >> node.attr('input1')
        other >> node.attr('input2')
        if normalize:
            node.attr('normalizeOutput').set(True)
        return node.attr('outputX')

    def rotateByAxisAngle(self, axisVector, angle):
        """
        Rotates this vector by the specified axis and angle.

        Maya must be set to native units for this method.
        """
        node = nodes['AxisAngleToQuat'].createNode()
        axisVector >> node.attr('inputAxis')
        angle >> node.attr('inputAngle')
        return self * node.attr('outputQuat').asMatrix()

    def rejectFrom(self, other):
        """
        Makes this vector perpendicular to *otherVector*.
        See https://en.wikipedia.org/wiki/Vector_projection.
        """
        other, _, _ = _mm.info(other, data['Vector'])
        cosTheta = self.dot(other, normalize=True)
        rejection = self - (self.length() * cosTheta) * other.normal()
        return rejection

    def mostPerpendicular(self, others):
        """
        Graph router. Returns the vector output that's most perpendicular to
        this one.
        """
        others = [_mm.info(other)[0] for other in others]

        lastDot = None
        lastOutput = None

        for other in others:
            thisDot = self.dot(other, normalize=True).abs()
            if lastDot is None:
                lastDot = thisDot
                lastOutput = other
            else:
                isBetter = thisDot.lt(lastDot)
                lastDot = isBetter.ifElse(thisDot, lastDot)
                lastOutput = isBetter.ifElse(other, lastOutput)

        return lastOutput.asType(Vector)

    @cache_dg_output
    def guessUpVector(self):
        """
        Runs comparisons against base X, Y and Z and vectors, and returns the
        one that's most perpendicular to this vector.
        """
        choice = nodes['Choice'].createNode()
        _choice = str(choice)
        m.addAttr(_choice, ln='baseVector', at='double3', nc=3, multi=True)
        for axis in 'XYZ':
            m.addAttr(_choice,
                      ln=f'baseVector{axis}',
                      at='double',
                      parent='baseVector')
        multiAttr = choice.attr('baseVector')
        for i, value in enumerate([(1, 0, 0), (0, 1, 0), (0, 0, 1)]):
            multiAttr[i].set(value)
        baseVectors = [multiAttr[i] for i in range(3)]
        return self.mostPerpendicular(baseVectors)

    #-----------------------------------------|    Operators

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other, data['Quaternion'])

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            self >> node.attr('input1')
            for child in node.attr('input2').children:
                child.put(other, isPlug)
            return node.attr('output')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            self >> node.attr('input1')
            node.attr('input2').put(other, isPlug)
            return node.attr('output')

        if shape == 16:
            node = nodes.VectorProduct.createNode()
            node.attr('operation').set(3)
            self >> node.attr('input1')
            node.attr('matrix').put(other, isPlug)
            return node.attr('output')

        if shape == 4: # vector * quaternion
            return self * other.asRotateMatrix()

        return NotImplemented

    #-----------------------------------------|    Point-matrix mult, or cross

    def __xor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3: # cross product
            node = nodes.VectorProduct.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input1')
            node.attr('input2').put(other, isPlug)
            return node.attr('output')

        if shape == 16: # point-matrix mult
            node = nodes.PointMatrixMult.createNode()
            self >> node.attr('inPoint')
            node.attr('inMatrix').put(other, isPlug)
            return node.attr('output')

        return NotImplemented

    def __rxor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3: # cross product
            node = nodes.VectorProduct.createNode()
            node.attr('operation').set(2)
            node.attr('input1').put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output')

        return NotImplemented

    #-----------------------------------------|    Parallel transport

    @short(perpendicularize='per')
    def transport(self, startTangent, endTangent, perpendicularize:bool=True):
        """
        Performs single-step parallel transport.

        :param startTangent: the starting tangent
        :param endTangent: the tangent onto which to transport the vector
        :param perpendicularize/per: pass False only if you know that this
            vector is already perpendicular to *startTangent*; defaults to True
        :return: This vector, transported onto *endTangent*.
        """
        vectorTypes = [Vector, data['Vector']]
        startTangent = _mm.conform(startTangent, vectorTypes)
        endTangent = _mm.conform(endTangent, vectorTypes)

        if perpendicularize:
            vector = self.rejectFrom(startTangent)
        else:
            vector = self

        matrix = startTangent.matrixTo(endTangent)

        return vector * matrix

    #-----------------------------------------|    Conversions

    @cache_dg_output
    def asTranslateMatrix(self):
        """
        :return: A matrix with the w (position) row set to this vector.
        """
        node = nodes['FourByFourMatrix'].createNode()
        self >> node.w
        return node.attr('output')

    @cache_dg_output
    def asScaleMatrix(self):
        """
        :return: A matrix with the base axis magnitudes set to the components of
            this vector.
        """
        node = nodes['FourByFourMatrix'].createNode()
        for child, field in zip(
                self.children,
                ('in00', 'in11', 'in22')
        ):
            child >> node.attr(field)
        return node.attr('output')

    #-----------------------------------------|    Effects

    def coneFalloff(self, maxAngle:float, spreadFactor=1.0, power:int=2):
        """
        The current vector state will be captured, therefore this is best
        calculated in local space and then transformed as needed.

        A neat trick is to calculate within deformed space, for ellipsoid cones.

        :param maxAngle: the clamping angle (in radians)
        :param spreadFactor: higher values will make the slowdown slower; lower
            values will make the slowdown faster; experiment in the range of
            0.5 -> 1.5 at first; defaults to 1.0
        :param power: the easing power; must be one of 2, 3 or 4; higher powers
            work better with higher spread factors; defaults to 2
        :return: The constrained vector.
        """
        initPose = self()

        ab = nodes['AngleBetween'].createNode()
        ab.attr('vector1').set(initPose)
        self >> ab.attr('vector2')

        liveAngle = ab.attr('angle')
        axis = ab.attr('axis')

        targetAngle = liveAngle.slowDownAndStop(maxAngle, spreadFactor, power)
        outVector = initPose.rotateByAxisAngle(axis, targetAngle)

        return outVector