import maya.api.OpenMaya as om

from ..plugtypes import __pool__ as plugs


class NurbsSurface(plugs['Geometry']):

    def _getData(self) -> om.MObject:
        return self._getSamplingPlug(
            ).asMDataHandle().asNurbsSurfaceTransformed()