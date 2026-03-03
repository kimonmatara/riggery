import json
from copy import deepcopy
import re
from typing import Union, Optional, Literal, Iterator, Iterable
from functools import reduce

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..lib import names as _nm, poses as _pos

from riggery.general.functions import short
from riggery.internal.typeutil import UNDEFINED
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.mappings import deep_merge_dicts, deep_intersect_dicts

WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m
import maya.api.OpenMaya as om

#-----------------------------------------|
#-----------------------------------------|    HELPERS
#-----------------------------------------|

def checkTransformUnambiguouslyExists(lookup:str, quiet:bool=False) -> bool:
    matches = m.ls(lookup, type='transform')
    if len(matches) == 1:
        return True

    if not quiet:
        m.warning(f"No unambiguous match for {lookup}")

    return False

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

    #---------------------------|    Higher-level

    def _cleanupOutputGeo(self, geoXform, parent=None) -> 'nodes.Transform':
        geoXform = nodes['Transform'](geoXform)
        geoXform.parent = parent

        ratio = self.ratio

        name = self.node()._buildTargetName(
            self.target.index,
            ratio=None if ratio == 1.0 else ratio
        )

        geoXform.setName(name, conformShapeNames=True)

        return geoXform

    def _connectInputShape(self, shape):
        shape = nodes['DependNode'](shape)

        if self.node().attr('origin')() == 0:
            src = shape.worldOutput
        else:
            src = shape.localOutput

        src >> self.geoInput

    def _doCreateShapeCmd(self) -> 'nodes.Shape':
        return nodes['Transform'](m.sculptTarget(str(self.node()),
                                                 e=True,
                                                 t=self.target.index,
                                                 ibw=self.ratio,
                                                 r=True)[0]).shape

    @short(connect='con',
           parent='p')
    def createShape(self, *,
                    connect:Optional[bool]=None,
                    parent:Optional['nodes.Transform']=None) -> 'nodes.Shape':
        """
        This method will always create a shape, even if one is already
        present and connected. To reuse a shape instead, use :meth:`getShape`.

        :param connect/con: this will default to True or False depending on
            circumstances
        :param parent/p: an optional destination parent for the generated
            geometry's transform.
        :return: The geometry shape.
        """
        incomingConnection = next(self.geoInput.iterInputs(plugs=True), None)

        if incomingConnection:
            inputNode = incomingConnection.node()

            if isinstance(inputNode, nodes['DeformableShape']):
                incomingConnection // self.geoInput
                outShape = self._doCreateShapeCmd()
                self._cleanupOutputGeo(outShape.parent, parent=parent)

                if connect is None:
                    connect = True

                if not connect:
                    self.geoInput.disconnect(inputs=True)

                return outShape
            else:
                outShape = incomingConnection.createShape()
                self._cleanupOutputGeo(outShape.parent, parent=parent)
                self._connectInputShape(outShape)

                return outShape
        else:
            outShape = self._doCreateShapeCmd()
            self._cleanupOutputGeo(outShape.parent, parent=parent)

            if connect is None:
                connect = not self.target.inPostMode()

            if not connect:
                self.geoInput.disconnect(inputs=True)

            return outShape

    def update(self, src:'nodes.DagNode', *, connect:bool=False):
        """
        Temporarily connects a new shape and afterwards disconnects it.

        :param connect/con: keep the connection; defaults to False
        """
        incomingConnection = next(self.geoInput.iterInputs(plugs=True), None)

        src = nodes['DagNode'](src).toShape()
        self._connectInputShape(src)

        if not connect:
            if incomingConnection:
                incomingConnection >> self.geoInput
            else:
                self.geoInput.disconnect(inputs=True)

        return self

    @short(create='c',
           connect='con',
           parent='p',
           inspectScene='ins')
    def getShape(
            self, *,
            create:bool=False,
            connect:Optional[bool]=None,
            inspectScene:bool=False,
            parent:Optional['nodes.Transform']=None
    ) -> Optional['nodes.Shape']:
        """
        :param create/c: create a shape if one could not be found from the input
            connection; False
        :param connect/con: ignored if *create* is False or a scene shape was
            not retrieved; defaults to True or False depending on circumstances
        :param parent/p: an optional destination parent for the generated
            shape's transform; defaults to None
        :param inspectScene/ins: if no connected shape could be found, look for
            a geometry in the scene that obeys the 'scene map' naming
            convention for blend shapes; defaults to False
        :return: The retrieved or recreated shape, or None.
        """
        incomingConnection = next(self.geoInput.iterInputs(plugs=True), None)

        if incomingConnection:
            inputNode = incomingConnection.node()

            if isinstance(inputNode, nodes['DeformableShape']):
                return inputNode
            else:
                if create:
                    outShape = incomingConnection.createShape()
                    self._cleanupOutputGeo(outShape.parent, parent=parent)

                    if connect is None:
                        connect = True

                    if connect:
                        self._connectInputShape(outShape)

                    return outShape
        else:
            if inspectScene:
                baseShape = next(self.node().shapes)
                baseXf = baseShape.parent
                baseGeoName = baseXf.shortName()
                lookup = f"{baseGeoName}_*_{_nm.BLENDSUFFIX}"

                matches = m.ls(lookup, type='transform')

                if matches:
                    pat = (r"^"
                           + baseGeoName
                           + r"_(.*?)(?:_([0-9]+))?_"
                           + _nm.BLENDSUFFIX
                           + r"$")

                    for match in matches:
                        matchName = match.split('|')
                        mt = re.match(pat, matchName)

                        if mt:
                            alias, pc = mt.groups()

                            if pc is None:
                                ratio = 1.0
                            else:
                                ratio = float(pc) / 100.0

                            if ratio == self.ratio:
                                outShape = nodes['Transform'](match).shape

                                if connect is not None and connect:
                                    self._connectInputShape(outShape)

                                return outShape

            if create:
                outShape = self._doCreateShapeCmd()
                self._cleanupOutputGeo(outShape.parent, parent=parent)

                if connect is None:
                    connect = not self.target.inPostMode()

                if not connect:
                    self.geoInput.disconnect(inputs=True)

                return outShape

    shape = property(getShape)

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
        return self._index

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

    def solo(self, weight:float=1.0, /) -> 'Target':
        """
        Sets this target to 1.0 (or *weight) and all other targets to 0.0.

        This is a 'soft' implementation. It will fail loudly if the weight plug
        is locked or connected.
        """
        node = self.node()

        for index in node.attr('weight').indices():
            node.attr('weight')[index].set(weight
                                           if index == self.index else 0.0)

        return self

    @property
    def weight(self):
        """:return: The corresponding ``weight`` input."""
        return self._node.attr('weight')[self._index]

    #---------------------------|    Granular weights

    def getWeights(self) -> list[float]:
        """
        :return: The per-vertex weights for this target.
        """
        return self.node().getWeightsForTargetByIndex(self._index)

    def setWeights(self, weights:list[float]) -> 'Target':
        """
        Sets the weights for this target.

        :param weights: the weights to set; the list must be complete
            (non-sparse)
        """
        self.node().setWeightsForTargetByIndex(self._index, weights)
        return self

    weights = property(getWeights, setWeights)

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

    def inPostMode(self) -> bool:
        return self.group.attr('postDeformersMode')() != 0

    def inTangentMode(self) -> bool:
        return self.group.attr('postDeformersMode')() == 1

    def inTransformMode(self) -> bool:
        return self.group.attr('postDeformersMode')() == 2

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

    #---------------------------|    Update

    @short(transform='t',
           connect='con',
           alias='a')
    def update(self,
               geo, *,
               transform:Optional[Union[str, 'nodes.Transform']]=None,
               connect:Optional[bool]=None,
               alias:Optional[str]=None) -> 'Target':
        """
        :param geo: the geometry with which to update this target
        :param connect/c: default varies depending on circumstances
        :param transform/t: an optional transform for transform-driven 'post'
            targets; defaults to None
        :param alias/a: an optional new alias; defaults to None (no change)
        :raises TypeError: Can't connect the transform because the target is not
            a transform-mode target.
        """
        if transform is not None:
            if self.inTransformMode():
                transform = nodes['Transform'](transform)
                transform.attr('worldMatrix') >> self.group.attr('targetMatrix')
            else:
                _id = self.alias

                if _id is None:
                    _id = self.index
                else:
                    _id = repr(_id)

                raise TypeError(
                    f"Can't update target {_id} with transform "
                    f"'{transform}': target not in transform mode"
                )

        self[1.0].update(geo, connect=connect)

        if alias is not None:
            self.alias = alias

        return self

    #---------------------------|    Add tween

    @short(connect='c',
           topologyCheck='tc',
           update='u')
    def add(self,
            geo,
            ratio:float, *,
            connect:Optional[bool]=None,
            topologyCheck:bool=True,
            update:bool=False) -> 'Tween':
        """
        Adds an inbetween shape.

        :param geo: the target geometry
        :param ratio: the weight at which to create the inbetween target
        :param connect/c: keep the target connected; defaults to False if the
           main target is a 'tangentSpace' or 'transform' target, otherwise
           True
        :param update/u: if the ratio already exists, attempt to update it;
            defaults to False
        :raises ValueError: The ratio already exists.
        """
        try:
            existing = self[ratio]
        except IndexError:
            existing = None

        if existing:
            return existing.update(geo, connect=connect)

        bsn = self.node()
        _bsn = str(bsn)

        args = (_bsn,)

        geoShape = nodes['DagNode'](geo).toShape()
        geoXf = geoShape.parent

        kwargs = {'e': True,
                  'ib': True,
                  't':(str(next(bsn.shapes)), self._index, str(geoXf), ratio),
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
            tween._connectInputShape(geoShape)
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

    #---------------------------|    Add target

    @short(alias='a',
           tangentSpace='ts',
           connect='c',
           index='i',
           transform='t',
           topologyCheck='tc',
           skinCluster='sc',
           update='u')
    def add(self,
            geo:'nodes.DagNode',
            alias:Optional[str]=None, *,
            tangentSpace:bool=False,
            transform:Optional['nodes.Transform']=None,
            connect:Optional[bool]=None,
            index:Optional[int]=None,
            topologyCheck:bool=True,
            update:bool=False) -> 'Target':
        """
        Adds a main (not inbetween) target. The weight for the new target will
        be 0.0 by default.

        :param geo: the target geometry
        :param alias: the weight alias; defaults to the geometry transform's
            short name
        :param update/u: if the target already exists, attempt to update it;
            defaults to False
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
        geoShape = nodes['DagNode'](geo).toShape()
        geoXf = geoShape.parent
        bsn = self.node()

        existing = None

        if index is None:
            index = bsn.attr('weight').nextIndex()
        else:
            try:
                existing = self.getByIndex(index)
            except IndexError:
                pass

            if existing is not None:
                if update:
                    return existing.update(geoXf,
                                           transform=transform,
                                           connect=connect,
                                           alias=alias)
                else:
                    raise ValueError("index in use: {}".format(index))

        if alias is None:
            alias = geoXf.shortName(sns=True)

        try:
            existing = self.getByAlias(alias)
        except KeyError:
            pass

        if existing is not None:
            if update:
                return existing.update(geoXf,
                                       transform=transform,
                                       connect=connect)
            else:
                raise ValueError("alias in use: {}".format(index))

        if index is None:
            index = bsn.attr('weight').index.nextIndex()

        kwargs = {'topologyCheck': topologyCheck}

        post = bsn.inPostMode()

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

        base = next(bsn.shapes)

        m.blendShape(str(bsn),
                     e=True,
                     t=[str(base), index, str(geoXf), 1.0],
                     w=[index, 0.0],
                     **kwargs)

        #------------------|    Post-config

        target = Target(self, index)
        target.alias = alias
        geoInput = target.geoInput

        if connect:
            worldSpace = bsn.attr('origin')() == 0
            src = (geoShape.worldOutput
                       if worldSpace else geoShape.localOutput)
            src >> geoInput
        else:
            geoInput.disconnect(inputs=True)

        return target

    #---------------------------|    Repr

    def __repr__(self):
        return '{}.targets'.format(repr(self._node))

#-----------------------------------------|
#-----------------------------------------|    MAIN CLASS
#-----------------------------------------|

class BlendShape(WeightGeometryFilter):
    """
    Notes on scene maps
    ===================

    Scene maps rely on in-scene geometries that follow this naming convention:

    ``<base geo name>_<target descriptor>_<percentage>_BLEND``

    The ``<percentage>`` element may be omited.

    Sculpted blend shape targets need an embedded inversion pose in an attribute
    called 'inversionPose'. Poses can be generated using the tools in
    :mod:`riggery.core.lib.poses`, and embedded using
    :meth:`setInversionPoseOnTargetGeo` and
    :meth:`getInversionPoseFromTargetGeo` on this class.
    """

    #---------------------------|    Constructors

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

    #---------------------------|    Retargeting

    @short(parent='p',
           smoothInfluences='si',
           softNormalization='sn',
           associativeGeometry='ag')
    def generateRebasedTargets(
            self,
            newBase:'nodes.DagNode',
            targetIndices:Optional[
                Union[int, list[int], tuple[int]]
            ]=None, /,
            parent:Optional['nodes.Transform']=None,
            smoothInfluences:Optional[int]=None,
            softNormalization:bool=False,
            associativeGeometry:Optional['nodes.DagNode']=None,
    ) -> dict:
        """
        Recreates target geometries for this blend shape node, but for a
        different base. A new blend shape node is not created; use
        :meth:`recreateOnNewBase` for that instead.

        Limitations
        -----------

        -   Only implemented for meshes
        -   Intended for topology transfers, so *newBase* must have a similar
            shape to the current base (uses proximityWrap)

        To-Dos
        ------

        -   Implement for non-mesh types too
        -   Implement a 'byUV' option

        :param newBase: the base shape for which to create the targets
        :param targetIndices: an optional list of target indices to include;
            defaults to all target indices
        :param parent/p: an optional destination parent for the generated
            geometries; defaults to None (world)
        :param smoothInfluences/si: forwarded to proximityWrap; defaults to None
        :param softNormalization/sn: forwarded to proximityWrap; defaults to
            None
        :param associativeGeometry/an: forwarded to proximityWrap; defaults to
            None

        :return: A dictionary with the following structure:
            ```
            {
                targetIndex (int): {
                    'main': <Transform>,
                    'alias': <str>,
                    'tweens': {tweenWeight (float): <Transform>, ...}
                },
                ...
            }
            ```
        """

        #----------------|    Early erroring

        if self.inPostMode():
            raise NotImplementedError(
                'currently only supported for pre-deformation (classic) blend '
                'shapes'
            )

        newBase = nodes['DagNode'](newBase).toTransform()
        thisBase = next(self.shapes, None).parent

        meshesToCheck = [newBase, thisBase]

        if associativeGeometry is not None:
            associativeGeometry = nodes['DagNode'](
                associativeGeometry
            ).toTransform()

            meshesToCheck.append(associativeGeometry)

        if not all((isinstance(x.shape, nodes.Mesh) for x in meshesToCheck)):
            raise NotImplementedError('currently only supported for meshes')

        #----------------|    Gather information

        if targetIndices is None:
            targetIndices = self.attr('weight').indices()
        else:
            targetIndices = list(
                without_duplicates(expand_tuples_lists(targetIndices))
            )

        targetSpecs = {}

        for targetIndex in targetIndices:
            target = self.targets[targetIndex]

            thisSpec = {}

            alias = target.alias

            if alias is None:
                alias = 'target_{}'.format(str(targetIndex).zfill(3))

            thisSpec['alias'] = alias

            tweenRatios = [tween.ratio for tween in list(target)]

            if 1.0 not in tweenRatios:
                raise RuntimeError(
                    "Malformed target at [{}]: no tween at 1.0".format(
                        targetIndex
                    )
                )

            tweenRatios.remove(1.0)
            tweenRatios.sort(reverse=True)

            if tweenRatios:
                thisSpec['tweenRatios'] = tweenRatios

            targetSpecs[targetIndex] = thisSpec

        _wrapMaster = self.attr(
            'originalGeometry')[0].inputs(plugs=True)[0].createShape().parent
        wrapMaster = _wrapMaster.duplicate(n='wrap_master')[0]
        m.delete(str(_wrapMaster))

        wrapSlave = newBase.duplicate(name='wrap_slave')[0]

        # For each target index:
        #     regenerate input geometry, set aside, store in a map

        regeneratedGeos = {} # index: {'main': geo, 'tweens': {float:geo}}

        for targetIndex, targetSpec in targetSpecs.items():
            srcTarget = self.targets[targetIndex]
            mainGeo = srcTarget[1.0].createShape(connect=False)
            tweenGeos = {
                tweenRatio: srcTarget[tweenRatio].createShape(connect=False)
                for tweenRatio in targetSpec.get('tweenRatios', [])
            }

            thisInfo = {'main': mainGeo, 'alias': targetSpec['alias']}

            if tweenGeos:
                thisInfo['tweens'] = tweenGeos

            regeneratedGeos[targetIndex] = thisInfo

        # Create a blend shape on 'wrapMaster', recreate all the blend shapes,
        # discard targets

        wrapMasterBsn = self.create(wrapMaster, n='wrap_master_bsn')

        for targetIndex, info in regeneratedGeos.items():
            newTarget = wrapMasterBsn.targets.add(info['main'],
                                                  alias=info['alias'])

            m.delete(str(info['main']))

            for tweenRatio, tweenGeo in info.get('tweens', {}).items():
                newTarget.add(tweenGeo, tweenRatio)
                m.delete(str(tweenGeo))

        # Wrap

        wrap = nodes.ProximityWrap.create(wrapSlave,
                                          smoothInfluences=smoothInfluences,
                                          softNormalization=softNormalization)

        if associativeGeometry is not None:
            associativeGeometry.worldOutput >> wrap.attr('associativeGeometry')

        wrap.addDriver(wrapMaster)

        # Recreate all targets and tweens

        out = {} # weight index: info

        for targetIndex, targetSpec in targetSpecs.items():
            for _target in wrapMasterBsn.targets:
                _target.weight.set(0.0)

            thisInfo = {'alias': targetSpec['alias']}

            # Main
            target = wrapMasterBsn.targets[targetIndex]
            target.weight.set(1.0)

            thisInfo['main'] = geo = wrapSlave.duplicate()[0]
            geo.show()

            geo.parent = parent
            geo.name = targetSpec['alias']

            tweens = {}

            for tweenRatio in targetSpec.get('tweenRatios', []):
                target.weight.set(tweenRatio)
                pc = str(int(tweenRatio * 100)).zfill(3)
                name = '{}_{}'.format(targetSpec['alias'], pc)
                tweens[tweenRatio] = tweenGeo = wrapSlave.duplicate()[0]
                tweenGeo.show()
                tweenGeo.parent = parent
                tweenGeo.name = name

            if tweens:
                thisInfo['tweens'] = tweens

            out[targetIndex] = thisInfo

        m.delete(str(wrapMaster), str(wrapSlave))

        return out

    @short(parent='p',
           smoothInfluences='si',
           softNormalization='sn',
           associativeGeometry='ag',
           name='n')
    def recreateOnNewBase(
            self,
            newBase:'nodes.DagNode',
            targetIndices:Optional[
                Union[int, list[int], tuple[int]]
            ]=None, /,
            name:Optional[str]=None,
            parent:Optional['nodes.Transform']=None,
            smoothInfluences:Optional[int]=None,
            softNormalization:bool=False,
            associativeGeometry:Optional['nodes.DagNode']=None,
            keepTargets:Optional[bool]=False
    ) -> tuple['BlendShape', Optional[dict]]:
        """
        Limitations
        -----------

        -   Only implemented for meshes
        -   Intended for topology transfers, so *newBase* must have a similar
            shape to the current base (uses proximityWrap)

        :param newBase: the new base shape on which to create the blend shape
        :param targetIndices: an optional list of target indices to include;
            defaults to all target indices
        :param keepTargets/kt: keep the regenerated target shapes in the scene;
            defaults to False
        :param parent/p: ignored if *keepTargets* is False; an optional
            destination parent for the generated geometries; defaults to None
            (world)
        :param smoothInfluences/si: forwarded to proximityWrap; defaults to None
        :param softNormalization/sn: forwarded to proximityWrap; defaults to
            None
        :param associativeGeometry/an: forwarded to proximityWrap; defaults to
            None

        :return: A tuple comprising the new node and, if *keepTargets* is True,
            the dictionary returned by :meth:`generateRebasedTargets`, otherwise
            None.
        """
        newBase = nodes['DagNode'](newBase).toTransform()
        newTargets = self.generateRebasedTargets(
            newBase,
            targetIndices,
            parent=parent,
            smoothInfluences=smoothInfluences,
            softNormalization=softNormalization,
            associativeGeometry=associativeGeometry
        )

        newBsn = self.create(newBase, name=name)

        for targetIndex, targetInfo in newTargets.items():
            newTarget = newBsn.targets.add(targetInfo['main'],
                                           alias=targetInfo['alias'])

            if not keepTargets:
                m.delete(str(targetInfo['main']))

            for tweenWeight, tweenGeo in targetInfo.get('tweens', {}).items():
                newTarget.add(tweenGeo, tweenWeight)

                if not keepTargets:
                    m.delete(str(tweenGeo))

            # Copy any weight input
            weightInputs = self.targets[targetIndex].weight.inputs(plugs=True)

            if weightInputs:
                weightInputs[0] >> newTarget.weight

        out = [newBsn, None]

        if keepTargets:
            out[1] = newTargets

        return tuple(out)

    #---------------------------|    Scene mapping

    """
    Scene map structure:
    
    {
        baseGeoName:[str]: {
            alias:[str]: {
                'main': {
                    'geo': str,
                    'inversionPose': dict
                },
                'tweens': {
                    ratio[float]: {
                        'geo': str,
                        'inversionPose': dict
                    }
                }
            }
        }
    }
    
    Inversions need a pose (as in :mod:`riggery.core.lib.poses`), in JSON
    format, embedded onto the target in an attribute called 'inversionPose'. The
    name of the pose doesn't matter. 
    """

    @classmethod
    def setInversionPoseOnTargetGeo(cls,
                                    pose:Optional[dict],
                                    targetGeo:Union[str, 'nodes.DagNode']):
        targetGeo = nodes['DagNode'](targetGeo).toTransform()

        if pose is None:
            if targetGeo.hasAttr('inversionPose'):
                targetGeo.deleteAttr('inversionPose')
        else:
            if not targetGeo.hasAttr('inversionPose'):
                targetGeo.addAttr('inversionPose', dt='string')
            plug = targetGeo.attr('inversionPose')
            plug.set(json.dumps(pose))

    @classmethod
    def getInversionPoseFromTargetGeo(cls,
                                      targetGeo:Union[str, 'nodes.DagNode']
                                      ) -> Optional[dict]:
        targetGeo = nodes['DagNode'](targetGeo).toTransform()
        try:
            plug = targetGeo.attr('inversionPose')
        except AttributeError:
            return

        return json.loads(plug())

    @classmethod
    def getSceneMapFromBase(cls, baseGeo:Union[str, 'nodes.DagNode']) -> dict:
        baseGeo = nodes['DagNode'](baseGeo).toTransform()
        baseGeoName = baseGeo.shortName()
        targetLookup = '{}_*_{}'.format(baseGeoName, _nm.BLENDSUFFIX)

        out = {}

        for _targetGeo in m.ls(targetLookup, type='transform'):
            if checkTransformUnambiguouslyExists(_targetGeo, quiet=True):
                pat = (r"^"
                       + baseGeoName
                       + r"_(.*?)(?:_([0-9]+))?_"
                       + _nm.BLENDSUFFIX
                       + r"$")

                mt = re.match(pat, _targetGeo)

                if mt:
                    alias, pc = mt.groups()

                    if pc is None:
                        isMain = True
                    else:
                        ratio = float(pc) / 100.0
                        isMain = ratio == 1.0

                    targetInfo = out.setdefault(baseGeoName,
                                                {}).setdefault(alias, {})

                    innerD = {'geo': _targetGeo}

                    inversionPose = cls.getInversionPoseFromTargetGeo(
                        _targetGeo
                    )

                    if inversionPose is not None:
                        innerD['inversionPose'] = inversionPose

                    if isMain:
                        targetInfo['main'] = innerD
                    else:
                        tweensD = targetInfo.setdefault('tweens', {})
                        tweensD[ratio] = innerD

        return out

    @classmethod
    def getSceneMapFromTarget(cls,
                              targetGeo:Union[str, 'nodes.DagNode']) -> dict:
        targetGeo = nodes['DagNode'](targetGeo).toTransform()
        targetGeoName = targetGeo.shortName()

        pat = (r"^(.*?)(?:_([0-9]+))?_" + _nm.BLENDSUFFIX + r"$")
        mt = re.match(pat, targetGeoName)

        out = {}

        if mt:
            head, pc = mt.groups()

            if pc is None:
                isMain = True
            else:
                ratio = float(pc) / 100.0
                isMain = ratio == 1.0

            elems = head.split('_')
            numElems = len(elems)

            for x in reversed(range(numElems)):
                baseGeoName = '_'.join(elems[:x])

                if checkTransformUnambiguouslyExists(baseGeoName, quiet=True):
                    alias = '_'.join(elems[x:])
                    targetInfo = {}
                    innerD = {'geo': targetGeoName}
                    inversionPose = cls.getInversionPoseFromTargetGeo(
                        targetGeoName
                    )
                    if inversionPose is not None:
                        innerD['inversionPose'] = inversionPose

                    if isMain:
                        targetInfo['main'] = innerD
                    else:
                        targetInfo['tweens'] = {ratio: innerD}

                    out[baseGeoName] = {alias: targetInfo}
                    break

        return out

    @classmethod
    def getSceneMapFromGeo(cls, geo) -> dict:
        out = cls.getSceneMapFromBase(geo)
        if not out:
            return cls.getSceneMapFromTarget(geo)

    @classmethod
    def getSceneMap(cls, *geos) -> dict:
        if geos:
            geos = expand_tuples_lists(*geos)
            geos = without_duplicates((nodes['DagNode'](geo).toTransform()
                                       for geo in geos))
            sceneMaps = [cls.getSceneMapFromGeo(x) for x in geos]
        else:
            sceneMaps = [cls.getSceneMapFromTarget(x)
                         for x in m.ls(f'*_{_nm.BLENDSUFFIX}')]

        if sceneMaps:
            return deep_merge_dicts(*sceneMaps)
        return {}

    @classmethod
    def createFromSceneMap(cls,
                           sceneMap:Optional[dict],
                           *geos,
                           update:bool=False) -> list['BlendShape']:
        if geos:
            geos = expand_tuples_lists(*geos)
            geos = without_duplicates((nodes['DagNode'](geo).toTransform()
                                       for geo in geos))
            geoSceneMaps = (cls.getSceneMapFromGeo(x) for x in geos)
            geoSceneMap = deep_merge_dicts(*geoSceneMaps)

        if sceneMap is None:
            if geos:
                sceneMap = geoSceneMap
            else:
                sceneMap = cls.getSceneMap()

        else:
            if geos:
                sceneMap = deep_intersect_dicts(sceneMap, geoSceneMap)

        # Gather a list of all controls involved in pose inversions
        controls = set()
        baseGeosWithInversions = []

        for baseGeo, baseInfo in sceneMap.items():
            theseControls = set()

            for alias, targetInfo in baseInfo.items():
                theseControls = theseControls.union(
                    set(
                        (pair[0] for pair in
                         targetInfo.get('main',
                                        {}).get('inversionPose',
                                                {}).get('controls', []))
                    )
                )
                for ratio, tweenInfo in targetInfo.get('tweens', {}).items():
                    theseControls = theseControls.union(
                        set(
                            (pair[0] for pair in
                             tweenInfo.get('inversionPose',
                                           {}).get('controls', []))
                        )
                    )

            if theseControls:
                baseGeosWithInversions.append(baseGeo)
                controls = controls.union(theseControls)

        defaultPose = None

        if controls:
            controls = [x for x in controls
                        if checkTransformUnambiguouslyExists(x)]

            if controls:
                defaultPose = _pos.capturePose('default', controls)

        out = []

        for baseGeo, baseInfo in sceneMap.items():
            if update:
                bsn = next(cls.fromGeo(baseGeo), None)

                if bsn is None:
                    bsn = cls.create(baseGeo)
            else:
                bsn = cls.create(baseGeo)

            out.append(bsn)

            hasInversions = baseGeo in baseGeosWithInversions

            if hasInversions:
                skinCluster = next(nodes['SkinCluster'].fromGeo(baseGeo))

            for alias, targetInfo in baseInfo.items():
                mainTarget = None

                if 'main' in targetInfo:
                    targetGeo = targetInfo['main']['geo']

                    if checkTransformUnambiguouslyExists(targetGeo):
                        inversionPose = targetInfo['main'].get('inversionPose')

                        if inversionPose is None:
                            mainTarget = bsn.targets.add(targetGeo,
                                                         alias=alias,
                                                         update=update)
                        else:
                            missingControls = [
                                x[0] for x in inversionPose['controls']
                                if not checkTransformUnambiguouslyExists(
                                    x[0],
                                    quiet=True
                                )
                            ]

                            if missingControls:
                                _missingControls = ', '.join(missingControls)
                                m.warning(f"Can't apply target '{alias}' to "
                                          f"base '{baseGeo}' because of these "
                                          "missing controls: "
                                          "{_missingControls}")

                            else:
                                if skinCluster is None:
                                    m.warning(
                                        f"Can't apply target '{alias}' to base"
                                        f" '{baseGeo}' because there is no "
                                        "skinCluster to perform the inversion"
                                    )
                                else:
                                    _pos.applyPose(inversionPose)
                                    # m.refresh()

                                    invertedTarget = skinCluster.invertShape(
                                        targetGeo,
                                        ee=True
                                    ).toTransform()

                                    if defaultPose is not None:
                                        _pos.applyPose(defaultPose)
                                        # m.refresh()

                                    mainTarget = bsn.targets.add(invertedTarget,
                                                                 alias=alias,
                                                                 update=update)

                                    m.delete(str(invertedTarget))

                for tweenRatio, tweenInfo in targetInfo.get('tweens',
                                                            {}).items():
                    tweenGeo = tweenInfo.get('geo')

                    if checkTransformUnambiguouslyExists(tweenGeo):
                        if mainTarget is None:
                            m.warning(
                                f"Can't apply tween for target '{alias}' on"
                                f" base {baseGeo} because the main target "
                                "could not be resolved"
                            )
                            continue

                        inversionPose = tweenInfo.get('inversionPose')

                        if inversionPose is None:
                            mainTarget.add(tweenGeo, tweenRatio, update=update)

                        else:
                            missingControls = [
                                x[0] for x in inversionPose['controls']
                                if not checkTransformUnambiguouslyExists(
                                    x[0],
                                    quiet=True
                                )
                            ]

                            if missingControls:
                                _missingControls = ', '.join(missingControls)
                                m.warning(f"Can't apply tween for target "
                                          f"'{alias}' on base '{baseGeo}' "
                                          "because of these missing controls: "
                                          f"{_missingControls}")
                            else:
                                if skinCluster is None:
                                    m.warning(
                                        f"Can't apply tween for target "
                                        f"'{alias}' on base {baseGeo} because"
                                        " there is no skinCluster to perform"
                                        " the inversion"
                                    )
                                else:
                                    _pos.applyPose(inversionPose)
                                    # m.refresh()
                                    invertedTween = skinCluster.invertShape(
                                        tweenGeo,
                                        ee=True
                                    ).toTransform()

                                    if defaultPose is not None:
                                        _pos.applyPose(defaultPose)
                                        # m.refresh()

                                    mainTarget.add(invertedTween,
                                                   tweenRatio,
                                                   update=update)

                                    m.delete(str(invertedTween))

        return out

    def _buildTargetName(self,
                         targetIndex:int, *,
                         ratio:Optional[float]=None) -> str:
        """
        :param targetIndex: the target index
        :param ratio: an optional tween ratio to include in the name, as a
            percentage
        """
        baseShape = next(self.shapes)
        baseXf = baseShape.parent

        elems = [baseXf.shortName()]
        alias = self.attr('weight')[targetIndex].alias

        if alias is None:
            alias = 'target{}'.format(targetIndex)

        elems.append(alias)

        if ratio:
            pc = str(int(ratio * 100))
            elems.append(pc)

        elems.append(_nm.BLENDSUFFIX)
        return '_'.join(elems)

    #---------------------------|    Granular weight control

    def iterAliases(self, includeNone:bool=False) -> Iterator[str]:
        """
        Do not rely on this to get a target count, since on some blendShape
        nodes the aliases may be malformed / missing.

        :param includeNone: in the (unusual) event that a weight plug doesn't
            have an alias, yield None; defaults to False (skip)
        :return: An iterator of target aliases.
        """
        for slot in self.attr('weight'):
            alias = slot.alias

            if (not includeNone) and alias is None:
                continue

            yield alias

    def getBaseWeights(self) -> list[float]:
        """
        :return: The full list of base weights for the blend shape node.
        """
        return self.attr('weightList'
                         )[0].attr('weights').readWeightsMulti(
            self.numPoints(0),
            1.0
        )

    def setBaseWeights(self, weights:list[float]):
        """
        Sets the base weights for the blend shape node.

        :param weights: the full (non-sparse) weights list
        """
        self.attr('weightList'
                  )[0].attr('weights').writeWeightsMulti(weights)
        return self

    def getWeightsForTargetByIndex(self, targetIndex:int) -> list[float]:
        """
        :param targetIndex: the target index
        :return: The full (non-sparse) weights list for the target.
        """
        weightAttr = self.attr('inputTarget')[0].attr(
            'inputTargetGroup')[targetIndex].attr('targetWeights')
        numPoints = self.numPoints(0)

        return weightAttr.readWeightsMulti(numPoints, 1.0)

    def setWeightsForTargetByIndex(self, targetIndex:int, weights:list[float]):
        """
        :param targetIndex: the target index
        :param weights: Tthe full (non-sparse) weights list for the target
        """
        weightAttr = self.attr('inputTarget')[0].attr(
            'inputTargetGroup')[targetIndex].attr('targetWeights')
        weightAttr.writeWeightsMulti(weights)
        return self

