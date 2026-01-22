import re
import maya.cmds as m
import maya.api.OpenMaya as om

from .. import str2api as _s2a
from .parseaac import parseAddAttrCmd
from riggery.general.reorder import bunched_partial_reorder, Reorder as _Reorder
from riggery.general.iterables import issublist

#---------------------------------|    Attr inspections

def getBaseAttr(fullPath):
    if m.addAttr(fullPath, q=True, usedAsProxy=True):
        inp = m.connectionInfo(fullPath, sfd=True)
        if inp:
            return inp
    return fullPath

def conformToLongName(node, attr) -> str:
    return m.attributeQuery(attr, node=node, longName=True)

def attrIsMulti(node, attr):
    m.attributeQuery(attr, node=node, multi=True)

def attrIsCompound(node, attr):
    typ = m.getAttr(f"{node}.{attr}", type=True)

    if typ is None:
        return False

    return bool(re.match(
        r"^(?:compound|reflectance|spectrum|(?:float|double|long|short)[1-3])$",
        typ
    ))

def getReorderableAttrs(node:str) -> list[str]:
    worklist = m.listAttr(node, userDefined=True)

    out = []

    if worklist:
        # Remove compounds and their children
        compoundAttrs = [x for x in worklist if attrIsCompound(node, x)]
        compoundMembers = []

        for attr in compoundAttrs:
            children = m.attributeQuery(attr,
                                        node=node,
                                        listChildren=True,
                                        longName=True)

            if children:
                compoundMembers += children

        worklist = [x for x in worklist
                    if x not in compoundAttrs + compoundMembers]

        # Remove multi attrs
        worklist = [x for x in worklist if not attrIsMulti(node, x)]

        # Remove attributes which are neither keyable nor channelbox
        out = [x for x in worklist if m.getAttr(f'{node}.{x}', k=True)
               or m.getAttr(f'{node}.{x}', cb=True)]

    return out

def getAddAttrCmd(node, attr):
    mPlug = _s2a.getMPlug(f"{node}.{attr}")
    mObj = mPlug.attribute()
    return om.MFnAttribute(mObj).getAddAttrCmd(True)

def getInput(node, attr, disconnect:bool=False) -> str:
    fullPath = f'{node}.{attr}'
    input = m.connectionInfo(fullPath, sfd=True)

    if input:
        if disconnect:
            thisState = pushUnlock(fullPath)
            inputState = pushUnlock(input)

            m.disconnectAttr(input, fullPath)

            popUnlock(thisState)
            popUnlock(inputState)

    return input

def getOutputs(node, attr, disconnect:bool=False) -> list[str]:
    fullPath = f'{node}.{attr}'
    outputs = m.connectionInfo(fullPath, dfs=True)

    if outputs:
        if disconnect:
            thisState = pushUnlock(fullPath)

            for output in outputs:
                outputState = pushUnlock(output)
                m.disconnectAttr(fullPath, output)
                popUnlock(outputState)

            popUnlock(thisState)
        return outputs
    return []

def getConnections(node, attr, disconnect:bool=False) -> dict:
    out = {}
    input = getInput(node, attr, disconnect=disconnect)

    if input:
        out['input'] = input
    outputs = getOutputs(node, attr, disconnect=disconnect)

    if outputs:
        out['outputs'] = outputs

    return out

def recreateConnections(node, attr, connectionInfo:dict):
    if connectionInfo:
        fullPath = f'{node}.{attr}'
        thisState = pushUnlock(fullPath)

        input = connectionInfo.get('input')

        if input:
            inputState = pushUnlock(input)
            m.connectAttr(input, fullPath)
            popUnlock(inputState)

        outputs = connectionInfo.get('outputs')

        if outputs:
            for output in outputs:
                outputState = pushUnlock(output)
                m.connectAttr(fullPath, output)
                popUnlock(outputState)

        popUnlock(thisState)

#---------------------------------|    Lock management

def pushUnlock(fullAttrPath:str):
    isLocked = m.getAttr(fullAttrPath, l=True)

    if isLocked:
        m.setAttr(fullAttrPath, l=False)

    return (fullAttrPath, isLocked)

def popUnlock(lockState:tuple):
    m.setAttr(lockState[0], l=lockState[1])

#---------------------------------|    Section management

def attrIsSection(node, attr) -> bool:
    if m.getAttr(f'{node}.{attr}', l=True):
        if m.getAttr(f'{node}.{attr}', type=True) == 'enum':
            if m.addAttr(f'{node}.{attr}', q=True, enumName=True) == ' ':
                return True
    return False

def getSectionMembers(node:str, section:str):
    attrs = getReorderableAttrs(node)
    sectionIndex = attrs.index(section)
    attrsBelow = attrs[sectionIndex+1:]

    out = []

    for attr in attrsBelow:
        if attrIsSection(node, attr):
            break
        out.append(attr)

    return out

def getSectionNames(node:str) -> list[str]:
    return [attr for attr in getReorderableAttrs(node)
            if attrIsSection(node, attr)]

def hasSection(node:str, sectionName:str):
    return sectionName in getSectionNames(node)

def getSectionMap(node) -> dict[str:list[str]]:
    return {k: getSectionMembers(node, k) for k in getSectionNames(node)}

def createSection(node, sectionName:str):
    m.addAttr(node, ln=sectionName, at='enum', k=False, enumName=' ')
    fullPath = f'{node}.{sectionName}'
    m.setAttr(fullPath, cb=True)
    m.setAttr(fullPath, l=True)

def collectIntoSection(node:str, sectionName:str, memberNames:list[str],
                       atTop:bool=False, force:bool=False):
    existingMembers = getSectionMembers(node, sectionName)
    newMembers = [conformToLongName(node, x) for x in memberNames]

    if force:
        existingMembers = [x for x in existingMembers if x not in newMembers]
        _newMembers = newMembers[:]
    else:
        _newMembers = [x for x in newMembers if x not in existingMembers]

    if _newMembers:
        if atTop:
            rebuildList = [sectionName] + _newMembers + existingMembers
        else:
            rebuildList = [sectionName] + existingMembers + _newMembers

        reorder(node, rebuildList, expandSections=True)

def removeSection(node:str, sectionName:str):
    if hasSection(node, sectionName):
        fullPath = f'{node}.{sectionName}'
        m.setAttr(fullPath, l=False)
        m.deleteAttr(fullPath)
    else:
        raise AttributeError("section doesn't exist")

#---------------------------------|    Macro

def getAttrMacro(node, attr, disconnect:bool=False) -> dict:

    fullPath = f'{node}.{attr}'

    out = {'attr': attr}
    out['addAttrKwargs'] = parseAddAttrCmd(getAddAttrCmd(node, attr))

    out['isLocked'] = m.getAttr(fullPath, l=True)
    out['isKeyable'] = m.getAttr(fullPath, k=True)
    out['isChannelBox'] = m.getAttr(fullPath, cb=True)

    connections = getConnections(node, attr, disconnect=disconnect)

    if connections:
        out['connections'] = connections

    return out

#---------------------------------|    Deletion / recreation

def deleteAttr(node, attr) -> None:
    fullPath = f'{node}.{attr}'
    m.setAttr(fullPath, l=False)
    m.deleteAttr(fullPath)

def recreateAttr(node, macro) -> None:
    m.addAttr(node, **macro['addAttrKwargs'])
    connections = macro.get('connections')

    if connections:
        recreateConnections(node, macro['attr'], connections)

    fullPath = f'{node}.{macro["attr"]}'
    
    m.setAttr(fullPath, keyable=False)
    m.setAttr(fullPath, channelBox=False)
    
    if macro['isKeyable']:
        m.setAttr(fullPath, keyable=True)

    elif macro['isChannelBox']:
        m.setAttr(fullPath, channelBox=True)

    if macro['isLocked']:
        m.setAttr(fullPath, l=True)

#---------------------------------|    Reorder

def reorder(node:str, attrs:list[str], expandSections:bool=False):
    attrs = [conformToLongName(node, x) for x in attrs]

    if expandSections:
        _attrs = []

        sectionMap = getSectionMap(node)
        mentionedSections = set(attrs).intersection(set(sectionMap))

        # Re-impose preferred ordering
        
        for k in mentionedSections:
            members = sectionMap[k]
            reference = [x for x in attrs if x in members]

            if reference:
                sectionMap[k] = bunched_partial_reorder(members, reference)
            
        for attr in attrs:
            if attr in sectionMap:
                # If this is a section, expand it and add to list
                _attrs.append(attr)
                _attrs += sectionMap[attr]
            else:
                # Not a section. If it's a member of the mentioned sections,
                # omit it; otherwise, include it

                if any((attr in sectionMap[k] for k in mentionedSections)):
                    continue

                _attrs.append(attr)

        attrs = _attrs

    reorderableAttrs = list(getReorderableAttrs(node))

    if issublist(attrs, reorderableAttrs):
        # Nothing to do, already in-order
        return

    macros = [getAttrMacro(node, attr, disconnect=True) for attr in attrs]

    for attr in attrs:
        deleteAttr(node, attr)

    for macro in macros:
        recreateAttr(node, macro)

def shiftMulti(node:str,
               attrsToMove:list[str],
               offset:int, *,
               expandSections:bool=False,
               roll:bool=False) -> None:
    """
    Shifts multiple attributes up or down in the Channel Box.
    """
    attrsToMove = [conformToLongName(node, attr) for attr in attrsToMove]
    allNames = _Reorder(getReorderableAttrs(node))
    allNames.shift(attrsToMove, offset, roll)
    reorder(node, allNames, expandSections=expandSections)

def sendToTop(node:str,
              attrsToMove:list[str],
              expandSections:bool=False) -> None:
    attrsToMove = [conformToLongName(node, x) for x in attrsToMove]

    allNames = [x for x in getReorderableAttrs(node)
                if x not in attrsToMove]

    reorderList = attrsToMove + allNames
    reorder(node, reorderList, expandSections=expandSections)