from ..lib import mixedmode as _mm
from ..datatypes import __pool__
from ..nodetypes import __pool__ as nodes


class Tensor2(__pool__['Tensor']):

    __shape__ = 2

    #-----------------------------------------|    Add

    def __add__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 2:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('input2D')[0].set(self)
                node.attr('input2D')[1].put(other, True)
                return node.attr('output2D')

            return NotImplemented
        return super().__add__(other)

    def __radd__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 2:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('input2D')[0].put(other, True)
                node.attr('input2D')[1].set(self)
                return node.attr('output2D')

            return NotImplemented
        return super().__radd__(other)
    
    #-----------------------------------------|    Sub

    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 2:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('operation').set(2)
                node.attr('input2D')[0].set(self)
                node.attr('input2D')[1].put(other, True)
                return node.attr('output2D')

            return NotImplemented
        return super().__sub__(other)

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 2:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('operation').set(2)
                node.attr('input2D')[0].put(other, True)
                node.attr('input2D')[1].set(self)
                return node.attr('output2D')

            return NotImplemented
        return super().__rsub__(other)

    #-----------------------------------------|    Average

    def average(self, *others):
        """
        :return: The average of [*self*] + others.
        """
        states = [_mm.info(x)[2] for x in others]

        if any(states):
            node = nodes.PlusMinusAverage.createNode()
            node.attr('operation').set(3)
            node.attr('input2D')[0].set(self)

            for i, (item, state) in enumerate(zip(others, states), start=1):
                node.attr('input2D')[i].put(item, state)

            return node.attr('output2D')

        return super().average(*others)