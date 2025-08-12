"""Extracts node type tags from online help."""

import re
import maya.cmds as m

URL = r"https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Tech-Docs/Nodes/index_tags.html"
PAT = re.compile(r'^\s*<tt>(.*?)</tt>.*?>(.*?)</a>.*?$')
ALLNODETYPES = set(m.allNodeTypes(includeAbstract=False))

def download() -> dict:
    """
    :return: A dictionary of nodeType: node tag. In riggery, tags are typically
        used as node suffixes.
    """
    import requests
    response = requests.get(URL)
    out = {}
    for line in response.text.split('\n'):
        mt = re.match(PAT, line)
        if mt:
            tag, nodeType = mt.groups()
            if nodeType in ALLNODETYPES:
                out[nodeType] = tag
    return out