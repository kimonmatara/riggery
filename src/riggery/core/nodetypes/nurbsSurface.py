from typing import Optional, Literal
from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes
SurfaceShape = nodes['SurfaceShape']

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.functions import short
from riggery.general.numbers import floatrange


class NurbsSurface(SurfaceShape):

    #-------------------------------------|    Geometry queries

    @short(worldSpace='ws')
    def closestPoint(self,
                     point:'_data.Point',
                     worldSpace:bool=False
                     ) -> tuple['_data.Point', float, float]:
        """
        :param point: the reference point
        :param worldSpace/ws: calculate in world-space; defaults to False
        :return: Tuple of point, u param, v param
        """
        point = _data['Point'](point)

        fn = self.__apimfn__(dag=True)

        point, u, v = fn.closestPoint(
            point.api,
            space=om.MSpace.kWorld if worldSpace else om.MSpace.kObject
        )

        return _data['Point'].fromApi(point), u, v

    def numCVs(self) -> int:
        """:return: The number of CVs on this surface."""
        fn = self.__apimfn__()

        cvsU = fn.numCVsInU
        cvsV = fn.numCVsInV
        formU = fn.formInU
        formV = fn.formInV

        if formU == om.MFnNurbsSurface.kPeriodic:
            cvsU -= fn.degreeInU

        if formV == om.MFnNurbsSurface.kPeriodic:
            cvsV -= fn.degreeInV

        return cvsU * cvsV

    numVertices = numCVs

    def knotDomainInU(self) -> tuple[float, float]:
        """Returns the min / max U parameters."""

        return self.__apimfn__().knotDomainInU

    def knotDomainInV(self) -> tuple[float, float]:
        """Returns the min / max V parameters."""

        return self.__apimfn__().knotDomainInV

    def formInU(self) -> Literal[1, 2, 3]:
        """
        kOpen: 1
        kClosed: 2
        kPeriodic: 3
        """
        return self.__apimfn__().formInU

    def formInV(self) -> Literal[1, 2, 3]:
        """
        kOpen: 1
        kClosed: 2
        kPeriodic: 3
        """
        return self.__apimfn__().formInV

    def degreeInU(self) -> int:
        return self.__apimfn__().degreeInU

    def degreeInV(self) -> int:
        return self.__apimfn__().degreeInV

    @short(visible='v')
    def numCVsInU(self, visible:bool=False) -> int:
        """
        :param visible/v: accounts for periodic form and subtracts the number of
            invisible 'overlap' CVs; defaults to False
        """
        out = self.__apimfn__().numCVsInU

        if visible:
            if self.formInU() == 3:
                out -= self.degreeInU()

        return out

    @short(visible='v')
    def numCVsInV(self, visible:bool=False) -> int:
        """
        :param visible/v: accounts for periodic form and subtracts the number of
            invisible 'overlap' CVs; defaults to False
        """
        out = self.__apimfn__().numCVsInV

        if visible:
            if self.formInV() == 3:
                out -= self.degreeInV()

        return out

    def cvUVIndexToFlatIndex(self, uIndex:int, vIndex:int) -> int:
        """
        Given a standard U, V CV index, returns a flat CV index (e.g. as on
        ``surfaceInfo.controlPoints`` arrays).
        """
        return (uIndex * self.numCVsInV()) + vIndex

    def cvFlatIndexToUVIndex(self, flatIndex:int) -> tuple[int, int]:
        """
        Given a flat CV index (e.g. as on ``surfaceInfo.controlPoints`` arrays),
        returns the U, V index.
        """
        numCVsV = self.numCVsInV()
        u = flatIndex // numCVsV
        v = flatIndex % numCVsV
        return (u, v)

    #-------------------------------------|    Misc sampling

    @short(plug='p',
           worldSpace='ws')
    def pointAtCV(self,
                  uIndex:int,
                  vIndex:int,
                  plug:bool=False,
                  worldSpace:bool=False):
        if plug:
            if worldSpace:
                output = self.attr('worldSpace')[0]
            else:
                output = self.attr('local')

            return output.info().attr(
                'controlPoints')[self.cvUVIndexToFlatIndex(uIndex, vIndex)]

        return _data['Point'](m.pointPosition(
            '{}.cv[{}][{}]'.format(self, uIndex, vIndex),
            world=worldSpace
        ))

    # @short(minU='mnu',
    #        maxU='mxu',
    #        minV='mnv',
    #        maxV='mxv')
    # def distributeParams(self,
    #                      numU,
    #                      numV,
    #                      minU:Optional[float]=None,
    #                      maxU:Optional[float]=None,
    #                      minV:Optional[float]=None,
    #                      maxV:Optional[float]=None):
    #     ...