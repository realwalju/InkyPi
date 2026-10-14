# Bundled third-party plugins

These community plugins are copied into `src/plugins/` so they ship with this fork instead of being installed one by one on the Pi. All credit goes to their authors. Check the upstream repos for updates.

| Plugin | Folder | Author | Source (commit) | License |
|:-|:-|:-|:-|:-|
| Plugin Manager | `pluginmanager` | [RobinWts](https://github.com/RobinWts) | [InkyPi-Plugin-PluginManager](https://github.com/RobinWts/InkyPi-Plugin-PluginManager) (`4e98349`) | GPL-3.0 (stated in its README) |
| Hardware Buttons | `hardwarebuttons` | [RobinWts](https://github.com/RobinWts) | [InkyPi-Plugin-hardwarebuttons](https://github.com/RobinWts/InkyPi-Plugin-hardwarebuttons) (`e208ed6`) | None specified |
| Duo Weather | `duo_weather` | [saulob](https://github.com/saulob) | [InkyPi-Duo-Weather](https://github.com/saulob/InkyPi-Duo-Weather) (`6a3d9c1`) | MIT |
| Mini Weather | `mini_weather` | [saulob](https://github.com/saulob) | [InkyPi-Mini-Weather](https://github.com/saulob/InkyPi-Mini-Weather) (`5cc829e`) | MIT |
| Literature Clock | `literature_clock` | [harshithdepa](https://github.com/harshithdepa) | [InkyPi-literature-clock](https://github.com/harshithdepa/InkyPi-literature-clock) (`113f2d3`) | MIT |
| Windows PC Stats | `pc_stats` | [sndjy1986](https://github.com/sndjy1986) | [InkyPi-PC_Stats](https://github.com/sndjy1986/InkyPi-PC_Stats) (`02dfb3e`) | None specified |

## Changes from upstream

- **Core patch pre-applied.** Plugin Manager and Hardware Buttons both patch `src/inkypi.py` and `src/plugins/plugin_registry.py` at runtime to register their Flask routes. That patch (`register_plugin_blueprints`) is committed here so the Pi's checkout stays clean and `git pull` keeps working.
- **`gpiozero` added to `install/requirements.txt`** for Hardware Buttons, since InkyPi runs in its own venv. Run `sudo bash install/update.sh` to install it.
- **PC Stats layout rewritten** to fill the display at its configured resolution and orientation instead of a fixed 250×122 canvas. It uses InkyPi's bundled Jost font, shrinks text to fit the width, draws bars only where they fit, and shows when the data was last received (flagged `STALE` after 10 minutes).
- **PC Stats file path** changed from the original author's home folder to `/home/walju/pc_stats.txt`.
- **PC Stats sync script rewritten in PowerShell.** `windows_scripts/pc_sync.ps1` replaces `pc_sync_hidden.bat`, which used `wmic` (removed from recent Windows 11 builds). It sends to `walju@walju.local` by default, reports RAM as percent used (so it gets a progress bar), reads the actually focused window, falls back to the Windows GPU counter on non-NVIDIA cards, and leaves out any stat it can't read. `start_sync.vbs` launches it hidden from its own folder. Test with `pc_sync.ps1 -DryRun` (print only) or `-Once` (single upload).
- Filled in or corrected the `repository` field in `plugin-info.json` for Duo Weather, PC Stats and Literature Clock.

## Known issues

- Hardware Buttons and PC Stats have no license in their upstream repos.
