from typing import Union, Optional
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
Transform = nodes['Transform']

import maya.cmds as m


class PrimitiveFalloff(Transform):
    
    #---------------------------------|    Constructor

    @classmethod
    @short(name='n')
    def create(cls,
               primitive:Literal[0, 1, 'sphere', 'plane', 'Sphere', 'Plane']=0,
               *,
               name:Optional[str]=None,
               **attrConfig):
        """
        Basic constructor.

        :param name/n: an optional explicit name for the node
        :param \*\*attrConfig: optional values or inputs for node attributes
        :return: The configured ``PrimitiveFalloff`` node.
        """
        node = cls.createNode(name=name)
        for k, v in attrConfig.items():
            node.attr(k).put(v)

        return node