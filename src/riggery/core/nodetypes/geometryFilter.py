from pathlib import Path
import os
from typing import Iterator, Union, Optional, Literal

from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short

from riggery.core.lib import names as _nm
from riggery.core.lib import xmlweights as _xw

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
DependNode = nodes['DependNode']

import maya.cmds as m


class GeometryFilter(DependNode):

    #-------------------------------------|    Constructors

    @classmethod
    def fromGeo(cls, geo) -> Iterator['GeometryFilter']:
        """
        Yields deformers of this type in the specified geometry's history. Use
        next([...], None) to get the first result or None.
        """
        geo = nodes['DependNode'](geo).toShape()
        history = m.listHistory(geo, fullNodeName=True, historyAttr=True)
        visited = set()

        if history:
            for item in history:
                if item in visited:
                    continue
                try:
                    if m.objectType(item, isAType=cls.__melnode__):
                        visited.add(item)
                        yield DependNode(item)
                except:
                    continue

    #-------------------------------------|    Membership

    def addGeo(self, *geo):
        """
        Thin wrapper for :func:`maya.cmds.deformer` in edit mode.
        """
        shapes = list(
            without_duplicates(map(str, (nodes['DagNode'](x).toShape()
                                         for x in expand_tuples_lists(*geo))))
        )

        if shapes:
            m.deformer(str(self), e=True, geometry=shapes)

        return self

    def removeGeo(self, *geo):
        """
        Thin wrapper for :func:`maya.cmds.deformer` in edit mode.
        """
        shapes = list(
            without_duplicates(map(str, (nodes['DagNode'](x).toShape()
                                         for x in expand_tuples_lists(*geo))))
        )

        if shapes:
            m.deformer(str(self), e=True, geometry=shapes, remove=True)

        return self

    #-------------------------------------|    Shapes

    @property
    def shapes(self) -> Iterator['GeometryFilter']:
        """Iterates over shapes affected by this deformer."""
        out = m.deformer(str(self), q=True, g=True)

        if out:
            for x in out:
                yield nodes['DependNode'](x)

    #-------------------------------------|    Weights

    @short(destShape='ds',
           sourceShape='ss',
           sourceUVSet='suv',
           destUVSet='duv',
           method='m')
    def copyWeightsFrom(
            self,
            sourceDeformer:Union[str, 'GeometryFilter'],
            sourceShape:Optional[Union[str, 'nodes.DeformableShape']]=None,
            destShape:Optional[Union[str, 'nodes.DeformableShape']]=None,
            sourceUVSet:Optional[str]=None,
            destUVSet:Optional[str]=None,
            method:Literal[
                'index',
                'bilinear',
                'barycentric',
                'nearest',
                'over',

                'closestPoint',
                'closestComponent',
                'uv',
                'rayCast'
            ]='index'
    ):
        """
        Copies weights from another deformer to this one.

        :param sourceDeformer: the deformer to copy weights from
        :param sourceShape/ssh: the shape to copy weights from; if omitted,
            defaults to the first detected shape
        :param destShape/dsh: the shape to copy weights to; if omitted,
            defaults to the first detected shape
        :param sourceUVSet/suv: if specified, 'method' will be overriden to
            'uv'; if omitted, and 'method' is 'uv', the current UV set will
            be used; defaults to None
        :param destUVSet/duv: if specified, 'method' will be overriden to
            'uv'; if omitted, and 'method' is 'uv', the current UV set will
            be used; defaults to None
        :param str method/m: one of:

            - ``index`` (via XML)
            - ``bilinear`` (via XML)
            - ``barycentric`` (via XML)
            - ``nearest`` (via XML)
            - ``over`` (via XML)

            - ``closestPoint`` (in-scene)
            - ``closestComponent`` (in-scene)
            - ``uv`` (in-scene)
            - ``rayCast`` (in-scene)

        :raises RuntimeError: No shapes on deformer.
        :return: ``self``
        """
        DependNode = nodes['DependNode']

        sourceDeformer = DependNode(sourceDeformer)

        if sourceShape:
            sourceShape = DependNode(sourceShape).toShape()

        else:
            sourceShape = next(sourceDeformer.shapes, None)

            if sourceShape is None:
                raise RuntimeError("No shapes on deformer")

        if destShape:
            destShape = DependNode(destShape).toShape()

        else:
            destShape = next(self.shapes, None)

            if destShape is None:
                raise RuntimeError("No shapes on deformer")

        if sourceUVSet or destUVSet:
            method = 'uv'

        if method in ('over', 'index', 'nearest',
                      'bilinear', 'barycentric'):
            self._copyWeightsViaXMLFrom(
                sourceDeformer, sourceShape, destShape, method
            )
        else:
            self._copyWeightsViaCmdFrom(sourceDeformer,
                                        sourceShape,
                                        destShape,
                                        method,
                                        sourceUVSet=sourceUVSet,
                                        destUVSet=destUVSet)
        return self

    def _copyWeightsViaXMLFrom(self,
                               sourceDeformer,
                               sourceShape,
                               destShape,
                               method):
        kwargs = {}

        bothSkins = sourceDeformer.__melnode__ == \
                    'skinCluster' and self.__melnode__ == 'skinCluster'

        if bothSkins:
            kwargs['attribute'] = 'blendWeights'

        tmpPath = _xw.getTempFilePath()

        vertexConnections = method in ('bilinear', 'barycentric')
        sourceDeformer.dumpWeights(tmpPath, vc=vertexConnections, **kwargs)

        remap = ['{};{}'.format(str(sourceDeformer), str(self)),
                 '{};{}'.format(str(sourceShape).split('|')[-1],
                                str(destShape).split('|')[-1])]

        try:
            self.loadWeights(tmpPath, method=method, remap=remap, **kwargs)

        finally:
            os.remove(tmpPath)

    def _copyWeightsViaCmdFrom(self,
                               sourceDeformer,
                               sourceShape,
                               destShape,
                               method,
                               sourceUVSet=None,
                               destUVSet=None):
        if sourceUVSet or destUVSet:
            method = 'uv'

        if method == 'uv':
            if not sourceUVSet:
                sourceUVSet = sourceShape.uvSet

            if not destUVSet:
                destUVSet = destShape.uvSet

        kwargs = {'nm': True}

        uv = method == 'uv'

        if method == 'uv':
            kwargs['uvSpace'] = [sourceUVSet, destUVSet]

        else:
            kwargs['sa'] = method

        _sourceDeformer = str(sourceDeformer)
        _destDeformer = str(self)

        if sourceDeformer.__melnode__ == 'skinCluster' \
                and self.__melnode__ == 'skinCluster':

            cmd = m.copySkinWeights
            kwargs['ss'] = _sourceDeformer
            kwargs['ds'] = _destDeformer
            kwargs['ia'] = 'oneToOne'

        else:
            cmd = m.copyDeformerWeights
            kwargs['sd'] = _sourceDeformer
            kwargs['ds'] = _destDeformer
            kwargs['ss'] = str(sourceShape)
            kwargs['ds'] = str(destShape)

        cmd(**kwargs)

    #-------------------------------------|    XML weight I/O

    @short(attribute='at',
           defaultValue='dv',
           deformer='df',
           shape='sh',
           weightPrecision='wp',
           weightTolerance='wt',
           vertexConnections='vc',
           remap='r')
    def dumpWeights(self,
                    filepath:Union[str, Path],
                    shape:Optional[Union[
                        str,
                        list[str],
                        'nodes.DeformableShape',
                        list['nodes.DeformableShape']]]=None,
                    remap:Optional[str]=None,
                    vertexConnections:bool=False,
                    weightPrecision:int=3,
                    weightTolerance:float=0.001,
                    attribute:Optional[Union[
                        str,
                        list[str],
                        'plugs.Attribute',
                        list['plugs.Attribute']
                    ]]=None,
                    defaultValue:Optional[Union[int, float]]=None):
        """
        Wrapper for :func:`~maya.cmds.deformerWeights` in 'export' mode.
        Arguments are post-processed to ensure that only relevant deformers and
        shapes are included. See Maya help for :func:`deformerWeights` for
        complete flag information.
        """
        if shape:
            shape = list(map(str, expand_tuples_lists(shape)))

        if attribute:
            attribute = list(map(str, expand_tuples_lists(attribute)))

        _xw.dump(filepath,
                 deformer=str(self),
                 shape=shape,
                 remap=remap,
                 vertexConnections=vertexConnections,
                 weightPrecision=weightPrecision,
                 weightTolerance=weightTolerance,
                 attribute=attribute,
                 defaultValue=defaultValue)

        return self

    @short(shape='sh',
           method='m',
           worldSpace='ws',
           attribute='at',
           ignoreName='ig',
           positionTolerance='pt',
           remap='r')
    def loadWeights(
            self,
            filepath:Union[str, Path],
            shape:Optional[Union[
                str,
                list[str],
                'nodes.DeformableShape',
                list['nodes.DeformableShape']]]=None,
            method:Literal[
                'index', 'nearest', 'barycentric',
                'bilinear', 'over'
            ]='index',
            worldSpace:Optional[bool]=None,
            attribute:Optional[Union[
                str,
                list[str],
                'plugs.Attribute',
                list['plugs.Attribute']
            ]]=None,
            ignoreName:bool=False,
            positionTolerance:Optional[Union[int, float]]=None,
            remap:Optional[str]=None
    ):
        """
        Wrapper for :func:`~maya.cmds.deformerWeights` in 'import' mode.
        Arguments are post-processed to ensure that only relevant deformers and
        shapes are included. See Maya help for :func:`deformerWeights` for
        complete flag information.
        """
        if shape:
            shape = list(map(str, expand_tuples_lists(shape)))

        if attribute:
            attribute = list(map(str, expand_tuples_lists(attribute)))

        _xw.load(filepath,
                 deformer=str(self),
                 shape=shape,
                 remap=remap,
                 method=method,
                 worldSpace=worldSpace,
                 attribute=attribute,
                 ignoreName=ignoreName,
                 positionTolerance=positionTolerance)

        return self

    #-------------------------------------|    Name

    @classmethod
    def _deriveNameFromGeo(cls, geo):
        geo = nodes.DependNode(geo).toTransform()
        name = geo.shortName(stripTypeSuffix=True)
        return "{}_{}".format(name, cls.__typesuffix__)

    def renameFromGeo(self):
        """
        Names this deformer after the transform of the shape it affects.
        """
        shape = next(self.shapes, None)

        if shape is not None:
            self.rename(self._deriveNameFromGeo(shape))

        return self