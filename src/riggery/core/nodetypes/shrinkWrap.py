from riggery.general.iterables import without_duplicates, expand_tuples_lists

from ..nodetypes import __pool__ as nodes
WeightGeometryFilter = nodes['WeightGeometryFilter']

from riggery.core.lib import names as _nm, mixedmode as _mm

import maya.cmds as m



class ShrinkWrap(WeightGeometryFilter):

    @classmethod
    def create(cls,
               *geos,
               projection:Union[Literal[
                   'Toward Inner Object',
                   'Toward Center',
                   'Parallel To Axes',
                   'Vertex Normals',
                   'Closest'
               ], _mm.MixedScalar]='Vertex Normals',
               closestIfNoIntersection:_mm.MixedScalar=False,
               reverse:_mm.MixedScalar=False,
               bidirectional:_mm.MixedScalar=False,
               offset:_mm.MixedScalar=0.0,
               targetInflation:_mm.MixedScalar=0.0,
               targetSmoothLevel:_mm.MixedScalar=0,
               **moreAttrs
               ):
        """
        :param \*geos: 'paper' (slave) geos first, 'rock' geo last; need at
            least two geometries passed in
        :param \*\*nodeConfig: inputs or values for node attributes
        """
        #----------------------------------|    Wrangle args

        geos = expand_tuples_lists(*geos)
        geos = without_duplicates((nodes['DagNode'](x).toShape() for x in geos))
        geos = list(geos)

        numGeos = len(geos)

        if numGeos < 2:
            raise ValueError(
                "Need at least one paper geometry and one rock geometry."
            )

        paperGeos = geos[:-1]
        rockGeo = geos[-1]

        kwargs = {}

        if _nm.Name.__elems__:
            kwargs['name'] = _nm.Name.evaluate(typeSuffix=cls.__typesuffix__)

        #----------------------------------|    Init build

        _paperGeos = list(map(str, paperGeos))

        _node = m.deformer(_paperGeos[0],
                           type='shrinkWrap', includeHiddenSelections=True)[0]

        for geo in _paperGeos[1:]:
            m.deformer(_node, e=True, g=geo)

        node = cls(_node)

        moreAttrs.update({'projection': projection,
                          'closestIfNoIntersection': closestIfNoIntersection,
                          'reverse': reverse,
                          'bidirectional': bidirectional,
                          'offset': offset,
                          'targetInflation': targetInflation,
                          'targetSmoothLevel': targetSmoothLevel})

        for k, v in moreAttrs.items():
            node.attr('k').put(v)

        rockGeo.worldOutput >> node.attr('targetGeom')
        node.attr('outputGeometry').evaluate()

        return node