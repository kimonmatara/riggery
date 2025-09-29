"""Contains utility classes for quick construction of DAG hierarchies."""

from typing import Optional, Generator

from ..elem import Elem
from ..nodetypes import __pool__ as nodes
from ..lib import names as _nm


class GroupTree:

    #-----------------------------------------|    Inst

    def __init__(self, *, key=None, node=None, parent=None):
        self._key = key

        if node is not None:
            node = nodes['Transform'](node)

        self._node = node
        self._parent = parent

    #-----------------------------------------|    Properties

    @property
    def key(self) -> Optional[str]:
        return self._key

    @property
    def parent(self) -> Optional['GroupTree']:
        return self._parent

    #-----------------------------------------|    Get branches

    def __getitem__(self, key):
        return GroupTree(key=key, parent=self)

    #-----------------------------------------|    Traversal

    @property
    def root(self):
        if self.isRoot():
            return self

        for parent in self.parents:
            if parent.isRoot():
                return parent

    def isRoot(self) -> bool:
        return not self._key

    @property
    def keys(self) -> list[str]:
        if self.isRoot():
            return []

        out = [self.key]
        for parent in self.parents:
            if parent.isRoot():
                break
            out.append(parent.key)
        return list(reversed(out))

    @property
    def parents(self) -> Generator['GroupTree', None, None]:
        current = self
        while True:
            current = current.parent
            if current is None:
                break
            yield current

    @property
    def stack(self) -> list:
        return list(reversed(list(self.parents))) + [self]

    def node(self, **xformAttrs):
        """
        Retrieves, or creates, a node at this tree depth.

        :param \*\*xformAttrs: a dictionary of attribute names, and values, to
            quickly configure the node.
        """
        if self.isRoot():
            return self._node
        out = nodes['Transform'].createFromDagPath(str(self))
        if xformAttrs:
            out.setAttrs(**xformAttrs)
        return out

    #-----------------------------------------|    Repr

    def __str__(self):
        """
        The projected DAG path for the node at this tree depth.
        """
        stack = self.stack
        root = stack.pop(0)

        namespace = str(root._node.namespace)

        if not namespace.endswith(':'):
            namespace += ':'
        prefix = root._node.prefix

        suffix = '_' + _nm.TYPESUFFIXES['transform']

        keys = [branch.key for branch in stack]
        elems = [root._node.longName()] + [f"{namespace}{prefix}{key}{suffix}"
                                           for key in keys]
        return '|'.join(elems)

    def __repr__(self):
        _node = self._node
        if _node is None:
            _node = 'None'
        else:
            _node = repr(str(_node))

        if self.isRoot():
            return "{}(node={})".format(self.__class__.__name__, _node)

        root = self.root
        tail = ''.join([f"['{key}']" for key in self.keys])
        return f"{repr(root)}{tail}"