import re
from typing import Union, Iterator, Optional
from pathlib import Path

from ..nodetypes import __pool__ as nodes
from riggery.general.functions import short
from riggery.core.lib import namespaces as _ns

DependNode = nodes['DependNode']

import maya.cmds as m


class Reference(DependNode):

    __capture_construction__ = False

    #-------------------------------------|    Constructors

    @classmethod
    @short(namespace='ns')
    def create(cls, filePath:Union[str, Path], namespace:Optional[str]=None):
        """
        :param filePath: the file path to point the reference to
        :param namespace/ns: the reference namespace; if omitted, one will be
            improvised
        """
        filePath = Path(filePath)

        if namespace is None:
            i = 0
            stem = filePath.stem

            while True:
                namespace = stem

                if i > 0:
                    namespace += str(i)

                if m.namespace(exists=namespace):
                    i += 1
                    continue

                break

        result = m.file(filePath.as_posix(),
                        namespace=namespace,
                        reference=True)
        return cls(m.referenceQuery(result, referenceNode=True))

    @classmethod
    def iterPaths(cls, withoutCopyNumber:bool=False) -> Iterator[Path]:
        """
        Yields paths used by all references in the scene.

        :param withoutCopyNumber/wcn: strip Maya copy numbers, and return just
            the base paths; defaults
        """
        visited = set()

        for ref in m.file(q=True, r=True):
            if withoutCopyNumber:
                ref = cls._stripCopyNumber(ref)

                if ref in visited:
                    continue

                visited.add(ref)
                yield Path(ref)

    @classmethod
    def findFromPath(cls,
                     filePath:Union[str, Path],
                     strict:Optional[bool]=None) -> Iterator['Reference']:
        """
        Yields references that point to the given path.

        :param filePath: the file path, in posix or nt format
        :param strict: if this is True, then any copy number is stripped from
            *filePath* before searching; if it's False, then only references
            with this exact path will be returned; defaults to True if
            *filePath* is provided with a copy number, otherwise False
        """
        if strict is None:
            strict = cls._getCopyNumber(filePath) is not None

        filePath = Path(filePath)

        for ref in cls.ls():
            if ref.getPath(withoutCopyNumber=not strict) == filePath:
                yield ref

    #-------------------------------------|    Path access

    @short(withoutCopyNumber='wcn')
    def getPath(self, withoutCopyNumber:bool=False) -> Path:
        """
        :param withoutCopyNumber/wcn: strip any Maya 'copy number'; defaults to
            False
        :return: The file path this reference points to.
        """
        return Path(m.referenceQuery(str(self),
                                     filename=True,
                                     withoutCopyNumber=withoutCopyNumber))

    path = property(getPath)

    def getBasePath(self) -> Path:
        """Equivalent to ``getPath(withoutCopyNumber=True)``."""
        return self.getPath(withoutCopyNumber=True)

    basePath = property(getBasePath)

    #-------------------------------------|    Util

    @staticmethod
    def _getCopyNumber(filePath:str) -> Optional[int]:
        mt = re.match(r"^.*?\{([0-9]+)}$", str(filePath))
        if mt:
            return int(mt.group(1))

    @staticmethod
    def _stripCopyNumber(filePath:str) -> str:
        filePath = str(filePath)
        mt = re.match(r"^(.*?)\{[0-9]+}$", filePath)

        if mt:
            return mt.group(1)
        return filePath