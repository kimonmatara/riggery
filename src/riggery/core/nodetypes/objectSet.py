from typing import Iterator, Optional

from ..nodetypes import __pool__ as nodes
from ..lib import names as _nm

from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short

import maya.cmds as m

DependNode = nodes['DependNode']


class ObjectSet(DependNode):

    #---------------------------------|    Constructor

    @classmethod
    @short(name='n', parent='p')
    def create(cls, *members, name:Optional[str]=None, parent=None):
        kwargs = {'empty': True}

        if name:
            kwargs['name'] = name
        else:
            if _nm.Name.__elems__:
                kwargs['name'] = _nm.Name.evaluate(
                    typeSuffix=cls.__typesuffix__
                )

        node = nodes['ObjectSet'](m.sets(**kwargs))

        if members:
            node.add(members)

        if parent:
            nodes['ObjectSet'](parent).add(node)

        return node

    #---------------------------------|    Add members

    def add(self, *members) -> 'ObjectSet':
        """Adds the specified members to this set."""
        members = list(
            without_duplicates(map(str, expand_tuples_lists(*members)))
        )
        if members:
            m.sets(members, e=True, fe=str(self))

        return self

    #---------------------------------|    Get members

    def iterDagSetMembers(self) -> Iterator:
        """
        Yields objects that connect into the `dagSetMembers` multi-attribute.
        Useful for quick ordered queries.
        """
        for slot in self.attr('dagSetMembers'):
            inputs = slot.inputs(plugs=True)
            if inputs:
                yield inputs[0].node()