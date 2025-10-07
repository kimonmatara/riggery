from typing import Iterable, Literal, Optional
import maya.api.OpenMaya as om

from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists


class NurbsSurface(plugs['Geometry']):

    #-------------------------------------|    Esoteric queries

    def _getData(self) -> om.MObject:
        return self._getSamplingPlug(
            ).asMDataHandle().asNurbsSurfaceTransformed()

    #-------------------------------------|    Attachments

    @short(method='m',
           blendBias='bb',
           blendKnotInsertion='bki',
           parameter='p',
           keepMultipleKnots='kmk',
           directionU='du',
           reverse1='rv1',
           reverse2='rv2',
           swap1='sw1',
           swap2='sw2',
           twist='tw')
    def attach(self,
               other,
               method=0,
               blendBias=0.5,
               parameter=0.1,
               blendKnotInsertion=False,
               keepMultipleKnots=True,
               directionU=True,
               reverse1=False,
               reverse2=False,
               swap1=False,
               swap2=False,
               twist=False):
        """
        :param method/m: one of 0 ('Connect') or 1 ('Blend'), or an input
        :param blendBias/bb: skew the result toward the first or the second
            curve depending on the blend factory being smaller or larger than
            0.5; defaults to 0.5
        :param parameter/p: the parameter value for the positioning of the newly
            inserted knot; defaults to 0.1
        :param keepMultipleKnots/kmk: if true, keep multiple knots at the join
            parameter; defaults to True
        :param directionU/du: if True attach in U direction of surface and V
            direction otherwise; defaults to True
        :param reverse1/r1: reverse the direction (specified by directionU) of
            the first input surface before doing attach; defaults to False
        :param reverse2/r2: reverse the direction (specified by directionU) of
            the second input surface before doing attach; defaults to False
        :param swap1/sw1: swap the UV directions of the first input surface
            before doing attach; defaults to False
        :param swap2/sw2: swap the UV directions of the second input surface
            before doing attach; defaults to False
        :param twist/tw: reverse the second surface in the opposite direction
            (specified by directionU) before doing attach; defaults to False
        :return: The joined surface.
        """
        other = self.conformToOutput(other)
        node = nodes['AttachSurface'].createNode()
        method >> node.attr('method')
        blendBias >> node.attr('blendBias')
        blendKnotInsertion >> node.attr('blendKnotInsertion')
        keepMultipleKnots >> node.attr('keepMultipleKnots')
        directionU >> node.attr('directionU')
        reverse1 >> node.attr('reverse1')
        reverse2 >> node.attr('reverse2')
        swap1 >> node.attr('swap1')
        swap2 >> node.attr('swap2')
        twist >> node.attr('twist')

        self >> node.attr('inputSurface1')
        other >> node.attr('inputSurface2')
        return node.attr('outputSurface')

    @short(keep='k')
    def detach(self,
               parameter,
               direction=1,
               keep:Optional[Iterable]=None) -> list:

        node = nodes['DetachSurface'].createNode()
        node.attr('direction').set(direction)
        self >> node.attr('inputSurface')

        for i, parameter in enumerate(expand_tuples_lists(parameter)):
            parameter >> node.attr('parameter')[i]

        node.attr('outputSurface').evaluate()

        if keep is None:
            return list(node.attr('outputSurface'))

        if isinstance(keep, (tuple, list)):
            return [node.attr('outputSurface')[i] for i in keep]

        return node.attr('outputSurface')[keep]