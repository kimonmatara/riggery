import re
from typing import Optional, Literal
from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..elem import Elem
SurfaceShape = nodes['SurfaceShape']

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.functions import short
from riggery.general.numbers import floatrange
from riggery.general.iterables import without_duplicates, expand_tuples_lists
from riggery.core.lib.mixedmode import MixedScalar


class NurbsSurface(SurfaceShape):

    __point_comp_ext__ = 'cv'

    #-------------------------------------|    Constructors

    @classmethod
    @short(worldSpace='ws')
    def createBoundary(cls,
                       curve1,
                       curve2,
                       curve3,
                       curve4,
                       worldSpace:bool=False,
                       order:bool=True,
                       endPoint:bool=False) -> 'NurbsSurface':
        """Creates a boundary surface."""
        curve1 = Elem(curve1).toPlug(worldSpace=worldSpace)
        return curve1.boundary(curve2, curve3, curve4,
                               endPoint=endPoint,
                               order=order,
                               worldSpace=worldSpace).createShape()

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

    def knotsInU(self) -> tuple[float, float]:
        return self.__apimfn__().knotsInU()

    def knotsInV(self) -> tuple[float, float]:
        return self.__apimfn__().knotsInV()

    def numPatchesInU(self) -> int:
        return self.__apimfn__().numPatchesInU

    def numPatchesInV(self) -> int:
        return self.__apimfn__().numPatchesInV

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

    #-------------------------------------|    Geo editing

    @classmethod
    def _conformPatchArgs(cls, *args) -> list[tuple[int, int]]:
        args = expand_tuples_lists(*args, keep_tuples=True)
        out = []

        pat = re.compile(r"^(?:.*?\.)?sf\[(.*?)\]\[(.*?)\]$")

        for arg in args:
            if isinstance(arg, str):
                indices = tuple(map(int, re.match(pat, arg).groups()))
                out.append(indices)
            elif (isinstance(arg, tuple)
                  and len(arg) == 2
                  and all((isinstance(x, int) for x in arg))):
                out.append(arg)
            else:
                raise TypeError("can't parse: ", arg)

        return out

    def patchesToUVRange(self,
                         *patches,
                         precision:int=6) -> tuple[float, float, float, float]:
        """
        :param patches: patch components, e.g. "shape.sf[4][2:4]" etc. Only
            indices are parsed; the node component is discarded.
        :return: minU, maxU, minV, maxV
        """
        indexPairs = self._conformPatchArgs(*patches)
        uIndices, vIndices = zip(*indexPairs)

        degU = self.degreeInU()
        degV = self.degreeInV()

        knotsU = self.knotsInU()
        knotsV = self.knotsInV()

        uMin = knotsU[min(uIndices) + degU - 1]
        uMax = knotsU[max(uIndices) + degU]
        vMin = knotsV[min(vIndices) + degV - 1]
        vMax = knotsV[max(vIndices) + degV]

        uMin, uMax, vMin, vMax = ((round(x, precision)
                                   for x in (uMin, uMax, vMin, vMax)))

        return uMin, uMax, vMin, vMax

    def extractPatchBoundingBox(self, *patches, separate:bool=False):
        """
        :param patches: patch components, e.g. "shape.sf[4][2:4]" etc. Only
            indices are parsed; the node component is discarded.
        """
        if separate:
            stream = self.getOutput(worldSpace=worldSpace)
        else:
            stream = self.getHistoryInput(create=True)

        uMin, uMax, vMin, vMax = self.patchesToUVRange(*patches)

        stream = stream.trimStart(
            uMin, 'u').trimEnd(
            uMax, 'u').trimStart(
            vMin, 'v').trimEnd(
            vMax, 'v'
        )

        if separate:
            return stream.createShape()

        stream >> self.input
        return self

    #-------------------------------------|    Tessellate

    def slidyTessellate(self, uNumber, vNumber):
        """
        Performs a slidy tessellation and returns a new shape.
        """
        return self.worldOutput.slidyTessellate(uNumber,
                                                vNumber).createShape()

    #-------------------------------------|    Rebuilds

    def rebuildUniform(self,
                       spansU:MixedScalar,
                       spansV:MixedScalar):
        """
        Quickly applies a cubic uniform rebuild.
        :return: ``self``
        """
        historyInput = self.getHistoryInput(create=True)
        node = nodes.RebuildSurface.createNode()

        for k, v in {'spansU': spansU,
                     'spansV': spansV,
                     'rebuildType': 'Uniform',
                     'degreeU': 3,
                     'degreeV': 3,
                     'direction': 2,
                     'endKnots': 1,
                     'keepRange': 2,
                     'keepCorners': 0,
                     'keepControlPoints': 0}.items():
            node.attr(k).put(v)

        historyInput >> node.attr('inputSurface')
        node.attr('outputSurface') >> self.input
        return self

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