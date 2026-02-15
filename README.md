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
## ⚠️ License & Usage
**SimsAIChat is 100% Free.**
If you downloaded this from anywhere other than Nexus Mods, Itch.io, Mod The Sims or this GitHub, **you may have been scammed.**

*   **Author:** dino2007
*   **License:** "Personal Use Only - No Redistribution"
*   **Commercial Use:** Strictly Prohibited.
