from riggery.core.lib.evaluation import cache_dg_output
from ..plugtypes import __pool__
from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes
from ..lib import mixedmode as _mm

import maya.api.OpenMaya as om


class Tensor3(__pool__['Tensor']):

    __datacls__ = _data['Tensor3']
    __shape__ = 3

    #-----------------------------------------|    Add

    def __add__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            node = nodes.PlusMinusAverage.createNode()
            self >> node.attr('input3D')[0]
            node.attr('input3D')[1].put(other, isPlug)
            return node.attr('output3D').asType(type(self))

        return NotImplemented

    def __radd__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            node = nodes.PlusMinusAverage.createNode()
            self >> node.attr('input3D')[1]
            node.attr('input3D')[0].put(other, isPlug)
            return node.attr('output3D').asType(type(self))

        return NotImplemented
    
    #-----------------------------------------|    Sub

    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input3D')[0]
            node.attr('input3D')[1].put(other, isPlug)
            return node.attr('output3D').asType(type(self))

        return NotImplemented

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input3D')[1]
            node.attr('input3D')[0].put(other, isPlug)
            return node.attr('output3D').asType(type(self))

        return NotImplemented

    #-----------------------------------------|    Average

    def average(self, *others):
        """
        Returns the average of [*self*] + others.
        """
        node = nodes.PlusMinusAverage.createNode()
        node.attr('operation').set(3)
        self >> node.attr('input3D')[0]

        for i, item in enumerate(others, start=1):
            node.attr('input3D')[i].put(item)

        return node.attr('output3D').asType(type(self))

    #-----------------------------------------|    Multiply

    @cache_dg_output
    def __neg__(self):
        node = nodes.MultiplyDivide.createNode()
        self >> node.attr('input1')
        node.attr('input2').set([-1] * 3)
        return node.attr('output').asType(type(self))

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            self >> node.attr('input1')
            for child in node.attr('input2').children:
                child.put(other, isPlug)
            return node.attr('output').asType(type(self))

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            self >> node.attr('input1')
            node.attr('input2').put(other, isPlug)
            return node.attr('output').asType(type(self))

        return NotImplemented

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            for child in node.attr('input1').children:
                child.put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output').asType(type(self))

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('input1').put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output').asType(type(self))

        return NotImplemented

    #-----------------------------------------|    Divide

    def __truediv__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input1')
            for child in node.attr('input2').children:
                child.put(other, isPlug)
            return node.attr('output').asType(type(self))

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input1')
            node.attr('input2').put(other, isPlug)
            return node.attr('output').asType(type(self))

        return NotImplemented

    def __rtruediv__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)
            for child in node.attr('input1').children:
                child.put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output').asType(type(self))

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)
            node.attr('input1').put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output').asType(type(self))

        return NotImplemented

    #-----------------------------------------|    Power

    def __pow__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)
            self >> node.attr('input1')
            for child in node.attr('input2').children:
                child.put(other, isPlug)
            return node.attr('output').asType(type(self))

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)
            self >> node.attr('input1')
            node.attr('input2').put(other, isPlug)
            return node.attr('output').asType(type(self))

        return NotImplemented

    def __rpow__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)
            for child in node.attr('input1').children:
                child.put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output').asType(type(self))

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)
            node.attr('input1').put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output').asType(type(self))

        return NotImplemented

    #-----------------------------------------|    Blending

    def blend(self, other, weight=0.5):
        """
        Blends this tensor towards *other*. When *weight* is at 1.0, *other*
        will have fully taken over.

        :param other: the tensor towards which to blend; must be of the same
            dimension as this one
        :param weight: the blending weight; defaults to 0.5
        :return: The blended output.
        """
        node = nodes.BlendColors.createNode()
        self >> node.attr('color2')
        other >> node.attr('color1')
        weight >> node.attr('blender')
        return node.attr('output').asType(type(self))