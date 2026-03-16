"""Defines classes to manage skeletal chains."""
import re
import math
from typing import Iterator, Optional, Union, Iterable, Literal
from itertools import chain as _chain

import riggery.core.lib.mathops as _mo
from riggery.core.lib import meshutil as _mu
import riggery.core.lib.mixedmode as _mm
import riggery.core.lib.triadutil as _tr
from riggery.general.functions import short
from riggery.general.iterables import (expand_tuples_lists, pad_nones,
                                       issublist, without_duplicates)
from riggery.general.numbers import floatrange
from ..lib import names as _nm
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as data

import maya.cmds as m

def conform(*args) -> list:
    return list(map(nodes['DagNode'], expand_tuples_lists(*args)))


class Chain(list):

    #-------------------------------------------|    Loaders

    @classmethod
    @short(expandLeftovers='exp',
           skipWishbones='swb')
    def reduceToBones(cls,
                      *args,
                      expandLeftovers:bool=False,
                      skipWishbones:bool=True,
                      ) -> tuple[list['Chain'], list['nodes.Joint']]:
        """
        :param \*args: any combination of joints or chains
        :param expandLeftovers/exp: attempt to derive bones from any leftover
            joints by looking for child joints outside the selection list;
            defaults to None
        :param skipWishbones/swb: if a joint has more than one child joint,
            don't generate a bone for each; skip the junction and continue
            iterating from each child separately; defaults to True
        :return: A tuple of two members: the first member will be a list of any
            bones formed betwen the parsed joints; the second will be a list of
            any leftover joints.
        """
        joints = list(without_duplicates(
            (map(nodes['Joint'], expand_tuples_lists(*args)))
        ))

        bones = []

        for parentJoint in joints:
            children = list(parentJoint.iterChildren(type='joint'))

            if not expandLeftovers:
                children = [x for x in children if x in joints]

            if skipWishbones and len(children) != 1:
                continue

            for child in children:
                bone = Chain((parentJoint, child))

                if bone not in bones:
                    bones.append(bone)

        bones = tuple(without_duplicates(bones, False))
        usedUpJoints = set(_chain.from_iterable(bones))
        leftovers = tuple((x for x in joints if x not in usedUpJoints))

        return bones, tuple(leftovers)

    @classmethod
    @short(skipWishbones='swb')
    def iterBonesFrom(cls,
                      startJoint:'nodes.Joint', *,
                      skipWishbones:bool=True) -> Iterator['Chain']:
        """
        Iterates across every bone (two-joint chain) that can be detected from
        *startJoint* downwards.

        :param skipWishbones/swb: if a joint has more than one child joint,
            don't generate a bone for each; skip the junction and continue
            iterating from each child separately; defaults to True
        """
        def chase(parentJoint):
            if skipWishbones:
                children = list(parentJoint.iterChildren(type='joint'))

                if len(children) == 1:
                    yield Chain((parentJoint, children[0]))

                for child in children:
                    yield from chase(child)
            else:
                for child in parentJoint.iterChildren(type='joint'):
                    yield Chain((parentJoint, child))
                    yield from chase(child)

        yield from chase(nodes['Joint'](startJoint))

    @classmethod
    def boneFrom(cls, startJoint:'nodes.Joint') -> Optional['Chain']:
        """
        :return: A :class:`Chain` instance comprising *startJoint* and the first
            joint child detected underneath it, or None if no immediate child
            joint could be found.
        """
        startJoint = nodes['Joint'](startJoint)
        child = next(startJoint.iterChildren(type='joint'), None)

        if child is None:
            return None

        return Chain((startJoint, child))

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
    def createTriad(cls,
                    p1:data['Point'],
                    p2:data['Point'],
                    p3:data['Point'],
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
        baseVectors, isInline = _mo.calcMatrixChainBaseVectors(points, upVector)

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

    def orient(self,
               boneAxis:str,
               curlAxis:str,
               curlVector,
               tipMatrix=None):
        """
        Orients this chain. If this chain has defined curvature, then any up
        vectors will follow it (with flips removed), but will be biased
        towards *curlVector*. If this chain is in-line, *curlVector* will be
        used explicitly as the up vector instead.

        :param boneAxis: the axis running down each bone
        :param curlAxis: the axis that will be aligned towards *curlVector*
        :param curlVector: the reference 'up' vector
        :param tipMatrix: an optional override for the tip joint; defaults to
            None
        """
        num = len(self)

        if num < 2:
            raise RuntimeError("not enough joints")

        Matrix = data['Matrix']
        baseVectors, _ = _mo.calcMatrixChainBaseVectors(self.points, curlVector)

        for i, (joint, (boneVector, curlVector)) in enumerate(
                zip(self, baseVectors)
        ):
            if i == num -1 and tipMatrix is not None:
                matrix = tipMatrix
            else:
                matrix = Matrix.createOrtho(boneAxis, boneVector,
                                            curlAxis, curlVector)

            joint.setRestRotateMatrix(matrix, rr=True, ws=True)
            joint.attr('displayLocalAxis').set(True)

        return self

    #-------------------------------------------|    Sampling

    @short(plug='p')
    def iterPoints(self, plug=False) -> Iterator[
        Union['data.Point', 'plugs.Points']
    ]:
        """
        Yields world-space joint positions.
        """
        for joint in self:
            yield joint.worldPosition(plug=plug)

    @short(plug='p')
    def getPoints(self,
                  plug:bool=False) -> list[Union['data.Point', 'plugs.Point']]:
        """
        Flat version of :meth:`iterPoints`.
        """
        return list(self.iterPoints(plug=plug))

    points = property(fget=iterPoints)

    def getRatios(self) -> list[float]:
        return _mo.getLengthRatios(self.points)

    ratios = property(fget=getRatios)

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

    @short(plug='p')
    def iterVectors(self, plug=False):
        points = list(self.iterPoints(plug=plug))
        for thisPoint, nextPoint in zip(points, points[1:]):
            yield nextPoint - thisPoint

    vectors = property(fget=iterVectors)

    @short(plug='p')
    def getChordVector(self, plug=False):
        return self[-1].worldPosition(p=plug) - self[0].worldPosition(p=plug)

    chordVector = property(getChordVector)

    def length(self):
        """
        :return: the sum of all the bones' vectors.
        """
        return sum([vector.length() for vector in self.vectors])

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

    def detectCurlAxis(self, curlVector=None, /):
        """
        Returns the joint axis most commonly aligned to *curlVector*. the tip
        joint is ignored.

        :raises RuntimeError: need more joints
        :raises RuntimeError: can't auto-derive curl vector, provide explicitly
        """
        if curlVector is None:
            if len(self) < 3:
                raise RuntimeError(
                    "can't auto-derive curl vector, provide explicitly"
                )

            vectors = list(self.vectors)
            curlVectors = []

            for thisVector, nextVector in zip(vectors, vectors[1:]):
                cross = thisVector.cross(nextVector)

                if cross.length() < 1e-5:
                    cross = None

                curlVectors.append(cross)

            try:
                curlVectors = pad_nones(curlVectors, conserve=True)
            except ValueError:
                raise RuntimeError(
                    "can't auto-derive curl vector, provide explicitly"
                )
            curlVectors.insert(0, curlVectors[0])
        else:
            numJoints = len(self)

            if numJoints < 2:
                raise RuntimeError("need at least two joints")

            curlVectors = [data.Vector(curlVector)] * (numJoints-1)

        axes = [joint.getMatrix(ws=True).closestAxis(curlVector, asString=True,
                                                     includeNegative=True)
                for curlVector, joint in zip(curlVectors, self[:-1])]
        axes.sort(key=lambda x: axes.count(x))
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

    def splitBone(self, numSplits:int, twist:bool=False):
        if not self.isBone():
            raise TypeError("not a bone")

        if numSplits < 1:
            return self.copy()

        # Calculate tween ratios
        tweenRatios = list(floatrange(0, 1, numSplits+2))[1:-1]

        # Calculate tween points
        startPoint, endPoint = self.points
        tweenPoints = [startPoint.blend(endPoint,
                                        weight=x) for x in tweenRatios]

        if twist:
            # Will figure out twist using a parallel-transport style solution,
            # i.e. transport the start twist vector to the lower bone, and then
            # measure a delta from the lower bone's actual twist axis

            boneAxis = self.detectBoneAxis()
            absBoneAxis = boneAxis.strip('-')

            twistAxis = next((ax for ax in 'xyz' if ax != absBoneAxis))

            startMatrix = self[0].getMatrix(ws=True)
            endMatrix = self[1].getMatrix(ws=True)

            startTwistVector = startMatrix.getAxis(twistAxis)
            startBoneVector = endPoint - startPoint
            endBoneVector = endMatrix.getAxis(boneAxis)
            endRefTwistVector = (startTwistVector
                                 * (startBoneVector.quatTo(endBoneVector)))

            angle = endRefTwistVector.angleTo(endMatrix.getAxis(twistAxis),
                                              shortest=True,
                                              normal=endBoneVector)

            tweenTwistVectors = [
                startTwistVector.rotateByAxisAngle(startBoneVector,
                                                   angle * weight)
                for weight in tweenRatios
            ]

            tweenMatrices = [
                _mm.createOrthoMatrix(boneAxis, startBoneVector,
                                      twistAxis, tweenTwistVector,
                                      w=point).pick(t=True, r=True)
                for point, tweenTwistVector in zip(tweenPoints,
                                                   tweenTwistVectors)
            ]
        else:
            rmtx = self[0].getMatrix(worldSpace=True).pick(r=True)
            tweenMatrices = [rmtx * x.asTranslateMatrix() for x in tweenPoints]

        tweenJoints = [nodes.Joint.create(matrix=matrix, worldSpace=True)
                       for matrix in tweenMatrices]

        newJoints = [self[0]] + tweenJoints + [self[1]]

        for parent, child in zip(newJoints, newJoints[1:]):
            child.setParent(parent)

        return Chain(newJoints)


    def displayLocalAxis(self):
        for x in self:
            x.attr('displayLocalAxis').set(True)
        return self

    #-------------------------------------------|    DAG editing

    @property
    def roots(self) -> Iterator:
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
           compose='c',
           mirror='mir')
    def duplicate(self, *,
                  parent=None,
                  compose:bool=False,
                  mirror:bool=False):
        """
        :param parent/p: an optional destination parent for the duplicated
            chain
        :param compose/c: if this chain is disjointed, make the duplicate
            contiguous; defaults to False
        :return: The duplicate chain.
        """
        duplicates = []

        if mirror:
            boneAxis = self.detectBoneAxis()
            otherAxis = _mo.nextAxisLetter(boneAxis)
            mirrorer = data.Matrix()
            mirrorer.flipAxis('x')

        for i, joint in enumerate(self):
            parent = joint.parent

            if i > 0 and parent == self[i-1]:
                parent = duplicates[-1]

            macro = joint.macro()

            duplicate = joint.createFromMacro(macro, parent=parent)

            if mirror:
                origName = joint.shortName(sns=True)
                mt = re.match(r"^([LR])_(.*?)$", origName)
                if mt:
                    side, base = mt.groups()
                    side = {'L':'R', 'R':'L'}[side]
                    newName = '_'.join([side, base])
                    origNs = joint.namespace

                    if not origNs.isRoot():
                        newName = '{}:{}'.format(origNs, newName)

                    duplicate.name = newName

                # Get info
                origPosition = joint.worldPosition()
                origWMatrix = joint.getMatrix(ws=True)
                origBoneVector = origWMatrix.getAxis(boneAxis)
                origOtherVector = origWMatrix.getAxis(otherAxis)

                # Construct the projected pose matrix
                mirrorPoseMatrix = data.Matrix.createOrtho(
                    boneAxis, -(origBoneVector * mirrorer),
                    otherAxis, -(origOtherVector * mirrorer),
                    w=origPosition ^ mirrorer
                ).pick(t=True, r=True)


                # Apply the projected pose matrix
                mirrorPoseMatrix.decomposeAndApply(duplicate, ws=True)

                # Apply the projected rest matrix (without a reset)
                origWRestMatrix = joint.getRestRotateMatrix(ws=True)
                origBoneVector = origWRestMatrix.getAxis(boneAxis)
                origOtherVector = origWRestMatrix.getAxis(otherAxis)

                mirrorRestMatrix = data.Matrix.createOrtho(
                    boneAxis, -(origBoneVector * mirrorer),
                    otherAxis, -(origOtherVector * mirrorer)
                ).pick(r=True)

                duplicate.setRestRotateMatrix(mirrorRestMatrix,
                                              ws=True,
                                              pc=False)
                duplicate.attr('r').set(joint.attr('r')())

            duplicates.append(duplicate)

        out = type(self)(duplicates)

        if compose:
            out.compose()

        if _nm.Name.__elems__:
            out.rename()

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

    def getClosestJointsOn(self, otherChain, indices:bool=False) -> list:
        """
        For each joint on this chain, returns the closest joint on *otherChain*.
        """
        out = []

        otherPoints = list(zip(otherChain,
                               [x.worldPosition() for x in otherChain]))

        for i, thisJoint in enumerate(self):
            thisPoint = thisJoint.worldPosition()
            bestMatch = None
            bestDistance = None

            for ii, (otherJoint, otherPoint) in enumerate(otherPoints):
                vector = otherPoint - thisPoint
                distance = vector.length()
                if ii == 0 or distance < bestDistance:
                    bestMatch = ii
                    bestDistance = distance

            out.append(bestMatch)

        if indices:
            return out

        return [otherChain[i] for i in indices]

    def getClosestBone(self, refPoint) -> 'Chain':
        """Returns the closest bone to *refPoint*."""
        refPoint = data['Point'](refPoint)
        candidates = []

        for boneRootIndex, (thisPoint, nextPoint) in enumerate(
                zip(self.points, list(self.points)[1:])
        ):
            closestPoint = _mo.closestPointOnLine(
                refPoint,
                thisPoint,
                (nextPoint - thisPoint),
                clamp=True
            )
            distance = (refPoint-closestPoint).length()
            thisBone = Chain([self[boneRootIndex], self[boneRootIndex+1]])
            candidates.append((distance, thisBone))

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def getClosestJointsWithWeights(self,
                                    refPoint:'data.Point',
                                    maxNumber:Optional[int]=None, /
                                    ) -> list[tuple['nodes.Transform', float]]:
        """
        Returns joints, and associated weights, ranked by proximity to
        *refPoint*. Useful for quickly calculating multi-joint constraint
        weights.

        :return: list of tuple(joint, weight)
        """
        weights = _mo.calcDistanceWeights(refPoint, list(self.points))
        out = list(sorted(zip(self, weights), key=lambda x: x[1], reverse=True))

        if maxNumber is not None and len(out) > maxNumber:
            joints, weights = zip(*out[:maxNumber])
            weights = _mo.calcDistanceWeights(refPoint,
                                              [j.worldPosition()
                                               for j in joints])
            return list(zip(joints, weights))

        return out

    def getClosestJoints(self, refPoint:'data.Point') -> list['nodes.Joint']:
        """
        :return: A list of this chain's member, ranked by proximity to
        *refPoint*.
        """
        refPoint = data['Point'](refPoint)
        ranked = ((joint.worldposition()))

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

    def isInline(self, tolerance=1e-4) -> bool:
        """
        :param tolerance: the minimum cross product length; defaults to 1e-4,
            which is around the point when Maya IK handles will fail
        :raises ValueError: Need at least 3 joints.
        :return: True if this chain is in-line.
        """
        num = len(self)

        if num < 3:
            raise ValueError("need at least 3 joints")

        vectors = [v.normal() for v in self.vectors]

        for thisVector, nextVector in zip(vectors, vectors[1:]):
            if thisVector.cross(nextVector).length() > tolerance:
                return False

        return True

    def getPoleVector(self) -> 'data.Vector':
        """
        :return: The default pole vector for this chain, as Maya would calculate
            it. No in-line checking is performed; the pole vector may be of zero
            length.
        """
        return _mo.getPoleVector(list(self.points))['poleVector']

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

    def createIkHandles(self, parent=None) -> list:
        """Creates one IK handle per bone."""
        out = []

        for i, bone in enumerate(self.bones):
            with _nm.Name(i+1):
                ikh = bone.createIkHandle(parent=parent)
            out.append(ikh)

        return out

    #-------------------------------------------|    Naming

    def rename(self):
        for i, joint in enumerate(self):
            with _nm.Name(i+1, pad=len(str(len(self)))):
                del(joint.name)
        return self

    #-------------------------------------------|    Instance copying

    def copy(self):
        """Returns a copy of this Chain instance. No new joints are created."""
        return type(self)(self)

    #-------------------------------------------|    Instance access

    def rebracket(self, greedy:bool=False):
        """
        Updates this chain's membership by tracing a path between its first and
        last joints.

        :param greedy: chase more joints beyond the last one; defaults to False
        """
        cls = type(self) # for clarity
        newChain = cls.fromStartEnd(self[0], self[-1])

        if greedy:
            newChain = newChain[:-1] + cls.fromStart(self[-1])

        self[:] = newChain

        return self

    def __getitem__(self, item):
        out = super().__getitem__(item)
        if isinstance(item, slice):
            return type(self)(out)
        return out

    @property
    def bones(self) -> Iterator['Chain']:
        """
        Returns non-overlapping :class:`Chain` pairwise segments.
        """
        for thisJoint, nextJoint in zip(self, self[1:]):
            yield Chain([thisJoint, nextJoint])

    #-------------------------------------------|    Rigging

    def iterVerticesAlongBoneAxis(
            self,
            mesh:Union[str, nodes['DagNode']],
            radius:float,
            firstHit:bool=False,
            indices:bool=False
    ) -> Iterator[Union[str, int]]:
        """
        Detects vertices on *mesh* using a cylindrical projection / containment
        test.

        :param mesh: the mesh on which to detect vertices
        :param radius: the cylinder radius
        :param firstHit: skip vertices that are occluded from the cylinder axis
            by *mesh* itself; defaults to False
        :param indices: return vertex indices rather than full component paths;
            defaults to False
        :return: The selected vertices on *mesh*.
        """
        if len(self) == 2:
            points = list(self.points)
            cylinderVector = points[1]-points[0]
            cylinderOrigin = points[0]

            _mesh = str(mesh)

            for x in _mu.selectVertsInsideCylinder(_mesh,
                                                   cylinderOrigin.api,
                                                   cylinderVector.api,
                                                   radius,
                                                   firstHit=firstHit):
                if indices:
                    yield x
                else:
                    yield f"{_mesh}.vtx[{x}]"
        else:
            raise TypeError("not a bone chain")

    def selectVerticesAlongBoneAxis(self,
                                    mesh:Union[str, nodes['DagNode']],
                                    radius:float,
                                    firstHit:bool=False,
                                    add:bool=False) -> list[str]:
        """
        Selects vertices on *mesh* using a cylindrical projection / containment
        test.

        :param mesh: the mesh on which to select vertices
        :param radius: the cylinder radius
        :param firstHit: don't select vertices that are occluded from the
            cylinder axis by *mesh* itself; defaults to False
        :return: The selected vertices on *mesh*.
        """
        verts = list(
            self.iterVerticesAlongBoneAxis(mesh,
                                           radius,
                                           firstHit=firstHit)
        )
        kwargs = {}
        if add:
            kwargs['add'] = True
        else:
            kwargs['replace'] = True
        m.select(verts, **kwargs)

        return verts

    #-------------------------------------------|    Curves

    @short(degree='d', plug='p')
    def fitCurve(self,
                 *,
                 degree:int=3,
                 ep:bool=False,
                 plug:bool=False,
                 parent:Optional['nodes.Transform']=None) -> 'nodes.Transform':
        """
        :return: The curve transform.
        """
        points = list(self.iterPoints(plug=plug))
        curveShape = nodes['NurbsCurve'].create(points, degree=degree, ep=ep)
        curveXform = curveShape.parent

        if parent is not None:
            curveXform.parent = parent

        return curveXform

    #-------------------------------------------|    Instance editing

    def isSubchain(self, otherChain) -> bool:
        """
        :return: True if this chain occurs within *otherChain* in the same
            order, otherwise False.
        """
        return issublist(self, otherChain)

    def __eq__(self, other:Union[tuple, list]):
        if isinstance(other, (list, tuple)):
            return all((x == y for x, y
                        in zip(self, map(nodes['Joint'], other))))
        return False

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