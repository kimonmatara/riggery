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
import maya.mel as mel

import riggery.core as r
from riggery.core.lib.selection import keepsel
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
               obeyMaxInfluences:Optional[bool]=False,
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
                 'skinMethod', 'weightDistribution', 'bindMethod',
                 'dropoffRate', 'normalizeWeights', 'toSelectedBones'),
                (maximumInfluences, obeyMaxInfluences, skinMethod,
                 weightDistribution, bindMethod, dropoffRate,
                 normalizeWeights, toSelectedBones)
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
        skins = m.ls(type='skinCluster')

        if skins:
            shapes = set()

            for vert in without_duplicates(
                    map(str, expand_tuples_lists(*verts))
            ):
                mt = re.match(r"^(.*?)\.vtx\[.*?]$", vert)
                if mt:
                    node = mt.group(1)

                    if m.objectType(node, isAType='shape'):
                        shapes.add(node)
                    else:
                        shapes.add(m.listRelatives(node,
                                                   shapes=True,
                                                   noIntermediate=True,
                                                   path=True)[0])

            for skin in skins:
                shape = m.skinCluster(skin, q=True, geometry=True)[0]

                if shape in shapes:
                    yield nodes['DependNode'](skin)

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

    def pruneWeightsBelow(self, threshold:float):
        """Prunes weights below the specified threshold."""
        _self = str(self)
        m.skinPercent(_self,
                      m.skinCluster(_self, q=1, geometry=1)[0], prw=threshold)
        return self

    def iterInfluencesFromVerts(self, verts:list[str]) -> list['nodes.Joint']:
        """
        Returns the influences on this skinCluster that affect the given
        vertices.
        """
        _self = str(self)
        influences = m.skinCluster(_self, q=True, influence=True)
        geo = m.skinCluster(_self, q=True, geometry=True)

        if verts and influences and geo:
            verts = m.ls(verts, flatten=True)
            shape = geo[0]

            for influence in influences:
                for vert in verts:
                    value = m.skinPercent(_self,
                                          shape,
                                          vert,
                                          q=True,
                                          transform=influence,
                                          value=True)
                    if value is None:
                        continue

                    if value > 0.0:
                        yield nodes['DependNode'](influence)
                        break

    def getInfluencesFromVerts(self, verts:list[str]) -> list['nodes.Joint']:
        """Flat-list version of :meth:`iterInfluencesFromVerts`."""
        return list(self.iterInfluencesFromVerts(verts))

    # @classmethod
    # def smoothInfluencesOnVerts(cls,
    #                             verts:list[str],
    #                             *skinClusters,
    #                             iterations:int=10):

    #     if skinClusters:
    #         skinClusters = list(
    #             without_duplicates(map(nodes['DependNode'],
    #                                    expand_tuples_lists(*skinClusters)))
    #         )
    #     else:
    #         skinClusters = list(cls.fromVerts(verts))
    #
    #     if skinClusters:
    #         for skinCluster in skinClusters:
    #             skinCluster.artSmoothInfluencesOnVerts(verts,
    #                                                    iterations=iterations)

    @short(iterations='i')
    def artSmoothInfluencesOnVerts(self, verts, iterations:int=10):
        """Smooths weights only on the specified vertices. """
        influences = self.getInfluencesFromVerts(verts)
        if influences:
            self.artSmoothInfluences(influences,
                                     iterations=iterations,
                                     selection=verts)

    @short(iterations='i')
    @keepsel
    def artSmoothInfluences(self,
                            *influences,
                            iterations:int=10,
                            selection=None):
        """
        :param \*influences: the influences to smooth; if omitted, defaults to
            all influences
        :param iterations/i: the number of times to click the 'Smooth' button;
            defaults to 10
        :param selection: if you only want to affect particular components,
            pass them in here; defaults to None
        """
        influences = expand_tuples_lists(*influences)

        influences = list(without_duplicates(
            (nodes['DependNode'](x) for x in influences)))

        if influences:
            influences = [x for x in influences if x in self.getInfluence()]
        else:
            influences = self.getInfluence()

        if influences:
            # Switch weight normalization to post temporarily
            nw = r.skinCluster(self, q=True, nw=True)
            r.skinCluster(self, e=True, nw=2)

            # Select geo, activate artisan weight painting
            if selection is None:
                selection = r.skinCluster(self, q=True, geometry=True)[0]

            r.select(selection)

            initCtx = m.currentCtx()
            settingsVis = m.workspaceControl('ToolSettings',
                                             q=True, visible=True)

            mel.eval('ArtPaintSkinWeightsToolOptions')

            mel.eval('artAttrPaintOperation artAttrSkinPaintCtx Smooth;')
            mel.eval('artAttrSkinPaintCtx -e -opacity 1 `currentCtx`;')

            for infl in influences:
                mel.eval('setSmoothSkinInfluence {}'.format(infl))

                for x in range(iterations):
                    mel.eval('artAttrSkinPaintCtx -e -clear `currentCtx`')

            r.skinCluster(self, e=True, fnw=True)
            r.skinCluster(self, e=True, nw=nw)
            m.setToolTo(initCtx)


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