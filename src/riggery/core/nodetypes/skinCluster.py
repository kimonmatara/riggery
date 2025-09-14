from ..nodetypes import __pool__ as nodes
GeometryFilter = nodes['GeometryFilter']

import maya.cmds as m


class SkinCluster(GeometryFilter):

    #-------------------------------------|    Influence management

    def getInfluence(self) -> list:
        """
        :return: The list of influences driving this skin cluster.
        """
        out = m.skinCluster(str(self), q=True, influence=True)
        if out:
            return list(map(nodes['DependNode'], out))
        return []