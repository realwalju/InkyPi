"""Plugin Manager plugin - manages installation and uninstallation of third-party plugins."""

from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
import logging
import os
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


class PluginManager(BasePlugin):
    """Plugin for managing third-party plugins installation/uninstallation."""
    
    @classmethod
    def get_blueprint(cls):
        """Return the Flask blueprint for this plugin's API routes."""
        from . import api
        return api.plugin_manage_bp
    
    @staticmethod
    def _get_plugin_last_commit_date(plugin_id):
        """Get the last commit date for a plugin from its local git repository."""
        try:
            from flask import current_app
            from config import Config
            
            plugins_dir = os.path.join(Config.BASE_DIR, "plugins")
            plugin_dir = os.path.join(plugins_dir, plugin_id)
            git_dir = os.path.join(plugin_dir, ".git")
            
            if not os.path.isdir(git_dir):
                return None
            
            # Get the last commit date
            result = subprocess.run(
                ["git", "-C", plugin_dir, "log", "-1", "--format=%ci", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Return the complete timestamp as-is (format: "2024-01-15 10:30:45 +0100")
                return result.stdout.strip()
            
            return None
        except Exception as e:
            logger.debug(f"Could not get commit date for plugin {plugin_id}: {e}")
            return None
    
    def generate_settings_template(self):
        """Add third-party plugins list to template parameters."""
        template_params = super().generate_settings_template()
        # Access device_config via Flask's current_app
        try:
            from flask import current_app
            
            # Check if core files need patching FIRST
            core_needs_patch = False
            core_patch_missing = []
            try:
                from .patch_core import check_core_patched
                is_patched, missing = check_core_patched()
                core_needs_patch = not is_patched
                core_patch_missing = missing
            except Exception as e:
                logger.warning(f"Could not check patch status: {e}")
            
            template_params['core_needs_patch'] = core_needs_patch
            template_params['core_patch_missing'] = core_patch_missing
            
            # If core is not patched, trigger patch script in the background
            if core_needs_patch:
                patch_script = os.path.join(os.path.dirname(__file__), "patch-core.sh")
                if os.path.isfile(patch_script):
                    try:
                        # Fire-and-forget: do not wait, service will restart during/after this call
                        subprocess.Popen(
                            ["bash", patch_script],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        template_params['auto_patch_started'] = True
                    except Exception as e:  # pragma: no cover - best-effort logging
                        logger.warning(f"Could not start auto core patch: {e}")
                        template_params['auto_patch_started'] = False
                else:
                    logger.warning("patch-core.sh not found for pluginmanager")
                    template_params['auto_patch_started'] = False
                
                # Skip loading plugins when unpatched
                template_params['third_party_plugins'] = []
            else:
                # Core is patched, normal behaviour: load third-party plugins list
                device_config = current_app.config.get('DEVICE_CONFIG')
                if device_config:
                    third_party = [p for p in device_config.get_plugins() if p.get("repository")]
                    # Add version date (last commit date) to each plugin
                    for plugin in third_party:
                        plugin_id = plugin.get("id")
                        if plugin_id:
                            version_date = self._get_plugin_last_commit_date(plugin_id)
                            plugin['version_date'] = version_date or "Unknown"
                    template_params['third_party_plugins'] = third_party
                else:
                    template_params['third_party_plugins'] = []
        except (RuntimeError, ImportError):
            # Not in Flask context or Flask not available
            template_params['third_party_plugins'] = []
            template_params['core_needs_patch'] = False
            template_params['core_patch_missing'] = []
            template_params['auto_patch_started'] = False
        return template_params
    
    def generate_image(self, settings, device_config):
        """Return a placeholder image - this plugin is UI-only."""
        # Create a simple placeholder image
        width, height = device_config.get_resolution()
        img = Image.new('RGB', (width, height), color='white')
        return img
