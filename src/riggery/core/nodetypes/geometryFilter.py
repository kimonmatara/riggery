from functools import partial
import json
from pathlib import Path
import os
from typing import Iterator, Union, Optional, Literal, Iterable, Callable

from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short
from riggery.general.strings import cap

from riggery.core.lib import names as _nm
from riggery.core.lib import xmlweights as _xw

from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
DependNode = nodes['DependNode']

import maya.cmds as m
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma


class GeometryFilter(DependNode):
    """
    To implement deformer archiving:

        -   Implement macro() concisely (don't worry about class mapping, that
            should happen externally)
        -   Implement createFromMacro() concisely
        -   Implement _applyReplacerToArchiveMacro() to perform name
            on a macro where requested
        -   If / where needed, overload _loadWeightsFromArchive(),
            createFromArchive(), or dumpArchive()

    To implement granular weight management:

        -   Implement _getWeightsForShapeAndChannel() / _setWeightsForShapeAndChannel()
        -   Implement _getChannelIndex()
    """
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

    # __archive_extra_attrs__ = None

    #-------------------------------------|    Archiving

    def _resolveArchiveDumpShapes(self,
                                  shapes=None) -> list['nodes.DeformableShape']:

        ourShapes = list(self.shapes)

        if shapes:
            shapes = expand_tuples_lists(shapes)
            shapes = (nodes['DagNode'](x).toShape() for x in shapes)
            shapes = without_duplicates(shapes)
            shapes = (x for x in shapes if x is not None and x in ourShapes)
            shapes = list(shapes)
        else:
            shapes = ourShapes

        return shapes

    def _archiveDumpShapeXMLWeights(self,
                                    filePath:Path,
                                    shape:'nodes.DeformableShape'):
        """Here as a hook for per-deformer implementations."""

        self.dumpWeights(filePath, shape=shape, vertexConnections=True)

    def _generateMacroForArchive(self) -> dict:
        return self.macro()

    def _generateArchiveInfoContent(self) -> dict:
        out = {'deformerName': str(self),
               'deformerNodeType': self.__melnode__,
               'deformerMacro': self._generateMacroForArchive()}

        shapeInfos = {}
        shapeOrder = []

        deformerName = str(self)
        deformerNameNoNs = deformerName.split(':')[-1]

        for shape in self.shapes:
            shapeShortName = shape.shortName()
            shapeShortNameNoNs = shapeShortName.split(':')[-1]

            shapeInfo = {
                'transformName': shape.parent.shortName(),
                'xmlWeights': '{}_on_{}_weights.xml'.format(deformerNameNoNs,
                                                            shapeShortNameNoNs)
            }
            shapeInfos[shapeShortName] = shapeInfo
            shapeOrder.append(shapeShortName)

        if shapeInfos:
            out['shapeOrder'] = shapeOrder
            out['shapeInfos'] = shapeInfos

        return out

    def dumpArchive(self,
                    parentDir:Union[str, Path],
                    shapes:Optional[
                        Union[
                            'nodes.DagNode',
                            Iterable['nodes.DagNode']
                        ]
                    ]=None, /) -> dict:

        # Resolve parent dir
        parentDir = Path(parentDir)

        if not parentDir.is_dir():
            raise FileNotFoundError(
                "Parent directory doesn't exist: {}".format(parentDir)
            )

        # Resolve info file path
        deformerName = self.shortName()
        deformerNameNoNs = deformerName.split(':')[-1]
        infoFileName = "{}_info.json".format(deformerNameNoNs)
        infoFilePath = parentDir / infoFileName

        # Generate info data
        infoContent = self._generateArchiveInfoContent()
        infoContentJson = json.dumps(infoContent, indent=4)

        # Dump the info file
        with open(infoFilePath, 'w') as f:
            f.write(infoContentJson)

        print("Wrote: {}".format(infoContentJson))

        # Resolve the shapes worklist
        shapes = self._resolveArchiveDumpShapes(shapes)

        # Dump XML weights for each shape
        for shape in shapes:
            shapeNameNoNs = shape.shortName(sns=True)
            fileName = "{}_on_{}_weights.xml".format(deformerNameNoNs,
                                                     shapeNameNoNs)
            filePath = parentDir / fileName
            self._archiveDumpShapeXMLWeights(filePath, shape)

        return {'infoFilePath': infoFilePath,
                'info': infoContent,
                'dumpedShapes': shapes}

    @classmethod
    def _applyReplacerToArchiveMacro(cls,
                                     replacer:Callable,
                                     macro:dict) -> None:
        """
        The *replacer* is a one-shot function that pre-applies any substitutions
        defined in the ``remap`` argument for ``deformerWeights()``.

        This method should be implemented by the subclasses to edit the macro
        in-place, updating any relevant string content (e.g. references to
        influences, targets, geometry, deformers, etc).

        :param replacer: the string-substitution callable
        :param macro: the deformer macro loaded from the 'info' file in the
            deformer archive
        :return: None. This is an in-place operation.
        """
        pass

    def _loadWeightsFromArchive(self,
                                info:dict,
                                infoFilePath:Path, *,
                                method='index',
                                remap=None):
        """
        Extend / overload this for sidecar weight loading (e.g. for skinCluster
        blend weights).
        """
        if not remap:
            remap = []

        _self = str(self)
        specDeformerName = info['deformerName']

        if specDeformerName != _self:
            remap.append(r'^'+specDeformerName+'$;'+_self)

        if remap:
            replacer = _xw.remapToReplacer(remap)

        pdir = infoFilePath.parent
        xmlKwargs = {'method': method}

        if remap:
            xmlKwargs['remap'] = remap

        for shapeName, shapeInfo in info.get('shapeInfos', {}).items():
            xmlFileName = shapeInfo['xmlWeights']
            xmlFilePath = pdir / xmlFileName

            if remap:
                shapeName = replacer(shapeName)

            if xmlFilePath.is_file():
                try:
                    _xw.load(xmlFilePath,
                             shape=shapeName,
                             deformer=_self,
                             **xmlKwargs)
                    print("Loaded: {}".format(xmlFileName))
                except Exception as e:
                    m.warning(
                        "Couldn't load XML weights from {}: {}".format(
                            xmlFileName,
                            e
                        )
                    )

    def loadWeightsFromArchive(self,
                               infoFilePath:Union[str, Path], *,
                               method:Literal[
                                   'index', 'nearest', 'barycentric',
                                   'bilinear', 'over'
                               ]='index',
                               remap:Optional[Union[str, Iterable[str]]]=None):
        infoFilePath = Path(infoFilePath)

        with open(infoFilePath, 'r', encoding='utf-8') as f:
            data = f.read()

        data = json.loads(data)

        self._loadWeightsFromArchive(data,
                                     infoFilePath,
                                     method=method,
                                     remap=remap)

    @classmethod
    @short(method='m', remap='r', loadWeights='lw')
    def createFromArchive(cls,
                          infoFilePath:Union[str, Path],
                          method:Literal[
                              'index', 'nearest', 'barycentric',
                              'bilinear', 'over'
                          ]='index',
                          remap:Optional[Union[str, Iterable[str]]]=None,
                          loadWeights:bool=True,
                          **createFromMacroKwargs) -> dict:
        """
        How to format *remap* argument
        ------------------------------
        Provide this as a list of strings. Each string should be formatted
        like this:

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

        :param remap/r: forwarded to ``deformerWeights``, and also parsed to
            update the deformer macro (where the class implementation
            supports it)
        """
        #--------------|    Load the archive info

        infoFilePath = Path(infoFilePath)

        with open(infoFilePath, 'r', encoding='utf-8') as f:
            info = f.read()

        info = json.loads(info)

        #--------------|    Ask subclass to update the macro

        deformerMacro = info['deformerMacro']

        if remap:
            remap = _xw.expandRemapArg(remap)
            replacer = _xw.remapToReplacer(remap)
            cls._applyReplacerToArchiveMacro(replacer, deformerMacro)
        else:
            remap = []

        #--------------|    Use the macro to recreate the deformer

        deformer = cls.createFromMacro(deformerMacro, **createFromMacroKwargs)
        finalDeformerName = str(deformer)

        #--------------|    If final deformer name is different, update the XML
        #--------------|    spec

        specDeformerName = info['deformerName']

        if finalDeformerName != specDeformerName:
            remap.append(r'^'+specDeformerName+r'$;'+finalDeformerName)

            # Update it even if we don't use it later, in case we want to pass
            # it along
            replacer = _xw.remapToReplacer(remap)

        #--------------|    Load weights

        if loadWeights:
            deformer._loadWeightsFromArchive(info,
                                             infoFilePath,
                                             method=method,
                                             remap=remap)

        return deformer

    #-------------------------------------|    Granular weight management

    def getNumPoints(self, shapeIndex:int) -> int:
        shape = self._getShapeMObjectAtIndex(shapeIndex)

        if shape.hasFn(om.MFn.kMesh):
            return om.MFnMesh(shape).numVertices

        if shape.hasFn(om.MFn.kNurbsCurve):
            return om.MFnNurbsCurve(shape).numCVs

        if shape.hasFn(om.MFn.kNurbsSurface):
            fn = om.MFnNurbsSurface(shape)
            return fn.numCVsInU * fn.numCVsInV

        if shape.hasFn(om.MFn.kLattice):
            fn = om.MFnDependencyNode(shape)
            numS = fn.findPlug("sDivisions", False).asInt()
            numT = fn.findPlug("tDivisions", False).asInt()
            numU = fn.findPlug("uDivisions", False).asInt()
            return numS * numT * numU

        raise TypeError(
            "unsupported geometry type: {}".format(shape.apiTypeStr)
        )

    def _getShapeMObjectAtIndex(self, shapeIndex:int) -> om.MObject:
        return self._getShapeMDagPathAtIndex(shapeIndex).node()

    def _getShapeMDagPathAtIndex(self, shapeIndex:int) -> om.MDagPath:
        return oma.MFnGeometryFilter(
            self.__apimobject__()
        ).getPathAtIndex(shapeIndex)

    def getShapeAtIndex(self, shapeIndex:int) -> 'nodes.DeformableShape':
        """
        :return: The shape at the specified deformer index.
        """
        return nodes['DeformableShape'].fromMObject(
            self._getShapeMDagPathAtIndex(shapeIndex)
        )

    def getShapeIndex(self, shape:Union['nodes.DagNode', str]) -> int:
        """
        :param shape: the output (deformed) shape
        :return: The logical index for the deformed shape.
        """
        shape = nodes['DagNode'](shape).toShape().__apimobject__()
        fn = om.MFnGeometryFilter(self.__apimobject__())
        return fn.indexForOutputShape(shape)

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