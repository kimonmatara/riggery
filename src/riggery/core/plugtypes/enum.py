from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short, resolve_flags
from riggery.general.iterables import without_duplicates
from typing import Union, Optional
from ..plugtypes import __pool__
from ..nodetypes import __pool__ as nodes
from ..lib import names as _nm
from ..elem import Elem

import maya.api.OpenMaya as om
import maya.cmds as m


class Enum(__pool__['Int']):

    #-----------------------------------------|    Selectors

    @classmethod
    @short(noneLabel='nl',
           allLabel='al',
           section='s',
           defaultValue='dv')
    def createVisCarousel(cls,
                          node,
                          attrName:str,
                          labelsGroups:Union[list, dict],
                          noneLabel:Optional[str]=None,
                          allLabel:Optional[str]=None,
                          section:Optional[str]=None,
                          defaultValue:Optional[Union[str, int]]=None):
        """
        Creates an enum attribute where each item defines a visibility group for
        DAG nodes.

        :param node: the node on which to create the attribute
        :param attrName: the attribute name
        :param labelsGroups: a mapping of label: [dagNode, dagNode...]; this
            can either be a dict or zipped pairs
        :param noneLabel: if this is specified, an extra group with this label,
            and an empty member list, will be inserted at index 0 of
            *labelsGroups*; defaults to None
        :param allLabel: if this is specified, an extra group with this label,
            and a list comprising all members, will be appended to
            *labelsGroups*; defaults to None
        :param defaultValue/dv: the default value of the attribute, as a label
            of index; defaults to 0
        :param section/s: an optional section name for the new attribute;
            defaults to None
        :return: The constructed attribute.
        """

        # Conform args

        node = nodes['DependNode'](node)

        if isinstance(labelsGroups, dict):
            labels, groups = zip(*labelsGroups.items())
        else:
            labels, groups = zip(*labelsGroups)

        DagNode = nodes['DagNode']

        labels = list(labels)

        _groups = []
        for group in groups:
            _group = []
            for item in group:
                try:
                    plug = __pool__['Attribute'](item)
                except:
                    plug = DagNode(item).attr('v')
                _group.append(plug)
            _groups.append(_group)
        groups = _groups

        # groups = [[DagNode(x).attr('v') for x in group] for group in groups]

        allPlugs = []

        for group in groups:
            allPlugs += group
        allPlugs = list(without_duplicates(allPlugs))

        if allLabel:
            labels.append(allLabel)
            groups.append(allPlugs)

        if noneLabel:
            labels.insert(0, noneLabel)
            groups.insert(0, [])

        # Create attribute

        sw = node.createAttr(attrName,
                             at='enum',
                             enumName=':'.join(labels),
                             cb=True,
                             dv=defaultValue,
                             s=section)

        # Capture existing inputs

        inputMap = {}

        for plug in allPlugs:
            inputs = plug.inputs(plugs=True)
            if inputs:
                input = inputs[0]
                input // plug
                inputMap[plug] = input

        # Iterate

        for i, group in enumerate(groups):
            for plug in allPlugs:
                value = 1 if plug in group else 0
                m.setDrivenKeyframe(str(plug),
                                    cd=str(sw),
                                    dv=i,
                                    v=value,
                                    ott='step')

        for plug, input in inputMap.items():
            (plug.inputs(plugs=True) * input) >> input

        return sw

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
        enumNames = self.enumNames

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
            value = self.enumNames.index(value)
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

    def isEmpty(self) -> bool:
        fn = self.__apimfn__()
        return fn.getMin() == 1000 and fn.getMax() == -1

    def getEnumNames(self) -> list[str]:
        if self.isEmpty():
            return []
        return m.addAttr(str(self), q=True, enumName=True).split(':')

    def clearEnumNames(self):
        if not self.isEmpty():
            m.addAttr(str(self), e=True, enumName='')
        return self

    def setEnumNames(self, names:Union[list[str], tuple[str]]):
        if names:
            if self.isEmpty():
                fn = self.__apimfn__()

                for i, name in enumerate(names):
                    fn.addField(name, i)
            else:
                m.addAttr(str(self), e=True, enumName=':'.join(names))
        else:
            self.clearEnumNames()
        return self

    enumNames = property(getEnumNames, setEnumNames, clearEnumNames)

    #-----------------------------------------|    Sections

    def isSectionAttr(self) -> bool:
        """
        :return: ``True`` if this looks like a 'section' enum attribute.
        """
        if self.isLocked():
            enumNames = self.enumNames
            if len(enumNames) == 1 and enumNames[0] == ' ':
                return True
        return False