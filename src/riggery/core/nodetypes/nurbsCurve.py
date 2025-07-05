from typing import Optional, Union, Generator, Iterable

import maya.api.OpenMaya as om
import maya.cmds as m

from ..lib import names as _nm, mixedmode as _mm, nurbsutil as _nut
from riggery.general.functions import short
from riggery.general.numbers import floatrange
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data


class NurbsCurve(nodes['CurveShape']):

    #----------------------------------------------|    Constructor(s)

    @classmethod
    def _prepBuildPoints(cls,
                         points,
                         parent=None,
                         worldSpace=False) -> tuple[list, list, bool]:
        """
        :return: Tuple of point values, point plugs, has plugs (bool)
        """
        if parent is not None:
            parent = nodes['DagNode'](parent)

        #-----------------------------------------|    Prep points

        points = list(points)
        numCVs = len(points)
        if numCVs < 2:
            raise ValueError("need at least two CVs")

        pointPlugs = []
        pointValues = []
        hasPlugs = False

        Point = data['Point']

        for point in points:
            point, _, isPlug = _mm.info(point, Point)
            if isPlug:
                hasPlugs = True
                pointPlugs.append(point)
                pointValues.append(Point(point.get()))
            else:
                pointPlugs.append(None)
                pointValues.append(point)

        if worldSpace:
            if parent is not None:
                for i in range(numCVs):
                    pointValue = pointValues[i]
                    pointValue *= parent.attr('wim').get()
                    pointValues[i] = pointValue

                for i in range(numCVs):
                    plug = pointPlugs[i]
                    if plug is not None:
                        pointPlugs[i] = plug * parent.attr('wim')

        return pointValues, pointPlugs, hasPlugs

    @classmethod
    @short(degree='d',
           parent='p',
           periodic='per',
           name='n',
           worldSpace='ws',
           displayType='dt',
           lineWidth='lw')
    def create(cls,
               points:Iterable,
               degree=None,
               parent=None,
               periodic:bool=False,
               name:Optional[str]=None,
               worldSpace:bool=False,
               ep:bool=False,
               displayType=None,
               lineWidth:Optional[float]=None):
        """
        :param points: the CV points; these can be plugs (for a 'live' curve)
            or values
        :param degree/d: if omitted, defaults to 3, but drops to 2 or 1 when
            there aren't enough CVs
        :param parent/p: an optional parent for the curve shape; defaults to
            None
        :param periodic/per: whether to create a fully closed (periodic) curve;
            defaults to False
        :param name/n: if provided, and a parent is provided, will be used as
            the shape name; if a parent is not provided, it will be used to
            name the newly-generated parent; if omitted, block naming will be
            used, where available; defaults to False
        :param displayType/dt: sets the override display type; defaults to
            None
        :param lineWidth/lw: an optional value for the display line width;
            defaults to None
        :raises ValueError: Fewer than two CVs were requested, or the number
            of CVs is not possible given the requested degree.
        :return: The generated curve shape.
        """
        if ep:
            degree = 1

        if parent is not None:
            parent = nodes['DagNode'](parent)

        #-----------------------------------------|    Prep points

        pointValues, pointPlugs, hasPlugs = cls._prepBuildPoints(
            points,
            parent=parent,
            worldSpace=worldSpace
        )

        numCVs = len(pointValues)

        #------------------------------------|    Prep for curve()

        if degree is None:
            degree = _nut.clampDegree(numCVs, 3)

        spans, knots = _nut.getSpansKnots(numCVs, degree)
        kwargs = {'point': pointValues, 'knot': knots, 'degree': degree}

        # Wrangle name argument
        if parent is None:
            if name:
                kwargs['name'] = name
            elif _nm.Name.__elems__:
                kwargs['name'] = _nm.Name.evaluate(
                    typeSuffix=cls.__typesuffix__
                )

        #------------------------------------|    Draw static curve with curve()

        curveXform = m.curve(**kwargs)

        if periodic:
            m.closeCurve(curveXform,
                         constructionHistory=False,
                         blendBias=0.5,
                         blendKnotInsertion=False,
                         preserveShape=0,
                         replaceOriginal=True)

        curveXform = nodes['DagNode'](curveXform)
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

        inputs = [pointValue if pointPlug is None else pointPlug for pointValue,
        pointPlug in zip(pointValues, pointPlugs)]

        curveShape.driveCVs(inputs)

        #------------------------------------|    EP

        if ep:
            curveShape.newInput().toBSpline() >> curveShape.input
            if not hasPlugs:
                curveShape.deleteHistory()

        #------------------------------------|    Niceties

        if displayType is not None:
            curveShape.attr('overrideEnabled').set(True)
            curveShape.attr('overrideDisplayType').set(displayType)

        if lineWidth is not None:
            lineWidth >> curveShape.attr('lineWidth')

        #------------------------------------|    Return

        return curveShape

    @classmethod
    @short(parent='p', name='n')
    def createFromMacros(
            cls,
            macros:list,
            parent=None,
            name:Optional[str]=None,
            rescale:Union[None, int, float]=None
    ) -> list:
        """
        Reconstitutes one or more curve shapes under a single transform.
        Useful for control shape serialization etc.

        :param macros: one or more dicts of the type returned by :meth:`macro`
        :param parent/p: an optional destination parent; if omitted, a new one
            will be created
        :param name/n: this will only be used if a new parent is
            created; shapes will derive their name from the resolved parent;
            defaults to None
        :param rescale: an optional rescaling factor; defaults to None
        :return: The generated shapes, in a list.
        """
        if parent:
            parent = nodes['DagNode'](parent)
            _parent = parent.__apimobject__()
            conformPerShape = True
        else:
            name = _nm.resolveNameArg(name, typeSuffix=cls.__typesuffix__)
            parent = nodes['Transform'].createNode(name=name)
            _parent = parent.__apimobject__()
            conformPerShape = False

        mfn = om.MFnNurbsCurve()
        shapes = []

        for macro in macros:
            points, knots, degree, form, is2D, rational = [
                macro[k] for k in ('points', 'knots', 'degree',
                                   'form', 'is2D','rational')
            ]
            if rescale is not None:
                points = [[point[0] * rescale,
                           point[1] * rescale,
                           point[2] * rescale] for point in points]

            shape = nodes['DagNode'].fromMObject(mfn.create(
                [om.MPoint(point) for point in points],
                knots,
                degree,
                form,
                is2D,
                rational,
                _parent
            ))

            try:
                shape.attr('lineWidth').set(macro['lineWidth'])
            except KeyError:
                pass

            if 'overrideColor' in macro:
                shape.attr('overrideEnabled').set(True)
                shape.attr('overrideColor').set(macro['overrideColor'])

            shapes.append(shape)

        if conformPerShape:
            for shape in shapes:
                shape.conformShapeName()
        else:
            parent.conformShapeNames()

        return shapes

    #----------------------------------------------|    Serialization

    def _getArgsForMFnCreate(self) -> tuple: # -> tuple[tuple, dict]
        """
        Returns positional arguments that can be passed onto
        :meth:`maya.api.OpenMaya.MFnNurbsCurve.create` to recreate this curve.
        The 'parent' keyword argument will have to be provided separately if
        needed.

        All information is sampled in object space.
        """
        mFn = self.__apimfn__()
        points = mFn.cvPositions(om.MSpace.kObject)
        return tuple([
            points,
            mFn.knots(),
            mFn.degree,
            mFn.form,
            all([point[2] == 0.0 for point in points]),
            self.isRational()
        ])

    def macro(self, *, captureOverrideColor:bool=False) -> dict:
        """
        :return: A dictionary of information that can be used to recreate
            the curve. The informaton is in object-space; world
            transformations are discarded. Useful for control shapes etc.
        """
        points, knots, degree, form, is2D, \
            rational = self._getArgsForMFnCreate()

        out = {'points': [list(x) for x in points],
               'knots': list(knots),
               'degree': degree,
               'form': form,
               'is2D': is2D,
               'rational': rational,
               'lineWidth': self.attr('lineWidth').get()}

        if captureOverrideColor:
            if self.attr('overrideEnabled').get():
                overrideColor = self.attr('overrideColor').get()
                if overrideColor > 0:
                    out['overrideColor'] = overrideColor

        return out

    #----------------------------------------------|    Iterators

    @short(worldSpace='ws')
    def iterCVPoints(self, worldSpace:bool=False) -> Generator:
        """
        Yields CV points.

        :param worldSpace: sample points in world-space; defaults to False
        """
        for item in self.__apimfn__(dag=True).cvPositions(
                space=om.MSpace.kWorld if worldSpace else om.MSpace.kObject
        ):
            yield data['Point'](item)

    cvPoints = property(fget=iterCVPoints)

    #----------------------------------------------|    Queries

    def isRational(self) -> bool:
        """
        :return: True if any of the CVs on this curve have non-1.0 weights.
        """
        for w in self.cvWeights:
            if w != 1.0:
                return True
        return False

    def iterCVWeights(self) -> Generator[float, None, None]:
        """
        Iterates over the CV weights. These are retrieved via forced reads
        on the ``weights`` attribute.
        """
        plug = self.attr('weights')
        for index in range(self.numCVs()):
            yield plug[index].get()

    cvWeights = property(iterCVWeights)

    def is2D(self) -> bool:
        """
        This is really here to give some sort considered argument for the API
        constructor.

        :return: True if the all the Z components of the object-space CV
            positions are zero.
        """
        return all((point[2] == 0.0 for point in self.cvPoints))

    def degree(self) -> int:
        """
        :return: The curve degree (e.g. 3 for cubic).
        """
        return self.__apimfn__().degree

    def form(self) -> int:
        """
        :return: One of 1 (open), 2 (closed), 3 (periodic)
        """
        return self.__apimfn__().form

    def numCVs(self) -> int:
        """
        :return: The number of CVs on the curve.
        """
        return self.__apimfn__().numCVs

    def knotDomain(self) -> tuple[float, float]:
        """
        :return: The curve's min U and max U.
        """
        return self.__apimfn__().knotDomain

    def knots(self) -> list[float]:
        """
        :return: The knot list for this curve.
        """
        return list(self.__apimfn__().knots())

    @short(worldSpace='ws')
    def cageLength(self, worldSpace:bool=False) -> float:
        """
        :param worldSpace/ws: return the world-space cage length; defaults to
            False
        :return: The length of the cage formed by the curve's CVS. On degree-1
            curves, this will be the same as the curve length.
        """
        points = list(self.iterCVPoints(worldSpace))
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
        :param tolerance/tol: the matching tolerance; defaults to 1e-6
        :param asComponent/ac: return component strings rather than indices;
            defaults to False
        :return: A list of tuples, where each tuple is a grouping of indices or
            component paths for a given CV point.
        """
        mapping = [] # [(point, [cvIndex, cvIndex])]

        cvPositions = list(self.cvPoints)

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

        # Create proxy multi
        proxyMulti = shape.addPointAttr('proxyControlPoints', multi=True)

        for i, point in enumerate(points):
            point >> shape.attr('controlPoints')[i]

            # src = str(point)
            # dest = str(shape.attr('controlPoints')[i])
            # m.connectAttr(src, dest, f=True)

        return self

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
        indices = list(range(self.numCVs()))
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