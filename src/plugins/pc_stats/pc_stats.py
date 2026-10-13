import os
import time
import re
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from plugins.base_plugin.base_plugin import BasePlugin

class PCStats(BasePlugin):
    def generate_image(self, settings, device_config):
        # 1. Setup Canvas
        width, height = 250, 122
        image = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        # 2. Strict Boolean Helper
        def is_on(key):
            val = settings.get(key, False)
            if isinstance(val, str):
                return val.lower() == 'true'
            return bool(val)

        # 3. Pull Settings
        title = settings.get('title', 'WINDOWS PC')
        base_size = int(settings.get('font_size_base', 14))
        pc_file = "/home/walju/pc_stats.txt"  # must match DEST_PATH in windows_scripts/pc_sync_hidden.bat

        # 4. Load Fonts
        try:
            f_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(f_path):
                f_path = "/usr/local/inkypi/src/resources/fonts/FreeSansBold.ttf"
            f_sm = ImageFont.truetype(f_path, base_size - 2)
            f_md = ImageFont.truetype(f_path, base_size)
            f_lg = ImageFont.truetype(f_path, 18)
        except:
            f_sm = f_md = f_lg = ImageFont.load_default()

        # 5. Draw Header
        draw.text((40, 5), title.upper(), font=f_lg, fill=(0, 0, 0))
        draw.line((10, 28, width-10, 28), fill=(0, 0, 0), width=2)

        if not os.path.exists(pc_file):
            draw.text((12, 45), "NO DATA RECEIVED", font=f_md, fill=(0, 0, 0))
            return image

        # 6. Parse PC Data
        data = {}
        with open(pc_file, "r") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip().lower()] = v.strip()

        # 7. Statistics Map (Key in file, setting toggle, Display Label)
        stats_map = [
            ('cpu', 'show_cpu', 'CPU'),
            ('gpu', 'show_gpu', 'GPU'),
            ('ram', 'show_ram', 'RAM'),
            ('ssd', 'show_disk', 'SSD'),
            ('localip', 'show_local_ip', 'IP'),
            ('extip', 'show_ext_ip', 'EXT'),
            ('focus', 'show_focus', 'WIN')
        ]

        y = 35
        spacing = base_size + 4
        
        # 8. Draw Each Active Line
        for key, toggle, label in stats_map:
            if is_on(toggle) and key in data:
                draw.text((12, y), f"{label}: {data[key]}", font=f_md, fill=(0, 0, 0))
                
                # Draw Visual Progress Bar for Percentages
                if is_on('show_bars') and '%' in data[key]:
                    try:
                        val_num = int(re.search(r'\d+', data[key]).group())
                        # Draw bar outline
                        bar_x = 110
                        draw.rectangle([bar_x, y+2, bar_x+80, y+(base_size-2)], outline=(0,0,0))
                        # Draw bar fill (scaled to fits)
                        draw.rectangle([bar_x, y+2, bar_x+int(val_num*0.8), y+(base_size-2)], fill=(0,0,0))
                    except: pass
                
                y += spacing

        # 9. Forced Refresh Timestamp
        t_stamp = datetime.now().strftime("%H:%M")
        draw.text((width-40, height-15), t_stamp, font=f_sm, fill=(0, 0, 0))

        # 10. Return Image
        return image
