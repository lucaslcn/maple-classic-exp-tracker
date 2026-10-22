import os
import sys


def get_app_dir() -> str:
    """
    Returns the directory containing the executable when frozen (PyInstaller),
    or the project root directory when running from Python source.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_bundle_dir() -> str:
    """
    Returns the internal bundle directory (_MEIPASS) when frozen (PyInstaller),
    or the project root directory when running from Python source.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.abspath(sys._MEIPASS)
    return get_app_dir()


def get_data_path(*parts: str) -> str:
    """
    Resolves a path inside the persistent 'data' folder located next to the executable.
    """
    data_dir = os.path.join(get_app_dir(), "data")
    if not parts:
        return data_dir
    return os.path.join(data_dir, *parts)

