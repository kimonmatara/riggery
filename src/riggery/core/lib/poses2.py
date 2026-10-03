from typing import Optional, Union
import json
from pathlib import Path
import os
from unittest import skip

from ..nodetypes import __pool__ as _nodes
from ..plugtypes import __pool__ as _plugs
from ..lib import namespaces as _ns

from .serialize import simplify

from riggery.general.iterables import without_duplicates, expand_tuples_lists
from riggery.general.functions import short

import maya.cmds as m

class MissingControlError(Exception):...

def getControlState(control) -> dict:
    """:return: Information on the control's state, in a dict."""
    out = []

    control = _nodes['DependNode'](control)
    _control = str(control)
    attrsOfInterest = m.listAttr(control, write=True)
    _attrsOfInterest = []

    for attrName in attrsOfInterest:
        attrPath = f"{_control}.{attrName}"

        try:
            keyable = m.getAttr(attrPath, k=True)
        except:
            continue

        if keyable:
            include = True
        else:
            include = m.getAttr(attrPath, cb=True)

        if include:
            attr = _plugs['Attribute'](attrPath)
            if attr.isMulti() or attr.isCompound():
                continue

            _attrsOfInterest.append(attr)

    return {attr.attrName(longName=True): simplify(attr())
            for attr in _attrsOfInterest}

def setControlState(control:Union[str, 'nodes.DependNode'], state:dict) -> bool:
    control = _nodes['DependNode'](control)

    edited = False

    for attrName, attrValue in state.items():
        try:
            attr = control.attr(attrName)
        except AttributeError:
            continue

        try:
            attr.set(attrValue)
            edited = True
        except:
            continue

    return edited

def capturePose(name:str, *controls):
    controls = list(without_duplicates(map(_nodes['DependNode'], expand_tuples_lists(*controls))))

    if not controls:
        raise ValueError("no controls")

    return {'name': name,
            'controls': {control.shortName(stripNamespace=True): getControlState(control)
                         for control in controls}}

def applyPose(pose:dict,
              *sceneControls,
              namespace:str=':',
              skipMissing:bool=False):
    """
    :param pose: the pose to apply
    :param sceneControls: if these are provided, *namespace* will be ignored and
        controls will be matched by short name
    :param namespace/ns: ignored if *sceneControls* are provided; a mapping
        namepace; defaults to ':' (root)
    :param skipMissing/sm: skip controls that can't be found instead of
        raising MissingControlError
    :raises MissingControlError:
    """
    DependNode = _nodes['DependNode']

    sceneControlsMap = None

    if sceneControls:
        sceneControls = without_duplicates(
            map(r.Elem, expand_tuples_lists(*sceneControls))
        )

        sceneControlsMap = {c.shortName(sns=True): c for c in sceneControls}

    namespace = _ns.Namespace(namespace)

    for controlBasename, controlState in pose.get('controls', {}).items():
        if sceneControlsMap is not None:
            try:
                control = sceneControlsMap[controlBasename]
            except KeyError:
                continue

        else:
            actualControlName = namespace.concat(controlBasename)

            if m.objExists(actualControlName):
                control = DependNode(actualControlName)
            else:
                if skipMissing:
                    continue
                else:
                    raise MissingControlError(actualControlName)

        setControlState(control, controlState)

def loadPose(filepath:str|Path) -> dict:
    filepath = Path(filepath)

    with open(filepath, 'r', encoding='utf-8') as f:
        data = f.read()

    out = json.loads(data)
    print("Read pose '{}' from {}".format(out['name'], filepath))
    return out

def dumpPose(pose:dict, filepath:str|Path) -> Path:
    data = json.dumps(pose, indent=4)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(data)

    print("Wrote pose '{}' to: {}".format(pose['name'], filepath))