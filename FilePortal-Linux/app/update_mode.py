# -*- coding: utf-8 -*-
# 模块说明：维护模式命令行入口（源码版调用 server.update_mode）
"""更新模式命令行入口（给 update_mode.bat / console.py 调用）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.update_mode import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
