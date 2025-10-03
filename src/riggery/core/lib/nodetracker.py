"""Tools for automatic node capture / collection."""

from typing import Generator, Union, Optional, Callable

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
import riggery.internal.nodeinfo as _ni
import riggery.internal.api2str as _a2s
from ..lib import namespaces as _ns
from ..nodetypes import __pool__ as _nodes


class NodeTracker:

    __stack__ = []
    __callbacks__ = []

    #-------------------------------------|    Inst

    def __init__(self, predicate=None):
        """
        :param predicate: an optional callable, that will receive an MObject
            for a node, and should return True if the node should be tracked or
            False if it shouldn't; defaults to None
        """
        self._nodes = []
        self.predicate = predicate

    def getPredicate(self):
        return self._predicate

    def setPredicate(self, predicate:Optional[Callable]):
        if predicate is None:
            self._predicate = lambda _: True
        else:
            self._predicate = predicate

    def clearPredicate(self):
        self.setPredicate(None)

    predicate = property(getPredicate, setPredicate, clearPredicate)

    #-------------------------------------|    Context

    def __enter__(self):
        self._nodes.clear()
        NodeTracker.__stack__.append(self)

        if len(NodeTracker.__stack__) == 1:
            self._startCallbacks()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if len(NodeTracker.__stack__) == 1:
            self._stopCallbacks()

        del(NodeTracker.__stack__[-1])

        return False

    #-------------------------------------|    Add / remove methods

    def _addNode(self, node:om.MObject) -> bool:
        if self.predicate(node):
            self._nodes.append(node)
            return True
        return False

    def _removeNode(self, node:om.MObject) -> bool:
        try:
            self._nodes.remove(node)
            return True
        except ValueError:
            return False

    #-------------------------------------|    Callbacks

    @classmethod
    def _nodeAdded(cls, node:om.MObject, *args):
        for tracker in reversed(NodeTracker.__stack__):
            tracker._addNode(node)

    @classmethod
    def _nodeRemoved(cls, node:om.MObject, *args):
        for tracker in reversed(NodeTracker.__stack__):
            tracker._removeNode(node)

    @classmethod
    def _startCallbacks(cls):
        NodeTracker.__callbacks__[:] = [
            om.MDGMessage.addNodeAddedCallback(cls._nodeAdded, 'dependNode'),
            om.MDGMessage.addNodeRemovedCallback(cls._nodeRemoved, 'dependNode')
        ]

    @classmethod
    def _stopCallbacks(cls):
        om.MMessage.removeCallbacks(NodeTracker.__callbacks__)
        NodeTracker.__callbacks__.clear()

    #-------------------------------------|    List interface

    def ofType(self, type:Union[str, list[str]]) -> Generator:
        """
        In contrast to :meth:`__iter__`, only yields nodes that match the
        specified node type(s).

        :param type: one or more node types (e.g. 'camera')
        """
        if type is None:
            cls = _nodes['DependNode']

            for node in self._nodes:
                yield cls.fromMObject(node)
        else:
            acceptedTypes = set(expand_tuples_lists(type))

            for node in self._nodes:
                nodeType = om.MFnDependencyNode(node).typeName
                nodeTypes = set(m.nodeType(nodeType,
                                           inherited=True,
                                           isTypeName=True))
                if nodeTypes.intersection(acceptedTypes):
                    cls = _nodes[nodeType[0].upper()+nodeType[1:]]
                    yield cls.fromMObject(node)

    def __iter__(self):
        cls = _nodes['DependNode']

        for node in self._nodes:
            yield cls.fromMObject(node)