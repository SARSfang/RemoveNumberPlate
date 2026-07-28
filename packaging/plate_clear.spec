# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path(SPEC).resolve().parent.parent

model_files = [
    "manifest.json",
    "ppyoloe_vehicle.onnx",
    "ppocrv3_plate.onnx",
    "inpainting_lama_2025jan.onnx",
]

datas = [
    (str(project_root / "app" / "web"), "app/web"),
    (str(project_root / "README.md"), "."),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "RELEASE.md"), "."),
    (str(project_root / "packaging" / "third_party_licenses"), "third_party_licenses"),
]
datas.extend((str(project_root / "models" / name), "models") for name in model_files)
a = Analysis(
    [str(project_root / "run.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["onnxruntime"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "tkinter",
        "matplotlib",
        "pytest",
        "mypy",
        "ruff",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="消除车牌",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project_root / "packaging" / "app.ico"),
    version=str(project_root / "packaging" / "version_info.txt"),
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="消除车牌",
)
