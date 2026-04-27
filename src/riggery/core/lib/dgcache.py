import re
import ast
from typing import get_type_hints, Union, Optional, Iterator
from types import FunctionType
from functools import wraps
import inspect

from .mixedmode import isPlug
from riggery.general.types import UNDEFINED, conform_instance
from ..elem import Elem
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from .serialize import simplify
from .names import TYPESUFFIXES

class NoCachedResultError(RuntimeError):
    ...

class DGCache:
    """Used by the :func:`dgcache` decorator."""

    #---------------------------------|    Construction

    @classmethod
    def _initNode(cls, name:Optional[str]=None):
        node = nodes['Network'].createNode(name=name)

        node.addAttr('dgref', at='compound', multi=True, nc=2)
        node.addAttr('reftarget', at='message', parent='dgref')
        node.addAttr('refismultiroot', at='bool', parent='dgref')

        node.addAttr('dgcache', at='compound', multi=True, nc=2)
        node.addAttr('dgkey', dt='string', parent='dgcache')
        node.addAttr('dgresult', dt='string', parent='dgcache')

        return node

    @classmethod
    def create(cls, name:Optional[str]=None):
        return cls(cls._initNode(name=name))

    #---------------------------------|    Init

    def __init__(self, networkNode):
        self._node = nodes['DependNode'](networkNode)

    #---------------------------------|    Properties

    def node(self):
        return self._node

    @property
    def attr(self):
        return self._node.attr

    #---------------------------------|    Add to cache

    def __setitem__(self, key:str, value):
        slot = next((x for x in self.attr('dgcache')
                     if x.attr('dgkey')() == key), None)

        if slot is None:
            slot = self.attr('dgcache').nextElement()
            slot.attr('dgkey').set(key)

        slot.attr('dgresult').set(repr(self._simplify(value)))

    #---------------------------------|    Retrieve from cache

    def retrieve(self, key:str, typeHint=UNDEFINED, /):
        for slot in self.attr('dgcache'):
            if slot.attr('dgkey')() == key:
                _out = slot.attr('dgresult')()
                out = self._actualize(_out)

                if typeHint is not UNDEFINED:
                    try:
                        conformed = conform_instance(out, typeHint)
                        return conformed
                    except TypeError:
                        raise TypeError(
                            f"dgcache: could not cast to hinted return type"
                        )
                return out
        raise NoCachedResultError()

    #---------------------------------|    DG refs

    def getRefFromSlot(self, slot:'plugs.Attribute'):
        inp = next(slot.attr('reftarget').iterInputs(plugs=True), None)

        if inp is not None:
            if slot.attr('refismultiroot')():
                inp = inp.toMulti()

            elif isinstance(inp, plugs['Message']):
                return inp.node()

            return inp

    def getRef(self, index:int):
        if index in self.attr('dgref').indices():
            return self.getRefFromSlot(self.attr('dgref')[index])

    def iterRefs(self) -> Iterator[tuple[int, 'Elem']]:
        for slot in self.attr('dgref'):
            ref = self.getRefFromSlot(slot)

            if ref is not None:
                yield slot.index(), ref

    def findRefIndex(self, item:'Elem') -> Optional[int]:
        try:
            item = Elem(item)
        except:
            return None

        for i, ref in self.iterRefs():
            if ref == item:
                return i

    #---------------------------------|    Serialize

    def _simplify(self, value):
        if isinstance(value, str):
            try:
                value = Elem(value)
            except:
                return value

        if isinstance(value, Elem):
            index = self.findRefIndex(value)

            if index is None:
                index = self.attr('dgref').nextIndex()
                slot = self.attr('dgref')[index]

                if isinstance(value, nodes['DependNode']):
                    value.attr('message') >> slot.attr('reftarget')
                else:
                    value >> slot.attr('reftarget')

                    if value.isMulti():
                        slot.attr('refismultiroot').set(True)

            return f'<dg ref {index}>'

        return simplify(value)

    #---------------------------------|    Deserialize

    def _actualize(self, val:str):
        val = ast.literal_eval(val)

        if isinstance(val, str):
            mt = re.match(r"^\<dg ref ([0-9]+)\>$", val)

            if mt:
                index = int(mt.group(1))
                ref = self.getRef(index)

                if ref is None:
                    raise NoCachedResultError

                return ref

        return val

    #---------------------------------|    Key wrangling

    def constructKey(self, f:FunctionType, _self, *args, **kwargs):
        """
        format: [
            <funcName>:str,
            [(argName, argValue), ...]
        ]
        """
        paramEntries = []

        signature = inspect.signature(f)
        args = signature.bind(*((_self,) + args), **kwargs)

        for argName, argValue in list(args.arguments.items())[1:]:
            paramEntries.append((argName, self._simplify(argValue)))

        return repr([f.__name__, paramEntries])

    #---------------------------------|    Repr

    def __repr__(self):
        return "<DG cache instance>"

def resultIsCachable(result) -> bool:
    if isinstance(result, (tuple, list)):
        return any((resultIsCachable(x) for x in result))
    try:
        return isPlug(result)
    except:
        pass

    return False

def dgcache(f):
    """
    Decorator, for use on instance methods of plugs or nodes. Caches output
    results, but only if they comprise plugs, or lists or tuples which contain
    plugs.
    """
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        typeHints = get_type_hints(f)

        if 'return' not in typeHints:
            raise TypeError("dgcache: the return type must be hinted")

        if isinstance(self, plugs['Attribute']):
            owner = self.node()
        elif isinstance(self, nodes['DependNode']):
            owner = self
        else:
            raise TypeError("expected DependNode or Attribute")

        cacheNode = owner.tags.get('_dg_cache', None)
        key = None

        if cacheNode is None:
            cache = None
        else:
            cache = DGCache(cacheNode)
            key = cache.constructKey(f, self, *args, **kwargs)

            try:
                return cache.retrieve(key,
                                      typeHints.get('return', UNDEFINED))
            except NoCachedResultError:
                pass

        result = f(self, *args, **kwargs)

        if resultIsCachable(result):
            if cache is None:
                name = "{}_dgcache_{}".format(owner.shortName(sts=True),
                                              TYPESUFFIXES['network'])
                cache = DGCache.create(name)
                owner.tags['_dg_cache'] = cache.node()
                newCache = True

            if key is None:
                key = cache.constructKey(f, self, *args, **kwargs)

            cache[key] = result

        return result
    return wrapper