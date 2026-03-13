from itertools import chain
from typing import Literal
import re

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates
import maya.cmds as m
from ..nodetypes import __pool__ as nodes

SUPPORTED_CAST_TYPES = {'vtx', 'e', 'f', 'map'}
MESH_COMP_CAST_PAT = re.compile(r"^.*?\.(vtx|e|f|uv)\[.*?\]$")

@short(expandMeshes='em', flatten='fl')
def castMeshComponent(
        component:str,
        preferredType:Literal[tuple(SUPPORTED_CAST_TYPES)],
        flatten:bool=False,
        expandMeshes:bool=False
) -> list[str]:
    """
    Expects a single component string (which could be a range), but always
    returns a list.

    :param component: the component to inspect / cast
    :param preferredType: the type to cast to; one of 'f', 'vtx', 'e', or 'map'
    :param flatten/fl: flatten any component ranges in the return list; defaults
        to False
    :param expandMeshes/em: if a mesh is passed-in instead of a component,
        return a full component instead of throwing :class:`TypeError`; defaults
        to False
    """
    if preferredType not in SUPPORTED_CAST_TYPES:
        raise ValueError(
            "expected 'vtx', 'e', 'f' or 'map': {}".format(preferredType)
        )

    mt = re.match(MESH_COMP_CAST_PAT, component)

    if mt:
        thisType = mt.group(1)

        if thisType in SUPPORTED_CAST_TYPES:
            if thisType == preferredType:
                return [component]

            kwargs = {{'vtx': 'fromVertex',
                       'e': 'fromEdge',
                       'f': 'fromFace',
                       'map': 'fromUV',
                       }[thisType]: True,
                      {'vtx': 'toVertex',
                       'e': 'toEdge',
                       'f': 'toFace',
                       'map': 'toUV',
                       }[preferredType]: True}

            out = m.polyListComponentConversion(component, **kwargs)

            if flatten:
                out = m.ls(out, flatten=True)

            return out
        else:
            raise TypeError(
                    "Not a mesh vertex, edge, face, UV or mesh: ", component
                )
    else:
        if expandMeshes:
            try:
                e = nodes['DagNode'](component)
            except:
                raise TypeError(
                    "Not a mesh vertex, edge, face, UV or mesh: ", component
                )

            try:
                e = e.toShape()
            except AttributeError:
                raise TypeError(
                    "Not a mesh vertex, edge, face, UV or mesh: ", component
                )

            if isinstance(e, nodes['Mesh']):
                item = f"{e}.{preferredType}[*]"
                if flatten:
                    out = m.ls(item, flatten=True)
                else:
                    out = [item]

                return out

            raise TypeError(
                "Not a mesh vertex, edge, face, UV or mesh: ", component
            )
        else:
            raise TypeError("Not a mesh vertex, edge, face or UV: ", component)

@short(removeDuplicates='rd',
       flatten='fl',
       expandMeshes='em')
def castMeshComponents(components:list[str],
                       preferredType:Literal['vtx', 'e', 'f', 'map'],
                       flatten:bool=False,
                       removeDuplicates:bool=False,
                       expandMeshes:bool=False
                       ) -> list[str]:
    """
    Conforms a list of mesh components into a preferred type.

    :param components: a list[str] of mesh faces, edges, vertices or UVs
    :param preferredType: the type to convert / expand to; one of 'vtx', 'e',
        'f' or 'map' (for UVs)
    :param flatten/fl: flatten the component list; defaults to False
    :param removeDuplicates/rd: remove duplicates in the return list; defaults
        to False
    :param expandMeshes/em: if a mesh is passed-in instead of a component,
        return a full component instead of throwing :class:`TypeError`; defaults
        to False
    """
    out = list(
        chain.from_iterable(
            (castMeshComponent(x,
                               preferredType,
                               expandMeshes=expandMeshes) for x in components)
        )
    )

    if flatten:
        out = m.ls(out, flatten=True)

    if removeDuplicates:
        out = list(without_duplicates(out))

    return out