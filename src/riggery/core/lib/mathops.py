"""Miscellaneous math operations."""

from typing import Optional, Iterator, Union, Literal, Iterable
import math
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data
from . import mixedmode as _mm
from . import names as _nm
from riggery.general.numbers import floatrange

TOLERANCE = 1e-10

AXISVECS = {'x': (1, 0, 0),
            'y': (0, 1, 0),
            'z': (0, 0, 1),
            '-x': (-1, 0, 0),
            '-y': (0, -1, 0),
            '-z': (0, 0, -1)}

def axisLetterToVector(axis:str) -> list[float]:
    return data['Vector'](AXISVECS[axis])

def nextAxisLetter(axis1:str, axis2:Optional[str]=None, /) -> str:
    """
    If two axes are given, uses origin-space cross products; otherwise, simply
    returns the next axis in xyz order, with sign preserved.
    """
    if axis2 is None:
        neg = '-' in axis1
        out = 'xyz'[(('xyz'.index(axis1.strip('-')))+1) % 3]
        if neg:
            out = '-' + out
        return out
    else:
        vec1 = axisLetterToVector(axis1)
        vec2 = axisLetterToVector(axis2)
        vec3 = vec1.cross(vec2)

        return data.Matrix().closestAxis(vec3,
                                         asString=True,
                                         includeNegative=True)

def flipAxisLetter(axis:str) -> str:
    if axis.startswith('-'):
        return axis[1:]
    return '-' + axis

def idealRotateOrder(boneAxis:str, curlAxis:str) -> str:
    boneAxis = boneAxis.strip('-')
    curlAxis = curlAxis.strip('-')
    thirdAxis = [ax for ax in 'xyz' if ax not in (boneAxis, curlAxis)][0]
    return boneAxis+curlAxis+thirdAxis

def getLengthRatios(points) -> list:
    """
    .. warning::

        Value-only.

    For each point, returns a ratio from 0.0 to 1.0 representing how far along
    the chain the point is.
    """
    points = list(points)
    num = len(points)

    if num > 1:
        cumulativeLengths = [0.0]

        for thisPoint, nextPoint in zip(points, points[1:]):
            vector = nextPoint - thisPoint
            cumulativeLengths.append(cumulativeLengths[-1] + vector.length())

        fullLength = cumulativeLengths[-1]
        return [x / fullLength for x in cumulativeLengths]

    return []

def alignPoints(points, sideVector):
    """
    :param points: the points to align
    :param sideVector: an up-vector for the alignment calculations
    :return: the aligned points
    """
    points = list(map(data['Point'], points))
    sideVector = data['Vector'](sideVector)
    chordVector = points[-1]-points[0]

    mtx = data['Matrix'].createOrtho('y', chordVector,
                                     'x', sideVector,
                                     w=points[0]).pick(t=True, r=True)

    points = [point ^ mtx.inverse() for point in points]
    for point in points:
        point[0] = point[2] = 0.0
    points = [point ^ mtx for point in points]
    return points

def blendElements(a, b, weight:float):
    """
    If *a* is an iterable, assumes that *a* and *b* are both iterables of the
    same length, and performs elementwise blending, matching the output type to
    *a*. Otherwise, performs simple scalar blending.

    :param a: the base value
    :param b: the value towards which to blend
    :param weight: a float between 0.0 to 1.0, representing how closely the
        output should match *b*
    """
    try:
        a = [float(member) for member in a]
        b = [float(member) for member in b]
        isIter = True
    except TypeError:
        a = float(a)
        b = float(b)
        isIter = False

    if isIter:
        T = type(a)
        return T([(_a + ((_b - _a) * weight)) for _a, _b in zip(a, b)])

    return a + ((b-a) * weight)

class Interpolator:
    """
    Simple linear interpolator. Works with scalars or vector-like iterables
    (for consistent results, maintain input length and type).

    .. code-block:: python

        interp = Interpolator()
        interp[0.0] = Vector([1, 2, 3])
        interp[10.0] = Vector([20, 40, 5])

        print(interp[5.0])
        # [10.5, 21.0, 4.0]
    """

    #-----------------------------------------|    Inst

    @classmethod
    def fromPairs(cls, pairs):
        inst = cls()
        for k, v in pairs:
            inst[k] = v
        return inst

    @classmethod
    def fromDict(cls, d:dict):
        return cls.fromPairs(d.items())

    def __init__(self):
        self._data = []

    #-----------------------------------------|    Get

    @property
    def __len__(self):
        return self._data.__len__

    @property
    def __bool__(self):
        return self._data.__bool__

    def _indexFromPosition(self, position:float) -> int:
        """
        :raises IndexError:
        """
        for i, p in enumerate(self.keys()):
            if math.isclose(p, position, rel_tol=TOLERANCE):
                return i
        raise IndexError

    def keys(self) -> Iterator[float]:
        """
        :return: The keys (positions) of the interpolator.
        """
        for k, v in self._data:
            yield k

    def values(self) -> Iterator:
        """
        :return: The defined values of the interpolator.
        """
        for k, v in self._data:
            yield v

    def items(self) -> Iterator[tuple]:
        """
        :return: Pairs of defined positions and values.
        """
        for k, v in self._data:
            yield k, v

    __iter__ = items

    #-----------------------------------------|    Set

    def __setitem__(self, position:Union[float, int], value):
        try:
            self._data[self._indexFromPosition(position)] = (position, value)
        except IndexError:
            self._data.append((position, value))
            self._data.sort(key=lambda pair: pair[0])

    #-----------------------------------------|    Get

    def getKeyframeAtOrBefore(self, samplePosition:float) -> Optional[tuple]:
        for k, v in reversed(list(self.items())):
            if k <= samplePosition:
                return k, v

    def getKeyframeAtOrAfter(self, samplePosition:float) -> Optional[tuple]:
        for k, v in self.items():
            if k >= samplePosition:
                return k, v

    def __getitem__(self, samplePosition:float):
        prevKeyframe = self.getKeyframeAtOrBefore(samplePosition)
        nextKeyframe = self.getKeyframeAtOrAfter(samplePosition)

        if prevKeyframe is None:
            if nextKeyframe is None:
                raise ValueError("empty interpolator")
            return nextKeyframe[1]
        elif nextKeyframe is None:
            return prevKeyframe[1]

        if prevKeyframe[0] == nextKeyframe[0]:
            return prevKeyframe[1]

        prevPosition, nextPosition = prevKeyframe[0], nextKeyframe[0]

        localRatio = (samplePosition-prevPosition) / (nextPosition-prevPosition)

        prevValue, nextValue = prevKeyframe[1], nextKeyframe[1]
        return blendElements(prevValue, nextValue, localRatio)

    #-----------------------------------------|    Repr

    def __repr__(self):
        return f"{type(self).__name__}({repr(self._data)}"

def getBoneAxisFromMatrices(matrices) -> str:
    """
    :param matrices: matrices in a chain-like arrangement
    :return: The most common bone-facing axis, as a string (e.g. '-y').
    """
    if len(matrices) < 2:
        raise ValueError("expected at least 2 matrices")
    matrices = list(map(data['Matrix'], matrices))
    points = [matrix.w for matrix in matrices]
    vectors = ((p2-p1) for p1, p2 in zip(points, points[1:]))

    axes = []

    for vector, matrix in zip(vectors, matrices[:-1]):
        axes.append(matrix.closestAxis(vector,
                                       includeNegative=True,
                                       asString=True))

    axes = list(sorted(axes, key=lambda axis: axes.count(axis)))
    return axes[-1]

def aimMatrices(matrices:Iterable,
                aimAxis:str,
                upAxis:str,
                aimLast:bool=True) -> list:
    """
    Aims a sequence of matrices to each other. The end matrix will re-use the
    last aim vector. Up vectors will be derived from the matrices themselves
    using *aimAxis*.

    :param matrices: the matrices to aim
    :param aimAxis: the axis to align to the aiming vector
    :param upAxis: the axis to extract from the matrices as an up vector
    :param aimLast: if this is False, the last matrix will be passed-through
        as-is; defaults to False
    :return: The aimed matrices.
    """
    matrices = [_mm.info(matrix)[0] for matrix in matrices]

    out = []

    points = [matrix.w for matrix in matrices]
    aimVectors = [nextPoint - thisPoint
                  for thisPoint, nextPoint in zip(points, points[1:])]
    upVectors = [matrix.getAxis(upAxis) for matrix in matrices]

    for i, (matrix, point, aimVector, upVector) in enumerate(
            zip(matrices[:-1], points[:-1], aimVectors, upVectors[:-1])
    ):
        matrix = matrix.asScaleMatrix() * _mm.createOrthoMatrix(
            aimAxis, aimVector,
            upAxis, upVector,
            w=point
        ).pick(t=True, r=True)
        out.append(matrix)

    if aimLast:
        endMatrix = out[-1].pick(r=True,
                                 s=True) * points[-1].asTranslateMatrix()
    else:
        endMatrix = matrices[-1]

    out.append(endMatrix)
    return out

def globaliseMatrixChain(matrices, parentMatrix=None):
    """
    Given a bunch of hierarchical, but local, matrices (e.g. 'matrix' attributes
    on a joint chain), returns the world matrices.

    :param matrices: the matrices to globalise
    :param parentMatrix: a parent matrix to globalise the first matrix in the
        chain; defaults to None
    """
    if parentMatrix is not None:
        parentMatrix = _mm.info(parentMatrix)[0]

    matrices = [_mm.info(matrix)[0] for matrix in matrices]
    out = []

    for i, matrix in enumerate(matrices):
        if i == 0:
            if parentMatrix is not None:
                matrix *= parentMatrix
            out.append(matrix)
        else:
            out.append(matrix * out[-1])

    return out

def localiseMatrixChain(matrices, parentMatrix=None):
    """
    Given a bunch of hierarchical, but world-space, matrices (e.g. 'worldMatrix'
    attributes on a joint chain), derives local matrices.

    :param matrices: the matrices to localise
    :param parentMatrix: a parent matrix to localise the first matrix in the
        chain; defaults to None
    :return:
    """
    if parentMatrix is not None:
        parentMatrix = _mm.info(parentMatrix)[0]

    matrices = [_mm.info(matrix)[0] for matrix in matrices]
    out = []
    for i, matrix in enumerate(matrices):
        if i == 0:
            if parentMatrix is not None:
                matrix *= parentMatrix.inverse()
            out.append(matrix)
        else:
            out.append(matrix * matrices[i-1].inverse())
    return out

def getLengthFromPoints(points):
    """
    This is kind wasteful if working from plugs. Pulls vectors between the
    points and returns the sum of their magnitudes.

    :param points: the points; can be plugs or values
    :return: The total length of the vectors between the points.
    """
    infos = list(map(_mm.info, points))
    hasPlugs = any((info[2] for info in infos))
    points = [info[0] for info in infos]

    vectors = [nextPoint-thisPoint for thisPoint, nextPoint in zip(
        points, points[1:]
    )]

    lengths = [vector.length() for vector in vectors]

    if hasPlugs:
        node = nodes['Sum'].createNode()
        for i, length in enumerate(lengths):
            node.attr('input')[i].put(length)
        return node.attr('output')

    return sum(lengths)

def calcMatrixChainBaseVectors(
        points,
        refVector
) -> tuple[list[tuple[list[float], list[float]]], bool]:
    """
    Returns bone vector, up vector pairs for a chain. The last member will be
    a duplicate of the penultimate member.

    :param points: the chain points, including tip
    :param refVector: a reference curl vector; if the points are in-line, this
        will be used wholesale; otherwise, it will be used to bias cross product
        vectors

    :raises ValueError: Need two or more points.
    :return: A tuple comprising two members. The first member will be a list of
        (bone vector, up vector) pairs, the last of which will be a duplicate.
        The second member will be True if the chain was in-line, otherwise
        False.
    """
    #---------------------|    Wrangle args

    points = [data['Point'](point) for point in points]
    refVector = data['Vector'](refVector)

    #---------------------|    Prep

    numPoints = len(points)

    if numPoints < 2:
        raise ValueError("need two or more points")

    vectors = [(nextPoint-thisPoint)
               for thisPoint, nextPoint in zip(points, points[1:])]
    ratios = getLengthRatios(points)

    #---------------------|    Calc cross product keys

    perRatioCrosses = {}
    lastCross = None

    for i, (thisVector, nextVector) \
            in enumerate(zip(vectors, vectors[1:])):
        cross = thisVector.cross(nextVector)

        mag = cross.length()

        if mag < TOLERANCE:
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
        interp = Interpolator.fromDict(perRatioCrosses)
        upVectors = [data['Vector'](interp[ratio])
                     for ratio in ratios]

    else:
        upVectors = list(perRatioCrosses.values())
        upVectors.insert(0, upVectors[0])
        upVectors.append(upVectors[-1])

    #---------------------|    Zip and return

    vectors.append(vectors[-1]) # tip
    return list(zip(vectors, upVectors)), inline

def calcChainMatrices(
        points:list[list[float]],
        refVector:list[float],
        boneAxis:Literal['x', 'y', 'z', '-x', '-y', '-z'],
        curlAxis:Literal['x', 'y', 'z', '-x', '-y', '-z']
) -> list[list[float]]:
    """
    :param points: the chain points, including tip
    :param refVector: a reference curl vector; if the points are in-line, this
        will be used wholesale; otherwise, it will be used to bias cross product
        vectors
    :raises ValueError: Need two or more points.
    :return: A list of matrices suitable for drawing, say, joint chains.
    """
    boneVectors, upVectors = zip(
        *calcMatrixChainBaseVectors(points, refVector)[0]
    )
    Matrix = data['Matrix']
    return [Matrix.createOrtho(boneAxis, boneVector,
                               curlAxis, upVector,
                               w=point).pick(t=True, r=True)
            for boneVector, upVector, point in zip(boneVectors,
                                                   upVectors,
                                                   points)]

# Bezier tangent length to get a quadrant of a unit circle
BEZIER_CIRCLE_CONSTANT = (4/3) * ((2 ** 0.5)-1)
# Bezier tangent length for a given arc radius
# kappa = (4/3) * tan(arc_angle / 4)
# handle_length = radius * kappa

def bezierInterp(points, u):
    """
    Performs bezier interpolation.

    :param points: three (quadratic) or four (cubic) points to define the bezier
        curve
    :param u: the parameter at which to sample a point
    :return: The sampled point.
    """
    num = len(points)
    if num not in (3, 4):
        raise ValueError("Need three or four points.")
    points = list(map(
        lambda x: _mm.conform(x, (data.Point, plugs.Point)),
        points
    ))
    u = _mm.conform(u, (float, plugs.Number))

    for i in range(num-1):
        interpolated = []

        for p0, p1 in zip(points, points[1:]):
            vec = p1 - p0
            newPoint = p0 + (vec * u)
            interpolated.append(newPoint)

        points = interpolated

    return points[0]

def guessApproxBezierSegmentLength(p0, p1, p2, p3, steps:int=50) -> float:
    """
    :param steps: The number of measuring passes; this is Python, so bring this
        down if you just want a very general approximation; defaults to 50
    :return: The approximate length of the cubic bezier curve segment defined by
    the specified four points. Does not create any Maya nodes.
    """
    totalLength = 0.0
    prevPoint = p0

    p0, p1, p2, p3 = map(data.Point, (p0, p1, p2, p3))

    for i in range(1, steps + 1):
        u = i / steps
        currentPoint = bezierInterp((p0, p1, p2, p3), u)

        # Add the length of the current segment
        segmentLength = (currentPoint - prevPoint).length()
        totalLength += segmentLength
        prevPoint = currentPoint

    return totalLength

def vectorFromLineToPoint(
        refPoint:Union[str, list[float], 'plugs.Point'],
        lineStart:Union[str, list[float], 'plugs.Point'],
        lineVector:Union[str, list[float], 'plugs.Vector']
) -> Union['data.Vector', 'plugs.Vector']:
    """
    :param refPoint: the reference point
    :param lineStart: the start point of the line
    :param lineVector: the line vector
    :return: The vector from the closest point on *lineStart* to reference
        point *refPoint*.
    """
    pointOnLine = closestPointOnLine(refPoint, lineStart, lineVector)
    refPoint = _mm.conform(refPoint, (plugs.Point, data.Point), force=True)
    return refPoint - pointOnLine

def distanceFromLine(
        refPoint:Union[str, list[float], 'plugs.Point'],
        lineStart:Union[str, list[float], 'plugs.Point'],
        lineVector:Union[str, list[float], 'plugs.Vector']
) -> Union[float, 'plugs.Float']:
    """
    :param refPoint: the reference point
    :param lineStart: the start point of the line
    :param lineVector: the line vector
    :return: The distance between *refPoint* and the closest point on the line.
        The calculation is *not* clamped to the line segment ends.
    """
    return vectorFromLineToPoint(refPoint, lineStart, lineVector).length()

def closestPointOnLine(refPoint:Union[list[float], str, 'plugs.Point'],
                       lineStart:Union[list[float], str, 'plugs.Point'],
                       lineVector:Union[list[float], str, 'plugs.Vector'],
                       clamp:bool=False) -> Union['data.Point', 'plugs.Point']:
    """
    :param refPoint: the reference point
    :param lineStart: the start point of the line
    :param lineVector: the line vector
    :param clamp: keep the output point within the bounds of the line; defaults
        to False
    :return: The point on the line segment that falls closest to *refPoint*.
    """
    refPoint, _, refIsPlug = _mm.info(refPoint,
                                      (data.Point, plugs.Point),
                                      force=True)

    lineStart, _, lineStartIsPlug = _mm.info(lineStart,
                                             (data.Point, plugs.Point),
                                             force=True)

    lineVector, _, lineVectorIsPlug = _mm.info(lineVector,
                                               (data.Vector, plugs.Vector),
                                               force=True)

    hasPlugs = any((refIsPlug, lineStartIsPlug, lineVectorIsPlug))

    refVector = refPoint - lineStart
    projectedVector = refVector.projectOnto(lineVector)

    if clamp:
        projectedLength = projectedVector.length()
        lineLength = lineVector.length()
        dot = lineVector.dot(projectedVector)

        if hasPlugs:
            projectedVector = (projectedLength > lineLength).ifElse(
                lineVector,
                projectedVector,
                plugs.Vector
            )

            outPoint = lineStart + projectedVector

            outPoint = (dot < 0.0).ifElse(lineStart,
                                          outPoint,
                                          plugs.Point)
        else:
            if projectedLength > lineLength:
                projectedVector = lineVector

            outPoint = lineStart + projectedVector

            if dot < 0.0:
                outPoint = lineStart
    else:
        outPoint = lineStart + projectedVector

    return outPoint

def getPoleVector(
        chainPoints:list[Union[str, list[float], 'plugs.Point']],
) -> dict:
    """
    Suitable for chains of arbitrary length.

    :return: A dictionary with piecemeal calculations. Grab 'poleVector' for
        the definitive output. No in-line checking is performed; the pole vector
        may be zero-length.
    """
    pointInfos = [_mm.info(x, (data.Point, plugs.Point), force=True)
                  for x in chainPoints]

    num = len(pointInfos)

    if num < 2:
        raise ValueError("need at least 3 points")

    points = [x[0] for x in pointInfos]
    hasPlugs = any((x[2] for x in pointInfos))

    startPoint = points[0]
    endPoint = points[-1]

    chordVector = endPoint - startPoint

    if hasPlugs:
        outDistance = None
        outPoleVector = None

        for innerPoint in points[1:-1]:
            closestPoint = closestPointOnLine(innerPoint,
                                              startPoint,
                                              chordVector)
            thisPoleVector = innerPoint - closestPoint
            thisDistance = thisPoleVector.length()

            if outPoleVector is None:
                outPoleVector = thisPoleVector
                outDistance = thisDistance
            else:
                thisIsGreater = thisDistance > outDistance

                outPoleVector = thisIsGreater.ifElse(
                    thisPoleVector,
                    outPoleVector,
                    plugs.Vector
                )

                outDistance = thisIsGreater.ifElse(
                    thisDistance,
                    outDistance,
                    plugs.Number
                )
    else:
        bestDistance = None
        bestPoleVector = None

        for innerPoint in points[1:-1]:
            thisPoleVector = vectorFromLineToPoint(innerPoint,
                                                   startPoint,
                                                   chordVector)
            thisLength = thisPoleVector.length()

            if bestDistance is None or thisLength > bestDistance:
                bestDistance = thisLength
                bestPoleVector = thisPoleVector

        outPoleVector = bestPoleVector

    return {'poleVector': outPoleVector,
            'chordVector': chordVector,
            'points': points}

def intersectVectorsPlugs(p1:'plugs.Point',
                          v1:'plugs.Vector',
                          p2:'plugs.Point',
                          v2:'plugs.Vector') -> 'plugs.Point':
    """
    :param p1: the origin of the first line segment
    :param v1: the direction of the first line segment
    :param p2: the origin of the second line segment
    :param v2: the direction of the second line segment
    """
    p1 = _mm.conform(p1, (plugs.Point, data.Point), force=True)
    p2 = _mm.conform(p2, (plugs.Point, data.Point), force=True)
    v1 = _mm.conform(v1, (plugs.Vector, data.Vector), force=True)
    v2 = _mm.conform(v2, (plugs.Vector, data.Vector), force=True)

    w = p1 - p2

    a = v1.dot(v1)
    b = v1.dot(v2)
    c = v2.dot(v2)
    d = v1.dot(w)
    e = v2.dot(w)

    denom = (a * c) - (b * b)

    t = (b * e - c * d) / denom
    s = (a * e - b * d) / denom

    pointA = p1 + t * v1
    pointB = p2 + s * v2

    return (pointA + pointB) / 2

def intersectLinesValues(p1, p2, p3, p4, tolerance:float=1e-6) -> 'data.Point':
    """
    Assumes infinite lines. Only works with values (not plugs).
    """
    p1, p2, p3, p4 = map(data['Point'], (p1, p2, p3, p4))

    # Direction vectors
    d1 = p2 - p1
    d2 = p4 - p3

    # Vector between line start points
    w = p1 - p3

    # Params for closest points
    a = d1.dot(d1)
    b = d1.dot(d2)
    c = d2.dot(d2)
    d = d1.dot(w)
    e = d2.dot(w)

    denom = a*c - b*b

    if abs(denom) < tolerance: # parallel
        return None

    s = (b*e - c*d) / denom
    t = (a*e - b*d) / denom

    point1 = p1 + d1 * s
    point2 = p3 + d2 * t

    # Check if they actually intersect (not skew)
    if (point2 - point1).length() > tolerance:
        return None

    return point1

def splitBias(bias,
              minRange:_mm.MixedScalar,
              maxRange:_mm.MixedScalar
              ) -> tuple[_mm.MixedScalar, _mm.MixedScalar]:
    """
    Returns two weights, (both in the 0 -> 1 range). The first weight represents
    the deviation of *bias* towards *minRange*. The second weight represents the
    deviation of *bias* towards *maxRange*.

    In other words, if *bias* is at the exact midpoint between *minRange* and
    *maxRange*, the output weights will be 0.5, 0.5. If *bias* is at *maxRange*,
    the weights will be 0.0, 1.0.
    """
    ratio = (bias - minRange) / (maxRange - minRange)
    return 1 - ratio, ratio

def normalizeWeights(weights:Iterable[_mm.MixedScalar],
                     ) -> Union[list[float], list[plugs['Float']]]:
    """
    Normalizes all the weights into the 0.0 -> 1.0 range. If all the weights
    are at zero, sets them all to 1.0.

    If there are any plugs in *weights*, the output will be a list of plugs.
    Otherwise, the output will be a list of floats.
    """
    weightInfo = [_mm.info(weight) for weight in weights]
    num = len(weightInfo)
    weights = [x[0] for x in weightInfo]
    hasPlugs = any((x[2] for x in weightInfo))

    if hasPlugs:
        total = weights[0].sum(*weights[1:])

        with _nm.Name('patchbay'):
            pb = nodes['Network'].createNode()
            one = pb.addAttr('one', k=1, dv=1, l=True, at='double')

        atZero = total < 1e-4

        return [atZero.ifElse(1 / num, w / total, plugs['Float'])
                for w in weights]

    total = sum(weights)

    if total <= 0.0:
        return [1 / num] * num

    return [x / total for x in weights]

def parallelTransport(
        startNormal:Union['data.Vector', 'plugs.Vector'],
        tangents:Iterable[Union['data.Vector', 'plugs.Vector']],
        endNormal:Optional[Union['data.Vector', 'plugs.Vector']]=None, *,
        useRawStartNormal:bool=False,
        useRawEndNormal:bool=False
) -> list[Union['data.Vector'], 'plugs.Vector']:
    """
    Robust parallel transport solver with optional twist functionality. Do not
    pass ``True`` for *useRawStartNormal* or *useRawEndNormal* unless you know
    what you're doing.

    :param startNormalHint: the normal to transport; this NOT expected to be
        perpendicular to the first tangent
    :param tangents: the tangents along which to transport the normal
    :param endNormalHint: if this is provided, it will be used to distribute the
        angle delta backwards; dfaults to None
    :param useRawStartNormal: when this is True, the provided *startNormal* will
        be used as-is for parallel transport, and will not be transported to the
        first tangent (if the first tangent is a plug) or perpendicularized
        against it; defaults to False
    :param useRawEndNormal: when this is True, the provided *endNormal* will be
        used as-is for parallel transport, and will not be perpendicularized
        against the last tangent; defaults to False
    :return: One normal vector per tangent.
    """
    #----------------|    Conform input arguments

    startNormal, _, startNormalIsPlug = _mm.info(startNormal,
                                                 (data['Vector'],
                                                  plugs['Vector']),
                                                 force=True)

    tangentInfos = [_mm.info(tangent,
                             (data['Vector'], plugs['Vector']),
                             force=True)
                    for tangent in tangents]

    tangents = [tangentInfo[0] for tangentInfo in tangentInfos]

    numTangents = len(tangentInfos)

    if numTangents == 0:
        raise ValueError("no tangents provided")

    if endNormal is not None:
        endNormal, _, endNormalIsPlug = _mm.info(endNormal,
                                                 (data['Vector'],
                                                  plugs['Vector']),
                                                 force=True)

    #----------------|    Resolve start normal hint

    startTangent, _, startTangentIsPlug = tangentInfos[0]

    if not useRawStartNormal:
        if startTangentIsPlug:
            _startTangent = startTangent()
            startNormal *= _startTangent.quatTo(startTangent)

        startNormal = startNormal.rejectFrom(startTangent)

    #----------------|    Resolve end normal hint

    if endNormal is not None:
        # The end normal should not be 'transported' in the same way as the
        # start normal for initialization; the semantics are different at the
        # end of the curve; transporting the end hint would twist it in
        # unhelpful ways
        endTangent, _, _ = tangentInfos[-1]

        if not useRawEndNormal:
            endNormal = endNormal.rejectFrom(endTangent)

    #----------------|    Transport

    if numTangents > 1:
        normals = [startNormal]

        for thisTangent, nextTangent in zip(tangents[:-1], tangents[1:]):
            thisQuat = thisTangent.quatTo(nextTangent)
            thisNormal = normals[-1] * thisQuat
            normals.append(thisNormal)

        if endNormal is not None:
            angle = normals[-1].angleTo(endNormal, tangents[-1], shortest=True)
            tweenRatios = list(floatrange(0, 1, numTangents+2))[1:-1]

            normals = ([startNormal]
                       + [normal.rotateByAxisAngle(tangent, angle * x)
                          for normal, tangent, x in zip(normals[1:-1],
                                                        tangents[1:-1],
                                                        tweenRatios)]
                       + [endNormal])

        return normals

    return [startNormal]