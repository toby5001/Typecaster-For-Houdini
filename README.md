# Typecaster-For-Houdini
A complete toolkit for working with fonts in Houdini

## Installation
Typecaster is structured as a standard Houdini package, and can be installed as such. Here's a brief outline of the method:
1. Get Typecaster for Houdini from the github repo. This can be done through one of two ways:
    - **Option 1** *(reccomended)* - Cloning the repo: Run the following from the directory you would like to install Typecaster to.
        ```
        git clone https://github.com/toby5001/Typecaster-For-Houdini
        ```
    - **Option 2** - Downloading the repo as a zip file: Click the green code button near the top of the repo's main page and select "Download as ZIP".
2. Once you have Typecaster downloaded, locate the Typecaster.json file within and move it to to one of the package search locations for Houdini. This is often something like ``C:\Users\<USERNAME>\Documents\houdini20.5\packages``
3. Open Typecaster.json and make sure that the TYPECASTER variable (the first one) is set to the location of Typecaster on your computer.
4. Launch Houdini and place a Typecaster Font node. Depending on the setting of ``auto_install_python_dependencies`` in the config file, you will either be reccomended to press the install button in Typecaster's shelf tools, or everything will be handled automatically.
5. Typecaster and it's dependencies should now be installed!