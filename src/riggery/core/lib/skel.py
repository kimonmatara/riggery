"""Defines classes to manage skeletal chains."""
import math
from typing import Generator, Optional, Union, Iterable

import riggery.core.lib.mathops as _mo
import riggery.core.lib.mixedmode as _mm
import riggery.core.lib.triadutil as _tr
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from riggery.general.numbers import floatrange
from ..lib import names as _nm
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data

import maya.cmds as m

def conform(*args) -> list:
    return list(map(nodes['DagNode'], expand_tuples_lists(*args)))


class Chain(list):

    #-------------------------------------------|    Loaders

    @classmethod
    def fromStartEnd(cls, startJoint, endJoint):
        """
        :param startJoint: the chain root joint
        :param endJoint: the chain end joint
        :return: A chain instance from *startJoint* down to *endJoint*,
            inclusively.
        """
        DagNode = nodes['DagNode']

        startJoint = DagNode(startJoint)
        endJoint = DagNode(endJoint)

        if startJoint == endJoint:
            raise RuntimeError("same start /end joints")

        path = [endJoint]

        while True:
            parent = path[-1].parent
            if parent is None:
                raise RuntimeError(
                    f"no path from {startJoint} to {endJoint}"
                )
            path.append(parent)
            if parent == startJoint:
                break

        return cls(map(DagNode, reversed(path)))

    @classmethod
    def fromStart(cls, joint) -> 'Chain':
        """
        :param joint: the root joint from which to start digging
        :return: A chain comprising *joint* and every joint under, up until
            joints run out, or a junction is met.
        """
        out = [nodes['DagNode'](joint)]
        while True:
            current = out[-1]
            children = list(current.iterChildren(type='joint'))
            if len(children) == 1:
                current = children[0]
                out.append(current)
                continue
            break
        return cls(out)

    #-------------------------------------------|    Constructor(s)

    @classmethod
    def createTriad(cls, p1, p2, p3,
                    boneAxis:str,
                    curlAxis:str, *,
                    bevel:Optional[float]=None,
                    parent=None,
                    curlVector=None,
                    rotateOrder:Union[str, int]=0,
                    tipMatrix=None):
        if bevel not in (0, None):
            points = [p1] + _tr.bevelTriad(p1, p2, p3, bevel) + [p3]
        else:
            points = [p1, p2, p3]

        if curlVector is None:
            curlVector = _tr.getTriadInfo(points)['curlVector']

        return cls.createFromPoints(points,
                                    boneAxis,
                                    curlAxis,
                                    curlVector,
                                    rotateOrder=rotateOrder,
                                    parent=parent,
                                    tipMatrix=tipMatrix)

    @classmethod
    def createFromStartEndPoints(cls,
                                 startPoint,
                                 endPoint,
                                 numJoints:int,
                                 boneAxis:str,
                                 curlAxis:str,
                                 upVector,
                                 rotateOrder='xyz',
                                 parent=None):
        startPoint = data['Point'](startPoint)
        endPoint = data['Point'](endPoint)
        tweenRatios = list(floatrange(0, 1, numJoints))[1:-1]
        tweenPoints = [startPoint.blend(endPoint, weight=weight)
                       for weight in tweenRatios]
        allPoints = [startPoint] + tweenPoints + [endPoint]
        chordVector = endPoint - startPoint
        upVector = data['Vector'](upVector)
        rmtx = _mm.createOrthoMatrix(boneAxis, chordVector,
                                     curlAxis, upVector).asRotateMatrix()
        matrices = [rmtx * point.asTranslateMatrix() for point in allPoints]
        return cls.createFromMatrices(matrices,
                                      rotateOrder=rotateOrder,
                                      parent=parent)

    @classmethod
    @short(rotateOrder='ro', parent='p')
    def createFromMatrices(cls,
                           matrices, *,
                           rotateOrder='xyz',
                           parent=None) -> 'Chain':
        """
        .. warning::

            The input matrices are not sanitized at all; ensure that they are
            free of scale / shear information.

        :param matrices: the matrices to use
        :param rotateOrder / ro: the rotate order to use; defaults to 'xyz'
        :return: The :class:`Chain` instance.
        """
        joints = []
        Joint = nodes['Joint']

        for i, matrix in enumerate(list(matrices)):
            with _nm.Name(i+1):
                joints.append(
                    Joint.create(
                        matrix=matrix,
                        worldSpace=True,
                        parent=joints[-1] if joints else None,
                        rotateOrder=rotateOrder
                    )
                )
        if parent is not None:
            joints[0].parent = parent
        return Chain(joints)

    @classmethod
    @short(rotateOrder='ro',
           tipMatrix='tm',
           parent='p')
    def createFromPoints(cls,
                         points,
                         boneAxis,
                         upAxis,
                         upVector, /,
                         rotateOrder:str='xyz',
                         tipMatrix=None,
                         parent=None) -> 'Chain':
        """
        Draws a skeletal chain.

        :param points: the points
        :param boneAxis: the axis aiming down each bone
        :param upAxis: the axis to aim towards the up vector
        :param upVector: a reference up vector; this will be biased by cross
            product calculations
        :param rotateOrder / ro: the rotate order to use; defaults to 'xyz'
        :param tipMatrix/tm: an optional override matrix for the tip joint
            (only rotation is used); defaults to None
        :param parent/p: an optional parent for the root joint; defaults to
            None
        :return: The :class:`Chain` instance.
        """
        Point, Matrix = data['Point'], data['Matrix']
        points = list(map(Point, points))
        baseVectors, isInline = cls._calcBaseVectors(points, upVector)

        matrices = [
            Matrix.createOrtho(
                boneAxis, boneVector,
                upAxis, upVector,
                w=point
            ).pick(translate=True,rotate=True) \
            for point, (boneVector, upVector) in zip(points, baseVectors)
        ]

        if tipMatrix is not None:
            tipMatrix = Matrix(tipMatrix).pick(rotate=True, default=matrices[-1])
            matrices[-1] = tipMatrix

        return cls.createFromMatrices(matrices,
                                      rotateOrder=rotateOrder,
                                      parent=parent)

    @classmethod
    def createFromCurve(cls, curve, numPoints:int, boneAxis, upAxis, upVector):
        """
        At the moment this is a basic implementation that merely delegates to
        :meth:`createFromPoints`; not particularly suitable for curves that
        break their own plane (those will need parallel transport, or somesuch).

        :param curve: the curve along which to sample points
        :param numPoints: the number of points to generate along the curve
        :param boneAxis: the axis aiming down each bone
        :param upAxis: the axis to aim towards the up vector
        :param upVector: a reference up vector; this will be biased by cross
            product calculations
        :return: The :class:`Chain` instance.
        """
        curve = nodes['DagNode'](curve)
        points = [curve.pointAtFraction(fraction, worldSpace=True) \
                  for fraction in floatrange(0, 1, numPoints)]
        return cls.createFromPoints(points, boneAxis, upAxis, upVector)

    #-------------------------------------------|    Init

    def __init__(self, items=None, /):
        if items is None:
            super().__init__()
        else:
            super().__init__(conform(*items))

    #-------------------------------------------|    Orientation

    @classmethod
    def _calcBaseVectors(cls, points, refVector) -> tuple[list, bool]:
        """
        Internal. Checks / casting are not performed. Returns a tuple with
        two members: A zipped list of down vector, up vector pairs, and a
        bool which will be True if the chain is in-line (and therefore the
        ref vector was used throughout).
        """
        #---------------------|    Prep

        points = list(points)
        numPoints = len(points)
        if numPoints < 2:
            raise NotImplementedError("need two or more points")

        Point = data['Point']
        Vector = data['Vector']

        points = [Point(point) for point in points]
        vectors = [(nextPoint-thisPoint) \
                   for thisPoint, nextPoint in zip(points, points[1:])]
        refVector = Vector(refVector)
        ratios = _mo.getLengthRatios(points)

        #---------------------|    Calc cross product keys

        perRatioCrosses = {}
        lastCross = None

        for i, (thisVector, nextVector) \
            in enumerate(zip(vectors, vectors[1:])):
            cross = thisVector.cross(nextVector)

            mag = cross.length()

            if mag < _mo.TOLERANCE:
                continue

            # Bias towards ref vec
            cross = cross.flipIfCloserTo(refVector)

            # Deflip
            if lastCross is not None:
                cross = cross.flipIfCloserTo(lastCross)

            perRatioCrosses[ratios[i+1]] = lastCross = cross

        #---------------------|    Resolve up vectors

        inline = False

        numCrosses = len(perRatioCrosses)
        if numCrosses == 0:
            upVectors = [refVector] * numPoints
            inline = True
        elif numCrosses < numPoints-2:
            interp = _mo.Interpolator.fromDict(perRatioCrosses)
            upVectors = [Vector(interp[ratio]) for ratio in ratios]
        else:
            upVectors = list(perRatioCrosses.values())
            upVectors.insert(0, upVectors[0])
            upVectors.append(upVectors[-1])

        #---------------------|    Zip and return

        vectors.append(vectors[-1]) # tip
        return list(zip(vectors, upVectors)), inline

    def orient(self, boneAxis, curlAxis, refVector, tipMatrix=None):
        """
        Orients this chain. If this chain has defined curvature, then any up
        vectors will follow it (with flips removed), but will be biased
        towards *refVector*. If this chain is in-line, *refVector* will be
        used explicitly as the up vector instead.

        :param boneAxis: the axis running down each bone
        :param curlAxis: the axis that will be aligned towards *refVector*
        :param refVector: the reference ('up') vector
        :param tipMatrix: an optional override for the tip joint; defaults to
            None
        """
        num = len(self)
        if num < 2:
            raise RuntimeError("not enough joints")
        baseVectors, isInline = self._calcBaseVectors(self.points, refVector)
        self.explode()

        Matrix = data['Matrix']

        for i, (joint, (downVec, upVec)) in enumerate(zip(self, baseVectors)):
            if i == num -1 and tipMatrix is not None:
                matrix = tipMatrix
            else:
                matrix = Matrix.createOrtho(boneAxis, downVec, curlAxis, upVec)
            joint.setMatrix(matrix, rotate=True, worldSpace=True)
            joint.makeIdentity(apply=True, rotate=True, jointOrient=False)

        self.compose()
        return self

    #-------------------------------------------|    Sampling

    @property
    def points(self) -> Generator:
        """
        Yields world-space joint positions.
        """
        for joint in self:
            yield joint.worldPosition()

    @property
    def ratios(self) -> list[float]:
        return _mo.getLengthRatios(self.points)

    def pointAtRatio(self, atRatio:float):
        """
        :param atRatio: the ratio along the chain at which to retrieve a point
        :return: The point at the specified ratio along the chain.
        """
        interp = _mo.Interpolator()
        points = list(self.points)
        ratios = _mo.getLengthRatios(points)

        for ratio, point in zip(ratios, points):
            interp[ratio] = point
        return data['Point'](interp[atRatio])

    @property
    def vectors(self) -> Generator:
        """
        Yields world-space bone vectors.
        """
        points = list(self.points)
        for thisPoint, nextPoint in zip(points, points[1:]):
            yield nextPoint - thisPoint

    def length(self):
        """
        :return: the sum of all the bones' vectors.
        """
        return sum([vector.length() for vector in self.vectors])

    def isInline(self) -> bool:
        """
        :raises ValueError: This chain has fewer than three joints.
        :return: ``True`` if this chain is in-line.
        """
        tol = _mo.TOLERANCE * 0.5

        if len(self) > 2:
            vecs = list(self.vectors)
            for i, (thisVec, nextVec) in enumerate(zip(vecs, vecs[1:])):
                dot = abs(thisVec.dot(nextVec, normalize=True))
                minSlack = 1.0 - tol
                maxSlack = 1.0 + tol
                inline = dot >= minSlack and dot <= maxSlack
                if not inline:
                    return False
            return True
        raise ValueError("not enough joints")

    def detectBoneAxis(self):
        """
        Returns the joint axis most commonly aligned to the bone lengths.
        :raises ValueError: Need at least two joints.
        """
        if len(self) < 2:
            raise ValueError("need at least two joints")

        vectors = self.vectors
        _axes = [
            joint.getMatrix(worldSpace=True).closestAxis(vector,
                                                         includeNegative=True,
                                                         asString=True) \
            for joint, vector in zip(self, self.vectors)
        ]

        axes = list(set(_axes))
        axes.sort(key=lambda x: _axes.count(x))
        return axes[-1]

    def detectCurlAxis(self, curlVector):
        """
        Returns the joint axis most commonly aligned to *curlVector*. the
        tip joint is ignored.
        :raises ValueError: Need at least two joints.
        """
        if len(self) < 2:
            raise ValueError("need at least two joints")
        curlVector = data['Vector'](curlVector)
        _axes = [
            joint.getMatrix(worldSpace=True).closestAxis(curlVector,
                                                         includeNegative=True,
                                                         asString=True) \
            for joint in self[:-1]
        ]
        axes = list(set(_axes))
        axes.sort(key=lambda x: _axes.count(x))
        return axes[-1]

    #-------------------------------------------|    Misc

    def setAttr(self, attrName, attrValue):
        """
        Convenience method. Sets an attribute across every joint in this chain.

        :param attrName: the attribute to set
        :param attrValue: the attribute value
        :return: self
        """
        for joint in self:
            joint.attr(attrName).set(attrValue)
        return self

    def setAttrs(self, **kwargs):
        """
        Convenience method. Sets attributes across all joints in this chain.

        :param \*\*kwargs: the attributes to set, with their corresponding
            values
        :return: self
        """
        for joint in self:
            for k, v in kwargs.items():
                joint.attr(k).set(v)
        return self

    #-------------------------------------------|    Bones

    def isBone(self) -> bool:
        """
        :return: True if this chain has exactly two joints.
        """
        return len(self) == 2

    def splitBone(self, numSplits:int) -> list:
        """
        .. note::

            This is not an in-place operation; a new Chain instance will be
            returned. This is intentional, to maintain access to indices on the
            original.

        :param numSplits: the number of joints to insert between the start and
            end
        :return: A new Chain instance, comprising the original start joint,
            the new inbetween joints, and the original end joint.
        """
        if len(self) != 2:
            raise TypeError("not a bone")

        self.compose()

        startPoint, endPoint = self.points

        vector = endPoint - startPoint
        pmtx = self[0].attr('pm')[0]()
        innerPoints = [
            startPoint.blend(endPoint, ratio)
            for ratio in list(floatrange(0, 1, numSplits+2))[1:-1]
        ]

        newJoints = []

        for innerPoint in innerPoints:
            newJoint = self[0].cleanCopy()
            newJoint.attr('t').set(innerPoint ^ newJoint.pim[0]())
            newJoints.append(newJoint)

        newStack = [self[0]] + newJoints + [self[1]]
        for thisJoint, nextJoint in zip(newStack, newStack[1:]):
            nextJoint.parent = thisJoint
        return Chain(newStack)

    #-------------------------------------------|    DAG editing

    @property
    def roots(self) -> Generator:
        """
        Yields joints whose parent is not a member of this chain.
        """
        for joint in self:
            parent = joint.parent
            if parent is None or parent not in self:
                yield joint

    def getParent(self):
        """
        :return: The first member's parent.
        """
        if self:
            return self[0].parent

    def setParent(self, parent):
        """
        :param parent: the parent to assign to the first member of this chain.
        :return: self
        """
        if self:
            self.compose()[0].parent = parent
        return self

    def clearParent(self):
        """
        Reparents the first joint of this chain to the world.
        """
        if self:
            self.compose()[0].parent = None
        return self

    parent = property(getParent, setParent, clearParent)

    def explode(self):
        """
        Reparents every joint in this chain to the parent of the first joint.
        """
        if len(self) > 1:
            parent = self[0].parent
            for joint in self[1:]:
                joint.parent = parent
        return self

    @short(parent='p',
           renumber='ren',
           startNumber='sn',
           compose='c')
    def duplicate(self, *, parent=None, startNumber:int=1, compose:bool=False):
        """
        :param parent/p: an optional destination parent for the duplicated
            chain
        :param startNumber/sn: the start number for renumbering; defaults to 1
        :param compose/c: if this chain is disjointed, make the duplicate
            contiguous; defaults to False
        :return: The duplicate chain.
        """
        duplicates = []

        for i, joint in enumerate(self):
            parent = joint.parent
            if i > 0 and parent == self[i-1]:
                parent = duplicates[-1]
            macro = joint.macro()
            with _nm.Name(i+startNumber):
                duplicate = joint.createFromMacro(macro,
                                                  parent=parent,
                                                  worldSpace=False)
            duplicates.append(duplicate)

        out = type(self)(duplicates)
        if compose:
            out.compose()
        return out

    def compose(self):
        """
        Parents every joint in this chain to the one before it.
        """
        if len(self) > 1:
            for thisJoint, nextJoint in zip(self, self[1:]):
                nextJoint.parent = thisJoint
        return self

    def hasOverflow(self) -> bool:
        """
        :return: True if there are more joints below the last member of this
            :class:`Chain` instance.
        """
        for child in self[-1].iterChildren(type='joint'):
            return True
        return False

    def appendChain(self, lowerChain, replaceTip:bool=False):
        """
        This is an in-place operation. Reparents the root of *lowerChain* to the
        bottom of this chain and amends membership in this instance.

        :param lowerChain: the chain to append
        :param replaceTip: delete the tip of this chain before reparenting
            *lowerChain*; defaults to False
        :return: self (for convenience)
        """
        if replaceTip:
            m.delete(str(self[-1]))
            del(self[-1])

        nodes['DagNode'](lowerChain[0]).parent = self[-1]
        self[:] = self + lowerChain
        return self

    # The below is buggy, rewrite more carefully
    # def splitAtRatios(self, atRatios:list[float]):
    #     """
    #     This is an in-place operation; the chain instance will be updated to
    #     include the inserted joints.
    #
    #     :param atRatios: the length ratios at which to insert joints
    #     :return: A list of lists, where each sublist comprises a tuple of
    #         (startJoint, endJoint) and a second tuple with the joints inserted
    #         inbetween.
    #     """
    #     points = list(self.points)
    #     existingRatios = _mo.getLengthRatios(points)
    #     existingJoints = {existingRatio:existingJoint \
    #                       for existingRatio, existingJoint \
    #                       in zip(existingRatios, self)}
    #
    #     outJoints = []
    #     out = []
    #     Joint = nodes['Joint']
    #
    #     for (thisExistingRatio, nextExistingRatio), \
    #             (thisExistingJoint, nextExistingJoint), \
    #             (thisPoint, nextPoint) in zip(
    #         zip(existingRatios, existingRatios[1:]),
    #         zip(self, self[1:]),
    #         zip(points, points[1:])
    #     ):
    #         outJoints.append(thisExistingJoint)
    #         requestedRatios = [ratio for ratio in atRatios \
    #                            if ratio > thisExistingRatio \
    #                            and ratio < nextExistingRatio]
    #
    #         if requestedRatios:
    #             matrix = thisExistingJoint.getMatrix(worldSpace=True)
    #             interp = _mo.Interpolator()
    #             interp[thisExistingRatio] = thisPoint
    #             interp[nextExistingRatio] = nextPoint
    #
    #             newJoints = []
    #
    #             for requestedRatio in requestedRatios:
    #                 newMatrix = matrix.copy()
    #                 newMatrix.w = interp[requestedRatio]
    #                 newJoint = Joint.create(matrix=newMatrix, worldSpace=True)
    #                 newJoints.append(newJoint)
    #
    #             newStack = [thisExistingJoint] + newJoints + [nextExistingJoint]
    #             for thisJoint, nextJoint in zip(newStack, newStack[1:]):
    #                 nextJoint.setParent(thisJoint)
    #
    #             outJoints += newJoints
    #
    #             out.append([(thisExistingJoint,
    #                          nextExistingJoint),
    #                         tuple(newJoints)])
    #
    #     outJoints.append(self[-1])
    #     self[:] = outJoints
    #
    #     return out
    #
    # def splitAtIndices(self,
    #                    indexPairs:Iterable[tuple[int, int]],
    #                    splitsPerPair:Iterable[int]):
    #     raise NotImplementedError

    #-------------------------------------------|    Transformations

    def reset(self):
        """
        Sets rotation channels to 0.0 on every joint in the chain.
        """
        for joint in self:
            joint.attr('r').set([0] * 3)
        return self

    def freeze(self):
        """
        Freezes rotations on every joint in the chain.
        """
        for joint in self:
            joint.makeIdentity(rotate=True, jointOrient=False, apply=True)
        return self

    #-------------------------------------------|    IK

    def ikJitter(self,
                 jitterVector,
                 forcePlane=False, /,
                 isInline:Optional[bool]=None):
        """
        This method will do nothing if the chain is not in-line, or if there are
        fewer than three joints.

        :param jitterVector: the axis vector around which the inner joints will
            be rotated counterclockwise to generate a preferred angle
        :param forcePlane: if this is ``True``, then the joint will be rotated
            strictly around *jitterVector*, disregarding existing joint axes;
            defaults to False
        :param isInline: if you already know if the chain is in-line, pass this
            here to avoid extraneous checks; defaults to None
        :return: self
        """
        if isInline is None:
            try:
                isInline = self.isInline()
            except ValueError:
                return self
        if not isInline:
            return self

        Vector = data['Vector']
        jitterVector = Vector(jitterVector)

        for joint in self[1:-1]:
            if forcePlane:
                vector = jitterVector
            else:
                vector = joint.getMatrix(
                    worldSpace=True
                ).closestAxis(jitterVector, includeNegative=True)

            vector *= joint.attr('pim')[0]()
            current = joint.getMatrix(worldSpace=True).quaternion()
            jitter = data['Quaternion'].fromAxisAngle(vector, math.radians(10))
            euler = jitter.asEulerRotation(order=joint.attr('rotateOrder')())
            joint.attr('preferredAngle').set(joint.attr('r')() + euler)

        return self

    @short(upVector='up', curve='c', parent='p')
    def createIkHandle(self, upVector=None, *, curve=None, parent=None):
        """
        Delegates to :meth:`~riggery.core.nodetypes.ikHandle.IkHandle.create`.
        """
        if len(self) > 1:
            self.compose()
            return nodes['IkHandle'].create(self[0], self[-1],
                                            upVector,
                                            curve=curve,
                                            parent=parent)

        raise ValueError("need two or more joints")

    #-------------------------------------------|    Naming

    def rename(self, startNumber:int=1):
        for i, joint in enumerate(self):
            with _nm.Name(i+startNumber, pad=len(str(len(self)))):
                del(joint.name)
        return self

    #-------------------------------------------|    Instance access

    def __getitem__(self, item):
        out = super().__getitem__(item)
        if isinstance(item, slice):
            return type(self)(out)
        return out

    #-------------------------------------------|    Instance editing

    def __add__(self, other):
        return type(self)(super().__add__(other))

    def __iadd__(self, other:list):
        return type(self)(super().__iadd__(other))

    def __radd__(self, other:list):
        return type(self)(super().__radd__(other))

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            value = conform(value)
        else:
            value = nodes['DagNode'](value)
        super().__setitem__(key, value)

    #-------------------------------------------|    Repr

    def __repr__(self):
        return "{}({})".format(type(self).__name__,
                               repr([str(x) for x in self]))