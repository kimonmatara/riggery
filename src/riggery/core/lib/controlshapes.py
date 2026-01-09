import os
import re
import json
from copy import deepcopy
from pathlib import Path
from typing import Iterator, Iterable, Optional, Union

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.internal import str2api as _s2a
from riggery.internal import apimath as _am
from riggery.internal import api2str as _a2s
from riggery.internal.typeutil import SingletonMeta

#-----------------------------------------|
#-----------------------------------------|    ERRORS
#-----------------------------------------|

class ControlShapeError(RuntimeError):
    ...

class NoShapesError(ControlShapeError):
    ...

class NoTargetsError(ControlShapeError):
    ...

class MissingNodeError(ControlShapeError):
    ...

class ShapeLibraryError(RuntimeError):
    ...

class LibraryKeyExistsError(ShapeLibraryError):
    ...

#-----------------------------------------|
#-----------------------------------------|    LOW-LEVEL
#-----------------------------------------|

def transformCurveCVs(curveShape:str, translate=None, rotate=None, scale=None):
    """Transforms NURBS curve CVs."""
    print("on curve shape ", curveShape)

    if any((x is not None for x in (translate, rotate, scale))):
        if scale is not None:
            args = list(scale) + [f'{curveShape}.cv[:]']
            m.scale(*args, relative=True, objectSpace=True)

        if rotate is not None:
            args = list(rotate) + [f'{curveShape}.cv[:]']
            m.rotate(*args, relative=True, objectSpace=True)

        if translate is not None:
            args = list(translate) + [f'{curveShape}.cv[:]']
            m.move(*args, relative=True, objectSpace=True)

def iterCurveShapes(*sources) -> Iterator[str]:
    """
    :param \*sources: curve shapes or transforms
    :return: A list of curve shapes expanded / parsed from ``*sources``.
    """
    yielded = set()

    for source in expand_tuples_lists(*sources):
        source = str(source)

        if m.objectType(source, isAType='transform'):
            curveShapes = m.listRelatives(
                source,
                shapes=True,
                type='nurbsCurve',
                noIntermediate=True,
                path=True
            )
            if curveShapes:
                for curveShape in curveShapes:
                    if curveShape not in yielded:
                        yielded.add(curveShape)
                        yield curveShape

        elif m.objectType(source, isAType='nurbsCurve'):
            if source not in yielded:
                yielded.add(source)
                yield source

def getCurveMacro(curveShape:str,
                  captureColor:bool=True,
                  captureVisInput:bool=True) -> dict:
    out = {}

    obj = _s2a.getNodeMObject(curveShape)
    fn = om.MFnNurbsCurve(obj)
    out['points'] = points = [list(point)[:3]
                              for point in fn.cvPositions(om.MSpace.kObject)]
    out['knots'] = list(fn.knots())
    out['degree'] = fn.degree
    out['form'] = fn.form
    out['is2D'] = all([point[2] == 0.0 for point in points])
    rational = False

    for i in range(fn.numCVs):
        if m.getAttr(f"{curveShape}.weights[{i}]") != 1.0:
            rational = True
            break

    out['rational'] = rational
    out['lineWidth'] = m.getAttr(f"{curveShape}.lineWidth")

    if m.nodeType(curveShape) == 'bezierCurve':
        out['isBezier'] = True

    if captureColor:
        if m.getAttr(f"{curveShape}.overrideEnabled"):
            col = m.getAttr(f"{curveShape}.overrideColor")
            if col > 0:
                out['overrideColor'] = col

    if captureVisInput:
        inp = m.connectionInfo(f"{curveShape}.v", sfd=True)
        if inp:
            out['visInput'] = inp

    return out

def clearCurveShapes(*sources) -> None:
    """
    This will ignore intermediate curve shapes, unless they are explicitly
    passed-in.

    :param \*source: curve shapes or transforms
    """
    for curveShape in list(iterCurveShapes(*sources)):
        try:
            m.delete(curveShape)
        except:
            continue

def createShapeFromCurveMacro(macro:dict,
                              parent:str,
                              applyColor:bool=True,
                              applyVisInput:bool=True,
                              preserveBezier:bool=False) -> str:
    """
    :param macro: the type of macro returned by :func:`getCurveMacro`
    :param parent: the parent transform
    :param applyColor: apply any color information in the macro; defaults to
        True
    :param applyVisInput: (attempt to) connect any visibility input captured in
        the macro; defaults to True
    :param preserveBezier: if the macro was extracted from a bezier curve,
        recreate as a bezier curve; defaults to False
    :return: The curve shape.
    """
    parentMObject = _s2a.getNodeMObject(parent)
    args = [macro[k] for k in ('points',
                               'knots',
                               'degree',
                               'form',
                               'is2D',
                               'rational')]
    kwargs = {'parent': parentMObject}
    shapeMObject = om.MFnNurbsCurve().create(*args, **kwargs)
    shape = _a2s.fromNodeMObject(shapeMObject, isDagNode=True)

    if macro['degree'] == 3:
        m.displaySmoothness(shape, pointsWire=16)

    if preserveBezier and macro.get('isBezier', False):
        m.select(shape)
        shape = m.nurbsCurveToBezier()[0]

    if applyVisInput:
        visInput = macro.get('visInput')
        if visInput:
            try:
                m.connectAttr(visInput, f"{shape}.v")
            except:
                pass

    if applyColor:
        overrideColor = macro.get('overrideColor')
        if overrideColor:
            m.setAttr(f"{shape}.overrideEnabled", True)
            m.setAttr(f"{shape}.overrideColor", overrideColor)

    m.setAttr(f"{shape}.lineWidth", macro['lineWidth'])
    return shape

def conformShapeNames(transform:str) -> list[str]:
    """
    Fixes wonky shape names under a transform node.

    :return: The resolved shape paths.
    """
    shapes = m.listRelatives(transform, shapes=True, path=True)

    if shapes:
        transformShortName = transform.split('|')[-1]

        numShapes = len(shapes)
        newNames = [f'_gibberish_{x}' for x in range(numShapes)]
        shapes = [m.rename(shape, x) for shape, x in zip(shapes, newNames)]

        mt = re.match(r"^(.*?)([0-9]+)$", transformShortName)

        if mt:
            basename, startingIndex = mt.groups()
            startingIndex = int(startingIndex)
            newNames = [f'{basename}Shape{x}'
                        for x in range(startingIndex, numShapes+startingIndex)]
        else:
            newNames = ['{}Shape{}'.format(transformShortName,
                                           '' if x == 0 else x)
                        for x in range(numShapes)]
        shapes = [m.rename(shape, x) for shape, x in zip(shapes, newNames)]
        return shapes

    return []

def getFirstVisInput(*sources):
    """
    Returns the first curve-shape-level visibility input across ``*sources``,
    or None.
    """
    for curveShape in iterCurveShapes(*sources):
        inp = m.connectionInfo(f"{curveShape}.v", sfd=True)

        if inp:
            return inp

def getFirstOverrideColor(*sources):
    """
    Returns the first curve-shape-level override color across ``*sources``, or
    None.
    """
    for curveShape in iterCurveShapes(*sources):
        if m.getAttr(f"{curveShape}.overrideEnabled"):
            col = m.getAttr(f"{curveShape}.overrideColor")
            if col > 0:
                return col

#-----------------------------------------|
#-----------------------------------------|    CONTROL SHAPE CLASS
#-----------------------------------------|

class ControlShape:

    #---------------------------------|    Constructors

    @classmethod
    def capture(cls,
                *sources,
                captureColor:bool=True,
                captureVisInput:bool=True,
                normalizePoints:bool=False) -> 'ControlShape':
        """
        :raises NoShapesError: no detected curve shapes
        """
        macros = [getCurveMacro(curveShape,
                                captureColor=captureColor,
                                captureVisInput=captureVisInput)
                  for curveShape in iterCurveShapes(*sources)]

        if macros:
            inst = cls(macros)

            if normalizePoints:
                inst.normalizePoints()
            return inst

        raise NoShapesError('no detected curve shapes')

    #---------------------------------|    Init

    def __init__(self, curveMacros:Iterable[dict]):
        """
        Note that the dictionaries in *curveMacros* are ingested without
        copying; look out for mutability if editing externally.

        :param curveMacros: an iterable / list / tuple of macro dictionaries, of
            the type returned by :func:`getCurveMacro`
        """
        self.curveMacros = [deepcopy(x) for x in curveMacros]

    #---------------------------------|    Apply

    def test(self, name:Optional[str]=None, /) -> str:
        """
        :param name/n: an optional name for the group node
        :return: A group node with the curve shape applied, for visualization /
            testing purposes.
        """
        kwargs = {}

        if name:
            kwargs['name'] = name

        group = m.group(empty=True, **kwargs)
        self.apply(group)

        return group

    def apply(
            self,
            *transforms,
            applyColor:bool=True,
            applyVisInput:bool=True,
            replace:bool=True,

            translate:Optional[list[float]]=None,
            rotate:Optional[list[float]]=None,
            scale:Optional[list[float]]=None,
            axisRemap:Optional[
                Union[tuple[str, str], tuple[str, str, str, str]]
            ]=None
    ) -> list[str]:
        """
        :param \*transforms: the transforms under which to create curve shapes
            from this entry
        :param applyColor: apply embedded color information; defaults to True
        :param applyVisInput: (attempt to) apply embedded visibility inputs;
            defaults to True

        :param translate: optional triple of CV translation values
        :param rotate: optional triple of CV rotation values
        :param scale: optional triple of CV scale values
        :param axisRemap: tuple of either two or four axis letters (e.g. 'x',
            '-z' etc); if provided, they will be interpreted as pairwise axis
            remappings for quick shape reorientation; defaults to None
        :return: A list of generated shapes.
        """
        out = []

        # If there are translate / rotate / scale requests, make a copy of
        # 'self' and perform them on that

        edits = {}

        for name, state in zip(
                ('scale', 'axisRemap', 'rotate', 'translate'),
                (scale, axisRemap, rotate, translate)
        ):
            if state is not None:
                edits[name] = state

        if edits:
            self = self.copy()

            for k, v in edits.items():
                getattr(self, k)(v)

        for transform in without_duplicates(expand_tuples_lists(*transforms)):
            # Attempt to reuse existing user vis input / override col info
            # where things are undefined

            existingVisInput = getFirstVisInput(transform)
            existingOverrideColor = getFirstOverrideColor(transform)

            if existingVisInput or existingOverrideColor:
                thisInst = self.copy()

                for curveMacro in thisInst.curveMacros:
                    if existingVisInput:
                        if applyVisInput is False \
                                or 'visInput' not in curveMacro:
                            curveMacro['visInput'] = existingVisInput

                    if existingOverrideColor:
                        if applyColor is False \
                                or 'overrideColor' not in curveMacro:
                            curveMacro['overrideColor'] = existingOverrideColor
            else:
                thisInst = self

            if replace:
                clearCurveShapes(transform)

            shapeMObjects = []

            for curveMacro in thisInst.curveMacros:
                shape = createShapeFromCurveMacro(curveMacro,
                                                  transform,
                                                  applyColor=applyColor,
                                                  applyVisInput=applyVisInput)
                shapeMObjects.append(_s2a.getNodeMObject(shape))

            conformShapeNames(transform)
            out += [_a2s.fromNodeMObject(x,
                                         isDagNode=True) for x in shapeMObjects]

        return out

    #---------------------------------|    Transformations

    def iterPoints(self) -> Iterator[list[float]]:
        """Yields points across all curves in this entry."""

        for curveMacro in self.curveMacros:
            for point in curveMacro['points']:
                yield point

    points = property(iterPoints)

    def transform(self, matrix:Union[list[float], om.MMatrix]):
        """Transforms CVs using a matrix, in object space."""

        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).applyMatrix(matrix).simple()
        return self

    def translate(self, translate:list[list[float]]):
        """Applies object-space translation to the curve CVs."""

        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).translate(translate).simple()
        return self

    def rotate(self, rotate:list[list[float]]):
        """Applies object-space rotation to the curve CVs."""

        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).rotate(rotate).simple()
        return self

    def scale(self, scale:list[list[float]]):
        """Applies object-space scaling to the curve CVs."""

        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).scale(scale).simple()
        return self

    def axisRemap(self, *axes:str):
        """
        :param \*axes: two or four axis letters (e.g. 'x', '-z' etc), they will
            be interpreted as pairwise axis remappings for quick shape
            reorientation
        """
        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).axisRemap(*axes).simple()
        return self

    def normalizePoints(self):
        """Fits CVs into a unit cube."""

        allPoints = []
        for curveMacro in self.curveMacros:
            allPoints += curveMacro['points']

        allPoints = _am.PointWrangler(allPoints).normalizeBoundingBox().simple()
        lastLength = 0

        for i, curveMacro in enumerate(self.curveMacros):
            thisLength = len(curveMacro['points']) + lastLength
            curveMacro['points'][:] = allPoints[lastLength:thisLength]
            lastLength = thisLength
        return self

    #---------------------------------|    Serialization

    def copy(self) -> 'ControlShape':
        return type(self)(deepcopy(self.curveMacros))

    def __copy__(self):
        return self.copy()

    def macro(self) -> dict:
        return {'curveMacros': deepcopy(self.curveMacros)}

    @classmethod
    def createFromMacro(cls, macro:dict) -> 'ControlShape':
        return cls(macro['curveMacros'])

    #---------------------------------|    Repr

    def __repr__(self):
        num = len(self.curveMacros)
        if num == 0:
            return '<empty control shape entry>'
        elif num == 1:
            return '<control shape entry with 1 curve>'
        return f'<control shape entry with {num} curves>'

#-----------------------------------------|
#-----------------------------------------|    SCENE ARCHIVING
#-----------------------------------------|

def iterSceneControls(ignoreReferenced:bool=True,
                      ignoreWithNamespaces:bool=True) -> Iterator[str]:
    """
    Yields scene transforms with attached controller tags.

    :param ignoreReferenced: ignore nodes from referenced files; defaults to
        True
    :param ignoreWithNamespaces: ignore nodes with namespaces; defaults to True
    """
    controllerTags = m.ls(type='controller')

    yielded = set()

    if controllerTags:
        for controllerTag in controllerTags:
            input = m.connectionInfo(f"{controllerTag}.controllerObject",
                                     sfd=True)
            if input:
                node = input.split('.')[0]

                if m.objectType(node, isAType='transform'):
                    if ((ignoreWithNamespaces and ':' in node)
                            or (ignoreReferenced and m.referenceQuery(
                                node,
                                isNodeReferenced=True
                            ))):
                        continue

                    if node not in yielded:
                        yielded.add(node)
                        yield node

def getDefaultSceneArchiveKeys(ignoreReferenced:bool=True,
                               ignoreWithNamespaces:bool=True) -> list[str]:
    """
    Returns default keys for a scenewide control shape dump. These will be the
    short names of transforms with controller tags.
    """
    return list(without_duplicates((x.split('|')[-1] for x in iterSceneControls(
        ignoreReferenced=ignoreReferenced,
        ignoreWithNamespaces=ignoreWithNamespaces
    ))))

def resolveSceneArchiveKeys(
        controls:Optional[Iterable[str]]=None, /,
        ignoreReferenced:Optional[bool]=None,
        ignoreWithNamespaces:Optional[bool]=None
) -> list[str]:
    """
    :param controls: scene controls to use for the keys; if omitted, defers to
        :func:`getDefaultArchiveKeys`
    :param ignoreReferenced: defaults to True if *controls* is omitted,
        otherwise False
    :param ignoreWithNamespaces:  defaults to True if *controls* is omitted,
        otherwise False
    """
    if not controls:
        if ignoreReferenced is None:
            ignoreReferenced = True

        if ignoreWithNamespaces is None:
            ignoreWithNamespaces = True

        return getDefaultSceneArchiveKeys(
            ignoreReferenced=ignoreReferenced,
            ignoreWithNamespaces=ignoreWithNamespaces
        )

    out = []

    if ignoreReferenced is None:
        ignoreReferenced = False

    if ignoreWithNamespaces is None:
        ignoreWithNamespaces = False

    for control in controls:
        control = str(control)

        if ignoreWithNamespaces and ':' in control:
            continue

        if ignoreReferenced:
            try:
                isReferenced = m.referenceQuery(control, isNodeReferenced=True)
            except RuntimeError:
                isReferenced = False

            if isReferenced:
                continue

        out.append(control.split('|')[-1])

    return list(without_duplicates(out))

def captureSceneArchive(controls:Optional[Iterable[str]]=None, /,
                        ignoreReferenced:Optional[bool]=None,
                        ignoreWithNamespaces:Optional[bool]=None) -> dict:
    """
    Captures scenewide control shape information.

    :param controls: the controls to capture; if omitted, scene transforms with
        controller tags are used instead
    :param ignoreReferenced: defaults to True if *controls* is omitted,
        otherwise False
    :param ignoreWithNamespaces: defaults to True if *controls* is omitted,
        otherwise False
    :return: A dictionary that can be passed along to `dumpSceneArchive`.
    """
    keys = resolveSceneArchiveKeys(controls,
                                   ignoreReferenced=ignoreReferenced,
                                   ignoreWithNamespaces=ignoreWithNamespaces)

    out = {}

    for key in keys:
        matches = m.ls(key, type='transform')

        if matches:
            out[key] = ControlShape.capture(matches[0]).macro()

    return out

def applySceneArchive(archive:dict,
                      controls:Optional[Iterable[str]]=None, /,
                      applyColor:bool=True,
                      applyVisInput:bool=True) -> list[str]:
    """
    :param applyColor: apply any color information in the macro; defaults to
        True
    :param applyVisInput: (attempt to) connect any visibility input captured in
        the macro; defaults to True
    :return: A list of generated shapes.
    """
    out = []

    if controls:
        controls = list(without_duplicates(map(str, controls)))

    for controlName, entryMacro in archive.items():
        if controls:
            matches = [x for x in controls if x.split('|')[-1] == controlName]
        else:
            matches = m.ls(controlName, type='transform')

        if matches:
            num = len(matches)
            if num == 1:
                out += ControlShape.createFromMacro(entryMacro).apply(
                    matches,
                    applyColor=applyColor,
                    applyVisInput=applyVisInput
                )
            else:
                m.warning(f"Skipping '{controlName}': no unambiguous match")

    return out


def loadSceneArchive(filePath:str) -> dict:
    """
    Loads and returns data from the type of scene archive written by
    :func:`dumpSceneArchive`. This can then be applied using
    :func:`applySceneArchive`.
    """
    with open(filePath, 'r', encoding='utf-8') as f:
        _data = f.read()
    return json.loads(_data)

def dumpSceneArchive(archive:dict,
                     filePath:str,
                     makeDirs:bool=False) -> None:
    """
    :param archive: the type of archive generated by :func:`captureSceneArchive`
    :param filePath: the path to a JSON file; the extension will be
        automatically conformed
    :param makeDirs: create parent directory structure if necessary; defaults to
        False
    :raises FileNotFoundError: Parent directory does not exist.
    """
    filePath = Path(filePath)
    parentDir = filePath.parent

    if not parentDir.is_dir():
        if makeDirs:
            os.makedirs(parentDir)
            print(f"Created directory: {parentDir}")
        raise FileNotFoundError("parent directory does not exist")

    filePath = parentDir / (filePath.stem + '.json')

    _data = json.dumps(archive, indent=2)

    with open(filePath, 'w', encoding='utf-8') as f:
        f.write(_data)

    print("Dumped {} control shape(s) into: {}".format(len(archive), filePath))

#-----------------------------------------|
#-----------------------------------------|    GENERAL TOOLS
#-----------------------------------------|

def canDisableOverrides(shape) -> bool:
    """
    :return: True if all the display override attributes on *shape* are at
        default values, and have no inputs.
    """
    for attrName, defaultValue in {
        'overrideDisplayType': 0,
        'overrideLevelOfDetail': 0,
        'overrideShading': True,
        'overrideTexturing': True,
        'overridePlayback': True,
        'overrideVisibility': True,
        'overrideRGBColors': False,
        'overrideColor': 0,
        'overrideColorRGB': [(0.0, 0.0, 0.0)],
        'overrideColorR': 0.0,
        'overrideColorG': 0.0,
        'overrideColorB': 0.0,
        'overrideColorA': 1.0
    }.items():
        attr = f"{shape}.{attrName}"
        input = m.connectionInfo(attr, sfd=True)

        if input:
            return False

        value = m.getAttr(attr)

        if value != defaultValue:
            return False

    return True

def setColor(color:Optional[int], *controls):
    """
    Applies the specified color to the specified controls.

    :param color: a standard Maya color index; if this is 0 or None, color
        overrides will be removed instead
    :param \*controls: transforms or curve shapes; color is applied strictly at
        the shape level
    """
    for curve in iterCurveShapes(*controls):
        if color in (0, None):
            m.setAttr(f"{curve}.overrideColor", 0)

            if canDisableOverrides(curve):
                m.setAttr(f"{curve}.overrideEnabled", False)
        else:
            m.setAttr(f"{curve}.overrideEnabled", True)
            m.setAttr(f"{curve}.overrideColor", color)

def copyColor(source:str, *destinations):
    """
    Copies override color from *source* to *destinations*. Does nothing if
    the override color on *source* is undefined.
    """
    color = getFirstOverrideColor(source)

    if color not in (0, None):
        setColor(color, *destinations)

#-----------------------------------------|
#-----------------------------------------|    LIBRARY
#-----------------------------------------|

LIBRARY_PATH = os.path.join(os.path.dirname(__file__),
                            "{}.json".format(__name__.split('.')[-1]))


class ShapeLibrary(metaclass=SingletonMeta):
    """
    Syncing is not persistent. You must call :meth:`dump` yourself after
    any edit operation.
    """

    #---------------------------------|    Inst

    def __init__(self):
        self._entries = {}
        self.load()

    #---------------------------------|    Get members

    def __len__(self):
        return len(self._entries)

    def __contains__(self, key:str):
        return key in self._entries

    def keys(self):
        return self._entries.keys()

    def values(self):
        return self._entries.values()

    def items(self):
        return self._entries.items()

    def __getitem__(self, key:str) -> ControlShape:
        return self._entries[key]

    def __iter__(self):
        return self._entries.__iter__()

    #---------------------------------|    Add members

    def __setitem__(self, key:str, value:ControlShape):
        if isinstance(value, ControlShape):
            self._entries[key] = value
        else:
            raise TypeError("expected ControlShape")

    def add(self,
            key:str,
            *sources,
            overwrite:bool=False,
            captureColor:bool=False,
            normalizePoints:bool=True) -> 'ControlShape':
        """
        :param key: the new entry name
        :param \*sources: transforms or curve shapes to extract shape
            information from; note that all of it will end up under a single key
        :param overwrite: if the key already exists, overwrite it instead of
            throwing an error
        :param captureColor: capture color information; defaults to False
        :param normalizePoints: fit curve CVs into a unit cube; defaults to True
        :raises LibraryKeyExistsError: the key exists, and *overwrite* is False
        """
        if (not overwrite) and key in self:
            raise LibraryKeyExistsError(key)

        self._entries[key] = out = ControlShape.capture(
            *sources,
            captureColor=captureColor,
            normalizePoints=normalizePoints,
            captureVisInput=False
        )

        print("Added '{}' to shape library.".format(key))

        return out

    #---------------------------------|    Remove members

    def __delitem__(self, key):
        del(self._entries[key])

    def clear(self):
        self._entries.clear()

    #---------------------------------|    Serialization

    def load(self):
        with open(LIBRARY_PATH, 'r', encoding='utf-8') as f:
            _data = f.read()

        data = json.loads(_data)
        entries = {k: ControlShape.createFromMacro(v)
                   for k, v in data['entries'].items()}

        self._entries.clear()
        self._entries.update(entries)

        return self

    def dump(self):
        data = {'entries': {k: v.macro() for k, v in self._entries.items()}}
        _data = json.dumps(data, indent=2)

        with open(LIBRARY_PATH, 'w', encoding='utf-8') as f:
            f.write(_data)

        print("Dumped {} control shape(s) into: {}".format(len(data['entries']),
                                                           LIBRARY_PATH))

    #---------------------------------|    Work scene

    def createWorkScene(self, spacing:float=0.5):
        """
        Creates a scene with all the library shapes in a row, for easy
        inspection and editing.
        """
        m.file(newFile=True, force=True)

        groups = [entry.test(name) for name, entry in self._entries.items()]

        for i, thisGroup in enumerate(groups[1:], start=1):
            lastGroup = groups[i-1]
            lastBBox = m.exactWorldBoundingBox(lastGroup,
                                               calculateExactly=True)
            thisBBox = m.exactWorldBoundingBox(thisGroup,
                                               calculateExactly=True)

            startingX = lastBBox[3] + spacing

            distanceToPivot = m.xform(thisGroup,
                                      q=True,
                                      rp=True,
                                      ws=True)[0] - thisBBox[0]

            thisX = startingX + distanceToPivot
            m.setAttr(f"{thisGroup}.tx", thisX)

    #---------------------------------|    Repr

    def __repr__(self):
        return "<control shapes library>"