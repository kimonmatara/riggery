from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short, resolve_flags
from typing import Union, Optional
from ..plugtypes import __pool__
from ..nodetypes import __pool__ as nodes
from ..lib import names as _nm
from ..elem import Elem

import maya.api.OpenMaya as om
import maya.cmds as m


class Enum(__pool__['Int']):

    #-----------------------------------------|    Axis pickers

    @classmethod
    @short(defaultValue='dv',
           channelBox='cb',
           keyable='k')
    def createBoolCarousel(cls,
                           node,
                           attrName:str,
                           nameGroupPairs:list[tuple[str, list]],
                           defaultValue=None,
                           channelBox=None,
                           keyable=None):
        """
        Creates a sort of 'switchboard' configuration for boolean attributes,
        where selecting one of the enums will pipe True into every boolean
        attribute in the group assigned to that enum, and False into every
        boolean attribute that's not assigned to that enum, but is a member of
        the overall pool.

        Good for user visibility presets.

        :param node: the node on which to create the attribute
        :param attrName: the attribute name
        :param nameGroupPairs: a list of tuples, where each tuple comprises
            an enum name and a list of target boolean attributes (e.g. node
            visibility channels)
        :param defaultValue/dv: a default value for the enum; defaults to None
        :param channelBox/cb: make the enum settable; defaults to False
        :param keyable/k: make the enum keyable; defaults to False
        :return: The enum attribute.
        """
        # Conform the group pairs
        Attribute = __pool__['Attribute']

        nameGroupPairs = [(name, list(map(Attribute, group)))
                          for (name, group) in nameGroupPairs]

        allMembers = []
        for (name, group) in nameGroupPairs:
            allMembers += list(group)
        allMembers = list(set(allMembers))
        names = [pair[0] for pair in nameGroupPairs]

        # Init the attribute
        node = nodes['DependNode'](node)

        kwargs = {}
        if keyable is not None:
            kwargs['keyable'] = keyable
        if channelBox is not None:
            kwargs['channelBox'] = channelBox
        if defaultValue is not None:
            kwargs['defaultValue'] = defaultValue

        attr = node.addAttr(attrName,
                            at='enum',
                            enumName=':'.join(names),
                            **kwargs)
        _attr = str(attr)

        for i, (name, group) in enumerate(nameGroupPairs):
            for member in allMembers:
                m.setDrivenKeyframe(str(member),
                                    currentDriver=_attr,
                                    driverValue=i,
                                    value=member in group)

        return attr

    @classmethod
    @short(defaultValue='dv',
           channelBox='cb',
           keyable='k')
    def createAxisPicker(cls,
                         node,
                         attrName:str,
                         defaultValue=None,
                         channelBox=None,
                         keyable=None,
                         includeNegative:bool=False):
        """
        Creates an enum attribute to pick axes (e.g. x, y etc.).
        :param node: the node on which to add the attribute
        :param attrName: the attribute name
        :param defaultValue: the default value, as a string (e.g. 'x') or index;
            defaults to None
        :param channelBox: make the attribute settable; defaults to False
        :param keyable: make the attribute keyable; defaults to False
        :param includeNegative: include negative axes (e.g. '-y'); defaults to
            False
        :return: The attribute
        """
        keys = ['x', 'y', 'z']
        if includeNegative:
            keys += ['-'+key for key in keys]

        node = nodes['DependNode'](node)
        kwargs = {'attributeType': 'enum', 'enumName': ':'.join(keys)}

        if defaultValue is not None:
            kwargs['defaultValue'] = defaultValue

        if channelBox is not None:
            kwargs['channelBox'] = channelBox

        if keyable is not None:
            kwargs['keyable'] = keyable

        return node.createAttr(attrName, **kwargs)

    @property
    @cache_dg_output
    def axisPickerVectorOutput(self):
        enumNames = self.enumNames()

        with _nm.Name('axis_as_vec'):
            nw = nodes['Network'].createNode()

            vectors = __pool__['Vector'].createAxisVectors(
                nw, 'axisVectors',
                includeNegative=len(enumNames) > 3
            )

            outVector = nw.addVectorAttr(
                'axisVector', k=True, l=True,
                i = self.select(vectors, __pool__['Vector'])
            )

        return outVector

    @cache_dg_output
    def flipAxisPickerOutput(self):
        """
        For attributes created using :meth:`createAxisPicker` with
        *includeNegative* set to True. Flips the integer output, such that if
        'y' is selected, the index for '-y' is returned instead, and so on.
        """
        network = None

        for output in self.outputs(plugs=True, type='network'):
            if output.attrName() == 'axisToFlip':
                network = output.node()
                break

        if network is None:
            with _nm.Name('flip_axis'):
                network = nodes['Network'].createNode()

            inp = network.addAttr('axisToFlip', at='short', k=True)
            self >> inp
            inp.lock()

            network.addAttr('flippedAxis',
                            at='enum',
                            enumName='x:y:z:-x:-y:-z',
                            k=True, dv=self.defaultValue)
            attr = network.attr('flippedAxis')

            ((self + 3) % 6) >> attr
            attr.lock()

        return network.attr('flippedAxis')

    #-----------------------------------------|    Default value

    def setDefaultValue(self, value:Union[int, str]):
        if isinstance(value, str):
            value = self.enumNames().index(value)
        return super().setDefaultValue(value)

    #-----------------------------------------|    Get

    def _getValue(self, *, asString=False, frame=None, **kwargs):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        kwargs = {}
        if frame is not None:
            kwargs['context'] = om.MDGContext(
                om.MTime(frame, om.MTime(frame, unit=om.MTime))
            )
        value = plug.asInt(**kwargs)
        if asString:
            return om.MFnEnumAttribute(plug.attribute()).fieldName(value)
        return value

    #-----------------------------------------|    Set

    def _setValue(self, value, /, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        if isinstance(value, str):
            value = om.MFnEnumAttribute(plug.attribute()).fieldValue(value)
        plug.setInt(value)

    #-----------------------------------------|    Enum methods

    def enumValues(self) -> list[int]:
        """
        :return: The enum values in this attribute, in a list.
        """
        fn = om.MFnEnumAttribute(self.__apimobject__())
        min = fn.getMin()
        max = fn.getMax()
        return list(range(min, max+1))

    def enumNames(self) -> list[str]:
        """
        :return: The enum names in this attribute, in a list.
        """
        fn = om.MFnEnumAttribute(self.__apimobject__())
        min = fn.getMin()
        max = fn.getMax()
        return [fn.fieldName(i) for i in range(min, max+1)]

    def enums(self) -> list[tuple]:
        """
        :return: Pairs of *enum name, enum value*.
        """
        return list(zip(self.enumNames(), self.enumValues()))

    #-----------------------------------------|    Sections

    def isSectionAttr(self) -> bool:
        """
        :return: ``True`` if this looks like a 'section' enum attribute.
        """
        if self.isLocked():
            enumNames = self.enumNames()
            if len(enumNames) == 1 and enumNames[0] == ' ':
                return True
        return False