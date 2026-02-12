from typing import Union, Optional, Literal, Iterator

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..lib import names as _nm

from riggery.general.functions import short

WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m

#-----------------------------------------|
#-----------------------------------------|    INTERFACES
#-----------------------------------------|

class Tween:

    """Interface for editing of inbetween targets."""

    #---------------------------|    Inst

    def __init__(self, target:'Target', index:int):
        self._target = target
        self._index = index
        self._node = target._node

    #---------------------------|    Basics

    def node(self) -> 'BlendShape':
        """Returns the blend shape node."""
        return self._node

    @property
    def target(self):
        """
        Navigates upwards to the :class:`Target` instance that owns this tween.
        """
        return self._target

    @property
    def index(self) -> int:
        """
        :return: The 5000-6000 index that corresponds to this tween.
        """
        return self._index

    @property
    def ratio(self) -> float:
        """
        :return: The tween ratio.
        """
        return self.node().tweenItemIndexToRatio(self._index)

    #---------------------------|    Plug shortcuts

    @property
    def item(self) -> 'Attribute':
        """:return: The ``inputTargetItem`` slot output."""
        return self._target.group.attr('inputTargetItem')[self._index]

    @property
    def geoInput(self):
        """:return: The ``inputGeomTarget`` geometry input."""
        return self.item.attr('inputGeomTarget')

    #---------------------------|    Repr

    def __repr__(self):
        return "{}[{}]".format(self._target, self.ratio)


class Target:

    """
    Interface for editing 'main' targets (i.e. not inbetweens).
    Use subscripting with floats to edit tweens.
    """

    #---------------------------|    Inst

    def __init__(self, targets:'Targets', index:int):
        self._targets = targets
        self._node = self._targets._node
        self._index = index

    #---------------------------|    Basics

    @property
    def index(self) -> int:
        """:return: The target weight index."""
        self._index

    @property
    def targets(self):
        """
        Navigates upwards to the :class:`Targets` interface.
        """
        return self._targets

    def node(self) -> 'BlendShape':
        """:return: The blend shape node."""
        return self._node

    #---------------------------|    Weight

    @property
    def weight(self):
        """:return: The corresponding ``weight`` input."""
        return self._node.attr('weight')[self._index]

    #---------------------------|    Alias

    def getAlias(self) -> Optional[str]:
        """Implements the ``.alias`` property."""
        return self.weight.alias

    def setAlias(self, alias:Optional[str]):
        """Implements the ``.alias`` property."""
        self.weight.alias = alias
        return self

    def clearAlias(self):
        """Implements the ``.alias`` property."""
        del(self.weight.alias)
        return self

    alias = property(getAlias, setAlias, clearAlias)

    #---------------------------|    Plug shortcuts

    @property
    def group(self) -> 'Attribute':
        """:return: The ``inputTargetGroup`` slot."""
        return self._node.attr('inputTarget'
                               )[0].attr('inputTargetGroup')[self._index]

    @property
    def targetMatrix(self) -> 'Attribute':
        """
        :return:The matrix input for the driver transform, if the target is in
            'transform' post mode.
        """
        return self.group.attr('targetMatrix')

    def getTransform(self) -> Optional['nodes.Transform']:
        """Implements the ``.transform`` property."""
        out = self.targetMatrix.inputs(type='transform')
        if out:
            return out[0]

    def setTransform(self, transform:Optional['nodes.Transform']):
        """Implements the ``.transform`` property."""
        if transform is None:
            return self.clearTransform()
        nodes['Transform'](transform).attr('worldMatrix') >> self.targetMatrix

    def clearTransform(self):
        """Implements the ``.transform`` property."""
        self.targetMatrix.disconnect(inputs=True)

    transform = property(getTransform, setTransform, clearTransform)

    @property
    def geoInput(self) -> 'Attribute':
        """:return: The geometry input for the tween at ratio 1.0."""
        return self[1.0].geoInput

    #---------------------------|    Add tween

    @short(connect='c',
           topologyCheck='tc')
    def add(self,
            geo,
            ratio:float,
            connect:Optional[bool]=None,
            topologyCheck:bool=True):
        """
       Adds an inbetween shape.

       :param geo: the target geometry
       :param ratio: the weight at which to create the inbetween target
       :param connect/c: keep the target connected; defaults to False if the
           main target is a 'tangentSpace' or 'transform' target, otherwise
           True
       """
        node = self.node()
        _node = str(node)
        args = (_node,)

        kwargs = {'e': True,
                  'ib': True,
                  't':(str(next(node.shapes)), self._index, str(geo), ratio),
                  'tc': topologyCheck}

        postDeformMode = self.group.attr('postDeformersMode')()

        if postDeformMode == 0: # regular
            if connect is None:
                connect = True
        else:
            if connect is None:
                connect = False

            if postDeformMode == 1: # tangent
                kwargs['tangentSpace'] = True

            elif postDeformMode == 2: # transform
                transform = self.transform

                if transform:
                    kwargs['transform'] = str(transform)

        # run the command
        m.blendShape(*args, **kwargs)

        tween = self[ratio]

        if connect:
            if node.attr('origin')() == 0:
                geoOutput = geo.worldOutput
            else:
                geoOutput = geo.localOutput

            geoOutput >> tween.geoInput
        else:
            tween.geoInput.disconnect(inputs=True)

        return tween

    #---------------------------|    Get tweens

    def ratioExists(self, ratio:float) -> bool:
        """
        :return: ``True`` if this target includes a tween at the specified
            ratio.
        """
        return self.node().tweenRatioToItemIndex(ratio) in self.indices()

    def indices(self) -> Iterator[int]:
        """
        :return: An iterator of indices in the 5000-6000 range, corresponding to
            tweens for this target.
        """
        for index in self.group.attr('inputTargetItem').indices():
            if index == 0:
                continue
            yield index

    def ratios(self) -> Iterator[float]:
        """:return: An iterator of tween ratios for this target."""
        node = self.node()

        for index in self.group.attr('inputTargetItem').indices():
            if index == 0:
                continue
            yield node.tweenItemIndexToRatio(index)

    def __getitem__(self, ratio:float):
        index = self.node().tweenRatioToItemIndex(ratio)

        if index in self.indices():
            return Tween(self, index)

        raise IndexError("no tween at ratio {}".format(ratio))

    def __iter__(self) -> Iterator[Tween]:
        for index in self.indices():
            yield Tween(self, index)

    def __len__(self):
        return len(list(self.indices()))

    def __bool__(self):
        return len(self) > 0

    #---------------------------|    Repr

    def __repr__(self):
        content = self.alias

        if content is None:
            content = self._index

        return "{}[{}]".format(repr(self._targets), repr(content))


class Targets:

    #---------------------------|    Inst

    def __init__(self, node):
        self._node = node

    #---------------------------|    Basics

    def node(self) -> 'BlendShape':
        """:return: The blend shape node."""
        return self._node

    #---------------------------|    Get

    def keys(self) -> Iterator[str]:
        """:return: An iterator of weight aliases."""
        for slot in self.node().attr('weight'):
            alias = slot.alias
            if alias is None:
                continue
            yield alias

    def indices(self) -> Iterator[int]:
        """:return: An iterator of weight indices."""
        yield from self.node().attr('weight').indices()

    def getByAlias(self, alias:str) -> 'Target':
        """
        :return: A :class:`Target` instance from the given alias.
        """
        for slot in self.node().attr('weight'):
            if slot.alias == alias:
                return Target(self, slot.index())
        raise KeyError("no target with alias '{}'".format(alias))

    def getByIndex(self, index:int) -> 'Target':
        """
        :return: A :class:`Target` instance from the given index.
        """
        if self.indexExists(index):
            return Target(self, index)
        raise IndexError("no target at index {}".format(index))

    def aliasExists(self, alias:str) -> bool:
        """:return: ``True`` if the specified target alias exists."""

        for slot in self.node().attr('weight'):
            if slot.alias == alias:
                return True
        return False

    def indexExists(self, index:int) -> bool:
        """:return: ``True`` if the specified target index exists."""

        return index in self.node().attr('weight').indices()

    def __len__(self):
        return len(self.node().attr('weight'))

    def __bool__(self):
        return len(self) > 0

    def __getitem__(self, indexOrAlias:Union[str, int]):
        if isinstance(indexOrAlias, str):
            return self.getByAlias(indexOrAlias)
        return self.getByIndex(indexOrAlias)

    def __iter__(self):
        for index in self.indices():
            yield Target(self, index)

    #---------------------------|    Add

    @short(alias='a',
           tangentSpace='ts',
           connect='c',
           index='i',
           transform='t',
           topologyCheck='tc')
    def add(self,
            geo:'nodes.DagNode',
            alias:Optional[str]=None, *,
            tangentSpace:bool=False,
            transform:Optional['nodes.Transform']=None,
            connect:Optional[bool]=None,
            index:Optional[int]=None,
            topologyCheck:bool=True) -> 'Target':
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
       """
        #------------------|    Wrangle args

        node = self.node()

        post = node.inPostMode()
        geo = nodes['DagNode'](geo)

        if index is None:
            index = node.attr('weight').nextIndex()

        elif index in node.attr('weight').indices():
            raise ValueError(f"index {index} in use")

        if alias is None:
            alias = geo.toTransform().shortName(sns=True)

        if self.aliasExists(alias):
            raise ValueError(f"alias '{alias}' in use")

        kwargs = {'topologyCheck': topologyCheck}

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

        base = next(node.shapes)

        m.blendShape(str(node),
                     e=True,
                     t=[str(base), index, str(geo), 1.0],
                     w=[index, 0.0],
                     **kwargs)

        #------------------|    Post-config

        target = Target(self, index)
        geoInput = target.geoInput

        if connect:
            worldSpace = node.attr('origin')() == 0
            geoPlug = geo.worldOutput if worldSpace else geo.localOutput
            geoPlug >> geoInput
        else:
            geoInput.disconnect(inputs=True)

        target.alias = alias

        return target

    #---------------------------|    Repr

    def __repr__(self):
        return '{}.targets'.format(repr(self._node))

#-----------------------------------------|
#-----------------------------------------|    MAIN CLASS
#-----------------------------------------|

class BlendShape(WeightGeometryFilter):

    #---------------------------|    Constructor

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

    #---------------------------|    Interfaces

    @property
    def targets(self) -> Targets:
        return Targets(self)

    #---------------------------|    General queries

    def inPostMode(self) -> bool:
        """
        :return: True if the blend shape node is configured for
            'post-deformation', otherwise False.
        """
        return self.attr('deformationOrder')() == 1

    @staticmethod
    def tweenRatioToItemIndex(ratio:float) -> int:
        ratio = round(ratio, 3)
        ratio = ratio * 1000
        return 5000 + int(ratio)

    @staticmethod
    def tweenItemIndexToRatio(itemIndex:int) -> float:
        return (itemIndex - 5000) / 1000