"""
Retrieves (from an adjacent cache file) or regenerates a dictionary with
three keys, 'node', 'plug' and 'data'. The values are themselves dictionaries
of ``apiType: [MFnBase subclass, MFnBase subclass...]``, representing the
most-specific available function sets for the given type.
"""
import json
import os

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.api.OpenMayaUI as omui
import maya.api.OpenMayaRender as omr

import maya.cmds as m

MODS = {'OpenMaya': om,
        'OpenMayaAnim': oma,
        'OpenMayaUI': omui,
        'OpenMayaRender': omr}

import maya.cmds as m
from . import typeutil as _tu

MFNMATCHES = {}

CACHE_FILE_NAME = os.path.splitext(os.path.basename(__file__))[0]+'.json'
CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), CACHE_FILE_NAME)

def _generateMFnMatches() -> dict:
    mFnTypes = _tu.get_subclasses_recursive(om.MFnBase)
    mFnEnums = {k: v for k, v in om.MFn.__dict__.items() if k.startswith('k')}

    out = {}

    for k, v in mFnEnums.items():
        matches = [T for T in mFnTypes if T().hasObj(v)]
        matches = _tu.collapse_ancestors(matches)
        if matches:
            out[v] = matches

    return out

def _clsToRepr(T:type) -> str:
    return f"{T.__module__}.{T.__name__}"

def _reprToCls(_t:str) -> type:
    modName, clsName = _t.split('.')

    try:
        return getattr(MODS[modName], clsName)
    except AttributeError:
        for k, v in MODS.items():
            if k == modName:
                continue
            try:
                return getattr(v, clsName)
            except:
                continue

    raise ValueError(
        f"Couldn't reconstitute class: {modName}.{clsName}"
    )

def _start():
    global MFNMATCHES
    try:
        with open(CACHE_FILE_PATH, 'r') as f:
            _MFNMATCHES = json.load(f)
        MFNMATCHES = {int(k): list(map(_reprToCls, v)) \
                      for k, v in _MFNMATCHES.items()}
    except FileNotFoundError:
        MFNMATCHES = _generateMFnMatches()
        _MFNMATCHES = {str(k): list(map(_clsToRepr, v)) \
                       for k, v in MFNMATCHES.items()}
        try:
            with open(CACHE_FILE_PATH, 'w') as f:
                json.dump(_MFNMATCHES, f, indent=4)
        except OSError as exc:
            m.warning(
                "Couldn't write cache file: "+
                f"{CACHE_FILE_PATH};\n{exc}"
            )

def fallbackInst(obj:om.MObject, fn:om.MFnBase) -> tuple[om.MFnBase, bool]:
    """
    Attempts to instantiate the function set of the specified type around the
    specified object. If instantiation fails, tries ancestor function sets.
    This is useful in situations where more specific, compatible function sets
    fail (e.g. in the case of :class:`~maya.api.OpenMaya.MFnMesh` with empty
    mesh objects).

    :param obj: the :class:`~maya.api.OpenMaya.MObject` around which to
        instantiate
    :param fn: the preferred :class:`~maya.api.OpenMaya.MFnBase` subclass
    :raises TypeError: Couldn't instantiate any function set.
    :return: A tuple of function set instance, and ``True`` if the preferred
        class was used, otherwise ``False``.
    """
    try:
        return fn(obj), True
    except:
        for T in fn.mro()[1:]:
            if T is om.MFnBase:
                break
            try:
                out = T(obj), False
                m.warning(
                    "Couldn't use preferred Fn "+
                    f"'{fn.__name__}', defaulting"+
                    f" to '{T.__name__}'"
                )
                return out
            except:
                continue

    raise TypeError(
        "Couldn't instantiate an MFn for the given object."
    )

_start()