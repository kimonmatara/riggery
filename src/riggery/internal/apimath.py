from typing import Optional, Literal, Union
import maya.cmds as m
import maya.api.OpenMaya as om
from riggery.general.iterables import expand_tuples_lists

#-----------------------------------------|
#-----------------------------------------|    CONSTANTS
#-----------------------------------------|

AXISVECS = {'x': om.MVector([1, 0, 0]),
            'y': om.MVector([0, 1, 0]),
            'z': om.MVector([0, 0, 1]),
            '-x': om.MVector([-1, 0, 0]),
            '-y': om.MVector([0, -1, 0]),
            '-z': om.MVector([0, 0, -1])}

BBOX_UNIT_DIAGONAL = 1.7320508075688772

#-----------------------------------------|
#-----------------------------------------|    MATRIX UTILITIES
#-----------------------------------------|

def setMatrixAxis(matrix:om.MMatrix,
                  axis:Literal['x', 'y', 'z', '-x', '-y', '-z', 'w'],
                  vector:Union[om.MVector, om.MPoint, list[float]]) -> None:
    vector = om.MVector(vector)

    if '-' in axis:
        axis = axis.strip('-')
        vector *= -1.0

    row = 'xyzw'.index(axis)
    for col, value in zip(range(3), vector):
        matrix.setElement(row, col, value)

def testMatrix(matrix:Union[list[float], om.MMatrix], name=None):
    kwargs = {}
    if name is not None:
        kwargs['name'] = name
    loc = m.spaceLocator(**kwargs)[0]
    m.xform(loc, matrix=list(matrix))
    m.setAttr(f"{loc}.displayLocalAxis", True)
    return loc

def createOrthoMatrix(
        aimAxis:Literal['x', 'y', 'z', '-x', '-y', '-z'],
        aimVector:Union[list[float], om.MVector],
        upAxis:Literal['x', 'y', 'z', '-x', '-y', '-z'],
        upVector:Union[list[float], om.MVector],
        w:Optional[Union[list[float], om.MPoint]]=None) -> om.MMatrix:
    """
    Creates an orthogonal matrix using two vectors.
    """
    aimVector = om.MVector(aimVector)
    upVector = om.MVector(upVector)

    if w is not None:
        w = om.MPoint(w)

    swapAim = '-' in aimAxis
    aimAxis = aimAxis.lower().strip('-')

    swapUp = '-' in upAxis
    upAxis = upAxis.lower().strip('-')

    if aimAxis == upAxis:
        raise ValueError("Aim axis same as up axis")

    consec = aimAxis + upAxis in 'xyzxy'

    if swapAim:
        aimVector *= -1.0

    if swapUp:
        upVector *= -1.0

    if consec:
        thirdVector = aimVector ^ upVector
        upVector = thirdVector ^ aimVector
    else:
        thirdVector = upVector ^ aimVector
        upVector = aimVector ^ thirdVector

    thirdAxis = [ax for ax in 'xyz' if ax not in aimAxis+upAxis][0]
    out = om.MMatrix()

    setMatrixAxis(out, aimAxis, aimVector)
    setMatrixAxis(out, upAxis, upVector)
    setMatrixAxis(out, thirdAxis, thirdVector)

    if w is not None:
        setMatrixAxis(out, 'w', w)

    return out

#-----------------------------------------|
#-----------------------------------------|    POINT WRANGLER
#-----------------------------------------|

class PointWrangler(list):
    """
    Convenience list subclass; applies transformations to points.
    """

    #-----------------------------|    Init

    def __init__(self, *args):
        super().__init__(*args)
        self[:] = map(om.MPoint, self)

    #-----------------------------|    Conversions

    def simple(self) -> list[list[float]]:
        """
        :return: A simplified list where each point is a list of three floats.
        """
        return [list(x)[:3] for x in self]

    #-----------------------------|    Transformations

    def applyMatrix(self, matrix:Union[list[float], om.MMatrix]):
        matrix = om.MMatrix(matrix)
        self[:] = [x * matrix for x in self]
        return self

    def translate(self, translation:list[float]):
        matrix = om.MTransformationMatrix()
        matrix.setTranslation(om.MPoint(translation), om.MSpace.kTransform)
        return self.applyMatrix(matrix.asMatrix())

    def rotate(self, euler:list[float]):
        matrix = om.MTransformationMatrix()
        matrix.setRotation(om.MEulerRotation(euler))
        return self.applyMatrix(matrix.asMatrix())

    def scale(self, scale:Union[float, int, list[float]]):
        if isinstance(scale, (float, int)):
            scale = [scale] * 3

        matrix = om.MTransformationMatrix()
        matrix.setScale(om.MVector(scale), om.MSpace.kTransform)
        return self.applyMatrix(matrix.asMatrix())

    def axisRemap(self, *axes:Union[str, list[str]]):
        """
        :param \*axes: two (e.g. 'x', 'y') or four (e.g. 'x', 'y', 'z', 'x')
            letter axes, indicating how to construct the orthogonal remapping
            matrix
        """
        axes = expand_tuples_lists(*axes)
        num = len(axes)
        if num not in (2, 4):
            raise ValueError("expected two or four arguments")

        if num == 2:
            thirdAxis = [ax for ax in 'xyz' \
                         if ax not in (axes[0].strip('-'),
                                       axes[1].strip('-'))][0]
            axes = list(axes) + [thirdAxis, thirdAxis]

        remapMatrix = createOrthoMatrix(axes[0], AXISVECS[axes[1]],
                                        axes[2], AXISVECS[axes[3]])
        return self.applyMatrix(remapMatrix)

    def normalizeBoundingBox(self):
        bbox = om.MBoundingBox()
        for point in self:
            bbox.expand(point)
        diagonalVector = bbox.max - bbox.min
        diagonalLength = diagonalVector.length()
        correction = BBOX_UNIT_DIAGONAL / diagonalLength

        factors = [correction] * 3
        return self.scale(factors)

    #-----------------------------|    Repr

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, super().__repr__())