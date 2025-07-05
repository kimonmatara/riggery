from ..lib import mixedmode as _mm
from ..datatypes import __pool__
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs


class Tensor3(__pool__['Tensor']):

    __shape__ = 3

    #-----------------------------------------|    Add

    def __add__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 3:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('input3D')[0].set(self)
                node.attr('input3D')[1].put(other, True)
                return node.attr('output3D').asType(self.plugClass())

            return NotImplemented
        return super().__add__(other)

    def __radd__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 3:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('input3D')[0].put(other, True)
                node.attr('input3D')[1].set(self)
                return node.attr('output3D').asType(self.plugClass())

            return NotImplemented
        return super().__radd__(other)
    
    #-----------------------------------------|    Sub

    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 3:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('operation').set(2)
                node.attr('input3D')[0].set(self)
                node.attr('input3D')[1].put(other, True)
                return node.attr('output3D').asType(self.plugClass())

            return NotImplemented
        return super().__sub__(other)

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)
        if isPlug:
            if shape == 3:
                node = nodes.PlusMinusAverage.createNode()
                node.attr('operation').set(2)
                node.attr('input3D')[0].put(other, True)
                node.attr('input3D')[1].set(self)
                return node.attr('output3D').asType(self.plugClass())

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
            node.attr('input3D')[0].set(self)

            for i, (item, state) in enumerate(zip(others, states), start=1):
                node.attr('input3D')[i].put(item, state)

            return node.attr('output3D').asType(self.plugClass())

        return super().average(*others)

    #-----------------------------------------|    Multiply

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').set(self)
                for dest in node.attr('input2').children:
                    dest.put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').set(self)
                node.attr('input2').put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            return NotImplemented
        return super().__mul__(other)

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                for dest in node.attr('input1').children:
                    dest.put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output').asType(self.plugClass())

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('input1').put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output').asType(self.plugClass())

            return NotImplemented
        return super().__rmul__(other)

    #-----------------------------------------|    Div

    def __truediv__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(2)
                node.attr('input1').set(self)
                for dest in node.attr('input2').children:
                    dest.put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(2)
                node.attr('input1').set(self)
                node.attr('input2').put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            return NotImplemented
        return super().__truediv__(other)

    def __rtruediv__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(2)
                for dest in node.attr('input1').children:
                    dest.put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output').asType(self.plugClass())

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(2)
                node.attr('input1').put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output').asType(self.plugClass())

            return NotImplemented
        return super().__rtruediv__(other)

    #-----------------------------------------|    Power

    def __pow__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(3)
                node.attr('input1').set(self)
                for dest in node.attr('input2').children:
                    dest.put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(3)
                node.attr('input1').set(self)
                node.attr('input2').put(other, isPlug)
                return node.attr('output').asType(self.plugClass())

            return NotImplemented
        return super().__pow__(other)

    def __rpow__(self, other):
        other, shape, isPlug = _mm.info(other)

        if isPlug:
            if shape is None:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(3)
                for dest in node.attr('input1').children:
                    dest.put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output').asType(self.plugClass())

            if shape == 3:
                node = nodes.MultiplyDivide.createNode()
                node.attr('operation').set(3)
                node.attr('input1').put(other, isPlug)
                node.attr('input2').set(self)
                return node.attr('output').asType(self.plugClass())

            return NotImplemented
        return super().__rpow__(other)