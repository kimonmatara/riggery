from typing import Optional

from ..nodetypes import __pool__ as nodes

WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m

from . import __pool__ as _nodes

from ..lib import names as _nm

from ...general.functions import short
from ...general.iterables import without_duplicates, expand_tuples_lists


class DeltaMush(WeightGeometryFilter):

    #-------------------------------------|    Constructor

    @classmethod
    @short(name='n', s='s')
    def create(cls,
               geo,
               iterations=20, *,
               scale=None,
               name:Optional[str]=None,
               **nodeConfig):

        kw = {}

        if name is None and _nm.Name.__elems__:
            name = _nm.Name.evaluate(typeSuffix=cls.__typesuffix__)

        if name:
            kw['name'] = name

        m.select(str(geo))
        node = _nodes['DependNode'](m.deltaMush(**kw)[0])

        node.attr("smoothingIterations").put(iterations)

        if scale is not None:
            node.attr('scale').put(scale)

        for k, v in nodeConfig.items():
            node.attr(k).put(v)

        return node

    #-------------------------------------|    Macro

    def copyTo(self, *geos) -> list['DeltaMush']:
        geos = expand_tuples_lists(*geos)
        geos = list(without_duplicates(map(nodes['DependNode'], geos)))

        if not geos:
            raise ValueError("No target geometries specified.")

        srcMacro = self.macro()

        out = []

        for geo in geos:
            thisMacro = srcMacro.copy()
            thisMacro['geo'] = geo
            out.append(self.createFromMacro(thisMacro))

        return out

    def macro(self) -> dict:
        attrNames = ['caching',
                     'envelope',
                     'smoothingIterations',
                     'smoothingAlgorithm',
                     'smoothingStep',
                     'inwardConstraint',
                     'outwardConstraint',
                     'distanceWeight',
                     'pinBorderVertices',
                     'displacement',
                     'scale',
                     'scaleX',
                     'scaleY',
                     'scaleZ']

        return {
            'geo': str(next(self.shapes)),
            'attrs': {
                attrName:self.attr(attrName).getState(input=True, value=True)
                for attrName in attrNames
            }
        }

    @classmethod
    def createFromMacro(cls, macro:dict) -> 'DeltaMush':
        node = cls.create(macro['geo'])

        for attrName, attrState in macro['attrs'].items():
            node.attr(attrName).setState(attrState)

        return node

    def getWeights(self, shapeIndex:int) -> list[float]:
        """
        :return: The full weight list for the specified shape index.
        """
        plug = self.attr('weightList')[0].attr('weights')
        return plug.readWeightsMulti(self.numPoints(0), 1.0)

    def setWeights(self, shapeIndex:int, weights:list[float]):
        """
        Sets the full weight list fot he specified shape index.
        """
        plug = self.attr('weightList')[0].attr('weights')
        plug.writeWeightsMulti(weights)
        return self