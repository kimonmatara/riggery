from typing import Optional, Iterable, Union
import importlib
import os
import sys

#-----------------------------------------|
#-----------------------------------------|    HELPERS
#-----------------------------------------|

uncap = lambda x: x[0].lower()+x[1:]

#-----------------------------------------|
#-----------------------------------------|    ERRORS
#-----------------------------------------|

class ClassPoolError(RuntimeError):
    ...

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
#-----------------------------------------|    META
#-----------------------------------------|

class ClassPoolMeta(type):

    def __new__(meta, clsname, bases, dct):
        if bases and dct.get('__pool_package__') is None:
            raise TypeError('__pool_package__ must be defined')

        return super().__new__(meta, clsname, bases, dct)

#-----------------------------------------|
#-----------------------------------------|    CLASS
#-----------------------------------------|

class ClassPool(metaclass=ClassPoolMeta):

    __pool_package__:str
    __can_invent__:bool = False

    #-----------------------------|    Init

    def __new__(cls):
        if cls is ClassPool:
            raise TypeError("The base ClassPool class can't be instantiated")
        return object.__new__(cls)

    def __init__(self):
        self._cache = {}

    #-----------------------------|    Retrieval

    def _checkKey(self, key):
        if not key[0].isupper():
            raise CpInvalidKeyError(f"Invalid class name: '{key}'")

    def _getClassModule(self, modname:str):
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

    def _inventClass(self, clsname:str):
        raise NotImplementedError

    def _getClass(self, key:str):
        self._checkKey(key)

        try:
            cls = self._cache[key]
        except KeyError:
            cls = self._loadClass(key)

            if cls is None:
                try:
                    cls = self._inventClass(key)
                except NotImplementedError:
                    raise KeyError(f"No class '{key}'")

            self._cache[key] = cls

        return cls

    __getitem__ = __getattr__ = _getClass

    #-----------------------------|    Rehash

    def rehash(self):
        """
        Clears the class cache and removes any associated modules from
        ``sys.modules``, so that reloads will be triggered on subsequent
        access attempts.
        """
        modsFromClasses = [cls.__module__ for cls in self._cache.values()]
        modsToDelete = [mod for mod in modsFromClasses
                        if mod.startswith(self.__pool_package__)]

        for mod in modsToDelete:
            try:
                del(sys.modules[mod])
            except KeyError:
                continue

        self._cache.clear()

    #-----------------------------|    Stubbing

    @property
    def packageDir(self):
        """
        :return: The class pool's root directory.
        """
        return os.path.dirname(
            importlib.util.find_spec(self.__pool_package__).origin
        )

    def _getModBasenameFromClsName(self, clsname:str):
        return clsname[0].lower()+clsname[1:]

    def _initStubFilePath(self, clsname:str):
        filename = "{}.py".format(self._getModBasenameFromClsName(clsname))
        return os.path.join(self.packageDir, filename)

    def _initStubContent(self, clsname:str):
        raise NotImplementedError(
            "Stubbing is not supported for class pool {}".format(self)
        )

    def initStub(self, clsname:str):
        self._checkKey(clsname)
        filepath = self._initStubFilePath(clsname)

        if os.path.isfile(filepath):
            raise RuntimeError(f"Stub file already exists: {filepath}")

        content = self._initStubContent(clsname)

        with open(filepath, 'w') as f:
            f.write(content)

        print(f"Created stub file: {filepath}")
        return filepath

    #-----------------------------|    Repr

    def __repr__(self):
        return "<'{}' pool at {}>".format(self.__class__.__name__,
                                          self.__pool_package__)