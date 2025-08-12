"""Contains utility classes for quick construction of DAG hierarchies."""

from typing import Optional
from ..elem import Elem
from ..nodetypes import __pool__ as nodes
from ..lib import names as _nm

class GroupTree:

    def __init__(self, root=None, /):
        if root:
            root = Elem(root)
        self._node = root

    def node(self):
        return self._node

    @property
    def root(self):
        return self

    def isRoot(self) -> bool:
        return True

    def __getitem__(self, key:str):
        return GroupLeaf(self, key)

    def __repr__(self):
        return "{}({})".format(type(self).__name__,
                               repr(str(self._node)) if self._node else '')


class GroupLeaf:

    def __init__(self, parent:GroupTree, key:str):
        self._parent = parent
        self._key = key

    @property
    def parent(self):
        return self._parent

    @property
    def key(self):
        return self._key

    def isRoot(self):
        return False

    def node(self, **xformAttrs) -> str:
        """
        Retrieves, or creates, the group at the current level.

        :param \*\*xformAttrs: optional attibute edits, as keyword arguments;
            for example, to set 'inheritsTransform' to False on retrieval, do:

            .. code-block:: python

                tree['util'].node(it=False)
        """
        keys = []
        current = self
        root = None

        while True:
            keys.append(current.key)
            current = current.parent
            if current.isRoot():
                root = current
                break

        rootNode = root.node()
        namespace = None
        prefix = None

        if rootNode:
            namespace = rootNode.namespace
            prefix = rootNode.shortName(sns=True, sts=True)

        out = []
        if rootNode:
            out.append(rootNode.absoluteName())

        ts = _nm.TYPESUFFIXES['transform']

        for key in reversed(keys):
            name = f"{key}_{ts}"
            if prefix:
                name = f"{prefix}_{name}"
            if namespace:
                name = f"{namespace}:{name}"
            out.append(name)

        dagPath = '|'.join(out)
        node = nodes['Transform'].createFromDagPath(dagPath)
        if xformAttrs:
            node.setAttrs(**xformAttrs)
        return node

    def __getitem__(self, key):
        return GroupLeaf(self, key)