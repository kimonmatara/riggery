from typing import Union
import maya.api.OpenMaya as om

def select(
        item:Union[
            str, # pattern match
            om.MDagPath, # DAG node
            om.MObject, # anything
            tuple[om.MDagPath, om.MObject] # component
        ],
        add:bool=False,
        searchChildNamespaces=False) -> om.MSelectionList:
    sel = om.MSelectionList()
    sel.add(item)
    mode = om.MGlobal.kAddToList if add else om.MGlobal.kReplaceList
    om.MGlobal.setActiveSelectionList(sel, mode)
    return sel