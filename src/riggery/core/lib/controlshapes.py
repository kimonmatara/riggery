"""Tools to manage control shapes."""

from typing import Union, Optional, Iterable
from copy import copy, deepcopy
import os
import json

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from ..elem import Elem
from riggery.internal.typeutil import SingletonMeta

from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data


import maya.cmds as m

FILEPATH = os.path.join(os.path.dirname(__file__), 'controlshapes.json')
AUTO_SHAPE_SCALE_FACTOR = 0.01666


class ControlShapesLibrary(metaclass=SingletonMeta):

    __autodump__ = False
    __instance__ = None

    def __init__(self):
        self._data = {}
        self.load()

    #-------------------------------------|    I/O

    def load(self):
        """
        Reads ``FILEPATH`` to populate internal data. If the file is missing, a
        warning will be issued.

        :return: self
        """
        try:
            with open(FILEPATH, 'r') as f:
                self._data = json.load(f)
        except FileNotFoundError:
            m.warning(f"Missing shape library: {FILEPATH}")
        return self

    def dump(self):
        """
        Dumps internal data to ``FILEPATH``.

        :return: self
        """
        with open(FILEPATH, 'w') as f:
            json.dump(self._data, f, indent=4)
        return self

    #-------------------------------------|    Get members

    def keys(self):
        """
        Yields entry names.
        """
        for key in self._data.keys():
            yield key

    def values(self):
        """
        Yields deep copies of entry dictionaries.
        """
        for value in self._data.values():
            yield deepcopy(value)

    def items(self):
        """
        Yields pairs of (entry name, deep copy of entry dict)
        """
        for key, value in self._data.items():
            yield key, deepcopy(value)

    def __getitem__(self, key):
        return deepcopy(self._data[key])

    def __contains__(self, key):
        return key in self.keys()

    def __len__(self):
        return len(self._data)

    def __bool__(self):
        return bool(self._data)

    #-------------------------------------|    Add members

    def __setitem__(self, key, value):
        self._data[key] = deepcopy(value)

    @classmethod
    def _normalize(cls, entry:list) -> None:
        allPoints = []

        for macro in entry:
            allPoints += macro['points']

        bbox = data.BoundingBox.createFromPoints(allPoints)
        mag = bbox.diagonal.length()

        if mag:
            correction = 1.7320508075688772 / bbox.diagonal.length()
            for macro in entry:
                macro['points'][:] = [
                    [point[0] * correction,
                     point[1] * correction,
                     point[2] * correction] \
                    for point in macro['points']
                ]

    @short(normalize='n',
           tags='t',
           dump='d',
           captureOverrideColor='cc',
           force='f')
    def add(self,
            key:str,
            *sources,
            normalize:bool=True,
            tags:Union[str, list, None]=None,
            dump:bool=None,
            captureOverrideColor:bool=False,
            force:bool=False):
        """
        :param key: the entry name
        :param *sources: transforms or shapes from which to extract curve
            shapes
        :param normalize/n: normalize overall shape scale; defaults to True
        :param dump/d: dump immediately to ``FILEPATH``; if omitted, defaults to
            ``True`` if the class ``__autodump__`` attribute is to ``True``,
            otherwise ``False``
        :param captureOverrideColor/cc: capture color overrides; defaults to
            False
        :param force/f: if *key* already exists, suppress :class:`KeyError`
            overwrite the entry; defaults to False
        :raises KeyError: A namesake entry already exists.
        :raises ValueError: No curve shapes were specified.
        :return: self
        """
        if (not force) and key in self:
            raise KeyError(f"key already exists: {key}")

        #-----------------------------|    Sort through *sources

        sources = without_duplicates(map(Elem, expand_tuples_lists(*sources)))
        curveShapes = []
        for source in sources:
            if isinstance(source, nodes.Transform):
                curveShapes += source.getShapes(
                    type=['nurbsCurve', 'bezierCurve'],
                    intermediate=False
                )
            elif isinstance(source, (nodes.NurbsCurve, nodes.BezierCurve)):
                curveShapes.append(source)
        curveShapes = without_duplicates(curveShapes)

        if not curveShapes:
            raise ValueError("no curve shapes specified")

        entry = [curveShape.macro(captureOverrideColor=captureOverrideColor) \
                 for curveShape in curveShapes]

        if normalize:
            self._normalize(entry)

        self[key] = entry

        if dump is None:
            dump = self.__autodump__

        if dump:
            self.dump()

        return self

    #-------------------------------------|    Apply

    @short(shapeAxisRemap='sar',
           shapeScale='ss')
    def apply(self,
              key:str,
              transform,
              shapeScale=None,
              add=False,
              shapeAxisRemap=None):
        """
        :param key: the shape entry name
        :param transform: the transform to apply the entry shapes to
        :param shapeScale: an optional scaling factor
        :param add: don't replace existing curve shapes under *transform*;
            defaults to False
        :param shapeAxisRemap/sar: if provided, should be two or four letter
            axes, defining pairwise remaps for the control shape; defaults to
            None
        :return: The generated shape(s).
        """
        transform = Elem(transform)
        if not add:
            existing = transform.getShapes(intermediate=False)
            for shape in existing:
                m.delete(str(shape))

        entry = self[key]

        if shapeAxisRemap is not None:
            num = len(shapeAxisRemap)
            if num == 2:
                thirdAxis = [ax for ax in 'xyz' \
                             if ax not in (shapeAxisRemap[0].strip('-'),
                                           shapeAxisRemap[1].strip('-'))][0]
                shapeAxisRemap = list(shapeAxisRemap) + [thirdAxis, thirdAxis]

            vecs = {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1],
                    '-x': [-1, 0, 0], '-y': [0, -1, 0], '-z': [0, 0, -1]}

            remapMatrix = data.Matrix.createOrtho(
                shapeAxisRemap[0], vecs[shapeAxisRemap[1]],
                shapeAxisRemap[2], vecs[shapeAxisRemap[3]]
            )

            for macro in entry:
                macro['points'] = [data.Point(point) ^ remapMatrix \
                                   for point in macro['points']]

        out = nodes.NurbsCurve.createFromMacros(entry,
                                                parent=transform,
                                                rescale=shapeScale)

        for macro, shape in zip(entry, out):
            try:
                overrideColor = macro['overrideColor']
            except KeyError:
                continue
            shape.attr('overrideEnabled').set(True)
            shape.attr('overrideColor').set(overrideColor)

        return out

    def test(self, *keys):
        """
        :param keys (optional): the keys to test; if omitted, all keys are
            tested
        """
        if keys:
            keys = without_duplicates(expand_tuples_lists(*keys))
        else:
            keys = list(self.keys())

        for i, key in enumerate(keys):
            parent = self._test(key)
            parent.attr('tx').set(1.25 * i)

    def _test(self, key:str):
        try:
            parent = nodes.Transform.createNode(name=key)
            self.apply(key, parent)
        except KeyError as exc:
            m.delete(str(parent))
            raise exc
        return parent

    #-------------------------------------|    Repr

    def __repr__(self):
        return "<control shapes library>"


CONTROLSHAPES = ControlShapesLibrary()

CONTROLCOLORS = {'red': 13,
                 'green': 14,
                 'yellow': 17,
                 'blue': 6,
                 'black': 1,
                 'white': 16,

                 # Rig 'roles'
                 'left': 6,
                 'left1': 23,
                 'right': 13,
                 'right1': 12,
                 'center': 14,
                 'center1': 23,
                 'options': 16,
                 'options1': 2,
                 'options3': 1}

def deriveShapeScaleFromPoints(points:Iterable, factor=None) -> float:
    """
    Used to improvise shape scales for chains etc. Uses the cumulative vector
    length.
    """
    if factor is None:
        factor = AUTO_SHAPE_SCALE_FACTOR
    points = list(map(data['Point'], points))
    vectors = ((p2-p1) for p1, p2 in zip(points, points[1:]))
    length = sum((vector.length() for vector in vectors))
    return length * factor

def showcase():
    """
    Starts a new scene and generates all the current control shapes for
    inspection.
    """
    m.file(newFile=True, force=True)
    CONTROLSHAPES.test()