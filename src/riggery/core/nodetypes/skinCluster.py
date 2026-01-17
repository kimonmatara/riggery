from copy import deepcopy
import re
import os
import shutil
from tempfile import gettempdir
from pathlib import Path
from typing import Literal, Union, Iterator, Optional, Iterable
import xml.etree.ElementTree as ET

from ..nodetypes import __pool__ as nodes
GeometryFilter = nodes['GeometryFilter']

import maya.cmds as m

import riggery.core as r
from riggery.core.lib import skinwtio as _sw
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short

class SkinCluster(GeometryFilter):

    #-------------------------------------|    Contructors

    @classmethod
    @short(maximumInfluences='mi',
           obeyMaxInfluences='omi',
           skinMethod='sm',
           weightDistribution='wd',
           bindMethod='bm',
           dropoffRate='dr',
           normalizeWeights='nw',
           removeUnusedInfluence='rui',
           toSelectedBones='tsb',
           name='n')
    def create(cls,
               *jointsAndGeo, # geo last, to match Maya
               name:Optional[str]=None,
               maximumInfluences:Optional[int]=None,
               obeyMaxInfluences:Optional[bool]=None,
               skinMethod:int=0, # linear
               weightDistribution:int=0, # distance
               bindMethod:int=0, # closest distance
               dropoffRate:Optional[float]=None,
               normalizeWeights:int=1, # interactive,
               removeUnusedInfluence:bool=False,
               toSelectedBones:bool=True):

        jointsAndGeo = expand_tuples_lists(jointsAndGeo)

        if name is None:
            name = cls._deriveNameFromGeo(jointsAndGeo[-1])

        kwargs = {'name': name}

        for k, v in zip(
                ('maximumInfluences', 'obeyMaxInfluences',
                 'dropoffRate'),
                (maximumInfluences, obeyMaxInfluences, dropoffRate)
        ):
            if v is not None:
                kwargs[k] = v

        return r.skinCluster(*jointsAndGeo, **kwargs)[0]

    @classmethod
    @short(bindMethod='bm',
           maximumInfluences='mi',
           falloff='fo')
    def createAsGeomVoxel(cls,
                          *args,
                          maximumInfluences:Optional[int]=None,
                          validateVoxelState:bool=True,
                          resolution:int=256,
                          falloff:float=0.2,
                          rebuild:bool=False,
                          **buildKwargs) -> 'SkinCluster':
        """
        A more controlled constructor for geom-voxel mode skinClusters.
        """
        skin = r.skinCluster(*args, bm=3, mi=maximumInfluences, **buildKwargs)
        kwargs = {'fo': falloff, 'gvp': [resolution, validateVoxelState]}

        if maximumInfluences is not None:
            kwargs['mi'] = maximumInfluences

        r.geomBind(skin, bm=3, **kwargs)

        if rebuild:
            skin = skin.rebuild()

        return skin

    #-------------------------------------|    Retrievals

    @classmethod
    def fromVerts(cls, *verts:Union[str, list[str]]) -> Iterator['SkinCluster']:
        """
        :return: Skin clusters driving the specified vertices.
        """
        verts = list(filter(
            lambda x: re.match(r"^.*?\.vtx\[.*?]$", x),
            without_duplicates(expand_tuples_lists(*verts))
        ))

        if verts:
            visited = set()
            sceneSkinClusters = m.ls(type='skinCluster')

            if sceneSkinClusters:
                out = []
                skinMap = {}

                for skinCluster in sceneSkinClusters:
                    shape = m.skinCluster(skinCluster, q=True, geometry=True)

                    if shape:
                        shape = shape[0]

                        if m.nodeType(shape) == 'mesh':
                            skinMap.setdefault(skinCluster, []
                                               ).append(shape+'.vtx[:]')

                if skinMap:
                    for vert in verts:
                        for skinCluster, skinnedRange in skinMap.items():
                            if vert in set(m.ls(skinnedRange, flatten=True)):
                                if skinCluster not in visited:
                                    visited.add(skinCluster)
                                    yield nodes['DependNode'](skinCluster)

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
        """
        Completely resurrects a skinCluster from an XML file. The XML file must
        be atomic (i.e. one shape, one skinCluster).
        """
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
                "More than one deformer specified inside: {}".format(xmlfile)
            )

        if nm == 0:
            raise RuntimeError(
                "No deformer information found inside: {}".format(xmlfile)
            )

        deformer = deformerNames[0]

        # Deal with existing
        existing = list(r.nodes.SkinCluster.fromGeo(shape))

        if existing:
            r.delete(existing)

        # Get influences
        joints = [weightEntry.attrib['source'] for weightEntry in weightEntries]

        for joint in joints:
            if not m.objExists(joint):
                m.createNode('joint', n=joint)

        # Create the deformer
        args = joints + [shape]

        kwargs = {'tsb': True,
                  'n': deformerNames[0],
                  'bm': 0,
                  'dr': 4.5,
                  'nw': 1,
                  'omi': False,
                  'sm': 0,
                  'wd': 0}

        skin = r.skinCluster(*args, **kwargs)[0]

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

    # @classmethod
    # def createFromMacro(cls, macro:dict, **overrides) -> 'SkinCluster':
    #     """
    #     Recreates a skinCluster using the type of macro returned by
    #     :meth:`macro`.
    #     """
    #     macro = macro.copy()
    #     macro.update(overrides)
    #
    #     shape = macro['geometry'][0]
    #     influences = macro['influence']
    #
    #     buildArgs = influences + [shape]
    #     buildKwargs = {k: macro[k] for k in [
    #         'bindMethod', 'maximumInfluences', 'obeyMaxInfluences',
    #         'skinMethod', 'weightDistribution', 'name']}
    #
    #     buildKwargs['toSelectedBones'] = True
    #
    #     skin = r.skinCluster(*buildArgs, **buildKwargs)[0]
    #
    #     config = {k: macro[k] for k in
    #               ['deformUserNormals', 'useComponents',
    #                'envelope', 'dqsSupportNonRigid']}
    #
    #     for k, v in config.items():
    #         skin.attr(k).set(v)
    #
    #     for attrName, attrInfo in macro['dqsScale'].items():
    #         input = attrInfo['input']
    #         value = attrInfo['value']
    #         plug = skin.attr(attrName)
    #
    #         if input:
    #             try:
    #                 r.connectAttr(input, plug)
    #
    #             except RuntimeError:
    #                 r.warning(
    #                     ("Couldn't connect {} into {}; "+
    #                      "setting the value instead.").format(input, plug)
    #                 )
    #
    #                 plug.set(value)
    #         else:
    #             plug.set(value)
    #
    #     return skin

    # def macro(self) -> dict:
    #     """
    #     :return: A dictionary representation of this skin cluster that can be
    #         used to restore it later.
    #     """
    #     macro = super().macro()
    #     _self = macro['name']
    #     influences = list(map(str, self.influence))
    #
    #     if influences:
    #         macro['influence'] = influences
    #
    #     for flag in ['bindMethod',
    #                  'maximumInfluences',
    #                  'obeyMaxInfluences',
    #                  'skinMethod',
    #                  'weightDistribution']:
    #         macro[flag] = m.skinCluster(_self, q=True, **{flag:True})
    #
    #     macro['geometry'] = [str(next(self.shapes))]
    #
    #     for attrName in ['deformUserNormals',
    #                      'useComponents',
    #                      'envelope',
    #                      'dqsSupportNonRigid']:
    #         macro[attrName] = self.attr(attrName).get()
    #
    #     macro['dqsScale'] = dqs = {}
    #
    #     wlist = [self.attr('dqsScale')]
    #     wlist += list(wlist[0].children)
    #
    #     for plug in wlist:
    #         val = plug()
    #         inputs = plug.inputs(plugs=True)
    #
    #         if inputs:
    #             input = str(inputs[0])
    #         else:
    #             input = None
    #
    #         dqs[plug.attrName()] = {'value': val, 'input': input}
    #
    #     return macro

    def _deriveCreateArgsKwargs(self) -> tuple[tuple, dict]:
        args = list(map(str, self.influence)) + [str(next(self.shapes))]
        _self = str(self)
        kwargs = {k: m.skinCluster(_self, q=True, **{k:True})
                  for k in ('maximumInfluences',
                            'obeyMaxInfluences',
                            'skinMethod',
                            'weightDistribution',
                            'bindMethod',
                            'normalizeWeights')}
        kwargs.update({'toSelectedBones': True, 'name': str(self)})
        return args, kwargs

    #-------------------------------------|    Influences

    def getInfluence(self) -> list:
        """
        :return: The list of influences driving this skin cluster.
        """
        return list(self.influence)

    @property
    def influence(self) -> Iterator['nodes.Joint']:
        out = m.skinCluster(str(self), q=True, influence=True)

        if out:
            for x in out:
                yield nodes['DependNode'](x)

    def addInfluence(self, *influences, preserveWeights:bool=False):
        """
        :param \*influences: one or more influences to add
        :param preserveWeights: if this is on, new influences will be added with
            a weight of 0.0; defaults to False
        """
        skin = str(self)

        influencesToAdd = without_duplicates(
            map(str, expand_tuples_lists(*influences))
        )

        existingInfluences = m.skinCluster(skin,
                                           q=True, weightedInfluence=True)

        if existingInfluences:
            influencesToAdd = (x for x in influencesToAdd
                               if x not in existingInfluences)

        kw = {}

        if preserveWeights:
            kw['lw'] = True
            kw['wt'] = 0.0

        for infl in influencesToAdd:
            m.skinCluster(skin, e=True, ai=infl, **kw)

            if preserveWeights:
                m.setAttr('{}.liw'.format(infl), 0)

        return self

    def removeInfluence(self, *influences, quiet:bool=False):
        """
        :param \*influences: one or more influences to remove
        :param quiet: suppress ``RuntimeError`` and skip joints that aren't on
            this skin cluster's influence list; defaults to False
        """
        influences = list(map(str, expand_tuples_lists(*influences)))

        if influences:
            _self = str(self)

            if quiet:
                for influence in influences:
                    try:
                        m.skinCluster(_self, e=True, ri=influence)
                    except RuntimeError:
                        continue
            else:
                m.skinCluster(_self, e=True, ri=influences)

        return self

    def removeUnusedInfluence(self):
        """Removes unused influences."""
        skin = str(self)
        allInfls = m.skinCluster(skin, q=True, influence=True)
        wtInfls = m.skinCluster(skin, q=True, weightedInfluence=True)

        if allInfls and wtInfls:
            inflsToRemove = set(allInfls)-set(wtInfls)

            for infl in inflsToRemove:
                m.skinCluster(skin, e=True, ri=infl)

        return self

    def getPerComponentWeights(self):
        """
        Weights will be returned, and should be set, using a list of
        lists: [
            Per-joint weights for component #0: [weight, weight...],
            Per-joint weights for component #1: [weight, weight...],
            Per-joint weights for component #2: [weight, weight...]
            ...
        ]
        """
        return _sw.SkinClusterWeightsWrangler(str(self)).getWeights()

    def setPerComponentWeights(self, weights):
        """
        Weights will be returned, and should be set, using a list of
        lists: [
            Per-joint weights for component #0: [weight, weight...],
            Per-joint weights for component #1: [weight, weight...],
            Per-joint weights for component #2: [weight, weight...]
            ...
        ]
        """
        _sw.SkinClusterWeightsWrangler(str(self)).setWeights(weights)

    @short(influenceAssociation='ia', surfaceAssociation='sa',autoLabel='al')
    def mirrorWeights(
            self,
            influenceAssociation:Literal[
                "closestJoint",
                "closestBone",
                "label",
                "name",
                "oneToOne"
            ]='closestJoint',
            surfaceAssociation:Literal[
                "closestPoint",
                "rayCast",
                "closestComponent"
            ]='closestComponent',
            autoLabel:bool=False
    ):
        """
        :param bool autoLabel/al: if this is ``True``, *influenceAssociation*
            will be overriden to 'label', and joint labels auto-configured
            based on L_ or R_ prefixes (labels will be reverted after
            mirroring); defaults to ``False``
        :return: ``self``
        """
        if autoLabel:
            elems = ['label']
            if influenceAssociation != 'label':
                elems.append(influenceAssociation)
            else:
                elems.append('closestJoint')

            states = {joint:joint.autoLabel() for joint in self.getInfluence()}
            influenceAssociation = elems

        r.copySkinWeights(ss=self,
                          ds=self,
                          ia=influenceAssociation,
                          sa=surfaceAssociation,
                          mm='YZ')

        if autoLabel:
            for joint, state in states.items():
                joint.setLabelState(state)

        return self

    def clampMaxInfluences(self, maxInfluences:int=4, normalizeAround=None):
        """
        An alternative method to limit influences (for, say, a games
        engine). Doesn't use Maya's obeyMaxInfluences / maxInfluences;
        rather sets all influences lower than the *maxInfluences* to
        0.0. In some cases this yields a closer visual match.

        The *obeyMaxInfluences* flag isn't edited at all. If it's on,
        it will be left on.

        :param normalizeAround: try to prioritize preserving the weight of
            these joints when normalizing; defaults to ``None``
        """
        availInfls = list(self.influence)
        r.skinCluster(self, e=True, fnw=True)

        if normalizeAround:
            if isinstance(normalizeAround, (tuple, list)):
                normalizeAround = list(normalizeAround)
            else:
                normalizeAround = [normalizeAround]
            inflNames = [str(x).split('|')[-1] for x in availInfls]
            anchorIndices = [inflNames.index(x) for x in normalizeAround]

        perCompWeights = self.getPerComponentWeights()

        numInfls = len(availInfls)

        if numInfls <= maxInfluences:
            print("No need to clamp, already at max influences.")
            return

        inflIndices = list(range(numInfls))

        for compIndex, weights in enumerate(perCompWeights):
            pairs = [[i, w] for i, w in zip(inflIndices, weights)]

            if normalizeAround:
                hasAnchorWeights = any(
                    [pairs[i][1] > 0.0 for i in anchorIndices]
                )
                if hasAnchorWeights:
                    keyer = lambda pair: 10000.0 \
                        if pair[0] in anchorIndices else pair[1]
                else:
                    keyer = lambda pair: pair[1]
            else:
                keyer = lambda pair: pair[1]

            # Reorder, largest weights first
            pairs = list(reversed(sorted(pairs, key=keyer)))

            for i in range(maxInfluences, numInfls):
                pairs[i][1] = 0.0

            pairs.sort(key=lambda x: x[0])
            weights = [pair[1] for pair in pairs]

            perCompWeights[compIndex] = weights

        self.setPerComponentWeights(perCompWeights)
        r.skinCluster(self, e=True, fnw=True)

        print("Clamping done.")

        return self

    #-------------------------------------|    Weights

    @short(maximumInfluences='mi')
    def configInfluencesForRealtimeBETA(self, maximumInfluences:int=4):
        """
        Restricts influences while preserving as much weight detail as possible.
        """
        # Basics
        r.skinCluster(self, e=True, nw=1) # interactive
        geo = str(self.getGeometry()[0])
        r.skinPercent(self, f"{geo}.vtx[:]", normalize=True)

        # Dump weights somewhere safe
        tempdir = gettempdir()
        tempfile = os.path.join(tempdir, 'infl_constr_tmp_weights.xml')
        self.dumpWeights(tempfile, shape=self.getGeometry()[0])

        # Constrain
        r.skinCluster(self, e=True, mi=maximumInfluences, omi=True)

        # Load weights
        self.loadWeights(tempfile, method='index')
        r.skinCluster(self, e=True, fnw=True)

        os.remove(tempfile)
        return self

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
        ``deformerWeights(at='blendWeights')`` results in a wrong index mapping.
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

            thisMacro = deepcopy(macro)
            args, kwargs = thisMacro['createArgsKwargs']
            args = list(args)
            args[-1] = shape
            try:
                del(kwargs['name'])
            except KeyError:
                pass
            thisMacro['createArgsKwargs'] = args, kwargs

            newSkin = self.createFromMacro(thisMacro)

            if weights:
                newSkin.copyWeightsFrom(self,
                                        destShape=shape,
                                        sourceUVSet=sourceUVSet,
                                        destUVSet=destUVSet,
                                        method=method)

            out.append(newSkin)

        return out

    def rebuild(self) -> 'SkinCluster':
        """
        Deletes and rebuilds this skinCluster via a temporary weight dump. The
        return value must be caught.
        """
        root = gettempdir()
        basename = 'tmp_weight_dump'
        index = 0

        while True:
            fullname = basename
            if index > 0:
                fullname += str(index)
            fullname += '.xml'

            fullpath = os.path.join(root, fullname)

            if os.path.isfile(fullpath):
                index += 1
                continue

            break

        try:
            self.dumpWeights(fullpath)
            newSkin = SkinCluster.createFromXMLFile(fullpath)
        finally:
            os.remove(fullpath)
            print(f"Removed temporary file: {fullpath}")

        return newSkin