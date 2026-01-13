import os
from typing import Optional, Iterator, Union
from pathlib import Path
import re

class SGStreamInvalidTemplateError(ValueError):
    ...

class SGStreamInvalidVersionError(ValueError):
    ...

class SGStream:
    """
    Notes
    =====

    Templates must follow this format:
    <any identifier>_v<any number of hashes ('#')>.<file extension>

    All version listings are yielded *in reverse* (highest version first).
    """

    #-------------------------------------|    Inst

    @classmethod
    def prep(cls, parentDir, basename, padding=3):
        basename, ext = os.path.splitext(basename)

        if not ext:
            raise SGStreamInvalidTemplateError(
                "basename must have an extension"
            )

        baseTemplate = "{}_v{}.{}".format(basename, '#'*padding, ext[1:])
        return cls(Path(parentDir) / baseTemplate)

    def __init__(self, template:str):
        """
        Templates must follow this format:
        <any identifier>_v<any number of hashes ('#')>.<file extension>

        For example: ``C:\renders\render_v003.exr``
        """
        template = Path(template)
        parentDir = template.parent
        templateBasename = str(template.name)

        templatePat = r"^(.*?)_v#+\.([^\.]+)$"

        mt = re.match(templatePat, templateBasename)

        if mt:
            name, hashes, ext = mt.groups()

            self._parent = parentDir
            self._name = name
            self._padding = len(hashes)
            self._extension = ext
        else:
            raise SGStreamInvalidTemplateError("invalid template")

    #-------------------------------------|    Properties

    def getName(self) -> str:
        return self._name

    def setName(self, name:str):
        self._name = name

    name = property(getName, setName)

    def getParent(self) -> Path:
        return self._parent

    def setParent(self, parent):
        self._parent = Path(parent)

    parent = property(getParent, setParent)

    def getPadding(self) -> int:
        return self._padding

    def setPadding(self, padding:int):
        self._padding = padding

    padding = property(getPadding, setPadding)

    def getExtension(self) -> str:
        return self._extension

    def setExtension(self, ext):
        self._extension = ext.strip('.')

    extension = property(getExtension, setExtension)

    #-------------------------------------|    Member path construction

    def __getitem__(self, version:int) -> Path:
        if version >= 0:
            return self.parent / "{}_v{}.{}".format(
                self.name,
                str(version).zfill(self.padding),
                self.extension
                )
        raise SGStreamInvalidVersionError("version must be >= 0")

    #-------------------------------------|    Actual I/O

    def exists(self) -> bool:
        """This does NOT strictly check for padding."""

        if self.parent.is_dir():
            listing = os.listdir(self.parent)

            if listing:
                pat = re.compile("^" + self.name + "_v[0-9]+" + r"\."
                                 + self.extension + r"$")

                for item in listing:
                    if re.match(pat, item):
                        return True

        return False

    def __iter__(self) -> Iterator[tuple[int, Path]]:
        """:raises FileNotFoundError: the parent directory doesn't exist"""
        pat = re.compile("^" + self.name + "_v([0-9])+" + r"\."
                             + self.extension + r"$")
        versionMap = []

        for item in os.scandir(self.parent):
            name = item.name
            mt = re.match(pat, name)

            if mt:
                versionMap.append((int(mt.group(1)), name))

        for version, name in reversed(
                sorted(versionMap, key=lambda pair: pair[0])
        ):
            yield version, Path(name)

    def first(self) -> tuple[int, Path]:
        return list(self)[-1]

    def last(self) -> tuple[int, Path]:
        """:raises FileNotFoundError: the parent directory doesn't exist"""
        return next(iter(self), None)

    def next(self) -> tuple[int, Path]:
        """
        This is forgiving; if the parent path doesn't exist, it will construct
        a nominal version 1.
        """
        try:
            lastVersion, lastPath = self.last()
            nextVersion = lastVersion + 1
            return nextVersion, self[nextVersion]

        except FileNotFoundError:
            return 1, self[1]

    def __len__(self):
        return len(list(iter(self)))

    #-------------------------------------|    Repr

    def __str__(self):
        return str(self.parent / "{}_v{}.{}".format(self.name,
                                                    '#'*self.padding,
                                                    self.extension))

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, repr(str(self)))


def force_ext(filePath:Union[Path, str], extension:str) -> Path:
    extension = extension.strip('.')
    return Path(os.path.splitext(str(filePath))[0] + '.' + extension)