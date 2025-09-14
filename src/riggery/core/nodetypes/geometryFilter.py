from typing import Generator
from ..nodetypes import __pool__ as nodes
DependNode = nodes['DependNode']

import maya.cmds as m


class GeometryFilter(DependNode):

    #-------------------------------------|    Retrievals

    @classmethod
    def fromGeo(cls, geo) -> Generator:
        """
        Yields deformers of this type in the specified geometry's history. Use
        next([...], None) to get the first result or None.
        """
        geo = nodes['DependNode'](geo).toShape()
        history = m.listHistory(geo, fullNodeName=True, historyAttr=True)
        visited = set()
        if history:
            for item in history:
                if item in visited:
                    continue
                try:
                    if m.objectType(item, isAType=cls.__melnode__):
                        visited.add(item)
                        yield DependNode(item)
                except:
                    continue