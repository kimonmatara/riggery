import math
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

import maya.cmds as m


class BezierCurve(NurbsCurve):

    #----------------------------------------------|    Constructor(s)

    @classmethod
    def createCornerFillet_Plugs(cls, point1, point2, point3):

        #---------------|    Gather basics

        with _nm.Name('patchbay'):
            pb = nodes.Network.createNode()

        p0, p1, p2 = map(plugs.Attribute, (point1, point2, point3))
        rays = [p0 - p1, p2 - p1]

        normal, externalAngle = rays[0].axisAngleTo(rays[1])

        #---------------|    Solve at origin

        #---|    Visualize

        oRay0 = data.Vector((0, 0, 1))
        oRay1 = oRay0.rotateByAxisAngle((0, 1, 0), externalAngle)
        # oRay0.loc(name='ray0')
        # oRay1.loc(name='ray1')

        # Half chord length
        chordLength = ((-(oRay0)) + oRay1).length()
        halfChordLength = chordLength * 0.5

        # External height
        externalHeight = (1 - (halfChordLength ** 2)) ** 0.5

        # Internal height
        internalAngle = math.radians(180) - externalAngle
        halfInternalAngle = internalAngle * 0.5
        internalHeight = halfChordLength / halfInternalAngle.tan()

        # Circle centre
        kiteHeight = externalHeight + internalHeight
        kiteVectorN = (oRay0 + oRay1).normal()
        circleCentre = kiteVectorN * kiteHeight

        # Radius
        radius = ((halfChordLength ** 2) + (internalHeight ** 2)) ** 0.5

        # Draw
        kappa = (4/3) * (internalAngle / 4).tan()
        handleLength = radius * kappa

        _p0 = data.Point(oRay0)
        _p1 = _p0 - (oRay0 * handleLength)
        _p3 = oRay1.asType(plugs.Point)
        _p2 = _p3 - (oRay1 * handleLength)

        #---------------|    Draw

        outShape = cls.create((_p0, _p1, _p2, _p3))

        #---------------|    Create skew matrix, transform

        """
        In origin space:
            ray0 is Z
            ray1 is X
            normal is Y
        """
        ff = nodes.FourByFourMatrix.createNode()
        ff.z.put(rays[0])
        ff.x.put(rays[1])
        ff.y.put(normal)
        ff.w.put(p1)

        skew = ff.attr('output')

        ff1 = nodes.FourByFourMatrix.createNode()
        ff1.z.put(oRay0)
        ff1.x.put(oRay1)
        ff1.y.put((0, 1, 0))

        orig = ff1.attr('output')
        delta = orig.inverse() * skew

        (outShape.newInput() * delta) >> outShape.input

        return outShape


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
        points = list(self.iterCVPoints(visible=True))
        inputs = next(self.iterCVDrivers(simple=True))

        if inputs is not None:
            # Discard shape, keep (index, input) pairs
            inputs = inputs[1]
            inputs = [(index, input.split('|')[-1]) for index, input in inputs]

        name = self.shortName()
        parent = self.parent.shortName()

        out = {'points': points,
               'name': name,
               'parent': parent}

        if inputs:
            out['inputs'] = inputs

        out['attrStates'] = {
            x: self.attr(x).getState() for x in ('overrideEnabled',
                                                 'overrideDisplayType',
                                                 'visibility',
                                                 'overrideColor',
                                                 'lineWidth',
                                                 'anchorSmoothness',
                                                 'anchorWeighting',
                                                 'dispCV')
        }

        return out

    @classmethod
    @short(restoreInputs='ri',
           restoreValues='rv',
           restoreParent='rp')
    def createFromMacro(cls,
                        macro:dict,
                        restoreInputs:bool=False,
                        restoreValues:bool=True,
                        restoreParent:bool=True) -> 'BezierCurve':

        createKwargs = {'name': macro['name']}
        points = macro['points']

        if 'inputs' in macro:
            for index, input in macro['inputs']:
                # Look for a match
                _node, _attr = input.split('.', 1)
                nodeMatches = m.ls(_node)

                if len(nodeMatches) > 0:
                    points[index] = '.'.join([nodeMatches[0], _attr])

        createArgs = (points,)

        if restoreParent:
            parent = macro['parent']
            matches = m.ls(parent, type='transform')

            if len(matches) > 0:
                createKwargs['parent'] = matches[0]

        inst = cls.create(*createArgs, **createKwargs)

        for x, state in macro['attrStates'].items():
            inst.attr(x).setState(state,
                                  input=restoreInputs,
                                  value=restoreValues)

        return inst