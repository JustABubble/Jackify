#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Winetricks Handler Module
Handles wine component installation using bundled winetricks
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class WinetricksHandler:
    """
    Handles wine component installation using bundled winetricks
    """

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.winetricks_path = self._get_bundled_winetricks_path()

    def _get_bundled_winetricks_path(self) -> Optional[str]:
        """
        Get the path to the bundled winetricks script following AppImage best practices
        """
        possible_paths = []

        # AppImage environment - use APPDIR (standard AppImage best practice)
        if os.environ.get('APPDIR'):
            appdir_path = os.path.join(os.environ['APPDIR'], 'opt', 'jackify', 'tools', 'winetricks')
            possible_paths.append(appdir_path)

        # Development environment - relative to module location
        module_dir = Path(__file__).parent.parent.parent  # Go from handlers/ up to jackify/
        dev_path = module_dir / 'tools' / 'winetricks'
        possible_paths.append(str(dev_path))

        # Try each path until we find one that works
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                self.logger.debug(f"Found bundled winetricks at: {path}")
                return str(path)

        self.logger.error(f"Bundled winetricks not found. Tried paths: {possible_paths}")
        return None

    def _get_bundled_cabextract(self) -> Optional[str]:
        """
        Get the path to the bundled cabextract binary, checking same locations as winetricks
        """
        possible_paths = []

        # AppImage environment - same pattern as winetricks detection
        if os.environ.get('APPDIR'):
            appdir_path = os.path.join(os.environ['APPDIR'], 'opt', 'jackify', 'tools', 'cabextract')
            possible_paths.append(appdir_path)

        # Development environment - relative to module location, same as winetricks
        module_dir = Path(__file__).parent.parent.parent  # Go from handlers/ up to jackify/
        dev_path = module_dir / 'tools' / 'cabextract'
        possible_paths.append(str(dev_path))

        # Try each path until we find one that works
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                self.logger.debug(f"Found bundled cabextract at: {path}")
                return str(path)

        # Fallback to system PATH
        try:
            import shutil
            system_cabextract = shutil.which('cabextract')
            if system_cabextract:
                self.logger.debug(f"Using system cabextract: {system_cabextract}")
                return system_cabextract
        except Exception:
            pass

        self.logger.warning("Bundled cabextract not found in tools directory")
        return None

    def is_available(self) -> bool:
        """
        Check if winetricks is available and ready to use
        """
        if not self.winetricks_path:
            self.logger.error("Bundled winetricks not found")
            return False

        try:
            env = os.environ.copy()
            result = subprocess.run(
                [self.winetricks_path, '--version'],
                capture_output=True,
                text=True,
                env=env,
                timeout=10
            )
            if result.returncode == 0:
                self.logger.debug(f"Winetricks version: {result.stdout.strip()}")
                return True
            else:
                self.logger.error(f"Winetricks --version failed: {result.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Error testing winetricks: {e}")
            return False

    def install_wine_components(self, wineprefix: str, game_var: str, specific_components: Optional[List[str]] = None) -> bool:
        """
        Install the specified Wine components into the given prefix using winetricks.
        If specific_components is None, use the default set (fontsmooth=rgb, xact, xact_x64, vcrun2022).
        """
        if not self.is_available():
            self.logger.error("Winetricks is not available")
            return False

        env = os.environ.copy()
        env['WINEDEBUG'] = '-all'  # Suppress Wine debug output
        env['WINEPREFIX'] = wineprefix
        env['WINETRICKS_GUI'] = 'none'  # Suppress GUI popups
        # Less aggressive popup suppression - don't completely disable display
        if 'DISPLAY' in env:
            # Keep DISPLAY but add window manager hints to prevent focus stealing
            env['WINEDLLOVERRIDES'] = 'winemenubuilder.exe=d'  # Disable Wine menu integration
        else:
            # No display available anyway
            env['DISPLAY'] = ''

        # Force winetricks to use Proton wine binary - NEVER fall back to system wine
        try:
            from ..handlers.config_handler import ConfigHandler
            from ..handlers.wine_utils import WineUtils

            config = ConfigHandler()
            user_proton_path = config.get_proton_path()

            # If user selected a specific Proton, try that first
            wine_binary = None
            if user_proton_path != 'auto':
                # Check if user-selected Proton still exists
                if os.path.exists(user_proton_path):
                    # Resolve symlinks to handle ~/.steam/steam -> ~/.local/share/Steam
                    resolved_proton_path = os.path.realpath(user_proton_path)

                    # Check for wine binary in different Proton structures
                    valve_proton_wine = os.path.join(resolved_proton_path, 'dist', 'bin', 'wine')
                    ge_proton_wine = os.path.join(resolved_proton_path, 'files', 'bin', 'wine')

                    if os.path.exists(valve_proton_wine):
                        wine_binary = valve_proton_wine
                        self.logger.info(f"Using user-selected Proton: {user_proton_path}")
                    elif os.path.exists(ge_proton_wine):
                        wine_binary = ge_proton_wine
                        self.logger.info(f"Using user-selected GE-Proton: {user_proton_path}")
                    else:
                        self.logger.warning(f"User-selected Proton path invalid: {user_proton_path}")
                else:
                    self.logger.warning(f"User-selected Proton no longer exists: {user_proton_path}")

            # Fall back to auto-detection if user selection failed or is 'auto'
            if not wine_binary:
                self.logger.info("Falling back to automatic Proton detection")
                best_proton = WineUtils.select_best_proton()
                if best_proton:
                    wine_binary = WineUtils.find_proton_binary(best_proton['name'])
                    self.logger.info(f"Auto-selected Proton: {best_proton['name']} at {best_proton['path']}")

            if not wine_binary:
                self.logger.error("Cannot run winetricks: No compatible Proton version found")
                return False

            if not (os.path.exists(wine_binary) and os.access(wine_binary, os.X_OK)):
                self.logger.error(f"Cannot run winetricks: Wine binary not found or not executable: {wine_binary}")
                return False

            env['WINE'] = str(wine_binary)
            self.logger.info(f"Using Proton wine binary for winetricks: {wine_binary}")

            # CRITICAL: Set up protontricks-compatible environment
            proton_dist_path = os.path.dirname(os.path.dirname(wine_binary))  # e.g., /path/to/proton/dist/bin/wine -> /path/to/proton/dist
            self.logger.debug(f"Proton dist path: {proton_dist_path}")

            # Set WINEDLLPATH like protontricks does
            env['WINEDLLPATH'] = f"{proton_dist_path}/lib64/wine:{proton_dist_path}/lib/wine"

            # Ensure Proton bin directory is first in PATH
            env['PATH'] = f"{proton_dist_path}/bin:{env.get('PATH', '')}"

            # Set DLL overrides exactly like protontricks
            dll_overrides = {
                "beclient": "b,n",
                "beclient_x64": "b,n",
                "dxgi": "n",
                "d3d9": "n",
                "d3d10core": "n",
                "d3d11": "n",
                "d3d12": "n",
                "d3d12core": "n",
                "nvapi": "n",
                "nvapi64": "n",
                "nvofapi64": "n",
                "nvcuda": "b"
            }

            # Merge with existing overrides
            existing_overrides = env.get('WINEDLLOVERRIDES', '')
            if existing_overrides:
                # Parse existing overrides
                for override in existing_overrides.split(';'):
                    if '=' in override:
                        name, value = override.split('=', 1)
                        dll_overrides[name] = value

            env['WINEDLLOVERRIDES'] = ';'.join(f"{name}={setting}" for name, setting in dll_overrides.items())

            # Set Wine defaults from protontricks
            env['WINE_LARGE_ADDRESS_AWARE'] = '1'
            env['DXVK_ENABLE_NVAPI'] = '1'

            self.logger.debug(f"Set protontricks environment: WINEDLLPATH={env['WINEDLLPATH']}")

        except Exception as e:
            self.logger.error(f"Cannot run winetricks: Failed to get Proton wine binary: {e}")
            return False

        # Set up bundled cabextract for winetricks
        bundled_cabextract = self._get_bundled_cabextract()
        if bundled_cabextract:
            env['PATH'] = f"{os.path.dirname(bundled_cabextract)}:{env.get('PATH', '')}"
            self.logger.info(f"Using bundled cabextract: {bundled_cabextract}")
        else:
            self.logger.warning("Bundled cabextract not found, relying on system PATH")

        # Set winetricks cache to jackify_data_dir for self-containment
        from jackify.shared.paths import get_jackify_data_dir
        jackify_cache_dir = get_jackify_data_dir() / 'winetricks_cache'
        jackify_cache_dir.mkdir(parents=True, exist_ok=True)
        env['WINETRICKS_CACHE'] = str(jackify_cache_dir)

        if specific_components is not None:
            all_components = specific_components
            self.logger.info(f"Installing specific components: {all_components}")
        else:
            all_components = ["fontsmooth=rgb", "xact", "xact_x64", "vcrun2022"]
            self.logger.info(f"Installing default components: {all_components}")

        if not all_components:
            self.logger.info("No Wine components to install.")
            return True

        # Reorder components for proper installation sequence
        components_to_install = self._reorder_components_for_installation(all_components)
        self.logger.info(f"WINEPREFIX: {wineprefix}, Game: {game_var}, Ordered Components: {components_to_install}")

        # Check user preference for component installation method
        from ..handlers.config_handler import ConfigHandler
        config_handler = ConfigHandler()
        use_winetricks = config_handler.get('use_winetricks_for_components', True)

        # Choose installation method based on user preference and components
        if use_winetricks and "dotnet40" in components_to_install:
            self.logger.info("Using optimized approach: protontricks for dotnet40 (reliable), winetricks for other components (fast)")
            return self._install_components_hybrid_approach(components_to_install, wineprefix, game_var)
        elif not use_winetricks:
            self.logger.info("Using legacy approach: protontricks for all components")
            return self._install_components_protontricks_only(components_to_install, wineprefix, game_var)

        # For non-dotnet40 installations, install all components together (faster)
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                self.logger.warning(f"Retrying component installation (attempt {attempt}/{max_attempts})...")
                self._cleanup_wine_processes()

            try:
                # Build winetricks command - using --unattended for silent installation
                cmd = [self.winetricks_path, '--unattended'] + components_to_install

                self.logger.debug(f"Running: {' '.join(cmd)}")
                self.logger.debug(f"Environment WINE={env.get('WINE', 'NOT SET')}")
                self.logger.debug(f"Environment DISPLAY={env.get('DISPLAY', 'NOT SET')}")
                self.logger.debug(f"Environment WINEPREFIX={env.get('WINEPREFIX', 'NOT SET')}")
                result = subprocess.run(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=600
                )

                self.logger.debug(f"Winetricks output: {result.stdout}")
                if result.returncode == 0:
                    self.logger.info("Wine Component installation command completed successfully.")
                    # Set Windows 10 mode after component installation (matches legacy script timing)
                    self._set_windows_10_mode(wineprefix, env.get('WINE', ''))
                    return True
                else:
                    # Special handling for dotnet40 verification issue (mimics protontricks behavior)
                    if "dotnet40" in components_to_install and "ngen.exe not found" in result.stderr:
                        self.logger.warning("dotnet40 verification warning (common in Steam Proton prefixes)")
                        self.logger.info("Checking if dotnet40 was actually installed...")

                        # Check if dotnet40 appears in winetricks.log (indicates successful installation)
                        log_path = os.path.join(wineprefix, 'winetricks.log')
                        if os.path.exists(log_path):
                            try:
                                with open(log_path, 'r') as f:
                                    log_content = f.read()
                                if 'dotnet40' in log_content:
                                    self.logger.info("dotnet40 found in winetricks.log - installation succeeded despite verification warning")
                                    return True
                            except Exception as e:
                                self.logger.warning(f"Could not read winetricks.log: {e}")

                    self.logger.error(f"Winetricks command failed (Attempt {attempt}/{max_attempts}). Return Code: {result.returncode}")
                    self.logger.error(f"Stdout: {result.stdout.strip()}")
                    self.logger.error(f"Stderr: {result.stderr.strip()}")

            except Exception as e:
                self.logger.error(f"Error during winetricks run (Attempt {attempt}/{max_attempts}): {e}", exc_info=True)

        self.logger.error(f"Failed to install Wine components after {max_attempts} attempts.")
        return False

    def _reorder_components_for_installation(self, components: list) -> list:
        """
        Reorder components for proper installation sequence.
        Critical: dotnet40 must be installed before dotnet6/dotnet7 to avoid conflicts.
        """
        # Simple reordering: dotnet40 first, then everything else
        reordered = []

        # Add dotnet40 first if it exists
        if "dotnet40" in components:
            reordered.append("dotnet40")

        # Add all other components in original order
        for component in components:
            if component != "dotnet40":
                reordered.append(component)

        if reordered != components:
            self.logger.info(f"Reordered for dotnet40 compatibility: {reordered}")

        return reordered

    def _prepare_prefix_for_dotnet(self, wineprefix: str, wine_binary: str) -> bool:
        """
        Prepare the Wine prefix for .NET installation by mimicking protontricks preprocessing.
        This removes mono components and specific symlinks that interfere with .NET installation.
        """
        try:
            env = os.environ.copy()
            env['WINEDEBUG'] = '-all'
            env['WINEPREFIX'] = wineprefix

            # Step 1: Remove mono components (mimics protontricks behavior)
            self.logger.info("Preparing prefix for .NET installation: removing mono")
            mono_result = subprocess.run([
                self.winetricks_path,
                '-q',
                'remove_mono'
            ], env=env, capture_output=True, text=True, timeout=300)

            if mono_result.returncode != 0:
                self.logger.warning(f"Mono removal warning (non-critical): {mono_result.stderr}")

            # Step 2: Set Windows version to XP (protontricks uses winxp for dotnet40)
            self.logger.info("Setting Windows version to XP for .NET compatibility")
            winxp_result = subprocess.run([
                self.winetricks_path,
                '-q',
                'winxp'
            ], env=env, capture_output=True, text=True, timeout=300)

            if winxp_result.returncode != 0:
                self.logger.warning(f"Windows XP setting warning: {winxp_result.stderr}")

            # Step 3: Remove mscoree.dll symlinks (critical for .NET installation)
            self.logger.info("Removing problematic mscoree.dll symlinks")
            dosdevices_path = os.path.join(wineprefix, 'dosdevices', 'c:')
            mscoree_paths = [
                os.path.join(dosdevices_path, 'windows', 'syswow64', 'mscoree.dll'),
                os.path.join(dosdevices_path, 'windows', 'system32', 'mscoree.dll')
            ]

            for dll_path in mscoree_paths:
                if os.path.exists(dll_path) or os.path.islink(dll_path):
                    try:
                        os.remove(dll_path)
                        self.logger.debug(f"Removed symlink: {dll_path}")
                    except Exception as e:
                        self.logger.warning(f"Could not remove {dll_path}: {e}")

            self.logger.info("Prefix preparation complete for .NET installation")
            return True

        except Exception as e:
            self.logger.error(f"Error preparing prefix for .NET: {e}")
            return False

    def _install_components_separately(self, components: list, wineprefix: str, wine_binary: str, base_env: dict) -> bool:
        """
        Install components separately like protontricks does.
        This is necessary when dotnet40 is present to avoid component conflicts.
        """
        self.logger.info(f"Installing {len(components)} components separately (protontricks style)")

        for i, component in enumerate(components, 1):
            self.logger.info(f"Installing component {i}/{len(components)}: {component}")

            # Prepare environment for this component
            env = base_env.copy()

            # Special preprocessing for dotnet40 only
            if component == "dotnet40":
                self.logger.info("Applying dotnet40 preprocessing")
                if not self._prepare_prefix_for_dotnet(wineprefix, wine_binary):
                    self.logger.error("Failed to prepare prefix for dotnet40")
                    return False
            else:
                # For non-dotnet40 components, install in standard mode (Windows 10 will be set after all components)
                self.logger.debug(f"Installing {component} in standard mode")

            # Install this component
            max_attempts = 3
            component_success = False

            for attempt in range(1, max_attempts + 1):
                if attempt > 1:
                    self.logger.warning(f"Retrying {component} installation (attempt {attempt}/{max_attempts})")
                    self._cleanup_wine_processes()

                try:
                    cmd = [self.winetricks_path, '--unattended', component]
                    env['WINEPREFIX'] = wineprefix
                    env['WINE'] = wine_binary

                    self.logger.debug(f"Running: {' '.join(cmd)}")

                    result = subprocess.run(
                        cmd,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=600
                    )

                    if result.returncode == 0:
                        self.logger.info(f"✓ {component} installed successfully")
                        component_success = True
                        break
                    else:
                        # Special handling for dotnet40 verification issue
                        if component == "dotnet40" and "ngen.exe not found" in result.stderr:
                            self.logger.warning("dotnet40 verification warning (expected in Steam Proton)")

                            # Check winetricks.log for actual success
                            log_path = os.path.join(wineprefix, 'winetricks.log')
                            if os.path.exists(log_path):
                                try:
                                    with open(log_path, 'r') as f:
                                        if 'dotnet40' in f.read():
                                            self.logger.info("✓ dotnet40 confirmed in winetricks.log")
                                            component_success = True
                                            break
                                except Exception as e:
                                    self.logger.warning(f"Could not read winetricks.log: {e}")

                        self.logger.error(f"✗ {component} failed (attempt {attempt}): {result.stderr.strip()}")
                        self.logger.debug(f"Full stdout for {component}: {result.stdout.strip()}")

                except Exception as e:
                    self.logger.error(f"Error installing {component} (attempt {attempt}): {e}")

            if not component_success:
                self.logger.error(f"Failed to install {component} after {max_attempts} attempts")
                return False

        self.logger.info("✓ All components installed successfully using separate sessions")
        # Set Windows 10 mode after all component installation (matches legacy script timing)
        self._set_windows_10_mode(wineprefix, env.get('WINE', ''))
        return True

    def _install_components_hybrid_approach(self, components: list, wineprefix: str, game_var: str) -> bool:
        """
        Hybrid approach: Install dotnet40 with protontricks (known to work),
        then install remaining components with winetricks (faster for other components).

        Args:
            components: List of all components to install
            wineprefix: Wine prefix path
            game_var: Game variable for AppID detection

        Returns:
            bool: True if all installations succeeded, False otherwise
        """
        self.logger.info("Starting hybrid installation approach")

        # Separate dotnet40 (protontricks) from other components (winetricks)
        protontricks_components = [comp for comp in components if comp == "dotnet40"]
        other_components = [comp for comp in components if comp != "dotnet40"]

        self.logger.info(f"Protontricks components: {protontricks_components}")
        self.logger.info(f"Other components: {other_components}")

        # Step 1: Install dotnet40 with protontricks if present
        if protontricks_components:
            self.logger.info(f"Installing {protontricks_components} using protontricks...")
            if not self._install_dotnet40_with_protontricks(wineprefix, game_var):
                self.logger.error(f"Failed to install {protontricks_components} with protontricks")
                return False
            self.logger.info(f"✓ {protontricks_components} installation completed successfully with protontricks")

        # Step 2: Install remaining components with winetricks if any
        if other_components:
            self.logger.info(f"Installing remaining components with winetricks: {other_components}")

            # Use existing winetricks logic for other components
            env = self._prepare_winetricks_environment(wineprefix)
            if not env:
                return False

            return self._install_components_with_winetricks(other_components, wineprefix, env)

        self.logger.info("✓ Hybrid component installation completed successfully")
        # Set Windows 10 mode after all component installation (matches legacy script timing)
        wine_binary = self._get_wine_binary_for_prefix(wineprefix)
        self._set_windows_10_mode(wineprefix, wine_binary)
        return True

    def _install_dotnet40_with_protontricks(self, wineprefix: str, game_var: str) -> bool:
        """
        Install dotnet40 using protontricks (known to work reliably).

        Args:
            wineprefix: Wine prefix path
            game_var: Game variable for AppID detection

        Returns:
            bool: True if installation succeeded, False otherwise
        """
        try:
            # Extract AppID from wineprefix path (e.g., /path/to/compatdata/123456789/pfx -> 123456789)
            appid = None
            if 'compatdata' in wineprefix:
                # Standard Steam compatdata structure
                path_parts = Path(wineprefix).parts
                for i, part in enumerate(path_parts):
                    if part == 'compatdata' and i + 1 < len(path_parts):
                        potential_appid = path_parts[i + 1]
                        if potential_appid.isdigit():
                            appid = potential_appid
                            break

            if not appid:
                self.logger.error(f"Could not extract AppID from wineprefix path: {wineprefix}")
                return False

            self.logger.info(f"Using AppID {appid} for protontricks dotnet40 installation")

            # Import and use protontricks handler
            from .protontricks_handler import ProtontricksHandler

            # Determine if we're on Steam Deck (for protontricks handler)
            steamdeck = os.path.exists('/home/deck')

            protontricks_handler = ProtontricksHandler(steamdeck, logger=self.logger)

            # Detect protontricks availability
            if not protontricks_handler.detect_protontricks():
                self.logger.error("Protontricks not available for dotnet40 installation")
                return False

            # Install dotnet40 using protontricks
            success = protontricks_handler.install_wine_components(appid, game_var, ["dotnet40"])

            if success:
                self.logger.info("✓ dotnet40 installed successfully with protontricks")
                return True
            else:
                self.logger.error("✗ dotnet40 installation failed with protontricks")
                return False

        except Exception as e:
            self.logger.error(f"Error installing dotnet40 with protontricks: {e}", exc_info=True)
            return False

    def _prepare_winetricks_environment(self, wineprefix: str) -> Optional[dict]:
        """
        Prepare the environment for winetricks installation.
        This reuses the existing environment setup logic.

        Args:
            wineprefix: Wine prefix path

        Returns:
            dict: Environment variables for winetricks, or None if failed
        """
        try:
            env = os.environ.copy()
            env['WINEDEBUG'] = '-all'
            env['WINEPREFIX'] = wineprefix
            env['WINETRICKS_GUI'] = 'none'

            # Existing Proton detection logic
            from ..handlers.config_handler import ConfigHandler
            from ..handlers.wine_utils import WineUtils

            config = ConfigHandler()
            user_proton_path = config.get_proton_path()

            wine_binary = None
            if user_proton_path != 'auto':
                if os.path.exists(user_proton_path):
                    resolved_proton_path = os.path.realpath(user_proton_path)
                    valve_proton_wine = os.path.join(resolved_proton_path, 'dist', 'bin', 'wine')
                    ge_proton_wine = os.path.join(resolved_proton_path, 'files', 'bin', 'wine')

                    if os.path.exists(valve_proton_wine):
                        wine_binary = valve_proton_wine
                    elif os.path.exists(ge_proton_wine):
                        wine_binary = ge_proton_wine

            if not wine_binary:
                best_proton = WineUtils.select_best_proton()
                if best_proton:
                    wine_binary = WineUtils.find_proton_binary(best_proton['name'])

            if not wine_binary or not (os.path.exists(wine_binary) and os.access(wine_binary, os.X_OK)):
                self.logger.error(f"Cannot prepare winetricks environment: No compatible Proton found")
                return None

            env['WINE'] = str(wine_binary)

            # Set up protontricks-compatible environment (existing logic)
            proton_dist_path = os.path.dirname(os.path.dirname(wine_binary))
            env['WINEDLLPATH'] = f"{proton_dist_path}/lib64/wine:{proton_dist_path}/lib/wine"
            env['PATH'] = f"{proton_dist_path}/bin:{env.get('PATH', '')}"

            # Existing DLL overrides
            dll_overrides = {
                "beclient": "b,n", "beclient_x64": "b,n", "dxgi": "n", "d3d9": "n",
                "d3d10core": "n", "d3d11": "n", "d3d12": "n", "d3d12core": "n",
                "nvapi": "n", "nvapi64": "n", "nvofapi64": "n", "nvcuda": "b"
            }

            env['WINEDLLOVERRIDES'] = ';'.join(f"{name}={setting}" for name, setting in dll_overrides.items())
            env['WINE_LARGE_ADDRESS_AWARE'] = '1'
            env['DXVK_ENABLE_NVAPI'] = '1'

            # Set up winetricks cache
            from jackify.shared.paths import get_jackify_data_dir
            jackify_cache_dir = get_jackify_data_dir() / 'winetricks_cache'
            jackify_cache_dir.mkdir(parents=True, exist_ok=True)
            env['WINETRICKS_CACHE'] = str(jackify_cache_dir)

            return env

        except Exception as e:
            self.logger.error(f"Failed to prepare winetricks environment: {e}")
            return None

    def _install_components_with_winetricks(self, components: list, wineprefix: str, env: dict) -> bool:
        """
        Install components using winetricks with the prepared environment.

        Args:
            components: List of components to install
            wineprefix: Wine prefix path
            env: Prepared environment variables

        Returns:
            bool: True if installation succeeded, False otherwise
        """
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                self.logger.warning(f"Retrying winetricks installation (attempt {attempt}/{max_attempts})")
                self._cleanup_wine_processes()

            try:
                cmd = [self.winetricks_path, '--unattended'] + components
                self.logger.debug(f"Running winetricks: {' '.join(cmd)}")

                result = subprocess.run(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=600
                )

                if result.returncode == 0:
                    self.logger.info(f"✓ Winetricks components installed successfully: {components}")
                    # Set Windows 10 mode after component installation (matches legacy script timing)
                    wine_binary = env.get('WINE', '')
                    self._set_windows_10_mode(env.get('WINEPREFIX', ''), wine_binary)
                    return True
                else:
                    self.logger.error(f"✗ Winetricks failed (attempt {attempt}): {result.stderr.strip()}")

            except Exception as e:
                self.logger.error(f"Error during winetricks run (attempt {attempt}): {e}")

        self.logger.error(f"Failed to install components with winetricks after {max_attempts} attempts")
        return False

    def _set_windows_10_mode(self, wineprefix: str, wine_binary: str):
        """
        Set Windows 10 mode for the prefix after component installation (matches legacy script timing).
        This should be called AFTER all Wine components are installed, not before.
        """
        try:
            env = os.environ.copy()
            env['WINEPREFIX'] = wineprefix
            env['WINE'] = wine_binary

            self.logger.info("Setting Windows 10 mode after component installation (matching legacy script)")
            result = subprocess.run([
                self.winetricks_path, '-q', 'win10'
            ], env=env, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self.logger.info("✓ Windows 10 mode set successfully")
            else:
                self.logger.warning(f"Could not set Windows 10 mode: {result.stderr}")

        except Exception as e:
            self.logger.warning(f"Error setting Windows 10 mode: {e}")

    def _install_components_protontricks_only(self, components: list, wineprefix: str, game_var: str) -> bool:
        """
        Legacy approach: Install all components using protontricks only.
        This matches the behavior of the original bash script.
        """
        try:
            self.logger.info(f"Installing all components with protontricks (legacy method): {components}")

            # Import protontricks handler
            from ..handlers.protontricks_handler import ProtontricksHandler

            # Determine if we're on Steam Deck (for protontricks handler)
            steamdeck = os.path.exists('/home/deck')
            protontricks_handler = ProtontricksHandler(steamdeck, logger=self.logger)

            # Get AppID from wineprefix
            appid = self._extract_appid_from_wineprefix(wineprefix)
            if not appid:
                self.logger.error("Could not extract AppID from wineprefix for protontricks installation")
                return False

            self.logger.info(f"Using AppID {appid} for protontricks installation")

            # Detect protontricks availability
            if not protontricks_handler.detect_protontricks():
                self.logger.error("Protontricks not available for component installation")
                return False

            # Install all components using protontricks
            success = protontricks_handler.install_wine_components(appid, game_var, components)

            if success:
                self.logger.info("✓ All components installed successfully with protontricks")
                # Set Windows 10 mode after component installation
                wine_binary = self._get_wine_binary_for_prefix(wineprefix)
                self._set_windows_10_mode(wineprefix, wine_binary)
                return True
            else:
                self.logger.error("✗ Component installation failed with protontricks")
                return False

        except Exception as e:
            self.logger.error(f"Error installing components with protontricks: {e}", exc_info=True)
            return False

    def _extract_appid_from_wineprefix(self, wineprefix: str) -> Optional[str]:
        """
        Extract AppID from wineprefix path.

        Args:
            wineprefix: Wine prefix path

        Returns:
            AppID as string, or None if extraction fails
        """
        try:
            if 'compatdata' in wineprefix:
                # Standard Steam compatdata structure
                path_parts = Path(wineprefix).parts
                for i, part in enumerate(path_parts):
                    if part == 'compatdata' and i + 1 < len(path_parts):
                        potential_appid = path_parts[i + 1]
                        if potential_appid.isdigit():
                            return potential_appid
            self.logger.error(f"Could not extract AppID from wineprefix path: {wineprefix}")
            return None
        except Exception as e:
            self.logger.error(f"Error extracting AppID from wineprefix: {e}")
            return None

    def _get_wine_binary_for_prefix(self, wineprefix: str) -> str:
        """
        Get the wine binary path for a given prefix.

        Args:
            wineprefix: Wine prefix path

        Returns:
            Wine binary path as string
        """
        try:
            from ..handlers.config_handler import ConfigHandler
            from ..handlers.wine_utils import WineUtils

            config = ConfigHandler()
            user_proton_path = config.get_proton_path()

            # If user selected a specific Proton, try that first
            wine_binary = None
            if user_proton_path != 'auto':
                if os.path.exists(user_proton_path):
                    resolved_proton_path = os.path.realpath(user_proton_path)
                    valve_proton_wine = os.path.join(resolved_proton_path, 'dist', 'bin', 'wine')
                    ge_proton_wine = os.path.join(resolved_proton_path, 'files', 'bin', 'wine')

                    if os.path.exists(valve_proton_wine):
                        wine_binary = valve_proton_wine
                    elif os.path.exists(ge_proton_wine):
                        wine_binary = ge_proton_wine

            # Fall back to auto-detection if user selection failed or is 'auto'
            if not wine_binary:
                best_proton = WineUtils.select_best_proton()
                if best_proton:
                    wine_binary = WineUtils.find_proton_binary(best_proton['name'])

            return wine_binary if wine_binary else ""
        except Exception as e:
            self.logger.error(f"Error getting wine binary for prefix: {e}")
            return ""

    def _cleanup_wine_processes(self):
        """
        Internal method to clean up wine processes during component installation
        Only cleanup winetricks processes - NEVER kill all wine processes
        """
        try:
            # Only cleanup winetricks processes - do NOT kill other wine apps
            subprocess.run("pkill -f winetricks", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.debug("Cleaned up winetricks processes only")
        except Exception as e:
            self.logger.error(f"Error cleaning up winetricks processes: {e}")