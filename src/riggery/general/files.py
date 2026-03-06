import os
from typing import Optional, Iterator, Union
from pathlib import Path
import re
from .functions import short

class SGStreamInvalidTemplateError(ValueError):
    ...

class SGStreamInvalidFileOrDirNameError(ValueError):
    ...

SG_PARSE_PAT = re.compile(r"^(?:(.*?)_)?v([0-9]+)(?:\.([^.]+))?$")
SG_TMPL_PAT = re.compile(r"^(?:(.*?)_)?v(#+)(?:\.([^.]+))?$")

def conformExtension(ext) -> Optional[str]:
    if ext:
        if ext.startswith('.'):
            ext = ext[1:]
        return ext

class SGStream:
    """
    Notes
    =====

    Templates must follow this format:
    <any identifier>_v<any number of hashes ('#')>.<file extension>
    or
    v<any number of hashes ('#')>.<file extension>

    All version listings are yielded *in reverse* (highest version first).
    """
    #-------------------------------|    Init

    @classmethod
    def iterFromDir(cls, parentdir:Union[str, Path]) -> Iterator['SGStream']:
        visited = []
        parentdir = Path(str(parentdir))

        for item in os.scandir(parentdir):
            try:
                stream = cls.fromName(parentdir / item.name)
            except SGStreamInvalidFileOrDirNameError:
                continue

            if stream not in visited:
                visited.append(stream)
                yield stream

    @classmethod
    def fromTemplate(cls, template:Union[str, Path]):
        template = Path(str(template))

        mt = re.match(SG_TMPL_PAT, template.name)

        if mt:
            descriptor, hashes, extension = mt.groups()
            inst = cls()
            inst.descriptor = descriptor
            inst.padding = len(hashes)
            inst.extension = extension
            inst.parent = template.parent

            return inst

        raise SGStreamInvalidTemplateError(template)

    @classmethod
    def fromName(cls, fileOrDirName:Union[str, Path]):
        fileOrDirName = Path(fileOrDirName)

        mt = re.match(SG_PARSE_PAT, fileOrDirName.name)

        if mt:
            descriptor, version, extension = mt.groups()
            inst = cls()
            inst.descriptor = descriptor
            inst.padding = len(version)
            inst.extension = extension
            inst.parent = fileOrDirName.parent

            return inst

        raise SGStreamInvalidFileOrDirNameError(fileOrDirName)

    def __init__(self,
                 parent:Optional[Union[str, Path]]=None,
                 descriptor:Optional[str]=None,
                 padding:int=3,
                 extension:Optional[str]=None):
        self.parent = parent
        self.descriptor = descriptor
        self.padding = padding
        self.extension = padding

    #-------------------------------|    Properties

    def getParent(self):
        return self._parent

    def setParent(self, parentDir:Optional[Union[str, Path]]):
        if parentDir:
            self._parent = Path(parentDir)
        else:
            self._parent = None

    def clearParent(self):
        self._parent = None
        return self

    parent = property(getParent, setParent, clearParent)

    def getDescriptor(self) -> Optional[str]:
        return self._descriptor

    def setDescriptor(self, descriptor:Optional[str]):
        self._descriptor = descriptor
        return self

    def clearDescriptor(self):
        self._descriptor = None
        return self

    descriptor = property(getDescriptor, setDescriptor, clearDescriptor)

    def getPadding(self) -> int:
        return self._padding

    def setPadding(self, padding:int):
        self._padding = padding

    padding = property(getPadding, setPadding)

    def getExtension(self) -> str:
        return self._extension

    def setExtension(self, ext:Optional[str]):
        self._extension = conformExtension(ext)
        return self

    def clearExtension(self):
        self._extension = None
        return self

    extension = property(getExtension, setExtension, clearExtension)

    #-------------------------------|    Access

    @short(ignorePadding='ip')
    def getPattern(self, ignorePadding:bool=False) -> re.Pattern:
        elems = []

        if self.descriptor:
            elems.append(self.descriptor)

        if ignorePadding:
            elems.append(r"v([0-9]+)")
        else:
            elems.append(r"v([0-9]{" + str(self.padding) + "})")

        pat = '_'.join(elems)
        if self.extension:
            pat += '.' + self.extension

        pat = r"^" + pat + "$"
        return re.compile(pat)

    pattern = property(getPattern)

    def _items(self) -> Iterator[tuple[int, Path]]:
        if self.parent is not None:
            pat = self.pattern

            for item in os.scandir(self.parent):

                n = item.name
                mt = re.match(pat, n)

                if mt:
                    version = int(mt.group(1))
                    yield version, self.parent / n

    def items(self) -> Iterator[tuple[int, Path]]:
        yield from sorted(self._items(), key=lambda pair: pair[0])

    def _versions(self) -> Iterator[int]:
        for version, path in self._items():
            yield version

    def versions(self) -> Iterator[int]:
        yield from sorted(self._versions())

    def _paths(self) -> Iterator[Path]:
        for version, path in self._items():
            yield path

    def paths(self) -> Iterator[Path]:
        for version, path in self.items():
            yield path

    def __contains__(self, version:int) -> bool:
        return version in self._versions()

    def first(self) -> Optional[Path]:
        return next(self.paths(), None)

    def last(self) -> Optional[Path]:
        paths = list(self.paths())
        if paths:
            return paths[-1]

    def firstVersion(self) -> Optional[int]:
        return next(self.versions(), None)

    def lastVersion(self) -> Optional[int]:
        versions = list(self.versions())
        if versions:
            return versions[-1]

    def nextVersion(self) -> int:
        lastVersion = self.lastVersion()
        if lastVersion is None:
            return 1
        return lastVersion + 1

    def next(self) -> Path:
        return self[self.nextVersion()]

    def __getitem__(self, version:int):
        tmpl = Path(str(self))
        basename = tmpl.name
        basename = basename.replace(
            '#' * self.padding, str(version).zfill(self.padding)
        )
        return tmpl.parent / basename

    def __len__(self):
        return len(list(self.items()))

    def exists(self) -> bool:
        return next(self._items(), None) is not None

    #-------------------------------|    Repr

    def __str__(self):
        elems = []

        if self.descriptor:
            elems.append(self.descriptor)

        elems.append('v' + ('#' * self.padding))

        basename = '_'.join(elems)

        if self.extension:
            basename += '.' + self.extension

        if self.parent:
            return str(self.parent / basename)
        return basename

    def __eq__(self, other):
        return str(self) == str(other)