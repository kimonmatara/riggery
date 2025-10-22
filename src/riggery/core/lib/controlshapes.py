import os
import re
from copy import deepcopy
import json
from typing import Iterable, Optional, Generator, Union, Literal

import maya.cmds as m
import maya.api.OpenMaya as om
from riggery.internal import str2api as _s2a
from riggery.internal import api2str as _a2s
from riggery.internal import apimath as _am
from riggery.general.iterables import expand_tuples_lists, \
    without_duplicates, \
    fill_nones_with_chase
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

#-----------------------------------------|
#-----------------------------------------|    SCALE TRACKER
#-----------------------------------------|

class ShapeScale:
    """
    Context manager to track relative / nested shape scaling. For external use;
    not used within this module at all.
    """
    __factor__ = None

    def __init__(self, factor:float, override:bool=False):
        self._factor = factor
        self._override = override

    def __enter__(self):
        self._prev = ShapeScale.__factor__
        if self._override:
            ShapeScale.__factor__ = self._factor
        else:
            if self._prev is None:
                ShapeScale.__factor__ = self._factor
            else:
                ShapeScale.__factor__ *= self._factor
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ShapeScale.__factor__ = self._prev
        return False

#-----------------------------------------|
#-----------------------------------------|    LOW-LEVEL
#-----------------------------------------|

def iterShapesUnderTransform(
        transform:str,
        includeLocators:bool=False
) -> Generator[str, None, None]:
    types = ['nurbsCurve']
    if includeLocators:
        types.append('locator')
    out = m.listRelatives(transform,
                          noIntermediate=True,
                          shapes=True,
                          type=types,
                          path=True)
    if out:
        for x in out:
            yield x

def iterShapesFromMixedSources(
        *sources:Union[str, list[str]]
) -> Generator[str, None, None]:
    visited = set()

    for source in without_duplicates(expand_tuples_lists(*sources)):
        nt = m.nodeType(source)
        if nt in ('transform', 'joint'):
            for x in iterShapesUnderTransform(source):
                if x in visited:
                    continue
                visited.add(x)
                yield x
        elif nt in ('nurbsCurve', 'bezierCurve'):
            if source in visited:
                continue
            visited.add(source)
            yield source

def getCurveMacroFromShape(curveShape:str,
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

def iterCurveMacrosFromTransform(
        transform:str,
        captureColor:bool=True,
        captureVisInput:bool=True
) -> Generator[dict, None, None]:
    for shape in iterShapesUnderTransform(transform):
        yield getCurveMacroFromShape(shape,
                                     captureColor=captureColor,
                                     captureVisInput=captureVisInput)

def iterCurveMacrosFromMixedSources(
        *sources:Union[str, list[str]],
        captureColor:bool=True,
        captureVisInput:bool=True
) -> Generator[dict, None, None]:
    for shape in iterShapesFromMixedSources(*sources):
        yield getCurveMacroFromShape(shape,
                                     captureColor=captureColor,
                                     captureVisInput=captureVisInput)

def clearShapesUnderTransform(transform):
    shapes = list(iterShapesUnderTransform(transform, includeLocators=True))
    for shape in shapes:
        try:
            m.delete(shape)
        except:
            continue

def createShapeFromCurveMacro(macro:dict,
                              parent:str,
                              applyColor:bool=True,
                              applyVisInput:bool=True,
                              preserveBezier:bool=False) -> str:
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

def iterSceneSourceTransforms(*userProvided) -> Generator[str, None, None]:
    visited = set()

    for x in expand_tuples_lists(*userProvided):
        if m.nodeType(x) not in ('transform', 'joint'):
            raise TypeError("expected a transform node")

        if x in visited:
            continue
        visited.add(x)
        yield x

    if not visited:
        allCurves = m.ls(type='nurbsCurve')
        if allCurves:
            for curve in allCurves:
                if m.getAttr(f"{curve}.intermediateObject"):
                    continue
                parent = m.listRelatives(curve, parent=True, path=True)[0]
                if parent in visited:
                    continue
                visited.add(parent)
                yield parent

def getFirstVisInputUnderControl(control:str) -> Optional[str]:
    for shape in iterShapesUnderTransform(control, includeLocators=True):
        inp = m.connectionInfo(f"{shape}.v", sfd=True)
        if inp:
            return inp

def getFirstOverrideColorUnderControl(control:str) -> Optional[int]:
    for shape in iterShapesUnderTransform(control, includeLocators=True):
        if m.getAttr(f"{shape}.overrideEnabled"):
            col = m.getAttr(f"{shape}.overrideColor")
            if col > 0:
                return col

#-----------------------------------------|
#-----------------------------------------|    CONTROL SHAPE CLASS
#-----------------------------------------|

class ControlShape:

    #---------------------------------|    Init

    def __init__(self, curveMacros:Iterable[dict]):
        self.curveMacros = list(curveMacros)

    #---------------------------------|    Capture

    @classmethod
    def capture(cls,
                *sources,
                captureColor:bool=True,
                captureVisInput:bool=True,
                normalizePoints:bool=False) -> 'ControlShape':
        """
        :raises NoShapesError
        """
        macros = list(
            iterCurveMacrosFromMixedSources(
                *sources,
                captureColor=captureColor,
                captureVisInput=captureVisInput
            )
        )
        if macros:
            inst = cls(macros)
            if normalizePoints:
                inst.normalizePoints()
            return inst
        raise NoShapesError

    #---------------------------------|    Apply

    def test(self, name=None):
        kwargs = {}
        if name:
            kwargs['name'] = name
        group = m.group(empty=True, **kwargs)
        self.apply(group)
        return group

    def apply(self,
              *transforms,
              applyColor:bool=True,
              applyVisInput:bool=True,
              replace:bool=True,

              translate:Optional[list[float]]=None,
              rotate:Optional[list[float]]=None,
              scale:Optional[list[float]]=None,
              axisRemap:Optional[list[str]]=None) -> list[str]:
        """
        Per transform:
            Make a copy of this entry
            Look for the first vis input under the control
                If there is one, assign it to every macro in this entry, but
                only if applyVisInput is False or the entry doesn't have a
                defined vis input
            Look for the first override color
                If there is one, assign it to every macro in this entry, but
                only if applyColor is False or the entry doesn't have a defined
                vis input
        """
        out = []

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

            existingVisInput = getFirstVisInputUnderControl(transform)
            existingOverrideColor = getFirstOverrideColorUnderControl(transform)

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
                clearShapesUnderTransform(transform)

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

    def iterPoints(self) -> Generator[list[float], None, None]:
        for curveMacro in self.curveMacros:
            for point in curveMacro['points']:
                yield point

    def transform(self, matrix:Union[list[float], om.MMatrix]):
        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).applyMatrix(matrix).simple()
        return self

    def translate(self, translate:list[list[float]]):
        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).translate(translate).simple()
        return self

    def rotate(self, rotate:list[list[float]]):
        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).rotate(rotate).simple()
        return self

    def scale(self, scale:list[list[float]]):
        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).scale(scale).simple()
        return self

    def axisRemap(self, *axes:str):
        for curveMacro in self.curveMacros:
            curveMacro['points'][:] = _am.PointWrangler(
                curveMacro['points']
            ).axisRemap(*axes).simple()
        return self

    def normalizePoints(self):
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

    def json(self) -> str:
        return json.dumps(self.macro())

    @classmethod
    def createFromMacro(cls, macro:dict) -> 'ControlShape':
        return cls(macro['curveMacros'])

    @classmethod
    def createFromJson(cls, data:str) -> 'ControlShape':
        return cls.createFromMacro(json.loads(data))

    #---------------------------------|    Repr

    def __repr__(self):
        num = len(self.curveMacros)
        if num == 0:
            return '<empty control shape entry>'
        elif num == 1:
            return '<control shape entry with 1 curve>'
        return f'<control shape entry with {num} curves>'

#-----------------------------------------|
#-----------------------------------------|    FUNCTIONAL / INTERACTIVE
#-----------------------------------------|

def transformControlShapes(*controls:Union[str, list[str]],
                           translate:Optional[list[list[float]]]=None,
                           rotate:Optional[list[list[float]]]=None,
                           scale:Optional[list[list[float]]]=None,
                           axisRemap:Optional[list[str]]=None) -> None:
    """
    Transforms control shapes, in local space, across the specified controls.
    """
    for control in without_duplicates(expand_tuples_lists(*controls)):
        for curveShape in iterShapesUnderTransform(control):
            fn = om.MFnNurbsCurve(_s2a.getNodeMObject(curveShape))
            points = list(fn.cvPositions(space=om.MSpace.kObject))
            wrangler = _am.PointWrangler(points)

            if scale is not None:
                wrangler.scale(scale)
            if axisRemap is not None:
                wrangler.axisRemap(axisRemap)
            if rotate is not None:
                wrangler.rotate(rotate)
            if translate is not None:
                wrangler.translate(translate)

            for i, point in enumerate(wrangler):
                m.move(point[0], point[1], point[2],
                       f"{curveShape}.cv[{i}]",
                       a=True, objectSpace=True)

def copyControlShapes(srcControl:str,
                      *destControls:Union[str, list[str]],
                      copyColor:bool=True,
                      copyVisInput:bool=False,

                      translate:Optional[list[float]]=None,
                      rotate:Optional[list[float]]=None,
                      scale:Optional[Union[float, list[float]]]=None,

                      worldSpace=False,
                      worldMirrorAxis:Optional[Literal['x', 'y', 'z']]=None,

                      replace:bool=True) -> list[str]:
    destControls = list(without_duplicates(expand_tuples_lists(*destControls)))

    if not destControls:
        raise NoTargetsError

    worldSpace = worldSpace or worldMirrorAxis

    entry = ControlShape.capture(srcControl,
                                 captureVisInput=copyVisInput,
                                 captureColor=copyColor)
    edits = {}

    for name, state in zip(('scale', 'rotate', 'translate'),
                           (scale, rotate, translate)):
        if state is not None:
            edits[name] = state

    if edits:
        for k, v in edits.items():
            getattr(entry, k)(v)

    if worldSpace:
        out = []
        origMatrix = m.xform(srcControl, q=True, matrix=True, worldSpace=True)
        entry.transform(origMatrix)

        if worldMirrorAxis:
            row, col = {'x': (0, 0), 'y': (1, 1), 'z': (2, 2)}[worldMirrorAxis]
            flipperMatrix = om.MMatrix()
            flipperMatrix.setElement(row, col,
                                     flipperMatrix.getElement(row, col) * -1)
            entry.transform(flipperMatrix)

        for destControl in destControls:
            thisMatrix = om.MMatrix(
                m.xform(destControl, q=True, matrix=True, worldSpace=True)
            ).inverse()

            thisEntry = entry.copy()
            thisEntry.transform(thisMatrix)

            out += thisEntry.apply(destControl, replace=replace)
        return out
    return entry.apply(destControls, replace=replace)

def setControlColor(color:int, *destControls:Union[str, list[str]]) -> None:
    doReset = color in (0, None)

    visited = False

    for ct in without_duplicates(expand_tuples_lists(*destControls)):
        visited = True
        for shape in iterShapesUnderTransform(ct, includeLocators=True):
            try:
                if doReset:
                    m.setAttr(f"{shape}.overrideEnabled", False)
                    m.setAttr(f"{shape}.overrideColor", 0)
                else:
                    m.setAttr(f"{shape}.overrideEnabled", True)
                    m.setAttr(f"{shape}.overrideColor", color)
            except RuntimeError:
                continue

    if not visited:
        raise NoTargetsError

def copyControlColor(srcControl:str,
                     *destControls:Union[str, list[str]]):
    colors = []

    destControls = without_duplicates(expand_tuples_lists(*destControls))
    if not destControls:
        raise NoTargetsError

    for shape in iterShapesUnderTransform(srcControl, includeLocators=True):
        if m.getAttr(f"{shape}.overrideEnabled"):
            _color = m.getAttr(f"{shape}.overrideColor")
            if _color > 0:
                colors.append(_color)
                continue
            else:
                colors.append(None)
        else:
            colors.append(None)

    fill_nones_with_chase(colors)
    numAvailCols = len(colors)

    if numAvailCols == colors.count(None):
        return

    for destControl in destControls:
        theseShapes = list(iterShapesUnderTransform(destControl,
                                                    includeLocators=True))
        thisColList = colors[:]
        diff = len(theseShapes) - numAvailCols

        if diff > 0:
            thisColList += [thisColList[-1]] * diff

        for col, shape in zip(thisColList, theseShapes):
            try:
                m.setAttr(f"{shape}.overrideEnabled", True)
                m.setAttr(f"{shape}.overrideColor", col)
            except:
                continue

#-----------------------------------------|
#-----------------------------------------|    ARCHIVE CLASS
#-----------------------------------------|

class ControlShapeArchive:

    #---------------------------------|    Init

    def __init__(self, entries:Optional[dict[str, ControlShape]]=None, /):
        if entries is None:
            entries = {}
        self._entries = entries

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

    def capture(self,
                key:str,
                *sources,
                captureColor:bool=True,
                captureVisInput:bool=False,
                force:bool=False,
                normalizePoints:bool=True) -> 'ControlShape':
        if (not force) and key in self:
            raise KeyError("key taken: {}".format(key))

        newEntry = ControlShape.capture(*sources,
                                        captureColor=captureColor,
                                        captureVisInput=captureVisInput,
                                        normalizePoints=normalizePoints)
        self._entries[key] = newEntry
        return newEntry

    def _captureFromScene(self,
                          *sourceTransforms,
                          normalizePoints:bool,
                          captureColor:bool,
                          captureVisInput:bool) -> list[ControlShape]:
        out = []

        for transform in iterSceneSourceTransforms(*sourceTransforms):
            try:
                entry = ControlShape.capture(transform,
                                             captureColor=captureColor,
                                             captureVisInput=captureVisInput)
            except NoShapesError:
                continue
            key = transform.split('|')[-1]
            self._entries[key] = entry
            out.append(entry)

        return out

    def captureSceneArchive(self, *sourceTransforms):
        """
        Use this for rig builds / scene templating.
        """
        return self._captureFromScene(*sourceTransforms,
                                      normalizePoints=False,
                                      captureColor=True,
                                      captureVisInput=True)

    def applySceneArchive(self,
                          applyColor:bool=True,
                          applyVisInput:bool=True) -> list[str]:
        out = []

        for k, v in self._entries.items():
            matches = m.ls(k, type='transform')
            if matches:
                for match in matches:
                    out += v.apply(match,
                                   applyColor=applyColor,
                                   applyVisInput=applyVisInput,
                                   replace=True)
        return out

    def createShowcaseScene(self,
                            force:bool=False,
                            spacing:float=0.5) -> list[str]:
        """
        Creates a new scene and dumps all shapes in the archive into it for
        visual inspections.

        :param spacing: the margin, along X, between each 'rendered' shape;
            defaults to 0.5
        :return: The list of generated shape nodes.
        """
        m.file(newFile=True, force=True)

        groups = [m.group(name=k, empty=True) for k in self]

        out = self.applySceneArchive()

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

        return out

    def recaptureFromShowcaseScene(self):
        curves = m.ls(type='nurbsCurve')
        if curves:
            curves = [x for x in curves
                      if not m.getAttr(f"{x}.intermediateObject")]
            curveXForms = list(
                without_duplicates(
                    [m.listRelatives(x, path=True, parent=True)[0]
                     for x in curves]
                )
            )
            if curveXForms:
                curveXForms = [x for x in curveXForms
                               if not m.listRelatives(x, parent=True)]
                if curveXForms:
                    self._captureFromScene(curveXForms,
                                           captureVisInput=False,
                                           captureColor=True,
                                           normalizePoints=True)
        return self

    def __setitem__(self, key:str, value:ControlShape):
        if isinstance(value, ControlShape):
            self._entries[key] = value
        else:
            raise TypeError("expected ControlShape")

    #---------------------------------|    Remove members

    def __delitem__(self, key):
        del(self._entries[key])

    def clear(self):
        self._entries.clear()

    #---------------------------------|    Serialization

    def macro(self) -> dict:
        return {'entries': {k: v.macro() for k, v in self._entries.items()}}

    def json(self) -> str:
        return json.dumps(self.macro())

    @classmethod
    def createFromMacro(cls, macro:dict) -> 'ControlShapeArchive':
        return cls().setToMacro(macro)

    @classmethod
    def createFromJson(cls, data:str) -> 'ControlShapeArchive':
        return cls.createFromMacro(json.loads(data))

    def setToMacro(self, macro:dict):
        entries = {k: ControlShape.createFromMacro(v)
                   for k, v in macro['entries'].items()}
        self._entries.clear()
        self._entries.update(entries)
        return self

    def setToJson(self, data:str):
        return self.setToMacro(json.loads(data))

    #---------------------------------|    Repr

    def __repr__(self):
        num = len(self._entries)
        if num == 0:
            return "<empty control shape archive>"
        elif num == 1:
            return "<control shape archive with 1 shape>"
        return f"<control shape archive with {num} shapes>"


class ControlShapeLibrary(ControlShapeArchive, metaclass=SingletonMeta):
    """
    Singleton variant of :class:`ControlShapeArchive` that keeps track of an
    adjacent json file named after this module, and implements :meth:`load`
    and :meth:`dump` convenience methods. Syncing is not persistent.
    """
    #---------------------------------|    Init

    def __init__(self):
        super().__init__()
        self._filepath = os.path.join(
            os.path.dirname(__file__),
            "{}.json".format(__name__.split('.')[-1])
        )
        self.load()

    #---------------------------------|    I/O

    @property
    def filepath(self) -> str:
        return self._filepath

    def load(self, *_):
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = f.read()
            self.setToJson(data)
        except IOError:
            self._entries = {}

    def dump(self, *_):
        data = self.json()
        with open(self.filepath, 'w') as f:
            f.write(data)
        print("Dumped {} control shape(s) into: {}".format(len(self),
                                                           self.filepath))