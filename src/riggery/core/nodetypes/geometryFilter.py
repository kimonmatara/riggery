from typing import Iterator
from ..nodetypes import __pool__ as nodes
DependNode = nodes['DependNode']

import maya.cmds as m


class GeometryFilter(DependNode):

    #-------------------------------------|    Constructors

    @classmethod
    def fromGeo(cls, geo) -> Iterator['GeometryFilter']:
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

    #-------------------------------------|    Shapes

    @property
    def shapes(self) -> Iterator['GeometryFilter']:
        """
        Iterates over shapes affected by this deformer.
        """
        out = m.deformer(str(self), q=True, g=True)

        if out:
            for x in out:
                yield nodes['DependNode'](x)