import sys
import os
from typing import Optional
from pathlib import Path
import importlib.util

def modname_from_filename(filename:str) -> Optional[str]:
    """
    :param filename: the module file path; if it's a directory, the reference
        will be converted to a nested ``__init__.py`` file
    :return: An import name for the given Python module, but only if it would
        be reachable via a standard ``import`` statement, otherwise None.
    """
    full_path = Path(filename).resolve()

    if full_path.is_dir():
        full_path /= '__init__.py'

    if not full_path.is_file() or full_path.suffix.lower() != '.py':
        return None

    base_module_name = full_path.stem

    for path_entry in sys.path:
        path_entry = Path(path_entry).resolve()

        try:
            relative_path = full_path.relative_to(path_entry)
            parts = relative_path.parts
            package_parts = parts[:-1]

            current_dir = path_entry
            is_valid_package_structure = True

            for part in package_parts:
                current_dir = current_dir / part
                if not (current_dir / "__init__.py").exists():
                    is_valid_package_structure = False
                    break

            if is_valid_package_structure:
                dotted_name_parts = list(package_parts) + [base_module_name]
                return ".".join(dotted_name_parts)

        except ValueError:
            continue

    return None

def filename_from_modname(modname:str) -> Optional[str]:
    try:
        return sys.modules[modname].__file__
    except KeyError:
        spec = importlib.util.find_spec(modname)

        if spec is None:
            return None

        return spec.origin