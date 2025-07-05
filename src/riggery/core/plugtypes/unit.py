from typing import Union, Optional
from ..plugtypes import __pool__


class Unit(__pool__['Float']):

    __apiunittype__ = None # e.g. om.MDistance

    #-----------------------------------------|    Default value

    def getDefaultValue(self):
        return super().getDefaultValue().value

    def setDefaultValue(self, value):
        return super().setDefaultValue(self.__apiunittype__(value))

    #-----------------------------------------|    Unit stubs

    @classmethod
    def _conformUnit(cls, unit):
        # Stub
        raise NotImplementedError

    def unitEnums(self) -> dict:
        """
        :return: Accepted enums, in a dict, for reference.
        """
        raise NotImplementedError