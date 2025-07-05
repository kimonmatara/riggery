from ..plugtypes import __pool__
from ..datatypes import __pool__ as _data


class Tensor4(__pool__['Tensor']):

    __datacls__ = _data['Tensor4']
    __shape__ = 4