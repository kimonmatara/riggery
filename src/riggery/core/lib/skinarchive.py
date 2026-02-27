from typing import Optional
import re
import json
import os
from pathlib import Path

import maya.cmds as m

from ..elem import Elem
from riggery.general.modules import LazyModule
from riggery.general.iterables import expand_tuples_lists, without_duplicates

r = LazyModule('riggery.core')

#--------------------------------------------------|
#--------------------------------------------------|    ERRORS
#--------------------------------------------------|

class SkinArchiveError(RuntimeError):
    pass


class NodeNotAShapeError(RuntimeError):
    pass


class MissingArchiveGeometryError(SkinArchiveError):
    pass


class MultipleOrNoMatchesForSceneShapeError(SkinArchiveError):
    pass


class MultipleMatchesForSceneShapeError(
    MultipleOrNoMatchesForSceneShapeError
):
    pass


class NoMatchForSceneShapeError(
    MultipleOrNoMatchesForSceneShapeError
):
    pass


class NoSkinClustersInSceneError(SkinArchiveError):
    pass


class EmptyArchiveError(SkinArchiveError):
    pass


class MissingUVSetError(SkinArchiveError):
    pass

#--------------------------------------------------|
#--------------------------------------------------|    UTILITIES
#--------------------------------------------------|

def sceneNodeExistsAndHasNoDuplicates(name):
    name = str(name).split('|')[-1]
    matches = m.ls(name)
    return matches and len(matches) == 1

def findSceneNode(name) -> str:
    """
    :raises MultipleMatchesForSceneShapeError:
    :raises NoMatchForSceneShapeError:
    """
    if isinstance(name, Elem):
        return name

    matches = m.ls(name)

    if matches:
        ln = len(matches)

        if ln == 1:
            return Elem(matches[0])

        raise MultipleMatchesForSceneShapeError(
            "Found multiple matches for scene shape '{}'.".format(name)
        )

    raise NoMatchForSceneShapeError(
        "Couldn't find a match for scene shape '{}'.".format(name)
    )

#--------------------------------------------------|
#--------------------------------------------------|    SINGLE DUMPING
#--------------------------------------------------|

def dumpSkinCluster(skinCluster, destDir, captureGeometry=False):
    skinCluster = Elem(skinCluster)
    destDir = Path(destDir)
    shape = r.skinCluster(skinCluster, q=True, geometry=True)[0]
    xform = shape.parent

    _shapeName = shape.shortName()
    _xformName = xform.shortName()
    _skinClusterName = str(skinCluster)

    prefix = "{}_on_{}".format(_skinClusterName, _shapeName)

    #--------------------------|    Collect & dump info

    info = {'obeyMaxInfluences': r.skinCluster(skinCluster, q=True, omi=True),
            'skinMethod': r.skinCluster(skinCluster, q=True, skinMethod=True),
            'joints': [joint.shortName() for joint in skinCluster.influence],
            'shape': _shapeName,
            'transform': _xformName,
            'skinCluster': _skinClusterName}

    infoFileName = '{}_info.json'.format(prefix)
    infoFilePath = destDir / infoFileName

    data = json.dumps(info)

    with open(infoFilePath, 'w', encoding='utf-8') as f:
        f.write(data)

    print("Wrote: {}".format(infoFilePath))

    #--------------------------|    Dump weights

    xmlFileName = '{}_weights.xml'.format(prefix)
    xmlFilePath = destDir / xmlFileName

    skinCluster.dumpWeights(xmlFilePath,
                            shape=str(shape),
                            vertexConnections=shape.nodeType()=='mesh')

    out = {'info': infoFilePath, 'weights': xmlFilePath}

    #--------------------------|    Dump blend weights separately, as iffy

    if info['skinMethod'] == 2:
        skinCluster._padBlendWeights()
        weights = m.getAttr(f'{skinCluster}.blendWeights')[0]
        blendWeightsPath = destDir / '{}_blend_weights.json'.format(prefix)
        _data = json.dumps(weights)

        with open(blendWeightsPath, 'w', encoding='utf-8') as f:
            f.write(_data)

        print("Wrote: {}".format(blendWeightsPath))

    #--------------------------|    Dump geometry archive

    if captureGeometry:
        origParent = shape.parent
        origParentName = origParent.shortName()

        rootGp = r.group(empty=True, n='{}_root'.format(origParentName))

        dummyXform = r.group(empty=True)
        r.parent(shape, dummyXform, r=True, add=True, shape=True)
        outXform = dummyXform.duplicate()[0]
        r.delete(dummyXform)
        outXform.parent = rootGp
        outXform.name = origParentName
        outXform.setMatrix(origParent.getMatrix(worldSpace=True),
                           worldSpace=True)
        outShape = outXform.getShape()
        outShape.name = _shapeName

        maFileName = '{}_geometry.ma'.format(prefix)
        maFilePath = destDir / maFileName

        rootGp.select()

        m.file(maFilePath.as_posix(),
               force=True,
               options='v=0;',
               typ='mayaAscii',
               es=True)

        r.delete(rootGp)

        print('Dumped geo to: {}'.format(maFilePath))

        out['geometry'] = maFilePath

    return out


def findSkinClusterFromGeo(shapeLookup:str, transformLookup:str):
    raise NotImplementedError

def loadSkinCluster(infoFilePath,
                    method='index',
                    forceShapeTo=None,
                    loadWeights=True,
                    weightsOnly=False,
                    replace:bool=True,
                    uvSet=None):
    """
    :Notes:

        -   If the scene is missing joints expected by the archive, those will
            be recreated under a group called 'missing_joints'

    :param str infoFilePath: the path to info json file
    :param str method: One of:

        -   'index' (XML)
        -   'barycentric' (XML)
        -   'bilinear' (XML)
        -   'nearest' (XML)
        -   'closestPoint' (copySkinWeights)
        -   'closestComponent' (copySkinWeights)
        -   'rayCast' (copySkinWeights)
        -   'uv' (copySkinWeights)

        Defaults to 'index'

    :param str uvSet: ignored if *method* is not 'uv'; defaults to the current
        UV set name on the scene shape
    :param forceShapeTo: a specific scene shape to map to; defaults to
        ``None``
    :type forceShapeTo: :class:`~payo.runtime.nodes.Shape`, :class:`str`
    :param bool weightsOnly: don't create any new skinClusters; only load
        weights for existing ones; defaults to False
    :param bool loadWeights: ignored if *weightsOnly* is True; defaults to
        ``True``
    :param replace: replace any existing skinCluster; if False, edit the
        existing skinCluster instead; defaults to ``True``
    :return: The regenerated or retrieved skinCluster, or None
    """
    #-------------------|    Basics

    if weightsOnly:
        loadWeights = True

    infoFilePath = Path(infoFilePath)
    parentDir = infoFilePath.parent

    prefix = re.match(r"^(.*?)_info.json$", infoFilePath.name).groups()[0]

    with infoFilePath.open('r') as f:
        data = f.read()

    info = json.loads(data)

    #-------------------|    Resolve shape

    if forceShapeTo:
        # allow to error
        sceneShape = findSceneNode(forceShapeTo)
    else:
        try:
            sceneShape = findSceneNode(info['shape'])
        except MultipleOrNoMatchesForSceneShapeError:
            sceneShape = findSceneNode(info['transform']).shape

    #-------------------|    Resolve skinCluster and influences

    skinCluster = next(r.nodes.SkinCluster.fromGeo(sceneShape), None)

    if skinCluster is None:
        if weightsOnly:
            return
        else:
            if replace:
                r.delete(skinCluster)
                skinCluster = None

        joints = []

        for jointName in info['joints']:
            try:
                joint = findSceneNode(jointName)
            except (NoMatchForSceneShapeError,
                    MultipleMatchesForSceneShapeError):

                if not r.objExists('missing_joints'):
                    r.group(empty=True, n='missing_joints')

                joint = r.createNode('joint')
                joint.parent = 'missing_joints'
                joint.name = jointName

            joints.append(joint)

        if skinCluster is None:
            kwargs = {'name': info['skinCluster'],
                      'obeyMaxInfluences': info['obeyMaxInfluences'],
                      'skinMethod': info['skinMethod'],
                      'toSelectedBones': True,
                      'bindMethod': 0,
                      'dropoffRate': 4.5,
                      'weightDistribution': 0,
                      'normalizeWeights': 1}

            args = joints + [sceneShape]
            skinCluster = r.skinCluster(*args, **kwargs)[0]

            if not loadWeights:
                return skinCluster

        else:
            if not loadWeights:
                return skinCluster

            notInSkin = [x for x in joints if x not in skinCluster.influence]

            if notInSkin:
                skinCluster.addInfluence(notInSkin, preserveWeights=True)

    #-------------------|    Load weights

    if method in ['closestPoint', 'closestComponent', 'rayCast', 'uv']:

        # Reference-in the geometry archive
        infoFileName = infoFilePath.name
        maFileName = '{}_geometry.ma'.format(
            re.match(r"^(.*?)_info\.json$", infoFileName).groups()[0]
        )

        maFilePath = infoFilePath.parent / maFileName

        if not maFilePath.is_file():
            raise MissingArchiveGeometryError(
                ("Can't load by {} because no archive geometry"+
                 " could be found at: {}").format(method, maFilePath)
            )

        ref = m.file(maFilePath.as_posix(),
                     type='mayaAscii',
                     ignoreVersion=True,
                     reference=True,
                     namespace='tmp_archive_ref',
                     mergeNamespacesOnClash=False,
                     options='v=0;',
                     gl=False)

        # Get actual resultant namespace
        namespace = m.referenceQuery(ref, namespace=True)

        # Get the geo parent in the reference
        infoTransformName = info['transform']
        geoXf = Elem('{}:{}'.format(namespace, infoTransformName))

        # Make a local copy; capture local name
        geoXf = geoXf.duplicate()[0]
        geoXf.parent = None
        interimSceneShape = geoXf.getShape()
        _interimSceneShape = str(interimSceneShape)

        # Remove the reference
        m.file(ref, rr=True)

        try:
            # Recreate the skinCluster onto this interim shape, loading weights
            # by index
            interimSkinCluster = loadSkinCluster(
                infoFilePath,
                method='index',
                forceShapeTo=_interimSceneShape,
                loadWeights=True
            )

            # Copy weights across to the correct skinCluster using
            # requested copySkinWeights method
            kwargs = {'ss': str(interimSkinCluster),
                      'ds': str(skinCluster),
                      'ia': 'oneToOne',
                      'nm': True}

            if method == 'uv':
                if not uvSet:
                    uvSet = sceneShape.getUVSet()

                if not(uvSet in sceneShape.getUVSetNames() and \
                       uvSet in interimSceneShape.getUVSets()):
                    raise MissingUVSetError(
                        ("UV set '{}' is not available on either "+
                         "or both of the scene and archive geometries."
                         ).format(uvSet)
                    )

                kwargs['uvSpace'] = [uvSet, uvSet]

            else:
                kwargs['sa'] = method

            m.copySkinWeights(**kwargs)

        finally:
            r.delete(geoXf)

    else:
        #--------------------------|    Formulate and check XML path

        xmlFilePath = parentDir / '{}_weights.xml'.format(prefix)

        if not xmlFilePath.is_file():
            raise MissingXMLWeightsFile(
                "Missing XML weights file: {}".format(xmlFilePath)
            )

        #--------------------------|    Load XML weights

        # Collect info on xml vs scene shape and xml vs scene
        # skinCluster

        _xmlShape = info['shape']
        _sceneShape = str(sceneShape)

        _xmlSkinCluster = info['skinCluster']
        _sceneSkinCluster = str(skinCluster)

        remaps = []

        if _xmlShape != _sceneShape:
            remaps.append("{};{}".format(_xmlShape, _sceneShape))

        if _xmlSkinCluster != _sceneSkinCluster:
            remaps.append("{};{}".format(_xmlSkinCluster, _sceneSkinCluster))

        kwargs = {}

        if remaps:
            kwargs['remap'] = remaps

        skinCluster.loadWeights(xmlFilePath.as_posix(),
                                shape=sceneShape,
                                method=method,
                                worldSpace=True,
                                **kwargs)

        # Load blend weights from separate dump

        if method == 'index' and info['skinMethod'] == 2:
            blendWeightsPath = parentDir / '{}_blend_weights.json'.format(
                prefix
            )
            if blendWeightsPath.is_file():
                with open(blendWeightsPath, 'r') as f:
                    data = f.read()

                data = json.loads(data)
                _skin = str(skinCluster)

                for i in range(len(data)):
                    m.setAttr(f'{_skin}.blendWeights[{i}]', data[i])

    # Normalize weights
    r.skinCluster(skinCluster, e=True, fnw=True)

    return skinCluster

#--------------------------------------------------|
#--------------------------------------------------|    MULTI DUMPING
#--------------------------------------------------|

def dumpMulti(dirpath,
              skinClusters:Optional[list]=None, /,
              captureGeometry:bool=False,
              clearDirectory:bool=False):
    if skinClusters:
        skinClusters = list(without_duplicates(map(Elem, skinClusters)))
    else:
        skinClusters = r.ls(type='skinCluster')

    if skinClusters:
        dirpath = Path(dirpath)

        if dirpath.is_dir():
            if clearDirectory:
                for item in os.listdir(dirpath):
                    fullPath = dirpath / item

                    if fullPath.is_file():
                        os.remove(fullPath)
        else:
            os.makedirs(dirpath)

        num = len(skinClusters)

        for i, skinCluster in enumerate(skinClusters):
            print("Dumping skinCluster #{} of {}...".format(i+1, num))
            dumpSkinCluster(skinCluster,
                            dirpath,
                            captureGeometry=captureGeometry)

        print("Dumped {} skinClusters into: {}".format(num, dirpath))

    else:
        raise NoSkinClustersInSceneError(
            "No skinClusters were specified for dumping."
        )

def loadMulti(infoFiles:list,
              onlyForSceneShapes=None, /,
              loadWeights:bool=True,
              weightsOnly:bool=False,
              method='index',
              uvSet:Optional[str]=None,
              skipFails:bool=False,
              skipDuplicates:bool=True):

    #-----------------------------|    Wrangle info files

    infoFiles = list(without_duplicates(map(Path, infoFiles)))

    #-----------------------------|    Wrangle worklist

    if onlyForSceneShapes:
        sceneTargets = [str(x).split('|')[-1]
                        for x in expand_tuples_lists(*onlyForSceneShapes)]

        for sceneTarget in sceneTargets:
            if not sceneNodeExistsAndHasNoDuplicates(sceneTarget):
                raise MultipleOrNoMatchesForSceneShapeError(
                    ("No matches, or multiple matches, found for "+
                     "scene node '{}'.").format(sceneTarget)
                )

            if not m.objectType(sceneTarget, isAType='shape'):
                raise NodeNotAShapeError(
                    "Node '{}' is not a shape.".format(sceneTarget)
                )
    else:
        sceneTargets = None

    alreadyProcessed = [] # short names
    numInfoFiles = len(infoFiles)
    skinClusters = []

    for i, infoFile in enumerate(infoFiles):
        # Read the info file, check shape
        with infoFile.open('r') as f:
            data = f.read()

        info = json.loads(data)
        infoShape = info['shape']

        if sceneTargets and infoShape not in sceneTargets:
            continue

        if skipDuplicates and infoShape in alreadyProcessed:
            continue

        try:
            skinCluster = loadSkinCluster(infoFile,
                                          method=method,
                                          weightsOnly=weightsOnly,
                                          loadWeights=loadWeights,
                                          uvSet=uvSet)

            if skinCluster is None: # weightsOnly and no scene skinCluster
                continue

            print(
                "Processed skinCluster '{}' on shape '{}'".format(
                    skinCluster,
                    infoShape
                )
            )

            skinClusters.append(skinCluster)
            alreadyProcessed.append(infoShape)

        except Exception as exc:
            if skipFails:
                print("Failed on file {} with error: {}".format(infoFile, exc))
                continue

            raise exc

    return skinClusters

def findInfoFiles(directories):
    directories = list(
        without_duplicates(map(Path, expand_tuples_lists(directories)))
    )
    out = []

    for dr in directories:
        fileNames = [i for i in os.listdir(dr)
                     if re.match(r"^.*?_on_.*?_info\.json", i)]

        out += [dr / fileName for fileName in fileNames]

    return out

def loadMultiFromDir(dr,
                     onlyForSceneShapes=None, /,
                     weightsOnly:bool=False,
                     **kwargs):
    return loadMulti(findInfoFiles(dr),
                     onlyForSceneShapes,
                     weightsOnly=weightsOnly,
                     **kwargs)