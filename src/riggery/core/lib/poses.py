"""
General tools for managing rig poses.
"""

import json
from pathlib import Path
from typing import Optional, Union
from .names import CONTROLSUFFIX
from .namespaces import Namespace
from .serialize import simplify

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs

from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short


import maya.cmds as m

def _withNamespace(shortName:str,
                   namespace:str) -> str:
    namespace = Namespace(namespace)
    shortName = shortName.split(':')[-1]
    if namespace.isRoot():
        return ':' + shortName
    return ':'.join((namespace, shortName))

def _hasNamespace(node:str, namespace:str) -> bool:
    elems = str(node).split('|')[-1].split(':')[:-1]
    thisNamespace = ':'.join(elems)

    if not thisNamespace:
        thisNamespace = ':'

    return Namespace(namespace) == Namespace(thisNamespace)

@short(filterNamespace='fns',
       collectWithTypeSuffix='cts',
       collectWithControllerTag='cct')
def getControls(
        *controls,
        filterNamespace:Optional[str]=None,
        collectWithTypeSuffix:Optional[str]=CONTROLSUFFIX,
        collectWithControllerTag:bool=True
) -> list['nodes.DependNode']:
    """
    :param \*controls: if any controls are provided, they will be conformed to
        instances and passed-through, with all other arguments ignored
    :param collectWithTypeSuffix/cts: collect nodes with this type suffix;
        defaults to :attr:`~riggery.core.lib.names.CONTROLSUFFIX`
    :param collectWithControllerTag/cct: collect nodes with controller tags;
        defaults to True
    :param filterNamespace/fns: if provided, will be used to filter anything
        collected using suffixes and / or control tags by the namespace;
        defaults to None (ignore namespaces)
    :return: The resolved control worklist.
    """
    if controls:
        controls = expand_tuples_lists(*controls)
        controls = map(nodes['DependNode'], controls)
        return list(without_duplicates(controls))

    if filterNamespace:
        filterNamespace = Namespace(filterNamespace)

    if collectWithTypeSuffix:
        if collectWithTypeSuffix.startswith('_'):
            collectWithTypeSuffix = collectWithTypeSuffix[1:]

    out = []

    if collectWithTypeSuffix:
        kwargs = {}
        lsLookups = [collectWithTypeSuffix, f'*_{collectWithTypeSuffix}']

        if filterNamespace:
            if filterNamespace.isRoot():
                lsLookups = [':' + lookup for lookup in lsLookups]
            else:
                lsLookups = ['{}:{}'.format(filterNamespace, lookup)
                             for lookup in lsLookups]
        else:
            kwargs['r'] = True

        for lookup in lsLookups:
            out += m.ls(lookup, type='transform', **kwargs)

    if collectWithControllerTag:
        allControllers = m.controller(q=True, ac=True)

        if allControllers:
            if filterNamespace:
                out += list(filter(
                    lambda x: _hasNamespace(x, filterNamespace),
                    allControllers
                ))
            else:
                out += allControllers

    return list(map(nodes['DependNode'], without_duplicates(out)))

def getControlState(control) -> dict:
    out = []

    control = nodes['DependNode'](control)
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
            attr = plugs['Attribute'](attrPath)
            if attr.isMulti() or attr.isCompound():
                continue

            _attrsOfInterest.append(attr)

    return {attr.attrName(longName=True): simplify(attr())
            for attr in _attrsOfInterest}

def setControlState(control:Union[str, 'nodes.DependNode'], state:dict) -> bool:
    control = nodes['DependNode'](control)

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

@short(filterNamespace='fns',
       collectWithTypeSuffix='cts',
       collectWithControllerTag='cct')
def capturePose(
        name:str,
        *controls,
        filterNamespace:Optional[str]=None,
        collectWithTypeSuffix:Optional[str]=CONTROLSUFFIX,
        collectWithControllerTag:bool=True
) -> dict:
    """
    :param name: the name of the new pose
    :param \*controls: if any controls are provided, they will be conformed to
        instances and passed-through, with all other arguments ignored
    :param collectWithTypeSuffix/cts: collect nodes with this type suffix;
        defaults to :attr:`~riggery.core.lib.names.CONTROLSUFFIX`
    :param collectWithControllerTag/cct: collect nodes with controller tags;
        defaults to True
    :param filterNamespace/fns: if provided, will be used to filter anything
        collected using suffixes and / or control tags by the namespace;
        defaults to None (ignore namespaces)
    :return: The pose dictionary.
    """
    controls = getControls(*controls,
                           filterNamespace=filterNamespace,
                           collectWithTypeSuffix=collectWithTypeSuffix,
                           collectWithControllerTag=collectWithControllerTag)

    return {'name': name,
            'controls':[(control.shortName(),  getControlState(control))
                        for control in controls]}

@short(forceNamespace='fns')
def applyPose(pose:dict,
              *filterControls,
              forceNamespace:Optional[str]=None,
              quiet:bool=False) -> int:
    """
    :param pose: the type of dictionary generated by :meth:`capturePose`
    :param \*filterControls: only modify these controls (if matches are found)
    :param forceNamespace/fns: remap any namespace in the *pose* dict to this
        namespace; defaults to None (no remapping)
    :return: The number of controls that were modified.
    """
    count = 0

    if filterControls:
        filterControls = set(
            map(nodes['DependNode'], expand_tuples_lists(*filterControls))
        )

    if forceNamespace:
        forceNamespace = Namespace(forceNamespace)

    for controlName, controlState in pose.get('controls', []):
        if forceNamespace:
            controlName = _withNamespace(controlName, forceNamespace)

        matches = m.ls(controlName)

        if len(matches) == 1:
            control = nodes['DependNode'](matches[0])

            if filterControls and control not in filterControls:
                continue

            modified = setControlState(matches[0], controlState)
        else:
            if not quiet:
                m.warning(f"No unambiguous matches for control '{controlName}'")
            continue

        if modified:
            count += 1

    if not quiet:
        print("Applied pose '{}' to {} control(s).".format(pose['name'], count))

    return count

@short(title='t')
def dumpPose(pose:dict, filePath:str):
    """
    :param pose: the type of dictionary generated by :meth:`capturePose`
    :param filePath: the file into which to write the pose
    """
    filePath = Path(filePath)

    data = json.dumps(pose, indent=4)

    with open(filePath, 'w', encoding='utf-8') as f:
        f.write(data)

    print("Dumped pose '{}' into: {}".format(pose['name'], filePath))

def loadPose(filePath:str) -> dict:
    """
    :param filePath: the file from which to read the pose
    :return: The pose dictionary.
    """
    filePath = Path(filePath)

    with open(filePath, 'r', encoding='utf-8') as f:
        pose = f.read()

    out = json.loads(pose)
    print("Loaded pose '{}' from: {}".format(pose['name'], filePath))
    return out