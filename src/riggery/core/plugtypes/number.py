from functools import reduce
from typing import Optional, Union, Literal, Iterable

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from ..plugtypes import __pool__
from ..lib import mixedmode as _mm
from ..lib import names as _nm
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
        node = nodes.MultDL.createNode()
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
            node = nodes.MultDL.createNode()
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
            node = nodes.MultDL.createNode()
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

    def floorDiv(self, other):
        """
        Here as a method rather than as an override for `__floordiv__`, to
        preserve parity with PyMEL, which uses `__floordiv__` for
        disconnections.
        """
        return (self / other).trunc()

    #-----------------------------------------|    Pow

    def sqrt(self):
        return self ** 0.5

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

    def neq(self, other, epsilon=None):
        out = self.eq(other, epsilon=epsilon)
        return out.NOT()

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
        Blends this number towards *other*. Basically lerp.

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

    def remap(self, oldMin, oldMax, newMin, newMax):
        """
        Performs simple linear remapping. The output will be unclamped.
        """
        ratio = (self - oldMin) / (oldMax - oldMin)
        return newMin + ((newMax - newMin) * ratio)

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

    def dampCeiling(self, dampingStart, ceiling, damping=2, /):
        """
        Directional max-clamping. Yields an output that will never overshoot an
        incrementing input. In other words, the 'driver' will always keep
        climbing as the output slows down to a stop at *ceiling*.

        Note that 'ceiling' should be a *heigher* number than 'dampingStart'.

        :param dampingStart: the value on this plug (the 'master') when the
            modified output should start slowing down
        :param ceiling: the maximum value that the output should ever reach
        :param damping: the amount of damping; 1 yields a regular 'clamp';
            higher values 'spread out' the damping more; defaults to 2
        """
        isBelow = self.le(dampingStart)
        regularRange = ceiling - dampingStart
        hasNoRange = regularRange <= 1e-5

        with _nm.Name('patchbay'):
            one = nodes.Network.createNode().addAttr('one', k=1, at='double',
                                                     dv=1, l=True)

        T = type(self)

        expandedRange = regularRange * damping
        safeDivisor = hasNoRange.ifElse(one, expandedRange, T)

        ratio = ((self - dampingStart) / safeDivisor).clamp(0, 1)
        ratio = 1 - (1 - ratio) ** damping
        solution = dampingStart + (regularRange * ratio)

        return isBelow.ifElse(self,
                              hasNoRange.ifElse(self.maxClamp(ceiling),
                                                solution,
                                                T),
                              T)

    def dampFloor(self, dampingStart, floor, damping=2, /):
        """
        Directional min-clamping. Yields an output that will never overshoot a
        *decrementing* input. In other words, the 'driver' will always keep
        dropping as the output slows down to a stop at *floor*.

        Note that 'floor' should be a *lower* number than 'dampingStart'.

        :param dampingStart: the value on this plug (the 'master') when the
            modified output should start slowing down
        :param floor: the minimum value that the output should ever reach
        :param damping: the amount of damping; 1 yields a regular 'clamp';
            higher values 'spread out' the damping more; defaults to 2
        """
        isAbove = self.ge(dampingStart)

        regularRange = dampingStart - floor
        hasNoRange = regularRange <= 1e-5

        with _nm.Name('patchbay'):
            one = nodes.Network.createNode().addAttr('one', k=1, at='double',
                                                     dv=1, l=True)

        expandedRange = regularRange * damping

        T = type(self)
        safeDivisor = hasNoRange.ifElse(one, expandedRange, T)

        ratio = ((dampingStart - self) / safeDivisor).clamp(0, 1)
        ratio = 1 - (1 - ratio) ** damping
        solution = dampingStart - (regularRange * ratio)

        return isAbove.ifElse(self,
                              hasNoRange.ifElse(self.minClamp(floor),
                                                solution,
                                                T),
                              T)

    def splitBias(self,
                  minRange:_mm.MixedScalar,
                  maxRange:_mm.MixedScalar
                  ) -> tuple[_mm.MixedScalar, _mm.MixedScalar]:
        """
        Returns two weights, (both in the 0 -> 1 range). The first weight
        represents the deviation of *self* towards *minRange*. The second weight
        represents the deviation of *self* towards *maxRange*.

        In other words, if *self* is at the exact midpoint between *minRange*
        and *maxRange*, the output weights will be 0.5, 0.5. If *self* is at
        *maxRange*, the weights will be 0.0, 1.0.
        """
        ratio = (self - minRange) / (maxRange - minRange)
        return 1 - ratio, ratio

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

    #-----------------------------------------|    Connections

    def slipInput(self, input):
        """
        If this attribute already has an input, multiplies *input* by the
        existing input before connecting it into this plug. Otherwise, connects
        *input* as-is.

        :param input: the input to connect into this plug
        :return: Self.
        """
        currentInputs = self.inputs(plugs=True)
        if currentInputs:
            input = currentInputs[0] * input
        input >> self
        return self

    #-----------------------------------------|    Multi read / write

    def readSparseWeightsMulti(self, length:int, default:float) -> list[float]:
        """
        :param length: the expected weights length
        :param default: the default to return for missing indices
        :return: The full weight list.
        """
        mplug = self.__apimplug__()

        if mplug.isArray:
            indices = mplug.getExistingArrayAttributeIndices()

            return [mplug.elementByLogicalIndex(i).asDouble()
                    if i in indices else default
                    for i in range(length)]

        raise TypeError("Not a multi.")

    def writeSparseWeightsMulti(self, weights:list[float], default:float):
        """
        :param weights: the full, non-sparse weights list
        :param default: the default value to omit from writing
        """
        mplug = self.__apimplug__()

        if mplug.isArray:
            indices = mplug.getExistingArrayAttributeIndices()

            if len(indices):
                dgMod = om.MDGModifier()

                for index in indices:
                    dgMod.removeMultiInstance(
                        mplug.elementByLogicalIndex(index),
                        True
                    )

                dgMod.doIt()

            for i, weight in enumerate(weights):
                if weight == default:
                    continue

                mplug.elementByLogicalIndex(i).setDouble(weight)

            return self

        raise TypeError("Not a multi.")