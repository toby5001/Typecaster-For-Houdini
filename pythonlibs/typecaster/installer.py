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
import hashlib
try:
	from urllib.request import urlopen
	from urllib.request import Request
except ModuleNotFoundError or ImportError:
	from urllib2 import urlopen # type: ignore
	from urllib2.request import Request # type: ignore


# No point in working with the installer if $TYPECASTER doesn't exist.
if not os.getenv('TYPECASTER') or not Path( os.getenv('TYPECASTER') ).exists():
    raise Exception("Could not find the TYPECASTER environment variable or the path it's referencing doesn't exist!")

TYPECASTER_ROOT_PATH = Path( os.getenv('TYPECASTER') ).resolve()
TYPECASTER_URL = 'https://api.github.com/repos/toby5001/Typecaster-For-Houdini'
REQUIREMENTS_PATH = ( TYPECASTER_ROOT_PATH / "requirements.txt" ).resolve()
PYTHON_VERSION = f"{str(sys.version_info.major)}.{str(sys.version_info.minor)}"
PYTHON_INSTALLFOLDERNAME = f"python{PYTHON_VERSION}libs"
TYPECASTER_PYTHON_INSTALL_PATH = (TYPECASTER_ROOT_PATH / PYTHON_INSTALLFOLDERNAME).resolve()
HMAJOR = int(os.getenv("HOUDINI_MAJOR_RELEASE"))
HMINOR = int(os.getenv("HOUDINI_MINOR_RELEASE"))
PLATFORM = get_platform_system().upper()


def __runcmd__(cmd, do_print=True):
    # print(cmd)
    # return False, bytes(), bytes()
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=TYPECASTER_ROOT_PATH)
    stdout, stderr = process.communicate()

    if process.returncode == 0:
        return True, stdout, stderr
    else:
        if do_print:
            print(f'Running command "{cmd}" failed with the following error:')
            print(stderr.decode())
        return False, stdout, stderr


def __get_filehash__(file:Path):
    fhash = None
    if file.exists():
        with file.open('rb') as f:
            hashfunc = hashlib.new('sha256')
            hashfunc.update(f.read())
            fhash = hashfunc.hexdigest()
    return fhash


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
    cmd = f"""hython -m pip install --target "{TYPECASTER_PYTHON_INSTALL_PATH}" -r {REQUIREMENTS_PATH} --upgrade"""
    success, stdout, stderr = __runcmd__(cmd, do_print=False)
    if success:
        print("Dependency install process executed successfully")
    else:
        print("Dependency install process failed with error:")
        print(stderr.decode())

    # Update houdini path in-place
    if success and TYPECASTER_PYTHON_INSTALL_PATH not in sys.path:
        print(f"Adding {TYPECASTER_PYTHON_INSTALL_PATH} to path")
        sys.path.insert(0, str(TYPECASTER_PYTHON_INSTALL_PATH))
    return success


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


def update(mode:str=None, release:str=None, discard_changes=False, branch=None, force_clear=False):
    """Update Typecaster using the github repo

    Args:
        mode (str): How to update Typecaster. Options are "latest_commit", "latest_stable_release", "latest_release", and "release_tag".
        release (str, optional): When mode is set to "release_tag", this should be a string of a specific release (eg: "1.0.0e"). Defaults to None.
        discard_changes (bool, optional): When true, any changes made to the repo will be stashed and then permanently discarded. Defaults to False.
        branch (str, optional): When mode is set to "latest_commit", this will be the branch used. Main is used if not specified. Defaults to None.
        force_clear (bool, optional): Forces the python dependencies to be cleared after a successful update from git, even if it is not needed. Defaults to False.

    Raises:
        Exception: Raised if no releases are able to be found.
    """        
    # print("Updating Typecaster from github...")
    dependency_update = False
    discardcmd = f"git stash && {'git stash drop ; ' if discard_changes else ''}"
    fetchcmd = 'git fetch origin && git fetch --prune origin "+refs/tags/*:refs/tags/*" && '
    reqhash = __get_filehash__(REQUIREMENTS_PATH)

    if mode == 'latest_commit':
        # Pull the latest commit
        print("Updating to the latest commit")
        dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}git checkout {branch if branch else 'main'} && git pull")
        # Ideally I'll figure out a way to reimplement this, but it doesn't properly handle multiple operations being run in the same command
        # if dependency_update:
        #     if stdout.decode().endswith("Already up to date.\n"):
        #         print("Already on the latest commit!")
        #         dependency_update = False

    elif mode == 'latest_stable_release':
        # Checkout the latest normal release
        print("Updating to the latest stable release")
        rels = get_releases()['stable']
        if rels:
            dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}{fetchcmd}git checkout {rels[0]}")
        else:
            raise Exception('<TYPECASTER ERROR> No stable releases found!')

    elif mode == 'latest_release':
        # Checkout the latest release
        print("Updating to the latest release")
        rels = get_releases()['all']
        if rels:
            dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}{fetchcmd}git checkout {rels[0]}")

    elif mode == 'release_tag':
        # Checkout a user-defined release tag
        rels = get_releases()['all']
        if not release:
            raise Exception('<TYPECASTER ERROR> Release not specified!')
        else:
            print(f"Updating to release {release}...")
            if release in rels:
                dependency_update, stdout, stderr = __runcmd__(f"{discardcmd}{fetchcmd}git checkout {release}")
            else:
                raise Exception(f'<TYPECASTER ERROR> Invalid release {release} specified!')

    else:
        raise Exception(f'<TYPECASTER ERROR> Unknown update mode of {mode} specified!')

    newreqhash = __get_filehash__(REQUIREMENTS_PATH)
    updated = dependency_update
    if not force_clear and dependency_update and reqhash and reqhash == newreqhash:
        print(f"{REQUIREMENTS_PATH.name} is unchanged. Preserving dependencies.")
        dependency_update = False
        updated = True

    if dependency_update:
        # Since typecaster might be installed to multiple houdini versions at once,
        # it's simpler (and less error-prone) to just delete the dependencies and 
        # reinstall them during the update
        clear_dependencies()
        install_dependencies()
    
    if updated:
        print("Typecaster Successfully updated!")
    return updated


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

    if not validinstall:
        print("Typecaster could not be initialized properly. Are the dependencies installed?")
        if force_if_not_valid:
            validinstall = install_dependencies()
        elif auto_install and config.get_config().get("auto_install_python_dependencies", 0) == 1:
            print("Auto-install is enabled in the config. Attempting install.")
            validinstall = install_dependencies()
        else:
            print("""Auto-install is disabled. Please either run the installer from the shelf tool, or run typecaster.installer.install_dependencies() from a python shell.""")
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


def get_update_cmd(mode:str=None, release:str=None, discard_changes=False, branch=None, force_clear=False, explicit_path=True):
    code = 'hython "'
    # if use_command_line_tools:
    #     code = 'hython "'
    # else:
    #     pexec = (Path( os.getenv('HFS') )/'bin/hython.exe').resolve()
    #     code = f"""& "{pexec.as_posix()}" """

    if explicit_path:
        code += TYPECASTER_ROOT_PATH.as_posix()
    else:
        if PLATFORM == "WINDOWS":
            code += "%TYPECASTER%"
        else:
            code += "$TYPECASTER"
    code += '/pythonlibs/typecaster/installer.py" cli --o update '
    if mode == "latest_commit":
        code += "--r lc"
    elif mode == "latest_stable_release":
        code += "--r ls"
    elif mode == "latest_release":
        code += "--r lr"
    elif mode == "release_tag":
        code += f"--r {release}"

    if discard_changes:
        code += "--d"

    if branch:
        code += f"--b {branch}"

    if force_clear:
        code += "--c"

    return code


def launch_gui():
    print("Launching standalone GUI for Typecaster. Please wait...")
    cmd = f"hython {__file__} gui"
    if PLATFORM == "WINDOWS":
        cmd = f"start /B {cmd}"
    else:
        cmd = f"nohup {cmd} &"
    subprocess.run(cmd, shell=True)


if __name__ == "__main__":
    import argparse
    
    print("\n<TYPECASTER> Running Typecaster Installer outside of a Houdini session")
    MODEOPTIONS = (('latest_stable_release','ls'), ('latest_commit','lc'), ('latest_release','lr'), ('release_tag','release','r'))
    MODEOPTIONS_FLAT = [item for sublist in MODEOPTIONS for item in sublist]
        
    parser = argparse.ArgumentParser()
    parser.add_argument("standalone_mode", help='How you would like to use the installer. Options are "gui", "cli", and "none" to run without either.')
    parser.add_argument("-o", "--operation", help='The operation you would like to do. Options are "update" (or "u") and "install_dependencies" (or "id")')
    parser.add_argument("-r", "--release", help='What release to use. Options are "ls" for latest stable release, "lr" for latest release, "lc" for latest commit, or a specific release (eg: "1.0.0e").')
    parser.add_argument("-c", "--clear", action='store_true', help='When enabled, clear anything in the pythonX.XXlibs folders.')
    parser.add_argument("-d", "--discard_changes", action='store_true', help='When enabled and the operation is "update", any changes made to the repo will be discarded.')
    parser.add_argument("-b", "--branch", help='A specific branch to use when release is set to "latest commit". Defaults to "main" when not set.')

    args = parser.parse_args()

    standalone_mode = args.standalone_mode.lower()
    if standalone_mode == 'cli':
        print("<TYPECASTER> Using Installer CLI")
        operation = args.operation.lower() if args.operation else None
        op_options = (('u','update'),('id','install_dependencies'))
        op_options_flat = [item for sublist in op_options for item in sublist]
        if not operation:
            print(f"What would you like to do?\nOptions are:\n    {op_options[0]}: Update Typecaster.\n    {op_options[1]}: Install Typecaster's dependencies.")
            while operation not in op_options_flat:
                operation = input("Operation: ")
                if operation not in op_options_flat:
                    print("Please select a valid option!")
        if operation in op_options[0]:
            mode = None
            release = None
            branch = None
            clear = args.clear
            if args.release:
                branch = args.branch
                if args.release in MODEOPTIONS_FLAT:
                    if args.release in MODEOPTIONS[0]:
                        # Update using latest stable version
                        print("Updating to the latest stable release.")
                        mode = 'latest_stable_release'
                    elif args.release in MODEOPTIONS[1]:
                        mode = 'latest_commit'
                    elif args.release in MODEOPTIONS[2]:
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
                print(f'How would you like to update? \nOptions are:\n    {MODEOPTIONS[3]}: Select a specfic release.\n    {MODEOPTIONS[0]}: Use the latest stable release.\n    {MODEOPTIONS[2]}: Use the latest release.\n    {MODEOPTIONS[1]}: Use the latest commit. Most unstable.')
                while selection not in MODEOPTIONS_FLAT:
                    selection = input("Selection: ").lower()
                    if selection not in MODEOPTIONS_FLAT:
                        print("Please select a valid option!")
                if selection in MODEOPTIONS[0]:
                    mode = 'latest_stable_release'
                elif selection in MODEOPTIONS[1]:
                    mode = 'latest_commit'
                elif selection in MODEOPTIONS[2]:
                    mode = 'latest_release'
                elif selection in MODEOPTIONS[3]:
                    rels = get_releases()['all']
                    print("Recent releases:", rels[0:8 if len(rels) >= 8 else len(rels)])
                    selection = ''
                    while release not in rels:
                        release = input("Selection: ")
                        if release not in rels:
                            print("Please select a valid option!")
                    mode = 'release_tag'
            update(mode=mode, release=release, discard_changes=args.discard_changes, branch=branch, force_clear=clear)

        elif operation in op_options[1]:
            if args.clear:
                clear_dependencies()
            install_dependencies()

        else:
            print("<TYPECASTER ERROR> Please specify a valid operation!")
            parser.print_help()

    elif standalone_mode == 'gui':
        print("<TYPECASTER> Using Installer GUI")
        from PySide2 import QtWidgets, QtGui
        from PySide2.QtCore import Qt

        class QuestionWindow(QtWidgets.QMessageBox):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("Typecaster Standalone Installer")
                self.setText("What would you like to do?")
                self.setInformativeText("Please make sure that you don't have any currently running instances of Houdini before proceeding.")
                self.button_update = self.addButton("Update Typecaster", QtWidgets.QMessageBox.ActionRole)
                self.button_installdeps = self.addButton("Reinstall Dependencies", QtWidgets.QMessageBox.ActionRole)
                self.button_close = self.addButton("Close", QtWidgets.QMessageBox.RejectRole)

        class UpdaterWindow(QtWidgets.QMainWindow):
            def __init__(self):
                super().__init__()
                # Main layout
                self.setWindowTitle("Typecaster Standalone Updater")
                self.main_layout = QtWidgets.QVBoxLayout()
                self.general_layout = QtWidgets.QHBoxLayout()
                self.main_layout.addLayout(self.general_layout)
                container = QtWidgets.QWidget()
                container.setLayout(self.main_layout)
                self.setCentralWidget(container)

                # Update button
                self.update_button = QtWidgets.QPushButton(text="Update Typecaster")
                self.main_layout.addWidget(self.update_button)
                self.update_button.clicked.connect(self.do_update)

                # Basic config
                self.configlayout = QtWidgets.QVBoxLayout()
                self.general_layout.addLayout(self.configlayout)
                method_label = QtWidgets.QLabel('Update Method: ')
                self.configlayout.addWidget(method_label)
                self.update_method = QtWidgets.QComboBox()
                for i in [item[0].replace('_', ' ').title() for item in MODEOPTIONS]:
                    self.update_method.addItem(i)
                self.configlayout.addWidget(self.update_method)
                self.update_method.currentIndexChanged.connect(self.callback_update_method)

                # Release selector
                self.release_label = QtWidgets.QLabel('Release: ')
                self.release_tag = QtWidgets.QComboBox()
                self.configlayout.addWidget(self.release_label)
                self.configlayout.addWidget(self.release_tag)
                self._releases_ = []

                # Advanced options layout
                self.advanced_layout = QtWidgets.QFormLayout()
                self.advanced_group = QtWidgets.QGroupBox("Advanced Options")
                self.advanced_group.setCheckable(True)
                self.advanced_group.setChecked(False)
                self.configlayout.addWidget(self.advanced_group)
                self.advanced_group.setLayout(self.advanced_layout)
                self.advanced_layout.setLabelAlignment(Qt.AlignRight)

                self.configlayout.addStretch()

                # Advanced options
                self.clear_dependencies = QtWidgets.QCheckBox('Force Clear Dependencies')
                self.advanced_layout.addRow(self.clear_dependencies)
                self.discard_changes = QtWidgets.QCheckBox('Discard Changes')
                self.advanced_layout.addRow(self.discard_changes)
                self.branch_label = QtWidgets.QLabel('Branch:')
                self.branch_select = QtWidgets.QComboBox()
                for i in ('main', 'dev'):
                    self.branch_select.addItem(i)
                self.advanced_layout.addRow(self.branch_label, self.branch_select)

                # Log
                self.logcontainer = QtWidgets.QWidget()
                loglayout = QtWidgets.QVBoxLayout()
                self.logcontainer.setLayout(loglayout)
                self.general_layout.addWidget(self.logcontainer)
                loglabel = QtWidgets.QLabel("Log")
                loglayout.addWidget(loglabel)
                self.logwindow = QtWidgets.QPlainTextEdit()
                self.logwindow.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
                loglayout.addWidget(self.logwindow)
                self.logwindow.setReadOnly(True)
                fnt = QtGui.QFont("Monospace")
                fnt.setStyleHint(QtGui.QFont.Monospace)
                self.logwindow.setFont(fnt)
                self.logwindow.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                self.setBaseSize(self.sizeHint())
                self.logcontainer.setVisible(False)
                
                self.refresh()

            def addlogitem(self, *args):
                s = ''
                length = len(args)
                for i, arg in enumerate(args):
                    s += str(arg)
                    if length > 1 and i < length-1:
                        s += ' '
                self.logwindow.appendPlainText(s)

            def callback_update_method(self):
                selection = self.update_method.currentIndex()
                specific_release = selection == 3
                if specific_release:
                    if not self._releases_:
                        self._releases_ = get_releases()['all']
                        for release in self._releases_:
                            self.release_tag.addItem(release)
                self.release_label.setVisible(specific_release)
                self.release_tag.setVisible(specific_release)
                if self.advanced_group.isChecked():
                    self.branch_label.setEnabled(selection==1)
                    self.branch_select.setEnabled(selection==1)

            def enable_log(self):
                self.logcontainer.setVisible(True)
                global print
                print = self.addlogitem

            def do_update(self):
                selection = self.update_method.currentIndex()
                self.enable_log()
                self.update_button.setDisabled(True)
                # self.close_button.setVisible(True)
                discard_changes = False
                branch = None
                force_clear = False
                if self.advanced_group.isChecked():
                    discard_changes = self.discard_changes.isChecked()
                    branch = self.branch_select.currentText()
                    force_clear = self.clear_dependencies.isChecked()
                result = update(mode=MODEOPTIONS[selection][0], release=self.release_tag.currentText(), discard_changes=discard_changes, branch=branch, force_clear=force_clear)
                if result:
                    self.addlogitem("Update process completed. Window can be safely closed.")

            def refresh(self):
                self.callback_update_method()

        app = QtWidgets.QApplication(sys.argv)
        # app.setStyle('Windows')
        window = QuestionWindow()
        window.show()
        run = app.exec_()
        btn = window.clickedButton()
        if btn == window.button_update:
            window = UpdaterWindow()
            window.show()
            run = app.exec_()
        elif btn == window.button_installdeps:
            QtWidgets.QMessageBox.warning(
                window,
                "Error!",
                "Installing Typecaster's dependencies from the GUI is not yet supported. Please run operation from the CLI.",
                QtWidgets.QMessageBox.Close,
            )

        sys.exit(run)

    elif standalone_mode == 'none':
        print("Bypassing standalone functionality")

    else:
        raise Exception(f'<TYPECASTER ERROR> Unexpected standalone mode of "{standalone_mode}"!')

else:
    # Override update function when being run from another module, since this is presumbaly now in Houdini
    def update(*args, **kwargs):
        print("installer.update() can't currently be run from a Houdini session. Please run the following from Houdini's Command Line Tools:")
        cmd = get_update_cmd(*args, **kwargs)
        print(cmd)
