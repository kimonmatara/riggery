from typing import Optional
from riggery.general.functions import short
from riggery.general.modules import LazyModule
from riggery.core.lib import names as _nm
from ..nodetypes import __pool__ as nodes
PolyModifier = nodes['PolyModifier']

import maya.cmds as m
r = LazyModule('riggery.core')


class PolySmoothFace(PolyModifier):

    __node_defaults__ = {'method': 'Exponential',
                         'subdivisionType': 'OpenSubdiv Catmull-Clark',
                         'divisions': 1,
                         'osdVertBoundary': 1,
                         'osdFvarBoundary': 3,
                         'osdFvarPropagateCorners': 0,
                         'osdSmoothTriangles': 0,
                         'osdCreaseMethod': 0,
                         'continuity': 1.0,
                         'smoothUVs': True,
                         'keepBorder': True,
                         'keepSelectionBorder': False,
                         'keepHardEdge': False,
                         'propagateEdgeHardness': False,
                         'keepTessellation': True,
                         'keepMapBorders': 1,
                         'boundaryRule': 1}


    @classmethod
    @short(name='n')
    def createNode(cls, *, name:Optional[str]=None, **attrs):
        # Using a dummy because, for some reason, can't get the node to kick in
        # without running a command

        name = _nm.resolveNameArg(name, nodeType=cls.__melnode__)

        dummy = r.polyCube(w=1, h=1, d=1, sd=1, sh=1, sw=1, nds=1, n=name)[0]
        node = r.polySmooth(dummy)[0]
        node.attr('inputPolymesh').disconnect(inputs=True)
        node.attr('output').disconnect(outputs=True)
        r.delete(dummy)

        settings = cls.__node_defaults__.copy()
        settings.update(**attrs)

        for k, v in settings.items():
            node.attr(k).put(v)

        node.attr('nds').set(0)

        return node