from ..plugtypes import __pool__
from ..datatypes import __pool__ as _data
from ..nodetypes import __pool__ as nodes
from ..lib import mixedmode as _mm


class Tensor2(__pool__['Tensor']):

    __datacls__ = _data['Tensor2']
    __shape__ = 2

    #-----------------------------------------|    Add

    def __add__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 2:
            node = nodes.PlusMinusAverage.createNode()
            self >> node.attr('input2D')[0]
            node.attr('input2D')[1].put(other, isPlug)
            return node.attr('output2D')

        return NotImplemented

    def __radd__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 2:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('input2D')[0].put(other, isPlug)
            self >> node.attr('input2D')[1]
            return node.attr('output2D')

        return NotImplemented
    
    #-----------------------------------------|    Sub

    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 2:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input2D')[0]
            node.attr('input2D')[1].put(other, isPlug)
            return node.attr('output2D')

        return NotImplemented

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 2:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('operation').set(2)
            node.attr('input2D')[0].put(other, isPlug)
            self >> node.attr('input2D')[1]
            return node.attr('output2D')

        return NotImplemented

    #-----------------------------------------|    Average

    def average(self, *others):
        """
        Returns the average of [*self*] + others.
        """
        node = nodes.PlusMinusAverage.createNode()
        node.attr('operation').set(3)
        self >> node.attr('input2D')[0]

        for i, item in enumerate(others, start=1):
            node.attr('input2D')[i].put(item)

        return node.attr('output2D')