"""Miscellaneous math operations."""

from typing import Optional, Generator, Union, Literal, Iterable
import math
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data
from . import mixedmode as _mm
from . import names as _nm

TOLERANCE = 1e-10

AXISVECS = {'x': (1, 0, 0),
            'y': (0, 1, 0),
            'z': (0, 0, 1),
            '-x': (-1, 0, 0),
            '-y': (0, -1, 0),
            '-z': (0, 0, -1)}

def axisLetterToVector(axis:str) -> list[float]:
    return data['Vector'](AXISVECS[axis])

def nextAxisLetter(axis1:str, axis2:str) -> str:
    """
    Uses origin-space cross products.
    """
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

    def keys(self) -> Generator[float, None, None]:
        """
        :return: The keys (positions) of the interpolator.
        """
        for k, v in self._data:
            yield k

    def values(self) -> Generator:
        """
        :return: The defined values of the interpolator.
        """
        for k, v in self._data:
            yield v

    def items(self) -> Generator[tuple, None, None]:
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