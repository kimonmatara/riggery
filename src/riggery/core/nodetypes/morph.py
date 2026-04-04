from typing import Union, Optional, Literal
from riggery.general.functions import short

from ..nodetypes import __pool__ as nodes
WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m


class Morph(WeightGeometryFilter):

    #---------------------------------|    Constructor

    @classmethod
    @short(name='n')
    def create(cls,
               baseMesh:'nodes.DagNode',
               targetMesh:Optional['nodes.DagNode']=None, /,
               name:Optional[str]=None,
               **nodeAttrs):
        node = cls.createNode(name=name)
        node.connectGeometry(0, baseMesh)

        if targetMesh:
            node.connectTargetMesh(0, targetMesh)

        for k, v in nodeAttrs.items():
            node.attr(k).put(v)

        return node

    #---------------------------------|    DG util

    def connectTargetMesh(self,
                          index:int,
                          targetMesh:'nodes.DagNode'):
        targetMesh = nodes['DagNode'](targetMesh).toShape()
        targetMesh.worldOutput >> self.attr('morphTarget')[index]
        return self

    #---------------------------------|    Weights

    def getWeights(self, index:int) -> list[float]:
        plug = self.attr('weightList')
        return plug[index].attr('weights'
                                ).readWeights(self.numPoints(index), 1.0)

    def setWeights(self, index:int, weights:list[float]):
        plug = self.attr('weightList')
        plug[index].attr('weights').writeWeights(weights)
        return self