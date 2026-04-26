from typing import Union, Literal
import re
from riggery.general.iterables import expand_tuples_lists, without_duplicates
import maya.cmds as m

COMPPAT = re.compile(r"^(.*?)\.(vtx|e|f|map)\[(.*?)\]$")

def conformMeshComponents(components:Union[str, list[str]],
                          target:Literal['vtx', 'map', 'f', 'e'],
                          flatten:bool=False) -> list[str]:
    """
    Conforms string mesh component paths to a single representation (e.g.
    vertices).

    :param components: the component(s) to conform, e.g. `mesh.f[3:6]`
    :param target: the target type; one of 'vtx', 'map', 'f' or 'e'
    :param flatten: flatten the returned component list; defaults to False
    """
    if isinstance(components, str):
        comps = [components]
    else:
        comps = list(components)

    out = []

    kwargs = {{'vtx':'toVertex',
               'e':'toEdge',
               'f':'toFace',
               'map':'toUV'}[target]:True}

    for comp in comps:
        theseKwargs = kwargs.copy()

        mt = re.match(COMPPAT, comp)

        if mt:
            currentType = mt.group(2)

            if currentType == target:
                out.append(comp)
            else:
                theseKwargs[{'vtx':'fromVertex',
                             'e':'fromEdge',
                             'f':'fromFace',
                             'map':'fromUV'}[currentType]] = True

            out += m.polyListComponentConversion(comp, **theseKwargs)

    if flatten:
        out = list(without_duplicates(m.ls(out, flatten=True)))

    return out