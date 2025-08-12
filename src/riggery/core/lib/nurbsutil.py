"""NURBS utilities."""
from typing import Literal, Union, Iterable, Generator
from ..datatypes import __pool__ as _data
from ..plugtypes import __pool__ as _plugs
from . import mixedmode as _mm

FORM = {'open': 1, 'closed': 2, 'periodic': 3}
revFORM = {v: k for k, v in FORM.items()}

def resolveForm(form:Union[str, int]) -> int:
    """
    :param form: One of:
        1 or 'open'
        2 or 'closed'
        3 of 'periodic'
    :return: The user argument, conformed to an index matching an enum on
        :class:`~maya.api.OpenMaya.MFnNurbsCurve` as as ``kClosed``.
    """
    if isinstance(form, str):
        return {'open': 1, 'closed': 2, 'periodic': 3}[form]
    return form

def getSpansKnots(numCVs:int, degree:int) -> tuple[int, list[int]]:
    """
    :param numCVs: The target number of CVs.
    :param degree: The target curve degree.
    :raises ValueError: The number of CVs is impossible given the target
        degree.
    :return: A tuple of <number of spans>, <knot list>
    """
    numSpans = numCVs - degree
    if numSpans < 1:
        raise ValueError("num CVs impossible given degree / form")
    knots = [0] * degree + list(range(1, numSpans)) + [numSpans] * degree
    return numSpans, knots

def getBezierSpansKnots(numCVs:int) -> tuple[int, list[int]]:
    """
    Variant of :func:`getSpansKnots` appropriate for bezier curves, where the
    knot list is different.

    :param numCVs: The target number of CVs.
    :return: A tuple of <number of spans>, <knot list>.
    """
    numAnchors = numCVsToNumAnchors(numCVs)
    knots = [0, 0, 0]
    for i in range(1, numAnchors-1):
        knots += [i] * 3
    knots += [numAnchors-1] * 3
    return numAnchors + 1, knots

def clampDegree(numCVs:int, degree:int) -> int:
    """
    Returns *degree*, or the maximum degree that can produce the given number
    of CVs, whichever is lowest.

    :raises ValueError: *numCVs* is 1 or less.
    """
    if numCVs < 2:
        raise ValueError("need at least two CVs")
    return min(degree, numCVs-1)

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

def numAnchorsToParams(numAnchors:int) -> list[float]:
    """
    .. note::

        This is a pure projection. Results may be wrong for your curve if it has
        a non-default knot domain.

    :param numAnchors: the number of anchors
    :return: A list of parameters, one per anchor.
    """
    return [paramAtAnchor(i, numAnchors) for i in range(numAnchors)]

def numAnchorsToNumCVs(numAnchors:int) -> int:
    """
    For degree 3 beziers.

    :param numAnchors: the number of bezier anchors
    :return: The number of CVs.
    """
    return ((numAnchors - 2) * 3) + 4

def cvsToAnchorGroups(cvs:Iterable) -> Generator[dict, None, None]:
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

def anchorGroupsToCVs(anchorGroups:Iterable[dict]
                      ) -> Generator[int, None, None]:
    """
    Unpacks the type of dictionaries yielded by :func:`cvsToAnchorGroups`.
    """
    for anchorGroup in anchorGroups:
        for key in ('in', 'anchor', 'out'):
            try:
                yield anchorGroup[key]
            except KeyError:
                pass

def paramAtAnchor(anchorIndex:int, numAnchors:int) -> float:
    """
    This is pure projection, may be wrong if the bezier curve you're working
    with is parameterized in a non-default way.
    """
    numCVs = numAnchorsToNumCVs(numAnchors)
    spans, knots = getBezierSpansKnots(numCVs)
    return knots[::3][anchorIndex]

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