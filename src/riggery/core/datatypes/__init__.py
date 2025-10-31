import riggery.internal.classpool as _cp
import riggery.internal.datainfo as _di

STUB_TEMPLATE = \
"""\
from ..datatypes import __pool__ as data
{} = data['{}']


class {}({}):

    ..."""


class DataPool(_cp.ClassPoolWithInvention):

    def _initStubContent(self, clsname:str):
        baseClsName = _di.getPathFromKey(clsname)[-2]
        args = [baseClsName, baseClsName, clsname, baseClsName]

        if clsname == 'Tensor':
            args[3] = "{}, list".format(baseClsName)

        return STUB_TEMPLATE.format(*args)

    def _checkKey(self, key):
        if key not in _di.DATA_TREE:
            raise _cp.CpInvalidKeyError(f"Unrecognized data type: '{key}'")

    def _inventClass(self, clsname:str):
        if clsname == 'Data':
            return type(clsname, (), {})
        baseClsName = _di.getPathFromKey(clsname)[-2]
        baseCls = self[baseClsName]
        return type(baseCls)(clsname, (baseCls, ), {})


__pool__ = DataPool()