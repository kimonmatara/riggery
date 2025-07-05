import riggery.internal.classpool as _cp
import riggery.internal.datainfo as _di


class DataPool(_cp.ClassPool):

    __pool_package__ = __name__

    def _initStubContent(self, clsname:str):
        baseClsName = _di.getPathFromKey(clsname)[-2]
        tab = ' '*4

        if clsname == 'Tensor':
            lines = [
                'from ..datatypes import __pool__ as data',
                "{} = data['{}']".format(baseClsName, baseClsName),
                '', '',
                "class {}({}, list):".format(clsname, baseClsName),
                '', f'{tab}...'
            ]
        else:
            lines = [
                'from ..datatypes import __pool__ as data',
                "{} = data['{}']".format(baseClsName, baseClsName),
                '', '',
                "class {}({}):".format(clsname, baseClsName),
                '', f'{tab}...'
            ]

        return '\n'.join(lines)

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