from typing import Union, Optional

from riggery.general.functions import short

from ..elem import Elem
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
DependNode = nodes['DependNode']

import maya.cmds as m


class ProximityFalloff(DependNode):

    #---------------------------------|    Constructor

    @classmethod
    @short(name='n')
    def create(cls,
               geometry:Optional[
                   Union[str, 'nodes.DagNode', 'plugs.Geometry']
               ]=None,
               /,
               name:Optional[str]=None,
               **attrConfig):
        """
        :param geometry: the proximity geometry (plug or node); defaults to None
        :param name/n: an optional explicit name for the node
        :param \*\*attrConfig: optional values or inputs for node attributes
        :return: The configured ``ProximityFalloff`` node.
        """
        node = cls.createNode(name=name, **attrConfig)

        if geometry:
            geometry = Elem(geometry)

            if isinstance(geometry, plugs['Attribute']):
                plug = geometry
            else:
                plug = geometry.toShape().worldOutput

            plug >> node.attr('proximityGeometry')

        return node