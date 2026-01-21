from ..nodetypes import __pool__ as nodes
SurfaceShape = nodes['SurfaceShape']

import maya.cmds as m


class Mesh(SurfaceShape):

    #-------------------------------------|    Queries

    def numVertices(self) -> int:
        """:return: The number of vertices on this mesh."""
        return self.__apimfn__().numVertices

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

    def getUVSets(self) -> list[str]:
        out = m.polyUVSet(str(self), q=True, allUVSets=1)
        if out:
            return out
        return []