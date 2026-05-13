import itertools as _itr
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

    def woundMiddle(self, other, normal):
        """
        Constructs a 360-range middle vector between *self* and *other*. The
        output vector will be normalized. Good for things like elbows.

        :param other: the other vector
        :param normal: the winding clock normal
        :return: The middle vector.
        """

        #---------------------------------|    Prep inputs

        other = _mm.conform(other,
                            (data['Vector'], plugs['Vector']),
                            force=True)

        normal = _mm.conform(normal,
                             (data['Vector'], plugs['Vector']),
                             force=True)

        normal = normal.normal()

        self = self.rejectFrom(normal).normal()
        other = other.rejectFrom(normal).normal()

        #---------------------------------|    Get alignment info

        dot = self.dot(other)
        dotIsNegative = dot < 0
        absDot = dotIsNegative.ifElse(-dot, dot, plugs['Float'])
        tolerance = 1e-6
        absAligned = absDot > (1.0 - tolerance)
        backAligned = absAligned & dotIsNegative

        #---------------------------------|    Check if wind is flipped

        safeSecondTerm = absAligned.ifElse(normal, other)
        cross = self.cross(safeSecondTerm, normalize=True)
        flippedWind = cross.dot(normal) < 0.0

        #---------------------------------|    Cook alternative solutions

        basicSolution = self + other
        flippedSolution = -basicSolution
        backAlignedSolution = normal.cross(self)

        #---------------------------------|    Resolve

        return backAligned.ifElse(
            backAlignedSolution,
            flippedWind.ifElse(flippedSolution,
                               basicSolution),
            plugs['Vector']
        ).normal()

    def blend(self,
              other,
              weight=0.5,
              slerp:bool=False, *,
              preserveLength:bool=False):
        """
        Blends this vector towards *other*.

        :param other: the vector towards which to blend
        :param weight: the blending weight towards *other*
        :param slerp: perform quaternion-based slerping; defaults to False
        :param preserveLength: preserve this vector's length; defaults to False
        :return:
        """
        if slerp:
            quat = self.quatTo(other)
            quat = quat * weight
            out = self * quat
        else:
            out = super().blend(other, weight)

        if preserveLength:
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

    rotateTo = quatTo

    def matrixTo(self, otherVector):
        return self.quatTo(otherVector).asRotateMatrix()

    def axisAngleTo(self, other) -> tuple['plugs.Vector', 'plugs.Angle']:
        """
        :return: The axis and angle to *other*, both as plugs. Note that these
            are pulled from an ``angleBetween`` node, and the ``.axis`` output
            should *not* be treated as sized cross product, because in collapsed
            cases it becomes frame-dependent and may yield unintended results.
        """
        node = nodes['AngleBetween'].createNode()
        self >> node.attr('vector1')
        other >> node.attr('vector2')

        return node.attr('axis'), node.attr('angle')

    def angleTo(self,
                other:_mm.MixedVector,
                normal:Optional[_mm.MixedVector]=None, *,
                shortest:bool=False):

        other, otherIsPlug = _mm.asVector(other)

        angle = self.axisAngleTo(other)[1]

        if normal is not None:
            normal, normalIsPlug = _mm.asVector(normal)

            selfN = self.normal()
            otherN = other.normal()

            # Get the rotation axis
            cross = selfN.cross(otherN)
            crossLen = cross.length()
            noRotation = crossLen < 1e-5

            # Normalize it carefully
            pb = nodes['Network'].createNode()
            one = pb.addAttr('one', at='double', k=1, dv=1.0).lock()
            divisor = noRotation.ifElse(one, crossLen, plugs['Float'])
            crossN = cross / divisor

            # pull a norm dot product against the normal
            normalN = normal.normal()
            dot = crossN.dot(normalN)

            dot >> pb.addAttr('dot', k=1)

            if shortest:
                angle = dot.isNegative().ifElse(-angle, angle, plugs['Angle'])
            else:
                # Calc full angle
                angle = dot.isNegative().ifElse(math.radians(360) - angle,
                                                angle,
                                                plugs['Angle'])

        return angle

    @cache_dg_output
    def length(self):
        """
        :return: The length of this vector.
        """
        node = nodes['Length'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    def withLength(self, length):
        """
        Returns a copy of this normal with its length set to *length*.

        :param length: the target length
        :param guard: creates a more complex network to guard against
            ``basicExpression`` errors in cases where the magnitude of this
            vector dips to 0.0; defaults to False
        :return:
        """
        return (self.normal() * length).asType(type(self))

    def normal(self, quiet:bool=False) -> 'plugs.Vector':
        """
        :param quiet: if True, delegates to :meth:`normalOrZero`; defaults to
            False
        :return: A normalized (or zero-length, if *quiet* is True) version of
            this vector.
        """
        if quiet:
            return self.normalOrZero()

        return self._rawNormal()

    def normalOrZero(self, *,
                     epsilon:float=1e-5) -> tuple['plugs.Vector', 'plugs.Bool']:
        """
        Calculates a normalized or zero-length (if the input is zero-length)
        vector without spitting out DG errors if the vector is zero-length.

        :return: normal or zero-length, boolean output for isZeroLength
        """
        length = self.length()
        collapsed = length < epsilon

        node = nodes['MultiplyDivide'].createNode()
        node.attr('operation').set(2)
        one = node.addAttr('one', at='double', dv=1.0).lock()

        divisor = collapsed.ifElse(one, length)

        self >> node.attr('input1')
        node.attr('input1').splitInput()

        for dest in node.attr('input2').children:
            divisor >> dest

        return node.attr('output'), collapsed

    @cache_dg_output
    def _rawNormal(self):
        node = nodes['Normalize'].createNode()
        self >> node.attr('input')
        return node.attr('output').asType(type(self))

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
        out = isZero.ifElse(fallbackVec, self / mag, type(self))

        return out.asType(type(self))

    def cross(self, other, normalize:bool=False):
        """
        :param other: the other vector
        :param normalize: normalize the output vector; defaults to False
        :return: The cross product of *self* and *other*.
        """
        node = nodes['CrossProduct'].createNode()
        node.attr('input1').connectInput(self)
        other >> node.attr('input2')
        output = node.attr('output')

        if normalize:
            output = output.normal()

        return output

    def dot(self, other, normalize:bool=False):
        """
        :param other: the other vector
        :param normalize: normalize inputs; you'll usually want this to be
            True, but defaults to False for parity with the API
        :return: The cross product of *self* and *other*.
        """
        if normalize:
            self = self.normal()
            other = _mm.asVector(other)[0].normal()

        node = nodes['DotProduct'].createNode()
        node.attr('input1').connectInput(self)
        other >> node.attr('input2')

        return node.attr('output')

    def reciprocal(self,
                   other:_mm.MixedVector,
                   dot:Optional[_mm.MixedScalar]=None):
        """
        Equivalent to 1.0 / self.normal().dot(other.normal()).

        Used for mitering solutions. If you treat this (self) as a 'reference'
        axis, and *other* as an axis that rotates against *self*, the reciprocal
        is the stretch factor required to miter *other* (i.e. stretch it to fill
        a corner).

        This will approach infinity / conk out loudly as the two vectors become
        perpendicular.

        :param dot: if you already have the dot product, provide it here to
            avoid extraneous calculations; note that the dot product must be
            in the -1 to 1 range (normalized inputs); providing it here also
            gives you a chance to clamp it to avoid pure 0.0 (which lead to
            inifinity / NaN outputs)
        """
        other, otherIsPlug = _mm.asVector(other)

        if dot is None:
            dot = self.normal().dot(other.normal())
        else:
            dot, dotIsPlug = _mm.asScalar(dot)

        return 1.0 / dot

    def miter(self,
              vectorToSkew:_mm.MixedVector,
              fallbackHingeVector:_mm.MixedVector,
              epsilon:float=1e-4) -> tuple['plugs.Vector', 'plugs.Number']:
        """
        With ``self`` as a reference axial vector, and ``vectorToSkew`` as a
        vector that starts parallel to it but rotates away from it, returns the
        vector along which *vectorToSkew* should be stretched to fill a miter
        corner, and the magnitude. The vector will always be perpendicular to
        *self*.

        :param vectorToSkew: the tilted section vector
        :param fallbackHingeVector: a vector perpendicular to *self*; this will
            be used to guard against the degenerate (aligned) case
        """
        vectorToSkew, _ = _mm.asVector(vectorToSkew)
        fallbackHingeVector, _ = _mm.asVector(fallbackHingeVector)

        hingeVector, hingeAngle = vectorToSkew.axisAngleTo(self)
        dot = hingeAngle.cos()
        aligned = dot.abs() > 1.0 - epsilon

        hingeVector = aligned.ifElse(fallbackHingeVector,
                                     hingeVector,
                                     plugs['Vector'])

        stretchDirection = hingeVector.cross(self).normal()
        stretchAmount = self.reciprocal(vectorToSkew, dot)

        return stretchDirection, stretchAmount

    # def miterMatrix(self,
    #                 vectorToSkew:_mm.MixedVector,
    #                 fallbackHingeVector:_mm.MixedVector,
    #                 epsilon:float=1e-4):
    #     """
    #     With ``self`` as a reference axial vector, and ``vectorToSkew`` as a
    #     vector that starts parallel to it but rotates away from it, returns a
    #     matrix that can be used to stretch *vectorToSkew* to fill a miter
    #     corner.
    #
    #     If applying to a *matrix* instead, premultiply it with that matrix
    #     (i.e miterMatrix * otherMatrix).
    #     """
    #     direction, amount = self.miter(vectorToSkew,
    #                                    fallbackHingeVector,
    #                                    epsilon)
    #
    #     dOuterD = direction.outer(direction)
    #
    #     return (data['Matrix']()
    #             + (dOuterD * (amount - 1))).makeAffine()

    def outer(self, other:_mm.MixedVector) -> 'plugs.Matrix':
        """
        Computes the outer product (a.k.a. tensor product) of two vectors,
        yielding a 4x4 matrix.

        Unlike the dot product which collapses two vectors to a scalar, the
        outer product expands them into a matrix. Transforming any vector V
        by the result measures how much of *self* is in V, then scales *other*
        by that amount.
        """
        other, otherIsPlug = _mm.asVector(other)

        ff = nodes['FourByFourMatrix'].createNode()

        for ax in 'xyz':
            thisChild = getattr(self, ax)
            destCompound = getattr(ff, ax)

            for aax, destPlug in zip('xyz', destCompound.children):
                otherChild = getattr(other, aax)
                (thisChild * otherChild) >> destPlug

        return ff.attr('output')

    def rotateByAxisAngle(self, axisVector, angle):
        """
        Rotates this vector by the specified axis and angle.

        Maya must be set to native units for this method.
        """
        node = nodes['AxisAngleToQuat'].createNode()
        axisVector >> node.attr('inputAxis')
        angle >> node.attr('inputAngle')
        return (self * node.attr('outputQuat').asMatrix()).asType(type(self))

    def _rejectFrom(self, other:Union['data.Vector', 'plugs.Vector']):
        """Internal. Non-caching implementation of :meth:`rejectFrom`."""

        cosTheta = self.dot(other, normalize=True)
        return self - (self.length() * cosTheta) * other.normal()

    def _retrieveRejectFrom(self,
                            other:Union['data.Vector', 'plugs.Vector']
                            ) -> Optional['Vector']:
        """
        Internal. Looks for a cached calculation of :meth:`rejectFrom` and
        returns it.
        """
        for output in self.iterOutputs(plugs=True, type='network'):
            if output.attrName() == 'rejectFrom_caller':
                try:
                    nw = output.node()
                    _other, _ = nw.attr('otherVector').getInputOrValue()

                    if _other == other:
                        result = next(
                            nw.attr('outVectorRejection').iterInputs(plugs=True),
                            None
                        )
                        if result is not None:
                            return result
                except AttributeError:
                    continue

    def rejectFrom(self,
                   other:Union['data.Vector', 'plugs.Vector'],
                   reuse:bool=True):
        """
        Makes this vector perpendicular to *otherVector*.
        See https://en.wikipedia.org/wiki/Vector_projection.

        :param other: the other vector
        :param reuse/re: if a calculation with the same argument is detected,
            reuse it; defaults to True
        """
        other = _mm.conform(other,
                            (plugs['Vector'], data['Vector']),
                            force=True)
        if reuse:
            found = self._retrieveRejectFrom(other)

            if found is not None:
                return found

        output = self._rejectFrom(other)

        nw = nodes['Network'].createNode()

        nw.addVectorAttr('otherVector', i=other, l=True)
        nw.addVectorAttr('outVectorRejection', i=output, l=True)
        nw.addAttr('rejectFrom_caller', at='message', i=self, l=True)

        return output

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
            node = nodes['MultiplyVectorByMatrix'].createNode()
            node.attr('input').connectInput(self)
            node.attr('matrix').put(other, isPlug)

            return node.attr('output')

        if shape == 4: # vector * quaternion
            return self * other.asRotateMatrix()

        return NotImplemented

    #-----------------------------------------|    Point-matrix mult, or cross

    def __xor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3: # cross product
            node = nodes['CrossProduct'].createNode()
            node.attr('input1').connectInput(self)
            node.attr('input2').put(other, isPlug)

            return node.attr('output')

        if shape == 16: # point-matrix mult
            node = nodes['MultiplyPointByMatrix'].createNode()
            node.attr('input').connectInput(self)
            node.attr('matrix').put(other, isPlug)

            return node.attr('output').asPoint()

        return NotImplemented

    def __rxor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3: # cross product
            node = nodes['CrossProduct'].createNode()
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

    def asPoint(self) -> 'plugs.Point':
        """
        This is purely a type change; no DG modifications are performed.
        """
        return self.asType(plugs['Point'])

    def asVector(self):
        return self

    def asCarrier(self) -> 'plugs.Quaternion':
        """Equivalent to self().rotateTo(self)."""
        return self().rotateTo(self)

    #-----------------------------------------|    Effects

    def sphereClamp(
            self,
            origin:Optional[Union['plugs.Point', 'data.Point']]=None
    ) -> 'Vector':
        """
        Intended for use within a context matrix (which can be skewed). Add to
        the origin point to get the point on the sphere surface.

        If *origin* is omitted, the result is equivalent to :meth:`normal`. If
        *origin* ever escapes the unit bounds, the local origin will be used
        instead.

        Top tip:
        When working with a world matrix, to get the normal at the surface, do
        this:

        ```
        localNormal = (originPoint + outVector).normal()
        worldNormal = (localNormal * worldMatrix.inverse().transpose()).normal()
        ```
        """
        selfN = self.normal()

        if origin is None:
            return selfN

        origin = _mm.conform(origin,
                             (plugs['Point'], data['Point']),
                             force=True)

        a = self.dot(self)
        b = 2 * origin.dot(self)
        c = origin.dot(origin) - 1.0
        discriminant = (b ** 2) - 4 * a * c
        isValid = discriminant >= 1e-5

        pb = nodes['Network'].createNode()
        one = pb.addAttr('one', dv=1.0, l=True)

        discriminant = isValid.ifElse(discriminant, one, plugs['Float'])
        t = (-b + (discriminant ** 0.5)) / (2 * a)
        outVector = t * self

        return isValid.ifElse(outVector, selfN, plugs['Vector'])

    def coneClamp(self, maxAngle:float, normal=None):
        """
        Only works within a 180 spherical range.

        :param normal: the reference (starting point) vector; if omitted,
            defaults to a static capture of this vector
        :param maxAngle: the maximum angle in all directions; if this goes
            beyond 180, you'll get flips to the other side
        """
        if normal is None:
            normal = self()
        else:
            normal = _mm.conform(normal, (data['Vector'], Vector))

        axis, angle = normal.axisAngleTo(self)
        clampedAngle = angle.maxClamp(maxAngle)
        out = normal.rotateByAxisAngle(axis, clampedAngle)

        return out.normal() * self.length()

    def coneFalloff(self, lowerMaxAngle, upperMaxAngle, damping=2, /):
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

        targetAngle = liveAngle.dampCeiling(lowerMaxAngle,
                                            upperMaxAngle,
                                            damping)

        outVector = initPose.rotateByAxisAngle(axis, targetAngle)

        return outVector