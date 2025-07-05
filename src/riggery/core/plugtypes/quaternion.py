from typing import Union, Optional
import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short
from ..plugtypes import __pool__
from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes
from ..lib import mixedmode as _mm


class Quaternion(__pool__['Tensor4']):

    __datacls__ = _data['Quaternion']

    #-----------------------------------------|    Test

    @short(name='n', inheritsTransform='it')
    def loc(self, name=None, *, inheritsTransform=True):
        """
        Creates a locator and drives its rotation with this quaternion, for
        visualisation.

        :param name/n: if omitted, defaults to name blocks
        :param inheritsTransform/it: sets 'inheritsTransform' on the locator;
            defaults to True
        :return: The locator (transform).
        """
        loc = nodes.Locator.createNode().getParent()
        self.asMatrix() >> loc.attr('opm')
        inheritsTransform >> loc.attr('inheritsTransform')
        return loc

    #-----------------------------------------|    Set

    def _setValue(self, value, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        if self.isCompound:
            children = [plug.child(i) for i in range(plug.numChildren())]
            for src, child in zip(value, children):
                child.setDouble(src)
        else:
            fn = om.MFnNumericData()
            mobj = fn.create(om.MFnNumericData.k4Double)
            fn.setData(value)

            plug.setMObject(mobj)

    #-----------------------------------------|    Get

    def _getValue(self, *, frame=None, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        kwargs = {}
        if frame is not None:
            kwargs['context'] = om.MDGContext(
                om.MTime(frame, om.MTime.uiUnit())
            )

        if plug.isCompound:
            values = [plug.child(i).asDouble(
                **kwargs) for i in range(plug.numChildren())]
        else:
            values = om.MFnNumericalData(plug.asMObject(**kwargs)).getData()

        return self.__datacls__(values)

    #-----------------------------------------|    Constructors

    @classmethod
    def fromAxisAngle(cls, axis, angle):
        """
        :param axis: the axis vector
        :param angle: the angle (radians)
        """
        node = nodes.AxisAngleToQuat.createNode()
        axis >> node.attr('inputAxis')
        angle >> node.attr('inputAngle')
        return node.attr('outputQuat')

    #-----------------------------------------|    Add

    def __add__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            node = nodes.QuatAdd.createNode()
            self >> node.attr('input1Quat')
            node.attr('input2Quat').put(other, isPlug)
            return node.attr('outputQuat')

        return NotImplemented

    def __radd__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            node = nodes.QuatAdd.createNode()
            node.attr('input1Quat').put(other, isPlug)
            self >> node.attr('input2Quat')
            return node.attr('outputQuat')

        return NotImplemented

    #-----------------------------------------|    Sub

    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            node = nodes.QuatSub.createNode()
            self >> node.attr('input1Quat')
            node.attr('input2Quat').put(other, isPlug)
            return node.attr('outputQuat')

        return NotImplemented

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            node = nodes.QuatSub.createNode()
            node.attr('input1Quat').put(other, isPlug)
            self >> node.attr('input2Quat')
            return node.attr('outputQuat')

        return NotImplemented

    #-----------------------------------------|    Mult

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.QuatSlerp.createNode()
            node.attr('input1Quat').set(_data.Quaternion())
            self >> node.attr('input2Quat')
            other >> node.attr('inputT')
            return node.attr('outputQuat')

        if shape == 4:
            node = nodes.QuatProd.createNode()
            self >> node.attr('input1Quat')
            node.attr('input2Quat').put(other, isPlug)
            return node.attr('outputQuat')

        return NotImplemented

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 4:
            node = nodes.QuatProd.createNode()
            node.attr('input1Quat').put(other, isPlug)
            self >> node.attr('input2Quat')
            return node.attr('outputQuat')

        return NotImplemented

    #-----------------------------------------|    Misc quat operations

    @cache_dg_output
    def normal(self):
        """
        :return: A normalized version of this quaternion.
        """
        existing = self.outputs(type='quatNormalize')
        if existing:
            return existing[0].attr('outputQuat')
        node = nodes.QuatNormalize.createNode()
        self >> node.attr('inputQuat')
        return node.attr('outputQuat')

    @cache_dg_output
    def inverse(self):
        """
        :return: The inverse of this quaternion.
        """
        existing = self.outputs(type='quatInvert')
        if existing:
            return existing[0].attr('outputQuat')
        node = nodes.QuatInvert.createNode()
        self >> node.attr('inputQuat')
        return node.attr('outputQuat')

    @cache_dg_output
    def conjugate(self):
        """
        :return: The conjugation of this quaternion. Think of this as a
            faster / less strict inversion.
        """
        existing = self.outputs(type='quatConjugate')
        if existing:
            return existing[0].attr('outputQuat')
        node = nodes.QuatConjugate.createNode()
        self >> node.attr('inputQuat')
        return node.attr('outputQuat')

    @cache_dg_output
    def negate(self):
        """
        :return: The negation of this quaternion. Useful for mirroring
            operations.
        """
        existing = self.outputs(type='quatNegate')
        if existing:
            return existing[0].attr('outputQuat')
        node = nodes.QuatNegate.createNode()
        self >> node.attr('inputQuat')
        return node.attr('outputQuat')

    __neg__ = negate

    @short(weight='w', angleInterpolation='ai')
    def slerp(self, other, weight=0.5, *, angleInterpolation=0):
        """
        Blends this quaternion towards *other*. When *weight* is at 1.0,
        *other* will have taken over completely.

        :param other: the other quaternion
        :param weight/w: the blending weight; defaults to 0.5
        :param angleInterpolation/ai: the angle interpolation; one of:
            0 - 'Shortest'
            1 - 'Positive'
            2 - 'Negative';
            defaults to 0 - 'Shortest'
        :return: The blended quaternion.
        """
        node = nodes.QuatSlerp.createNode()
        self >> node.attr('input1Quat')
        other >> node.attr('input2Quat')
        weight >> node.attr('inputT')
        angleInterpolation >> node.attr('angleInterpolation')
        return node.attr('outputQuat')

    @short(angleInterpolation='ai')
    def atten(self, weight, angleInterpolation=0):
        """
        Equivalent to ``data.Quaternion().slerp(self, weight=weight...)``.
        """
        return _data.Quaternion().slerp(self,
                                        weight=weight,
                                        angleInterpolation=angleInterpolation)

    #-----------------------------------------|    Conversions

    def asOffset(self):
        """
        Equivalent to ``self.get().inverse() * self``
        """
        return self.get().inverse() * self

    @cache_dg_output
    def asRotateMatrix(self):
        """
        Alias: ``asMatrix()``

        :return: A rotation matrix from this quaternion.
        """
        node = nodes.ComposeMatrix.createNode()
        self >> node.attr('inputQuat')
        node.attr('useEulerRotation').set(False)
        return node.attr('outputMatrix')

    asMatrix = asRotateMatrix

    def asAxisAngle(self) -> tuple:
        """
        :return: A tuple of axis (vector plug), angle (angle plug).
        """
        node = nodes.QuatToAxisAngle.createNode()
        self >> node.attr('inputQuat')
        return node.attr('outputAxis'), node.attr('outputAngle')

    @short(rotateOrder='ro')
    def asEulerRotation(self, rotateOrder=None):
        """
        :param rotateOrder/ro: defaults to 0 / 'xyz'
        :return: The euler form of this quaternion rotation.
        """
        node = nodes.QuatToEuler.createNode()
        if rotateOrder is not None:
            rotateOrder >> node.attr('inputRotateOrder')
        self >> node.attr('inputQuat')
        return node.attr('outputRotate')