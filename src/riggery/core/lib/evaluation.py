"""Tools to manage DG evaluation."""

import inspect
from functools import wraps
import re
import maya.cmds as m
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..lib import names as _nm


class DGEval:
    """
    Switches to DG mode for the block. Doesn't always fix build issues;
    sometimes you're better off calling dgeval on nodes.
    """
    def __enter__(self):
        self._mode = m.evaluationManager(q=True, mode=True)[0]
        m.evaluationManager(mode='off')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        m.evaluationManager(mode=self._mode)
        m.evaluationManager(invalidate=True)
        return False

def cache_dg_output(f):
    """
    Decorator for node or plug methods that are unary, i.e. don't take any
    arguments beyond *self*, and return a single node or plug.
    """
    signature = inspect.signature(f)
    if len(list(signature.parameters)) > 1:
        raise TypeError("method has arguments")

    fname = f.__name__

    @wraps(f)
    def wrapper(self):
        isNode = isinstance(self, nodes['DependNode'])
        if isNode:
            src = self.attr('message')
        else:
            src = self

        network = None

        for output in src.outputs(plugs=True, type='network'):
            if output.attrName() == 'dg_cache_source':
                network = output.node()
                break

        if network is None:
            elems = []
            if isNode:
                bn = self.shortName(sns=True, sts=True)
                if bn:
                    elems.append(bn)
            else:
                bn = self.node().shortName(sns=True, sts=True)
                if bn:
                    elems.append(bn)
                elems.append(self.attrName())
            elems.append('dg_cache')

            with _nm.Name(*elems, override=True):
                network = nodes['Network'].createNode()
            src >> network.addAttr('dg_cache_source', at='message')
            network.attr('dg_cache_source').lock()

        attrName = f"cached_{fname}_output"
        if not network.hasAttr(attrName):
            network.addAttr(attrName, at='message')

        attr = network.attr(attrName)
        inputs = attr.inputs(plugs=True)
        if not inputs:
            result = f(self)
            attr.unlock()
            if isinstance(result, nodes['DependNode']):
                result.attr('message') >> attr
            else:
                result >> attr
            attr.lock()
            return result

        input = inputs[0]
        if input.attributeType() == 'message':
            return input.node()
        return input
    return wrapper