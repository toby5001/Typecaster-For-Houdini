"""

Submodule for installing and updating Typecaster

"""

from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
from typecaster import config
from platform import system as get_platform_system
import contextlib
import ssl
import json
import re
import shutil
try:
	from urllib.request import urlopen
	from urllib.request import Request
except ModuleNotFoundError or ImportError:
	from urllib2 import urlopen # type: ignore
	from urllib2.request import Request # type: ignore


TYPECASTER_ROOT_PATH = Path( os.getenv('TYPECASTER') ).resolve()
# No point in working with the installer if $TYPECASTER doesn't exist.
if not os.getenv('TYPECASTER') or not TYPECASTER_ROOT_PATH.exists():
    raise Exception("Could not find the TYPECASTER environment variable or the path doesn't exist!")

TYPECASTER_URL = 'https://api.github.com/repos/toby5001/Typecaster-For-Houdini'
REQUIREMENTS_PATH = ( TYPECASTER_ROOT_PATH / "requirements.txt" ).resolve()
PYTHON_VERSION = f"{str(sys.version_info.major)}.{str(sys.version_info.minor)}"
PYTHON_INSTALLFOLDERNAME = f"python{PYTHON_VERSION}libs"
TYPECASTER_PYTHON_INSTALL_PATH = (TYPECASTER_ROOT_PATH / PYTHON_INSTALLFOLDERNAME).resolve()
HMAJOR = int(os.getenv("HOUDINI_MAJOR_RELEASE"))
HMINOR = int(os.getenv("HOUDINI_MINOR_RELEASE"))

PIP_INSTALLCMD = f"""hython -m pip install --target "{TYPECASTER_PYTHON_INSTALL_PATH}" -r {REQUIREMENTS_PATH} --upgrade"""
    

def __runcmd__(cmd, do_print=True):
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=TYPECASTER_ROOT_PATH)
    stdout, stderr = process.communicate()
        
    if process.returncode == 0:
        return True, stdout, stderr
    else:
        if do_print:
            print(f'Running command "{cmd}" failed with the following error:')
            print(stderr.decode())
        return False, stdout, stderr


def install_dependencies():
    """Install Typecaster's dependencies that are not included with the main distribution.

    Args:
        verbose (bool, optional): If enabled, the full stdout of running pip will be printed. Defaults to False.

    Returns:
        bool: Returns True if Typecaster could be installed. Otherwise False.
    """    
    
    if HMAJOR < 19 or ( HMAJOR == 19 and HMINOR < 5 ):
        # If this is true, Houdini is below the version number where pip is included in it's python instalation. Additional checks will be run.
        print( f"pip not installed by default in this version of Houdini ({HMAJOR}.{HMINOR})! Checking for an existing installation.")
        pipstatus = check_install_pip()
        if not pipstatus:
            raise Exception("pip could not be found or installed. Typecaster install process terminated.")
            return False
    
    # If it doesn't already exist, create the folder which all of the packages will be installed into
    TYPECASTER_PYTHON_INSTALL_PATH.mkdir(exist_ok=True)

    print(f"Installing Typecaster dependencies for python {PYTHON_VERSION}...")
    success, stdout, stderr = __runcmd__(PIP_INSTALLCMD, do_print=False)
    if success:
        print("Dependency install process executed successfully")
    else:
        print("Dependency install process failed with error:")
        print(stderr.decode())

    # Update houdini path in-place
    if TYPECASTER_PYTHON_INSTALL_PATH not in sys.path:
        print(f"Adding {TYPECASTER_PYTHON_INSTALL_PATH} to path")
        sys.path.insert(0, str(TYPECASTER_PYTHON_INSTALL_PATH))
    return True


def clear_dependencies():
    """Clear any existing pythonX.XXlibs folders."""
    # This a straightforward way to ensure that the secondary python packages used by
    # Typecaster don't get out of step with the versions expected in the current commit.
    print(f"Removing existing pythonX.XXlibs folders in {TYPECASTER_ROOT_PATH}.")
    for f in TYPECASTER_ROOT_PATH.iterdir():
        if f.is_dir():
            if re.match("python\d\.\d{1,2}libs", f.name):
                print(f"""Removing folder "{f.name}" and it's contents...""")
                try:
                    shutil.rmtree(f)
                    print(f"""Folder "{f.name}" and it's contents removed successfully!""")
                except OSError as e:
                    print(f"Error: {f} : {e.strerror}")


def update(mode:str=None, release:str=None, discard_changes=False):
    """Update Typecaster using the github repo

    Args:
        mode (str): How to update Typecaster. Options are "latest_commit", "latest_stable", "latest_release", and "release_tag".
        release (str, optional): When mode is set to "release_tag", this should be a string of a specific release (eg: "1.0.0e"). Defaults to None.
        discard_changes (bool, optional): When true, any changes made to the repo will be stashed and then permanently discarded.

    Raises:
        Exception: Raised if no releases are able to be found.
    """        
    # print("Updating Typecaster from github...")
    dependency_update = False
    discardcmd = f"git stash && {'git stash drop && ' if discard_changes else ''}"
    fetchcmd = 'git fetch origin && git fetch --prune origin "+refs/tags/*:refs/tags/*" && '
    
    if mode == 'latest_commit':
        # Pull the latest commit
        print("Pulling from latest commit...")
        dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}git checkout main && git pull")
        if dependency_update:
            if stdout.decode().endswith("Already up to date.\n"):
                print("Already on the latest commit!")
                dependency_update = False
    
    elif mode == 'latest_stable':
        # Checkout the latest normal release
        rels = get_releases()['stable']
        if rels:
            dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}{fetchcmd}git checkout {rels[0]}")
        else:
            raise Exception('<TYPECASTER ERROR> No stable releases found!')

    elif mode == 'latest_release':
        # Checkout the latest release
        rels = get_releases()['all']
        if rels:
            dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}{fetchcmd}git checkout {rels[0]}")
    
    elif mode == 'release_tag':
        # Checkout a user-defined release tag
        rels = get_releases()['all']
        if not release:
            raise Exception('<TYPECASTER ERROR> Release not specified!')
        else:
            if release in rels:
                dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}{fetchcmd}git checkout {release}")
            else:
                raise Exception(f'<TYPECASTER ERROR> Invalid release {release} specified!')

    if dependency_update:
        # Since typecaster might be installed to multiple houdini versions at once,
        # it's simpler (and less error-prone) to just delete the dependencies and 
        # reinstall them during the update
        clear_dependencies()
        install_dependencies()


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
        from typecaster.font import Font # noqa: F401
        del Font
        from typecaster.fontFinder import FONTFILES # noqa: F401
        del FONTFILES
        from typecaster.bidi_segmentation import line_to_run_segments # noqa: F401
        del line_to_run_segments
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
    print("Attempting to run pip...")
    success, stdout, stderr = __runcmd__("hython -m pip", do_print=False)

    haspip = False
    if success:
        print("pip appears to be installed!")
        haspip = True
    elif auto_install:
        print("pip could not be run. Attempting install...")

        pipgetpath = (Path(os.getenv("HOUDINI_TEMP_DIR"))/"get-pip.py").resolve()
        pipgetpath.parent.mkdir(exist_ok=True)
        if sys.version_info.major < 3 or (sys.version_info.major == 3 and sys.version_info.minor < 9):
            # Main script only supports python 3.9 or higher, so get a version specific one.
            url = f"https://bootstrap.pypa.io/pip/{PYTHON_VERSION}/get-pip.py"
        else:
            url = "https://bootstrap.pypa.io/pip/get-pip.py"
        
        # Download pip installer
        success, stdout, stderr = __runcmd__(f"curl {url} -o {str(pipgetpath)}",do_print=False)
        if success:
            print("get-pip.py successfully downloaded.")
            print("Running get-pip.py...")
            # Run pip installer
            success, stdout, stderr = __runcmd__(f"hython {pipgetpath}",do_print=False)
            if success:
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


def get_releases(ignore_error=False):
    """get a list of all releases on github.
    
    Returns:
        dict[str,list]: a list of releases (version numbers)
    """
    releases = {'stable':[],'experimental':[],'all':[]}
    found = False
    with contextlib.closing(urlopen(Request(TYPECASTER_URL + "/releases"), context=ssl._create_unverified_context())) as response:
        data = response.read()
        if data == "":
            raise ValueError("No response from release server: {}".format(TYPECASTER_URL + "/releases"))
        j_data = json.loads(data.decode('utf-8'))
        try:
            for release in j_data:
                tag_name:str = release["tag_name"]
                if tag_name.endswith('e'):
                    releases['experimental'].append(tag_name)
                else:
                    releases["stable"].append(tag_name)
                releases['all'].append(tag_name)
                found = True
        except TypeError:
            raise ValueError("Rate limit reached. Please try again later.")
    if found or ignore_error:
        return releases
    else:
        raise Exception(f'<TYPECASTER ERROR> No releases found for {TYPECASTER_URL}!')


def get_update_cmd(mode: str = "", release: str = "", discard_changes: bool = False, explicit_path=True):
    code = 'hython "'
    # if use_command_line_tools:
    #     code = 'hython "'
    # else:
    #     pexec = (Path( os.getenv('HFS') )/'bin/hython.exe').resolve()
    #     code = f"""& "{pexec.as_posix()}" """

    if explicit_path:
        code += TYPECASTER_ROOT_PATH.as_posix()
    else:
        if get_platform_system().upper() == "WINDOWS":
            code += "%TYPECASTER%"
        else:
            code += "$TYPECASTER"
    code += '/pythonlibs/typecaster/installer.py" update '
    if mode == "latest_commit":
        code += "-r lc"
    elif mode == "latest_stable":
        code += "-r ls"
    elif mode == "latest_release":
        code += "-r lr"
    elif mode == "release_tag":
        code += f"-r {release}"
    
    if discard_changes:
        code += "-d"

    return code


if __name__ == "__main__":
    import argparse
    
    print("\nRunning Typecaster Installer as standalone!")
    options = (('latest_commit','lc'), ('latest_stable','ls','l'), ('latest_release','lr'), ('release','r'))
    options_flat = [item for sublist in options for item in sublist]
    
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", help='The operation you would like to do. Options are "update" (or "u"), "install_dependencies" or ("id"), and "nocli" to bypass the CLI tool completely.')
    parser.add_argument("-r", "--release", help='What release to use. Options are "ls" for latest stable release, "lr" for latest release, "lc" for latest commit, or a specific release (eg: "1.0.0e").')
    parser.add_argument("-c", "--clear", action='store_true', help='When enabled and the operation is "install_dependencies", clear anything in the pythonX.XXlibs folders.')
    parser.add_argument("-d", "--discard_changes", action='store_true', help='When enabled and the operation is "update", any changes made to the repo will be discarded. This flag is likely required if any changes have been made to tracked files')

    args = parser.parse_args()

    operation = args.operation.lower()
    if operation == 'u' or operation == 'update':
        mode = None
        release = None
        if args.release:
            if args.release in options_flat:
                if args.release in options[0]:
                    mode = 'latest_commit'
                elif args.release in options[1]:
                    # Update using latest stable version
                    print("Updating to the latest stable release.")
                    mode = 'latest_stable'
                elif args.release in options[2]:
                    print("Updating to the latest release.")
                    mode = 'latest_release'
            else:
                # Check if the string is an existing release and update using it if so.
                print("Release specified. Likely a specific version.")
                rels = get_releases()['all']
                if args.release in rels:
                    mode = 'release_tag'
                    release = args.release
                else:
                    raise Exception("<TYPECASTER ERROR> The release you specified doesn't exist!")
        else:
            selection = ''
            print('How would you like to update? \nOptions are:\n    "release": Select a specfic release.\n    "latest_stable": Use the latest stable release.\n    "latest_release": Use the latest release.\n    "latest_commit": Use the latest commit. Most unstable.')
            while selection not in options_flat:
                selection = input("Selection: ").lower()
                if selection not in options:
                    print("Please select a valid option!")
            if selection in options[0]:
                mode = 'latest_commit'
            elif selection in options[1] or selection in options[2]:
                mode = 'latest_stable'
            elif selection in options[2]:
                mode = 'latest_release'
            elif selection in options[3]:
                rels = get_releases()['all']
                print("Recent releases:", rels[0:8 if len(rels) >= 8 else len(rels)])
                selection = ''
                while release not in rels:
                    release = input("Selection: ")
                    if release not in rels:
                        print("Please select a valid option!")
                mode = 'release_tag'
        update(mode=mode, release=release, discard_changes=args.discard_changes)
                
    elif operation == 'id' or operation == 'install_dependencies':
        if args.clear:
            clear_dependencies()
        install_dependencies()
    elif operation == 'nocli':
        print("Bypassing CLI")
        pass
    else:
        raise Exception(f'<TYPECASTER ERROR> Unexpected operation of "{operation}"!')
else:
    # Override update function when being run from another module, since this is presumbaly now in Houdini
    def update(*args, **kwargs):
        print("installer.release() can't currently be run from a Houdini session. Please run the following from Houdini's Command Line Tools:")
        cmd = get_update_cmd(*args, **kwargs)
        print(cmd)
