# PyInstaller spec -- run from the apps/client directory:
#   uv run pyinstaller gank_client.spec
# A .spec file (rather than CLI --add-data flags) avoids the Windows (;) vs
# POSIX (:) path-separator mismatch in --add-data across the CI matrix.

a = Analysis(
    ["src/gank_client/main.py"],
    pathex=["src"],
    datas=[("src/gank_client/assets", "gank_client/assets")],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="gank-alert",
    console=False,
    onefile=True,
)
