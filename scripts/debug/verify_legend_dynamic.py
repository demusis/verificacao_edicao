
import cv2
import numpy as np
from pathlib import Path

def test_legend_dynamic():
    # Simulando imagens de tamanhos diferentes
    for h in [400, 1200]:
        w = int(h * 0.75)
        grad = np.linspace(0, 255, h*w).reshape(h, w).astype(np.uint8)
        heatmap = cv2.applyColorMap(grad, cv2.COLORMAP_JET)
        
        # Lógica duplicada de image_forensics.py para teste
        def _add_colorbar(img, colormap=cv2.COLORMAP_JET, label_min="Baixo", label_max="Alto", val_min=None, val_max=None):
            h, w = img.shape[:2]
            txt_max = str(label_max)
            txt_min = str(label_min)
            if val_max is not None: txt_max += f" ({val_max:.1f})"
            if val_min is not None: txt_min += f" ({val_min:.1f})"
            bar_w = 30
            v_margin = 50
            h_margin = 15
            left_offset = 15
            font = cv2.FONT_HERSHEY_SIMPLEX
            f_scale = max(0.4, min(1.0, h / 900.0))
            thickness = 1 if f_scale < 0.8 else 2
            color = (30, 30, 30)
            size_max, _ = cv2.getTextSize(txt_max, font, f_scale, thickness)
            size_min, _ = cv2.getTextSize(txt_min, font, f_scale, thickness)
            max_text_w = max(size_max[0], size_min[0])
            legend_w = left_offset + bar_w + h_margin + max_text_w + 20
            legend = np.full((h, int(legend_w), 3), 255, dtype=np.uint8)
            bar_h = h - (2 * v_margin)
            if bar_h <= 0: bar_h = h
            bar_pixels = np.linspace(255, 0, bar_h).astype(np.uint8).reshape(-1, 1)
            bar_pixels = np.repeat(bar_pixels, bar_w, axis=1)
            bar_colored = cv2.applyColorMap(bar_pixels, colormap)
            y_start = (h - bar_h) // 2
            legend[y_start:y_start+bar_h, left_offset:left_offset+bar_w] = bar_colored
            cv2.rectangle(legend, (left_offset, y_start), (left_offset+bar_w, y_start+bar_h), (180, 180, 180), 1)
            text_x = left_offset + bar_w + h_margin
            cv2.putText(legend, txt_max, (text_x, y_start + size_max[1] // 2), font, f_scale, color, thickness, cv2.LINE_AA)
            cv2.putText(legend, txt_min, (text_x, y_start + bar_h), font, f_scale, color, thickness, cv2.LINE_AA)
            return np.hstack((img, legend))

        # Testar com valores grandes e pequenos
        result = _add_colorbar(heatmap, cv2.COLORMAP_JET, "Ruido Baixo", "Ruido Alto", 1.23, 150.9)
        filename = f"verify_dynamic_h{h}.jpg"
        cv2.imwrite(filename, result)
        print(f"Gerado: {filename}")

if __name__ == "__main__":
    test_legend_dynamic()
