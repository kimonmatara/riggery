"""Utilities for managing triads."""

import math
from typing import Union, Optional, Iterable, Literal

from riggery.general.functions import short
from ..datatypes import __pool__ as _data
from ..plugtypes import __pool__ as _plugs
from ..nodetypes import __pool__ as _nodes

from . import mixedmode as _mm
from . import names as _nm

# The below is intended to match Maya's tolerances, which aren't particularly
# high or accurate
INLINE_TOLERANCE = 1e-5

class TriadInsufficientHintsError(ValueError):
    """
    Raised when triad framing can't be completed because the points are in-
    line and no further user hints have been provided.
    """

class TriadPointNumberError(ValueError):
    """
    Raised when a triad does not comprise exactly three or four points.
    """    

def bevelTriad(p0, p1, p2, length) -> tuple[
    'r.data.Point',
    'r.data.Point',
    'r.data.Point',
    'r.data.Point'
]:
    """
    Splits the middle point of a triad into two, creating an isosceles bevel.

    :param p0: the first point (value or plug)
    :param p1: the second point (value or plug)
    :param p2: the third point (value or plug)
    :param length: the length of the bevel (value or plug)
    :return: Four points: p0 (merely conformed), the first bevel point, the
        second bevel point and p2 (merely conformed).
    """
    pointTypes = (_plugs['Point'], _data['Point'])

    p0, _, p0IsPlug = _mm.info(p0, pointTypes)
    p1, _, p1IsPlug = _mm.info(p1, pointTypes)
    p2, _, p2IsPlug = _mm.info(p2, pointTypes)

    points = [p0, p1, p2]
    plugsInPoints = any((p0IsPlug, p1IsPlug, p2IsPlug))

    length, _, lengthIsPlug = _mm.info(length, _plugs['Float'])

    anyPlugs = plugsInPoints or lengthIsPlug

    # Get vectors

    v1 = points[0]-points[1] # reversed, radiating
    v2 = points[2]-points[1]

    # Get short angle

    angle = v1.angleTo(v2) * 0.5

    if plugsInPoints:
        sinAngle = angle.sin()
    else:
        sinAngle = math.sin(angle)

    opp = length * 0.5
    hyp = opp / sinAngle

    # Plot

    b0 = points[1] + (v1.normal() * hyp)
    b1 = points[1] + (v2.normal() * hyp)

    out = p0, b0, b1, p2
    return out

def unbevelTriad(p0, p1, p2, p3) -> tuple[
    Union['_data.Point', '_plugs.Point'],
    Union['_data.Point', '_plugs.Point'],
    Union['_data.Point', '_plugs.Point']
]:
    """
    Reverses the result of :func:`bevelTriad` (assumes an isosceles bevel).

    :param p0: the first triad point (value or plug)
    :param p1: the first bevel point (value or plug)
    :param p2: the second bevel point (value or plug)
    :param p3: the last triad point (value or plug)
    :return: Three points; the middle one will be the restored peak.
    """
    pointTypes = (_plugs['Point'], _data['Point'])

    p0, _, p0IsPlug = _mm.info(p0, pointTypes)
    p1, _, p1IsPlug = _mm.info(p1, pointTypes)
    p2, _, p2IsPlug = _mm.info(p2, pointTypes)
    p3, _, p3IsPlug = _mm.info(p3, pointTypes)

    hasPlugs = any((p0IsPlug, p1IsPlug, p2IsPlug, p3IsPlug))

    v0 = p1-p0
    v1 = p3-p2

    theta = (-v1).angleTo(v0) * 0.5
    opp = (p2-p1).length() * 0.5

    if hasPlugs:
        sinTheta = theta.sin()
        aligned = sinTheta.lt(1e-6)

        pb = _nodes['Network'].createNode()
        one = pb.addAttr('one', k=True, at='double', dv=1.0, l=True)
        operand = aligned.ifElse(one, sinTheta)

        hyp = opp / operand

        midpoint = aligned.ifElse(p1.blend(p2),
                                  p1 + (v0.normal() * hyp))

    else:
        sinTheta = math.sin(theta)
        aligned = sinTheta <= 1e-8

        if aligned:
            midpoint = p1.blend(p2)
        else:
            hyp = opp / sinTheta
            midpoint = p1 + (v0.normal() * hyp)

    return p0, midpoint, p3

def resolveTriadBevel(points:Iterable['_data.Point'],
                      bevel:Optional[float]=None
                      ) -> tuple[list['_data.Point'], bool]:
    """
    'Bevel' is overwritten on output with the *actual* bevel if four points are
    provided.

    :returns: list of three or four points, bevel length (float)
    """
    points, isBevelled = conformTriadPoints(points)

    if isBevelled:
        bevel = (points[2]-points[1]).length()
    else:
        if bevel is not None:
            points = bevelTriad(*points, bevel)

    return points, bevel

def getBoneVectorsFromTriadPoints(
        triadPoints:list[list[float]]
) -> tuple[list[float], list[float]]:
    """
    Convenience method. Returns two bone vectors from a list of three or four
    (bevelled) triad points.
    """
    num = len(triadPoints)
    if num == 3:
        triadPoints = [_data['Point'](x) for x in triadPoints]
        v0 = triadPoints[1] - triadPoints[0]
        v1 = triadPoints[2] - triadPoints[1]
    elif num == 4:
        triadPoints = [_data['Point'](x) for x in triadPoints]
        v0 = triadPoints[1] - triadPoints[0]
        v1 = triadPoints[3] - triadPoints[2]
    else:
        raise ValueError("Expected three or four (bevelled) triad points")
    return v0, v1

@short(inlineTolerance='tol')
def boneVectorsAreInline(v0, v1,
                         inlineTolerance:float=INLINE_TOLERANCE) -> bool:
    """
    :param v0: the top triad bone vector
    :param v0: the bottom triad bone vector
    :param inlineTolerance/tol: the dot product value below which the triad will
        be considered to be in-line; defaults to the global INLINE_TOLERANCE
        constant
    :return: True if the triad is in-line, otherwise False.
    """
    v0, v1 = map(_data['Vector'], (v0, v1))
    return v0.dot(v1, normalize=True) > 1.0 - inlineTolerance

@short(inlineTolerance='tol')
def triadIsInline(p0, p1, p2, inlineTolerance:float=INLINE_TOLERANCE) -> bool:
    """
    :param p0: the first triad point (value)
    :param p1: the second triad point (value)
    :param p2: the third triad point (value)
    :param inlineTolerance/tol: the dot product value below which the triad will
        be considered to be in-line; defaults to the global INLINE_TOLERANCE
        constant
    :return: True if the triad is in-line, otherwise False.
    """
    p0, p1, p2 = map(_data['Point'], (p0, p1, p2))
    v0 = p1 - p0
    v1 = p2 - p1
    return boneVectorsAreInline(v0, v1, inlineTolerance)

@short(curlVector='cv',
       poleVector='pv',
       kinkVector='kv',
       polePoint='pp',
       polePointDistance='ppd',
       inlineTolerance='tol',
       proportionalPolePointDistance='ppp')
def getTriadInfo(points, *,
                 curlVector=None,
                 poleVector=None,
                 kinkVector=None,
                 polePoint=None,
                 polePointDistance=None,
                 proportionalPolePointDistance=True,
                 inlineTolerance:float=INLINE_TOLERANCE) -> dict:
    """
    Returns information for triad framing. Only works with values, not plugs.

    If the chain is in-line, then at least one of *curlVector*, *poleVector*,
    *kinkVector* or *polePoint* must be provided.

    :param points: three or four (bevelled) triad points
    :param curlVector: a hint for the triad curl vector (i.e. the vector
        around which the second bone would rotate counterclockwise if an IK
        handle is applied)
    :param poleVector: a hint for the triad pole vector (i.e. the direction
        in which the knee / elbow should bend
    :param polePoint: a hint for the triad pole point (i.e. as typically used
        for pole vector constraints)
    :param polePointDistance: a preferred distance from the second triad point
        to the pole point
    :param proportionalPolePointDistance: if *polePointDistance* wasn't
        provided, improvise one by halving the triad's overall length; is
        overridden to True if a length can't be derived from any other hints;
        defaults to True
    :param inlineTolerance/tol: the dot product value below which the triad will
        be considered to be in-line; defaults to the global INLINE_TOLERANCE
        constant
    :raises TriadInsufficientHintsError: The triad was in-line, and no keyword-
        argument hints were provided to help complete the framing.
    :raises ValueError: Expected three or four triad points.
    :return: A dictionary with these keys:

        polePoint:          A point suitable for use as a pole-vector constraint
                            target
        chordVector:        The vector from the first point to the last point
        poleVector:         The pole vector, perpendicularized against the chord
                            vector and normalized
        curlVector:         The triad curl vector (follows the CCW rule)
        kinkVector:         The vector radiating from the elbow / knee
        polePointDistance:  The resolved pole point distance
        points:             The triad points (conformed to three)
        vectors:            The vectors for the triad 'legs'
        isBevelled:         True if four points were originally provided
    """
    points = list(points)   # consume any iterable / generator
    numPoints = len(points)

    if numPoints == 3:
        isBevelled = False
    elif numPoints == 4:
        isBevelled = True
    else:
        raise ValueError("expected three or four triad points")

    Vector = _data['Vector']
    Point = _data['Point']

    if isBevelled:
        points = unbevelTriad(*points)
    else:
        points = [_mm.conform(x, Point) for x in points]

    # Conform whatever was provided

    if curlVector is not None:
        curlVector = Vector(curlVector)

    if poleVector is not None:
        poleVector = Vector(poleVector)

    if kinkVector is not None:
        kinkVector = Vector(kinkVector)

    if polePoint is not None:
        polePoint = Point(polePoint)

    # Early erroring

    isInline = triadIsInline(*points, inlineTolerance=inlineTolerance)

    if isInline and all((x is None for x in (polePoint,
                                             poleVector,
                                             kinkVector,
                                             curlVector))):
        raise TriadInsufficientHintsError("insufficient hints for in-line triad")

    # Get secondary vectors

    v0 = points[1] - points[0]
    v1 = points[2] - points[1]
    chordVector = points[2] - points[0]

    # Resolve normalized curl vector

    if curlVector is None:
        if isInline:
            if poleVector is not None:
                curlVectorN = poleVector.cross(chordVector).normal()
            elif kinkVector is not None:
                curlVectorN = kinkVector.cross(chordVector).normal()
            else: # polePoint remains
                curlVectorN = (polePoint
                               - points[0]).cross(chordVector).normal()
        else:
            curlVectorN = v0.cross(v1).normal()
    else:
        curlVectorN = curlVector.normal()

    # Resolve normalized pole vector

    poleVectorN = chordVector.cross(curlVectorN).normal()

    # Resolve normalized kink vector

    if kinkVector is None:
        if isInline:
            kinkVectorN = poleVectorN.copy()
        else:
            kinkVectorN = (v0.normal() - v1.normal()).normal()
    else:
        kinkVectorN = kinkVector.normal()

    # Resolve pole point distance

    if polePointDistance is None:
        if proportionalPolePointDistance \
                or all((x is None
                        for x in (polePoint, poleVector, kinkVector))):
            overallLength = v0.length() + v1.length()
            polePointDistance = overallLength * 0.5
        else:
            if polePoint is not None:
                polePointDistance = (polePoint - points[1]).length()
            elif poleVector is not None:
                polePointDistance = poleVector.projectOnto(kinkVectorN).length()
            else: # kink vector remains
                polePointDistance = kinkVector.length()

    # Resolve pole point

    if polePoint is None:
        polePoint = points[1] + kinkVectorN * polePointDistance

    return {'points': points,
            'kinkVector': kinkVectorN * polePointDistance,
            'poleVector': poleVectorN.rejectFrom(chordVector).normal(),
            'curlVector': curlVectorN,
            'isBevelled': isBevelled,
            'polePoint': polePoint,
            'chordVector': chordVector,
            'vectors': (v0, v1)}

def getTriadMatrices(
        triadPoints:list[list[float]],
        boneAxis:Literal['x', 'y', 'z', '-x', '-y', '-z'],
        curlAxis:Literal['x', 'y', 'z', '-x', '-y', '-z'],
        curlVector:Optional[list[float]]=None, *,
        bevel:Optional[float]=None,
        inlineTolerance:float=INLINE_TOLERANCE
) -> list[list[float]]:
    """
    Generates construction matrices for a triad chain.

    :param triadPoints: three or four (bevelled) triad points
    :param boneAxis: one of 'x', 'y', 'z', '-x', '-y', '-z'
    :param curlAxis: one of 'x', 'y', 'z', '-x', '-y', '-z'
    :param curlVector: this *will* be required if the points are in-line;
        defaults to None
    :param bevel: ignored if there are already four *triadPoints*; an optional
        length to split the middle point into two; defaults to None
    :param inlineTolerance: the dot product value below which the triad will
        be considered to be in-line; defaults to the global INLINE_TOLERANCE
        constant
    :return: World-space construction matrices for a triad chain.
    """
    num = len(triadPoints)

    if num == 3:
        if bevel is None:
            triadPoints = [_data['Point'](x) for x in triadPoints]
            isBevelled = False
        else:
            triadPoints = bevelTriad(*triadPoints, bevel)
            isBevelled = True
    elif num == 4:
        triadPoints = [_data['Point'](x) for x in triadPoints]
        isBevelled = False
    else:
        raise ValueError("Expected three or four (bevelled) triad points")

    triadV0, triadV1 = getBoneVectorsFromTriadPoints(triadPoints)
    isInline = boneVectorsAreInline(triadV0, triadV1, inlineTolerance)

    if isInline:
        if curlVector is None:
            raise TriadInsufficientHintsError(
                "Insufficient hints for in-line triad"
            )
    else:
        curlVector = triadV0.cross(triadV1)

    boneVectors = [(nextPoint - thisPoint) for thisPoint, nextPoint in zip(
        triadPoints, triadPoints[1:]
    )]
    boneVectors.append(boneVectors[-1])

    matrices = [
        _mm.createOrthoMatrix(
            boneAxis, boneVector,
            curlAxis, curlVector,
            w=point
        ).pick(t=True, r=True) for boneVector, point in zip(boneVectors,
                                                            triadPoints[:-1])
    ]

    lastMatrix = matrices[-1].copy()
    lastMatrix.w = triadPoints[-1]
    matrices.append(lastMatrix)

    return matrices

def cookIKTriadSquashStretch(chain, # .skel.Chain
                             squashyAttr:'_plugs.Number',
                             stretchyAttr:'_plugs.Number',
                             globalScale:'_plugs.Number',
                             startPoint:'_plugs.Point',
                             endPoint:'_plugs.Point',
                             connect:bool=True):
    numJoints = len(chain)
    if numJoints == 3:
        isBevelled = False
    elif numJoints == 4:
        isBevelled = True
    else:
        raise ValueError("expected three or four joints")

    # Calculate native length
    _points = list(chain.points)
    _vectors = [y-x for x, y in zip(_points, _points[1:])]
    _length = sum((v.length() for v in _vectors))

    nativeLength = _length * globalScale
    chordVector = endPoint - startPoint
    targetLength = chordVector.length().gatedClamp(nativeLength,
                                                   squashyAttr,
                                                   stretchyAttr)

    if isBevelled:
        nativeBevelLength = (_points[2]-_points[1]).length() * globalScale
        factor = (targetLength
                  - nativeBevelLength) / (nativeLength
                                          - nativeBevelLength)
    else:
        factor = targetLength / nativeLength

    if connect:
        absBoneAxis = chain.detectBoneAxis().strip('-')
        chan = f's{absBoneAxis}'

        joints = chain[0], chain[2 if isBevelled else 1]

        for joint in joints:
            factor >> joint.attr(chan)

    out = {'factor': factor,
           'nativeLength': nativeLength,
           'targetLength': targetLength,
           'chordVector': chordVector}

    if isBevelled:
        out['nativeBevelLength'] = nativeBevelLength

    return out

def getTriadPeakPoint(points:Iterable['_data.Point']) -> '_data.Point':
    """
    If the triad is bevelled (four points):
        If the triad is in-line (or reverse-in-line), returns the blend of the
        bevel points
        Otherwise, returns the converged peak point
    Otherwise, returns points[1].
    """
    points, isBevelled = conformTriadPoints(points)
    if isBevelled:
        out = unbevelTriad(*points)[1]
    else:
        out = points[1]
    return out

def conformTriadPoints(points:Iterable['_data.Point']
                  ) -> tuple[list['_data.Point'], bool]:
    """
    :raises TriadPointNumberError: expected three or four points
    :return: Tuple of list-of-points, is-bevelled (bool).
    """
    points = list(map(_data.Point, points))
    numPoints = len(points)

    if numPoints == 3:
        isBevelled = False

    elif numPoints == 4:
        isBevelled = True

    else:
        raise TriadPointNumberError('expected three or four points')

    return points, isBevelled

def parseTriadCurlVectorAndPolePoint(
        points:Iterable['_data.Point'],
        polePoint:Optional['_data.Point']=None,
        curlVector:Optional['_data.Vector']=None,
        polePointDistance:Optional[float]=None
) -> tuple['_data.Vector', '_data.Point', bool]:
    """
    :param points: three or four (bevelled) points
    :param polePoint: the pole target point; if provided, it will be snapped, if
        necessary, to the resolved curl vector
    :param curlVector: the triad curl vector; ignored if the triad has a defined
        angle
    :param polePointDistance: only used if deriving a new pole point
    :raises TriadPointNumberError: expected three or four points
    :raises TriadInsufficientHintsError: insufficient hints for in-line triad
    :return: Tuple of curl vector, pole point and is-inline (bool)
    """
    # Conform givens

    points, isBevelled = conformTriadPoints(points)

    if polePoint is not None:
        polePoint = _data['Point'](polePoint)

    if curlVector is not None:
        curlVector = _data['Vector'](curlVector)

    # Resolve cross / inline

    vectors = [y-x for x, y in zip(points, points[1:])]
    cross = vectors[0].cross(vectors[-1])
    crossLen = cross.length()
    triadLen = sum((v.length() for v in vectors))

    isInline = crossLen < INLINE_TOLERANCE

    # Resolve curl vector

    chordVector = points[-1]-points[0]
    curlDerivedFromPolePoint = False

    if isInline:
        if curlVector is None:
            if polePoint is None:
                raise TriadInsufficientHintsError(
                    'insufficient hints for in-line triad'
                )
            poleVector = polePoint - points[0]
            curlVector = poleVector.cross(chordVector)
            curlDerivedFromPolePoint = True

        curlVector = curlVector.normal()
    else:
        curlVector = cross / crossLen

    # Resolve pole point

    if polePoint is None:
        if isInline:
            trajectory = chordVector.cross(curlVector).normal()
        else:
            trajectory = (vectors[0].normal()-vectors[-1].normal()).normal()

        if polePointDistance is None:
            polePointDistance = triadLen * 0.5

        triadPeakPoint = getTriadPeakPoint(points)
        trajectory = trajectory * polePointDistance
        polePoint = getTriadPeakPoint(points) + trajectory
    else:
        if not curlDerivedFromPolePoint:
            peakPoint = getTriadPeakPoint(points)
            vector = polePoint - peakPoint
            vectorLen = vector.length()

            vector = vector.rejectFrom(curlVector).normal() * vectorLen
            polePoint = peakPoint + vector

    return curlVector, polePoint, isInline