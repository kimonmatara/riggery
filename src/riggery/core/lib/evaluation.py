"""Tools to manage DG evaluation."""

from typing import get_type_hints
import inspect
from functools import wraps
import re
import maya.cmds as m

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs

from ..lib import names as _nm
from ..lib.serialize import simplify

from ...general.types import conform_instance
from ...general.functions import get_shorthands


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

def cache_plug_method(f):
    # Get type hints for all arguments past ``self``
    params = dict(list(signature.parameters.items())[1:])
    pos_only = []
    pos_or_kw = []

    hints = get_type_hints(f)

    for paramName, param in params.items():
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            pos_only.append(paramName)

        elif param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            pos_or_kw.append(paramName)

        elif param.kind in (inspect.Parameter.VAR_POSITIONAL,
                            inspect.Parameter.VAR_KEYWORD):

            raise TypeError("*args / **kwargs not supported")

    @wraps(f)
    def wrapper(self, *args, **kwargs):
        
        #--------------|    Figure out which arguments we got

        _pos_only = pos_only.copy()
        _pos_or_kw = pos_or_kw.copy()

        receivedParams = {}

        for arg in args:
            try:
                name = _pos_only.pop(0)
            except IndexError:
                try:
                    name = _pos_or_kw.pop(0)
                except IndexError:
                    raise TypeError("unexpected positional argument")

            receivedParams[name] = arg

        receivedParams.update(kwargs.copy())

        hints = get_type_hints(f)

        if hints:
            for k in list(receivedParams.keys()):
                try:
                    hint = hints[k]
                except KeyError:
                    continue

                receivedParams[k] = conform_instance(receivedParams[k],
                                                     hint,
                                                     False,
                                                     True)

        receivedParamNames = set(receivedParams.keys())

        #--------------|    Look for a match

        for output in self.iterOutputs(plugs=True, type='network'):
            if (output.type() == 'message'
                    and output.attrName() == '_dgCaller'):
                nw = output.node()

                if nw.attr('_dgMethod')() != f.__name__:
                    continue

                bail = False
                nwReceivedParamNames = eval(nw.attr('_dgParams')())

                if set(nwReceivedParamNames) == receivedParamNames:
                    for (receivedParamName,
                         receivedParamValue) in receivedParams.items():
                        slot = nw.attr('_dgParam{}'.format(paramName))
                        nwReceivedInputOrValue, isPlug = slot.getInputOrValue()

                        if not isPlug:
                            nwReceivedInputOrValue = eval(
                                newReceivedInputOrValue
                            )

                        try:
                            hint = hints[paramName]
                            doCast = True
                        except KeyError:
                            doCast = False

                        if doCast:
                            nwReceivedInputOrValue = conform_instance(
                                nwReceivedInputOrValue,
                                hint,
                                False,
                                True
                            )

                        if nwReceivedInputOrValue != receivedParamValue:
                            bail = True
                            break

                if bail:
                    continue

                output = nw.attr('_dgOutput').getInputOrValue()

                if output.type() == 'message':
                    out = next(output.iterInputs(plugs=True))

                    if out.type() == 'message':
                        return out.node()

                else:
                    out, _ = output.getInputOrValue()

                try:
                    hint = hints['return']
                    doCast = True
                except KeyError:
                    doCast = False

                if doCast:
                    out = conform_instance(out, hint, False, True)

                return out

        #--------------|    Get return, capture

        result = f(self, *args, **kwargs)

        try:
            hint = hints['return']
            doCast = True
        except KeyError:
            doCast = False

        if doCast:
            result = conform_instance(result, hint, False, True)

        nw = nodes['Network'].createNode()
        self >> nw.addAttr('_dgCaller', type='message')
        nw.addAttr('_dgMethod', dt='string').set(f.__name__).lock()

        for receivedParamName, receivedParamValue in receivedParams.items():
            slotName = f'_dgParam{receivedParamName}'

            if isinstance(receivedParamValue, plugs['Attribute']):
                slot = nw.addAttr(slotName, at='message', i=receivedParamName)
            else:
                slot = nw.addAttr(slotName, dt='string')
                slot.set(repr(simplify(receivedParamValue)))

            slot.lock()

        return result

    shorthands = get_shorthands(f)

    if shorthands:
        wrapper = short(**shorthands)(wrapper)

    return wrapper