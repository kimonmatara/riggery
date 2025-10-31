from warnings import warn
import inspect
import re
import os
import importlib
from pathlib import Path
from typing import Optional
from types import ModuleType
from abc import ABC, ABCMeta, abstractmethod
import sys

from riggery.general.strings import cap, uncap


#-----------------------------------------|
#-----------------------------------------|    ERRORS
#-----------------------------------------|

class ClassPoolError(Exception):
    pass

class CpInvalidKeyError(ClassPoolError):
    """Disallowed pool key (class name)."""

class CpMissingModuleError(ClassPoolError):
    """The class module could not be found."""

class CpModuleExecError(ClassPoolError):
    """The class module was found, but couldn't be imported."""

class CpClassAccessError(ClassPoolError):
    """The class module was successfully imported, but the class couldn't be
    retrieved."""

class CpInvalidKeyError(ClassPoolError):
    """Disallowed pool key (class name)."""

#-----------------------------------------|
#-----------------------------------------|    Constants
#-----------------------------------------|

DEFAULT_STUB_TEMPLATE = \
"""\
class {}:

    ...
"""

#-----------------------------------------|
#-----------------------------------------|    BASE CLASS
#-----------------------------------------|

class ClassPool:

    #-----------------------------|    Instantiation

    def __init__(self):
        frame = inspect.currentframe()
        caller_globals = frame.f_back.f_globals

        msg = (f"'{self.__class__.__name__}' must be instantiated inside a "
               "package __init__.py")

        modulename = caller_globals['__name__']

        if modulename == '__main__':
            raise TypeError(msg)

        try:
            filename = caller_globals['__file__']
        except KeyError:
            raise TypeError(msg)

        filename = Path(filename)

        if filename.name != '__init__.py':
            raise TypeError(msg)

        self.__package_dirname__ = str(filename.parent)
        self.__pool_package__ = modulename

        self._cache = {}

    #-----------------------------|    Retrieval

    def _checkKey(self, key:str) -> None:
        """:raises CpInvalidKeyError:"""
        if not key[0].isupper():
            raise CpInvalidKeyError(key)

    def _getClassModule(self, modname:str) -> ModuleType:
        """:raises CpMissingModuleError:"""
        try:
            return sys.modules[modname]
        except KeyError:
            spec = importlib.util.find_spec(modname)

            if spec is None:
                raise CpMissingModuleError(modname)

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sys.modules[modname] = mod

            return mod

    def _loadClass(self, clsname:str) -> Optional[type]:
        """:raises CpClassAccessError:"""
        modname = '{}.{}'.format(self.__pool_package__, uncap(clsname))
        try:
            mod = self._getClassModule(modname)
        except CpMissingModuleError:
            return

        try:
            return getattr(mod, clsname)
        except AttributeError:
            raise CpClassAccessError(
                f"Can't find '{clsname}' on module '{modname}'"
            )

    def _getClass(self, key:str) -> type:
        """
        :raises KeyError:
        """
        try:
            cls = self._cache[key]

        except KeyError:
            self._checkKey(key)
            cls = self._loadClass(key)

            if cls is None:
                raise KeyError(f"No class '{key}'")

            self._cache[key] = cls

        return cls

    __getitem__ = _getClass

    def __getattr__(self, key:str):
        try:
            return self._getClass(key)
        except:
            raise AttributeError(f"{key}")

    #-----------------------------|    Caching

    def preload(self) -> 'ClassPool':
        """
        Scans the class pool's directory and attempts to load any classes not
        already in the cache.
        """
        for item in os.listdir(self.__package_dirname__):
            mt = re.match(r"^(.*)\.py$", item)
            if mt:
                clsname = cap(mt.group(1))
                if clsname not in self._cache:
                    try:
                        retrieved = self._loadClass(clsname)
                    except:
                        retrieved = None

                    if retrieved is not None:
                        self._cache[clsname] = retrieved
        return self

    def rehash(self) -> 'ClassPool':
        """Clears the class cache and removes any associated modules from
        ``sys.modules``, so that reloads will be triggered on subsequent access
        attempts."""

        modsFromClasses = [cls.__module__ for cls in self._cache.values()]
        modsToDelete = set([mod for mod in modsFromClasses
                            if mod.startswith(self.__pool_package__)])

        for modName in sys.modules:
            if modName.startswith(self.__pool_package__) \
                    and modName != self.__pool_package__:
                modsToDelete.add(modName)

        for mod in modsToDelete:
            try:
                del(sys.modules[mod])
            except KeyError:
                continue

        self._cache.clear()
        return self

    #-----------------------------|    Authoring

    def _initStubContent(self, clsname, **kwargs):
        """This should be overriden in subclasses. The default implementation
        produces a very basic class declaration which may not work for every
        class pool."""

        return DEFAULT_STUB_TEMPLATE.format(clsname)

    def getStub(self, clsname:str, *, overwrite:bool=False, **kwargs
                ) -> tuple[str, type]:
        """
        Creates a module for the named class if one doesn't already exist. If
        *overwrite* is True, the file will be overwritten regardless.

        Once the filename has been resolved, an attempt is made to load the
        class; if that's unsuccessful (because the existing declaration or the
        stub content bugs out), the first member of the return tuple will be
        None.

        :param clsname: the name of the class to initialize
        :param overwrite: if the class file already exists, overwrite it;
            defaults to False
        :param \*\*kwargs: passed along to :meth:`_initStubContent` if you want
            to do something with it (e.g. specify a parent class)

        :return: Tuple of ``(retrieved class:Optional[type], filename:str)``
        """
        self._checkKey(clsname)
        modname = f'{uncap(clsname)}.py'
        filename = Path(self.__package_dirname__) / modname

        if not (filename.is_file() and not overwrite):
            content = self._initStubContent(clsname, **kwargs)

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
        try:
            cls = self[clsname]
        except:
            cls = None

        return cls, str(filename)


class ClassPoolWithInvention(ClassPool):

    __abstract__ = True

    @abstractmethod
    def _inventClass(self, clsname:str):
        """Implement this for dynamic class construction."""

    def _getClass(self, key:str) -> type:
        """
        :raises KeyError:
        """
        try:
            cls = self._cache[key]

        except KeyError:
            self._checkKey(key)
            cls = self._loadClass(key)

            if cls is None:
                cls = self._inventClass
            self._cache[key] = cls

        return cls