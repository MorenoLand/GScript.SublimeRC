Remote Control for GServers in Sublime Text, with player management, chat, file browsing, script editing, PMs, IRC tabs, bans, and server configuration workflows.

## GRClib requirement

This branch uses GRClib for the native protocol layer. Download the latest release for your operating system from:

https://github.com/MorenoLand/GScript.GRClib/releases

Place the native library in the same folder as `_sublime_grc.py`:

- Windows: `grclib.dll`
- Linux: `grclib.so`
- macOS: `grclib.dylib`

SublimeRC selects the correct library automatically based on the OS.

## Install

Copy the package files into your Sublime Text `Packages/SublimeRC` folder, then add the GRClib library for your OS next to `_sublime_grc.py`.

Legal Stoof: this is a fan project, so poke denveous@moreno.land if something needs handled.
