from typing import Union, Optional, Literal, Iterator

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..lib import names as _nm

from riggery.general.functions import short

WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m


class BlendShape(WeightGeometryFilter):

    #-------------------------------------|    Constructor

    @classmethod
    @short(name='n')
    def create(cls,
               base:Union['nodes.DeformableShape', 'nodes.Transform'], *,
               name:Optional[str]=None,
               pre:Optional[bool]=None,
               post:Optional[bool]=None,
               origin:Literal['world', 'local']='local'):
        """
        This is a simplified constructor that doesn't wrangle targets at all. It
        only initializes the blend shape node on the base geometry.
        """

        #--------------|    Resolve args

        kwargs = {'origin': origin, 'suppressDialog': True}

        if name:
            kwargs['name'] = name

        elif _nm.Name.__elems__:
            kwargs['name'] = _nm.Name.evaluate(
                typeSuffix=cls.__typesuffix__
            )

        if (not pre) and (not post):
            kwargs['automatic'] = True
        elif pre:
            kwargs['frontOfChain'] = True
        else:
            kwargs['before'] = True

        return cls(m.blendShape(str(base), **kwargs)[0])

    #-------------------------------------|    General queries

    def inPostMode(self) -> bool:
        """
        :return: True if the blend shape node is configured for
            'post-deformation', otherwise False.
        """
        return self.attr('deformationOrder')() == 1

    #-------------------------------------|
    #-------------------------------------|    Target wrangling
    #-------------------------------------|

    #-------------------------|    Aliases

    def iterWeightAliases(self) -> Iterator[Optional[str]]:
        """This will also yield None for any targets with no assigned alias."""
        for slot in self.attr('weight'):
            yield slot.alias

    #-------------------------|    Query targets

    @staticmethod
    def weightToItemIndex(weight:float) -> int:
        weight = round(weight, 3)
        weight = weight * 1000
        return 5000 + int(weight)

    @staticmethod
    def itemIndexToWeight(itemIndex:int) -> float:
        return (itemIndex - 5000) / 1000

    def getTargetGeoInput(self, targetIndex:int, weight:Optional[float]=None):
        if weight is None:
            itemIndex = 6000
        else:
            itemIndex = self.weightToItemIndex(weight)

        return self.attr('inputTarget'
                         )[0].attr('inputTargetGroup'
                                   )[targetIndex].attr('inputTargetItem'
                                                       )[itemIndex].attr(
            'inputGeomTarget'
        )

    #-------------------------|    Add targets

    @short(alias='a',
           tangentSpace='ts',
           connect='c',
           index='i',
           transform='t',
           topologyCheck='tc')
    def addTarget(self,
                  geo:'nodes.DagNode',
                  alias:Optional[str]=None, *,
                  tangentSpace:bool=False,
                  connect:Optional[bool]=None,
                  transform:Optional['nodes.Transform']=None,
                  index:Optional[int]=None,
                  topologyCheck:bool=True) -> int:
        """
        Adds a main (not inbetween) target. The weight for the new target will
        be 0.0 by default.

        :param geo: the target geometry
        :param alias: the weight alias; defaults to the geometry transform's
            short name
        :param tangentSpace/ts: only available if the blend shape node is in
            'post' mode; defaults to False
        :param connect/c: connect the target geometry; defaults to False if one
            of 'tangentSpace' or 'transform' were specified, otherwise True
        :param transform/t: if provided, will be used to configure a 'transform'
            space blend shape
        :param index/i: a preferred index for the target; defaults to the next
            available index
        :param topologyCheck/tc: check topology matches the bases; defaults to
            True
        :raises ValueError: 'tangentSpace' and 'transform' can't be used; blend
            shape node not in 'post mode
        :raises ValueError: 'tangentSpace' and 'transform' can't be used
            together
        :raises ValueError: index in use
        :raises ValueError: alias in use
        :return: The index of the new target.
        """
        #------------------|    Wrangle args

        post = self.inPostMode()
        geo = nodes['DagNode'](geo)

        kwargs = {'topologyCheck': topologyCheck}

        if index is None:
            index = self.attr('weight').nextIndex()

        elif index in self.attr('weight').indices():
            raise ValueError(f"index {index} in use")

        if alias is None:
            alias = geo.toTransform().shortName(sns=True)

        if alias in self.iterWeightAliases():
            raise ValueError(f"alias '{alias}' in use")

        if tangentSpace or transform:
            if not post:
                raise ValueError("'tangentSpace' and 'transform' can't be"
                                 f" used: {self} not in 'post' mode")

            if tangentSpace:
                if transform:
                    raise ValueError("'tangentSpace' and 'transform' can't be"
                                     " used together")
                kwargs['tangentSpace'] = True
            else:
                kwargs['transform'] = str(transform)

            if connect is None:
                connect = False
        else:
            if connect is None:
                connect = True

        #------------------|    Run

        base = next(self.shapes)

        m.blendShape(str(self),
                     e=True,
                     t=[str(base), index, str(geo), 1.0],
                     w=[index, 0.0],
                     **kwargs)

        #------------------|    Post-config

        geoInput = self.getTargetGeoInput(index)

        if connect:
            worldSpace = self.attr('origin')() == 0
            geoPlug = geo.worldOutput if worldSpace else geo.localOutput
            geoPlug >> geoInput
        else:
            geoInput.disconnect(inputs=True)

        weightPlug = self.attr('weight')[index]
        weightPlug.alias = alias

        return index

    # @short(connect='c',
    #        topologyCheck='tc')
    # def addInbetweenTarget(self,
    #                        geo,
    #                        index:int,
    #                        weight:float,
    #                        connect:Optional[bool]=None,
    #                        topologyCheck:bool=True):
    #     """
    #     Adds an inbetween shape.
    #
    #     :param geo: the target geometry
    #     :param index: the index of the main target (0-based)
    #     :param weight: the weight at which to create the inbetween target
    #     :param connect/c: keep the target connected; defaults to False if the
    #         main target is a 'tangentSpace' or 'transform' target, otherwise
    #         True
    #     """
    #     geo = nodes['DagNode'](geo)
    #
    #     m.blendShape(str(self),
    #                  e=True,
    #                  ib=True,
    #                  t=(str(next(self.shapes)), index, str(geo), weight),
    #                  tc=topologyCheck)
    #
    #     # Stub: need post config stuff here, complete soon