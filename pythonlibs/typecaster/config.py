"""
Submodule for parsing Typecaster's config file.
"""

from json import load as json_load
from os.path import expandvars
from pathlib import Path

CONFIG_PATHSTRING = "$TYPECASTER/Typecaster_config.json"

_CONFIG_ = {}

def __get_config__()-> dict:
    """Get the current config WITHOUT writing it to the module anywhere. In almost
    every situation this should not be used directly.

    Returns:
        dict: Dictionary of the config file's current state.
    """
    cfg = {}
    filepath = Path(expandvars(CONFIG_PATHSTRING))
    if filepath.exists():
        with filepath.open() as file:
            cfg = json_load(file)
    return cfg

__CONFIG_DEPENDENCIES__ = []

def add_config_dependencies( *args ):
    """Essentially, the goal here is that when you call update_config(),
    you'd expect all of typecaster to behave as if it's using the new config.
    Tracking and clearing specific cached iterables connected to the config 
    assists with this.

    An example of this would be typecaster.fontFinder's name_info(), families(), and path_to_name().
    Since the list of fonts returned by these functions are affected by the config file,
    it is best to clear their internal dicts and regenerate them whenever the config is updated.
    The reason why this isn't directly declared in this submodule is that it would require some circular
    importing, and wouldn't be needed if the config submodule is used on it's own in a session.

    Args:
        Iterable_to_clear (iterable): any argument given will be added to a list of
            things to clear on each config update.
    """
    for dep in args:
        __CONFIG_DEPENDENCIES__.append(dep)

def update_config():
    _CONFIG_.clear()
    for dependency in __CONFIG_DEPENDENCIES__:
        dependency.clear()
    _CONFIG_.update(__get_config__())

def get_config() -> (dict):
    """Returns a dictionary from the config file if it exists, initializing 
    the config file if it hasn't been already.
    """
    if not _CONFIG_:
        update_config()
    return _CONFIG_