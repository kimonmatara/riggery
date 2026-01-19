from typing import Any, Iterable, Optional, Iterator
from itertools import chain

import maya.api.OpenMaya as om

from riggery.general.functions import short
from riggery.general.numbers import remap

from . import mixedmode as _mm

from ..datatypes import __pool__ as _data
from ..plugtypes import __pool__ as plugs

#-----------------------------------------|
#-----------------------------------------|    Periodic curves
#-----------------------------------------|

# Periodic curves include an invisible extra span that overlaps the start of the
# curve to create the perfectly 'closed' continuity. This creates additional,
# internal CVs which can't be seen or manipulated in the Maya viewport.
#
# On periodic curves, Maya's API methods expect, and return, this 'expanded' CV
# list, but for higher-level manipulation you'll probably prefer to deal with
# the visible CVs instead.
#
# The general formula to add the *overlapping* segment to a list of 'visible
# only' CVs is: cvList + cvList[:degree]
#
# And, accordingly, to reverse the periodic 'padding', you do:
# cvList = cvList[:len(cvList)-degree]

def periodicToVisibleCVs(periodicCVs:Iterable[Any], degree:int) -> list[Any]:
    """
    :param periodicCVs: a CV list (indices, components, doesn't matter) of the
        length returned by the Maya API methods, which includes the periodic
        'overlap'
    :param degree: the curve degree
    :return: The CV list cropped to the visible range.
    """
    periodicCVs = list(periodicCVs)
    return periodicCVs[:len(periodicCVs)-degree]

def visibleToPeriodicCVs(visibleCVs:Iterable[Any], degree:int) -> list[Any]:
    """
    :param visibleCVs: a CV list (indices, components, doesn't matter) that only
        includes the *visible* range on a periodic curve
    :param degree: the curve degree
    :return: The CV list with the periodic overlap added to the end, as expected
        by the API functions.
    """
    visibleCVs = list(visibleCVs)
    return visibleCVs + visibleCVs[:degree]

def periodicToVisibleNumCVs(periodicNumCVs:int, degree:int) -> int:
    """
    :param periodicNumCVs: the number of CVs returned, and expected, by the
        Maya API methods on periodic curves
    :param degree: the curve degree
    :return: The number of *visible* CVs on the periodic curve.
    """
    return periodicNumCVs - degree

def visibleToPeriodicNumCVs(visibleNumCVs:int, degree:int) -> int:
    """
    :param visibleNumCVs: the number of visible CVs on a periodic curve
    :param degree: the curve degree
    :return: The internal number of CVs, as returned and expected by the API
        functions for periodic curves, including the 'overlap'.
    """
    return visibleNumCVs + degree

#-----------------------------------------|
#-----------------------------------------|    General analysis
#-----------------------------------------|

@short(degree='d',
       knotDomain='kd',
       periodic='per',
       uniform='u')
def expandDrawInfo(points:Iterable['_data.Point'], *,
                   degree:Optional[int]=None,
                   knotDomain:Optional[tuple[float, float]]=None,
                   periodic:bool=False,
                   uniform:bool=True) -> dict:
    """
    Expands basic drawing hints with expanded information expected by
    MFnNurbsCurve.create() and MFnNurbsCurve.createWithEditPoints(). Points will
    be conformed to MPoint.

    Note that, in the case of periodic curves, you may get more points returned
    than you specified; this is because periodic curves have internal
    'overlapping' CVs that the constructors expect to receive.

    :param points: the draw points; in the case of periodic curves, it's assumed
        these are strictly *visible* points, excluding the periodic overlap
    :param degree/d: the curve degree; if omitted, a 'convenient' degree will be
        selected based on the number of CVs
    :param knotDomain/kd: an optional custom knot domain
    :param periodic/per: indicate that this is for a periodic curve; defaults to
        False
    :param uniform/u: this is purely passed-through to the dict for convenience;
        it's for the EP API constructor, and defines whether parameterization
        should be uniform; defaults to True
    :return: A dictionary with these keys: points, degree, spans, rational,
        uniform, knots, is2D, form
    """
    points = list(points)
    numCVs = len(points)

    degree = resolveDegreeFromNumCVs(numCVs, degree, periodic=periodic)

    points = list(map(om.MPoint, points))

    # Normally you'll never want this, since it'll lock the curve to the 2D
    # plane
    is2D = False

    spans, knots = getSpansKnots(numCVs,
                                 degree,
                                 periodic=periodic,
                                 visibleCVs=True,
                                 knotDomain=knotDomain)

    if periodic:
        points = visibleToPeriodicCVs(points, degree)

    return {'points': points,
            'degree': degree,
            'spans': spans,
            'rational': False,
            'uniform': uniform,
            'knots': knots,
            'is2D': is2D,
            'form': 3 if periodic else 1}


@short(periodic='per')
def resolveDegreeFromNumCVs(numCVs:int,
                            degree:Optional[int]=None,
                            periodic:bool=False):
    """
    :param numCVs: the number of CVs on the curve; for periodic curves, this
        always assumes *visible* CVs
    :raises ValueError: numCVs impossible given degree and form
    :return: The resolved degree.
    """
    if numCVs < 2:
        raise ValueError("need at least 2 CVs")

    if periodic:
        if degree is None:
            if numCVs == 2:
                degree = 1
            elif numCVs >= 3:
                degree = 3
        else:
            if degree > numCVs:
                raise ValueError('degree impossible for num CVs and periodic')
    else:
        if degree is None:
            if numCVs == 2:
                degree = 1
            elif numCVs == 3:
                degree = 2
            else:
                degree = 3
        else:
            if degree > (numCVs - 1):
                raise ValueError("degree impossible for num CVs")

    return degree

@short(degree='d',
       periodic='per',
       visibleCVs='v',
       knotDomain='kd')
def getSpansKnots(
        numCVs:int,
        degree:int, *,
        periodic:bool=False,
        visibleCVs:bool=True,
        knotDomain:Optional[tuple[float, float]]=None
) -> tuple[int, list[int]]:
    """
    :param numCVs: the number of CVs
    :param degree/d: the curve degree
    :param periodic/d: whether the curve is periodic; defaults to False
    :param visibleCVs/v: ignored if *periodic* is False; if ``True``, *numCVs*
        will be taken to refer to *visible* rather than *internal* CVs; defaults
        to True
    :param knotDomain: by default, knots are returned in the 0 -> numSpans
        range; if you have a preferred min / max, enter it here to remap; on
        periodic curves, this will be taken as the 'visible' range in all cases;
        the returned knots will under- and over- shoot it to account for
        overlaps; defaults to None
    :raises ValueError: num CVs impossible given degree / form
    :return: Tuple of ``<number of spans>, <knot list>``.
    """
    if periodic:
        if not visibleCVs:
            numCVs = numCVs - degree

        if degree > numCVs:
            raise ValueError("num CVs impossible given degree / form")

        numSpans = numCVs

        internalKnotRange = list(range(numSpans + 1))
        startPadding = list(range(-(degree-1), 0))
        endPadding = list(range(numSpans + 1, numSpans + degree))

        knots = startPadding + internalKnotRange + endPadding
    else:
        numSpans = numCVs - degree

        if numSpans < 1:
            raise ValueError("num CVs impossible given degree / form")

        knots = [0] * degree + list(range(1, numSpans)) + [numSpans] * degree

    if knotDomain:
        knots = [remap(knot, 0, numSpans, knotDomain[0], knotDomain[1])
                 for knot in knots]

    return numSpans, knots

#-----------------------------------------|
#-----------------------------------------|    Beziers
#-----------------------------------------|

# Assumptions:
#     Bezier curves are always degree 3
#     Bezier curves are never periodic

def bezierSpansFromNumCVs(numCVs:int) -> int:
    return numCVs - 3

def bezierKnotsFromNumCVs(
        numCVs:int,
        knotDomain:Optional[tuple[float, float]]=None,
        spans:Optional[int]=None
) -> list[float]:
    if spans is None:
        spans = bezierSpansFromNumCVs(numCVs)

    numGroups = spans // 3 + 2

    out = list(
        map(float, chain.from_iterable([[x] * 3 for x in range(numGroups)]))
    )

    if knotDomain:
        out = [remap(x, 0, numGroups-1, knotDomain[0], knotDomain[1])
               for x in out]

    return out

def getBezierSpansKnots(
        numCVs:int, *,
        knotDomain:Optional[tuple[float, float]]=None
) -> tuple[int, list[float]]:
    spans = bezierSpansFromNumCVs(numCVs)
    knots = bezierKnotsFromNumCVs(numCVs, spans=spans, knotDomain=knotDomain)
    return spans, knots

def numCVsValidForBezier(numCVs:int) -> bool:
    """
    Assumes a degree 3 NURBS curve.

    :param numCVs: the number of CVs
    :return: True if the number of CVs can yield a clean bezier.
    """
    if numCVs >= 4:
        if (numCVs-4) % 3:
            return False
        return True
    return False

def cvIndexToAnchorIndex(cvIndex:int) -> int:
    """
    For degree 3 beziers.

    :param cvIndex: the CV index
    :return: The index of the anchor the CV belongs to.
    """
    return (cvIndex + 4) // 3 - 1

def anchorIndexToCVIndex(anchorIndex:int) -> int:
    """
    For degree 3 beziers.

    :param anchorIndex: the index of the bezier anchor
    :return: The index of the central anchor CV.
    """
    return ((anchorIndex + 2) * 3) - 6

def numCVsToNumAnchors(numCVs:int) -> int:
    """
    For degree 3 beziers.

    :param numCVs: the number of CVs
    :return: The number of bezier anchors.
    """
    return ((numCVs - 4) // 3) + 2

def numAnchorsToDefaultKnotDomain(numAnchors:int) -> tuple[float, float]:
    return 0.0, float(numAnchors - 1)

def numAnchorsToParams(
        numAnchors:int,
        knotDomain:Optional[tuple[float, float]]=None
) -> list[float]:
    """
    :param numAnchors: the number of anchors
    :param knotDomain: an optional custom knot domain
    :return: A list of parameters, one per anchor.
    """
    out = [paramAtAnchor(i, numAnchors) for i in range(numAnchors)]

    if knotDomain:
        origMin, origMax = numAnchorsToDefaultKnotDomain(numAnchors)
        out = [remap(x, origMin, origMax, knotDomain[0], knotDomain[1])
               for x in out]
    return out

def numAnchorsToNumCVs(numAnchors:int) -> int:
    """
    For degree 3 beziers.

    :param numAnchors: the number of bezier anchors
    :return: The number of CVs.
    """
    return ((numAnchors - 2) * 3) + 4

def cvsToAnchorGroups(cvs:Iterable) -> Iterator[dict]:
    """
    Yields dictionaries, where each dictionary has two or more of these keys:
    'in', 'anchor', 'out'.

    :param cvs: a list of CV indices, points, plugs, or whatever.
    :raises ValueError: Invalid number of CVs for a bezier.
    """
    out = []
    cvs = list(cvs)
    numCVs = len(cvs)
    if numCVsValidForBezier(numCVs):
        for anchorIndex in range(numCVsToNumAnchors(len(cvs))):
            bundle = {}
            origin = anchorIndexToCVIndex(anchorIndex)
            if anchorIndex > 0:
                bundle['in'] = cvs[origin-1]
            bundle['anchor'] = cvs[origin]
            try:
                bundle['out'] = cvs[origin+1]
            except IndexError:
                pass
            yield bundle
    else:
        raise ValueError("invalid number of CVs")

def anchorGroupsToCVs(anchorGroups:Iterable[dict]) -> Iterator[int]:
    """
    Unpacks the type of dictionaries yielded by :func:`cvsToAnchorGroups`.
    """
    for anchorGroup in anchorGroups:
        for key in ('in', 'anchor', 'out'):
            try:
                yield anchorGroup[key]
            except KeyError:
                pass

def paramAtAnchor(anchorIndex:int,
                  numAnchors:int, *,
                  knotDomain:Optional[tuple[float, float]]=None) -> float:
    numCVs = numAnchorsToNumCVs(numAnchors)

    spans, knots = getBezierSpansKnots(numCVs)
    out = knots[::3][anchorIndex]

    if knotDomain:
        origMin, origMax = numAnchorsToDefaultKnotDomain(numAnchors)
        out = remap(out, origMin, origMax, knotDomain[0], knotDomain[1])

    return out

def pointsToAnchorPointsAndTangents(points:Iterable[float]):
    """
    Given a flat list of bezier points, returns anchor points and anchor
    tangents.

    Note that unequal tangents aren't supported. Tangents will always be
    centered.
    """
    outAnchorPoints = []
    outAnchorTangents = []

    for anchorGroup in cvsToAnchorGroups(points):
        anchorPoint = anchorGroup['anchor']
        tanStart = anchorGroup.get('in', anchorPoint)
        tanEnd = anchorGroup.get('out', anchorPoint)
        anchorTangent = tanEnd - tanStart
        outAnchorPoints.append(anchorPoint)
        outAnchorTangents.append(anchorTangent)

    return outAnchorPoints, outAnchorTangents

def pointsAndTangentsToAnchorGroups(points, tangents) -> list[dict]:
    """
    Reorganizes a bezier specification in point + tangent format into anchor
    group format. On the first and last anchors, the full tangent length is used
    for the single-side tangent. On internal anchors, tangent lengths are halved
    to derive the in and out tangents.

    :param points: the main anchor pivot points
    :param tangents: the tangent vectors; it's assumed that tangent lengths
        are the same at either end of an anchor
    :return: A list of dictionaries with 'in', 'anchor' and 'out' keys; on the
        first anchor, the 'in' key will be omitted; on the last anchor, the
        'out' key will be omitted.
    """
    out = []
    points = list(map(_data.Point, points))
    tangents = list(map(_data.Vector, tangents))
    numAnchors = len(points)

    for i, (point, tangent) in enumerate(zip(points, tangents)):
        group = {}

        if i == 0:
            group['anchor'] = point
            group['out'] = point + tangent

        elif i == numAnchors - 1:
            group['in'] = point - tangent
            group['anchor'] = point

        else:
            halfTan = tangent * 0.5
            group['in'] = point - halfTan
            group['anchor'] = point
            group['out'] = point + halfTan

        out.append(group)

    return out

def pointsAndTangentsToPoints(points, tangents) -> list[list]:
    """
    Variant of :func:`pointsAndTangentsToAnchorGroups` that returns a flat point
    list.
    """
    out = []
    for anchorGroup in pointsAndTangentsToAnchorGroups(points, tangents):
        out += list(anchorGroup.values())
    return out

def anchorsAndTangentsFromAnchorGroups(anchorGroups:Iterable):
    """
    :return: Anchor points and tangents, in separate lists.
    """
    anchors = []
    tangents = []

    for anchorGroup in anchorGroups:
        anchor = anchorGroup['anchor']
        anchors.append(anchor)
        start = anchorGroup.get('in', anchor)
        end = anchorGroup.get('out', anchor)
        tangents.append(end-start)

    return anchors, tangents

def cvsFromAnchorSpecs(anchorSpecs):
    """
    An 'anchor spec' is a tuple of:
        anchorPoint
        anchor tangent vector
        anchor tangent length
        anchor up vector

    The tangent length is split off so that controls can still be drawn with
    correct orientation, even if they're driving a vector of zero length.

    This function flattens a list of anchor specs into a list of bezier CVs.
    """
    out = []
    num = len(anchorSpecs)
    out = []

    for i, (anchorPoint, anchorTangent, anchorLength, _) \
            in enumerate(anchorSpecs):
        anchorPoint = _data.Point(anchorPoint)
        anchorTangent = _data.Vector(anchorTangent).normal()
        anchorTangent *= anchorLength

        if i == 0:
            points = [anchorPoint, anchorPoint + anchorTangent]
        elif i == num -1:
            points = [anchorPoint - anchorTangent, anchorPoint]
        else:
            anchorTangent *= 0.5
            points = [anchorPoint - anchorTangent,
                      anchorPoint,
                      anchorPoint + anchorTangent]

        out += points
    return out

def tangentLengthToHandleLength(tangentLength):
    """
    :param tangentLength: the length of a tangent sampled from a NURBS or Bezier
        curve
    :return: The length a unified Bezier handle would need to have to produce
        this length of curve tangent.
    """
    return _mm.conform(tangentLength, _plugs['Float'])  * (2/3)

def handleLengthToTangentLength(handleLength):
    """
    :param handleLength: the length of a unified, two-sided Bezier anchor handle
    :return: The length a curve tangent would have if sampled at the anchor
        parameter driven by the Bezier anchor handle.
    """
    return _mm.conform(handleLength, _plugs['Float']) / (2/3)