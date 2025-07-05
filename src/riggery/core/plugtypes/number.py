from functools import reduce
from typing import Optional, Union

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from ..plugtypes import __pool__
from ..lib import mixedmode as _mm
from ..nodetypes import __pool__ as nodes


class Number(__pool__['Math']):

    #-----------------------------------------|    Add

    def sum(self, *others):
        """
        :return: The sum of this and *others*.
        """
        others = expand_tuples_lists(others)
        if others:
            node = nodes['Sum'].createNode()
            self >> node.attr('input')[0]
            for i, other in enumerate(others, start=1):
                node.attr('input')[i].put(other)
            return node.attr('output').asType(type(self))
        return self

    def __add__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes['Sum'].createNode()
            self >> node.attr('input')[0]
            node.attr('input')[1].put(other, isPlug)
            return node.attr('output').asType(type(self))

        return NotImplemented

    def __radd__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('input1D')[0].put(other, isPlug)
            self >> node.attr('input1D')[1]
            return node.attr('output1D').asType(type(self))

        return NotImplemented

    #-----------------------------------------|    Sub

    def __sub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input1D')[0]
            node.attr('input1D')[1].put(other, isPlug)
            return node.attr('output1D')

        return NotImplemented

    def __rsub__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.PlusMinusAverage.createNode()
            node.attr('operation').set(2)
            node.attr('input1D')[0].put(other, isPlug)
            self >> node.attr('input1D')[1]
            return node.attr('output1D')

        return NotImplemented

    #-----------------------------------------|    Average

    def average(self, *others):
        """
        Returns the average of [*self*] + others.
        """
        node = nodes.PlusMinusAverage.createNode()
        node.attr('operation').set(3)
        self >> node.attr('input1D')[0]

        for i, item in enumerate(others, start=1):
            node.attr('input1D')[i].put(item)

        return node.attr('output1D')

    #-----------------------------------------|    Multiply

    @cache_dg_output
    def __neg__(self):
        node = nodes.MultDoubleLinear.createNode()
        self >> node.attr('input1')
        node.attr('input2').set(-1.0)
        return node.attr('output').asType(type(self))

    def multiply(self, *others):
        """
        Shorthand: ``mul``
        """
        others = [__pool__['Attribute'](x) for x in expand_tuples_lists(others)]
        if others:
            node = nodes.Multiply.createNode()
            self >> node.attr('input')[0]
            for i, factor in enumerate(others, start=1):
                node.attr('input')[i].put(factor)
            return node.attr('output')
        return self

    mul = multiply

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultDoubleLinear.createNode()
            self >> node.attr('input1')
            node.attr('input2').put(other, isPlug)
            return node.attr('output')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            for child in node.attr('input1').children:
                self >> child
            node.attr('input2').put(other, isPlug)
            return node.attr('output')

        return NotImplemented

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultDoubleLinear.createNode()
            node.attr('input1').put(other, isPlug)
            self >> node.attr('input2')
            return node.attr('output')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('input1').put(other, isPlug)
            for child in node.attr('input2').children:
                self >> child
            return node.attr('output')

        return NotImplemented

    #-----------------------------------------|    Divide

    def __truediv__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)
            self >> node.attr('input1X')
            node.attr('input2X').put(other, isPlug)
            return node.attr('outputX')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)

            for dest in node.attr('input1').children:
                self >> dest

            node.attr('input2').put(other, isPlug)
            return node.attr('output')

        return NotImplemented

    def __rtruediv__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)
            node.attr('input1X').put(other, isPlug)
            self >> node.attr('input2X')
            return node.attr('outputX')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(2)
            node.attr('input1').put(other, isPlug)
            for dest in node.attr('input2').children:
                self >> dest
            return node.attr('output')

        return NotImplemented

    def __floordiv__(self, other):
        return (self / other).trunc()

    #-----------------------------------------|    Pow

    def __pow__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)
            self >> node.attr('input1X')
            node.attr('input2X').put(other, isPlug)
            return node.attr('outputX')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)

            for dest in node.attr('input1').children:
                self >> dest

            node.attr('input2').put(other, isPlug)
            return node.attr('outputX')

        return NotImplemented

    def __rpow__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape is None:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)
            node.attr('input1X').put(other, isPlug)
            self >> node.attr('input2X')
            return node.attr('outputX')

        if shape == 3:
            node = nodes.MultiplyDivide.createNode()
            node.attr('operation').set(3)

            for dest in node.attr('input2').children:
                self >> dest

            node.attr('input1').put(other, isPlug)
            return node.attr('outputX')

        return NotImplemented

    #-----------------------------------------|    Comparisons

    def eq(self, other, epsilon=None):
        """
        .. warning::

            Use this method, and not the equality (``==``) operator, since
            that's reserved for attribute identity checking.

        :param epsilon: an optional matching tolerance; defaults to None
        :return: A boolean output for 'equal'.
        """
        node = nodes['Equal'].createNode()
        self >> node.attr('input1')
        node.attr('input2').put(other)
        if epsilon is not None:
            node.attr('epsilon').put(epsilon)
        return node.attr('output')

    def gt(self, other):
        """
        :return: A boolean output for greater-than.
        """
        node = nodes['GreaterThan'].createNode()
        self >> node.attr('input1')
        node.attr('input2').put(other)
        return node.attr('output')

    def __gt__(self, other):
        return self.gt(other)

    def ge(self, other, epsilon=None):
        """
        :return: A boolean output for greater-than-or-equal.
        """
        return self.gt(other) | self.eq(other, epsilon)

    def __ge__(self, other):
        return self.ge(other)

    def lt(self, other):
        """
        :return: A boolean output for less-than.
        """
        node = nodes['LessThan'].createNode()
        self >> node.attr('input1')
        node.attr('input2').put(other)
        return node.attr('output')

    def __lt__(self, other):
        return self.lt(other)

    def le(self, other, epsilon=None):
        """
        :return: A boolean output for less-than-or-equal.
        """
        return self.lt(other) | self.eq(other, epsilon)

    def __le__(self, other):
        return self.le(other)

    #-----------------------------------------|    Graph flow

    def select(self, inputs, outputClass:Optional[type]=None, /):
        """
        Graph flow operator. Selects one of the specified inputs depending on
        the integer value of this plug.

        :param inputs: the list of inputs amongst which to select
        :param outputClass: a :class:`~riggery.plugtypes.Attribute` subclass to
            assign to the output instance (since ``output`` on ``choice`` is
            notoriously difficult to classify)
        :return: The output of the ``choice`` node.
        """
        node = nodes.Choice.createNode()
        self >> node.attr('selector')
        for i, input in enumerate(inputs):
            input >> node.attr('input')[i]

        out = node.attr('output')

        if outputClass is not None:
            out.__class__ = outputClass

        return out

    def ifElse(self,
               outputIfTrue,
               outputIfFalse,
               outputClass:Optional[type]=None, /):
        """
        :param outputIfTrue: the plug to return when this attribute evaluates
            as ``True``
        :param outputIfFalse: the plug to return when this attribute evaluates
            as ``False``
        :param outputClass: a :class:`~riggery.plugtypes.Attribute` subclass to
            assign to the output instance (since ``output`` on ``choice`` is
            notoriously difficult to classify)
        :return: The output of the ``choice`` node.
        """
        node = nodes.Choice.createNode()
        self >> node.attr('selector')

        outputIfTrue >> node.attr('input')[1]
        outputIfFalse >> node.attr('input')[0]

        out = node.attr('output')

        if outputClass is not None:
            out.__class__ = outputClass

        return out

    #-----------------------------------------|    Ranges

    def __mod__(self, other):
        """
        Implements the % operator (modulo).
        """
        node = nodes['Modulo'].createNode()
        self >> node.attr('input')
        node.attr('modulus').put(other)
        return node.attr('output')

    def __rmod__(self, other):
        """
        Implements the % operator (modulo).
        """
        node = nodes['Modulo'].createNode()
        node.attr('input').put(other)
        self >> node.attr('modulus')
        return node.attr('output')

    def blend(self, other, weight=0.5, *, swap:bool=False):
        """
        Blends this number towards *other*.

        :param other: the number towards which to blend
        :param weight: the blending weight; defaults to 0.5
        :param swap: swap the operands
        :return: The blended number.
        """
        node = nodes['BlendTwoAttr'].createNode()
        self >> node.attr('input')[1 if swap else 0]
        other >> node.attr('input')[0 if swap else 1]
        weight >> node.attr('attributesBlender')

        return node.attr('output')

    @cache_dg_output
    def abs(self):
        """
        :return: The absolute version of this number.
        """
        node = nodes['Absolute'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def trunc(self):
        """
        :return: The integer truncation of this number.
        """
        node = nodes['Truncate'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    def min(self, *others):
        """
        :param \*others: the scalars to compare to, unpacked
        :return: The minimum amongst [self] + others.
        """
        node = nodes['Min'].createNode()
        self >> node.attr('input')[0]

        for i, other in enumerate(others, start=1):
            node.attr('input')[i].put(other)

        return node.attr('output')

    def max(self, *others):
        """
        :param \*others: the scalars to compare to, unpacked
        :return: The maximum amongst [self] + others.
        """
        node = nodes['Max'].createNode()
        self >> node.attr('input')[0]

        for i, other in enumerate(others, start=1):
            node.attr('input')[i].put(other)

        return node.attr('output')

    def minClamp(self, other):
        """
        Clamps this value to a minimum of 'other'.

        :param other: the new range minimum
        :return: The min-clamped output.
        """
        return self.max(other)

    def maxClamp(self, other):
        """
        Clamps this value to a maximum of 'other'.

        :param other: the new range maximum
        :return: The max-clamped output.
        """
        return self.min(other)

    def clamp(self, min, max):
        """
        Clamps this output.
        """
        node = nodes['Clamp'].createNode()

        self >> node.attr('inputR')

        min >> node.attr('minR')
        max >> node.attr('maxR')

        return node.attr('outputR')

    def gatedClamp(self, floorOrCeiling, floorOpen, ceilingOpen):
        """
        Useful for squash-and-stretch control.

        :param floorOrCeiling: acts as a floor or ceiling for this output,
            depending on *floorOpen* and *ceilingOpen*
        :param floorOpen: when this is at 0.0, this output won't dip below
            *floorOrCeiling*
        :param ceilingOpen: when this is at 0.0, this output won't rise above
            *floorOrCeiling*
        :return: The clamped output.
        """
        ceiling = self.maxClamp(floorOrCeiling)
        ceiling = ceiling.blend(self, ceilingOpen)

        floor = ceiling.minClamp(floorOrCeiling)
        floor = floor.blend(ceiling, floorOpen)

        return floor

    def slowDownAndStop(self, ceiling, spreadFactor=1.0, power=2):
        """
        :param ceiling: the max clamp value; can be a plug
        :param spreadFactor: higher values will make the slowdown slower; lower
            values will make the slowdown faster; experiment in the range of
            0.5 -> 1.5 at first; defaults to 1.0
        :param power: the easing power; must be one of 2, 3 or 4; higher powers
            work better with higher spread factors; defaults to 2
        :return: The constrained vector.
        """
        assert power in (2, 3, 4), "power must be one of 2, 3, 4"

        ceiling = _mm.info(ceiling)[0]
        spreadFactor = _mm.info(spreadFactor)[0]

        easeStart = ceiling / (2 ** spreadFactor)
        easeEnd = ceiling * (2 ** spreadFactor)

        t = (self - easeStart) / (easeEnd - easeStart)
        s = (1.0 - t)
        easedT = 1.0 - s ** power

        out = easeStart + easedT * (ceiling - easeStart)
        out = self.ge(easeEnd).ifElse(
            ceiling,
            self.le(easeStart).ifElse(
                self,
                out
            )
        )

        out = out.asType(type(self))

        return out

    #-----------------------------------------|    Expression utils

    def unaryExpr(self, operation):
        """
        Configures an expression node to run a unary expression on this plug,
        and returns its output.

        Expects native units.

        :param str operation: the expression operation, for example ``'sin'``
        :return: the expression output
        :rtype: :class:`~bongo.plugtypes.number.Number`
        """
        node = nodes['Expression'].createNode()

        expr = '.O[0] = {}({})'.format(operation, self)
        node.attr('expression').set(expr)
        m.expression(str(node), e=True, alwaysEvaluate=False)

        return node.attr('output')[0]

    #-----------------------------------------|    Trigonometry

    @cache_dg_output
    def cos(self):
        """
        :return: The cosine of this angle (radians).
        """
        # If this is bugging out, check whether the inputs must be clamped per
        # the older expression behaviour
        node = nodes['Cos'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def acos(self):
        """
        :return: The arc cosine of this angle (radians).
        """
        node = nodes['Acos'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def sin(self):
        """
        :return: The sine of this angle (radians).
        """
        node = nodes['Sin'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def asin(self):
        """
        :return: The arc sine of this angle (radians).
        """
        node = nodes['Asin'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def tan(self):
        """
        :return: The tangent of this angle (radians).
        """
        node = nodes['Tan'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def atan(self):
        """
        :return: The arc tangent of this angle (radians).
        """
        node = nodes['Atan'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    #-----------------------------------------|    Conversions

    @cache_dg_output
    def asScaleMatrix(self):
        """
        :return: A matrix with the magnitudes of all the base vectors set to
            this scalar.
        """
        node = nodes['FourByFourMatrix'].createNode()
        for slot in ('in00', 'in11', 'in22'):
            self >> node.attr(slot)
        return node.attr('output')