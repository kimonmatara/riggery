from ..nodetypes import __pool__ as nodes
DependNode = nodes['DependNode']

import maya.cmds as m


class UvPin(DependNode):
    
    """
    Useful notes:
    outputMatrix X is the normal
    outputMatrix Z is the U tangent
    """