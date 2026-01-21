from typing import Optional, Union, Literal

import maya.internal.nodes.proximitywrap.cmd_create as cmd_create
import maya.internal.nodes.proximitywrap.node_interface as node_interface


from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
WeightGeometryFilter = nodes['WeightGeometryFilter']

import maya.cmds as m
import riggery.core as r
import riggery.core.lib.names as _nm
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates

def _toShape(x) -> str:
    if m.objectType(x, isAType='transform'):
        return m.listRelatives(x, shapes=True, noIntermediate=True,
                               path=True)[0]
    return x


class ProximityWrap(WeightGeometryFilter):

    __consider_for_serialization__ = False # not there yet

    #-------------------------------------|    Constructor

    @classmethod
    def create(cls,
               driven, *,
               wrapMode='Surface',
               falloffScale=1.0,
               dropoffRateScale=0.0,
               smoothInfluences=0,
               smoothNormals=0,
               spanSamples:int=2,
               softNormalization=False,
               name:Optional[str]=None,
               useBindTags:bool=False,
               scaleCompensation=None,
               maxDrivers:int=10):
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

    #-------------------------------------|    Driver management

    def addDriver(self, driver, **details):
        _driverShape = _toShape(str(driver))
        m.proximityWrap(str(self), e=True, addDrivers=[_driverShape])
        self.setDriverDetails(driver, **details)

    def setDriverDetails(self, driver, **details):
        """
        :param \*\*details: attribute name: attribute value or input for every
            child attribute of the driver slot (e.g. ``driverBindGeometry``)
        """
        if details:
            slot = self.getDriverSlot(driver)
            for k, v in details.items():
                v >> slot.attr(k)

    def getDriverSlot(self, driver) -> Optional['plugs.Attribute']:
        shape = r.Elem(driver).toShape()

        for attr in ('worldMesh[0]', 'outMesh'):
            for output in shape.attr(attr).outputs(plugs=True):
                if output.node() == self:
                    if output.attrName(longName=True) == 'driverGeometry':
                        return output.parent

    def getDriverIndex(self, driver) -> Optional[int]:
        out = self.getDriverSlot()
        if out is not None:
            return out.index()

    #-------------------------------------|    Driven management

    def addDriven(self, driven, **slotDetails):
        _drivenShape = _toShape(str(driven))
        _self = str(self)
        ni = node_interface.NodeInterface(_self)
        ni.addShapesToDeformer([_drivenShape])

        if slotDetails:
            slot = self.getDrivenSlot(driven)
            for k, v in slotDetails.items():
                v >> slot.attr(k)

        return self

    def getDrivenIndex(self, driven):
        shape = r.Elem(driven).toShape()
        inputs = shape.attr('inMesh').inputs(plugs=True)

        for input in inputs:
            if (
                    input.node() == self
                    and input.attrName(longName=True) == 'outputGeometry'
            ):
                return input.index()

    def setDrivenOrigGeo(self, driven, origGeo):
        index = self.getDrivenIndex(driven)
        r.Elem(origGeo).toShape().attr('worldMesh'
                                    )[0] >> self.attr('originalGeometry')[index]