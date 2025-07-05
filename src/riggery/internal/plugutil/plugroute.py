import maya.api.OpenMaya as om

from .plugtree import DATA as PLUG_TREE
from .descmplug import describeMPlug

cap = lambda x: x[0].upper()+x[1:]

CACHE = {}

def getKeyFromDesc(desc:dict) -> dict:

    hsh = hash(tuple(sorted(desc.items())))
    try:
        return CACHE[hsh]
    except KeyError:
        pass

    if desc.get('isArray'):
        try:
            key = desc.get('tensorType',
                           desc.get('scalarType',
                                    desc['otherType']))
            key = cap(key)+'Array'
        except KeyError:
            key = 'Array'
    else:
        scalarType = desc.get('scalarType')
        key = 'Attribute'

        if scalarType:
            key = 'Math'

            tensorShape = desc.get('tensorShape')
            if tensorShape is not None:
                if tensorShape == 16:
                    key = 'Matrix'
                else:
                    key = f'Tensor{tensorShape}{cap(scalarType)}'

                    unitType = desc.get('unitType')
                    if unitType:
                        key += cap(unitType)

                        key = {
                            'Tensor3FloatDistance': 'Point',
                            'Tensor3FloatAngle': 'EulerRotation'
                        }.get(key, key)
                    else:
                        key = {'Tensor4Float': 'Quaternion',
                               'Tensor3Float': 'Vector'}.get(key, key)
            else:
                key = cap(scalarType)

                unitType = desc.get('unitType')
                if unitType:
                    key = cap(unitType)
                else:
                    key = cap(desc.get('otherType', cap(scalarType)))
        else:
            geoType = desc.get('geoType')
            if geoType:
                key = cap(geoType)
            else:
                otherType = desc.get('otherType')
                if otherType:
                    key = cap(otherType)

    CACHE[hsh] = key
    return key

def getKeyFromMPlug(plug:om.MPlug) -> str:
    return getKeyFromDesc(describeMPlug(plug))

def getPathFromKey(key:str) -> list[str]:
    return PLUG_TREE.get_path_to(key)

def getPathFromMPlug(plug:om.MPlug) -> list[str]:
    return getPathFromKey(getKeyFromMPlug(plug))