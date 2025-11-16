from ..nodetypes import __pool__ as nodes
SurfaceShape = nodes['SurfaceShape']

import maya.cmds as m


class Mesh(SurfaceShape):

    #-------------------------------------|    UV set get / set
    
    def getUVSet(self) -> str:
        """Returns the name of the current UV set."""
        return m.polyUVSet(str(self), q=True, currentUVSet=True)

    getCurrentUVSetName = getUVSet # for parity with PyMEL

    def setUVSet(self, uvSet:str):
        """Sets the current UV set."""
        m.polyUVSet(str(self), e=True, currentUVSet=uvSet)
        return self

    setCurrentUVSetName = setUVSet # for parity with PyMEL

    uvSet = property(getUVSet, setUVSet)