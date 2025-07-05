from typing import Iterable, Optional

import maya.cmds as m

from riggery.general.functions import short
import riggery.core.lib.names as _nm
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
import riggery.core.lib.nurbsutil as _nut

NurbsCurve = nodes['NurbsCurve']


class BezierCurve(NurbsCurve):

    #----------------------------------------------|    Constructor(s)

    @classmethod
    @short(parent='p',
           name='n',
           worldSpace='ws',
           displayType='dt',
           lineWidth='lw')
    def create(cls,
               points:Iterable,
               parent=None,
               name:Optional[str]=None,
               worldSpace:bool=False,
               displayType=None,
               lineWidth:Optional[float]=None):
        """
        :param points: the CV points; these can be plugs (for a 'live' curve)
            or values
        :param parent/p: an optional parent for the curve shape; defaults to
            None
        :param name/n: if provided, and a parent is provided, will be used as
            the shape name; if a parent is not provided, it will be used to
            name the newly-generated parent; if omitted, block naming will be
            used, where available; defaults to False
        :param displayType/dt: sets the override display type; defaults to
            None
        :param lineWidth/lw: an optional value for the display line width;
            defaults to None
        :return: The generated curve shape.
        """
        points = list(points)
        if not _nut.numCVsValidForBezier(len(points)):
            raise ValueError("invalid number of CVs for bezier")

        pointValues, pointPlugs, hasPlugs = cls._prepBuildPoints(
            points,
            parent=parent,
            worldSpace=worldSpace
        )

        #------------------------------------|    Command build

        spans, knots = _nut.getBezierSpansKnots(len(pointValues))
        kwargs = {'point': pointValues, 'knot': knots, 'degree': 3,
                  'bezier': True}

        if parent is None:
            if name:
                kwargs['name'] = name
            elif _nm.Name.__elems__:
                kwargs['name'] = _nm.Name.evaluate(
                    typeSuffix=cls.__typesuffix__
                )
            else:
                kwargs['name'] = 'bezier1'

        curveXform = nodes['DagNode'](m.curve(**kwargs))
        curveShape = curveXform.shape

        #------------------------------------|    Parent wrangling

        if parent is not None:
            m.parent(str(curveShape), str(parent), r=True, shape=True)
            m.delete(str(curveXform))

            if name is None:
                curveShape.conformShapeName()
            else:
                curveShape.name = name

        #------------------------------------|    Connect plugs

        inputs = [pointValue if pointPlug is None else pointPlug
                  for pointValue, pointPlug in zip(pointValues, pointPlugs)]

        curveShape.driveCVs(inputs)

        #------------------------------------|    Niceties

        if displayType is not None:
            curveShape.attr('overrideEnabled').set(True)
            curveShape.attr('overrideDisplayType').set(displayType)

        if lineWidth is not None:
            lineWidth >> curveShape.attr('lineWidth')

        # Some bugs with naming, forcing it here, revisit this, as it overrides
        # situations where a shape name is explicitly passed
        curveShape.conformShapeName()

        #------------------------------------|    Return

        return curveShape

    @classmethod
    @short(parent='p',
           name='n',
           worldSpace='ws',
           displayType='dt',
           lineWidth='lw')
    def createFromAnchorGroups(cls,
                               anchorGroups:Iterable[dict],
                               parent=None,
                               name=None,
                               worldSpace=False,
                               displayType=None,
                               lineWidth=None):
        """
        Creates a bezier curve from point plugs or values organized into the
        sort of bundle returned by
        :func:`~riggery.core.lib.nurbsutil.cvsToAnchorGroups`.
        """
        return cls.create(_nut.anchorGroupsToCVs(anchorGroups),
                          parent=parent,
                          name=name,
                          worldSpace=worldSpace,
                          displayType=displayType,
                          lineWidth=lineWidth)