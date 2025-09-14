from typing import Iterable
import maya.api.OpenMaya as om

from ..plugtypes import __pool__ as plugs


class NurbsSurface(plugs['Geometry']):

    #-------------------------------------|    Constructor(s)

    @classmethod
    def fromSegmentedLoft(cls, curveInputs:Iterable):
        """
        Does the MPC-style thing of generating a lofted surface by performing
        pairwise lofts and then attaching the surfaces. This prevents EP-style
        overcompensation along the edge.

        :return: The surface output.
        """
        ...

    #-------------------------------------|    Esoteric queries

    def _getData(self) -> om.MObject:
        return self._getSamplingPlug(
            ).asMDataHandle().asNurbsSurfaceTransformed()

