import math
from ..lib import mixedmode as _mm
import maya.api.OpenMaya as om
from riggery.general.functions import short
from ..datatypes import __pool__
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs


class Vector(__pool__['Tensor3']):

    __apicls__ = om.MVector
    __ispoint__ = False

    #-----------------------------------------|    Testing

    @short(name='n', inheritsTransform='it')
    def loc(self, name=None, *, inheritsTransform:bool=True):
        """
        :param name/n: defaults to name blocks
        :param inheritsTransform/it: sets the 'inheritsTransform' attribute on
            the locator; defaults to True
        :return: A locator (transform) with its ``translate`` set to this
            vector or point.
        """
        loc = nodes.Locator.createNode(name=name).parent
        loc.attr('it').set(inheritsTransform)
        loc.attr('t').set(self)
        return loc

    #-----------------------------------------|    Vector ops

    def guessUpVector(self):
        """
        Runs comparisons against base X, Y and Z and vectors, and returns the
        one that's most perpendicular to this vector.
        """
        _self = self.normal()
        bestDot = None
        outVector = None
        for vector in map(Vector, [(1, 0, 0), (0, 1, 0), (0, 0, 1)]):
            thisDot = abs(vector.dot(_self))
            if bestDot is None or thisDot < bestDot:
                bestDot = thisDot
                outVector = vector
        return outVector

    def mostPerpendicular(self, others):
        """
        Returns the vector output that's most perpendicular to this one. At the
        moment this doesn't support mixed-mode (values mixed with plugs).
        """
        others = list(map(Vector, others))
        dots = []
        out = None

        for i, other in enumerate(others):
            dot = abs(self.dot(other, normalize=True))
            if i == 0:
                out = other
            else:
                if dot < dots[-1]:
                    out = other
            dots.append(dot)

        return out

    def projectOnto(self, otherVector):
        """
        :return: The projection of this vector onto *otherVector*.
        """
        otherVector, _, _ = _mm.info(otherVector,
                                     (__pool__['Vector'], plugs['Vector']))
        return (self.dot(otherVector)
                / otherVector.dot(otherVector)) * otherVector

    def rejectFrom(self, other, preserveLength=False):
        """
        Makes this vector perpendicular to *otherVector*.
        See https://en.wikipedia.org/wiki/Vector_projection.
        """
        if preserveLength:
            mag = self.length()
        other, _, _ = _mm.info(other, Vector)
        cosTheta = self.dot(other, normalize=True)
        rejection = self - (self.length() * cosTheta) * other.normal()
        if preserveLength:
            rejection = rejection.normal() * mag
        return rejection

    def quatTo(self, otherVector):
        otherVector, _, isPlug = _mm.info(otherVector)
        if isPlug:
            node = nodes['AngleBetween'].createNode()
            node.attr('vector1').set(self)
            otherVector >> node.attr('vector2')
            node2 = nodes['AxisAngleToQuat'].createNode()
            node.attr('axis') >> node2.attr('inputAxis')
            node.attr('angle') >> node2.attr('inputAngle')
            return node2.attr('outputQuat')

        return __pool__['Quaternion'].fromApi(
            self.api.rotateTo(om.MVector(otherVector))
        )

    def matrixTo(self, otherVector):
        return self.quatTo(otherVector).asMatrix()

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
            return self._simpleAngleTo(otherVector)
        return self._correctedAngleTo(otherVector, normal, shortest=shortest)

    def _simpleAngleTo(self, otherVector):
        otherVector, otherVectorShape, otherVectorIsPlug \
            = _mm.info(otherVector)

        if otherVectorIsPlug:
            node = nodes.AngleBetween.createNode()
            node.attr('vector1').set(self)
            node.attr('vector2').put(otherVector, True)
            return node.attr('angle')

        return om.MVector(self).angle(om.MVector(otherVector))

    def _correctedAngleTo(self, otherVector, normal, shortest=False):
        otherVector, _, otherIsPlug = _mm.info(otherVector, Vector)
        normal, _, normalIsPlug = _mm.info(normal, Vector)

        if (otherIsPlug or normalIsPlug):
            # Get 180 angle
            node = nodes.AngleBetween.createNode()
            node.attr('vector1').set(self)
            node.attr('vector2').put(otherVector, otherIsPlug)
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

            zeroAngle = nw.addAttr('zeroAngle', at='doubleAngle',
                                   dv=0.0, lock=True, k=True)

            halfAngle = nw.addAttr('halfAngle', at='doubleAngle',
                                   dv=math.radians(180.0), lock=True, k=True)

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

            return nw.addAttr('outAngle',
                              i=outAngle,
                              k=True,
                              at='doubleAngle',
                              lock=True)

        # Use API calls for everything
        self = om.MVector(self)
        other = om.MVector(otherVector)

        normal = om.MVector(normal).normal()

        cross = self ^ other
        if cross.length() < 1e-10:
            return math.radians(180)

        # Get partial angle
        partialAngle = self.angle(other)

        # Get dot between cross and normal
        windingDot = normal * cross

        if windingDot > 0.0:
            return partialAngle

        if shortest:
            return -partialAngle

        return math.radians(360.0)-partialAngle

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
        vectorTypes = [plugs['Vector'], Vector]
        startTangent = _mm.conform(startTangent, vectorTypes)
        endTangent = _mm.conform(endTangent, vectorTypes)

        if perpendicularize:
            vector = self.rejectFrom(startTangent)
        else:
            vector = self

        matrix = startTangent.matrixTo(endTangent)

        return vector * matrix

    def length(self):
        """
        :return: The length of this vector.
        """
        return om.MVector(self[:3]).length()

    def normal(self):
        """
        :return: A normalized copy of this vector or point.
        """
        apiVec = om.MVector(self.api).normal()
        return type(self)(apiVec)

    def withLength(self, length):
        """
        :return: A copy of this vector, with the specified length.
        """
        return self.normal() * length

    def cross(self, other, normalize:bool=False):
        """
        :param other: the other vector
        :return: The cross product of *self* and *other*.
        """
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            node = nodes.VectorProduct.createNode()
            node.attr('operation').set(2)
            node.attr('input1').set(self)
            node.attr('input2').put(other, True)
            if normalize:
                node.attr('normalizeOutput').set(normalize)
            return node.attr('output')
        out = om.MVector(self) ^ om.MVector(other)
        if normalize:
            out = out.normal()
        return Vector(out)

    def dot(self, other, normalize:bool=False):
        """
        :param other: the other vector
        :param normalize: normalize inputs; you'll usually want this to be
            True, but defaults to False for parity with the API
        :return: The cross product of *self* and *other*.
        """
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            node = nodes.VectorProduct.createNode()
            node.attr('operation').set(1)
            node.attr('input1').set(self)
            node.attr('input2').put(other, True)
            if normalize:
                node.attr('normalizeOutput').set(normalize)
            return node.attr('outputX')
        else:
            a = om.MVector(self)
            b = om.MVector(other)

            if normalize:
                a = a.normal()
                b = b.normal()
            return a * b

    def rotateByAxisAngle(self, axis, angle):
        """
        :param axis: the axis vector
        :param angle: the angle (radians)
        :return: The rotated vector
        """
        axis, _, axisIsPlug = _mm.info(axis)
        angle, _, angleIsPlug = _mm.info(angle)

        if axisIsPlug or angleIsPlug:
            quat = plugs['Quaternion'].fromAxisAngle(axis, angle)
        else:
            quat = __pool__['Quaternion'].fromAxisAngle(axis, angle)

        return self * quat

    def flipIfCloserTo(self, refVector):
        """
        :param refVector: the vector to compare to
        :return: Either ``self``, or the inverse, if the inverse is more
            closely-aligned to *refVector*.
        """
        refVector = Vector(refVector).normal()
        thisDot = self.dot(refVector, True)
        inv = -self
        invDot = inv.dot(refVector, True)
        return self if thisDot > invDot else inv

    def blend(self,
              other,
              weight=0.5,
              slerp:bool=False,
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
            l2 = _mm.info(other,
                          (__pool__['Vector'], plugs['Vector']),
                          force=Tre)[0].length()
            out = out.normal() * _mm.blendScalars(l1, l2, weight)
        elif preserveLength:
            out = out.normal() * self.length()
        return out

    # @short(perpendicularize='per',
    #        shortest='sho',
    #        blendLengths='bl')
    # def blend(self,
    #           otherVector,
    #           weight=0.5, *,
    #           normal=None,
    #           shortest:bool=False,
    #           perpendularize:bool=False,
    #           blendLengths:bool=False):
    #     """
    #     Blends this vector towards *otherVector* by the specified weight. No
    #     guarding is performed; errors will be issued if either vector is zero-
    #     length.
    #
    #     :param otherVector: the vector towards which to blend
    #     :param weight: the blend weight
    #     :param normal: the clock normal; if omitted, 180-only calculations will
    #         be performed
    #     :param perpendicularize/per: if *normal* is provided, force the input
    #         vectors to be perpendicular to the normal; defaults to False
    #     :param shortest/sho: blends along the closest circle side; defaults to
    #         False
    #     :param blendLengths/bl: blend the vector lengths too; defaults to False
    #     :return: The blended vector
    #     """
    #     other, _, otherIsPlug = _mm.info(otherVector, Vector)
    #     weight, _, weightIsPlug = _mm.info(weight)
    #     hasPlugs = otherIsPlug or weightIsPlug
    #
    #     if normal is None:
    #         angle = self.angleTo(other)
    #         axis = self ^ other
    #     else:
    #         normal, _, normalIsPlug = _mm.info(normal, Vector)
    #         if perpendularize:
    #             self = self.rejectFrom(normal)
    #             other = other.rejectFrom(normal)
    #         angle = self.angleTo(other, normal, shortest=shortest)
    #
    #     angle *= weight
    #     out = self.rotateByAxisAngle(normal, angle)
    #
    #     if blendLengths:
    #         targetLength = _mm.blendScalars(self.length(),
    #                                         other.length(),
    #                                         weight)
    #         out = out.withLength(targetLength)
    #
    #     return out

    #-----------------------------------------|    Multiply

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None: # (scalar)
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').set(self)
                for dest in node.attr('input2').children:
                    dest.put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            if shape == 3: # (three scalars)
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').set(self)
                node.attr('input2').put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            if shape == 16: # (vector-matrix or point-matrix)
                if self.__ispoint__:
                    node = nodes.PointMatrixMult.createNode()
                    node.attr('inPoint').set(self)
                    other >> node.attr('inMatrix')
                else:
                    node = nodes.VectorProduct.createNode()
                    node.attr('operation').set(3)
                    node.attr('input1').set(self)
                    other >> node.attr('matrix')
                return node.attr('output')

            if shape == 4:
                matrix = other.asRotateMatrix()

                if self.__ispoint__:
                    node = nodes.PointMatrixMult.createNode()
                    node.attr('inPoint').set(self)
                    matrix >> node.attr('inMatrix')
                else:
                    node = nodes.VectorProduct.createNode()
                    node.attr('operation').set(3)
                    node.attr('input1').set(self)
                    matrix >> node.attr('matrix')
                return node.attr('output')

            return NotImplemented

        if shape == 16:
            return type(self)(self.api * om.MMatrix(other))

        if shape == 4:
            matrix = om.MQuaternion(other).asMatrix()
            return type(self)(self.api * matrix)

        return super().__mul__(other)

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                for dest in node.attr('input1').children:
                    dest.put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output')

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output')

            return NotImplemented
        return super().__rmul__(other)

    #-----------------------------------------|    Cross / point-matrix mult

    def __xor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            if isPlug:
                node = nodes.VectorProduct.createNode()
                node.attr('operation').set(2)
                node.attr('input1').set(self)
                node.attr('input2').put(other, isPlug)
                return node.attr('output')

            return self.cross(other)

        if shape == 16:
            if isPlug:
                node = nodes['PointMatrixMult'].createNode()
                node.attr('inPoint').set(self)
                node.attr('inMatrix').put(other, isPlug)
                return node.attr('output')

            return __pool__['Point'](om.MPoint(self) * om.MMatrix(other))

        return NotImplemented

    def __rxor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            if isPlug:
                node = nodes.VectorProduct.createNode()
                node.attr('operation').set(2)
                node.attr('input1').put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output')

            return type(self)(om.MVector(other) ^ om.MVector(self))

        return NotImplemented

    #-----------------------------------------|    Conversions

    def asTranslateMatrix(self):
        """
        :return: A matrix with the w (position) row set to this vector /
            point.
        """
        matrix = __pool__['Matrix']()
        matrix[12:15] = self[:3]
        return matrix