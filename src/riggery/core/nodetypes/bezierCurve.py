from typing import Iterable, Optional
from copy import deepcopy

import maya.cmds as m

from riggery.general.functions import short
from riggery.core.lib.serialize import simplify
from riggery.internal.typeutil import UNDEFINED

from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs

from ..lib import names as _nm
from ..lib import mixedmode as _mm
from ..lib import nurbsutil as _nut

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
               points:Iterable, *,
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
        #-----------------|    Resolve points

        points = list(points)

        if not _nut.numCVsValidForBezier(len(points)):
            raise ValueError("invalid number of CVs for bezier")

        pointInfo = cls._parsePoints(points)
        pointValues = pointInfo['values']

        #-----------------|    Draw using Maya command

        kwargs = {}

        if parent is None:
            if name:
                kwargs['name'] = name

            elif _nm.Name.__elems__:
                kwargs['name'] = _nm.Name.evaluate(
                    typeSuffix=cls.__typesuffix__
                )
            reparented = False
        else:
            reparented = True

        spans, knots = _nut.getBezierSpansKnots(len(pointValues))

        if worldSpace and reparented:
            parent = nodes['DagNode'](parent)
            _wim = parent.attr('wim')()
            pointValues = [x ^ _wim for x in pointValues]

        outParent = nodes['DagNode'](m.curve(point=pointValues,
                                             knot=knots,
                                             degree=3,
                                             bezier=True, **kwargs))
        outShape = outParent.shape

        if reparented:
            outShape.parent = parent
            m.delete(str(outParent))
            outParent = outShape.parent

        #-----------------|    Resolve parent

        if reparented:
            if name is None:
                outShape.conformShapeName()
            else:
                outShape.name = name
        else:
            if name is not None:
                outShape.name = name

        #-----------------|    Drive

        if pointInfo['hasPlugs']:
            inputs = pointInfo['conformed']

            if worldSpace:
                wim = outParent.attr('wim')
                inputs = [input ^ wim for input in inputs]

            outShape.driveCVs(inputs)

        if displayType is not None:
            outShape.attr('overrideEnabled').set(True)
            displayType >> outShape.attr('overrideDisplayType')

        if lineWidth is not None:
            lineWidth >> outShape.attr('lineWidth')

        return outShape

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

    #----------------------------------------------|    Serialization

    def macro(self) -> dict:
        out = super().macro()
        out.update({'points': list(self.iterCVPoints(visible=True)),
                    'name': self.shortName(),
                    'parent': self.parent.shortName()})

        cvDrivers = next(self.iterCVDrivers(simple=True), None)

        if cvDrivers is not None:
            out['cvDrivers'] = cvDrivers[1]

        return out

    @classmethod
    def _getCreateArgsKwargsFromMacro(cls, macro:dict) -> tuple:
        points = macro['points']
        cvDrivers = macro.get('cvDrivers')

        if cvDrivers is not None:
            for cvIndex, cvInput in cvDrivers:
                _node, _attr = cvInput.split('.', 1)
                matches = m.ls(_node)
                if len(matches) == 1:
                    if m.objExists(cvInput):
                        points[cvIndex] = matches[0]+'.'+_attr

        args = (points,)
        kwargs = {'name': macro['name']}
        parent = macro['parent']

        matches = m.ls(parent, type='transform')

        if len(matches) == 1:
            kwargs['parent'] = matches[0]

        return args, kwargs

    __macro_attrs__ = ('overrideEnabled',
                       'overrideDisplayType',
                       'visibility',
                       'overrideColor',
                       'lineWidth',
                       'anchorSmoothness',
                       'anchorWeighting',
                       'dispCV')