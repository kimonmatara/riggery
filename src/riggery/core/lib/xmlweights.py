import re
from typing import Union, Optional, Literal, Iterable, Callable
import itertools
from pathlib import Path, PurePosixPath
from tempfile import gettempdir
import xml.etree.ElementTree as ET

import maya.cmds as m

from riggery.general.iterables import without_duplicates, expand_tuples_lists
from riggery.general.functions import short

#-----------------------------------------|
#-----------------------------------------|    UTILITIES
#-----------------------------------------|

def toList(item:Optional[list[str]]) -> list[str]:
    if item is None:
        return []
    return item

def getTempFilePath() -> str:
    num = 1
    tempDir = Path(gettempdir())

    while True:
        basename = 'riggeryXMLTemp{}.xml'.format(num)
        fullPath = tempDir / basename

        if fullPath.is_file():
            num += 1

        else:
            return fullPath.as_posix()

shortName = lambda x: str(x).split('|')[-1]

def getShapesFromDeformer(deformer:str) -> list[str]:
    shapes = m.deformer(deformer, q=True, g=True)

    if shapes:
        return shapes

    return []

def getDeformersFromShape(shape:str) -> list[str]:
    out = []
    history = m.listHistory(shape)

    if history:
        for x in history:
            if m.objectType(x, isAType='geometryFilter'):
                if shape in getShapesFromDeformer(x):
                    out.append(x)

    return out

#-----------------------------------------|
#-----------------------------------------|    ARG MANAGEMENT
#-----------------------------------------|

def remapToReplacer(remap:Optional[Union[str, Iterable[str]]]) -> Callable:
    """
    Uses a ``remap`` argument, formulated for the ``deformerWeights`` command,
    and returns a callable that can be used to perform direct string
    substitutions.
    """
    if not remap:
        return lambda x: x

    pairs = []

    for remapEntry in expandRemapArg(remap):
        origPat, origRepl = remapEntry.split(';')
        newRepl = re.sub(r'\$([0-9]+)', r'\\g<\g<1>>', origRepl)
        pairs.append((origPat, newRepl))

    def replacer(st:str) -> str:
        for pat, repl in pairs:
            st = re.sub(pat, repl, st)
        return st

    return replacer

def expandRemapArg(
        remap:Optional[Union[str, Iterable[str]]]
) -> Optional[list[str]]:
    """
    Performs minor cleanup on a user-provided ``remap`` argument, conforming to
    a list of strings in every case.

    How to format *remap* argument
    ------------------------------
    Each string should be formatted like this:

    ```
    <regex>;<replace>
    ```
    Use ``$1``, ``$2`` to refer to capture groups in the regex (1-based).
    For example, to replace the namespace 'banana' with 'apple' everywhere:

    ```
    banana:(.*);apple:($1)
    ```

    Which will have a result of:

    ```
    banana:joint1 -> apple:joint1
    etc.
    ```

    :param remap: either a single string (for a single substitution round) or
         a list of strings (for multiple substitutions)
    :return: a list of strings, or None
    """
    if remap:
        if isinstance(remap, str):
            return [remap]

        return list(remap)

def fixKwargs(kwargs:dict) -> None:
    # The only reliable way to run deformerWeights is to specify shapes via -sh
    # and deformers to skip via -df

    reqShapes = []

    for key in ('shape', 'sh'):
        try:
            reqShapes = toList(kwargs.pop(key))
            break
        except KeyError:
            continue

    reqDeformers = []

    for key in ('deformer', 'df'):
        try:
            reqDeformers = toList(kwargs.pop(key))
            break
        except KeyError:
            continue

    reqSkips = []

    for key in ('skip', 'sk'):
        try:
            reqSkips = toList(kwargs.pop(key))
            break
        except KeyError:
            continue

    outSkips = []
    outShapes = []
    outDeformers = []

    # First pass
    if reqShapes:
        reqShapes = expand_tuples_lists(reqShapes)

    if reqDeformers:
        reqDeformers = expand_tuples_lists(reqDeformers)

    if reqSkips:
        reqSkips = expand_tuples_lists(reqSkips)

    # Second pass
    if reqShapes:
        outShapes = reqShapes

        if reqDeformers:
            assocDeformers = itertools.chain.from_iterable(
                map(getDeformersFromShape, reqShapes)
            )
            outSkips = [x for x in assocDeformers if x not in reqDeformers]

    elif reqDeformers:
        outShapes = list(itertools.chain.from_iterable(
            map(getShapesFromDeformer, reqDeformers)
        ))
        assocDeformers = itertools.chain.from_iterable(
            map(getDeformersFromShape, outShapes)
        )
        outSkips = [d for d in assocDeformers if d not in reqDeformers]

    if reqSkips:
        outSkips = list(without_duplicates(reqSkips + outSkips))

    if outSkips:
        kwargs['skip'] = outSkips

    if outShapes:
        kwargs['shape'] = outShapes

#-----------------------------------------|
#-----------------------------------------|    WRAPPERS
#-----------------------------------------|

@short(shape='sh',
       deformer='df',
       vertexConnections='vc',
       attribute='at',
       remap='r',
       weightPrecision='wp',
       weightTolerance='wt',
       skip='sk',
       defaultValue='dv')
def dump(filepath:str,
         shape:Optional[Union[str, list[str]]]=None,
         deformer:Optional[Union[str, list[str]]]=None,
         vertexConnections:bool=False,
         weightPrecision:int=3,
         weightTolerance:float=0.001,
         remap:Optional[str]=None,
         attribute:Optional[Union[str, list[str]]]=None,
         skip:Optional[Union[str, list[str]]]=None,
         defaultValue:Optional[Union[int, float]]=None):
    """
    Wrapper for :func:`~pymel.internal.pmcmds.deformerWeights` in 'export'
    mode. Arguments are post-processed to ensure that only requested deformers
    and shapes are included. See Maya help for :func:`deformerWeights` for
    flag information.
    """
    filepath = PurePosixPath(Path(filepath).as_posix())
    args = (filepath.name,)

    kwargs = {'path': str(filepath.parent),
              'export': True,
              'vertexConnections': vertexConnections,
              'weightPrecision': weightPrecision,
              'weightTolerance': weightTolerance}

    if skip is not None:
        kwargs['skip'] = skip

    if attribute is not None:
        kwargs['attribute'] = attribute

    if defaultValue is not None:
        kwargs['defaultValue'] = defaultValue

    if remap is not None:
        kwargs['remap'] = remap

    if deformer:
        kwargs['deformer'] = expand_tuples_lists(deformer)

    if shape:
        kwargs['shape'] = expand_tuples_lists(shape)

    fixKwargs(kwargs)

    m.deformerWeights(*args, **kwargs)

@short(deformer='df',
       shape='sh',
       method='m',
       worldSpace='ws',
       attribute='at',
       ignoreName='ig',
       positionTolerance='pt',
       remap='r',
       skip='sk')
def load(filepath:str,
         deformer:Optional[Union[str, list[str]]]=None,
         shape:Optional[Union[str, list[str]]]=None,
         method:Literal[
             'index', 'nearest', 'barycentric', 'bilinear', 'over'
         ]='index',
         worldSpace:Optional[bool]=None,
         attribute:Optional[Union[str, list[str]]]=None,
         ignoreName:bool=False,
         positionTolerance:Optional[Union[float, int]]=None,
         remap:Optional[str]=None,
         skip:Optional[Union[str, list[str]]]=None):
    """
    Wrapper for :func:`~pymel.internal.pmcmds.deformerWeights` in 'import'
    mode. Arguments are post-processed to ensure that only requested deformers
    and shapes are included.  See Maya help for :func:`deformerWeights` for
    flag information.
    """
    filepath = PurePosixPath(Path(filepath).as_posix())
    args = (filepath.name,)

    kwargs = {'path': str(filepath.parent), 'im': True, 'method': method}

    if ignoreName:
        kwargs['ignoreName'] = True

    if positionTolerance is not None:
        kwargs['positionTolerance'] = positionTolerance

    if remap:
        kwargs['remap'] = remap

    if skip:
        kwargs['skip'] = expand_tuples_lists(skip)

    if attribute:
        kwargs['attribute'] = expand_tuples_lists(attribute)

    if worldSpace:
        kwargs['worldSpace'] = True

    if deformer:
        kwargs['deformer'] = expand_tuples_lists(deformer)

    if shape:
        kwargs['shape'] = expand_tuples_lists(shape)

    fixKwargs(kwargs)
    m.deformerWeights(*args, **kwargs)


def readXMLPerComponent(xmlfile, normalize:bool=False) -> dict:
    """
    Returns a dictionary in this format:
    {
        deformerName:
            'influences': [influence, influence, influence...]
            'shapes':
                shapeName: [
                    (for vertex 0): [weight, weight, weight, weight...],
                    (for vertex 1): [weight, weight, weight, weight...],
                    ...
                ]
    }
    """
    #-------------------------------|    Read file

    tree = ET.parse(xmlfile)
    root = tree.getroot()

    weightEntries = root.findall('weights')
    shapeEntries = root.findall('shape')

    #-------------------------------|    Gather information

    # Get a list of deformers
    deformers = []

    for weightEntry in weightEntries:
        deformer = weightEntry.attrib['deformer']
        if deformer not in deformers:
            deformers.append(deformer)

    # Get a list of shapes associated with each deformer
    perDeformerShapes = {}

    for weightEntry in weightEntries:
        shapesList = perDeformerShapes.setdefault(deformer, [])
        shape = weightEntry.attrib['shape']
        if shape not in shapesList:
            shapesList.append(shape)

    # Get vertex indices for each shape
    perShapeVertLists = {}

    for shapeEntry in shapeEntries:
        vertList = [int(point.attrib['index']) \
                    for point in shapeEntry.findall('point')]
        perShapeVertLists[shapeEntry.attrib['name']] = list(sorted(vertList))

    # Get influence lists for each deformer
    perDeformerInfluences = {}

    for weightEntry in weightEntries:
        deformer = weightEntry.attrib['deformer']
        layer = int(weightEntry.attrib['layer'])
        source = weightEntry.attrib['source']
        influenceDict = perDeformerInfluences.setdefault(deformer, {})
        influenceDict[layer] = source

    for deformer in perDeformerInfluences.keys():
        influenceDict = perDeformerInfluences[deformer]
        layers = sorted(influenceDict.keys())
        influenceList = [influenceDict[k] for k in layers]
        perDeformerInfluences[deformer] = influenceList

    #-------------------------------|    Gather per-component

    deformerBundles = {} # deformer: info

    for deformer in deformers:
        deformerBundle = deformerBundles.setdefault(deformer, {})
        influenceList = perDeformerInfluences[deformer]
        deformerBundle['influences'] = influenceList

        for shape in perDeformerShapes[deformer]:
            indices = perShapeVertLists[shape]

            shapeWeights = []

            for index in indices:
                thisLine = [0.0] * len(influenceList)
                shapeWeights.append(thisLine)

            for weightEntry in weightEntries:
                if weightEntry.attrib['deformer'] == deformer:
                    if weightEntry.attrib['shape'] == shape:
                        influence = weightEntry.attrib['source']
                        influenceIndex = influenceList.index(influence)

                        for pointEntry in weightEntry.findall('point'):
                            vertIndex = int(pointEntry.attrib['index'])
                            weight = float(pointEntry.attrib['value'])
                            shapeWeights[vertIndex][influenceIndex] = weight

            if normalize:
                shapeWeights = [normalize_scalars(
                    entry) for entry in shapeWeights]

            # shapeWeights = normalize_scalars(shapeWeights)
            deformerBundle.setdefault('shapes', {})[shape] = shapeWeights

    return deformerBundles