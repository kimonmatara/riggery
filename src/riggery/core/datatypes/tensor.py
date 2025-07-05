import operator
from typing import Optional, Iterable, Union
from ..datatypes import __pool__
from ..plugtypes import __pool__ as _plugs


def addOperator(opName, clsname, dct, unary=False) -> None:
    """
    Used by :class:`TensorMeta` to add elementwise arithmetic operators
    to the base :class:`Tensor` class.
    """
    op = getattr(operator, opName)

    if unary:
        def meth(self):
            return type(self)([op(elem) for elem in self])

        methName = meth.__name__ = f'__{opName}__'
        meth.__qualname__ = f"{clsname}.{methName}"
        dct[methName] = meth
    else:
        # E.g. __add__

        def meth(self, other):
            if isinstance(other, (float, int)):
                return type(self)([op(elem, other) for elem in self])
            if len(other) >= self.__shape__:
                return type(self)([op(a, b) for a, b in zip(self, other)])
            return NotImplemented

        methName = meth.__name__ = f'__{opName}__'
        meth.__qualname__ = f"{clsname}.{methName}"
        dct[methName] = meth

        # E.g. __radd__

        def invMeth(self, other):
            if isinstance(other, (float, int)):
                return type(self)([op(other, elem) for elem in self])
            if len(other) >= self.__shape__:
                return type(self)([op(a, b) for a, b in zip(other, self)])
            return NotImplemented

        invMethName = invMeth.__name__ = f'__r{opName}__'
        invMeth.__qualname__ = f"{clsname}.{invMethName}"
        dct[invMethName] = invMeth

        if opName in ('add', 'sub', 'mul', 'truediv', 'pow'):
            # E.g. __iadd__

            def iMeth(self, other):
                self[:] = op(self, other)
                return self

            iMethName = iMeth.__name__ = f'__i{opName}__'
            iMeth.__qualname__= f'{clsname}.{iMethName}'
            dct[iMethName] = iMeth

class TensorMeta(type):

    def __call__(cls, arg=None, **kwargs):
        if arg is None:
            return cls.fromApi(cls.__apicls__())

        if isinstance(arg, Tensor):
            return cls.fromApi(arg.api)

        if arg.__class__.__module__ == 'OpenMaya':
            return cls.fromApi(arg, **kwargs)

        return cls.fromIter(list(arg), **kwargs)

    def __new__(meta, clsname, bases, dct):
        if bases == (__pool__['Data'], list):
            for opName in (
                'add',
                'sub',
                'mul',
                'truediv',
                'floordiv',
                'mod',
                'pow'
            ):
                addOperator(opName, clsname, dct)

            for opName in ('neg', 'pos'):
                addOperator(opName, clsname, dct, unary=True)

        return super().__new__(meta, clsname, bases, dct)


class Tensor(__pool__['Data'], list, metaclass=TensorMeta):

    __apicls__ = None
    __shape__:int

    #-------------------------------------|    Instantiate

    @classmethod
    def fromApi(cls, apiDataObject, **kwargs):
        return cls.fromIter(apiDataObject, **kwargs)

    @classmethod
    def fromIter(cls, iterable, **kwargs):
        inst = list.__new__(cls)
        inst.__init__(list(iterable)[:cls.__shape__], **kwargs)
        return inst

    def copy(self):
        """
        :return: A copy of this data object.
        """
        return type(self)(list.copy(self))

    #-------------------------------------|    Basic methods

    def average(self, *others):
        """
        :return: The average of [*self*] + others.
        """
        allItems = [self] + list(others)
        num = len(allItems)
        out = [sum(member) / num for member in zip(*allItems)]
        return type(self)(out)

    #-------------------------------------|    Plug interop

    def plugClass(self) -> type:
        return _plugs[type(self).__name__]

    #-------------------------------------|    API

    @property
    def api(self):
        return self.__apicls__(self)

    #-------------------------------------|    Repr

    def __repr__(self):
        return "{}({})".format(type(self).__name__,
                               list.__repr__(self))