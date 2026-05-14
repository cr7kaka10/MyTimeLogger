# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../assets', 'assets'),
        ('../config', 'config'),
        ('../cloud', 'cloud')
    ],
    hiddenimports=[
        'app.ui.gui',
        'app.ui.activity_panel',
        'app.ui.daily_checklist',
        'app.ui.habit_tracker',
        'app.ui.goals_panel',
        'app.ui.reward_shop',
        'app.ui.sleep_statistics',
        'app.core.logic',
        'app.core.hotkeys',
        'app.core.ticktick_sync',
        'app.models.database',
        'app.models.category_manager',
        'app.utils.utils',
        'app.utils.config'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MyTimeLogger',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/icons/icon.ico',
)