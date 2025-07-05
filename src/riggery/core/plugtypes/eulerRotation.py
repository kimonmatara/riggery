from typing import Union, Optional

import maya.api.OpenMaya as om

from riggery.general.functions import short
import riggery.internal.mfnmatches as _mfm
import riggery.internal.niceunit as _nic
from ..plugtypes import __pool__
from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes


class EulerRotation(__pool__['Tensor3Float']):

    __datacls__ = _data['EulerRotation']

    #-----------------------------------------|    Testing

    @short(worldSpace='ws',
           name='n',
           rotateOrder='ro')
    def loc(self,
            name:Optional[str]=None, *,
            inheritTransform:bool=True,
            rotateOrder=None):
        """
        :param name/n: if omitted, uses name blocks
        :param inheritTransform/it: sets 'inheritTransform' on the locator;
            defaults to True
        :param rotateOrder/ro: sets the rotate order on the locator; if
            omitted then, if this is the 'rotate' channel on a transform node,
            uses the node's rotate order; otherwise, defaults to 0 / 'xyz'
        :return: A locator whose rotate channel will be driven by this plug.
        """
        out = nodes.Locator.createNode(name=name).getParent()
        out.attr('it').set(inheritTransform)
        self >> out.attr('r')

        if rotateOrder is None:
            rotateOrder = self.guessRotateOrder(plug=True)
        rotateOrder >> out.attr('ro')

        return out

    #-----------------------------------------|    Set

    def _setValue(self, value, /, unit=None, ui=False, **_):
        plug = self.__apimplug__()

        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        if unit is None:
            if ui:
                unit = om.MAngle.uiUnit()
            else:
                unit = om.MAngle.kRadians
        elif not isinstance(unit, int):
            unit = _nic.ANGLE_KEY_TO_VAL[unit]

        if unit != om.MAngle.kRadians:
            value = [
                om.MAngle(x, unit=unit).asUnits(om.MAngle.kRadians
                                                ) for x in value
            ]
        super()._setValue(value)

    #-----------------------------------------|    Get

    def _getValue(self, *,
                  unit=None,
                  ui=False,
                  frame=None,
                  rotateOrder=None,
                  **_):
        out = super()._getValue(frame=frame)

        if rotateOrder is None:
            rotateOrder = self.guessRotateOrder()
        else:
            if not isinstance(rotateOrder, int):
                rotateOrder = _nic.ROTORDERS.index(rotateOrder)

        out.order = rotateOrder

        # Right now we have an EulerRotation in radians.
        if unit is None:
            if ui:
                unit = om.MAngle.uiUnit()
            else:
                unit = om.MAngle.kRadians
        else:
            if not isinstance(unit, int):
                unit = _nic.ANGLE_KEY_TO_VAL[unit]

        if unit != om.MAngle.kRadians:
            out[:] = [om.MAngle(value).asUnits(unit) for value in out]
        return out

    #-----------------------------------------|    Rotate order

    def reorder(self, arg1=None, arg2=None, /):
        """
        If two arguments are passed, then they should be the original rotate
            order and the new rotate order, respectively.

        If one argument is passed, then this must be the main rotate channel
        on a transform node, so that the source rotate order can be derived.

        :raises ValueError: Wrong arguments.
        :return: The reordered rotation.
        """
        orders = []
        if arg1 is not None:
            orders.append(arg1)

        if arg2 is not None:
            orders.append(arg2)

        if orders:
            if len(orders) == 1:
                if self.isRotateChannel():
                    orders.insert(0, self.node().attr('rotateOrder'))
                else:
                    raise ValueError("undefined source order")
        else:
            raise ValueError("undefined source / end orders")
        return self.asQuaternion(ro=orders[0]).asEulerRotation(ro=orders[1])

    def isRotateChannel(self) -> bool:
        """
        :return: True if this is the main 'rotate' channel on a transform node.
        """
        return self.node().isTransform() and self.attrName() == 'r'

    @short(plug='p')
    def guessRotateOrder(self, *,
                         asString:bool=False,
                         plug:bool=False):
        """
        If this is the 'rotate' compound on a transform node, uses the
        transform node's rotate order.

        :param asString: return the rotate order in string form, e.g. 'zxy';
            defaults to False
        :param plug/p: where available, return the owner node's
            ``rotateOrder`` attribute itself; defaults to False
        :return: A best-guess for the rotate order.
        """
        node = self.node()
        if node.isTransform() and self.attrName() == 'r':
            attr = node.attr('rotateOrder')
            if plug:
                return attr
            return attr.getValue(asString=asString)
        return 'xyz' if asString else 0

    #-----------------------------------------|    Unit utils

    def unitEnums(self) -> dict:
        """
        :return: Accepted unit enums, in a dict.
        """
        return _nic.ANGLE_ENUMS.copy()

    #-----------------------------------------|    Conversions

    @short(rotateOrder='ro')
    def asRotateMatrix(self, rotateOrder=None):
        """
        Alias: ``asMatrix()``

        :param rotateOrder/ro: if omitted then, if this is the rotate channel
            on a transform node, uses the node's rotate order; otherwise,
            defaults to 0 / 'xyz'
        :return: A rotation matrix composed from this euler rotation.
        """
        node = nodes.ComposeMatrix.createNode()
        self >> node.attr('inputRotate')

        if rotateOrder is None:
            rotateOrder = self.guessRotateOrder(plug=True)

        rotateOrder >> node.attr('inputRotateOrder')
        return node.attr('outputMatrix')

    asMatrix = asRotateMatrix

    @short(rotateOrder='ro')
    def asQuaternion(self, rotateOrder=None):
        """
        :param rotateOrder/ro: if omitted then, if this is the rotate channel
            on a transform node, uses the node's rotate order; otherwise,
            defaults to 0 / 'xyz'
        :return: The quaternion form of this euler rotation.
        """
        node = nodes.EulerToQuat.createNode()
        self >> node.attr('inputRotate')

        if rotateOrder is None:
            rotateOrder = self.guessRotateOrder(plug=True)
        rotateOrder >> node.attr('inputRotateOrder')
        return node.attr('outputQuat')

    @short(rotateOrder='ro')
    def asAxisAngle(self, rotateOrder=None) -> tuple:
        """
        :param rotateOrder/ro: if omitted then, if this is the rotate channel
            on a transform node, uses the node's rotate order; otherwise,
            defaults to 0 / 'xyz'
        :return: A tuple of axis, angle (plugs).
        """
        return self.asQuaternion(rotateOrder=rotateOrder).asAxisAngle()