"""Tools to manage DG evaluation."""

import ast
from typing import get_type_hints
import inspect
from functools import wraps
import re
import maya.cmds as m
import maya.api.OpenMaya as om

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs

from ..lib import names as _nm
from ...internal.typeutil import UNDEFINED

from ...general.types import conform_instance
from ...general.functions import get_shorthands
from ...general.serialize import simplify


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

class _SkipNetworkError(Exception):
    ...

def cache_plug_method(f):

    @wraps(f)
    def wrapper(self, *args, **kwargs):
        # Get type hints for all arguments past ``self``; this parsing must
        # happen inside the wrapper, and not outside, otherwise we run into
        # grief with annotation evaluations

        signature = inspect.signature(f)
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

        #--------------|    Figure out which arguments we got

        receivedParams = {}

        for arg in args:
            try:
                name = pos_only.pop(0)
            except IndexError:
                try:
                    name = pos_or_kw.pop(0)
                except IndexError:
                    raise TypeError("unexpected positional argument")

            receivedParams[name] = arg

        receivedParams.update(kwargs.copy())

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

        receivedParamNames = list(receivedParams.keys())

        for output in self.iterOutputs(plugs=True, type='network'):
            if output.type() == 'message' and output.attrName() == '_dgCaller':
                nw = output.node()

                if nw.attr('_dgMethod')() == f.__name__:
                    def conformHandler(instance, *_):
                        if isinstance(instance, str):
                            mt = re.match(r"^\$([0-9])$", instance)
                            if mt:
                                slot = nw.attr('_dgMessage')[int(mt.group(1))]
                                inp = next(slot.iterInputs(plugs=True))
                                if inp.type() == 'message':
                                    return inp.node()
                                return inp
                        raise TypeError

                    try:
                        nwParamNames = ast.literal_eval(nw.attr('_dgParams')())

                        if set(nwParamNames) == set(receivedParamNames):
                            for (paramName,
                                 receivedValue) in receivedParams.items():
                                nwParamSlot = nw.attr(f'_dgParam{paramName}')
                                nwParamContent = ast.literal_eval(
                                    nwParamSlot()
                                )
                                hint = hints.get(paramName, UNDEFINED)

                                if hint is not UNDEFINED:
                                    nwParamContent = conform_instance(
                                        nwParamContent,
                                        hint,
                                        False,
                                        True,
                                        conformHandler
                                    )

                                if nwParamContent != receivedValue:
                                    raise _SkipNetworkError
                        else:
                            continue

                        # If we're still here, it's a match
                        nwOutputAttr = nw.attr('_dgOutput')
                        nwOutputContent = ast.literal_eval(nwOutputAttr())
                        hint = hints.get('return', UNDEFINED)

                        if hint is not UNDEFINED:
                            output = conform_instance(nwOutputContent,
                                                      hint,
                                                      False,
                                                      True,
                                                      conformHandler)
                        return output

                    except _SkipNetworkError:
                        continue

        result = f(self, *args, **kwargs)
        hint = hints.get('return', UNDEFINED)

        if hint is not UNDEFINED:
            result = conform_instance(result, hint, False, True)

        nw = nodes['Network'].createNode()
        nw.addAttr('_dgCaller', at='message', i=self, l=True)
        nw.addAttr('_dgMethod', dt='string').set(f.__name__).lock()
        nw.addAttr('_dgMessage', at='message', multi=True)
        nw.addAttr('_dgParams', dt='string').set(repr(receivedParamNames))

        msgIndex = {'index': 0}

        def handler(item):
            if isinstance(item, (om.MVector,
                                 om.MMatrix,
                                 om.MQuaternion,
                                 om.MEulerRotation)):
                return list(item)

            if isinstance(item, om.MPoint):
                return list(item)[:-3]

            if isinstance(item, plugs['Attribute']):
                out = '${}'.format(msgIndex['index'])
                item >> nw.attr('_dgMessage')[msgIndex['index']]
                msgIndex['index'] += 1
                return out

            elif isinstance(item, nodes['DependNode']):
                out = '${}'.format(msgIndex['index'])
                item.attr('message') >> nw.attr('_dgMessage')[msgIndex['index']]
                msgIndex['index'] += 1
                return out

            raise TypeError

        _result = simplify(result, handler)
        nw.addAttr('_dgOutput', dt='string').set(repr(_result)).lock()

        for paramName, paramValue in receivedParams.items():
            nw.addAttr(f'_dgParam{paramName}', dt='string').set(
                repr(simplify(paramValue, handler))
            ).lock()

        return result

    shorthands = get_shorthands(f)

    if shorthands:
        wrapper = short(**shorthands)(wrapper)

    return wrapper