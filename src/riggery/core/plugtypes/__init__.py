import riggery.internal.classpool as _cp
from riggery.internal.plugutil.plugtree import DATA as PLUG_TREE
import riggery.internal.plugutil.plugroute as _pr


class PlugPool(_cp.ClassPool):

    __pool_package__ = __name__

    #-------------------------------------|    Validation

    def _checkKey(self, key:str):
        if key not in PLUG_TREE:
            raise _cp.CpInvalidKeyError(f"Unrecognized plug type: '{key}'")

    #-------------------------------------|    Invention

    def _inventClass(self, clsname:str):
        # 'Attribute' should *always* exist under plugtypes
        baseClsName = _pr.getPathFromKey(clsname)[-2]
        baseCls = self[baseClsName]

        return type(baseCls)(clsname, (baseCls,), {})

    #-------------------------------------|    Stubbing

    def _initStubContent(self, clsname:str):
        if clsname == 'Attribute':
            raise TypeError("Stubbing not supported for 'Attribute'")

        baseClsName = _pr.getPathFromKey(clsname)[-2]
        tab = ' '*4

        lines = [
            "from ..plugtypes import __pool__ as plugs",
            "{} = plugs['{}']".format(baseClsName, baseClsName),
            '',
            "import maya.cmds as m",
            '', '',
            "class {}({}):".format(clsname, baseClsName),
            '',
            f'{tab}...'
        ]

        return '\n'.join(lines)

__pool__ = PlugPool()