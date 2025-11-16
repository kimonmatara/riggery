from typing import Literal, Union, Iterator

from ..nodetypes import __pool__ as nodes
GeometryFilter = nodes['GeometryFilter']

import maya.cmds as m


class SkinCluster(GeometryFilter):

    #-------------------------------------|    Influence management

    def getInfluence(self) -> list:
        """
        :return: The list of influences driving this skin cluster.
        """
        return list(self.influences)

    @property
    def influences(self) -> Iterator['nodes.Joint']:
        out = m.skinCluster(str(self), q=True, influence=True)

        if out:
            for x in out:
                yield nodes['DependNode'](x)