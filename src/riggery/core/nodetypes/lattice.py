from ..nodetypes import __pool__ as nodes
ControlPoint = nodes['ControlPoint']

import maya.cmds as m


class Lattice(ControlPoint):
    
    __point_comp_ext__ = 'pt'