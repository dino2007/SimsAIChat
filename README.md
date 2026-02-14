## Development & Build Instructions

This project uses a "Triangle Architecture" (Mod Node + App Node).

### Requirements
*   Python 3.11+
*   Flask
*   PyWebview
*   PyInstaller

### How to Build the App (.exe)
1.  Install dependencies: `pip install flask pywebview pyinstaller requests google-generativeai`
2.  Run the build command from the root directory:
    ```bash
    pyinstaller --noconsole --onefile --paths="." --hidden-import=Server --hidden-import=UI --icon="UI/icon.ico" --add-data="Server/templates;templates" --add-data="UI/icon.ico;UI" --name="SimsAIChat" main.py
    ```
