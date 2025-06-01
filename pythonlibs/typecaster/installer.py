"""

Submodule for installing and updating Typecaster

"""
import os, subprocess, sys
from pathlib import Path
from typecaster import config

VERBOSE = False

if not os.getenv('TYPECASTER'):
    raise Exception("Could not find the TYPECASTER environment variable!")

TYPECASTER_ROOT_PATH = Path( os.getenv('TYPECASTER') ).resolve()

REQUIREMENTS_PATH = ( TYPECASTER_ROOT_PATH / "requirements.txt" ).resolve()

PYTHON_INSTALLFOLDERNAME = f"python{str(sys.version_info.major)}.{str(sys.version_info.minor)}libs"

TYPECASTER_PYTHON_INSTALL_PATH = (TYPECASTER_ROOT_PATH / PYTHON_INSTALLFOLDERNAME).resolve()


def install():
    """Install Typecaster's dependencies that are not included with the main distribution.
    """
    # If it doesn't already exist, create the folder which all of the packages will be installed into
    TYPECASTER_PYTHON_INSTALL_PATH.mkdir(exist_ok=True)
    
    pathstring = str(TYPECASTER_PYTHON_INSTALL_PATH)

    print("Installing Typecaster dependency packages...")
    command = f"""hython -m pip install --target "{pathstring}" -r {REQUIREMENTS_PATH}"""
    # subprocess.run(command, shell=True)
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode == 0:
        print("Install process executed successfully")
        if VERBOSE: print(stdout.decode())
    else:
        print("Install process failed with error:")
        print(stderr.decode())

    # Update houdini path in-place
    if pathstring not in sys.path:
        print(f"Adding {pathstring} to path")
        sys.path.insert(0, pathstring)

def update():
    raise NotImplementedError("Yeah I should probably make an updater too...")

def check_installed(auto_install=True):
    """Check if Typecaster is fully installed, installing it's dependencies if needed
    (when enabled in the config file and auto_install is True).

    Arguments:
        auto_install (bool, optional): When enabled, typecaster will attempt to
            install it's dependencies if needed (and enabled in the config file).
            Defaults to True.

    Returns:
        bool: Returns True if typecaster is installed, or it was installed.
    """
    validinstall = False
    try:
        from typecaster.font import Font
        # # Do I need to do this or is attempting an import enough?
        # Font( path=Path(os.path.expandvars("$TYPECASTER/fonts/Roboto-VariableFont_wdth,wght.ttf")).resolve(), number=0)
        validinstall = True
    except ImportError:
        validinstall = False
        pass
    
    if not validinstall:
        if auto_install and config.get_config().get("auto_install_python_dependencies", 0) == 1:
            install()
            validinstall = True
    return validinstall