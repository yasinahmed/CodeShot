# CodeShot

CodeShot is a Sublime Text plugin for creating clean CodeSnap-style screenshots of selected code.

**Developer:** Yasin Jagral

## Features

- Copy selected code as an image to clipboard
- Save code screenshot to Desktop
- Clean rounded card-style screenshot layout
- Programming language shown in the screenshot header
- Default footer branding: `CodeShot by Yasin Jagral` (configurable via `footer_text`)
- Theme switching from the Tools menu
- Long-line wrapping for large lines of code
- Auto-dedent selected code so it starts from the first column
- Works offline
- Designed for Windows

## Requirements

CodeShot currently supports **Windows only**.

Required:

- Sublime Text
- Google Chrome or Microsoft Edge installed locally
- Windows PowerShell

CodeShot uses local Chrome or Microsoft Edge in headless mode to render the screenshot. It does not use any online API.

## Installation via Package Control

After CodeShot is accepted into Package Control:

1. Open Sublime Text.
2. Open the Command Palette:

```txt
Ctrl + Shift + P
```

3. Run:

```txt
Package Control: Install Package
```

4. Search for:

```txt
CodeShot
```

5. Install it.

## Manual Installation

1. Download or clone this repository.
2. Open Sublime Text.
3. Go to:

```txt
Preferences > Browse Packages
```

4. Copy the `CodeShot` package files into the Packages folder.

For manual folder installation, the structure should be:

```txt
Packages
  CodeShot
    .python_version
    CodeShot.py
    CodeShot.sublime-settings
    Default.sublime-commands
    Main.sublime-menu
    README.md
    LICENSE
```

Note: CodeShot does not include a default keymap file because Package Control packages should avoid forcing keyboard shortcuts.

5. Restart Sublime Text.

## Usage

Select code in Sublime Text, then use:

```txt
Tools > CodeShot > Copy Image to Clipboard
```

or:

```txt
Tools > CodeShot > Save Image to Desktop
```

or:

```txt
Tools > CodeShot > Open Preview Only
```

## Optional Key Binding

CodeShot does not force a default keyboard shortcut in the Package Control-ready version. This avoids overriding user shortcuts.

To add your own shortcut, open:

```txt
Preferences > Key Bindings
```

Add this to your user key bindings:

```json
{
    "keys": ["ctrl+alt+s"],
    "command": "code_shot",
    "args": {
        "mode": "copy"
    }
}
```

## Settings

Edit:

```txt
CodeShot.sublime-settings
```

Important settings:

```json
{
    "theme": "vscode-dark",
    "page_background": "#ffffff",
    "wrap_long_lines": true,
    "dedent_selection": true,
    "chrome_path": ""
}
```

If Chrome or Edge is not detected automatically, set the path manually.

Chrome example:

```json
"chrome_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
```

Microsoft Edge example:

```json
"chrome_path": "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
```

## Themes

CodeShot includes these themes:

- VS Code Dark
- Dracula
- GitHub Light
- Midnight

Change the theme from:

```txt
Tools > CodeShot > Themes
```

The selected theme is shown with a checkmark.

## Offline Support

CodeShot works offline. It creates a local HTML file, renders it locally using Chrome or Edge in headless mode, then copies or saves the generated PNG.

No internet connection is required.

## Compatibility

CodeShot currently supports Windows only.

Mac and Linux are not currently supported because clipboard handling and browser paths are OS-specific.

## Notes for Package Control Submission

This repository is prepared for Package Control submission:

- Package files are at repository root
- MIT License included
- `messages.json` included
- No `__pycache__` or `.pyc` files
- No forced default keybinding
- `.python_version` included to opt into the Python 3.8 plugin host
- Windows-only support is declared honestly

## License

MIT License. See `LICENSE`.
