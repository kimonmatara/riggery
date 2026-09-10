from typing import Iterator, Optional
import os
from pathlib import Path
import re

class NotAStreamedNameError(Exception):...
class BadSGTemplateError(Exception):...
class SGEmptyStreamError(Exception):...

#-----------------------------------|
#-----------------------------------|    Stream wrangling utilities
#-----------------------------------|

TMPL_FROM_NAME_PAT = re.compile(r"(?:(?<=^)|(?<=_))v[0-9]+(?=[.$_])")
TMPL_HASH_GROUP_PAT = re.compile(r"(?:(?<=^)|(?<=_))v#+(?=[.$_])")

def getTemplateFromName(fileName:str|Path) -> str:
    fileName = Path(fileName)
    baseName:str = fileName.name

    def replacer(x:re.Match):
        substring = x.string[x.start():x.end()]
        return re.sub(r"[0-9]", "#", substring)

    newString, numSubs = re.subn(TMPL_FROM_NAME_PAT, replacer, baseName)

    if numSubs == 0:
        raise NotAStreamedNameError(
            "Can't derive a template from name '{}'; no number group".format(baseName)
        )

    elif numSubs > 1:
        raise NotAStreamedNameError(
            "Can't derive a template from name '{}'; too many number groups".format(baseName)
        )

    return str(fileName.parent / newString)

def getVersionStringFromName(fileName:str|Path) -> str:
    found = re.findall(TMPL_FROM_NAME_PAT, Path(fileName).name)
    if len(found) == 1:
        return found[0][1:]
    raise NotAStreamedNameError(fileName)

def actualizeTemplate(template:str, version:int) -> str:
    template = Path(template)
    baseName:str = template.name

    def replacer(x:re.Match):
        substring = x.string[x.start():x.end()]
        return 'v' + str(version).zfill(substring.count('#'))

    newString, numSubs = re.subn(TMPL_HASH_GROUP_PAT, replacer, baseName)

    if numSubs != 1:
        raise BadSGTemplateError("Can't actualize bad template: '{}'".format(baseName))

    return str(template.parent / newString)

#-----------------------------------|
#-----------------------------------|    SG STREAM CLASS
#-----------------------------------|

class SGStream:

    #-------------------------------|    Init

    def __init__(self, template:str|Path):
        actualizeTemplate(template, 0) # error
        self._template = str(Path(template))

    #-------------------------------|    Constructors

    @classmethod
    def fromTemplate(cls, template:str|Path) -> 'SGStream':
        return cls(template)

    @classmethod
    def fromName(cls, name:str|Path) -> 'SGStream':
        template = getTemplateFromName(name)
        return cls(template)

    @classmethod
    def iterFromDir(cls, dirpath:str|Path) -> Iterator['SGStream']:
        visited = set()

        for item in os.scandir(Path(dirpath)):
            if item.is_file():
                path = item.path
                try:
                    inst = cls.fromName(path)
                except NotAStreamedNameError:
                    continue
                if inst not in visited:
                    visited.add(inst)
                    yield inst

    #-------------------------------|    Iteration

    def isMember(self, path:str|Path) -> bool:
        path = Path(path)
        return self.fromName(path) == self

    def _items(self) -> Iterator[tuple[int, Path]]:
        for item in os.scandir(Path(self._template).parent):
            if self.isMember(item.path):
                version = int(getVersionStringFromName(item.path))
                yield version, item.path

    def items(self) -> Iterator[tuple[int, Path]]:
        yield from sorted(self._items(), key=lambda pair: pair[0])

    def _versions(self) -> Iterator[int]:
        for version, _ in self._items():
            yield version

    def versions(self) -> Iterator[int]:
        yield from sorted(self._versions())

    def _paths(self) -> Iterator[Path]:
        for version, path in self._items():
            yield path

    def paths(self) -> Iterator[Path]:
        for version, path in self.items():
            yield path

    def first(self) -> Optional[Path]:
        return next(self.paths(), None)

    def last(self) -> Path:
        try:
            paths = list(self.paths())

            if paths:
                return paths[-1]

        except FileNotFoundError:
            pass
        raise SGEmptyStreamError

    def firstVersion(self) -> Optional[int]:
        return next(self.versions(), None)

    def lastVersion(self) -> int:
        """
        :raises SGEmptyStreamError
        """
        versions = list(self.versions())
        if versions:
            return versions[-1]
        raise SGEmptyStreamError

    def nextVersion(self) -> int:
        try:
            lastVersion = self.lastVersion()
        except SGEmptyStreamError:
            return 1
        return lastVersion + 1

    def next(self) -> Path:
        return self[self.nextVersion()]

    def __getitem__(self, version:int):
        return Path(actualizeTemplate(self._template, version))

    def __len__(self):
        return len(list(self._items()))

    def exists(self) -> bool:
        return next(self._items(), None) is not None

    #-------------------------------|    Identity

    def __eq__(self, value: object, /) -> bool:
        return str(value) == str(self)

    def __hash__(self) -> int:
        return hash((type(self), self._template))

    #-------------------------------|    Repr

    def __str__(self) -> str:
        return self._template

    def __repr__(self) -> str:
        return "{}({})".format(type(self).__name__, repr(self._template))