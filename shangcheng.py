"""商城任务入口：依次执行商城相关子流程。

入口 `main()`，被 GUI「商城」任务分发；友谊商城的购买逻辑在
`youyishangcheng`，本模块只负责入口与返回。依赖 `common`。
"""

import os
import time

import youyishangcheng
from common import get_templates_dir, wait_and_click

# 模板路径
templates_dir = get_templates_dir()

def main():
    print("开始执行商城任务...")
    
    # 1. 识别并点击shenmiwu
    shenmiwu_path = os.path.join(templates_dir, "shenmiwu.png")
    if not wait_and_click(shenmiwu_path, "shenmiwu"):
        print("未找到shenmiwu，任务终止")
        return False
    time.sleep(2)
    
    # 2. 识别并点击shangdian
    shangdian_path = os.path.join(templates_dir, "shangdian.png")
    if not wait_and_click(shangdian_path, "shangdian"):
        print("未找到shangdian，任务终止")
        return False
    time.sleep(2)
    
    # 3. 调用youyishangcheng
    print("开始调用youyishangcheng...")
    youyishangcheng.main()
    
    # 4. 点击exitck退出
    exitck_path = os.path.join(templates_dir, "exitck.png")
    if not wait_and_click(exitck_path, "exitck"):
        print("未找到exitck，退出失败")
    else:
        print("点击exitck退出成功")
    
    print("商城任务执行完成！")
    return True

if __name__ == "__main__":
    main()
