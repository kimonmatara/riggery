import re
from typing import Union, Optional, Literal, Iterator

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..lib import names as _nm

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates

WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m
import maya.api.OpenMaya as om

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
        geoXform.setName(self.node()._buildTargetName(self.target.index,
                                                      self.ratio),
                         conformShapeNames=True)
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

    @short(skinCluster='sc')
    def updateShape(self,
                    src:'nodes.DagNode', *,
                    skinCluster:Optional['nodes.SkinCluster']=None,
                    connect:bool=False):
        """
        Temporarily connects a new shape and afterwards disconnects it.

        :param skinCluster/sc: if this is provided, it will be used to invert
            the shape before updating; defaults to None
        :param connect/con: keep the connection; defaults to False
        """
        incomingConnection = next(self.geoInput.iterInputs(plugs=True), None)

        src = nodes['DagNode'](src).toShape()

        if skinCluster:
            skinCluster = nodes['SkinCluster'](skinCluster)
            src = skinCluster.invertShape(src)

        self._connectInputShape(src)

        if not connect:
            if incomingConnection:
                incomingConnection >> self.geoInput
            else:
                self.geoInput.disconnect(inputs=True)

        if skinCluster:
            r.delete(src.parent)

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
            a geometry in the scene that obeys the 'model asset' naming
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
                lookup = self.node()._buildTargetName(self.target.index,
                                                      self.ratio)
                matches = r.ls(lookup, type='transform')

                if len(matches) == 1:
                    outShape = matches[0].shape

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
           topologyCheck='tc',
           skinCluster='sc')
    def add(self,
            geo,
            ratio:float, *,
            connect:Optional[bool]=None,
            topologyCheck:bool=True,
            skinCluster:Optional['nodes.SkinCluster']=None):
        """
       Adds an inbetween shape.

       :param geo: the target geometry
       :param ratio: the weight at which to create the inbetween target
       :param skinCluster/sc: a skinCluster to perform inversion before
        applying; defaults to None
       :param connect/c: keep the target connected; defaults to False if the
           main target is a 'tangentSpace' or 'transform' target, otherwise
           True
       """
        bsn = self.node()
        _bsn = str(bsn)

        args = (_bsn,)

        if skinCluster:
            skinCluster = nodes['SkinCluster'](skinCluster)
            geoShape = skinCluster.invertShape(geo)
        else:
            geoShape = nodes['DagNode'](geo).toShape()

        geoXf = geoShape.parent

        kwargs = {'e': True,
                  'ib': True,
                  't':(str(next(node.shapes)), self._index, str(geoXf), ratio),
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

            if skinCluster:
                m.delete(str(geoXf))

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
           skinCluster='sc')
    def add(self,
            geo:'nodes.DagNode',
            alias:Optional[str]=None, *,
            tangentSpace:bool=False,
            transform:Optional['nodes.Transform']=None,
            connect:Optional[bool]=None,
            index:Optional[int]=None,
            skinCluster:Optional['nodes.SkinCluster']=None,
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
       :param skinCluster/sc: if this is provided, it will be used to invert
           the shape before application (note that this is not a 'live'
           operation, and that the skinCluster must be at-pose at the time of
           application); defaults to None
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

        bsn = self.node()
        post = bsn.inPostMode()

        if skinCluster:
            skinCluster = nodes['SkinCluster'](skinCluster)
            geoShape = skinCluster.invertShape(geo)
        else:
            geoShape = nodes['DagNode'](geo).toShape()

        geoXf = geoShape.parent

        if index is None:
            index = node.attr('weight').nextIndex()

        elif index in node.attr('weight').indices():
            raise ValueError(f"index {index} in use")

        if alias is None:
            alias = geoXf.shortName(sns=True)

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
                     t=[str(base), index, str(geoXf), 1.0],
                     w=[index, 0.0],
                     **kwargs)

        #------------------|    Post-config

        target = Target(self, index)
        target.alias = alias
        geoInput = target.geoInput

        if connect:
            worldSpace = node.attr('origin')() == 0
            geoPlug = (geoShape.worldOutput
                       if worldSpace else geoShape.localOutput)
            geoPlug >> geoInput
        else:
            geoInput.disconnect(inputs=True)

            if skinCluster:
                m.delete(str(geoXf))

        return target

    #---------------------------|    Repr

    def __repr__(self):
        return '{}.targets'.format(repr(self._node))

#-----------------------------------------|
#-----------------------------------------|    MAIN CLASS
#-----------------------------------------|

class BlendShape(WeightGeometryFilter):

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

        """
        Create a clean copy of our base. Call it 'wrapMaster'
        Create a clean copy of the new base. Call it 'wrapSlave'
        """

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

    #---------------------------|    Scene batch operations

    @classmethod
    def getSceneMap(cls, suffix:str=_nm.BLENDSUFFIX) -> dict:
        """
        Detects this type of model asset configuration for blend shapes:

        ``<base_geo_name>_<blend_descriptor>_<percent>_<suffix>``

        For example:

        ``face_DMSH_big_smile_100_BLEND``

        :param suffix: the suffix to look for; defaults to ``BLENDSUFFIX`` in
            :mod:`riggery.core.lib.names` (currently 'BLEND')
        :return: A dictionary with this structure:
            ```
            {
                <base geo> (str):
                    <target alias> (str) : {
                        <tween weight> (float) : <target geo> (str)
                        ...
                    },
                    ...
            }
            ```
        """
        out = {}
        pat = r"^(.*?)_([0-9]+)_" + suffix + r"$"

        for item in m.ls('*_{}'.format(suffix), type='transform'):
            name = item.split('|')[-1]
            mt = re.match(pat, name)
            if mt:
                head, pc = mt.groups()
                elems = head.split('_')
                numElems = len(elems)

                for i in range(1, numElems):
                    baseName = '_'.join(elems[:numElems-i])
                    descriptor = '_'.join(elems[numElems-i:])

                    matches = m.ls(baseName, type='transform')

                    if matches:
                        ratio = float(pc) / 100.0
                        out.setdefault(matches[0],
                                       {}).setdefault(descriptor,
                                                      {})[ratio] = item

        return out

    @classmethod
    def createFromSceneMap(cls,
                           sceneMap:dict,
                           *baseMeshes,
                           removeTargets:bool=False) -> list['BlendShape']:
        """
        :param sceneMap: the type of dictionary returned by :meth:`getSceneMap`
        :param \*baseMeshes: the base meshes to create blend shapes on; if
            omitted, all base meshes defined in the map will be used
        :param removeTargets: remove any targets that were used; defaults to
            False
        """
        if baseMeshes:
            baseMeshes = list(without_duplicates(
                (str(x).split('|')[-1] for x in expand_tuples_lists(baseMeshes))
            ))
        else:
            baseMeshes = list(sceneMap.keys())

        out = []

        for baseMesh in baseMeshes:
            if baseMesh in sceneMap:
                bsn = nodes['BlendShape'].create(baseMesh)

                for targetAlias, tweensMap in sceneMap[baseMesh].items():
                    ratios = list(sorted(tweensMap, reverse=True))

                    if 1.0 not in ratios:
                        raise RuntimeError(
                            "No 100 target for blend shape '{}'".format(
                                targetAlias
                            )
                        )

                    tweenRatios = ratios[1:]
                    target = bsn.targets.add(tweensMap[1.0], alias=targetAlias)

                    if removeTargets:
                        m.delete(tweensMap[1.0])

                    for tweenRatio in ratios[1:]:
                        target.add(tweensMap[tweenRatio], tweenRatio)

                        if removeTargets:
                            m.delete(tweensMap[tweenRatio])

                out.append(bsn)

            else:
                m.warning(
                    "Base mesh '{}' not in scene map, skipping.".format(
                        baseMesh
                    )
                )
                continue

        return out

    def _buildTargetName(self, targetIndex:int, tweenRatio:float=1.0, /):
        alias = self.attr('weight')[targetIndex].alias

        if alias is None:
            alias = 'target_{}'.format(str(targetIndex).zfill(3))

        elems = [next(self.shapes).parent.shortName(),
                 alias,
                 str(int(tweenRatio * 100)).zfill(3),
                 _nm.BLENDSUFFIX]

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

    def _getChannelIndex(self, shapeOrAlias:Union['nodes.DagNode', str]) -> int:
        """
        :raises NoTargetIndexError:
        """
        if isinstance(shapeOrAlias, str):
            for slot in self.attr('weight'):
                if slot.alias == shapeOrAlias:
                    return slot.index()

        try:
            shape = nodes['DagNode'](shapeOrAlias).toShape()
        except:
            raise self.NoTargetIndexError(
                "Couldn't derive a target index from {}".format(
                    repr(shapeOrAlias)
                )
            )

        for targetGroup in self.attr('inputTarget')[0].attr('inputTargetGroup'):
            for targetItem in targetGroup.attr('inputTargetItem'):
                if shape in targetItem.attr('inputGeomTarget').history(
                        type='deformableShape'
                ):
                    return slot.index()

        raise self.NoTargetIndexError(
            "Couldn't derive a target index from {}".format(
                repr(shapeOrAlias)
            )
        )

    def _getWeightsForShapeAndChannel(self,
                                      shapeIndex:int,
                                      channelIndex:int) -> list[float]:
        """
        Note that *shapeIndex* refers to the *base* index, which, until Autodesk
        decides to do something 'special' with blend shapes, will always be 0.
        """
        weightAttr = self.attr(
            'inputTarget'
        )[shapeIndex].attr('inputTargetGroup'
                           )[channelIndex].attr('targetWeights')

        return weightAttr.readWeightsMulti(
            list(self.shapes)[shapeIndex].numPoints(),
            1.0
        )

    def _setWeightsForShapeAndChannel(self,
                                      shapeIndex:int,
                                      channelIndex:int,
                                      weights:list[float]):
        """
        Note that *shapeIndex* refers to the *base* index, which, until Autodesk
        decides to do something 'special' with blend shapes, will always be 0.
        """
        weightAttr = self.attr(
            'inputTarget'
        )[shapeIndex].attr('inputTargetGroup'
                           )[channelIndex].attr('targetWeights')
        weightAttr.writeWeightsMulti(weights)

    def getBaseWeights(self) -> list[float]:
        """
        :return: The full list of base weights for the blend shape node.
        """
        return self.attr('weightList'
                         )[0].attr('weights').readWeightsMulti(
            next(self.shapes).numPoints(),
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

    def getWeightsForShapeAndChannel(self,
                                     shape:Union[str, 'nodes.DagNode'],
                                     channel:Union[str, int]) -> list[float]:
        """
        Returns the weights for the given channel (target).

        :param shape: this refers to the *base* shape which, until Autodesk
            decides to do something 'special' with blend shapes, should always
            be passed-in as 0
        :param channel: an index, alias or geometry name representing the target
            for which to get weights
        """
        shapeIndex = self._resolveShapeIndex(shape)
        channelIndex = self._resolveChannelIndex(channel)
        return self._getWeightsForShapeAndChannel(shapeIndex, channelIndex)

    def setWeightsForShapeAndChannel(self,
                                     shape:Union[str, 'nodes.DagNode'],
                                     channel:Union[str, int],
                                     weights:list[float]):
        """
        Sets the weights for the given channel (target).

        :param shape: this refers to the *base* shape which, until Autodesk
            decides to do something 'special' with blend shapes, should always
            be passed-in as 0
        :param channel: an index, alias or geometry name representing the target
            for which to get weights
        :param weights: the weight list; this must not be sparse
        """
        shapeIndex = self._resolveShapeIndex(shape)

        channelIndex = self._resolveChannelIndex(channel)
        self._setWeightsForShapeAndChannel(shapeIndex,
                                           channelIndex,
                                           weights)

        return self

    def getWeightsForTargetByIndex(self, targetIndex:int) -> list[float]:
        """
        :param targetIndex: the target index
        :return: The full (non-sparse) weights list for the target.
        """
        weightAttr = self.attr('inputTarget')[0].attr(
            'inputTargetGroup')[targetIndex].attr('targetWeights')
        numPoints = next(self.shapes).numPoints()

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