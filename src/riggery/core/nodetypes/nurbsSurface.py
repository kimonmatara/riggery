from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes
SurfaceShape = nodes['SurfaceShape']

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.functions import short


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
        if worldSpace:
            space = om.MSpace.kWorld
        else:
            space = om.MSpace.kObject

        fn = self.__apimfn__()
        result = fn.closestPoint(om.MPoint(point), space=space)
        return _data['Point'].fromApi(result[0]), result[1], result[2]

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