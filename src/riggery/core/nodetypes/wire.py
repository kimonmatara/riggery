from types import NoneType
from typing import Union, Optional, Iterator
from ..nodetypes import __pool__ as nodes
from ..lib import names as _nm

from riggery.general.functions import short
WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m


class Wire(WeightGeometryFilter):

    #-------------------------------------|    Constructor

    @classmethod
    @short(name='n')
    def create(cls,
               baseGeo:Union['nodes.DagNode', str],
               name:Optional[str]=None):
        """
        Similar to :class:`~riggery.core.nodetypes.blendShape.BlendShape`, this
        doesn't configure drivers. Use :meth:`addDriver` and so on for that.
        """
        kwargs = {}
        if name is None:
            if _nm.Name.__elems__:
                kwargs['name'] = _nm.Name.evaluate(
                    typeSuffix=cls.__typesuffix__
                )
        else:
            kwargs['name'] = name

        node = m.wire(baseGeo, **kwargs)[0]
        return cls(node)

    #-------------------------------------|    Inspections

    def wireCount(self) -> int:
        """:return: The number of drivers."""
        return m.wire(str(self), q=True, wireCount=True)

    #-------------------------------------|    Add drivers

    def iterDriverIndices(self) -> Iterator[int]:
        """Yields driver indices."""
        for index in self.attr('deformedWire').indices():
            plug = self.attr('deformedWire')[index]
            if next(plug.iterInputs(), None) is not None:
                yield index

    def addDriver(self,
                  curve:Union['nodes.DagNode', str]):
        """
        :param curve: the wire curve to add; a base curve will be automatically
            generated, per standard Maya behaviour.
        """
        m.wire(str(self), e=True, wire=str(curve))
        return self