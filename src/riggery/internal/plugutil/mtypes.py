"""
Generates, or retrieves, an exhaustive list of attribute types used by various
Maya commands such as :func:`~maya.cmds.addAttr`.

The list can be accessed via the global ``DATA`` constant.
"""

from typing import Generator
import re
import os
import json

import requests

import maya.api.OpenMaya as om
import maya.cmds as m

#--------------------------------------------|    CACHE FILE

uncap = lambda x: x[0].lower()+x[1:]

CACHE_FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    os.path.splitext(os.path.basename(__file__))[0]+'.json'
)

DATA = {}

#--------------------------------------------|    REGENERATE

CORRECTIONS = {
    'int64Array': 'Int64Array',
}

ADDITIONS = [
    'subdiv', 'subd',
    'dataBezierCurve',
    'TdataCompound', 'Tdata',
    'IntArray'
]

def _fromOnlineHelp(version:str='2025') -> Generator[str, None, None]:
    """
    Yields Maya attribute type strings scraped from the online Maya help.
    """
    yielded = []

    #--------------------|    FROM ADDATTR PAGE

    url = f"https://help.autodesk.com/cloudhelp/{version}/ENU/Maya-Tech-Docs/CommandsPython/addAttr.html"
    response = requests.get(url)
    for line in response.text.split('\n'):
        mt = re.match(r"^\s*\<tr\>\<td\>.*?\<\/td\>\<td\>(.*?)\<\/td\>\<\/tr\>\s*$", line)
        if mt:
            base = mt.groups()[0].strip()
            mt = re.match(r"^\-(?:dt|at)\s+(.*?)$", base)
            if mt:
                item = mt.groups()[0]
                if item not in yielded:
                    yield item
                    yielded.append(item)

    #--------------------|    FROM GETATTR PAGE

    url = f"https://help.autodesk.com/cloudhelp/{version}/ENU/Maya-Tech-Docs/CommandsPython/setAttr.html"
    response = requests.get(url)
    for line in response.text.split('\n'):
        mt = re.match(
            r'^\<td align=\"left\" valign=\"top\"\>\<b\>\-type (.*?)\<\/b\>\<\/td\>$',
            line
        )

        if mt:
            item = mt.groups()[0]
            item = item.replace("&quot;", "")
            if item not in yielded:
                yield item
                yielded.append(item)

def _fromMFn() -> Generator[str, None, None]:
    """
    Yields Maya attribute type strings derived from
    :class:`~maya.api.OpenMaya.MFn`.
    """
    yielded = []
    mFnAttr = om.MFnAttribute()
    mFnData = om.MFnData()

    for k, v in om.MFn.__dict__.items():
        if k.startswith('k') and (mFnAttr.hasObj(v) or mFnData.hasObj(v)):
            # e.g. kAttribute3Float
            mt = re.match(r"^kAttribute([2-4])(.*)$", k)

            if mt:
                shape, scalarType = mt.groups()
                mtype = f"{uncap(scalarType)}{shape}"
                mtype = CORRECTIONS.get(mtype, mtype)

                if mtype not in yielded:
                    yield mtype
                    yielded.append(mtype)
            else:
                # e.g.kSphereData or kFloatVectorArrayData
                mt = re.match(r"^k(.*?)Data$", k)
                if mt:
                    mtype = uncap(mt.groups()[0])
                    mtype = CORRECTIONS.get(mtype, mtype)
                    if mtype not in yielded:
                        yield mtype
                        yielded.append(mtype)
                else:
                    mt = re.match(r"kData([0-9])(.*)$", k)
                    if mt:
                        shape, scalarType = mt.groups()
                        mtype = f"{uncap(scalarType)}{shape}"
                        mtype = CORRECTIONS.get(mtype, mtype)
                        if mtype not in yielded:
                            yield mtype
                            yielded.append(mtype)
                    else:
                        mt = re.match(r"k(.*)Attribute$", k)
                        if mt:
                            mtype = uncap(mt.groups()[0])
                            mtype = CORRECTIONS.get(mtype, mtype)
                            if mtype not in yielded:
                                yield mtype
                                yielded.append(mtype)

def _fromMFnNumericData() -> Generator[str, None, None]:
    """
    Yields Maya attribute type strings derived from
    :class:`~maya.api.OpenMaya.MFnNumericData`.
    """
    yielded = []

    for k, v in om.MFnNumericData.__dict__.items():
        if k.startswith('k'):
            mt = re.match(r"^k([2-4])(.*?)$", k)
            if mt:
                shape, scalarType = mt.groups()
                scalarType = uncap(scalarType)
                mtype = f"{scalarType}{shape}"

                mtype = CORRECTIONS.get(mtype, mtype)
                if mtype not in yielded:
                    yield mtype
                    yielded.append(mtype)

def _fromAttrInfo() -> Generator[str, None, None]:
    """
    Yields Maya attribute type strings extracted using
    :func:`~maya.cmds.attributeQuery` and :func:`~maya.cmds.attributeInfo`.

    This is slow, will take a few seconds.
    """
    yielded = []

    for nodeType in m.allNodeTypes(includeAbstract=True):
        try:
            attrList = m.attributeInfo(t=nodeType, allAttributes=True)
        except RuntimeError:
            continue
        for attr in attrList:
            attrType = m.attributeQuery(attr,
                                        typ=nodeType,
                                        attributeType=True)
            if attrType not in yielded \
                and 'CtypeOf' not in attrType:
                yield attrType
                yielded.append(attrType)


def _fromMFnData() -> Generator[str, None, None]:
    """
    Yields Maya attribute type strings derived from
    :class:`~maya.api.OpenMaya.MFnData`.
    """
    yielded = []

    for k, v in om.MFnData.__dict__.items():
        if k.startswith('k'):
            mt = re.match(r"^k(.*)$", k)
            if mt:
                mtype = uncap(mt.groups()[0])
                if mtype not in yielded + ['last', 'invalid', 'any']:
                    yield mtype
                    yielded.append(mtype)

def _generate() -> list[str]:
    out = set()

    funcs = [_fromOnlineHelp,
               _fromMFn,
               _fromMFnData,
               _fromMFnNumericData,
               _fromAttrInfo]

    for func in funcs:
        out = out.union(set(func()))

    out = out.union(set(ADDITIONS))
    return list(sorted(out))

#--------------------------------------------|    INIT

def _start():
    global DATA

    try:
        with open(CACHE_FILE_PATH, 'r') as f:
            DATA = json.load(f)
    except FileNotFoundError:
        DATA = _generate()
        try:
            with open(CACHE_FILE_PATH, 'w') as f:
                json.dump(DATA, f, indent=4)
        except OSError:
            m.warning(f"Couldn't write cache file: {CACHE_FILE_PATH}")

_start()