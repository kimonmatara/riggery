from ..nodetypes import __pool__ as nodes
import maya.cmds as m


class SurfaceShape(nodes['ControlPoint']):

    def assignDefaultShader(self):
        m.sets(str(self), fe='initialShadingGroup')
        return self