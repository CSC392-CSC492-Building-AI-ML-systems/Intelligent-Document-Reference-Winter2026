import os
import shutil

import PyInstaller.__main__


def build_executable():
    # Define paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(base_dir, "src")
    main_script = os.path.join(src_dir, "main.py")

    # Clean previous builds
    shutil.rmtree(os.path.join(base_dir, "build"), ignore_errors=True)
    shutil.rmtree(os.path.join(base_dir, "dist"), ignore_errors=True)

    print(f"Building executable from {main_script}...")

    PyInstaller.__main__.run(
        [
            main_script,
            "--name=IntelligentDocRef_Service",
            "--onefile",
            "--clean",
            f"--paths={src_dir}",
            # '--noconsole', # Uncomment for background silent service
        ]
    )

    print("Build complete. Check 'dist' folder.")


if __name__ == "__main__":
    build_executable()
