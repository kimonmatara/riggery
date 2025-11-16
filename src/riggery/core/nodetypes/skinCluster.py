from pathlib import Path
from typing import Literal, Union, Iterator, Optional
import xml.etree.ElementTree as ET

from ..nodetypes import __pool__ as nodes
GeometryFilter = nodes['GeometryFilter']

import maya.cmds as m

import riggery.core as r
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short


class SkinCluster(GeometryFilter):

    #-------------------------------------|    Serialization

    @classmethod
    @short(
        worldSpace='ws',
        positionTolerance='pt',
        method='m',
        loadWeights='lw')
    def createFromXMLFile(
            cls,
            xmlfile:str,
            forceShapeTo:Optional[Union[str, 'nodes.DeformableShape']]=None,
            method:Literal[
                'index', 'nearest', 'bilinear', 'barycentric', 'over'
            ]='index',
            worldSpace:bool=False,
            positionTolerance:Optional[Union[int, float]]=None,
            loadWeights:bool=True
    ):
        # Open the XML file
        tree = ET.parse(xmlfile)
        root = tree.getroot()

        # Get this information from the first available deformer entry:
        # Shape name
        # Deformer name (will assume it's a skinCluster)
        # influence names

        # Determine shape name
        shapeEntry = root.find('shape')
        xmlShapeName = shapeEntry.attrib['name']

        if forceShapeTo:
            shapeName = forceShapeTo
        else:
            shapeName = xmlShapeName

        matches = m.ls(shapeName)
        nm = len(matches)

        if nm == 0:
            raise RuntimeError(
                "Shape doesn't exist: {}".format(shapeName))

        if nm > 1:
            raise RuntimeError(
                "More than one match found for: {}".format(shapeName))

        shape = matches[0]

        # Determine deformer name
        weightEntries = root.findall('weights')

        deformerNames = list(set([weightEntry.attrib['deformer'] \
                                  for weightEntry in weightEntries]))

        nm = len(deformerNames)

        if nm > 1:
            raise RuntimeError(
                "More than one deformers specified inside: {}".format(xmlfile)
            )

        if nm == 0:
            raise RuntimeError(
                "No deformer information found inside: {}".format(xmlfile)
            )

        deformer = deformerNames[0]

        # Deal with existing
        existing = r.nodes.SkinCluster.getFromGeo(shape)

        if existing:
            r.delete(existing)

        # Get influences
        joints = [weightEntry.attrib['source'] \
                  for weightEntry in weightEntries]

        for joint in joints:
            if not m.objExists(joint):
                m.createNode('joint', n=joint)

        # Create the deformer
        args = joints + [shape]
        kwargs = {
            'tsb': True,
            'n': deformerNames[0],
            'bm': 0,
            'dr': 4.5,
            'nw': 1,
            'omi': False,
            'sm': 0,
            'wd': 0
        }

        skin = r.skinCluster(*args, **kwargs)

        # Load weights
        if loadWeights:
            remaps = []

            if str(skin) != deformer:
                # Produced skinCluster name was different
                remaps.append('{};{}'.format(deformer, skin))

            if xmlShapeName != shapeName:
                remaps.append("{};{}".format(xmlShapeName, shapeName))

            kwargs = {}

            if remaps:
                kwargs['remap'] = remaps

            skin.loadWeights(xmlfile,
                             shape=shape,
                             method=method,
                             positionTolerance=positionTolerance,
                             **kwargs)

        return skin

    @classmethod
    def createFromMacro(cls, macro:dict, **overrides) -> 'SkinCluster':
        """
        Recreates a skinCluster using the type of macro returned by
        :meth:`macro`.
        """
        macro = macro.copy()
        macro.update(overrides)

        shape = macro['geometry'][0]
        influences = macro['influence']

        buildArgs = influences + [shape]
        buildKwargs = {k: macro[k] for k in [
            'bindMethod', 'maximumInfluences', 'obeyMaxInfluences',
            'skinMethod', 'weightDistribution', 'name']}

        buildKwargs['toSelectedBones'] = True

        skin = r.skinCluster(*buildArgs, **buildKwargs)[0]

        config = {k: macro[k] for k in
                  ['deformUserNormals', 'useComponents',
                   'envelope', 'dqsSupportNonRigid']}

        for k, v in config.items():
            skin.attr(k).set(v)

        for attrName, attrInfo in macro['dqsScale'].items():
            input = attrInfo['input']
            value = attrInfo['value']
            plug = skin.attr(attrName)

            if input:
                try:
                    r.connectAttr(input, plug)

                except RuntimeError:
                    r.warning(
                        ("Couldn't connect {} into {}; "+
                         "setting the value instead.").format(input, plug)
                    )

                    plug.set(value)
            else:
                plug.set(value)

        return skin

    def macro(self) -> dict:
        """
        :return: A dictionary representation of this skin cluster that can be
            used to restore it later.
        """
        macro = super().macro()
        _self = macro['name']
        influences = list(map(str, self.influences))

        if influences:
            macro['influence'] = influences

        for flag in ['bindMethod',
                     'maximumInfluences',
                     'obeyMaxInfluences',
                     'skinMethod',
                     'weightDistribution']:
            macro[flag] = m.skinCluster(_self, q=True, **{flag:True})

        macro['geometry'] = [str(next(self.shapes))]

        for attrName in ['deformUserNormals',
                         'useComponents',
                         'envelope',
                         'dqsSupportNonRigid']:
            macro[attrName] = self.attr(attrName).get()

        macro['dqsScale'] = dqs = {}

        wlist = [self.attr('dqsScale')]
        wlist += list(wlist[0].children)

        for plug in wlist:
            val = plug()
            inputs = plug.inputs(plugs=True)

            if inputs:
                input = str(inputs[0])
            else:
                input = None

            dqs[plug.attrName()] = {'value': val, 'input': input}

        return macro

    #-------------------------------------|    Influences

    def getInfluence(self) -> list:
        """
        :return: The list of influences driving this skin cluster.
        """
        return list(self.influences)

    @property
    def influences(self) -> Iterator['nodes.Joint']:
        out = m.skinCluster(str(self), q=True, influence=True)

        if out:
            for x in out:
                yield nodes['DependNode'](x)

    #-------------------------------------|    Weights

    def _padBlendWeights(self):
        # Set any missing array indices on ``.blendWeights`` to 0.0. This is a
        # workaround for the following bug:
        #
        # When the ``.blendWeights`` array is sparsely populated, dumping and
        # reloading the attribute via :func:`deformerWeights` results in wrong
        # index mapping.

        plug = self.attr('blendWeights')
        indices = plug.indices()
        shape = next(self.shapes)
        numVertices = shape.numVertices()

        missingIndices = list(sorted(set(range(numVertices))-set(indices)))

        _plug = str(plug)

        for index in missingIndices:
            m.setAttr('{}[{}]'.format(_plug, index), 0.0)

        return missingIndices

    @short(
        remap='r',
        vertexConnections='vc',
        weightTolerance='wt',
        weightPrecision='wp',
        shape='sh',
        attribute='at',
        defaultValue='dv'
    )
    def dumpWeights(
            self,
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
            defaultValue:Optional[Union[int, float]]=None,
            includeBlendWeights:bool=True):
        """
        Overrides
        :meth:`riggery.core.nodetypes.geometryFilter.GeometryFilter.dumpWeights`
        to include DQ blend weights by default, and to work around this bug:

        When the ``.blendWeights`` array on a skinCluster is sparsely populated
        (as is typically the case), dumping and reloading it via
        ``deformerWeights(at='blendWeights')`` results in a wrongindex mapping.
        """
        kwargs = {}

        if includeBlendWeights:
            if attribute is None:
                attribute = []
            else:
                attribute = list(expand_tuples_lists(attribute))

            attribute.append('blendWeights')
            indicesToRemove = self._padBlendWeights()

            kwargs['at'] = attribute

        nodes['GeometryFilter'].dumpWeights(self,
                                            filepath,
                                            sh=shape,
                                            r=remap,
                                            vc=vertexConnections,
                                            wp=weightPrecision,
                                            wt=weightTolerance,
                                            dv=defaultValue,
                                            **kwargs)

        if includeBlendWeights:
            _plug = '{}.blendWeights'.format(self)

            for index in indicesToRemove:
                m.removeMultiInstance('{}[{}]'.format(_plug, index))

        return self

    @short(name='n',
           replace='rep',
           sourceUVSet='suv',
           destUVSet='duv',
           method='m',
           weights='w')
    def copyTo(self,
               *geos,
               replace:bool=True,
               weights:bool=True,
               method:Literal[
                   'index',
                   'nearest',
                   'bilinear',
                   'barycentric',
                   'over',
                   'closestPoint',
                   'closestComponent',
                   'uv',
                   'rayCast'
               ]='index',
               sourceUVSet:Optional[str]=None,
               destUVSet:Optional[str]=None) -> list['SkinCluster']:
        """
        Copies this skinCluster onto the specified geometries.

        :param \*geos: the geometries onto which to replicate the skinCluster
        :param replace/rep: replace existing skinClusters on the destination
            geometries; defaults to True
        :param method/m: One of:
            'index' (XML)
            'nearest' (XML)
            'bilinear' (XML)
            'barycentric' (XML)
            'over' (XML)
            'closestPoint' (Maya command)
            'closestComponent' (Maya command)
            'uv' (Maya command)
            'rayCast' (Maya command)
        :param sourceUVSet/suv: the source UV set for 'uv' mode; defaults to the
            current UV set
        :param destUVSet/suv: the destination UV set for 'uv' mode; defaults to
            the current UV set
        :return: A list of all newly-generated skinClusters.
        """
        macro = self.macro()

        out = []

        for shape in without_duplicates((nodes['DagNode'](x).toShape()
                                         for x in expand_tuples_lists(geos))):

            if replace:
                for existing in self.fromGeo(shape):
                    r.delete(existing)

            thisMacro = macro.copy()
            thisMacro['geometry'] = [shape]

            newSkin = self.createFromMacro(thisMacro).renameFromGeo()

            if weights:
                newSkin.copyWeightsFrom(self,
                                        destShape=shape,
                                        sourceUVSet=sourceUVSet,
                                        destUVSet=destUVSet,
                                        method=method)

            out.append(newSkin)

        return out