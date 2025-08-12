"""Tools for automatic node capture / collection."""

from typing import Generator
import maya.api.OpenMaya as om
from riggery.general.functions import short
from ..nodetypes import __pool__ as _nodes

class NodeTracker:
    """
    Context manager. Collects nodes created during the block. To get
    :class:`~riggery.core.elem.Elem` instances for the nodes, either iterate over
    the object or cast it to a list.

    .. code-block:: python

        with NodeTracker() as nodes:
            m.createNode('joint')
            m.createNode('joint')

        print(list(nodes))
        # Result: [Joint('joint1'), Joint('joint2')]
    """

    @short(nodeType='nt')
    def __init__(self, nodeType:str='dependNode'):
        """
        :param nodeType / nt: the type of node to track; defaults to
            'dependNode' (i.e. every dependency node subtype)
        """
        self._nodeType = nodeType
        self._nodes:list = []
        self._callbacks = []

    def __enter__(self):
        self._nodes.clear()
        self._startCallbacks()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stopCallbacks()
        return False

    #-------------------------------------|    Start / stop

    def _startCallbacks(self):
        self._callbacks = [
            om.MDGMessage.addNodeAddedCallback(
                self._nodeAdded,
                self._nodeType
            ),
            om.MDGMessage.addNodeRemovedCallback(
                self._nodeRemoved,
                self._nodeType
            ),
        ]

    def _stopCallbacks(self):
        om.MMessage.removeCallbacks(self._callbacks)
        self._callbacks.clear()

    #-------------------------------------|    Populating

    def _nodeAdded(self, node:om.MObject, *args):
        self._nodes.append(node)

    def _nodeRemoved(self, node:om.MObject, *args):
        self._nodes.remove(node)

    #-------------------------------------|    List-like interface

    def __iter__(self):
        T = _nodes['DependNode']

        for node in self._nodes:
            yield T.fromMObject(node)

    def __len__(self):
        return len(list(self._nodes))

    def __bool__(self):
        return len(self) > 0