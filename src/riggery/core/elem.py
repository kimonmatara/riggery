"""Defines the fundamental Elem type."""

import os
from .nodetypes import __pool__ as nodes
from .plugtypes import __pool__ as plugs

import riggery


class ElemInstError(RuntimeError):
    ...


class ElemMeta(type):
    def __call__(cls, item):
        if isinstance(item, Elem):
            return item
        return cls.fromStr(str(item))

class AttributeClassGetter:
    def __get__(self, inst, instype):
        from .plugtypes import __pool__
        Elem.__attrcls__ = out = __pool__['Attribute']
        return out


class DependNodeClassGetter:
    def __get__(self, inst, instype):
        from .nodetypes import __pool__
        Elem.__depncls__ = out = __pool__['DependNode']
        return out


class Elem(metaclass=ElemMeta):

    #-----------------------------------------|    Construction

    __pool__ = None

    __attrcls__ = AttributeClassGetter()
    __depncls__ = DependNodeClassGetter()

    @classmethod
    def fromStr(cls, path:str):
        if '.' in path:
            return cls.__attrcls__.fromStr(path)
        return cls.__depncls__.fromStr(path)

    @staticmethod
    def _constructInst(cls, apiObjects:dict):
        inst = Elem.__new__(cls)
        inst.__apiobjects__ = apiObjects
        inst.__init__()
        return inst

    #-----------------------------------------|    Repr stubs

    def __bool__(self):
        return True

    def __eq__(self, other):
        try:
            other = Elem(other)
        except:
            return False
        return self.__hash__() == other.__hash__()

    def __hash__(self):
        raise NotImplementedError

    def __eq__(self, other):
        raise NotImplementedError

    def __str__(self):
        raise NotImplementedError