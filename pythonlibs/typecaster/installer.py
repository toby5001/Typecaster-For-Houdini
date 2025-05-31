"""

Submodule for installing and updating Typecaster

"""
import os, subprocess, sys
from pathlib import Path as PathlibPath

VERBOSE = False

def install():

    # If it doesn't already exist, create the folder which all of the packages will be installed into
    pythonfolder = f"python{str(sys.version_info.major)}.{str(sys.version_info.minor)}libs"
    tcpath = PathlibPath( os.path.expandvars(os.getenv('TYPECASTER')) )
    tc_env_path = tcpath / pythonfolder
    tc_env_path = tc_env_path.resolve()
    tc_env_path.mkdir(exist_ok=True)
    pathstring = str(tc_env_path)

    requirementspath = ( tcpath / "requirements.txt" ).resolve()

    print("Installing packages...")
    command = f"""hython -m pip install --target "{pathstring}" -r {requirementspath}"""
    # subprocess.run(command, shell=True)
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if process.returncode == 0:
        print("Command executed successfully")
        if VERBOSE: print(stdout.decode())
    else:
        print("Command failed with error:")
        print(stderr.decode())

    # Update houdini path in-place
    if pathstring not in sys.path:
        print(f"Adding {pathstring} to path")
        sys.path.insert(0, pathstring)

def update():
    raise NotImplementedError("Yeah I should probably make an updater too...")