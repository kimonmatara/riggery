"""Utilities for managing mathematical triads."""

import math
from typing import Union, Optional, Iterable

from riggery.general.functions import short
from ..datatypes import __pool__ as _data
from ..plugtypes import __pool__ as _plugs
from . import mixedmode as _mm
from . import names as _nm

# The below is intended to match Maya's tolerances, which aren't particularly
# high or accurate
INLINE_TOLERANCE = 1e-6

class TriadInsufficientHintsError(ValueError):
    """
    Raised when triad framing can't be completed because the points are in-
    line and no further user hints have been provided.
    """

def bevelTriad(p0, p1, p2, length) -> tuple:
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

    return p0, b0, b1, p2

def unbevelTriad(p0, p1, p2, p3) -> tuple:
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

    plugsInPoints = any((p0IsPlug, p1IsPlug, p2IsPlug, p3IsPlug))

    v0 = p1-p0
    v1 = p3-p2

    theta = (-v1).angleTo(v0) * 0.5
    opp = (p2-p1).length() * 0.5

    if plugsInPoints:
        sinTheta = theta.sin()
    else:
        sinTheta = math.sin(theta)

    hyp = opp / sinTheta
    midpoint = p1 + (v0.normal() * hyp)

    return p0, midpoint, p3

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
    return v0.dot(v1, normalize=True) > 1.0 - inlineTolerance

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