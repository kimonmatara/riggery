"""Tools to manage Maya names."""
import json
import os
import re
from typing import Optional, Union
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
import riggery.internal.nttags as _ntt

#--------------------------------------|
#--------------------------------------|    SUFFIXES
#--------------------------------------|

def _loadTypeSuffixes() -> dict:
    path = os.path.join(os.path.dirname(__file__), 'ntsuffixes.json')
    with open(path, 'r') as f:
        return json.load(f)

def _dumpTypeSuffixes(data:dict):
    path = os.path.join(os.path.dirname(__file__), 'ntsuffixes.json')
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def looksLikeTypeSuffix(s:str) -> bool:
    """
    :param s: the string to inspect
    :return: True if *s* looks like a type suffix, e.g. 'XFRM'.
    """
    return s.isupper() or s in TYPESUFFIXES

def _updateTypeSuffixes(overwrite:bool=False):
    """
    Downloads node type tags from the online Maya help, and inserts any missing
    entries to ``ntsuffixes.json``.

    :param overwrite: overwrite entries already in the file; defaults to False
    """
    suffcache = _loadTypeSuffixes()
    downloaded = _ntt.download()

    if not overwrite:
        downloaded = {k:v for k, v in downloaded.items() if k not in suffcache}

    suffcache.update(downloaded)
    _dumpTypeSuffixes(suffcache)

    global TYPESUFFIXES
    TYPESUFFIXES = suffcache

    print("Updated node type suffixes.")

TYPESUFFIXES = None
CONTROLSUFFIX = 'CTRL'

#--------------------------------------|
#--------------------------------------|    NAME CONSTRUCTION
#--------------------------------------|

@short(allowEmpty='ae')
def legalise(name:str, allowEmpty:bool=False) -> str:
    """
    Legalises a Maya node name.

    :param name: the name to legalise
    :param allowEmpty/ae: if, after legalisation, all that remains is an empty
        string, return it instead of defaulting to '_'; defaults to False
    :return: The legalised Maya node name.
    """
    # Strip white space and illegal characters from start and end
    pat = r"((?<=^)[^a-zA-Z_0-9]+)|([^a-zA-Z_0-9]+(?=$))"
    name = re.sub(pat, '', name)

    # Replace all remaining illegal characters with merged underscores
    pat = r"[^a-zA-Z_0-9]+"
    name = re.sub(pat, '_', name)

    # If leading digit, add underscore
    pat = r"^[0-9].*$"
    if re.match(pat, name):
        name = '_'+name

    if name == '':
        if allowEmpty:
            return name
        return '_'

    return name

def conformElems(*elems, pad:Optional[int]=None) -> list[str]:
    """
    :param elems: the name elements to conform
    :param pad: padding for integers; defaults to None
    :return: The cleaned-up name elements.
    """
    out = []

    for elem in expand_tuples_lists(*elems):
        if elem is None:
            continue
        if isinstance(elem, int):
            elem = str(elem)
            if pad:
                elem = elem.zfill(pad)
        else:
            elem = str(elem)
        if elem:
            out.append(elem)

    return out


class Name:

    __depth__ = 0
    __elems__ = []
    __pad__ = None

    def __init__(self,
                 *elems,
                 override:bool=False,
                 pad:Optional[int]=None):
        """
        Contributes name prefixes to the current block.

        :param elems: the prefix elements to contribute
        :param override/o: override previous elements instead of appending to
            them; defaults to False
        :param pad: padding for integers; defaults to None
        """
        self._elems = conformElems(*elems,
                                   pad=Name.__pad__ if pad is None else pad)
        self._override = override
        self._pad = pad

    def __enter__(self):
        self._old_elems = Name.__elems__[:]

        if self._override:
            Name.__elems__[:] = self._elems
        else:
            Name.__elems__ += self._elems

        Name.__depth__ += 1

        if self._pad is not None:
            self._old_pad = Name.__pad__
            Name.__pad__ = self._pad

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        Name.__elems__[:] = self._old_elems

        if self._pad is not None:
            Name.__pad__ = self._old_pad

        Name.__depth__ -= 0

        return False

    @classmethod
    @short(nodeType='nt', asControl='ac', typeSuffix='ts')
    def evaluate(cls,
                 *additionalElems,
                 typeSuffix=None,
                 nodeType=None,
                 asControl=False) -> str:
        """
        Connects all avaiable elements into a string. The string may be empty
        if there are no elements.

        :param \*additionalElems: any additional elements to add to the end of
            the block; defaults to []
        :param typeSuffix/ts: an explicit type suffix to use; if provided,
            *nodeType* and *asControl* will be ignored; defaults to None
        :param nodeType/nt: a node type to use for a suffix lookup; defaults
            to None
        :param asControl/ac: ignore *nodeType* and append the suffix for rig
            controls; defaults to False
        :return: The assembled name.
        """
        elems = conformElems(expand_tuples_lists(*additionalElems))
        if cls.__elems__:
            elems = cls.__elems__ + elems

        if typeSuffix:
            elems.append(typeSuffix)
        elif asControl:
            elems.append(CONTROLSUFFIX)
        elif nodeType is not None:
            try:
                elems.append(TYPESUFFIXES[nodeType])
            except KeyError:
                pass

        return legalise('_'.join(elems), allowEmpty=True)

@short(typeSuffix='ts',
       nodeType='nt',
       asControl='ac')
def resolveNameArg(nameArg:Union[str, None], *,
                   typeSuffix:Optional[str]=None,
                   nodeType:Optional[str]=None,
                   asControl:bool=False) -> Optional[str]:
    """
    For use inside constructors, which will use *name* verbatim if provided,
    or fall back to Name blocks otherwise.

    :param nameArg: the name argument received by the constructor
    :param asControl/ac: if provided, overrides *typeSuffix* to ``CTRL``;
        defaults to False
    :param typeSuffix/ts: an optional type suffix override, e.g. 'XFRM';
        defaults to None
    :param nodeType/nt: ignored if *typeSuffix* was provided; a node type
        key for a type suffix lookup; defaults to None
    """
    if nameArg:
        return nameArg

    if Name.__elems__:
        out = Name.evaluate(typeSuffix=typeSuffix,
                            nodeType=nodeType,
                            asControl=asControl)
        if out:
            return out

SIDE_EXTRACT = re.compile(r"^([LR])(?:$|_(.*)$)")

def extractSide(s:str, asString:bool=False) -> Optional[Union[int, str]]:
    """
    :param s: a name string; namespaces will be inspected, but DAG information
        will be discarded
    :param asString: return the extracted side, rather than the index
        representation; defaults to False
    :return: If *asString*: 'L', 'R' or None; otherwise, 1 for left (blue), -1
        for right (red), or None.
    """
    s = str(s).split('|')[-1].strip(':')
    elems = s.split(':')
    for elem in reversed(elems):
        mt = re.match(SIDE_EXTRACT, elem)
        if mt:
            side = mt.groups()[0]
            if asString:
                return side
            return sideStrToInt(side)

def sideIntToStr(side:int) -> Optional[str]:
    """
    :return: If *side* is 1, returns 'L'; otherwise if it's -1; returns 'R';
        otherwise returns None.
    """
    return {1:'L', -1:'R'}.get(side)

def sideStrToInt(side:str) -> Optional[int]:
    """
    :return: If *side* is 'L', returns 1; otherwise, if it's 'R'; returns -1;
        otherwise returns None.
    """
    return {'L': 1, 'R': -1}.get(side)

def splitSide(s:str) -> Optional[tuple[str, str]]:
    """
    If *s* is a string that starts with 'L_' or 'R_', or the string itself
    is 'L' or 'R', returns a tuple with two elements; the first will be the
    side, and the second will be the basename, which might be an empty string.

    Failing all the above, returns None.
    """
    mt = re.match(SIDE_EXTRACT, s)
    if mt:
        elems = mt.groups()
        if elems[1] is None:
            elems[1] = ''
        return tuple(elems)

#--------------------------------------|
#--------------------------------------|    STARTUP
#--------------------------------------|

def _startup():
    global TYPESUFFIXES
    TYPESUFFIXES = _loadTypeSuffixes()

_startup()