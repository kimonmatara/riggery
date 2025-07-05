import maya.api.OpenMaya as om

from ..plugtypes import __pool__


class SubdSurface(__pool__['Geometry']):

    __shape_class_name__ = 'Subdiv'

    def _getData(self) -> om.MObject:
        return self._getSamplingPlug(
            ).asMDataHandle().asSubdSurfaceTransformed()