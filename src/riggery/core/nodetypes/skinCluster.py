import json
from copy import deepcopy
import re
import os
from tempfile import gettempdir
from pathlib import Path
from typing import Literal, Union, Iterator, Optional, Iterable, Callable
import xml.etree.ElementTree as ET

from ..nodetypes import __pool__ as nodes
GeometryFilter = nodes['GeometryFilter']

import maya.cmds as m
import maya.mel as mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

import riggery.core as r

from riggery.core.lib.selection import keepsel
import riggery.core.lib.names as _nm
from riggery.core.lib import skinwtio as _sw

from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short
from riggery.internal.typeutil import UNDEFINED

if not m.pluginInfo('invertShape', loaded=1, q=1):
    m.loadPlugin('invertShape')


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
    def fromAny(cls, *items) -> Iterator['SkinCluster']:
        """
        Yields skinClusters from any combination of component, geometry,
        skinCluster or joint.
        """
        visited = set()

        for item in expand_tuples_lists(*items):
            _item = str(item)

            if '.' in _item:
                mt = re.match(r"^(.*?)\.(?:vtx|e|f|cv)\[.*$", _item)

                if mt:
                    node = mt.group(1)
                    for skin in cls.fromGeo(node):
                        if skin in visited:
                            continue
                        visited.add(skin)
                        yield skin
            else:
                try:
                    item = nodes['DependNode'](item)
                except:
                    continue

                if isinstance(item, nodes['Transform']):
                    if isinstance(item, nodes['Joint']):
                        for skin in item.skinClusters:
                            if skin in visited:
                                continue
                            visited.add(skin)
                            yield skin
                    else:
                        shape = item.getShape(intermediate=False,
                                              type='deformableShape')
                        if shape:
                            for skin in cls.fromGeo(shape):
                                if skin in visited:
                                    continue
                                visited.add(skin)
                                yield skin

                elif isinstance(item, nodes['DeformableShape']):
                    for skin in cls.fromGeo(item):
                        if skin in visited:
                            continue
                        visited.add(skin)
                        yield skin

                elif isinstance(item, nodes['SkinCluster']):
                    yield item

    @classmethod
    def fromVerts(cls, *verts:Union[str, list[str]]) -> Iterator['SkinCluster']:
        verts = expand_tuples_lists(*verts)
        verts = m.ls(verts, flatten=True)

        shapes = set()

        for vert in verts:
            mt = re.match(r"^(.*?)\.vtx\[.*$", vert)
            if mt:
                shapes.add(mt.group(1))

        visited = set()

        for shape in shapes:
            for skin in cls.fromGeo(shape):
                if skin in visited:
                    continue
                visited.add(skin)
                yield skin

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

    def iterInfluence(self) -> Iterator['nodes.Joint']:
        out = m.skinCluster(str(self), q=True, influence=True)

        if out:
            for x in out:
                yield nodes['DependNode'](x)

    influence = property(iterInfluence)

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
            try:
                m.skinCluster(skin, e=True, ai=infl, **kw)
            except:
                continue

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

    def mirrorWeights(
            self,
            influenceAssociation:Optional[Union[str, list[str]]]=None,
            surfaceAssociation:Literal[
                'closestPoint', 'rayCast', 'closestComponent'
            ]='closestComponent',
            alongPositiveX:bool=False,
            destinationSkin:Optional['SkinCluster']=None,
            autoLabel:bool=False
    ):
        """
        :param influenceAssociation/ia: one, or several (as fallbacks) of:
            'closestJoint', 'closestBone', 'label', 'name', 'oneToOne'; defaults
            to ['label', 'closestJoint', 'oneToOne'] if *autoLabel* is True,
            otherwise ['closestJoint', 'oneToOne']
        :param surfaceAssociation/sa: one of 'closestPoint', 'rayCast',
            'closestComponent'; defaults to 'closestComponent'
        """
        # Resolve influence association
        if influenceAssociation is None:
            influenceAssociation = ['closestJoint', 'oneToOne']
            if autoLabel:
                influenceAssociation.insert(0, 'label')

        # Resolve destination skin
        if destinationSkin is not None:
            destinationSkin = SkinCluster(destinationSkin)

        if autoLabel:
            allJoints = self.getInfluence()

            if destinationSkin is not None:
                allJoints += destinationSkin.getInfluence()
                allJoints = without_duplicates(allJoints)

            labelStates = {joint:joint.autoLabel() for joint in allJoints}

        # Run the command
        if destinationSkin is None:
            destinationSkin = self

        kwargs = {'ss': self, 'ds': destinationSkin,
                  'ia': influenceAssociation,
                  'sa': surfaceAssociation,
                  'mi': alongPositiveX,
                  'mm': 'YZ'}

        try:
            r.copySkinWeights(**kwargs)
        finally:
            if autoLabel:
                for joint, state in labelStates.items():
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

    #-------------------------------------|    Blend shapes

    def invertShape(
            self,
            sculptGeo:Union[str, 'nodes.Shape', 'nodes.Transform']
    ) -> 'nodes.Shape':
        """
        :param sculptGeo: a geo sculpted at the same pose as this skinCluster's
            currently at
        :return: a reversed version of the sculpted geo, that can be used as a
            pre-bind blend shape.
        """
        thisShape = next(self.shapes)
        xform = nodes.Transform(m.invertShape(str(thisShape), str(sculptGeo)))

        if _nm.Name.__elems__:
            xform.name = _nm.Name.evaluate(typeSuffix=thisShape.__typesuffix__)
        else:
            xform.name = "{}_inversion_{}".format(
                thisShape.parent.shortName(sts=True),
                thisShape.__typesuffix__
            )

        xform.assignDefaultShader()
        return xform.shape

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

    def dumpBlendWeights(self, jsonFilePath:Union[str, Path]):
        """
        At the moment this can only be done by-index.
        """
        jsonFilePath = Path(jsonFilePath).with_suffix('.json')
        parentDir = jsonFilePath.parent

        if not parentDir.is_dir():
            raise FileNotFoundError(
                "parent directory doesn't exist: {}".format(parentDir)
            )

        # Gather the data
        _self = str(self)

        indices = m.getAttr(f'{_self}.blendWeights', multiIndices=True)

        if indices:
            weights = m.getAttr(f'{_self}.blendWeights')[0]

            indices, weights = zip(*((i, w) for i, w in zip(indices, weights)
                                     if w > 0.0))

            data = {'indices': indices, 'weights': weights}

        else:
            data = {}

        _data = json.dumps(data, indent=4)

        with open(jsonFilePath, 'w', encoding='utf-8') as f:
            f.write(_data)

        print("Wrote: {}".format(jsonFilePath))

    def loadBlendWeights(self, jsonFilePath:Union[str, Path]):
        """
        At the moment this can only be done by-index.
        """
        jsonFilePath = Path(jsonFilePath)

        with open(jsonFilePath, 'r', encoding='utf-8') as f:
            data = f.read()

        data = json.loads(data)

        print("Loaded: {}".format(jsonFilePath))

        indices = data['indices']
        weights = data['weights']

        self.attr('blendWeights').clearMulti()
        _self = str(self)

        for index, weight in zip(indices, weights):
            m.setAttr(f'{_self}.blendWeights[{index}]', weight)

        return self

    def mirrorCopy(self, destGeo=None, /):
        # Resolve dest geo

        if destGeo is None:
            destGeo = next(self.shapes).parent.findOppositeNodeByName()

            if destGeo is None:
                raise RuntimeError("couldn't resolve destination geo")
        else:
            destGeo = nodes['DagNode'](destGeo)

        # Resolve destination influences
        destInfl = []

        srcInfl = list(self.influence)

        for srcJoint in self.influence:
            oppJoint = srcJoint.findOppositeNodeByName()

            if oppJoint is None:
                if not re.match(r"^[LR]_.*$", srcJoint.shortName()):
                    destInfl.append(srcJoint)
            else:
                destInfl.append(oppJoint)

        # Remove any skinCluster on destination
        existing = next(SkinCluster.fromGeo(destGeo), None)

        if existing is not None:
            m.delete(str(existing))

        # Rebind destination
        args = destInfl + [destGeo]
        destSkin = SkinCluster.create(*args).renameFromGeo()

        # Copy weights with mirroring and auto
        allInfl = srcInfl + destInfl
        states = {infl: infl.autoLabel() for infl in allInfl}

        m.copySkinWeights(ss=str(self), ds=str(destSkin),
                          ia=['label', 'oneToOne'],
                          mm='YZ',
                          spa=0,
                          sa='closestComponent')

        # Restore joint labels
        for joint, state in states.items():
            joint.setLabelState(state)

        return destSkin

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
            thisMacro['geoShape'] = shape
            thisMacro['geoTransform'] = shape.parent
            del(thisMacro['cmdFlags']['name'])

            newSkin = self.createFromMacro(thisMacro)

            if weights:
                newSkin.copyWeightsFrom(self,
                                        destShape=shape,
                                        sourceUVSet=sourceUVSet,
                                        destUVSet=destUVSet,
                                        method=method)

            out.append(newSkin)

        return out

    @short(preserveWeights='pw',
           verbose='v')
    def copyInfluencesTo(self,
                         *others,
                         preserveWeights:bool=True,
                         verbose:bool=False,):
        """
        Ensures that every skinCluster amongst *others* includes this
        skinCluster's influences.

        :param \*others: the skinClusters onto which to copy influences
        :param preserveWeights/pw: don't edit weights on the destination
            skinClusters; defaults to True
        :param verbose/v: print informational messages; defaults to False
        """
        others = without_duplicates(
            map(nodes['SkinCluster'], expand_tuples_lists(*others))
        )

        theseInfluences = set(self.influence)

        for other in others:
            otherInfluences = set(other.influence)
            inflsToAdd = [x for x in theseInfluences
                          if x not in otherInfluences]

            if inflsToAdd:
                other.addInfluence(inflsToAdd, preserveWeights=True)

                if verbose:
                    print("Added {} influence(s) to {}".format(len(inflsToAdd),
                                                               other))

        return self

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

    #-------------------------------------|    Serialization

    def macro(self) -> dict:
        """
        Returns a dictionary that can serialized and used to recreate the
        skinCluster (but without the original weight information).
        """
        name = str(self)
        influence = [x.shortName() for x in self.influence]
        geoShape = next(self.shapes)
        geoTransform = geoShape.parent
        geoShape = geoShape.shortName()
        geoTransform = geoTransform.shortName()

        cmdFlags = {x: m.skinCluster(name, q=True, **{x: True})
                    for x in ('maximumInfluences',
                              'obeyMaxInfluences',
                              'skinMethod',
                              'weightDistribution',
                              'bindMethod',
                              'normalizeWeights')}

        cmdFlags['toSelectedBones'] = True
        cmdFlags['dropoffRate'] = 4.0
        cmdFlags['name'] = name

        attrStates = {x: self.attr(x).getState()
                      for x in ('dqsScale',
                                'dqsSupportNonRigid',
                                'deformUserNormals',
                                'lockWeights')}

        return {'influence': influence, 'geoShape': geoShape,
                'geoTransform': geoTransform, 'cmdFlags': cmdFlags,
                'attrStates': attrStates}

    @classmethod
    @short(restoreInputs='ri',
           restoreValues='rv',
           createMissingInfluence='cmi')
    def createFromMacro(cls,
                        macro:dict,
                        restoreInputs:bool=False,
                        restoreValues:bool=True,
                        createMissingInfluence:bool=True,
                        replace:bool=False):
        """
        :param macro: the macro to use
        :param restoreInputs/ri: restore attribute inputs; defaults to False
        :param restoreValues/rv: restore attribute values; defaults to True
        :param replace: if True, replaces any existing skinCluster; defaults to
            False
        :param createMissingInfluence/cmi: recreates missing influences at the
            origin, and adds them to a 'missing_influences_OBST' set
        :raises RuntimeError: the geometry is already bound, and *replace* was
            False
        :raises RuntimeError: no matches found for the geometry
        :raises RuntimeError: no matches found for some, or any, of the
            influences, and *createMissingInfluence* was Falses
        """
        # Resolve influences
        joints = []

        restoredInfluences = []

        for joint in macro['influence']:
            matches = r.ls(joint, type='joint')

            if len(matches) == 0:
                if createMissingInfluence:
                    newJoint = r.createNode('joint', name=joint)
                    restoredInfluences.append(newJoint)
                    joints.append(newJoint)
                else:
                    raise RuntimeError("no match for '{}'".format(joint))
            else:
                joints.append(matches[0])

        if restoredInfluences:
            if not r.objExists('missing_joints_OBST'):
                oset = r.sets(empty=True, name='missing_joints_OBST')
            r.sets(joints, fe=oset)

        # Resolve geometry
        geometry = None
        usedLookups = []

        for key in ('geoShape', 'geoTransform'):
            try:
                lookup = macro[key]
                usedLookups.append(lookup)
            except KeyError:
                continue
            matches = r.ls(lookup, type='dagNode')

            if len(matches) > 0:
                geometry = matches[0]
                break

        if geometry is None:
            if usedLookups:
                raise RuntimeError(
                    "no matches for any of: {}".format(
                        ', '.join(usedLookups)
                    )
                )
            else:
                raise RuntimeError("missing geo info in macro")

        existing = next(SkinCluster.fromGeo(geometry), None)

        if existing is not None:
            if replace:
                r.delete(existing)
            else:
                raise RuntimeError(
                    "geometry '{}' is already bound".format(geometry)
                )

        # Init the skin cluster
        args = joints + [geometry]
        kwargs = macro['cmdFlags'].copy()

        if _nm.Name.__elems__:
            del(kwargs['name'])

        inst = r.skinCluster(*args, **kwargs)[0]

        # Configure attributes
        for attrName, attrState in macro['attrStates'].items():
            try:
                inst.attr(attrName).setState(attrState,
                                             input=restoreInputs,
                                             value=restoreValues)
            except:
                continue

        return inst

    @classmethod
    def _applyReplacerToArchiveMacro(cls,
                                     replacer:Callable,
                                     macro:dict) -> None:
        if 'influence' in macro: # edge cases
            macro['influence'][:] = map(replacer, macro['influence'])

        for key in ('name', 'geoShape', 'geoTransform'):
            macro[key] = replacer(macro[key])

    def _loadWeightsFromArchive(self,
                                info:dict,
                                infoFilePath:Path, *,
                                method='index',
                                remap=None):
        """
        Extends
        :meth:`~riggery.core.nodetypes.geometryFilter.GeometryFilter._loadWeightsFromArchive`
        to load side-car blend weights, where available.
        """
        result = super()._loadWeightsFromArchive(info,
                                                 infoFilePath,
                                                 method=method,
                                                 remap=remap)

        fileName = '{}_blendWeights.json'.format(info['deformerName'])
        filePath = infoFilePath.parent / fileName

        if filePath.is_file():
            if method == 'index':
                self.loadBlendWeights(filePath)
            else:
                m.warning(
                    "Can't read blend weights from {}:".format(fileName)+
                    " only supported for 'index' method"
                )

    def dumpArchive(self,
                    parentDir:Union[str, Path],
                    shapes:Optional[
                        Union[
                            'nodes.DagNode',
                            Iterable['nodes.DagNode']
                        ]
                    ]=None, /) -> dict:
        result = super().dumpArchive(parentDir, shapes)

        _self = str(self)

        if m.getAttr(f'{_self}.blendWeights', multiIndices=True):
            fileName = '{}_blendWeights.json'.format(_self)
            filePath = result['infoFilePath'].parent / fileName
            self.dumpBlendWeights(filePath)

        return result

    #-------------------------------------|    Granular weight management

    def _getWeights(self, shapeIndex:int, channelIndex:int) -> list[float]:
        shapeMDagPath = self._getShapeMDagPathAtIndex(shapeIndex)
        allComps = self._getAllWeightedComps(shapeIndex)

        skinMObject = self.__apimobject__()
        skinFn = oma.MFnSkinCluster(skinMObject)
        infIndices = om.MIntArray([channelIndex])

        return list(skinFn.getWeights(shapeMDagPath, allComps, infIndices))

    def _getChannelIndex(self, joint:Union[str, 'nodes.Joint']) -> int:
        joint = nodes['Transform'](joint)

        return oma.MFnSkinCluster(
            self.__apimobject__()
        ).indexForInfluenceObject(joint.__apimdagpath__())

    def _setWeights(self,
                    shapeIndex:int,
                    channelIndex:int,
                    weights:list[float]):
        """
        This will issue warnings if the skinCluster is set to 'interactive'. You
        might want to turn off normalization beforehand and resolve afterwards.
        """
        skinMObject = self.__apimobject__()
        skinFn = oma.MFnSkinCluster(skinMObject)
        shapeMDagPath = self._getShapeMDagPathAtIndex(shapeIndex)
        allComps = self._getAllWeightedComps(shapeIndex)
        inflIndices = om.MIntArray([channelIndex])
        weightsArray = om.MDoubleArray(list(weights))

        skinFn.setWeights(shapeMDagPath,
                          allComps,
                          inflIndices,
                          weightsArray,
                          normalize=False)

        return self