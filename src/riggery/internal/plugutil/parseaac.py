"""
Defines a function to parse the return of
:meth:`~maya.api.OpenMaya.MFnAttribute.getAddAttrCmd`.
"""
from typing import Union
import re

def interpretValue(value:str) -> Union[str, bool, float, int]:
    mt = re.match(r"^(true|false)$", value)
    if mt:
        return {'true': True, 'false': False}[mt.group(1)]
    else:
        mt = re.match(r"^\"(.*?)\"$", value)
        if mt:
            return mt.group(1)
        else:
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except:
                    return value

def parseAddAttrCmd(cmd:str) -> dict:
    """
    Parses the string returned by
    :meth:`~maya.api.OpenMaya.MFnAttribute.getAddAttrCmd` into a dictionary.
    """
    pat = r"-([a-zA-Z]+[a-zA-Z0-9]?) (true|false|\".*?\"|0-9|\-?[0-9]?.*?(?: |^))"
    return dict([(a, interpretValue(b.strip()))
                 for a, b in re.findall(pat, cmd)])