import riggery.internal.classpool as _cp
import riggery.internal.nodeinfo as _ni


class NodePool(_cp.ClassPool):

    __pool_package__ = __name__

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

        tab = ' '*4

        lines = [
            'from ..nodetypes import __pool__ as nodes',
            "{} = nodes['{}']".format(baseClsName, baseClsName), '',
            'import maya.cmds as m',
            '', '',
            "class {}({}):".format(clsname, baseClsName),
            '', f'{tab}...'
        ]

        return '\n'.join(lines)

__pool__ = NodePool()