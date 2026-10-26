"""Genera el ejecutable de Windows: dist/ComedorBaseNaval.exe

Uso:  python -m pip install pyinstaller
      python construir.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

from comedor import __version__

RAIZ = Path(__file__).resolve().parent
NOMBRE = "ComedorBaseNaval"
BUILD = RAIZ / "build"

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v}, 0), prodvers=({v}, 0)),
  kids=[
    StringFileInfo([StringTable('0C0A04B0', [
      StringStruct('CompanyName', 'Comedor Base Naval'),
      StringStruct('FileDescription', 'Comedor Base Naval - Facturación y costos'),
      StringStruct('FileVersion', '{texto}'),
      StringStruct('InternalName', '{nombre}'),
      StringStruct('OriginalFilename', '{nombre}.exe'),
      StringStruct('ProductName', 'Comedor Base Naval'),
      StringStruct('ProductVersion', '{texto}')])]),
    VarFileInfo([VarStruct('Translation', [3082, 1200])])
  ]
)
"""


def main():
    partes = [int(p) for p in __version__.split(".")] + [0] * 3
    BUILD.mkdir(exist_ok=True)
    archivo_version = BUILD / "version_info.txt"
    archivo_version.write_text(VERSION_INFO.format(v=", ".join(map(str, partes[:3])), texto=__version__,
                                                   nombre=NOMBRE), encoding="utf-8")
    shutil.rmtree(RAIZ / "dist", ignore_errors=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", str(RAIZ / "main.py"),
        "--name", NOMBRE,
        "--onefile", "--windowed", "--noconfirm", "--clean",
        "--icon", str(RAIZ / "recursos" / "comedor.ico"),
        "--add-data", f"{RAIZ / 'recursos'}{';' if sys.platform == 'win32' else ':'}recursos",
        "--version-file", str(archivo_version),
        "--workpath", str(BUILD), "--specpath", str(BUILD),
    ], check=True, cwd=RAIZ)
    print(f"\nListo: {RAIZ / 'dist' / (NOMBRE + '.exe')}  (versión {__version__})")


if __name__ == "__main__":
    main()
