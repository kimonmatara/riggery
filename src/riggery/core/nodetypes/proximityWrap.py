import re
from typing import Optional, Union, Iterator, Any

import maya.internal.nodes.proximitywrap.cmd_create as cmd_create

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..elem import Elem

WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m

from ..lib.selection import keepsel
from ..lib import names as _nm

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.strings import join_camel, cap

#---------------------------------------------|
#---------------------------------------------|    INTERFACES
#---------------------------------------------|

class _Interface:

    #------------------|    Init

    def __init__(self, owner):
        self.o = owner


class Slave(_Interface):

    #------------------|    Init

    def __init__(self, owner:'Slaves', index:int):
        super().__init__(owner)
        self._index = index

    #------------------|    Basics

    @property
    def index(self):
        return self._index

    def node(self) -> 'ProximityWrap':
        return self.o.o

    @property
    def output(self):
        return self.node().attr('outputGeometry')[self.index]

    #------------------|    Shape management

    def getShape(self) -> Optional['nodes.DeformableShape']:
        return self.node().findDrivenShapeAtIndex(self.index)

    shape = property(getShape)

    #------------------|    Base shape management

    @short(indirect='i')
    def getBaseShape(self,
                     indirect:bool=False) -> Optional['nodes.DeformableShape']:
        """
        :param indirect/i: if no shape is directly connected into
            ``originalGeometry``, return the first one further upstream;
            defaults to False
        """
        return self.node().findDrivenBaseShapeAtIndex(self.index,
                                                      indirect=indirect)

    def setBaseShape(self,
                     geoSource:Union['nodes.DagNode', 'plugs.Geometry']
                     ) -> 'Slave':
        """
        :param geoSource: a DAG geometry node or geometry output
        """
        self.node().setDrivenBaseShapeAtIndex(self.index, geoSource)
        return self

    baseShape = property(getBaseShape, setBaseShape)

    #------------------|    Repr

    def __int__(self):
        return self.index

    def __repr__(self):
        return "{}[{}]".format(repr(self.o), self._index)


class Slaves(_Interface):

    #------------------|    Basics

    def node(self) -> 'ProximityWrap':
        return self.o

    #------------------|    Get

    @property
    def __len__(self):
        return self.node().numDrivens

    @property
    def indices(self):
        return self.node().attr('outputGeometry').indices

    def __getitem__(self, index):
        node = self.node()
        node.checkDrivenIndex(index)
        return Slave(self, index)

    def __iter__(self):
        for index in self.indices():
            yield Slave(self, index)

    #------------------|    Add

    def add(self, drivenGeo) -> 'Slave':
        """
        :param drivenGeo: the driven geometry
        :return: A :class:`Slave` instance.
        """
        node = self.node()
        node.addDriven(drivenGeo)
        return Slave(self, node.findDrivenIndex(drivenGeo))

    #------------------|    Remove

    @short(force='f')
    def removeByGeo(self, drivenGeo, force=False) -> 'Slaves':
        """
        :param force/f: if the operation fails, attempt to force-remove the
            array slots; defaults to False
        """
        self.node().removeDriven(drivenGeo, force=force)
        return self

    @short(force='f')
    def removeByIndex(self, index, force=False) -> 'Slaves':
        """
        :param force/f: if the operation fails, attempt to force-remove the
            array slots; defaults to False
        """
        self.node().removeDrivenAtIndex(index, force=force)
        return self

    def remove(self, slave:'Slaves', force:bool=False) -> 'Slaves':
        """
        :param force/f: if the operation fails, attempt to force-remove the
            array slots; defaults to False
        """
        if not isinstance(slave, Slave):
            raise TypeError("expected a Slave instance")
        return self.removeByIndex(int(slave), force=force)

    def __delitem__(self, index:int):
        self.removeByIndex(index, force=True)

    #------------------|    Repr

    def __repr__(self):
        return "{}.slaves".format(repr(self.o))


class Master(_Interface):

    #------------------|    Init

    def __init__(self, owner:'Masters', index:int):
        super().__init__(owner)
        self._index = index

    #------------------|    Basics

    @property
    def index(self) -> int:
        return self._index

    def node(self) -> 'ProximityWrap':
        return self.o.o

    @property
    def slot(self) -> 'plugs.Attribute':
        return self.node().attr('drivers')[self.index]

    @property
    def input(self) -> 'plugs.Geometry':
        return self.slot.attr('driverGeometry')

    #------------------|    Shape management

    @short(indirect='i')
    def getShape(self,
                 indirect:bool=False) -> Optional['nodes.DeformableShape']:
        """
        :param indirect/i: if there's no direct shape connection into
            ``driverGeometry``, look for a shape further upstream; defaults to
            False
        """
        return self.node().findDriverShapeAtIndex(self._index)

    def setShape(self, source:Union['nodes.DagNode', 'plugs.Geometry']):
        """
        :param source: a geometry DAG node or geometry input
        """
        self.node().setDriverShapeAtIndex(self.index, source)
        return self

    shape = property(getShape, setShape)

    #------------------|    Base management

    @short(indirect='i')
    def getBaseShape(self,
                     indirect:bool=False) -> Optional['nodes.DeformableShape']:
        """
        :param indirect/i: if no direct shape connection into ``bindGeometry``
            is found, look for a shape further upstream; defaults to False
        """
        return self.node().findDriverBaseShapeAtIndex(self.index,
                                                      indirect=indirect)

    def setBaseShape(
            self,
            source:Union['nodes.DagNode', 'plugs.Geometry']
    ) -> 'Master':
        """
        :param baseShape: a geometry plug or a shape
        """
        self.node().setDriverBaseShapeAtIndex(self.index, source)
        return self

    baseShape = property(getBaseShape, setBaseShape)

    #------------------|    Details

    def getDetail(self, detailName:str, asString:bool=False) -> Any:
        """
        :param detailName: the name of a child attribute under ``drivers``,
            minus the 'driver' prefix, e.g. 'bindGeometry'
        :param asString: if an attribute is an enum, return its value as a
            string; defaults to False
        :return: The input on the attribute or, if there's not input and the
            attribute type is of a numerical type, the attribute value
        """
        return self.node().getDriverDetail(self.index)

    def setDetail(self, detailName:str, detailContent:Any) -> 'Master':
        """
        :param detailName: the name of a child attribute under ``drivers``
            minus the 'driver' prefix, e.g. 'bindGeometry'
        :param detailContent: an input or value for the attribute
        """
        self.node().setDriverDetail(self.index, detailName, detailContent)
        return self

    def setDriverDetails(self, **details) -> 'Master':
        """
        :param \*\*details: k, v pairs where each key is the the name of a child
            attribute under ``drivers`` minus the 'driver' prefix, e.g.
            'bindGeometry', and each value is a value or input for the attribute
        """
        self.node().setDriverDetails(self.index, **details)
        return self

    #------------------|    Repr

    def __int__(self):
        return self._index

    def __repr__(self):
        return "{}[{}]".format(repr(self.o), self._index)


class Masters(_Interface):

    #------------------|    Basics

    def node(self) -> 'ProximityWrap':
        return self.o

    #------------------|    Add

    def add(self, masterGeo:'nodes.DagNode') -> 'Master':
        """
        :param masterGeo: the driver geometry
        :return: A :class:`Master` instance for the driver.
        """
        node = self.node()
        node.addDriver(masterGeo)
        return Master(self, node.findDriverIndex(masterGeo))

    #------------------|    Remove

    @short(force='f')
    def remove(self, master:'Master', force:bool=False) -> 'Masters':
        """
        :param force/f: if the driver can't be removed using the
            ``proximityWrap`` command (e.g. due to a complex connection), fall
            back to ``removeMultiInstance``; defaults to False
        """
        if not isinstance(master, Master):
            raise TypeError("expected a Master instance")
        return self.removeByIndex(int(master))

    @short(indirect='i',
           force='f')
    def removeByGeo(self,
                    masterGeo:'nodes.DagNode',
                    indirect:bool=False,
                    force:bool=False) -> 'Masters':
        """
        This is a quiet operation. Nothing will happen if the geometry is not
        a driver.

        :param indirect/i: look for a slot match even if the driver does not
            directly connect into a ``driverGeometry`` slot; defaults to False
        :param force/f: if a match is found, but the operation fails, force-
            remove the slot instance; defaults to False
        """
        self.node().removeDriver(masterGeo, indirect=indirect, force=force)
        return self

    @short(force='f')
    def removeByIndex(self, masterIndex:int, force:bool=False) -> 'Masters':
        """
        :param force/f: if the driver can't be removed using the
            ``proximityWrap`` command (e.g. due to a complex connection), fall
            back to ``removeMultiInstance``; defaults to False
        """
        self.node().removeDriverAtIndex(masterIndex, force=force)
        return self

    def __delitem__(self, masterIndex:int):
        self.removeByIndex(masterIndex, force=True)

    #------------------|    Get

    @property
    def indices(self):
        return self.node().attr('drivers').indices

    @property
    def __len__(self):
        return self.node().numDrivers

    def __iter__(self):
        for index in self.node().attr('drivers').indices():
            yield Master(self, index)

    def __getitem__(self, index):
        self.node().checkDriverIndex(index)
        return Master(self, index)

    #------------------|    Repr

    def __repr__(self):
        return "{}.masters".format(repr(self.o))

#---------------------------------------------|
#---------------------------------------------|    MAIN CLASS
#---------------------------------------------|

class ProximityWrap(WeightGeometryFilter):

    #-------------------------------------|
    #-------------------------------------|    Constructor
    #-------------------------------------|

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

        node = Elem(cmd_create.Command().command()[0])

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

    #-------------------------------------|
    #-------------------------------------|    Interfaces
    #-------------------------------------|

    @property
    def masters(self) -> Masters:
        return Masters(self)

    @property
    def slaves(self) -> Slaves:
        return Slaves(self)

    #-------------------------------------|
    #-------------------------------------|    Errors
    #-------------------------------------|

    class PwError(RuntimeError):
        ...

    class PwNoDeformableShapeError(PwError):
        ...

    class PwNotADrivenShapeError(PwError):
        ...

    #-------------------------------------|
    #-------------------------------------|    Util
    #-------------------------------------|

    @classmethod
    def _toDeformableShape(cls, x, quiet:bool=False):
        x = nodes['DependNode'](x)

        if isinstance(x, nodes['DagNode']):
            shape = x.toShape()

            if isinstance(shape, nodes['DeformableShape']):
                return shape

        if not quiet:
            raise cls.PwNoDeformableShapeError('no deformable shape detected')

    @classmethod
    @short(worldSpace='ws')
    def _toGeoOutput(cls, x, worldSpace:bool=False) -> 'plugs.Geometry':
        x = Elem(x)

        if isinstance(x, plugs['Attribute']):
            if isinstance(x, plugs['Geometry']):
                return x
            raise TypeError(f"not a geometry plug: {x}")

        if isinstance(x, nodes['DagNode']):
            shape = x.toShape()
            if isinstance(shape, nodes['DeformableShape']):
                if worldSpace:
                    return shape.worldOutput
                return shape.localOutput

        raise self.PwNoDeformableShapeError('no deformable shape detected')

    #-------------------------------------|
    #-------------------------------------|    Driven
    #-------------------------------------|

    #------------------|    Query driven

    def checkDrivenIndex(self, drivenIndex:int):
        """
        :raises IndexError
        """
        if drivenIndex not in self.attr('outputGeometry').indices():
            raise IndexError(
                "driven index doesn't exist: {}".format(drivenIndex)
            )

    def hasDriven(self, drivenGeo:'nodes.DagNode') -> bool:
        """
        :raises PwNoDeformableShapeError:
        :return: True if the specified geometry is in this wrap's shape list.
        """
        return self._toDeformableShape(drivenGeo) in self.iterDrivenShapes()

    def iterDrivenShapes(self) -> Iterator['nodes.DeformableShape']:
        """
        :return: An iterator of shapes deformed by the wrap.
        """
        yield from self.shapes

    def findDrivenIndex(self, drivenShape:'nodes.DeformableShape'
                        ) -> Optional['nodes.DeformableShape']:
        """
        :param drivenShape: the shape to inspect
        :return: The index, or None if no match.
        """
        drivenShape = self._toDeformableShape(drivenShape)

        if drivenShape in self.iterDrivenShapes():
            for slot in self.attr('outputGeometry'):
                if drivenShape in slot.future(type='deformableShape'):
                    return slot.index()

    def numDrivens(self) -> int:
        """:return: The number of driven geometries."""
        return len(list(self.iterDrivenShapes()))

    def findDrivenShapeAtIndex(self,
                               index:int,
                               ) -> Optional['nodes.DeformableShape']:
        """
        :param index: the index to inspect
        :raises IndexError: the index doesn't exist
        :return: The shape at the specified index, or None.
        """
        self._checkDrivenIndex(index)
        slot = self.attr('outputGeometry')[index]

        for drivenShape in self.iterDrivenShapes():
            if drivenShape in slot.future(type='deformableShape'):
                return drivenShape

    #------------------|    Add driven

    def addDriven(self, drivenGeo) -> None:
        """
        Note: You may not see an effect until you edit the deformer falloff.

        This is a quiet operation. Nothing will happen if the geometry is
        already driven.

        :param drivenGeo: the geometry to deform
        """
        shape = self._toDeformableShape(drivenGeo)

        if shape not in self.iterDrivenShapes():
            m.deformer(str(self), e=True, geometry=[str(shape)])

    @short(force='f')
    def removeDriven(self, drivenGeo, force:bool=False) -> None:
        """
        This is a quiet operation. Nothing will happen if the geometry is not
        already driven

        :param drivenGeo: the geometry to stop deforming
        :param force/f: if the operation fails, attempt to force-remove the
            array slots; defaults to False
        """
        drivenGeo = self._toDeformableShape(drivenGeo)

        if drivenGeo in self.iterDrivenShapes():
            try:
                m.deformer(str(self), e=True, rm=True,
                           geometry=[str(drivenGeo)])

            except RuntimeError as e:
                if force:
                    index = self.findDrivenIndex(drivenGeo)

                    for attr in ('outputGeometry', 'originalGeometry'):
                        m.removeMultiInstance(f"{self}.{attr}[{index}]", b=True)
                else:
                    raise e

    @short(force='f')
    def removeDrivenAtIndex(self, drivenIndex:int, force:bool=False) -> None:
        """
        :param drivenIndex: the driven index
        :param force/f: if the operation fails, attempt to force-remove the
            array slots; defaults to False
        """
        if drivenIndex in self.attr('outputGeometry').indices():
            for drivenShape in self.iterDrivenShapes():
                if self.findDrivenIndex(drivenShape) == drivenIndex:
                    try:
                        m.deformer(str(self), e=True, rm=True,
                                   geometry=[str(drivenShape)])
                    except RuntimeError as e:
                        if force:
                            for attr in ('outputGeometry', 'originalGeometry'):
                                m.removeMultiInstance(
                                    f"{self}.{attr}[{drivenIndex}]", b=True
                                )
                        else:
                            raise e

    #------------------|    Driven base management

    @short(indirect='i')
    def findDrivenBaseShapeAtIndex(self,
                                   drivenIndex:int,
                                   indirect:bool=False
                                   ) -> Optional['nodes.DeformableShape']:
        """
        :param drivenIndex: the driven index
        :param indirect/i: if no shape is directly connected into
            ``originalGeometry``, return the first one further upstream;
            defaults to False
        """
        if drivenIndex in self.attr('outputGeometry').indices():
            slot = self.attr('originalGeometry')[drivenIndex]

            if indirect:
                return next(slot.history(type='deformableShape'))

            return next(slot.iterInputs(type='deformableShape', shapes=True))

        else:
            raise IndexError(
                "driven index doesn't exist: {}".format(drivenIndex)
            )

    def setDrivenBaseShapeAtIndex(
            self,
            drivenIndex:int,
            baseSource:Union['nodes.DeformableShape', 'plugs.Geometry']
    ) -> None:
        """
        :param drivenIndex: the driven index
        :param baseSource: a DAG geometry node or geometry plug to connect into
            the 'originalGeometry' slot
        """
        self._checkDrivenIndex(drivenIndex)
        self._toGeoOutput(baseSource
                          ) >> self.attr('originalGeometry')[drivenIndex]

    #-------------------------------------|
    #-------------------------------------|    Driver
    #-------------------------------------|

    #------------------|    Driver queries

    def checkDriverIndex(self, index:int) -> int:
        if index not in self.attr('drivers').indices():
            raise IndexError("driver index doesn't exist: {}".format(index))

    def numDrivers(self) -> int:
        """
        :return: the number of in-use driver slots on the deformer
        """
        return len(self.attr('drivers'))

    @short(indirect='i')
    def findDriverIndex(self,
                        driverGeo:'nodes.DagNode',
                        indirect:bool=False) -> Optional[int]:
        """
        :param driverGeo: the driver geo to inspect
        :param indirect/i: if no direct connection into a ``driverGeometry``
            slot is found, look for indirect matches further upstream; defaults
            to False
        """
        driverShape = self._toDeformableShape(driverGeo)

        # First pass
        for slot in self.attr('drivers'):
            plug = slot.attr('driverGeometry')
            if next(plug.iterInputs(type='deformableShape',
                                    shapes=True), None) == driverShape:
                return slot.index()

        if indirect:
            for slot in self.attr('drivers'):
                plug = slot.attr('driverGeometry')
                if driverShape in plug.history(type='deformableShape'):
                    return slot.index()

    def setDriverShapeAtIndex(
            self,
            driverIndex:int,
            shapeSource:Union['nodes.DagNode', 'plugs.Geometry']
    ):
        """
        :param driverIndex: the driver index
        :param shapeSource: a geometry DAG node or geometry input
        """
        self.checkDriverIndex(driverIndex)
        slot = self.attr('drivers')[driverIndex]
        plug = slot.attr('driverGeometry')
        shapeSource = self._toDeformableShape(shapeSource, worldSpace=True)
        shapeSource >> plug

    @short(indirect='i')
    def findDriverShapeAtIndex(self,
                               driverIndex:int,
                               indirect:bool=False
                               ) -> Optional['nodes.DeformableShape']:
        """
        :param driverIndex: the driver index to inspect
        :param indirect/i: if there's no direct shape connection into
            ``driverGeometry``, look for a shape further upstream; defaults to
            False
        :raises IndexError: the driver index doesn't exist
        """
        self.checkDriverIndex(driverIndex)
        slot = self.attr('drivers')[driverIndex].attr('driverGeometry')

        shape = next(slot.iterInputs(type='deformableShape', shapes=True),
                     None)

        if shape is not None:
            return shape

        if indirect:
            shape = next(slot.history(type='deformableShape'), None)
            if shape is not None:
                return shape
        else:
            raise IndexError(
                "driver index doesn't exist: {}".format(driverIndex)
            )

    @short(indirect='i',
           includeNone='inn')
    def iterDriverShapes(self,
                         indirect:bool=False,
                         includeNone:bool=False
                         ) -> Iterator['nodes.DeformableShape']:
        """
        :param indirect/i: if some ``driverGeometry`` slots don't have a direct
            connection to a shape, look for a shape further upstream; defaults
            to False
        :param includeNone/inn: include None returns to keep the length
            constant; defaults to False
        :return: An iterator of driver shapes.
        """
        for index in self.attr('drivers').indices():
            thisShape = self.findDriverShapeAtIndex(index, indirect=indirect)

            if thisShape is None and not includeNone:
                continue

            yield thisShape

    @short(indirect='i')
    def hasDriver(self, driverGeo:'nodes.DagNode', indirect:bool=False) -> bool:
        """
        :param driverGeo: the geometry to check
        :param indirect/i: if no direct connection is found, match a slot by
            looking further upstream; defaults to False
        """
        return self._toDeformableShape(
            driverGeo) in self.iterDriverShapes(indirect=indirect)

    #------------------|    Add drivers

    def addDriver(self, driverGeo:'nodes.DagNode') -> None:
        """
        This is a quiet operation. Nothing will happen if the geometry is
        already a driver.

        :param driverGeo: the driver geometry to add
        """
        driverShape = self._toDeformableShape(driverGeo)

        if not self.hasDriver(driverShape):
            m.proximityWrap(str(self), e=True, addDrivers=[str(driverShape)])

    #------------------|    Remove drivers

    @short(force='f')
    def removeDriverAtIndex(self, driverIndex:int, force:bool=False) -> None:
        """
        :param driverIndex: the driver index to remove
        :param force/f: if the driver can't be removed using the
            ``proximityWrap`` command (e.g. due to a complex connection), fall
            back to ``removeMultiInstance``; defaults to False
        """
        self.checkDriverIndex(driverIndex)
        slot = self.attr('drivers')[driverIndex]
        plug = slot.attr('driverGeometry')
        shape = next(plug.iterInputs(type='deformableShape', shapes=True),
                     None)
        if shape is None:
            if force:
                m.removeMultiInstance(str(slot), b=True)
            else:
                raise RuntimeError(
                    "no shape connected into index {}".format(driverIndex)
                )
        else:
            try:
                m.proximityWrap(str(self),
                                e=True,
                                removeDrivers=[str(shape)])
            except RuntimeError as e:
                if force:
                    m.removeMultiInstance(str(slot), b=True)
                else:
                    raise e

    @short(indirect='i',
           force='f')
    def removeDriver(self,
                     driverGeo:'nodes.DagNode',
                     indirect:bool=False,
                     force:bool=False) -> None:
        """
        This is a quiet operation. Nothing will happen if the geometry is not
        a driver.

        :param indirect/i: look for a slot match even if the driver does not
            directly connect into a ``driverGeometry`` slot; defaults to False
        :param force/f: if a match is found, but the operation fails, force-
            remove the slot instance; defaults to False
        """
        index = self.findDriverIndex(driverGeo, indirect=indirect)

        if index is not None:
            self.removeDriverAtIndex(index, force=force)

    #------------------|    Edit drivers

    def getDriverSlot(self, driverIndex:int) -> 'plugs.Attribute':
        """
        :param driverIndex: the driver index
        :return: The matching element on the ``drivers`` array.
        """
        self.checkDriverIndex(driverIndex)
        return self.attr('drivers')[driverIndex]

    @short(indirect='i')
    def findDriverBaseShapeAtIndex(self,
                                   driverIndex:int,
                                   indirect:bool=False
                                   ) -> Optional['nodes.DeformableShape']:
        """
        :param driverIndex: the driver index to inspect
        :param indirect/i: if no direct shape connection into ``bindGeometry``
            is found, look for a shape further upstream; defaults to False
        """
        self.checkDriverIndex(driverIndex)
        slot = self.attr('drivers')[driverIndex]
        plug = slot.attr('driverBindGeometry')

        shape = next(plug.iterInputs(type='deformableShape', shapes=True), None)

        if shape is not None:
            return shape

        if indirect:
            return next(plug.history(type='deformableShape'), None)

    def setDriverBaseShapeAtIndex(
            self,
            driverIndex:int,
            baseShape:Union['nodes.DagNode', 'plugs.Geometry']
    ):
        """
        :param driverIndex: the driver index
        :param baseShape: a geometry plug or a shape
        """
        self.checkDriverIndex(driverIndex)
        input = self._toGeoOutput(baseShape)
        input >> self.attr('drivers'
                           )[driverIndex].attr('driverBindGeometry')

    def getDriverDetail(self,
                        driverIndex:int,
                        detailName:str,
                        asString:bool=False) -> Any:
        """
        :param driverIndex: the driver index
        :param detailName: the name of a child attribute under ``drivers``,
            minus the 'driver' prefix, e.g. 'bindGeometry'
        :param asString: if an attribute is an enum, return its value as a
            string; defaults to False
        :return: The input on the attribute or, if there's not input and the
            attribute type is of a numerical type, the attribute value
        """
        self.checkDriverIndex(driverIndex)
        attrName = join_camel(('driver', detailName))
        plug = self.attr('drivers')[driverIndex].attr(attrName)
        input = next(plug.iterInputs(plugs=True), None)

        if input is not None:
            return input

        if isinstance(plug, (plugs['Math'], plugs['String'])):
            if asString and isinstance(plug, plugs['Enum']):
                return plug(asString=True)
            return plug()

    def setDriverDetail(self,
                        driverIndex:int,
                        detailName:str,
                        detailContent:Any) -> None:
        """
        :param driverIndex: the driver index
        :param detailName: the name of a child attribute under ``drivers``
            minus the 'driver' prefix, e.g. 'bindGeometry'
        :param detailContent: an input or value for the attribute
        """
        self.checkDriverIndex(driverIndex)
        attrName = join_camel(('driver', detailName))
        plug = self.attr('drivers')[driverIndex].attr(attrName)
        detailContent >> plug

    def setDriverDetails(self, driverIndex:int, **details) -> None:
        """
        Batch version of :meth:`setDriverDetail`.

        :param driverIndex: the driver index
        :param \*\*details: k, v pairs where each key is the the name of a child
            attribute under ``drivers`` minus the 'driver' prefix, e.g.
            'bindGeometry', and each value is a value or input for the attribute
        """
        self.checkDriverIndex(driverIndex)
        slot = self.attr('drivers')[driverIndex]

        for detailName, detailContent in details.items():
            attrName = join_camel(('driver', detailName))
            plug = slot.attr(attrName)
            detailContent >> plug