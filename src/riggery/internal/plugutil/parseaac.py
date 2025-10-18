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

# def parseAddAttrCmd(cmd:str) -> dict:
#     """
#     Parses the string returned by
#     :meth:`~maya.api.OpenMaya.MFnAttribute.getAddAttrCmd` into a dictionary.
#     """
#     pat = r"-([a-zA-Z]+[a-zA-Z0-9]?) (true|false|\".*?\"|0-9|\-?[0-9]?.*?(?: |^))"
#     return dict([(a, interpretValue(b.strip()))
#                  for a, b in re.findall(pat, cmd)])

# def parseAddAttrCmd(cmd:str) -> dict:

#     cmd = cmd.strip(' ').strip(';')
#     elems = cmd.split(' ')[1:]
#     out = []
#
#     print('The cmd is ', cmd)
#     print("The split elems are: ", elems)
#
#     for elem in elems:
#         mt = re.match("^-([a-zA-Z]+[a-zA-Z0-9]?)$", elem)
#         if mt: # it's a flag
#             if out:
#                 if len(out[-1]) == 1:
#                     out[-1].append(True)
#             out.append([mt.group(1)])
#         else:
#             out[-1].append(interpretValue(elem))
#
#     from pprint import pprint
#     pprint(out)
#     out = dict(out)
#
#     return out

def parseAddAttrCmd(cmd:str) -> dict:
    """
    Parses the string returned by
    :meth:`~maya.api.OpenMaya.MFnAttribute.getAddAttrCmd` into a dictionary.
    """
    cmd = cmd.strip(' ').strip(';')
    cmd = re.match(r"^\s*addAttr(.*)$", cmd).group(1)

    chunkPats = [r'".*?"',
                 r'-[a-zA-Z]+[a-zA-Z0-9]?']

    chunkPat = r"({})".format("|".join(chunkPats))

    chunks = list(filter(bool, [x.strip() for x in re.split(chunkPat, cmd)]))

    pairs = []

    for chunk in chunks:
        mt = re.match(r"^-([a-zA-Z]+[a-zA-Z0-9]?)$", chunk)
        if mt:
            pairs.append([mt.group(1)])
        else:
            value = interpretValue(chunk)
            pairs[-1].append(value)

    for pair in pairs:
        if len(pair) == 1:
            pair.append(True)

    return dict(pairs)