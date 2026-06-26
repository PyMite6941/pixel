import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill


class Screenshot(BaseSkill):
    @property
    def name(self) -> str:
        return "screenshot"

    @property
    def description(self) -> str:
        return "Capture the screen or a specific window to a file"

    @property
    def auto_triggers(self) -> list[str]:
        return ["screenshot", "capture screen", "take screenshot", "screen capture", "print screen"]

    def execute(self, action: str = "full", window: str | None = None, output: str | None = None, **kwargs: Any) -> str:
        if action == "full":
            return self._capture_full(output)
        elif action == "window":
            return self._capture_window(window, output)
        return f"Unknown action: {action}. Use: full, window"

    def _capture_full(self, output: str | None = None) -> str:
        if output is None:
            output = Path(tempfile.gettempdir()) / f"pixel_screenshot_{int(time.time())}.png"
            output = output.resolve()
        else:
            output = Path(output).resolve()
        try:
            ps_script = (
                'Add-Type -AssemblyName System.Drawing\n'
                'Add-Type -AssemblyName System.Windows.Forms\n'
                '$bmp = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height)\n'
                '$g = [System.Drawing.Graphics]::FromImage($bmp)\n'
                '$g.CopyFromScreen([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.X, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Y, 0, 0, $bmp.Size)\n'
                "$bmp.Save('" + str(output) + "', [System.Drawing.Imaging.ImageFormat]::Png)\n"
                '$g.Dispose()\n'
                '$bmp.Dispose()\n'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-"],
                input=ps_script, capture_output=True, text=True, timeout=15,
            )
            if output.exists() and output.stat().st_size > 0:
                size = output.stat().st_size
                return f"Screenshot saved: {output} ({size // 1024} KB)"
            err = result.stderr.strip() or result.stdout.strip() or "unknown error"
            return f"Screenshot failed: {err}"
        except subprocess.TimeoutExpired:
            return "Screenshot timed out after 15 seconds"
        except Exception as e:
            return f"Screenshot failed: {e}"

    def _capture_window(self, window: str | None = None, output: str | None = None) -> str:
        return "Window capture not implemented yet. Use action=full for full screen."
