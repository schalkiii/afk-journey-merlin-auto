import cv2
import numpy as np
import pyautogui
import time
import os
import sys

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "debug")
THRESHOLD = 0.8

COLORS = [
    (0, 0, 255), (0, 255, 0), (255, 0, 0), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (128, 0, 128), (128, 128, 0),
]


def screenshot_bgr():
    shot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)


def load_templates(hero_names):
    templates = {}
    for name in hero_names:
        for ext in (".png", ".jpg", ".jpeg"):
            path = os.path.join(TEMPLATE_DIR, name + ext)
            if os.path.exists(path):
                tpl = cv2.imread(path, cv2.IMREAD_COLOR)
                if tpl is not None:
                    templates[name] = (tpl, path)
                    break
        if name not in templates:
            print(f"[警告] 模板不存在: {name}")
    return templates


def match_all_templates(img, templates, threshold=THRESHOLD):
    matches = []
    for name, (tpl, _) in templates.items():
        th, tw = tpl.shape[:2]
        ih, iw = img.shape[:2]
        if ih < th or iw < tw:
            print(f"[跳过] {name}: 截图小于模板")
            continue

        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        print(f"{name} 匹配得分: {max_val:.3f}")

        if max_val >= threshold:
            x, y = max_loc
            matches.append((name, x, y, tw, th, max_val))
    return matches


def draw_matches(img, matches):
    out = img.copy()
    for i, (name, x, y, w, h, score) in enumerate(matches):
        color = COLORS[i % len(COLORS)]
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        label = f"{name} ({score:.2f})"
        label_y = y - 6 if y - 6 > 15 else y + h + 16
        cv2.putText(out, label, (x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return out


def main():
    if len(sys.argv) < 2:
        heroes = ["luolan", "wangzi"]
    else:
        heroes = sys.argv[1:]

    print(f"将在 3 秒后截屏并识别: {heroes}")
    print("请切换到目标界面...")
    time.sleep(3)

    img = screenshot_bgr()
    print(f"截图尺寸: {img.shape[1]}x{img.shape[0]}")

    templates = load_templates(heroes)
    if not templates:
        print("没有可用的模板，退出。")
        return

    matches = match_all_templates(img, templates)
    print(f"\n找到 {len(matches)} 个匹配:")

    for name, x, y, w, h, score in matches:
        print(f"  {name}: 位置({x},{y}) 大小({w}x{h}) 得分={score:.3f}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    result = draw_matches(img, matches)
    out_path = os.path.join(OUTPUT_DIR, f"match_{'_'.join(heroes)}_{int(time.time())}.png")
    cv2.imwrite(out_path, result)
    print(f"\n标注结果已保存: {out_path}")

    for name in heroes:
        matched = any(m[0] == name for m in matches)
        if matched:
            print(f"  {name} ✓ 识别成功")
        elif name in templates:
            print(f"  {name} ✗ 未识别到（可尝试降低阈值或更换截图场景）")


if __name__ == "__main__":
    main()
