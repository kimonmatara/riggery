import re
from typing import Optional, Union, Literal, Iterator, Any

import maya.internal.nodes.proximitywrap.cmd_create as cmd_create
import maya.internal.nodes.proximitywrap.node_interface as node_interface


from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..elem import Elem

WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m
import riggery.core as r
from riggery.core.lib.selection import keepsel
import riggery.core.lib.names as _nm

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.strings import join_camel, cap

#---------------------------------------------|
#---------------------------------------------|    HELPERS
#---------------------------------------------|

def _toShape(x) -> str:
    if m.objectType(x, isAType='transform'):
        return m.listRelatives(x, shapes=True, noIntermediate=True,
                               path=True)[0]
    return x

#---------------------------------------------|
#---------------------------------------------|    INTERFACES
#---------------------------------------------|

class _Interface:

    #---------------------------------|    Init

    def __init__(self, owner):
        self.o = owner


class MasterDetailsMeta(type):

    @classmethod
    def createGetter(cls, name):
        def getter(self):
            return self.o.slot.attr(
                'driver{}'.format(cap(name))).getInputOrValue()[0]

        return getter

    @classmethod
    def createSetter(cls, name):
        def setter(self, content):
            content >> self.o.slot.attr('driver{}'.format(cap(name)))

        return setter

    def __new__(meta, clsname, bases, dct):
        for name in dct['__detail_names__']:
            getter = meta.createGetter(name)
            setter = meta.createSetter(name)
            dct[name] = property(getter, setter)

        return super().__new__(meta, clsname, bases, dct)


class MasterDetails(_Interface, metaclass=MasterDetailsMeta):

    """Note: does not support 'driverFalloffRamp'."""

    __slots__ = ['o']

    __detail_names__ = ('bindGeometry',
                        'referenceGeometry',
                        'geometry',
                        'clusterRestMatrix',
                        'clusterMatrix',
                        'falloffStart',
                        'falloffEnd',
                        'dropoffRate',
                        'overrideFalloffRamp',
                        'strength',
                        'useTransformAsDeformation',
                        'scaleCompensation',
                        'smoothNormals',
                        'overrideSmoothNormals',
                        'spanSamples',
                        'smoothInfluences',
                        'overrideSmoothInfluences',
                        'overrideSpanSamples',
                        'wrapMode')

    #---------------------------------|    Basics

    def node(self) -> 'ProximityWrap':
        return self.o.o.o

    #---------------------------------|    Queries

    def items(self) -> Iterator[tuple[str, Any]]:
        for name in self.__detail_names__:
            yield name, getattr(self, name)

    #---------------------------------|    Repr

    def __repr__(self):
        return "{}.details".format(repr(self.o))


class Master(_Interface):

    """
    Use simple assignments on ``.details`` to configure the driver, e.g.

    .. code-block:: python

        master.details.bindGeometry = 'pCube1.outMesh'

    Note that the 'driver' prefix is omitted.
    """

    #---------------------------------|    Init

    def __init__(self, owner:'Masters', index:int):
        super().__init__(owner)
        self._index = index

    #---------------------------------|    Details interface

    @property
    def details(self) -> 'MasterDetails':
        return MasterDetails(self)

    #---------------------------------|    Basics

    @property
    def index(self) -> int:
        return self._index

    def node(self) -> 'ProximityWrap':
        return self.o.o

    @property
    def slot(self) -> 'plugs.Attribute':
        """
        :return: The corresponding ``.drivers`` element for this driver entry.
        """
        return self.node().attr('drivers')[self.index]

    #---------------------------------|    Main geo management

    def getInput(self) -> Optional['plugs.Geometry']:
        """Returns the main geometry source for the driver."""
        plug = self.slot.attr('driverGeometry')
        inputs = plug.inputs(plugs=True)

        if inputs:
            return inputs[0]

    def setInput(self,
                 shapeOrPlug:Union['nodes.DeformableShape', 'plugs.Geometry']):
        """
        This is a forgiving method, i.e. will allow you to assign a plug or a
        geometry DAG node, but you may not get the same thing back from
        :meth:`getShape`.

        If a dag node is assigned, its world geometry output will always be
        used.
        """
        shapeOrPlug = Elem(shapeOrPlug)

        if isinstance(shapeOrPlug, plugs.Attribute):
            input = shapeOrPlug
        else:
            input = shapeOrPlug.worldOutput

        self.details.geometry = input
        return self

    input = property(getInput, setInput)

    def getShape(self) -> Optional['nodes.DeformableShape']:
        """
        Note that this will return None if the driver input does not come from
        a shape, but rather from a generator, deformer etc.
        """
        input = self.getInput()
        node = input.node()

        if isinstance(node, nodes.DeformableShape):
            return node

    shape = property(getShape, setInput)

    #---------------------------------|    Base management

    def getBaseInput(self) -> Optional['plugs.Geometry']:
        """
        Variant of :meth:`getBaseShape` that, more, specifically, returns the
        input, if any.
        """
        plug = self.slot.attr('driverBindGeometry')
        inputs = plug.inputs(plugs=True)

        if inputs:
            return inputs[0]

    def setBaseInput(self,
                     shapeOrPlug:Union['nodes.DeformableShape',
                     'plugs.Geometry']):
        """
        This is a forgiving method, i.e. will allow you to assign a plug or a
        geometry DAG node, but you may not get the same thing back from
        :meth:`getBaseShape`.

        If a dag node is assigned, its local geometry output will always be
        used.

        :param shapeOrPlug: a shape output plug or geometry object
        """
        shapeOrPlug = Elem(shapeOrPlug)

        if isinstance(shapeOrPlug, plugs.Attribute):
            input = shapeOrPlug
        else:
            input = shapeOrPlug.localOutput

        self.details.bindGeometry = input
        return self

    baseInput = property(getBaseInput, setBaseInput)

    def getBaseShape(self) -> Optional['nodes.DeformableShape']:
        """
        Note: this will return ``None`` if the input for the base geometry does
        not come from a shape, but rather from something else, e.g. a deformer,
        generator etc.
        """
        plug = self.slot.attr('driverBindGeometry')
        inputs = plug.inputs(plugs=True)

        if inputs:
            inputNode = inputs[0].node()

            if isinstance(inputNode, nodes.DeformableShape):
                return inputNode

    baseShape = property(getBaseShape, setBaseInput)

    #---------------------------------|    Repr

    def __repr__(self):
        return "{}[{}]".format(repr(self.o), self.index)


class Masters(_Interface):

    #---------------------------------|    Basics

    def node(self) -> 'ProximityWrap':
        return self.o

    #---------------------------------|    Get masters

    def find(self, geo:'nodes.DagNode') -> Optional['Master']:
        """
        Retrieves a :class:`Master` instance for the given geometry, or None if
        there's no match.
        """
        index = self.node().getDriverIndex(geo)
        if index is not None:
            return Master(self, index)

    def indices(self) -> Iterator[int]:
        """Yields driver indices."""

        yield from self.node().attr('drivers').indices()

    def __getitem__(self, index:int) -> 'Master':
        if index in self.indices():
            return Master(self, index)

        raise IndexError(f'no driver at index {index}')

    def __iter__(self) -> Iterator['Master']:
        for index in self.indices():
            yield Master(self, index)

    #---------------------------------|    Add masters

    def add(self,
            master:'nodes.DagNode',
            masterBase:Optional[
                Union['nodes.DagNode', 'plugs.Geometry']
            ]=None, /,
            **details):
        """
        Adds a driver to the proximity wrap.

        :param master: the driver object
        :param masterBase: an optional custom base for the driver object; can
            be a geometry object or output; defaults to None
        :param \*\*details: inputs or values for the various attributes under
            the driver slot. See :class:`Master`.
        """
        node = self.node()

        _masterShape = _toShape(str(master))
        m.proximityWrap(str(node), e=True, addDrivers=[_masterShape])

        masterIndex = node.getDriverIndex(master)
        inst = Master(self, masterIndex)

        if masterBase is not None:
            inst.baseShape = masterBase

        for k, v in details.items():
            setattr(inst.details, k, v)

        return inst

    #---------------------------------|    Repr

    def __repr__(self):
        return f"{repr(self.o)}.masters"


class Slave(_Interface):

    #---------------------------------|    Inst

    def __init__(self, owner:'Slaves', index:int):
        super().__init__(owner)
        self._index = index

    #---------------------------------|    Basics

    def node(self) -> 'ProximityWrap':
        return self.o.o

    @property
    def index(self) -> int:
        return self._index

    #---------------------------------|    Geo management

    def getBaseInput(self) -> Optional['plugs.Geometry']:
        """
        :return: the source plug for the ``originalGeometry`` input
        """
        slot = self.node().attr('originalGeometry')[self.index]
        inputs = slot.inputs(plugs=True)
        if inputs:
            return inputs[0]

    def setBaseInput(self,
                     geoOrGeoInput:Union['plugs.Geometry', 'nodes.DagNode']):
        """
        This is a 'forgiving' method, in that it will allow you to assign a
        DAG node or a geometry input, but you may not get the same thing back
        from :meth:`getBaseShape`.

        If a DAG geometry node is assigned, its local geometry output will
        always be used.
        """
        geoOrGeoInput = Elem(geoOrGeoInput)
        slot = self.node().attr('originalGeometry')[self.index]

        if isinstance(geoOrGeoInput, plugs.Geometry):
            input = geoOrGeoInput
        else:
            input = geoOrGeoInput.localOutput

        input >> slot
        return self

    baseInput = property(getBaseInput, setBaseInput)

    def getBaseShape(self) -> Optional['nodes.DeformableShape']:
        """
        Note: this will return ``None`` if the input for the base geometry does
        note come from a shape, but rather from a deformer, generator etc.
        """
        input = self.getBaseInput()
        if input is not None:
            node = input.node()
            if isinstance(node, nodes.DeformableShape):
                return node

    baseShape = property(getBaseShape, setBaseInput)

    def getShape(self) -> 'nodes.DeformableShape':
        """:return: The slave shape. """

        for i, shape in enumerate(self.node().shapes):
            if i == self.index:
                return shape

    shape = property(getShape)

    #---------------------------------|    Repr

    def __repr__(self):
        return "{}[{}]".format(repr(self.o), self.index)


class Slaves(_Interface):

    #---------------------------------|    Basics

    def node(self) -> 'ProximityWrap':
        return self.o

    #---------------------------------|    Get slaves

    def indices(self) -> Iterator[int]:
        """Yields indices on the ``outputGeometry`` attribute."""
        yield from self.node().attr('outputGeometry').indices()

    def find(self, drivenGeo:'nodes.DagNode') -> Optional['Slave']:
        """
        :return: A :class:`Slave` instance for the driven geometry, or None if
            no match.
        """
        index = self.node().getDrivenIndex(drivenGeo)
        if index is not None:
            return Slave(self, index)

    def __getitem__(self, index:int) -> 'Slave':
        if index in self.indices():
            yield Slave(self, index)

    def __iter__(self) -> Iterator['Slave']:
        for index in self.indices():
            yield Slave(self, index)

    def __len__(self) -> int:
        return len(self.node().attr('outputGeometry'))

    #---------------------------------|    Repr

    def __repr__(self):
        return "{}.slaves".format(repr(self.o))

#---------------------------------------------|
#---------------------------------------------|    MAIN CLASS
#---------------------------------------------|

class ProximityWrap(WeightGeometryFilter):
    """
    Interfaces:

    ```
    .masters
        .masters[0]
            .details

    .slaves

    etc.
    """

    #---------------------------------|    Constructor

    @classmethod
    @keepsel
    def create(cls,
               driven,
               wrapMode='Surface',
               falloffScale=1.0,
               dropoffRateScale=0.0,
               smoothInfluences=0,
               smoothNormals=0,
               spanSamples:int=2,
               softNormalization=False,
               name:Optional[str]=None,
               useBindTags:bool=False,
               scaleCompensation=None, # use this for global scale
               maxDrivers:int=10):
        """
        Similar to :class:`~riggery.core.nodetypes.BlendShape`, this merely
        initializes the deformer on a single deformed object; use the
        ``masters`` and ``slaves`` interfaces`` for further editing.

        :param driven: the initial driven geometry
        """
        m.select(driven)

        node = r.Elem(cmd_create.Command().command()[0])

        if name is None:
            if _nm.Name.__elems__:
                node.rename(_nm.Name.evaluate(typeSuffix=cls.__typesuffix__))
        else:
            node.rename(name)

        for k, v in zip(
                ('wrapMode', 'falloffScale', 'dropoffRateScale',
                 'smoothInfluences', 'smoothNormals', 'softNormalization',
                 'maxDrivers', 'spanSamples', 'useBindTags',
                 'scaleCompensation'),
                (wrapMode, falloffScale, dropoffRateScale, smoothInfluences,
                 smoothNormals, softNormalization, maxDrivers, spanSamples,
                 useBindTags, scaleCompensation)
        ):
            if v is not None:
                v >> node.attr(k)

        return node

    #---------------------------------|    Interfaces

    @property
    def masters(self) -> Masters:
        return Masters(self)

    @property
    def slaves(self) -> Slaves:
        return Slaves(self)

    #---------------------------------|    Driver (master) queries

    def getDriverSlot(self,
                      driver:'nodes.DagNode') -> Optional['plugs.Attribute']:
        """
        :return: The corresponding input compound for the given driver geometry.
        """
        shape = r.Elem(driver).toShape()

        if isinstance(shape, nodes.DeformableShape):
            for attr in ('worldOutput', 'localOutput'):
                for output in getattr(shape, attr).outputs(plugs=True):
                    if output.node() == self:
                        if output.attrName(longName=True) == 'driverGeometry':
                            return output.parent

    def getDriverIndex(self, driver) -> Optional[int]:
        """
        :return: The corresponding input index for the given driver geometry, or
            None if no match.
        """
        out = self.getDriverSlot(driver)

        if out is not None:
            return out.index()

    #---------------------------------|    Driven (slave) queries

    def getDrivenIndex(self, driven) -> Optional[int]:
        """
        :return: The corresponding input index for the given driven geometry, or
            None if no match.
        """
        shape = r.Elem(driven).toShape()

        if isinstance(shape, nodes.DeformableShape):
            inputs = shape.input.inputs(plugs=True)

            for input in inputs:
                if (input.node() == self
                        and input.attrName(longName=True) == 'outputGeometry'):
                    return input.index()