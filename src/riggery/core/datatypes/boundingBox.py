from typing import Optional, Union

import maya.api.OpenMaya as om
import maya.cmds as m

from ..elem import Elem
from riggery.general.functions import short
from ..lib.nativeunits import nativeunits
from ..lib import names as _nm
from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes


class BoundingBox(data['Tensor']):

    __shape__ = 6
    __apicls__ = om.MBoundingBox

    #-----------------------------------------|    Constructor(s)

    @classmethod
    def createAsUnitCube(cls) -> 'BoundingBox':
        """
        :return: A 1X1 bounding box centered around the origin.
        """
        return cls([-0.5]*3 + [0.5]*3)

    @classmethod
    @short(calculateExactly='ce')
    def createFromObjects(cls,
                          objects:list,
                          calculateExactly:bool=False) -> 'BoundingBox':
        """
        :param objects: the objects to encapsulate, in a list
        :param calculateExactly/ce: makes everything betterer; defaults to
            False
        :return: The bounding box.
        """
        bbox = om.MBoundingBox()
        for object in objects:
            worldPosition = Elem(object).getPosition(worldSpace=True)
            bbox.expand(om.MPoint(worldPosition))

        return cls.fromApi(bbox)

    @classmethod
    def createFromPoints(cls, points:list) -> 'BoundingBox':
        """
        :param points: the points to contain
        :return: A BBox that can contain all of the specified points.
        """
        return cls().expandToPoints(points)

    @classmethod
    def fromApi(cls, value:om.MBoundingBox, **kwargs):
        values = list(value.min)[:3] + list(value.max)[:3]
        return cls.fromIter(values, **kwargs)

    #-----------------------------------------|    Testing

    @nativeunits
    def drawCurve(self, name:Optional[str]=None):
        """
        :param name/n: an optional name override for the curve
        :return: A curve outlining the bounding box, for visualization
            purposes. The transform is returned.
        """
        leftBottomBack, rightBottomBack, rightBottomFront, \
        leftBottomFront, leftTopFront, leftTopBack, rightTopBack, \
        rightTopFront = self.corners

        points = [
            leftBottomBack,
            rightBottomBack,
            rightBottomFront,
            leftBottomFront,
            leftBottomBack,
            leftTopBack,
            leftTopFront,
            leftBottomFront,
            leftTopFront,
            rightTopFront,
            rightBottomFront,
            rightTopFront,
            rightTopBack,
            rightBottomBack,
            rightTopBack,
            leftTopBack
        ]

        kwargs = {'point': points,
                  'knot': list(range(len(points))),
                  'degree': 1}

        if name is None:
            if _nm.Name.__elems__:
                name = _nm.Name.eval(nodes['NurbsCurve'].__typesuffix__)
        if name:
            kwargs['name'] = name

        return nodes['DependNode'].fromStr(m.curve(**kwargs))

    #-----------------------------------------|    Operations

    def _setToApi(self, bbox:om.MBoundingBox):
        point1, point2 = bbox.min, bbox.max
        self[:] = list(point1)[:3] + list(point2)[:3]

    def expandToPoint(self, point):
        """
        Expand the BBox to contain the specified point.
        :param point: the point to expand to
        """
        obj = self.api
        obj.expand(om.MPoint(point))
        self._setToApi(obj)
        return self

    def expandToPoints(self, points):
        """
        Expands the BBox to contain the specified points.
        :param points: the points to expand to
        """
        obj = self.api
        for point in points:
            obj.expand(om.MPoint(point))
        self._setToApi(obj)
        return self

    def reset(self):
        """
        Equivalent to :meth:`maya.api.OpenMaya.MBoundingBox.clear`
        """
        self[:] = [0.0] * 6
        return self

    def getSides(self) -> dict:
        """
        Property: ``.sides``

        :return: Return a dictionary with 'right', 'left', 'top', 'bottom',
            'front' and 'back' keys. Each value corresponds to an axis min /
            max, for example 'right' is the max X value, 'bottom' is the min
            Y value, and so on.
        """
        min, max = self.min, self.max
        return {'right': max.x,
                'left': min.x,
                'top': max.y,
                'bottom': min.y,
                'front': max.z,
                'back': min.z}

    sides = property(getSides)

    def getCorners(self) -> list:
        """
        Property: ``.corners``

        :return: A list of points:
            left-bottom-back,
            right-bottom-back,
            right-bottom-front,
            left-bottom-front,
            left-top-front,
            left-top-back,
            right-top-back,
            right-top-front
        """
        right, left, top, bottom, front, back = self.getSides().values()

        return list(map(r.data.Point, [[left, bottom, back],
                                       [right, bottom, back],
                                       [right, bottom, front],
                                       [left, bottom, front],
                                       [left, top, front],
                                       [left, top, back],
                                       [right, top, back],
                                       [right, top, front]]))

    corners = property(getCorners)

    def diagonalScale(self):
        """
        Note that this is not the same as ``self.diagonal.length()``. instead,
        it returns the deviation of the diagonal from 1.7320508075688772 (the
        magnitude of the diagonal of a unit cube).
        """
        return self.diagonal.length() / 1.7320508075688772

    @property
    def diagonal(self):
        return self.max - self.min

    def getMin(self):
        return data['Point'](self[:3])

    def setMin(self, minPoint):
        self[:3] = list(minPoint)

    min = property(getMin, setMin)

    def getMax(self):
        return data['Point'](self[3:])

    def setMax(self, maxPoint):
        self[3:] = list(maxPoint)

    max = property(getMax, setMax)

    #-----------------------------------------|    API

    @property
    def api(self):
        out = om.MBoundingBox()
        out.expand(om.MPoint(self[:3]))
        out.expand(om.MPoint(self[3:6]))
        return out