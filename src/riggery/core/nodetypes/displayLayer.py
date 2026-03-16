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
    @short(name='n')
    def create(cls, *members, name=None):
        kwargs = {}

        if name:
            kwargs['name'] = name
        elif _nm.Name.__elems__:
            kwargs['name'] = _nm.Name.evaluate(nodeType='displayLayer')

        layer = _nodes['DisplayLayer'](m.createDisplayLayer(empty=True,
                                                           **kwargs))
        if members:
            layer.addMembers(*members)
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