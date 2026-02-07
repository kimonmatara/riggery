from typing import Iterable, Literal, Optional, Iterator
import maya.api.OpenMaya as om

from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from riggery.general.functions import short
from ..lib import mathops as _mo
from ..lib import mixedmode as _mm
from riggery.general.iterables import expand_tuples_lists


class NurbsSurface(plugs['Geometry']):

    #-------------------------------------|    Static queries

    def _getData(self) -> om.MObject:
        return self._getSamplingPlug(
        ).asMDataHandle().asNurbsSurfaceTransformed()

    def __datamfn__(self) -> om.MFnNurbsSurface:
        return om.MFnNurbsSurface(self._getData())

    def numCVs(self) -> int:
        fn = self.__datamfn__()

        cvsU = fn.numCVsInU
        cvsV = fn.numCVsInV
        formU = fn.formInU
        formV = fn.formInV

        if formU == om.MFnNurbsSurface.kPeriodic:
            cvsU -= fn.degreeInU

        if formV == om.MFnNurbsSurface.kPeriodic:
            cvsV -= fn.degreeInV

        return cvsU * cvsV

    def iterCVPoints(self) -> Iterator['plugs.Point']:
        info = self.info()
        output = info.attr('controlPoints')

        for i in range(self.numCVs()):
            yield output[i]

    cvPoints = property(iterCVPoints)

    #-------------------------------------|    Cut / glue

    @short(method='m',
           blendBias='bb',
           blendKnotInsertion='bki',
           parameter='p',
           keepMultipleKnots='kmk',
           directionU='du',
           reverse1='rv1',
           reverse2='rv2',
           swap1='sw1',
           swap2='sw2',
           twist='tw')
    def attach(self,
               other,
               method=0,
               blendBias=0.5,
               parameter=0.1,
               blendKnotInsertion=False,
               keepMultipleKnots=True,
               directionU=True,
               reverse1=False,
               reverse2=False,
               swap1=False,
               swap2=False,
               twist=False):
        """
        :param method/m: one of 0 ('Connect') or 1 ('Blend'), or an input
        :param blendBias/bb: skew the result toward the first or the second
            curve depending on the blend factory being smaller or larger than
            0.5; defaults to 0.5
        :param parameter/p: the parameter value for the positioning of the newly
            inserted knot; defaults to 0.1
        :param keepMultipleKnots/kmk: if true, keep multiple knots at the join
            parameter; defaults to True
        :param directionU/du: if True attach in U direction of surface and V
            direction otherwise; defaults to True
        :param reverse1/r1: reverse the direction (specified by directionU) of
            the first input surface before doing attach; defaults to False
        :param reverse2/r2: reverse the direction (specified by directionU) of
            the second input surface before doing attach; defaults to False
        :param swap1/sw1: swap the UV directions of the first input surface
            before doing attach; defaults to False
        :param swap2/sw2: swap the UV directions of the second input surface
            before doing attach; defaults to False
        :param twist/tw: reverse the second surface in the opposite direction
            (specified by directionU) before doing attach; defaults to False
        :return: The joined surface.
        """
        other = self.conformToOutput(other)
        node = nodes['AttachSurface'].createNode()
        method >> node.attr('method')
        blendBias >> node.attr('blendBias')
        blendKnotInsertion >> node.attr('blendKnotInsertion')
        keepMultipleKnots >> node.attr('keepMultipleKnots')
        directionU >> node.attr('directionU')
        reverse1 >> node.attr('reverse1')
        reverse2 >> node.attr('reverse2')
        swap1 >> node.attr('swap1')
        swap2 >> node.attr('swap2')
        twist >> node.attr('twist')

        self >> node.attr('inputSurface1')
        other >> node.attr('inputSurface2')
        return node.attr('outputSurface')

    @short(keep='k')
    def detach(self,
               parameter,
               direction:Literal[0, 1, 'U', 'V']=1,
               keep:Optional[Iterable]=None) -> list:

        node = nodes['DetachSurface'].createNode()
        node.attr('direction').set(direction)
        self >> node.attr('inputSurface')

        for i, parameter in enumerate(expand_tuples_lists(parameter)):
            parameter >> node.attr('parameter')[i]

        node.attr('outputSurface').evaluate()

        if keep is None:
            return list(node.attr('outputSurface'))

        if isinstance(keep, (tuple, list)):
            return [node.attr('outputSurface')[i] for i in keep]

        return node.attr('outputSurface')[keep]

    #-------------------------------------|    Curves

    def extractCurve(self, param, v=False):
        """
        Note that, if you're setting this up from a returned closestPoint, the
        correspondence between the U, V of the point and the extractor here is
        reversed, so set *v* accordingly.

        :param param: the isoparm value
        :param v: whether to extract in the V rather than the U direction;
            defaults to False
        """
        node = nodes['CurveFromSurfaceIso'].createNode()
        self >> node.attr('inputSurface')
        param >> node.attr('isoparmValue')
        v >> node.attr('isoparmDirection')

        return node.attr('outputCurve')

    #-------------------------------------|    Surface-level sampling

    def info(self) -> 'nodes.SurfaceInfo':
        """Creates, or retrieves, a surfaceInfo node on this plug."""
        node = next(iter(self.outputs(type='surfaceInfo')), None)

        if node is None:
            node = nodes['SurfaceInfo'].createNode()
            self >> node.attr('inputSurface')

        return node

    #-------------------------------------|    Sampling (per-param)

    def infoAtParam(self,
                    paramU:_mm.MixedScalar,
                    paramV:_mm.MixedScalar) -> 'nodes.PointOnSurfaceInfo':
        """Creates, or retrieves, a pointOnSurfaceInfo node on this plug."""
        paramU, _, paramUIsPlug = _mm.info(paramU)
        paramV, _, paramVIsPlug = _mm.info(paramV)

        for posi in self.outputs(type='pointOnSurfaceInfo'):
            if posi.attr('turnOnPercentage')():
                continue

            thisParamU, thisParamUIsPlug = posi.attr('parameterU'
                                                     ).getInputOrValue()

            if (((paramUIsPlug and thisParamUIsPlug)
                 or not (paramUIsPlug or thisParamUIsPlug))
                    and paramU == thisParamU):

                thisParamV, thisParamVIsPlug = posi.attr('parameterV'
                                                         ).getInputOrValue()

                if (((paramVIsPlug and thisParamVIsPlug)
                     or not (paramVIsPlug or thisParamVIsPlug))
                        and paramV == thisParamV):
                    return posi

        posi = nodes['PointOnSurfaceInfo'].createNode()
        paramU >> posi.attr('parameterU')
        paramV >> posi.attr('parameterV')
        self >> posi.attr('inputSurface')
        return posi

    def pointAtParam(self,
                     paramU:_mm.MixedScalar,
                     paramV:_mm.MixedScalar) -> 'plugs.Point':
        """
        :return: The point. If a sample already exists for the given u, v, it is
            reused.
        """
        return self.infoAtParam(paramU, paramV).attr('position')

    def normalAtParam(self,
                      paramU:_mm.MixedScalar,
                      paramV:_mm.MixedScalar,
                      normalize:bool=False) -> 'plugs.Vector':
        """
        :return: The normal. If a sample already exists for the given u, v, it
            is reused.
        """
        return self.infoAtParam(paramU, paramV).attr(
            'normalizedNormal' if normalize else 'normal'
        )

    def tangentUAtParam(self,
                        paramU:_mm.MixedScalar,
                        paramV:_mm.MixedScalar,
                        normalize:bool=False) -> 'plugs.Vector':
        """
        :return: The U tangent. If a sample already exists for the given u, v,
            it is reused.
        """
        return self.infoAtParam(paramU, paramV).attr(
            'normalizedTangentU' if normalize else 'tangentU'
        )

    def tangentVAtParam(self,
                        paramU:_mm.MixedScalar,
                        paramV:_mm.MixedScalar,
                        normalize:bool=False) -> 'plugs.Vector':
        """
        :return: The V tangent. If a sample already exists for the given u, v,
            it is reused.
        """
        return self.infoAtParam(paramU, paramV).attr(
            'normalizedTangentV' if normalize else 'tangentV'
        )

    @short(manageScale='ms',
           normalLength='nl',
           resetLengths='rl')
    def matrixAtParam(
            self,
            paramU:_mm.MixedScalar,
            paramV:_mm.MixedScalar,

            axis1:Literal['x', 'y', 'z', '-x', '-y', '-z'],
            ref1:Literal['u', 'v', 'n'],
            axis2:Literal['x', 'y', 'z', '-x', '-y', '-z'],
            ref2:Literal['u', 'v', 'n'],

            axis3:Optional[Literal['x', 'y', 'z', '-x', '-y', '-z']]=None,
            ref3:Optional[Literal['u', 'v', 'n']]=None, /,

            manageScale:bool=True,
            normalLength:Optional[_mm.MixedScalar]=None,
            resetLengths:bool=False
    ):
        """
        If three (axis, ref pairs) are provided, a *skew* matrix will be
        returned. Otherwise, the matrix will be orthogonal.

        :param paramU: the U parameter (value or plug)
        :param paramV: the V parameter (value or plug)
        :param axis1: the axis to map *ref1* to, one of 'x', 'y', 'z', '-x',
            '-y', '-z'
        :param ref1: the surface component to use for *axis1*; one of 'u', 'v',
            'n'
        :param axis2: the axis to map *ref2* to, one of 'x', 'y', 'z', '-x',
            '-y', '-z'
        :param ref2: the surface component to use for *axis2*; one of 'u', 'v',
            'n'
        :param axis3: the axis to map *ref1* to, one of 'x', 'y', 'z', '-x',
            '-y', '-z'; defaults to None
        :param ref3: the surface component to use for *axis1*; one of 'u', 'v',
            'n'; defaults to None
        :param manageScale/ms: set this to False if you're not interested in
            axis lengths at all, and want to save on some calcs; defaults to
            True
        :param normalLength/nl: ignored if *manageScale* is False; sets the
            length of axis mapped to the surface normal (reference 'n');
            defaults to None (1.0)
        :param resetLength/rl: ignored if *manageScale* is False; normalizes the
            axis vectors *once*, but preserves dynamic scaling; defaults to
            False
        """
        #--------------------|    Gather info

        ortho = axis3 is None or ref3 is None
        refToAttr = {'u': 'tangentU', 'v': 'tangentV', 'n': 'normal'}

        info = self.infoAtParam(paramU, paramV)

        # 1
        ref1Content = info.attr(refToAttr[ref1])

        if '-' in axis1:
            axis1 = axis1.strip('-')
            ref1Content = ref1Content * -1

        # 2
        ref2Content = info.attr(refToAttr[ref2])

        if '-' in axis2:
            axis2 = axis2.strip('-')
            ref2Content = ref2Content * -1

        # 3
        if ortho:
            ref3 = next(iter({'u', 'v', 'n'} - {ref1, ref1}))
            axis3 = next(iter({'x', 'y', 'z'} - {axis1, axis2}))

        ref3Content = info.attr(refToAttr[ref3])

        if '-' in axis3:
            axis3 = axis.strip('-')
            ref3Content = ref3Content * -1

        #--------------------|    Ortho base matrix construction

        if ortho:
            matrix = _mo.createOrthoMatrix(axis1, ref1Content,
                                           axis2, ref2Content,
                                           w=info.attr('position'))
        else:
            ff = nodes['FourByFourMatrix'].createNode()
            ref1Content >> getattr(ff, axis1)
            ref2Content >> getattr(ff, axis2)
            ref3Content >> getattr(ff, axis3)
            info.attr('position') >> ff.w
            matrix = ff.attr('output')

        #--------------------|    Scale management

        if manageScale:
            matrix = matrix.pick(t=True,
                                 r=True,
                                 s=False,
                                 sh=not ortho)
            factors = {}

            for axis, ref, refContent in zip(
                    (axis1, axis2, axis3),
                    (ref1, ref2, ref3),
                    (ref1Content, ref2Content, ref3Content)
            ):
                if ref in 'uv':
                    mag = refContent.length()

                    if resetLengths:
                        mag = mag / mag()
                else:
                    if normalLength is None:
                        mag = 1.0
                    else:
                        mag = _mm.conform(normalLength)

                        if resetLengths:
                            mag = mag / mag()

                factors[axis] = mag

            factors = [factors[k] for k in 'xyz']
            smtx = _mm.createScaleMatrix(*factors)
            matrix = smtx * matrix

        return matrix