from ..nodetypes import __pool__ as nodes
SurfaceShape = nodes['SurfaceShape']

import maya.cmds as m


class Mesh(SurfaceShape):
    
    def getUVSet(self) -> str:
        """Returns the name of the current UV set."""
        return m.polyUVSet(str(self), q=True, currentUVSet=True)

    def setUVSet(self, uvSet:str):
        """Sets the current UV set."""
        m.polyUVSet(str(self), e=True, currentUVSet=uvSet)
        return self

    uvSet = property(getUVSet, setUVSet)