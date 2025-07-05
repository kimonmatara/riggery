from typing import Union, Optional
import maya.api.OpenMaya as om

from riggery.general.functions import short
import riggery.internal.niceunit as _nu
from ..lib import mixedmode as _mm
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__


class Quaternion(__pool__['Tensor4']):

    __apicls__ = om.MQuaternion

    #-----------------------------------------|    Constructors

    @classmethod
    def fromAxisAngle(cls, axis, angle):
        """
        :param axis: the axis vector
        :param angle: the angle (radians)
        """
        axis = om.MVector(axis)
        quat = om.MQuaternion()
        quat.setValue(om.MVector(axis), angle)
        return Quaternion(quat)

    #-----------------------------------------|    Test

    @short(name='n', inheritsTransform='it')
    def loc(self,
            name:Optional[str]=None, *,
            inheritsTransform:bool=True):
        """
        :param name/n: an optional name override; defaults to block naming
        :param inheritsTransform/it: sets 'inheritsTransform' on the node;
            defaults to True
        :return: A locator with its rotation set to this quaternion.
        """
        loc = nodes.Locator.createNode().parent
        loc.attr('inheritsTransform').set(inheritsTransform)
        loc.attr('displayLocalAxis').set(True)
        loc.attr('r').set(self.asEulerRotation())
        return loc

    #-----------------------------------------|    Add

    def __add__(self, other):
        other, shape, isPlug = _mm.info(other)
        if shape == 4:
            if isPlug:
                node = nodes.QuatAdd.createNode()
                node.attr('input1Quat').set(self)
                node.attr('input2Quat').put(other, True)
                return node.attr('outputQuat')
            return Quaternion(self.api + om.MQuaternion(other))
        return super().__add__(other)

    def __radd__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            if isPlug:
                node = nodes.QuatAdd.createNode()
                node.attr('input1Quat').put(other, True)
                node.attr('input2Quat').set(self)
                return node.attr('outputQuat')
            return Quaternion(om.MQuaternion(other) + self.api)
        return super().__radd__(other)

    #-----------------------------------------|    Sub
    
    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)
        if shape == 4:
            if isPlug:
                node = nodes.QuatSub.createNode()
                node.attr('input1Quat').set(self)
                node.attr('input2Quat').put(other, True)
                return node.attr('outputQuat')
            return Quaternion(self.api - om.MQuaternion(other))
        return super().__sub__(other)

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            if isPlug:
                node = nodes.QuatSub.createNode()
                node.attr('input1Quat').put(other, True)
                node.attr('input2Quat').set(self)
                return node.attr('outputQuat')
            return Quaternion(om.MQuaternion(other) - self.api)
        return super().__rsub__(other)

    #-----------------------------------------|    Mult

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)
        if shape == 4:
            if isPlug:
                node = nodes.QuatProd.createNode()
                node.attr('input1Quat').set(self)
                node.attr('input2Quat').put(other, True)
                return node.attr('outputQuat')
            return Quaternion(self.api * om.MQuaternion(other))
        return super().__mul__(other)

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            if isPlug:
                node = nodes.QuatProd.createNode()
                node.attr('input1Quat').put(other, True)
                node.attr('input2Quat').set(self)
                return node.attr('outputQuat')
            return Quaternion(om.MQuaternion(other) * self.api)

        if shape == 3:
            matrix = self.asRotateMatrix()
            return other * matrix

        return super().__rmul__(other)

    #-----------------------------------------|    Methods

    def conjugate(self):
        """
        :return: A conjugated copy of this quaternion.
        """
        return Quaternion(self.api.conjugate())

    def conjugateIt(self):
        """
        Conjugates this quaternion in-place and returns self.
        """
        self[:] = self.api.conjugate()
        return self

    def normal(self):
        """
        :return: A normalized copy of this quaternion.
        """
        return Quaternion(self.api.normal())

    def normalizeIt(self):
        """
        Normalizes this quaternion in-place and returns self.
        """
        self[:] = self.api.normal()
        return self

    def inverse(self):
        """
        :return: An inverted copy of this quaternion.
        """
        return Quaternion(self.inverse())

    def invertIt(self):
        """
        Inverts this quaternion in-place and returns self.
        """
        self[:] = self.api.inverse()
        return self

    def negate(self):
        """
        :return: A negated copy of this quaternion.
        """
        quat = self.api
        quat.negateIt()
        return Quaternion(quat)

    def negateIt(self):
        """
        Negates this quaternion in-place and returns self.
        """
        quat = self.api
        quat.negateIt()
        self[:] = quat
        return self

    #-----------------------------------------|    Slerp

    @short(weight='w', angleInterpolation='ai')
    def slerp(self, otherQuat, weight=0.5, angleInterpolation=None):
        """
        Performs slerp blending.

        :param otherQuat: the quat towards which to blend
        :param weight: the blend weight; defaults to 0.5
        :param angleInterpolation/ai: this is only available if *otherQuat* is
            a plug; one of 0 - 'Shortest', 1 - 'Positive', 2 - 'Negative';
            defaults to 'Shortest'
        :return: This quaternion, blended towards *otherQuat* by the given
            weight.
        """
        otherQuat, _, otherQuatIsPlug = _mm.info(
            otherQuat,
            (Quaternion, plugs['Quaternion'])
        )

        weight, _, weightIsPlug = _mm.info(weight)
        hasPlugs = otherQuatIsPlug or weightIsPlug

        if hasPlugs:
            node = nodes.QuatSlerp.createNode()
            node.attr('input1Quat').set(self)
            node.attr('input2Quat').put(otherQuat, otherQuatIsPlug)
            node.attr('inputT').put(weight, weightIsPlug)
            if angleInterpolation is None:
                node.attr('angleInterpolation').set(0)
            else:
                node.attr('angleInterpolation').put(angleInterpolation)
            return node.attr('outputQuat')
        if angleInterpolation is not None:
            raise ValueError(
                "angleInterpolation is only available if *otherQuat* is a plug"
            )
        otherQuat = om.MQuaternion(otherQuat)
        return Quaternion(self.api.slerp(otherQuat, weight))

    #-----------------------------------------|    Conversions

    def asRotateMatrix(self):
        """
        Alias: ``asMatrix()``

        :return: A rotation matrix from this quaternion.
        """
        return __pool__['Matrix'](self.api.asMatrix())

    asMatrix = asRotateMatrix

    def asAxisAngle(self) -> tuple:
        """
        :return: A tuple of axis (vector), angle (float).
        """
        axis, angle = self.api.asAxisAngle()
        axis = __pool__['Vector'](axis)
        return axis, angle

    def asEulerRotation(self, order:Union[str, int]=0):
        """
        :param order: the Euler rotation order; defaults to 0 ('xyz')
        :return: The Euler rotation.
        """
        eul = self.api.asEulerRotation()
        order = _nu.conformRotateOrder(order)
        if order != 0:
            eul.reorderIt(order)
        return __pool__['EulerRotation'](eul)