from typing import Union, Optional

from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__
import riggery.internal.niceunit as _nic
from riggery.general.functions import short

import maya.api.OpenMaya as om

def conformOrder(order):
    if isinstance(order, int):
        return order
    return _nic.ROTORDERS.index(order)


class EulerRotation(__pool__['Tensor3']):

    __apicls__ = om.MEulerRotation

    #-----------------------------------------|    Init

    @classmethod
    def fromApi(cls, data:om.MEulerRotation):
        """
        :param data: a :class:`~maya.api.OpenMaya.MEulerRotation` instance
        :return: A matched :class:`EulerRotation` instance
        """
        return cls.fromIter(data, order=data.order)

    def __init__(self, values, order=None):
        super().__init__(values)
        if order is None:
            self._order = 0
        else:
            self._order = conformOrder(order)

    @property
    def api(self):
        return om.MEulerRotation(self, order=self.order)

    def copy(self):
        """
        :return: A copy of this data object.
        """
        out = super().copy()
        out.order = self.order
        return out

    #-----------------------------------------|    Testing

    @short(inheritsTransform='it', name='n')
    def loc(self,
            name:Optional[str]=None, *,
            inheritsTransform:bool=True):
        """
        Creates a locator with its ``rotate`` and ``rotateOrder`` attributes
        set to this rotation object.

        :param name/n: an optional override for the locator name; defaults to
            block naming
        :param inheritsTransform/it: sets 'inheritsTransform' on the locator;
            defaults to True
        """
        out = nodes['Locator'].createNode(name=name).parent
        out.attr('displayLocalAxis').set(True)
        out.attr('it').set(inheritsTransform)
        out.attr('r').set(self)
        out.attr('ro').set(self.order)
        return out

    #-----------------------------------------|    Order

    def getOrder(self, asString=False) -> Union[int, str]:
        """
        :param asString: return the rotate order as a lowercase enum name,
            like 'xyz'; defaults to False
        :return: The rotate order; either an integer (one of the standard
            enum values) or a lowercase enum like 'xyz'.
        """
        if asString:
            return _nic.ROTORDERS[self._order]
        return self._order

    def setOrder(self, order:Union[str, int]):
        """
        Note that this does not reorder the rotation solution; it's just a
        tagging operation.

        :param order: the rotate order; either an integer (one of the standard
            enum values) or a lowercase enum like 'xyz'
        """
        self._order = conformOrder(order)

    order = property(getOrder, setOrder)

    def reorderIt(self, order:Union[str, int]):
        """
        Performs in-place reordering. Self is returned for convenience.
        :param order: the rotate order; either an integer (one of the standard
            enum values) or a lowercase enum like 'xyz'
        """
        order = conformOrder(order)
        if self.order != order:
            apiValue = self.api
            apiValue.reorderIt(order)
            self[:] = apiValue
            self.order = order
        return self

    #-----------------------------------------|    Repr

    def __repr__(self):
        return "{}({}, order={})".format(type(self).__name__,
                                         list.__repr__(self),
                                         repr(self.getOrder(asString=True)))