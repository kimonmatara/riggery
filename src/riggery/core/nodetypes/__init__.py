"""The main class pool for node types."""

from riggery.internal.classpool import ClassPoolWithInvention
import riggery.internal.nodeinfo as _ni

STUB_TEMPLATE = \
"""\
from ..nodetypes import __pool__ as nodes
{} = nodes['{}']

import maya.cmds as m


class {}({}):
    
    ..."""


class NodePool(ClassPoolWithInvention):

    #-------------------------------------|    Invention

    def _inventClass(self, clsname:str):
        # 'DependNode' should *always* exist under plugtypes
        baseClsName = _ni.getPathFromKey(clsname)[-2]
        baseCls = self[baseClsName]

        return type(baseCls)(clsname, (baseCls,), {})

    #-------------------------------------|    Stubbing

    def _getModBasenameFromClsName(self, clsname:str) -> str:
        return _ni.UNCAPMAP.get(clsname, clsname[0].lower()+clsname[1:])

    def _initStubContent(self, clsname:str):
        if clsname == 'DependNode':
            raise RuntimeError("'DependNode' cannot be stubbed.")

        baseClsName = _ni.getPathFromKey(clsname)[-2]

        return STUB_TEMPLATE.format(baseClsName, baseClsName, clsname,
                                    baseClsName)

__pool__ = NodePool()