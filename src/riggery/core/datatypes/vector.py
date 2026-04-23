from typing import Literal
import math
from ..lib import mixedmode as _mm
import maya.api.OpenMaya as om
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
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

    def sum(self, *others):
        otherInfos = [_mm.info(x) for x in others]
        hasPlugs = any((x[2] for x in otherInfos))

        if hasPlugs:
            node = nodes.PlusMinusAverage.createNode()
            self >> node.attr('input3D')[0]
            for i, (other, _, isPlug) in enumerate(otherInfos, start=1):
                node.attr('input3D')[i].put(other, isPlug=isPlug)
            return node.attr('output3D')

        out = self.copy()

        for (other, _, _) in otherInfos:
            out += other

        return out

    def closestAxisLetter(self) -> Literal['x', 'y', 'z', '-x', '-y', '-z']:
        """
        :return: The closest letter-axis representation of this vector.
        """
        axes = ('x', 'y', 'z', '-x', '-y', '-z')
        vectors = (Vector((1, 0, 0)),
                   Vector((0, 1, 0)),
                   Vector((0, 0, 1)),
                   Vector((-1, 0, 0)),
                   Vector((0, -1, 0)),
                   Vector((0, 0, -1)))

        dotsmap = ((k, self.dot(v, normalize=True))
                   for k, v in zip(axes, vectors))

        return sorted(dotsmap, key=lambda pair: pair[1])[-1][0]

    def closestAxis(self, asString:bool=False, includeNegative=False):
        axes = ['x', 'y', 'z']
        vectors = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]

        if includeNegative:
            axes += ['-x', '-y', '-z']
            vectors += [v * -1 for v in vectors]

        bestDot = None
        bestAxis = None
        bestVector = None

        for axis, vector in zip(axes, vectors):
            thisDot = vector.dot(self, normalize=True)
            if bestDot is None or thisDot > bestDot:
                bestDot = thisDot
                bestAxis = axis
                bestVector = vector

        return bestAxis if asString else bestVector

    def inventPerpendicular(self) -> 'Vector':
        """
        Finds the closest letter axis matching this vector, and returns a
        perpendicularized version of the next axis in letter order.
        """
        thisAxis = self.closestAxisLetter()
        thisAbsAxis = thisAxis.strip('-')
        outAxis = 'xyz'[('xyz'.index(thisAbsAxis)+1) % 3]
        if '-' in thisAxis:
            outAxis = '-'+thisAbsAxis

        axes = ('x', 'y', 'z', '-x', '-y', '-z')
        vectors = (Vector((1, 0, 0)),
                   Vector((0, 1, 0)),
                   Vector((0, 0, 1)),
                   Vector((-1, 0, 0)),
                   Vector((0, -1, 0)),
                   Vector((0, 0, -1)))

        return dict(zip(axes, vectors))[outAxis].rejectFrom(self)

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

    rotateTo = quatTo

    def matrixTo(self, otherVector):
        return self.quatTo(otherVector).asMatrix()

    def axisAngleTo(self, otherVector) -> tuple:
        otherVector, _, otherVectorIsPlug = _mm.info(otherVector,
                                                     (plugs['Vector'], Vector))

        if otherVectorIsPlug:
            node = nodes['AngleBetween'].createNode()
            node.attr('vector1').put(self, False)
            node.attr('vector2').put(otherVector, True)
            return (node.attr('axis'), node.attr('angle'))

        thisMVector = self.api
        otherMVector = otherVector.api

        mQuat = thisMVector.rotateTo(otherMVector)
        outMVector, angle = mQuat.asAxisAngle()

        return Vector.fromApi(outMVector), angle

    def angleTo(self, otherVector, normal=None, *, shortest=False):
        """
        :param otherVector: the vector towards which to measure an angle
        :param normal: if this is provided then, if *shortest* is True, the
            angle will be in the -180 -> +180 range; otherwise, it will be
            in the 0 -> 360 range; if omitted, it will be in the 0 -> 180
            range; defaults to None
        :param shortest: ignored if *normal* is omitted
        """
        otherVector, _, otherVectorIsPlug = _mm.info(otherVector,
                                                     (plugs['Vector'], Vector))

        hasPlugs = otherVectorIsPlug

        if normal is not None:
            normal, _, normalIsPlug = _mm.info(normal,
                                               (plugs['Vector'], Vector))
            hasPlugs = hasPlugs or normalIsPlug

        if hasPlugs:
            pb = nodes['Network'].createNode()
            otherVector = pb.addVectorAttr('otherVector', i=otherVector, l=True)

            if normal is not None:
                normal = pb.addVectorAttr('normal', i=normal, l=True)

            node = nodes['AngleBetween'].createNode()
            node.attr('vector1').set(self)
            otherVector >> node.attr('vector2')

            if normal is None:
                return node.attr('angle')

            outAngle = node.attr('angle')
            outAxis = node.attr('axis')

            aligned = outAxis.length().lt(1e-6)
            dot = normal.dot(aligned.ifElse(normal,
                                            outAxis,
                                            plugs['Vector']), normalize=True)
            flipped = dot.lt(0.0)

            pb = nodes['Network'].createNode()

            outAngle = flipped.ifElse(math.radians(360)-outAngle,
                                      outAngle,
                                      plugs['Angle'])

            if shortest:
                outAngle = outAngle.gt(math.radians(180)).ifElse(
                    outAngle - math.radians(360),
                    outAngle,
                    plugs['Angle']
                )

            nw = nodes['Network'].createNode()
            zero = nw.addAttr('zeroAngle', at='doubleAngle')

            return aligned.ifElse(zero, outAngle, plugs['Angle'])

        # Soft
        if normal is None:
            return om.MVector(self).angle(om.MVector(otherVector))

        self = om.MVector(self).normal()
        other = om.MVector(otherVector).normal()

        normal = om.MVector(normal).normal()
        cross = self ^ other

        if cross.length() < 1e-10:
            if (self * other) > 0.0:
                return 0.0
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
            node = nodes['CrossProduct'].createNode()
            node.attr('input1').set(self)
            node.attr('input2').put(other, True)

            output = node.attr('output')

            if normalize:
                output = output.normal()

            return output

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
            node = nodes['DotProduct'].createNode()

            if normalize:
                self = self.normal()
                other = other.normal()

            node.attr('input1').set(self)
            node.attr('input2').put(other, True)

            return node.attr('output')

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

    def deflipSequence(self, *others) -> list:
        """
        At the moment this is a value-only implementation.

        :return: A list of [self] + others, deflipped in sequence.
        """
        others = list(map(Vector, others))
        out = [self]

        for other in others:
            other = other.flipIfCloserTo(out[-1])
            out.append(other)
        return out

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
                op = nodes['Multiply{}ByMatrix'.format(
                    'Point' if self.__ispoint__ else 'Vector'
                )].createNode()

                op.attr('input').set(self)
                op.attr('matrix').connectInput(other)

                return op.attr('output').asType(plugs['Point']
                                                if self.__ispoint__
                                                else plugs['Vector'])

            if shape == 4:
                matrix = other.asRotateMatrix()

                op = nodes['Multiply{}ByMatrix'.format(
                    'Point' if self.__ispoint__ else 'Vector'
                )].createNode()

                op.attr('input').set(self)
                op.attr('matrix').connectInput(matrix)

                return op.attr('output').asType(plugs['Point']
                                                if self.__ispoint__
                                                else plugs['Vector'])

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
                return node.attr('output').asType(self.plugClass())

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').put(other, isPlug)
                node.attr('input2').set(self)

                return node.attr('output').asType(self.plugClass())

            return NotImplemented
        return super().__rmul__(other)

    #-----------------------------------------|    Cross / point-matrix mult

    def __xor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            if isPlug:
                node = nodes['CrossProduct'].createNode()
                node.attr('input1').set(self)
                node.attr('input2').connectInput(other)

                return node.attr('output')

            return self.cross(other)

        if shape == 16:
            if isPlug:
                node = nodes['MultiplyPointByMatrix'].createNode()
                node.attr('input').set(self)
                node.attr('matrix').connectInput(other)
                return node.attr('output').asPoint()

            return __pool__['Point'](om.MPoint(self) * om.MMatrix(other))

        return NotImplemented

    def __rxor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            if isPlug:
                node = nodes['CrossProduct'].createNode()
                node.attr('input1').connectInput(other)
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

    def asScaleMatrix(self):
        """
        :return: A matrix where the axis vectors have the magnitudes of this
            vector's elements.
        """
        out = __pool__['Matrix']()
        out.x *= self[0]
        out.y *= self[1]
        out.z *= self[2]

        return out

    def asPoint(self):
        return __pool__['Vector'](self)