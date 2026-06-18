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

    # The below should be renamed to addMembers; this is because remove()
    # in other riggery contexts refers to "remove this object"

    def add(self, *members) -> 'ObjectSet':
        """Adds the specified members to this set."""
        members = list(
            without_duplicates(map(str, expand_tuples_lists(*members)))
        )
        if members:
            m.sets(members, e=True, fe=str(self))

        return self

    addMembers = add

    def removeMembers(self, *members):
        members = list(
            without_duplicates(map(str, expand_tuples_lists(*members)))
        )
        if members:
            m.sets(members, e=True, remove=str(self))

        return self

    #---------------------------------|    Get members

    @short(recurse='r')
    def iterDagSetMembers(self,
                          recurse:bool=False) -> Iterator['nodes.DagNode']:
        visited = set()

        for slot in self.attr('dagSetMembers'):
            input = next(slot.iterInputs(plugs=True), None)

            if input is not None:
                node = input.node()
                visited.add(node)
                yield node

        if recurse:
            for subset in self.iterSubsets(recurse=True):
                for member in subset.iterDagSetMembers():
                    if member not in visited:
                        visited.add(member)
                        yield member

    def iterDnSetMembers(self) -> Iterator['nodes.DagNode']:
        for slot in self.attr('dnSetMembers'):
            input = next(slot.iterInputs(plugs=True), None)

            if input is not None:
                yield input.node()

    def iterSubsets(self, recurse:bool=False) -> Iterator['nodes.DagNode']:
        visited = set()

        for item in self.iterDnSetMembers():
            if isinstance(item, ObjectSet):
                if item not in visited:
                    visited.add(item)
                    yield item

                    if recurse:
                        for member in item.iterSubsets(recurse=True):
                            if member not in visited:
                                visited.add(item)
                                yield item