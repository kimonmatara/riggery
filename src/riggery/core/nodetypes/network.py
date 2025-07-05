import maya.cmds as m

from typing import Generator
from ..nodetypes import __pool__ as nodes

DependNode = nodes['DependNode']

import maya.cmds as m

class NetworkMeta(type(DependNode)):
    # This is necessary otherwise `updateType()` may overwrite with a wrong
    # melnode; a bit hacky

    def __new__(meta, clsname, bases, dct):
        dct['__melnode__'] = 'network'
        return super().__new__(meta, clsname, bases, dct)

class Network(DependNode, metaclass=NetworkMeta):

    # The following field allows an external framework (e.g. riggery_tools) to
    # inject a pool for network subtype instantiation. Absent that, 'network'
    # nodes will be managed same as any other node type.

    __subtype_pool__ = None

    def __init__(self):
        super().__init__()
        self.updateType()

    def updateType(self):
        """
        Reads the 'networkType' attribute, if present, retrieves a network
        subclass, and assigns it to this instance.

        :return: Self.
        """
        if self.__subtype_pool__ is not None:
            try:
                clsname = self.attr('networkType')()
            except AttributeError:
                return self
            try:
                self.__class__ = self.__subtype_pool__[clsname]
            except Exception as exc:
                m.warning(f"couldn't retype to '{clsname}': {exc}")
        return self

    @classmethod
    def createNode(cls, *args, **kwargs):
        out = DependNode.createNode.__func__(cls, *args, **kwargs)
        if cls is not Network:
            out._embedSubtype(cls.__name__)
            out.updateType()
        return out

    def _embedSubtype(self, T:str):
        if self.hasAttr('networkType'):
            attr = self.attr('networkType')
            attr.unlock()
        else:
            attr = self.addAttr('networkType', dt='string')
        attr.set(T)
        attr.lock()