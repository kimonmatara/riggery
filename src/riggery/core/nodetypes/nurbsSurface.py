from ..nodetypes import __pool__ as nodes
SurfaceShape = nodes['SurfaceShape']

import maya.api.OpenMaya as om
import maya.cmds as m


class NurbsSurface(SurfaceShape):
    
    #-------------------------------------|    Geometry queries

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