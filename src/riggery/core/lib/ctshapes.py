import re
from copy import deepcopy
import json
from typing import Iterable, Optional, Generator, Union

import maya.cmds as m
import maya.api.OpenMaya as om
from riggery.internal import str2api as _s2a
from riggery.internal import api2str as _a2s
from riggery.general.iterables import expand_tuples_lists, without_duplicates

#-----------------------------------------|    ERRORS

class ControlShapeError(RuntimeError):
    ...

class NoShapesError(ControlShapeError):
    ...

#-----------------------------------------|    CONTROL SHAPE CLASS

class ControlShapeSpec:

    #---------------------------------|    Constructors

    @classmethod
    def capture(cls,
                *sources,
                normalizePoints:bool=True,
                overrideColor:bool=True,
                visInput:bool=False):
        shapes = list(cls._detectCurveShapes(*sources))
        if not shapes:
            raise NoShapesError
        curveMacros = [cls._getCurveMacro(x) for x in shapes]
        args = (curveMacros,)

        kwargs = {}

        if overrideColor:
            color = cls._getFirstOverrideColor(shapes)
            if color is not None:
                kwargs['overrideColor'] = color

        if visInput:
            input = cls._getFirstVisInput(shapes)
            if input is not None:
                kwargs['visInput'] = input

        inst = cls(*args, **kwargs)
        if normalizePoints:
            inst.normalizePoints()
        return inst

    #---------------------------------|    Init

    def __init__(self,
                 curveMacros:list[dict],
                 overrideColor:Optional[int]=None,
                 visInput:Optional[str]=None):
        self.curveMacros = deepcopy(curveMacros)
        self.overrideColor = overrideColor
        self.visInput = visInput

    #---------------------------------|    Extraction utilities

    @classmethod
    def _getFirstVisInput(cls, shapes:list[str]) -> Optional[str]:
        for shape in shapes:
            input = m.connectionInfo(f"{shape}.v", sfd=True)
            if input:
                return input

    @classmethod
    def _getFirstOverrideColor(cls, shapes:list[str]) -> Optional[int]:
        for shape in shapes:
            if m.getAttr(f"{shape}.overrideEnabled"):
                color = m.getAttr(f"{shape}.overrideColor")
                if color > 0:
                    return color

    @classmethod
    def _getCurveMacro(cls, curveShape:str) -> dict:
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
        return out

    @classmethod
    def _detectCurveShapes(cls, *sources) -> Generator[str, None, None]:
        for source in without_duplicates(map(str,
                                             expand_tuples_lists(*sources))):
            obj = _s2a.getNodeMObject(source)

            if obj.hasFn(om.MFn.kDagNode):
                if obj.hasFn(om.MFn.kShape):
                    if obj.hasFn(om.MFn.kNurbsCurve):
                        yield source
                elif obj.hasFn(om.MFn.kTransform):
                    shapes = m.listRelatives(
                        source,
                        shapes=True,
                        noIntermediate=True,
                        path=True,
                        type=('nurbsCurve', 'bezierCurve')
                    )
                    if shapes:
                        for shape in shapes:
                            yield shape

    #---------------------------------|    Edits

    def scalePoints(self, factor:float):
        for curveMacro in self.curveMacros:
            curveMacro['points'] = [
                [point[0] * factor, point[1] * factor, point[2] * factor]
                for point in curveMacro['points']
            ]
        return self

    def normalizePoints(self):
        allPoints = []

        for curveMacro in self.curveMacros:
            allPoints += curveMacro['points']

        if allPoints:
            bbox = om.MBoundingBox()

            for point in map(om.MPoint, allPoints):
                bbox.expand(point)

            mag = (bbox.max - bbox.min).length()
            self.scalePoints(1.7320508075688772 / mag)

        return self

    #---------------------------------|    Application

    @classmethod
    def _conformShapeNames(cls, transform:str) -> list[str]:
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
                            for x in range(startingIndex,
                                           numShapes+startingIndex)]
            else:
                newNames = ['{}Shape{}'.format(transformShortName,
                                               '' if x == 0 else x)
                            for x in range(numShapes)]
            shapes = [m.rename(shape, x) for shape, x in zip(shapes, newNames)]
            return shapes
        return []

    def apply(self,
              *transforms,
              replace:bool=True,
              overrideColor:bool=True,
              visInput:bool=True,
              scale:Optional[float]=None) -> list[str]:
        transforms = list(
            without_duplicates(map(str, expand_tuples_lists(*transforms)))
        )
        if transforms:
            _self = self.copy()
            if scale is not None:
                _self.scalePoints(scale)

            outShapes = []
            doApplyVisInput = _self.visInput is not None \
                              and m.objExists(_self.visInput)

            for transform in without_duplicates(
                map(str, expand_tuples_lists(*transforms))
            ):
                if replace:
                    existingShapes = m.listRelatives(transform,
                                                     path=True,
                                                     type=('nurbsCurve',
                                                           'bezierCurve',
                                                           'locator'),
                                                     noIntermediate=True)
                    if existingShapes:
                        for shape in existingShapes:
                            try:
                                m.delete(shape)
                            except:
                                continue

                xfMObject = _s2a.getNodeMObject(transform)

                for macro in _self.curveMacros:
                    args = [macro[k] for k in ('points',
                                               'knots',
                                               'degree',
                                               'form',
                                               'is2D',
                                               'rational')]
                    kwargs = {'parent': xfMObject}
                    shapeMObject = om.MFnNurbsCurve().create(*args, **kwargs)
                    shape = _a2s.fromNodeMObject(shapeMObject, isDagNode=True)
                    m.setAttr(f"{shape}.lineWidth", macro['lineWidth'])

                    if doApplyVisInput:
                        m.connectAttr(self.visInput, f"{shape}.v")

                    if self.overrideColor is not None:
                        m.setAttr(f"{shape}.overrideEnabled", True)
                        m.setAttr(f"{shape}.overrideColor", self.overrideColor)
                self._conformShapeNames(transform)
        return self

    #---------------------------------|    Serialization

    def copy(self) -> 'ControlShapeSpec':
        args, kwargs = self.getArgsKwargs()
        return type(self)(*args, **kwargs)

    def getArgsKwargs(self) -> tuple[tuple, dict]:
        args = (deepcopy(self.curveMacros),)
        kwargs = {}
        if self.overrideColor is not None:
            kwargs['overrideColor'] = self.overrideColor
        if self.visInput is not None:
            kwargs['visInput'] = self.visInput
        return args, kwargs

    def macro(self) -> dict:
        args, kwargs = self.getArgsKwargs()
        return {'args': args, 'kwargs': kwargs}

    @classmethod
    def fromMacro(cls, macro:dict) -> 'ControlShapeSpec':
        args = macro['args']
        kwargs = macro['kwargs']
        return cls(*args, **kwargs)

    def toJson(self) -> str:
        return json.dumps(self.macro())

    @classmethod
    def fromJson(cls, data:str) -> 'ControlShapeSpec':
        return cls.fromMacro(json.loads(data))

#-----------------------------------------|    LIBRARY CLASS

# class ShapeLibrary:
#
#     #---------------------------------|    Init
#
#     def __init__(self, data:dict, filePath:Optional[str]=None):
#         self._data = deepcopy(data)
#         self._filePath = filePath
#
#     #---------------------------------|    Dict-like
#
#     @property
#     def keys(self):
#         return self._data.keys
#
#     @property
#     def values(self):
#         return self._data.values
#
#     @property
#     def items(self):
#         return self._data.items
#
#     @property
#     def __len__(self):
#         return self._data.__len__
#
#     @property
#     def __bool__(self):
#         return self._data.__bool__