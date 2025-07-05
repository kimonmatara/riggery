"""
Defines a function to parse the return of
:meth:`~maya.api.OpenMaya.MFnAttribute.getAddAttrCmd`.
"""

def parseAddAttrCmd(cmd:str) -> dict:
    """
    Parses the string returned by
    :meth:`~maya.api.OpenMaya.MFnAttribute.getAddAttrCmd` into a dictionary.
    """
    cmd = cmd.strip().strip(';')
    pairs = cmd.split(' -')

    out = {}
    del(pairs[0])

    for pair in pairs:
        pair = pair.split(' ')
        key = pair.pop(0)
        value = ' '.join(pair)
        value = value.strip('"')
        if value == '':
            value = True
        else:
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    value = {'true': True,
                             'false': False}.get(value, value)

        out[key] = value

    return out