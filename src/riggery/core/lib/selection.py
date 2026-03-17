from functools import wraps
from riggery.general.iterables import without_duplicates
import maya.cmds as m

def _fuzzySelect(items):
    if items:
        allMatches = []

        for item in items:
            matches = m.ls(item)

            if matches:
                allMatches += matches
            else:
                if '|' in item:
                    item = item.split('|')[-1]
                    matches = m.ls(item)

                    if matches:
                        allMatches += matches

        allMatches = list(without_duplicates(allMatches))

        def deferredSelect():
            m.select(cl=True)
            for x in allMatches:
                try:
                    m.select(x, add=True)
                except:
                    continue

        m.evalDeferred(deferredSelect)

    else:
        def deferredSelect():
            m.select(cl=True)

        m.evalDeferred(deferredSelect)

class Selection:
    def __enter__(self):
        self._prevSelection = m.ls(sl=True)
        return self

    def __exit__(self, type, value, traceback):
        _fuzzySelect(self._prevSelection)
        return False

def keepsel(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with Selection():
            result = f(*args, **kwargs)
        return result
    return wrapper