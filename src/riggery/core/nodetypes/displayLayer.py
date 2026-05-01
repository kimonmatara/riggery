from typing import Iterator
from ..nodetypes import __pool__ as nodes
DependNode = nodes['DependNode']

import maya.cmds as m
import riggery.core.lib.names as _nm
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates

from . import __pool__ as _nodes


class DisplayLayer(DependNode):

    #---------------------------------|    Constructor

    @classmethod
    @short(selection='sl',
           skipDefaultLayer='skd')
    def ls(cls,
           *patterns,
           selection:bool=False,
           skipDefaultLayer:bool=False) -> Iterator['DisplayLayer']:

        for layer in super().ls(*patterns, selection=selection):
            if skipDefaultLayer and layer.shortName(sns=True) == 'defaultLayer':
                continue
            yield layer

    @classmethod
    @short(name='n')
    def create(cls, *members, name=None, reuse:bool=False, **attrs):
        if not name:
            if _nm.Name.__elems__:
                name = _nm.Name.evaluate(typeSuffix=cls.__typesuffix__)

        kwargs = {}

        if name:
            kwargs['name'] = name

        if reuse and name:
            if m.objExists(name):
                if m.objectType(name, isType='displayLayer'):
                    return cls(name)

        layer = cls(m.createDisplayLayer(empty=True, **kwargs))

        if members:
            layer.addMembers(*members)

        for k, v in attrs.items():
            layer.attr(k).put(v)

        return layer

    #---------------------------------|    Members

    @short(recurse='r')
    def addMembers(self, *members, recurse:bool=False):
        """
        :param *members: the nodes to add to the layer
        :param recurse/r: include descendants; defaults to False
        """
        members = expand_tuples_lists(*members)
        members = map(str, members)
        members = without_duplicates(members)

        m.editDisplayLayerMembers(str(self), *members, noRecurse=not recurse)

        return self