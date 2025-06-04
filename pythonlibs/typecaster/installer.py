"""

Submodule for installing and updating Typecaster

"""
import os, subprocess, sys
from pathlib import Path
from typecaster import config


# No point in working with the installer if $TYPECASTER doesn't exist.
if not os.getenv('TYPECASTER'):
    raise Exception("Could not find the TYPECASTER environment variable!")

TYPECASTER_ROOT_PATH = Path( os.getenv('TYPECASTER') ).resolve()

REQUIREMENTS_PATH = ( TYPECASTER_ROOT_PATH / "requirements.txt" ).resolve()

PYTHTON_VERSION = f"{str(sys.version_info.major)}.{str(sys.version_info.minor)}"
PYTHON_INSTALLFOLDERNAME = f"python{PYTHTON_VERSION}libs"

TYPECASTER_PYTHON_INSTALL_PATH = (TYPECASTER_ROOT_PATH / PYTHON_INSTALLFOLDERNAME).resolve()

HMAJOR = int(os.getenv("HOUDINI_MAJOR_RELEASE"))

HMINOR = int(os.getenv("HOUDINI_MINOR_RELEASE"))

# If this is true, Houdini is below the version number where pip is included in it's python instalation. Additional checks will be run.
PIP_UNCERTAIN = HMAJOR < 19 or ( HMAJOR == 19 and HMINOR < 5 )

def install_dependencies(verbose=False):
    """Install Typecaster's dependencies that are not included with the main distribution.

    Args:
        verbose (bool, optional): If enabled, the full stdout of running pip will be printed. Defaults to False.

    Returns:
        bool: Returns True if Typecaster could be installed. Otherwise False.
    """    
    
    if PIP_UNCERTAIN:
        print( f"pip not installed by default in this version of Houdini ({HMAJOR}.{HMINOR})! Checking for an existing installation.")
        pipstatus = check_install_pip()
        if not pipstatus:
            print("pip could not be found or installed. Typecaster install process terminated.")
            return False
    
    # If it doesn't already exist, create the folder which all of the packages will be installed into
    TYPECASTER_PYTHON_INSTALL_PATH.mkdir(exist_ok=True)
    
    pathstring = str(TYPECASTER_PYTHON_INSTALL_PATH)

    print("Installing Typecaster dependency packages...")
    command = f"""hython -m pip install --target "{pathstring}" -r {REQUIREMENTS_PATH}"""
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode == 0:
        print("Dependency install process executed successfully")
        if verbose: print(stdout.decode())
    else:
        print("Dependency install process failed with error:")
        print(stderr.decode())

    # Update houdini path in-place
    if pathstring not in sys.path:
        print(f"Adding {pathstring} to path")
        sys.path.insert(0, pathstring)
    return True


def update():
    raise NotImplementedError("Updater is currently incomplete!")
    print("Updating Typecaster from github...")
    # command = f"""git pull || SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU && git pull"""
    command = f"""git pull"""
    # command = f"""hython -m pip install --target "{TYPECASTER_PYTHON_INSTALL_PATH}" -r {REQUIREMENTS_PATH}"""
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=TYPECASTER_ROOT_PATH)
    stdout, stderr = process.communicate()
    
    print(stdout.decode())
    print(stderr.decode())


def check_install(auto_install=True, force_if_not_valid=False):
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
        print("Typecaster could not be initialized properly. Are the dependencies installed?")
        if force_if_not_valid:
            validinstall = install_dependencies()
        elif auto_install and config.get_config().get("auto_install_python_dependencies", 0) == 1:
            print("Auto-install is enabled in the config. Attempting install.")
            validinstall = install_dependencies()
        else:
            print("""Auto-install is disabled. Please either run the installer from the shelf tool, or run typecaster.installer.install() from a python shell.""")
    elif force_if_not_valid:
        print("Typecaster already is installed!")
    return validinstall


def check_install_pip(auto_install=True):
    """Check if pip in installed to the current python environment, and attempt to install it if not.

    Raises:
        Exception: Raised if pip couldn't be run AND it couldn't be installed.
    """    
    cmd_piptest = f"""hython -m pip"""
    print(f"Attempting to run pip...")
    process = subprocess.Popen(cmd_piptest, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    haspip = False
    if process.returncode == 0:
        print("pip appears to be installed!")
        haspip = True
    elif auto_install:
        print("pip could not be run. Attempting install...")

        pipgetpath = (Path(os.getenv("HOUDINI_TEMP_DIR"))/"get-pip.py").resolve()
        pipgetpath.parent.mkdir(exist_ok=True)
        if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 9):
            # Main script only supports python 3.9 or higher, so get a version specific one.
            url = f"https://bootstrap.pypa.io/pip/{PYTHTON_VERSION}/get-pip.py"
        else:
            url = f"https://bootstrap.pypa.io/pip/get-pip.py"
        command = f"""curl {url} -o {str(pipgetpath)}"""
        print( f"Downloading get-pip.py to {pipgetpath}")
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            print("get-pip.py successfully downloaded.")

            # While I'd prefer to install pip to houdini specifically, putting stuff here involves admin privileges
            # pippath = (Path(os.getenv("PYTHONHOME"))/"Scripts").resolve()
            # pippath.mkdir(exist_ok=True)
            # command = f"""hython {pipgetpath} --prefix="{pippath}" """
                
            command = f"""hython {pipgetpath}"""
            print(f"Running get-pip.py...")
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                print("pip install process success!")
                haspip = True
            else:
                print("pip install process failed with error:")
                print(stderr.decode())
        else:
            print("get-pip.py download process failed with error:")
            print(stderr.decode())
    else:
        print("pip could not be run, and auto_install has been disabled!")
    return haspip