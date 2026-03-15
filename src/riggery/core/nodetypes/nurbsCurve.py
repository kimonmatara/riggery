import math
from copy import deepcopy
from typing import Optional, Union, Iterator, Iterable, Literal

import maya.api.OpenMaya as om
import maya.cmds as m

from ..lib import names as _nm, mixedmode as _mm, nurbsutil as _nut
from riggery.general.functions import short
from riggery.general.numbers import floatrange
from riggery.internal import str2api as _s2a
from riggery.internal import api2str as _a2s
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data
from ..plugtypes import __pool__ as plugs



class NurbsCurve(nodes['CurveShape']):

    #-------------------------------------|    Constructor

    @classmethod
    @short(center='c',
           degree='d',
           normal='nr',
           sections='s',
           sweep='sw')
    def createCircle(cls,
                     radius:float=1.0,
                     normal:Union[
                         'data.Vector', 'plugs.Vector', tuple[float]
                     ]=(0, 1, 0),
                     sweep:Union[float, 'plugs.Number' ]=math.radians(360.0),
                     degree:Union[int, 'plugs.Number']=3,
                     sections:Union[int, 'plugs.Number']=8,
                     center:Union[
                         'data.Vector',
                         'plugs.Vector',
                         tuple[float]
                     ]=(0, 0, 0),
                     name:Optional[str]=None):
        radius, _, radiusIsPlug = _mm.info(radius)
        sweep, _, sweepIsPlug = _mm.info(sweep)
        degree, _, degreeIsPlug = _mm.info(degree)
        sections, _, sectionsIsPlug = _mm.info(sections)
        center, _, centerIsPlug = _mm.info(center, (data.Vector, plugs.Vector),
                                           force=True)
        normal, _, normalIsPlug = _mm.info(normal, (data.Vector, plugs.Vector),
                                           force=True)

        node = nodes['MakeNurbCircle'].createNode()
        node.attr('radius').put(radius, radiusIsPlug)
        node.attr('sweep').put(sweep, sweepIsPlug)
        node.attr('degree').put(degree, degreeIsPlug)
        node.attr('sections').put(sections, sectionsIsPlug)
        node.attr('center').put(center, centerIsPlug)
        node.attr('normal').put(normal, normalIsPlug)

        shape = node.attr('outputCurve').createShape()

        if not any((radiusIsPlug,
                    sweepIsPlug,
                    degreeIsPlug,
                    sectionsIsPlug,
                    centerIsPlug,
                    normalIsPlug)):
            shape.deleteHistory()

        xf = shape.parent

        if name is None:
            if _nm.Name.__elems__:
                name = _nm.Name.evaluate(typeSuffix=cls.__typesuffix__)

        if name:
            xf.name = name
            xf.conformShapeNames()

        return xf

    @classmethod
    @short(degree='d',
           parent='p',
           periodic='per',
           name='n',
           worldSpace='ws',
           displayType='dt',
           lineWidth='lw')
    def create(cls,
               points:Iterable[Union['data.Point', 'plugs.Point']], *,
               degree:Optional[int]=None,
               parent=None,
               periodic:bool=False,
               name:Optional[str]=None,
               worldSpace:bool=False,
               ep:bool=False,
               displayType=None,
               lineWidth:Optional[float]=None):

        #-----------------|    Resolve points

        pointInfo = cls._parsePoints(points)

        pointsAsValues = pointInfo['values']
        pointsAsPlugs = pointInfo['plugs']
        hasPlugs = pointInfo['hasPlugs']

        useBSpline = ep and hasPlugs

        #-----------------|    Resolve parent

        kwargs = {}

        if parent is not None:
            reparented = True
            kwargs['parent'] = _s2a.getNodeMObject(str(parent))
        else:
            reparented = False

        #-----------------|    Get draw info

        drawInfo = _nut.expandDrawInfo(pointsAsValues,
                                       degree=1 if useBSpline else degree,
                                       periodic=periodic)

        if worldSpace and reparented:
            _wim = nodes['DagNode'](parent).attr('wim')().api
            drawInfo['points'] = [point * _wim for point in points]

        #-----------------|    Draw the curve

        fn = om.MFnNurbsCurve()

        useBSpline = ep and hasPlugs

        if ep and not useBSpline:
            # If we have incoming plugs, we can't draw as EP, since the input
            # points will no longer match; instead, draw as CV and convert to
            # EP in the DG
            result = fn.createWithEditPoints(drawInfo['points'],
                                             drawInfo['degree'],
                                             drawInfo['form'],
                                             drawInfo['is2D'],
                                             drawInfo['rational'],
                                             drawInfo['uniform'],
                                             **kwargs)
        else:
            result = fn.create(drawInfo['points'],
                               drawInfo['knots'],
                               drawInfo['degree'],
                               drawInfo['form'],
                               drawInfo['is2D'],
                               drawInfo['rational'],
                               **kwargs)

        if result.hasFn(om.MFn.kTransform):
            outParent = nodes['DependNode'].fromMObject(result)
            outShape = outParent.shape
        else:
            outShape = nodes['DependNode'].fromMObject(result)
            outParent = outShape.parent

        if reparented:
            if name is None:
                outShape.conformShapeName()
            else:
                outShape.name = name
        else:
            if name is None:
                if _nm.Name.__elems__:
                    outParent.name = _nm.Name.evaluate(cls.__typesuffix__)
            else:
                outShape.name = name

        if hasPlugs:
            inputs = pointInfo['conformed']

            if worldSpace:
                wim = outParent.attr('wim')
                inputs = [input ^ wim for input in inputs]

            outShape.driveCVs(inputs)

        if useBSpline:
            newInput = outShape.newInput()
            newInput.toBSpline() >> outShape.input

        if displayType is not None:
            outShape.attr('overrideEnabled').set(True)
            displayType >> outShape.attr('overrideDisplayType')

        if lineWidth is not None:
            lineWidth >> outShape.attr('lineWidth')

        return outShape

    # Point worklist utilities
    @classmethod
    def _parsePoints(cls, points) -> dict:
        """
        :return: Dictionary with these keys:
            'plugs':        list:[Optional[r.plugs.Point]]
            'values':       list:[r.data.Point]
            'conformed':    list[Union[r.plugs.Point, r.data.Point]]
            'hasPlugs':     bool
        """
        infos = [_mm.info(point, (data['Point'], plugs['Point']), force=True)
                 for point in points]
        hasPlugs = any((info[2] for info in infos))

        outPlugs = [info[0] if info[2] else None for info in infos]
        outValues = [info[0] if (not info[2]) else info[0]() for info in infos]
        outConformed = [info[0] for info in infos]

        return {'plugs': outPlugs,
                'values': outValues,
                'conformed': outConformed,
                'hasPlugs': hasPlugs}

    #-------------------------------------|    Inspections

    @short(worldSpace='ws',
           visible='v')
    def iterCVPoints(self, *,
                     worldSpace:bool=False,
                     visible:bool=False) -> Iterator:
        """
        Yields CV points.

        :param visible: on periodic curves, remove internal / overlapping CVs,
            which can neither be seen nor manipulated in the Maya viewport;
            defaults to False
        :param worldSpace: sample points in world-space; defaults to False
        """
        space = om.MSpace.kWorld if worldSpace else om.MSpace.kObject

        fn = self.__apimfn__(dag=True)
        out = list(fn.cvPositions(space=space))

        if visible and fn.form == fn.kPeriodic:
            out = out[:len(out)-fn.degree]

        for point in out:
            yield data['Point'](point)

    def knots(self) -> list[float]:
        """
        :return: The knot list for this curve.
        """
        return list(self.__apimfn__().knots())

    def knotDomain(self) -> tuple[float, float]:
        """
        :return: The curve's min U and max U.
        """
        return self.__apimfn__().knotDomain

    @short(visible='v')
    def numCVs(self, visible:bool=False) -> int:
        """
        :param visible: on periodic curves, remove internal / overlapping CVs,
            which can neither be seen nor manipulated in the Maya viewport;
            defaults to False
        :return: The number of CVs on the curve.
        """
        fn = self.__apimfn__()
        numCVs = self.__apimfn__().numCVs

        if visible and fn.form == fn.kPeriodic:
            numCVs -= fn.degree

        return numCVs

    numVertices = numCVs

    def form(self) -> int:
        """
        :return: One of 1 (open), 2 (closed), 3 (periodic)
        """
        return self.__apimfn__().form

    def isPeriodic(self) -> bool:
        """
        :return: True if this is a periodic (fully closed, circle-like) curve.
        """
        return self.__apimfn__().form == 3

    def degree(self) -> int:
        """
        :return: The curve degree (e.g. 3 for cubic).
        """
        return self.__apimfn__().degree

    @short(worldSpace='ws')
    def cageLength(self, worldSpace:bool=False) -> float:
        """
        On periodic curves, this only deals with visible CVs.

        :param worldSpace/ws: return the world-space cage length; defaults to
            False
        :return: The length of the cage formed by the curve's visible CVs.
            On degree-1 curves, this will be the same as the curve length.
        """
        points = list(self.iterCVPoints(worldSpace=worldSpace, visible=True))
        vectors = [(nextPoint-thisPoint) \
                   for thisPoint, nextPoint in zip(points, points[1:])]
        return sum([vector.length() for vector in vectors])

    @short(worldSpace='ws', tolerance='tol')
    def length(self, worldSpace:bool=False, tolerance:float=0.001) -> float:
        """
        Extends the MFn implementation to give a space-sensitive result.

        :param tolerance / tol: max error allowed in the calculation
        :return: The arc length of this curve or 0.0 if it cannot be computed.
        """
        out = self.__apimfn__().length()

        if not worldSpace:
            return out

        objectCageLength = self.cageLength()
        worldCageLength = self.cageLength(worldSpace=worldSpace)

        return out * (worldCageLength / objectCageLength)

    @short(tolerance='tol',
           asComponent='ac')
    def getCollocatedCVGroups(self, *,
                              tolerance=1e-6,
                              asComponent:bool=False) -> list[tuple[int]]:
        """
        On periodic curves, this only deals with visible CVs.

        :param tolerance/tol: the matching tolerance; defaults to 1e-6
        :param asComponent/ac: return component strings rather than indices;
            defaults to False
        :return: A list of tuples, where each tuple is a grouping of indices or
            component paths for a given CV point.
        """
        mapping = [] # [(point, [cvIndex, cvIndex])]

        cvPositions = list(self.iterCVPoints(visible=True))

        for i, thisPoint in enumerate(cvPositions):
            inserted = False
            for refPoint, members in mapping:
                if refPoint.isEquivalent(thisPoint, tolerance=tolerance):
                    members.append(i)
                    inserted = True
                    break
            if inserted:
                continue
            mapping.append((thisPoint, [i]))

        out = [tuple(entry[1]) for entry in mapping]

        if asComponent:
            _self = str(self)
            out = [tuple([f"{_self}.cv[{index}]" \
                          for index in entry]) for entry in out]

        return out

    #----------------------------------------------|    Soft sampling

    @short(normalize='nr', worldSpace='ws')
    def tangentAtParam(self,
                       param:float,
                       worldSpace:bool=False,
                       normalize:bool=False):
        """
        :param param: the parameter at which to sample a tangent
        :param worldSpace: return a world-space tangent; defaults to False
        :param normalize: return a normalized tangent; defaults to False
        :return: The tangent at the specified U value.
        """
        fn = self.__apimfn__(dag=worldSpace)
        space = om.MSpace.kWorld if worldSpace else om.MSpace.kObject

        if normalize:
            return data['Vector'](fn.tangent(param, space=space))
        return data['Vector'](fn.getDerivativesAtParam(param, space=space)[1])

    @short(worldSpace='ws')
    def pointAtParam(self, param:float, worldSpace:bool=False):
        """
        :param param: the parameter at which to sample a point
        :param worldSpace: return a world-space point; defaults to False
        :return: The point at the specified U value.
        """
        return data['Point'].fromApi(self.__apimfn__(dag=True).getPointAtParam(
            param,
            space=om.MSpace.kWorld if worldSpace else om.MSpace.kObject
        ))

    @short(worldSpace='ws')
    def pointAtCV(self, cvIndex:int, worldSpace:bool=False):
        out = m.pointPosition(f"{self}.cv[{cvIndex}]", world=worldSpace)
        return data['Point'](out)

    def paramAtLength(self, length:float, worldSpace:bool=False):
        """
        :param length: the length at which to sample a parameter
        :param worldSpace: specifies that *length* takes into account this
            curve's world-space transformations; defaults to False
        :return: The parameter at the specified length value.
        """
        if worldSpace:
            ratio = self.cageLength(True) / self.cageLength(False)
            length /= ratio

        fn = self.__apimfn__(dag=True)
        return fn.findParamFromLength(length)

    def paramAtFraction(self, fraction:float, *, length=None):
        """
        :param fraction: the length fraction at which to sample a parameter
        :param length: if you have a precalculated length, provide it here;
            defaults to None
        :return: The parameter at the specified length fraction.
        """
        if length is None:
            length = self.length()
        return self.paramAtLength(length * fraction)

    @short(worldSpace='ws')
    def pointAtLength(self, length:float, worldSpace:bool=False):
        """
        :param length: the length at which to sample a point
        :param worldSpace: return a world-space point; defaults to False
        :return: The point at the specified length value.
        """
        param = self.paramAtLength(length, worldSpace=worldSpace)
        return self.pointAtParam(param, worldSpace=worldSpace)

    @short(worldSpace='ws')
    def pointAtFraction(self, fraction, worldSpace:bool=False):
        """
        :param fraction: the fraction at which to sample a point
        :param worldSpace: return a world-space point; defaults to False
        :return: The point at the specified length fraction.
        """
        length = self.length(worldSpace=worldSpace) * fraction
        return self.pointAtLength(length, worldSpace=worldSpace)

    #----------------------------------------------|    Editing

    def driveCVs(self, points:Iterable):
        """
        Drives the CVs of this curve using point attributes.

        :param points: the point outputs to use
        :return: self
        """
        points = list(points)
        shape = self.newInput().node()

        for i, point in enumerate(points):
            point >> shape.attr('controlPoints')[i]

        return self

    def iterCVDrivers(self, simple:bool=False) -> Iterator:
        """
        Yields tuples where each tuple comprises
        ``(shape, [(cvIndex, cvDriver]])``. Shapes that do not share a parent
        with this shape are ignored.

        :param simple: return strings instead of Elem instances; defaults to
            False
        """
        thisParent = self.parent

        for shape in self.history():
            if isinstance(shape, NurbsCurve):
                if shape.parent == thisParent:
                    out = []
                    for i in shape.attr('controlPoints').indices():
                        slot = shape.attr('controlPoints')[i]
                        inputs = slot.inputs(plugs=True)
                        if inputs:
                            input = inputs[0]
                            if simple:
                                input = str(input)
                            out.append((i, input))
                    if out:
                        if simple:
                            shape = str(shape)
                        yield (shape, out)

    @short(collocated='col', tolerance='tol')
    def clusterAll(self, *, collocated:bool=False, tolerance=1e-6) -> list:
        """
        Creates clusters all along this curve.

        :param collocated/col: merge any collocated CVs under the same cluster;
            defaults to False
        :param tolerance/tol: the collocation tolerance; defaults to 1e-6
        """
        if collocated:
            groups = self.getCollocatedCVGroups(tolerance=tolerance,
                                                asComponent=True)
        else:
            _self = str(self)
            groups = ((f"{_self}.cv[{index}]",) \
                      for index in range(self.numCVs()))

        out = []

        for i, group in enumerate(groups):
            with _nm.Name(i+1):
                out.append(nodes['Cluster'].create(group))

        return out

    #----------------------------------------------|    Bezier

    @short(asIndex='ai',
           asComponent='ac',
           worldSpace='ws')
    def getAnchorGroups(self,
                        asIndex:bool=False,
                        asComponent:bool=False,
                        worldSpace:bool=False) -> list[dict]:
        indices = list(range(self.numCVs(visible=True)))

        if asIndex:
            content = indices
        else:
            _self = str(self)
            components = [f"{_self}.cv[{i}]" for i in indices]

            if asComponent:
                content = components
            else:
                content = [
                    data['Point'](m.pointPosition(x, world=worldSpace))
                    for x in components
                ]

        return list(_nut.cvsToAnchorGroups(content))

    #----------------------------------------------|    Distributions

    @short(parametric='par')
    def distributeParams(self, number:int, parametric:bool=False):
        """
        :param number: the number of parameters to generate
        :param parametric/par: distribute in parametric (U) space rather than by
            length; defaults to False
        :return: The generated parameter values.
        """
        if parametric:
            return list(floatrange(*self.knotDomain(), number))
        length = self.length()
        lengths = [length * fraction for fraction in floatrange(0, 1, number)]
        return [self.paramAtLength(length) for length in lengths]

    @short(worldSpace='ws', parametric='par')
    def distributePoints(self,
                         number:int,
                         worldSpace:bool=False,
                         parametric:bool=False) -> list:
        """
        :param number: the number of points to generate
        :param worldSpace/ws: generate points in world-space; defaults to False
        :param parametric/par: distribute in parametric (U) space rather than by
            length; defaults to False
        :return: The generated point values.
        """
        return [self.pointAtParam(param, worldSpace=worldSpace) for param in
                self.distributeParams(number, parametric=parametric)]

    @short(worldSpace='ws',
           normalize='nr',
           parametric='par')
    def distributeTangents(self,
                           number:int,
                           worldSpace:bool=False,
                           normalize:bool=False,
                           parametric:bool=False) -> list:
        """
        :param number: the number of tangents to generate
        :param worldSpace/ws: generate tangents in world-space; defaults to
            False
        :param parametric/par: distribute in parametric (U) space rather than by
            length; defaults to False
        :param normalize/nr: normalize the tangents; defaults to False
        :return: The generated tangent values.
        """
        return [self.tangentAtParam(param,
                                    worldSpace=worldSpace,
                                    normalize=normalize) for param in
                self.distributeParams(number, parametric=parametric)]

    #----------------------------------------------|    Closest

    @short(worldSpace='ws')
    def closestParam(self, point, worldSpace:bool=False):
        """
        :param point: the reference point
        :param worldSpace/ws: sample in world-space; defaults to False
        :return: The U parameter closest to the specified point.
        """
        fn = self.__apimfn__(dag=worldSpace)
        point = om.MPoint(point)
        space = om.MSpace.kWorld if worldSpace else om.MSpace.kObject
        out = fn.closestPoint(point, space=space)[1]
        return out

    @short(worldSpace='ws')
    def closestPoint(self, point, worldSpace:bool=False):
        """
        :param point: the reference point
        :param worldSpace/ws: sample in world-space; defaults to False
        :return: The point on this curve that's closest to the specified
            reference point.
        """
        fn = self.__apimfn__(dag=worldSpace)
        point = om.MPoint(point)
        space = om.MSpace.kWorld if worldSpace else om.MSpace.kObject
        mPoint =  fn.closestPoint(point, space=space)[0]
        out = data['Point'](mPoint)
        return out

    #----------------------------------------------|    Bezier

    def cvsAtAnchor(self, anchorIndex:int) -> tuple:
        return self.getAnchorGroup(anchorIndex, asComponent=True, explode=True)

    @short(asComponent='ac',
           asPoint='ap',
           worldSpace='ws',
           explode='ex')
    def getAnchorGroup(self,
                       anchorIndex:int,
                       asPoint:bool=False,
                       asComponent:bool=False,
                       worldSpace:bool=False,
                       explode:bool=False) -> Union[tuple, dict]:
        anchorCVIndex = _nut.anchorIndexToCVIndex(anchorIndex)

        if anchorCVIndex == 0:
            isFirst, isLast = True, False
        elif anchorCVIndex == self.numCVs()-2:
            isFirst, isLast = False, True
        else:
            isFirst = isLast = False

        anchorGroup = {}

        if not isFirst:
            anchorGroup['in'] = anchorCVIndex - 1

        anchorGroup['anchor'] = anchorCVIndex

        if not isLast:
            anchorGroup['out'] = anchorCVIndex + 1

        if asComponent:
            anchorGroup = {k: f"{self}.cv[{index}]"
                           for k, index in anchorGroup.items()}
        elif asPoint:
            anchorGroup = {k: self.pointAtCV(index, worldSpace=worldSpace)
                           for k, index in anchorGroup.items()}

        if explode:
            return tuple(anchorGroup.values())

        return anchorGroup

    def numAnchors(self) -> int:
        """
        :return: The number of Bezier anchors on this curve.
        """
        return _nut.numCVsToNumAnchors(self.numCVs())

    def paramAtAnchor(self, anchorIndex:int) -> float:
        """
        :param anchorIndex: the index of the anchor at which to sample a U
            parameter
        :return: The U parameter at the center of the specified Bezier anchor.
        """
        return self.knots()[::3][anchorIndex]

    #-------------------------------------|    CV driving

    def driveCVsNEW(self, points:Iterable[Union['data.Point', 'plugs.Point']]):
        """
        Replaces the older implementation of ``driveCVs``, which conked out in
        Maya 2026 (which broke curve driving via .controlPoints). This one uses
        DG clusters and component tags instead.
        """
        #---------------------------|    Gather info

        newPoints = [_mm.conform(x, (plugs['Point'], data['Point']), force=True)
                     for x in points]

        _oldPoints = list(self.iterCVPoints(visible=True))

        origShape = self.getOrigShape(True)
        origInput = self.getHistoryInput()

        #---------------------------|    Loop

        clusters = []
        incoming = origInput

        #---------------------------|    Loop

        for i, (_oldPoint, newPoint) in enumerate(
                zip(_oldPoints, newPoints)
        ) :
            with _nm.Name(i+1):
                # Create the cluster node
                cluster = nodes.Cluster.createNode()

                # Connect origShape into .originalGeometry
                origShape.attr('local') >> cluster.attr('originalGeometry')

                # Connect last output

                incoming >> cluster.attr('input')[0].attr('inputGeometry')

                #---------------|    Component tags

                # Create the component tag on the base shape
                tagName = m.componentTag(['{}.cv[{}]'.format(self, i)],
                                         cr=True,
                                         ntn='cluster{}'.format(i+1),
                                         utn=True)

                # Set the component tag expression on the cluster .input
                cluster.attr('input')[0].attr('componentTagExpression').set(
                    tagName
                )

                #---------------|    Drive the cluster

                with _nm.Name('asTmtx'):
                    tmtx = newPoint.asTranslateMatrix()

                with _nm.Name('asOffset'):
                    tmtx = tmtx.asOffset()

                tmtx >> cluster.attr('matrix')

                #---------------|    Finalize the loop

                clusters.append(cluster)
                incoming = cluster.attr('outputGeometry')[0]

        # Connect last cluster into this shape

        incoming >> self.attr('create')

        return self