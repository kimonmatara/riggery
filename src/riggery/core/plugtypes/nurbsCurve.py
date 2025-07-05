import math
from typing import Generator, Union, Optional, Iterable

import maya.api.OpenMaya as om

from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from riggery.general.numbers import floatrange
from ..lib import geo as _geo
from ..lib import mixedmode as _mm
from ..lib import names as _nm
from ..elem import Elem
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data


class NurbsCurve(plugs['Geometry']):

    #--------------------------------------|    Free-floating generation

    @classmethod
    def createLine(cls,
                   startPoint,
                   endPoint,
                   degree:Optional[int]=None,
                   numCVs:Optional[int]=None):
        """
        :param startPoint: the start point of the line, as a value or plug
        :param endPoint: the end point of the line, as a value or plug
        :param numCVs: the number of CVs on the curve; if *degree* is provided,
            defaults to minimum number of CVs for the given degree; if degree
            is also omitted, defaults to 2
        :param degree: the curve degree; if *numCVs* is provided, defaults to
            the minimum degree required for the number of CVs; if *numCVs* is
            also omitted, defaults to 1 (linear)
        :return: The output plug
        """
        #-----------------------|    Parse args

        if degree is None:
            if numCVs is None:
                degree, numCVs = 1, 2
            else:
                degree = max(3, numCVs-1)
        elif numCVs is None:
            numCVs = degree + 1

        #-----------------------|    Prep

        numSpans = numCVs - degree
        Point = data['Point']
        startPoint = _mm.info(startPoint, Point)[0]
        endPoint = _mm.info(endPoint, Point)[0]
        vector = endPoint - startPoint
        mag = vector.length()

        #-----------------------|    Generator

        node = nodes['MakeNurbsSquare'].createNode()
        numSpans >> node.attr('spansPerSide')
        node.attr('normal').set([0.0, 0.0, 1.0])
        node.attr('center').set([0.5, 0.5, 0.0])
        node.attr('sideLength1').set(1.0)
        node.attr('sideLength2').set(1.0)
        node.attr('degree').set(degree)
        output = node.attr('outputCurve3')

        #-----------------------|    Transformation

        scaleMatrix = _mm.createScaleMatrix(1.0, mag, 1.0)
        matrix = _mm.createOrthoMatrix(
            'y', vector,
            'x', [1, 0, 0],
            w = startPoint
        ).pick(translate=True, rotate=True)
        matrix = scaleMatrix * matrix

        return output * matrix

    #--------------------------------------|    Static sampling

    def _getData(self) -> om.MObject:
        return self._getSamplingPlug().asMDataHandle().asNurbsCurveTransformed()

    def __datamfn__(self) -> om.MFnNurbsCurve:
        return om.MFnNurbsCurve(self._getData())

    def knotDomain(self) -> tuple[float, float]:
        return self.__datamfn__().knotDomain

    def knots(self) -> list[float]:
        return self.__datamfn__().knots()

    def numCVs(self) -> int:
        """
        :return: The number of CVs in the curve.
        """
        return self.__datamfn__().numCVs

    def hasMultipleEndKnots(self) -> bool:
        """
        :return: True if this curve has multiple end knots.
        """
        fn = self.__datamfn__()
        degree = fn.degree
        if degree == 1:
            return False
        knots = fn.knots()
        head = knots[:degree]
        tail = knots[-degree:]
        return len(set(head)) == 1 or len(set(tail)) == 1

    def isPeriodic(self) -> bool:
        """
        :return: True if this curve is periodic (properly closed).
        """
        return self.__datamfn__().form == om.MFnNurbsCurve.kPeriodic

    def degree(self) -> int:
        """
        :return: The curve degree.
        """
        return self.__datamfn__().degree

    def numSpans(self) -> int:
        return self.__datamfn__().numSpans

    #--------------------------------------|    Dynamic sampling

    @cache_dg_output
    def info(self):
        """
        Retrieves or initializes a ``curveInfo`` node connected to this curve
        output.
        """
        for output in self.outputs(type='curveInfo'):
            return output

        node = nodes['CurveInfo'].createNode()
        self >> node.attr('inputCurve')
        return node

    @short(plug='p')
    def length(self, plug:bool=True):
        """
        :param plug/p: return the length as a live attribute rather than a
            value; defaults to Trues
        :return: The length of this curve
        """
        if plug:
            return self.info().attr('arcLength')
        return self.__datamfn__().length()

    @short(plug='p')
    def iterCVPoints(self, plug:bool=True) -> Generator:
        """
        Yields CV positions.

        :param plug/p: yield plugs rather than values; defaults to True
        """
        if plug:
            multi = self.info().attr('controlPoints')
            multi.evaluate()
            for i in range(self.numCVs()):
                yield multi[i]
        else:
            fn = self.__datamfn__()
            for point in fn.cvPositions():
                yield data['Point'](point)

    cvPoints = property(fget=iterCVPoints)

    @short(plug='p')
    def pointAtCV(self, cvIndex:int, plug:bool=True):
        """
        :param cvIndex: the index of the CV
        :param plug/p: return a live attribute instead of a value; defaults to
            True
        :return: The point at the given CV index.
        """
        if plug:
            return self.info().attr('controlPoints')[cvIndex]
        return data['Point'].fromApi(
            (self.__datamfn__().cvPositions()[cvIndex])
        )

    def infoAtParam(self, param):
        return _geo.CurveSampleInfoAtParam.create(self)[param]

    @short(plug='p')
    def pointAtParam(self, param, plug=True):
        """
        :param param: the parameter at which to sample a point
        :param plug: return a live attribute rather than a value; defaults to
            True
        """
        if plug:
            return self.infoAtParam(param).attr('position')
        return data['Point'].fromApi(
            self.__datamfn__().getPointAtParam(param,
                                               space=om.MSpace.kObject)
        )

    @short(plug='p')
    def tangentAtParam(self, param, normalize:bool=False, plug=True):
        if plug:
            return self.infoAtParam(param).attr('normalizedTangent'
                                                if normalize else 'tangent')
        fn = self.__datamfn__()
        if normalize:
            out = fn.tangent(param, space=om.MSpace.kObject)
        else:
            out = fn.getDerivativesAtParam(param, space=om.MSpace.kObject)[1]

        return data['Vector'](out)

    @short(plug='p')
    def pointAtFraction(self, fraction, plug=True):
        """
        :param fraction: the fraction at which to evaluate a point
        :param plug/p: return an attribute rather than a value; defaults to True
        """
        if plug:
            sampler = _geo.CurveSamplePointAtFraction.create(self)
            result = sampler[fraction]
            return result

        length = self.length(False) * fraction
        fn = self.__datamfn__()
        param = fn.findParamFromLength(length)
        point = fn.getPointAtParam(param, space=om.MSpace.kObject)
        return data['Point'].fromApi(point)

    @short(plug='p')
    def paramAtPoint(self, point, plug=True):
        """
        :param point: the point at which to sample a parameter
        :param plug/p: return an attribute rather than a value; defaults to
            True
        :return: The parameter at the specified point.
        """
        if plug:
            return _geo.CurveSampleClosestPoint.create(self
                                                    )[point].attr('parameter')

        fn = self.__datamfn__()
        point = om.MPoint(point)
        try:
            return fn.getParamAtPoint(
                point,
                tolerance=om.MFnNurbsCurve.kPointTolerance,
                space=om.MSpace.kObject
            )
        except RuntimeError:
            return fn.closestPoint(
                point,
                tolerance=om.MFnNurbsCurve.kPointTolerance,
                space=om.MSpace.kObject
            )[1]

    @short(plug='p')
    def paramAtFraction(self, fraction, plug=True):
        """
        :param fraction: the fraction at which to sample a U parameter
        :param plug/p: return a live attribute rather than a value; defaults to
            True
        :return: The parameter at the given fraction.
        """
        if plug:
            return self.paramAtPoint(self.pointAtFraction(fraction))
        length = self.length(False) * fraction
        return self.paramAtLength(length, False)

    def fractionAtLength(self, length, plug=True):
        if plug:
            sampler = _geo.CurveSampleFractionAtLength.create(self)
            result = sampler[length]
            return result
        return length / self.length(plug=False)

    def lengthAtParam(self, param):
        """
        At the moment this is plug-only.

        :param param: the parameter at which to return a length
        :return: The length at the specified parameter.
        """
        sampler = _geo.CurveSampleLengthAtParam.create(self)
        return sampler[param]

    def fractionAtParam(self, param):
        """
        At the moment this is plug-only.

        :param param: the parameter at which to return a fraction
        :return: The fraction at the specified parameter.
        """
        length = self.lengthAtParam(param)
        return self.fractionAtLength(length)

    @short(plug='p')
    def paramAtLength(self, length, plug=True):
        """
        :param length: the length at which to sample a U parameter
        :param plug/p: return a live attribute rather than a value; defaults to
            True
        :return: The parameter at the given length.
        """
        if plug:
            fraction = self.fractionAtLength(length)
            point = self.pointAtFraction(fraction)
            return self.paramAtPoint(point)
        return self.__datamfn__().findParamFromLength(length)

    #--------------------------------------|    Conversions

    @short(tolerance='tol',
           keepRange='kr')
    def toBSpline(self, *,
                  tolerance:float=0.1,
                  keepRange:Union[str, int]=1):
        """
        Generates a B-spline from this NURBS curve output. Works best with
        degree-1 input sources, for an 'EP' effect.

        :param tolerance/tol: the fitting tolerance; defaults to 0.1
        :param keepRange/kr: an enum value or label for the 'keepRange'
            attribute on the ``fitBspline`` node; defaults to 1 ('Original')
        """
        node = nodes['FitBspline'].createNode()
        self >> node.attr('inputCurve')
        node.attr('tolerance').set(tolerance)
        node.attr('keepRange').set(keepRange)
        return node.attr('outputCurve')

    #--------------------------------------|    Join / cut

    def cut(self, *parameters, keep=None) -> list:
        """
        :param parameters: the parameter(s) at which to cut
        :param keep: one or more output plug indices to keep for the return;
            defaults to all outputs
        :return: The selected output(s), in a list.
        """
        node = nodes['DetachCurve'].createNode()
        self >> node.attr('inputCurve')
        for i, parameter in enumerate(expand_tuples_lists(*parameters)):
            parameter >> node.attr('parameter')[i]
        node.attr('outputCurve').evaluate()

        if keep is None:
            keep = node.attr('outputCurve').indices()
        else:
            keep = expand_tuples_lists(keep)

        for i in range(len(parameters)+1):
            node.attr('keep')[i].set(i in keep)

        return [node.attr('outputCurve')[index] for index in keep]

    @short(blend='bl',
           keepMultipleKnots='kmk',
           reverse1='rv1',
           reverse2='rv2')
    def join(self,
             otherCurve, *,
             blend:bool=False,
             keepMultipleKnots=True,
             reverse1:bool=False,
             reverse2:bool=False):
        """
        :param otherCurve: the curve to connect to this one; if it's a shape,
            the local output is used
        :param blend/bl: use the 'blend' method rather than 'connect'; defaults
            to False
        :param keepMultipleKnots/kmk: keep multiple knots; defaults to True
        :param reverse1: reverse this curve before connecting; defaults to False
        :param reverse2: reverse the other curve before connecting; defaults to
            False
        :return: The combination curve.
        """
        otherCurve = Elem(otherCurve)
        if not isinstance(otherCurve, plugs['Attribute']):
            otherCurve = otherCurve.localOutput

        node = nodes['AttachCurve'].createNode()
        node.setAttrs(reverse1=reverse1,
                      reverse2=reverse2,
                      keepMultipleKnots=keepMultipleKnots,
                      method=1 if blend else 0)
        self >> node.attr('inputCurve1')
        otherCurve >> node.attr('inputCurve2')
        return node.attr('outputCurve')

    @short(blend='bl',
           keepMultipleKnots='kmk')
    def multiJoin(self,
                  *otherCurves,
                  blend:bool=False,
                  keepMultipleKnots=True):
        """
        Runs chained :method:`join` operations. No auto-reversals are performed;
        input curves must have the correct direction already.

        .. note::

            This does *not* run all the curves through a single ``attachCurve``
            node, as I've run into problems using that in the past.

        :param otherCurves: the curves to tack-on; if shapes are passed, the
            local output is used
        :param blend/bl: use the 'blend' method rather than 'connect'; defaults
            to False
        :param keepMultipleKnots/kmk: keep multiple knots; defaults to True
        :return: The combination curve.
        """
        Attribute = plugs['Attribute']
        otherCurves = map(Elem, expand_tuples_lists(*otherCurves))
        otherCurves = [curve if isinstance(curve, Attribute) \
                           else curve.localOutput for curve in otherCurves]
        allCurves = [self] + otherCurves
        return reduce(
            lambda x, y: x.join(y,
                                blend=blend,
                                keepMultipleKnots=keepMultipleKnots),
            allCurves
        )

    #--------------------------------------|    Rebuilds

    @cache_dg_output
    def reverse(self):
        """
        Reverses this curve's direction.
        """
        node = nodes['ReverseCurve'].createNode()
        self >> node.attr('inputCurve')
        return node.attr('outputCurve')

    @short(preserveShape='ps')
    def open(self, *, preserveShape=0):
        """
        Opens this curve, but only if it's closed.

        :param preserveShape/ps: an input or value for the ``preserveShape``
            attribute on the ``closeCurve`` node; defaults to 0 ('Ignore')
        """
        if self.isPeriodic():
            node = nodes['CloseCurve'].createNode()
            node.attr('preserveShape').set(preserveShape)
            self >> node.attr('inputCurve')
            return node.attr('outputCurve')
        return self

    @short(preserveShape='ps')
    def close(self, *, preserveShape=0):
        """
        Closes this curve, but only if it's open.

        :param preserveShape/ps: an input or value for the ``preserveShape``
            attribute on the ``closeCurve`` node; defaults to 0 ('Ignore')
        """
        if not self.isPeriodic():
            node = nodes['CloseCurve'].createNode()
            node.attr('preserveShape').set(preserveShape)
            self >> node.attr('inputCurve')
            return node.attr('outputCurve')
        return self

    @cache_dg_output
    def rebuildRange(self):
        """
        Rebuilds this curve into the 0 -> 1 range.
        """
        node = nodes['RebuildCurve'].createNode()

        node.setAttrs(
            rebuildType=2,
            endKnots=1 if self.hasMultipleEndKnots() else 0,
            keepRange=0,
            keepControlPoints=True,
            keepEndPoints=True,
            keepTangents=True
        )

        self >> node.attr('inputCurve')
        self >> node.attr('matchCurve')
        return node.attr('outputCurve')

    @cache_dg_output
    def rebuildLinear(self):
        """
        Rebuilds this curve with degree 1 and the same CVs.
        """
        node = nodes['RebuildCurve'].createNode()
        node.setAttrs(
            rebuildType=0,
            keepControlPoints=True,
            keepEndPoints=True,
            keepTangents=True,
            degree=1
        )
        self >> node.attr('inputCurve')
        return node.attr('outputCurve')

    def rebuildCVs(self, numCVs:int, *, keepRange:Union[int, str]=1):
        """
        :param numCVs: the target number of CVs; if this is very low, the curve
            degree may be dropped as well
        :param keepRange: a setting for the 'keepRange' enum on the
            ``rebuildCurve`` node; defaults to 1 ('Original')
        """
        degree = self.degree()
        while True:
            try:
                spans, knots = getSpansKnots(numCVs, degree)
            except ValueError as exc:
                if degree == 1:
                    raise exc
                degree -= 1
                continue
            break

        node = nodes['RebuildCurve'].createNode()

        node.setAttrs(rebuildType=0,
                      spans=spans,
                      degree=degree,
                      endKnots=1,
                      keepRange=keepRange,
                      keepEndPoints=True)

        self >> node.attr('inputCurve')
        return node.attr('outputCurve')

    #--------------------------------------|    Extensions

    @short(useSegment='uss',
           blendSegment='bss',
           removeMultipleKnots='rmk')
    def extendToPoint(self,
                      point, *,
                      useSegment:bool=None,
                      blendSegment:bool=False,
                      removeMultipleKnots:bool=False):
        """
        Extends this curve to meet the specified 3D point.

        :param point: the target point, as a value or plug
        :param useSegment/uss: extend using a line segment; if *blendSegment* is
            True, defaults to True, otherwise False
        :param blendSegment/bls: if using a segment, connect it using the
            'blend' method rather than 'connect'; defaults to False
        :param removeMultipleKnots/rmk: remove multiple knots; defaults to False
        """
        if useSegment is None:
            if blendSegment:
                useSegment = True

        if useSegment:
            startPoint = self.pointAtCV(self.numCVs()-1)
            segment = self.createLine(startPoint, point)
            return self.join(segment,
                             keepMultipleKnots=not removeMultipleKnots,
                             blend=blendSegment)

        node = nodes['ExtendCurve'].createNode()
        self >> node.attr('inputCurve1')
        point >> node.attr('inputPoint')
        node.setAttrs(start=0,
                      extendMethod=2,
                      removeMultipleKnots=removeMultipleKnots)
        return node.attr('outputCurve')

    @short(useSegment='uss',
           blendSegment='bls',
           removeMultipleKnots='rmk')
    def extendByVector(self,
                       vector, *,
                       useSegment:bool=None,
                       blendSegment:bool=False,
                       removeMultipleKnots:bool=False):
        """
        Variant of :meth:`extendToPoint`.

        :param point: the vector, as a value or plug
        :param useSegment/uss: extend using a line segment; if *blendSegment* is
            True, defaults to True, otherwise False
        :param blendSegment/bls: if using a segment, connect it using the
            'blend' method rather than 'connect'; defaults to False
        :param removeMultipleKnots/rmk: remove multiple knots; defaults to False
        """
        if useSegment is None:
            if blendSegment:
                useSegment = True

        startPoint = self.pointAtCV(self.numCVs()-1)
        endPoint = startPoint + vector

        if useSegment:
            segment = self.createLine(startPoint, endPoint)
            return self.join(segment,
                             keepMultipleKnots=not removeMultipleKnots,
                             blend=blendSegment)

        node = nodes['ExtendCurve'].createNode()
        self >> node.attr('inputCurve1')
        endPoint >> node.attr('inputPoint')
        node.setAttrs(start=0,
                      extendMethod=2,
                      removeMultipleKnots=removeMultipleKnots)
        return node.attr('outputCurve')

    @short(start='s',
           extensionType='et',
           removeMultipleKnots='rmk')
    def extendByDistance(self,
                         distance, *,
                         start=0,
                         extensionType=2,
                         removeMultipleKnots=False):
        """
        :param distance:
        :param start/s: a name or integer for the 'start' enum attribute on the
            ``extendCurve`` node (i.e. one of 0 - 'End', 1 - 'Start',
                2 - 'Both'); defaults to 0 ('End')
        :param extensionType/et: a name or integer for the 'extensionType' enum
            attribute on the ``extendCurve`` node (i.e. one of 0 - 'Linear',
                1 - 'Circular', 2 - 'Extrapolate); defaults to 2 ('Extrapolate')
        :param removeMultipleKnots/rmk: remove multiple knots; defaults to False
        """
        node = nodes['ExtendCurve'].createNode()
        node.setAttrs(extendMethod=0,
                      start=start,
                      extensionType=extensionType,
                      removeMultipleKnots=removeMultipleKnots)
        self >> node.attr('inputCurve1')
        distance >> node.attr('distance')
        return node.attr('outputCurve')

    def retract(self, length):
        """
        Retracts this curve by the given length.

        :param length: the length by which to retract this curve
        """
        targetLength = self.length() - length
        param = self.paramAtLength(targetLength)
        return self.cut(param, keep=0)[0]

    def setLength(self, length, extensionVector):
        nw = nodes['Network'].createNode()
        targetLength = nw.addAttr('targetLength', k=True, i=length, l=True)
        currentLen = nw.addAttr('currentLength',
                                k=True, i=self.length(), l=True)
        extensionVector = nw.addVectorAttr('extensionVector', k=True,
                                           i=extensionVector, l=True)
        tolerance = nw.addAttr('tolerance', k=True, dv=1e-6)

        extension = nw.addAttr('extension', k=True, l=True,
                               i=(targetLength-currentLen).minClamp(tolerance))

        retraction = nw.addAttr('retraction', k=True, l=True,
                               i=(currentLen-targetLength).minClamp(tolerance))

        extensionOutput = self.extendByVector(
            extensionVector.normal() * extension,
            useSegment=True
        )

        retractionOutput = self.retract(retraction)
        T = type(self)

        return extension.gt(tolerance).ifElse(
            extensionOutput,
            retraction.gt(tolerance).ifElse(
                retractionOutput,
                self,
                T
            ),
            T
        )

    def squashStretch(self,
                      squashyAttr,
                      stretchyAttr,
                      globalScale,
                      extensionVector):
        """
        :param squashyAttr: a user attribute which, when at 1.0, will allow the
            curve to overshoot its initial length
        :param stretchyAttr: a user attribute which, when at 1.0, will allow the
            curve to undershoot its initial length
        :param globalScale: a scalar output which will be used to normalize the
            initial curve length
        :param extensionVector: a vector which will be used for curve extensions
            when the curve is undershot; typically extract from a bezier end
            control's world matrix
        :return: The squash-stretched curve output.
        """
        squashyAttr, stretchyAttr, globalScale = map(
            plugs['Attribute'],
            (squashyAttr, stretchyAttr, globalScale)
        )

        liveLen = self.length()
        nativeLen = liveLen() * globalScale

        targetLen = liveLen.gatedClamp(nativeLen,
                                       squashyAttr,
                                       stretchyAttr)
        return self.setLength(targetLen, extensionVector)

    #--------------------------------------|    Distributions

    @short(parametric='par')
    def distributeParams(self, number:int, parametric:bool=False):
        """
        :param number: the number of parameters to generate
        :param parametric/par: distribute in parametric space (calculated once
            against the curve's current knot domain) rather by length; defaults
            to False
        :return: Scalar parameter (u value) outputs.
        """
        if parametric:
            return list(floatrange(*self.knotDomain(), number))
        length = self.length()
        fractions = floatrange(0, 1, number)
        out = []
        padding = len(str(number))
        for i, fraction in enumerate(fractions):
            with _nm.Name(i+1, pad=padding):
                thisLength = length * fraction
                thisParam = self.paramAtLength(thisLength)
                out.append(thisParam)
        return out

    @short(parametric='par')
    def distributePoints(self, number:int, parametric:bool=False):
        return [self.pointAtParam(param) for param
                in self.distributeParams(number, parametric=parametric)]

    @short(parametric='par', normalize='nr')
    def distributeTangents(self,
                           number:int,
                           normalize:bool=False,
                           parametric:bool=False):
        return [self.tangentAtParam(param, normalize=normalize) for param
                in self.distributeParams(number, parametric=parametric)]

    #--------------------------------------|    Closest

    def initClosestNode(self, refPoint):
        refPoint, _, isPlug = _mm.info(refPoint,
                                       (data['Point'], plugs['Point']),
                                       f=True)

        foundNodes = self.outputs(type='nearestPointOnCurve')
        if foundNodes:
            for node in foundNodes:
                plug = node.attr('inPosition')
                inputs = plug.inputs(plugs=True)
                if inputs:
                    if isPlug:
                        if refPoint in inputs:
                            return node
                        continue
                    continue
                else:
                    if not isPlug:
                        if plug().isEquivalent(refPoint):
                            return node
                        continue
                    continue

        node = nodes['NearestPointOnCurve'].createNode()
        self >> node.attr('inputCurve')
        node.attr('inPosition').put(refPoint, isPlug)
        return node

    def closestParam(self, refPoint):
        """
        :param refPoint: the reference point
        :return: The parameter closest to the specified point, as an attribute.
        """
        return self.initClosestNode(refPoint).attr('parameter')

    def closestFraction(self, refPoint):
        param = self.closestParam(refPoint)
        return self.fractionAtParam(param)

    #--------------------------------------|    Bezier-specific

    @cache_dg_output
    def toBezier(self):
        """
        :return: If this is a bezier plug, returns the plug itself; otherwise,
            converts it to a bezier.
        """
        if self.isBezier():
            return self
        node = nodes['NurbsCurveToBezier'].createNode()
        self >> node.attr('inputCurve')
        return node.attr('outputCurve')

    @cache_dg_output
    def toNurbs(self):
        """
        :return: If this is a bezier plug, converts it to NURBS; otherwise,
            returns the plug itself.
        """
        if self.isBezier():
            node = nodes['BezierCurveToNurbs'].createNode()
            self >> node.attr('inputCurve')
            return node.attr('outputCurve')
        return self

    def isBezier(self) -> bool:
        """
        :return: True if this plug is outputting bezier data.
        """
        if self.type() == 'dataBezierCurve':
            return True
        data = self._getData()
        apiType = data.apiType()
        if apiType == 0:
            shape = self.findShape()
            if shape:
                return isinstance(shape, nodes['BezierCurve'])
            return False
        return data.hasFn(om.MFn.kBezierCurveData)