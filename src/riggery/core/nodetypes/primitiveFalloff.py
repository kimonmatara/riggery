from typing import Union, Optional, Literal

from riggery.general.functions import short

from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from .falloffBase import FalloffBase

Transform = nodes['Transform']

import maya.cmds as m


class PrimitiveFalloff(FalloffBase, Transform):
    
    #---------------------------------|    Constructor

    @classmethod
    @short(name='n')
    def create(cls,
               primitive:Literal[0, 1, 'Sphere', 'Plane']=0,
               *,
               name:Optional[str]=None,
               **attrConfig):
        """
        Basic constructor.

        :param name/n: an optional explicit name for the node
        :param primitive: the primitive type; one of 0, 1, 'Sphere' or 'Plane';
            defaults to 0
        :param \*\*attrConfig: optional values or inputs for node attributes
        :return: The configured ``PrimitiveFalloff`` node.
        """
        return cls.createNode(name=name, primitive=primitive, **attrConfig)