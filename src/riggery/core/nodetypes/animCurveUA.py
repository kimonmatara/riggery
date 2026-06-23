from ..nodetypes import __pool__ as nodes
AnimCurve = nodes['AnimCurve']

import maya.cmds as m


class AnimCurveUA(AnimCurve):

    __time_based__ = False