from typing import Optional
from ..nodetypes import __pool__ as nodes
WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m
from ..lib import names as _nm
from . import __pool__ as _nodes
from riggery.general.functions import short


class DeltaMush(WeightGeometryFilter):

    #-------------------------------------|    Constructor
    
    @classmethod
    @short(name='n', s='s')
    def create(cls,
               geo,
               iterations=20, *,
               scale=None,
               name:Optional[str]=None):

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

        return node