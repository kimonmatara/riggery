from typing import Generator
from ..nodetypes import __pool__ as nodes
DependNode = nodes['DependNode']

import maya.cmds as m


class ObjectSet(DependNode):

    #---------------------------------|    Member queries

    def iterDagSetMembers(self) -> Generator:
        """
        Yields objects that connect into the `dagSetMembers` multi-attribute.
        Useful for quick ordered queries.
        """
        for slot in self.attr('dagSetMembers'):
            inputs = slot.inputs(plugs=True)
            if inputs:
                yield inputs[0].node()