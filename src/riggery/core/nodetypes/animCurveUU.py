from ..nodetypes import __pool__ as nodes
AnimCurve = nodes['AnimCurve']

import maya.cmds as m


class AnimCurveUU(AnimCurve):

    __time_based__ = False