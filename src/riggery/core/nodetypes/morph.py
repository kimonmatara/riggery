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
        node._connectBaseMesh(0, baseMesh)

        if targetMesh:
            node._connectTargetMesh(0, targetMesh)

        for k, v in nodeAttrs.items():
            node.attr(k).put(v)

        return node

    #---------------------------------|    DG util

    def _connectBaseMesh(self,
                         index:int,
                         baseMesh:'nodes.DagNode',
                         origShape:Optional['nodes.Mesh']=None):
        baseMesh = nodes['DagNode'](baseMesh).toShape()

        if origShape:
            origShape = nodes['DagNode'](origShape).toShape()
        else:
            origShape = baseMesh.getOrigShape(create=True)

        origShape.localOutput >> self.attr('originalGeometry')[index]
        origShape.worldOutput >> self.attr('input')[index].attr('inputGeometry')
        self.attr('outputGeometry')[index] >> baseMesh.input

    def _connectTargetMesh(self,
                           index:int,
                           targetMesh:'nodes.DagNode'):
        targetMesh = nodes['DagNode'](targetMesh).toShape()
        targetMesh.worldOutput >> self.attr('morphTarget')[index]

    #---------------------------------|    Weights

    def getWeights(self, index:int) -> list[float]:
        plug = self.attr('weightList')
        return plug[index].attr('weights'
                                ).readWeightsMulti(self.numPoints(index), 1.0)

    def setWeights(self, index:int, weights:list[float]):
        plug = self.attr('weightList')
        plug[index].attr('weights').writeWeightsMulti(weights)
        return self