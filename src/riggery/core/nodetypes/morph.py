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

    def _connectTargetMesh(self,
                           index:int,
                           targetMesh:'nodes.DagNode'):
        targetMesh = nodes['DagNode'](targetMesh).toShape()
        targetMesh.worldOutput >> self.attr('morphTarget')[index]