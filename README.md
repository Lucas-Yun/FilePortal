# FilePortal

**把电脑上的一个文件夹，变成一个可以分享的网页文件库。**
纯 Python 标准库 · 单文件启动 · 免数据库 / 免 Docker / 免 Node.js

[![Release](https://img.shields.io/github/v/release/Lucas-Yun/FilePortal?display_name=tag)](https://github.com/Lucas-Yun/FilePortal/releases/latest)
[![Build](https://github.com/Lucas-Yun/FilePortal/actions/workflows/build-release.yml/badge.svg)](https://github.com/Lucas-Yun/FilePortal/actions/workflows/build-release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11%20%7C%20Linux-555.svg)]()
[![Security Policy](https://img.shields.io/badge/security-policy-0f6fbd.svg)](SECURITY.md)
[![Contributions](https://img.shields.io/badge/contributions-welcome-2ea44f.svg)](CONTRIBUTING.md)

> **下载即用**
> - Windows 10 / 11（x64）单文件版：[FilePortal-Windows-x64.exe](https://github.com/Lucas-Yun/FilePortal/releases/latest/download/FilePortal-Windows-x64.exe)
> - Linux（x86_64）源码启动包：[FilePortal-Linux.zip](https://github.com/Lucas-Yun/FilePortal/releases/latest/download/FilePortal-Linux.zip)
> - 全部版本与 SHA256 校验值：[Releases](https://github.com/Lucas-Yun/FilePortal/releases/latest)
>
> 默认登录：`Admin` / `ChangeMe_Admin` —— **首次登录请立刻修改密码**。

---

## 目录

- [这是什么](#这是什么)
- [30 秒上手](#30-秒上手)
- [为什么选它](#为什么选它)
- [和常见做法的区别](#和常见做法的区别)
- [三种版本](#三种版本)
- [功能一览](#功能一览)
- [快速开始](#快速开始)
- [初始设置](#初始设置)
- [中英文切换](#中英文切换)
- [后台管理](#后台管理)
- [配置说明](#配置说明)
- [安全建议](#安全建议)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [开发与构建](#开发与构建)
- [参与贡献](#参与贡献)
- [安全政策](#安全政策)
- [行为准则](#行为准则)
- [支持与帮助](#支持与帮助)
- [变更日志](#变更日志)
- [License](#license)

---

## 这是什么

FilePortal 把本机或服务器上的**一个目录**映射成网页文件库。别人用浏览器打开你给的地址，用「姓名 + 密码」登录，就能按你分配的权限浏览、上传、下载、预览和打包——不需要装客户端，也不需要你搭一套网盘。

**它适合：**

| 场景 | 用法 |
| --- | --- |
| 教室 / 实验室资料分发 | 老师上传，学生按规则只读或只下载指定子目录 |
| 家庭资料库 | 老电脑、老设备、安卓 WebView 也能顺利下载，中文文件名不乱码 |
| 内网轻量网盘 | 不装 Docker、不建数据库，一个 EXE 或一条命令跑起来 |
| 临时对外分享 | 配合 HTTPS 或内网穿透，按人发权限，用完直接关掉 |

**它不适合：** 企业级对象存储、多租户大规模云盘、NAS / 备份系统的替代品。需要集群、S3 兼容接口、高并发时请选专业方案。

## 30 秒上手

### Windows（推荐给普通用户）

1. 下载 [FilePortal-Windows-x64.exe](https://github.com/Lucas-Yun/FilePortal/releases/latest/download/FilePortal-Windows-x64.exe)；
2. 放到一个有写入权限的文件夹（不要放只读光盘或受控目录），双击运行；
3. 浏览器会自动打开 `http://127.0.0.1:8000`；
4. 用 `Admin` / `ChangeMe_Admin` 登录；
5. 进 **后台 → 配置**，立刻做两件事：改 `admin_password`，把 `projection_root` 指向你要分享的目录。

首次启动会在 EXE 同目录创建 `FilePortalData/`，所有数据（配置、账号、回收站、日志）都在里面，删掉这个文件夹即等于彻底卸载。

### Linux

```bash
unzip FilePortal-Linux.zip && cd FilePortal-Linux
chmod +x launcher.sh
./launcher.sh
```

要求 Python 3.10+，无需 `pip install` 任何运行时依赖。详细步骤见 [Linux 版](#linux-版)。

## 为什么选它

| 你关心的 | FilePortal 的做法 |
| --- | --- |
| **部署成本** | 纯 Python 标准库，零第三方运行时依赖；Windows 是单个 EXE，Linux 是一个启动脚本；不需要数据库、Nginx、Docker |
| **按人分权限** | 姓名 + 密码登录；每条规则可单独指定权限（`download,preview,zip,upload,mkdir,rename,delete`）和可见子目录；支持通配姓名 `*` 与排除写法 `!姓名` |
| **老设备兼容** | 下载模式可切「标准 / 兼容」，文件名可选仅 ASCII，专门解决安卓 WebView 与老系统上的中文乱码 |
| **安全边界** | `realpath` 校验阻止目录穿越与符号链接逃逸；响应头带 CSP、X-Frame-Options、X-Content-Type-Options 等；下载直链含签名 + 有效期 + 规则指纹，规则一变旧链立即失效；后台写操作走同源校验 |
| **数据在你手里** | 配置、账号、回收站、日志全在本地 `data/` 与 `runtime/`；仓库不打包任何个人名单、账号、证书或日志 |
| **中文友好** | 内置中 / 英界面切换，中文文档完整，不需要自己汉化 |
| **可运维** | 托盘图标、运维控制台、`launcher.sh status/stop`；`zip_slots`、`upload_slots`、`max_upload_mb`、`user_quota_mb` 可限流限容 |
| **可交付** | GitHub Actions 自动构建 Windows EXE 与 Linux 包，附 SHA256 校验；CodeQL 静态扫描；MIT 许可，可自由改造 |

## 和常见做法的区别

- **公共网盘（百度网盘 / OneDrive）**：数据和访问规则都不在你手里，老设备装不了客户端，权限最细只能到「链接 + 提取码」。
- **`nginx autoindex` / `python -m http.server`**：几行就能列目录，但没有账号体系、没有上传、没有回收站、只有英文目录页。
- **AList / Cloudreve**：能力更重、依赖更多（Go / Node + 数据库），适合做存储聚合或多用户云盘；FilePortal 的目标是「单文件、单目录、按人给权限、开箱是中文」。

一句话：**要的是「把这台机器上的这个文件夹分享出去」，不是「再运营一个网盘平台」。**

## 三种版本

| 版本 | 目录 | 适用场景 | 启动方式 |
| --- | --- | --- | --- |
| Windows 源码版 | `FilePortal/` | 需要阅读/修改源码，或使用完整的多角色规则 | `python app/app.py --root <目录>` |
| Windows 单文件版 | `FilePortal-Portable/` | 普通 Windows 用户，双击即用 | 双击 `FilePortal.exe` |
| Linux 源码版 | `FilePortal-Linux/` | Linux 桌面或服务器，源码启动 | `./launcher.sh` |

三种版本共用同一套核心代码和页面，差别主要在启动器、目录布局和默认角色：

- **源码版**保留 `全权限 / 学习资料 / 只读` 三档密码配置，适合自行配置多角色。
- **Windows 单文件版**和 **Linux 版**默认只保留 `Admin` 一个初始账号，学习资料/只读密码留空，注册默认关闭；需要多角色时由管理员在后台自行创建。
- 三套版本都不附带任何个人名单、登录规则、账号、证书或运行日志。

## 功能一览

### 文件浏览与检索

- 文件夹层级浏览、面包屑导航、常用目录收藏；
- 当前目录及全部子目录递归搜索；
- 文件名、修改时间、大小、类型排序；
- 分页加载，避免大目录一次渲染过多内容。

### 文件操作

- 拖拽/多文件上传，支持子目录上传；
- 单文件下载、多文件批量 ZIP 打包；
- 重命名、移动、删除（进入回收站）；
- 回收站还原、彻底删除、清空回收站；
- 新建文件夹；
- 复制下载直链，方便不支持 Cookie 的系统下载器；
- 下载模式可选“标准/兼容”，并支持并发分片或单连接；
- 下载文件名可选保留中文或仅 ASCII（兼容老旧设备）。

### 在线预览

- 图片、视频、音频在线播放；
- PDF 内嵌预览；
- 文本、代码、日志、Markdown 等按文本展示；
- 常见图片缩略图与目录缩略图；
- 不支持预览的类型给出明确提示。

### 权限与账号

- 按“姓名 + 密码”登录；
- 后台可配置多条登录规则：姓名、密码、权限、可见子目录、备注；
- 支持通配姓名 `*` 和排除写法 `!姓名`；
- 白名单/黑名单按行维护，支持 Excel 名单导入（可选）；
- 屏蔽路径列表：对所有人隐藏指定文件或目录；
- 云空间账号：注册申请、管理员审核、验证码设密、头像、个人目录、容量限制；
- 多设备会话：同一账号可在多台设备登录，后台可查看在线用户；
- 登录失败锁定、全站限速、失败延迟，降低暴力破解风险。

### 后台管理

- 规则编辑与保存；
- 白名单/黑名单维护；
- 屏蔽路径维护；
- 云空间账号审核、开通、重置密码、删除；
- 在线用户与最近活跃设备；
- 配置项在线修改（部分配置需重启）；
- 操作日志按天写入 `runtime/logs/`。

### 部署与安全

- 纯 Python 标准库，无第三方运行时依赖；
- 支持 HTTP/HTTPS；
- 响应头包含 CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy、Permissions-Policy；
- 路径解析使用 realpath 校验，阻止目录穿越和符号链接逃逸；
- ZIP 打包跳过符号链接和隐藏文件；
- 下载直链带签名、有效期和规则指纹，规则变化后旧链接立即失效；
- 管理后台写操作启用同源请求校验；
- 上传文件名过滤 Windows 非法字符、保留设备名和路径分隔符。

## 快速开始（分版本详解）

### Windows 单文件版

1. 从 [Releases](https://github.com/Lucas-Yun/FilePortal/releases/latest) 下载 `FilePortal-Windows-x64.exe`。
2. 把 EXE 放到一个有写入权限的文件夹（不要放在只读光盘或受控目录）。
3. 双击运行。首次启动会在 EXE 同目录创建 `FilePortalData/`，并自动打开浏览器。
4. 默认登录：
   - 姓名：`Admin`
   - 密码：`ChangeMe_Admin`
5. 登录后立即到 **后台 → 配置** 修改 `admin_password` 和 `PW_FULL`。
6. 默认投射目录是当前用户的“文档”文件夹；可在 `FilePortalData/config.ini` 中修改 `projection_root`。

> Windows 10/11 首次运行可能出现 SmartScreen 提示。这是未签名单文件程序的常见行为；确认文件来自本仓库 Release 后，选择“更多信息 → 仍要运行”。如果不需要托盘图标，也可以直接用源码版。

### Linux 版

```bash
unzip FilePortal-Linux.zip
cd FilePortal-Linux
chmod +x launcher.sh
./launcher.sh
```

要求 Python 3.10+。首次启动会：

- 读取 `app/config.ini`；
- 如果 `projection_root` 为空或仍是 Windows 路径，自动改为当前用户的文档目录；没有文档目录时使用 `~/FilePortalShare`；
- 在 `~/FilePortalCloud` 创建云空间根目录；
- 启动服务并打开 `http://127.0.0.1:8000`。

默认登录同上：`Admin / ChangeMe_Admin`。首次登录后请立即修改密码。

常用命令：

```bash
./launcher.sh ensure    # 只启动服务，不打开浏览器
./launcher.sh status    # 查看是否运行
./launcher.sh stop      # 停止服务
./launcher.sh console   # 打开运维控制台
```

### 源码版

```bash
cd FilePortal
python3 app/app.py --root "/path/to/your/files"
```

Windows PowerShell：

```powershell
cd FilePortal
python app/app.py --root "D:\Files"
```

也可以不传 `--root`，直接编辑 `FilePortal/app/config.ini`：

```ini
[Server]
projection_root = D:\Files
port = 8000
host = 0.0.0.0
```

源码版默认保留三档密码：

- `PW_FULL`：全权限；
- `PW_STUDY`：学习资料目录；
- `PW_READ`：只读。

如果不需要多角色，把 `PW_STUDY`、`PW_READ` 留空即可。

## 初始设置

无论使用哪个版本，第一次启动后都建议按下面顺序完成初始设置。

### 1. 修改默认密码

默认密码仅用于首次登录，**必须在对外开放前修改**。

编辑 `config.ini` 的 `[Passwords]` 段：

```ini
[Passwords]
pw_full = 你的全权限密码
admin_password = 你的后台密码
```

后台地址：`http://127.0.0.1:8000/admin`
后台登录：姓名 `Admin` + `admin_password`。

修改后重启服务生效。也可以在后台“配置”页面修改部分配置，页面会提示是否需要重启。

### 2. 设置投射目录

`projection_root` 是网页上可见的根目录。建议：

- 使用一个专门的文件目录，不要把整个磁盘、系统目录或用户主目录直接投射；
- Windows 路径使用正斜杠或双反斜杠；
- Linux 路径使用绝对路径；
- 目录必须存在且当前进程有读取权限。

### 3. 设置访问角色

源码版可以在 `[Passwords]` 中设置三档密码；便携版/Linux 版默认只保留 Admin，其他角色留空。需要多角色时：

1. 登录后台；
2. 在“登录规则”中新增规则；
3. 填写姓名、密码、权限、可见目录；
4. 保存后立即生效，无需重启。

权限字段支持：

```text
download,preview,zip,upload,mkdir,rename,delete
```

留空表示只读；填 `delete,rename` 会进入全权限档。

### 4. 设置白名单/黑名单（可选）

- 白名单：只有名单中的姓名可以登录；
- 黑名单：名单中的姓名一律拒绝；
- 文件位置：`data/lists/whitelist/manual.txt`、`data/lists/blacklist/manual.txt`；
- 一行一个姓名，`#` 开头为注释；
- 后台页面也可以直接维护。

留空表示不启用名单限制。

### 5. 设置屏蔽路径（可选）

`data/blocked_paths.txt` 用于对所有人隐藏指定文件或目录。支持相对投射根的路径，也支持绝对路径；一行一个，`#` 开头为注释。

### 6. HTTPS（可选，公网部署建议）

在 `config.ini` 的 `[Server]` 段填写 `certfile`、`keyfile` 和 `https_port`，重启后通过 `https://` 访问。没有证书时先用 HTTP 仅在内网使用；不要把默认密码和 HTTP 直接暴露到公网。

## 中英文切换

三套版本都支持中文和英文：

- 页面右下角有 `中文 / English` 切换按钮；
- 选择会写入 Cookie `fp_lang`，有效期一年；
- 只支持 `zh` 和 `en` 两种语言，其他值回退为中文；
- 文件内容、文件名、目录名、用户姓名不会被翻译，只翻译界面文案；
- 下载文件名、预览内容、纯文本响应和 JSON 数据保持原样。

## 后台管理

后台路径：`/admin`

主要区域：

| 区域 | 作用 |
| --- | --- |
| 当前在线 | 最近 30 分钟活跃的姓名、设备和登录方式 |
| 登录规则 | 增删改规则，设置权限和可见目录 |
| 白名单/黑名单 | 按行维护姓名名单 |
| 屏蔽路径 | 对所有人隐藏文件/目录 |
| 云空间账号 | 审核注册申请、开通账号、重置密码、删除账号 |
| 配置 | 修改端口、根目录、密码、页脚、联系方式等 |
| 验证码 | 查看/更新注册申请的验证码 |

后台只对 `admin_name`（默认 `Admin`）且使用 `admin_password` 或 `PW_FULL` 登录的身份开放。普通全权限用户看不到后台入口。

## 配置说明

主要配置位于 `app/config.ini`（便携版是 `FilePortalData/config.ini`）。

```ini
[Server]
projection_root = /path/to/files
port = 8000
host = 0.0.0.0
workers =
zip_slots = 2
upload_slots = 4
list_cache_seconds = 3
per_page = 60
max_upload_mb = 2048
user_quota_mb = 0

[Passwords]
pw_full = ChangeMe_123
pw_study =
pw_read =
admin_password = ChangeMe_Admin
legacy_password =
full_name = Admin
admin_name = Admin
study_subpath = Study

[Cloud]
cloud_root = FilePortalCloud
register_enabled = 0

[Footer]
show_footer = false
contact_wechat =
contact_phone =
contact_email =
```

说明：

- `projection_root`：网页可见根目录；为空时使用当前用户文档目录。
- `workers`：并发请求上限；留空按 CPU 自动计算。
- `max_upload_mb`：单文件上传上限，`0` 表示不限制（不推荐）。
- `user_quota_mb`：每个云空间账号容量上限，`0` 表示不限制。
- `register_enabled`：是否允许访客提交云空间注册申请。
- `show_footer`：是否显示页脚备案/联系方式；默认关闭模板中的页脚。
- `contact_*`：页脚联系方式，默认留空。

## 安全建议

1. **先改密码，再开放网络。** 默认的 `ChangeMe_*` 只是占位值。
2. **不要在公网直接跑 HTTP。** 使用 HTTPS，或放在 VPN/内网穿透后面，并限制来源。
3. **不要投射整个磁盘、系统目录或用户主目录。** 使用专用目录，并只授予必要权限。
4. **定期备份 `data/` 和 `config.ini`。** 回收站不是备份，删除仍可能被清理。
5. **谨慎使用 `delete` 权限。** 对不信任的用户只给 `download/preview`。
6. **不要把 `config.ini`、`data/accounts.json`、`data/.session_secret`、证书和日志提交到公开仓库。**
7. **公网部署建议加反向代理和访问控制**，并监控 `runtime/logs/`。
8. 如果发现安全问题，请按 [SECURITY.md](SECURITY.md) 的方式私下报告，不要直接公开利用细节。

## 常见问题

### 首次启动提示“投射目录为空/不存在”

编辑 `config.ini` 的 `projection_root` 为真实存在的目录，或启动时传 `--root`。便携版/Linux 版启动器会自动写入当前用户文档目录；如果系统没有文档目录，Linux 版会使用 `~/FilePortalShare`。

### 忘记后台密码

停止服务，编辑 `config.ini` 的 `admin_password` 或 `pw_full`，重启。若两者都为空，可临时设置 `admin_password`。

### 端口被占用

修改 `config.ini` 的 `port`，或启动时传 `--port 8001`。Linux 版同时修改 `launcher.sh` 里的 `PORT` 环境变量（如 `PORT=8001 ./launcher.sh`）。

### Windows 提示 SmartScreen / 防火墙

单文件 EXE 未做代码签名，SmartScreen 可能提示。确认来源后选择“仍要运行”；防火墙提示用于局域网访问，选择允许即可。

### 中文文件名下载后变成乱码

在下载设置中切换为“仅英文和数字（兼容老旧设备）”，或使用标准模式/HTTPS。部分安卓 WebView 对中文 `Content-Disposition` 支持不佳。

### 回收站文件在哪里

在投射根目录下的隐藏目录 `.trash/`。不要手动删除该目录，否则无法在页面还原。

### 为什么 ZIP 里没有某个文件

ZIP 打包会跳过隐藏文件、临时文件、被屏蔽路径和符号链接；这是为了避免把投射根之外的内容打包进去。

## 项目结构

```text
FilePortal/
├─ FilePortal/                 # Windows 源码版
│  ├─ app/
│  │  ├─ app.py                # 服务入口
│  │  ├─ console.py            # 运维控制台
│  │  ├─ tray.py               # 托盘
│  │  ├─ server/               # 路由、会话、规则、页面、缓存、安全
│  │  ├─ assets/images/        # SVG 图标
│  │  ├─ data/                 # 空名单/空账号种子
│  │  └─ docs/
│  └─ launcher.bat
├─ FilePortal-Portable/        # Windows 单文件版源
│  └─ app/
│     ├─ portable.py           # PyInstaller 入口
│     ├─ app.py
│     ├─ console.py
│     ├─ tray.py
│     └─ server/
├─ FilePortal-Linux/           # Linux 源码版
│  ├─ launcher.sh
│  └─ app/
│     ├─ linux_launcher.py
│     ├─ linux_service.py
│     ├─ console.py
│     └─ server/
├─ .github/workflows/          # Windows EXE / Linux ZIP 自动构建、CodeQL
├─ .github/ISSUE_TEMPLATE/     # Bug 与功能建议表单
├─ .github/pull_request_template.md
├─ .github/dependabot.yml
├─ README.md
├─ CONTRIBUTING.md
├─ CODE_OF_CONDUCT.md
├─ SECURITY.md
├─ SUPPORT.md
├─ CHANGELOG.md
├─ LICENSE
└─ .gitignore
```

## 开发与构建

### 源码运行

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python FilePortal/app/app.py --root ./demo
```

项目只使用 Python 标准库，不需要 `pip install` 运行时依赖。

### Windows 单文件构建

在 Windows 上：

```powershell
cd FilePortal-Portable/app
pip install pyinstaller
pyinstaller --noconfirm --onefile --noconsole --name FilePortal `
  --add-data "config.ini;." `
  --add-data "assets;assets" `
  --add-data "data;seed_data" `
  --add-data "docs;docs" `
  --collect-submodules server `
  portable.py
```

生成文件：`dist/FilePortal.exe`。

仓库的 GitHub Actions 会在 `windows-latest` 上执行同样的构建，并把 EXE 附到 Release。

### Linux 打包

```bash
cd FilePortal-Linux
zip -r ../FilePortal-Linux.zip . \
  -x 'app/runtime/*' 'app/data/.session_secret' '__pycache__/*' '*.pyc'
```

### 发布

推送 `main` 分支后，`.github/workflows/build-release.yml` 会自动：

1. 构建 Windows EXE；
2. 打包 Linux ZIP；
3. 生成 SHA256 校验文件；
4. 创建/更新 `v1.0.0` Release 并上传资产。

## English Summary

FilePortal is a self-hosted, lightweight file portal written in pure Python. It maps a local folder to a browser-based file workspace with role-based access, upload/download, preview, ZIP packaging, recycle bin, cloud accounts, admin console, and a built-in Chinese/English UI switcher.

Three editions are provided: Windows source, Windows portable single-file EXE, and Linux source with a launcher script. Download the latest Windows EXE or Linux ZIP from [Releases](https://github.com/Lucas-Yun/FilePortal/releases/latest). The default login is `Admin / ChangeMe_Admin`; change it before exposing the service. See the Chinese sections above for full setup, configuration, and security guidance.

## 参与贡献

欢迎提交 Bug 修复、文档改进和经过讨论的功能建议。开发环境、代码规范、测试清单、PR 流程和隐私要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 安全漏洞不要公开提 Issue，请按 [SECURITY.md](SECURITY.md) 私密报告；
- 参与讨论和提交代码前，请阅读 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)；
- 使用问题、支持范围和商业使用说明见 [SUPPORT.md](SUPPORT.md)。

## 安全政策

安全模型、支持版本、私密报告渠道、协调披露、安全港、供应链和部署边界见 [SECURITY.md](SECURITY.md)。

公开部署至少应修改默认密码、使用 HTTPS 反向代理、限制投射目录、定期备份，并避免把真实配置、账号、名单、证书和日志提交到仓库。

## 行为准则

本项目采用 Contributor Covenant 2.1 的社区行为规范。参与项目即表示同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 支持与帮助

社区支持以文档和公开 Issue 为主，不提供针对个人生产环境的远程代维或商业 SLA。详见 [SUPPORT.md](SUPPORT.md)。

## 变更日志

版本变更、修复和安全相关调整记录在 [CHANGELOG.md](CHANGELOG.md)。

## 如果它对你有用

- 点一个 **Star**，是最便宜的鼓励，也能让更多人搜到这个项目；
- 有功能想法或踩到坑，欢迎开 [Issue](../../issues) —— 说得越具体，改得越快；
- 想让更多人知道自己用得上它，转发到班级群、实验室群、自建服务社区比任何推荐算法都管用。

## License

[MIT](LICENSE)
Copyright (c) 2026 Lucas-Yun and FilePortal contributors.
FilePortal is provided “as is”, without warranty of any kind. You are responsible for the data you expose, the network you bind to, and the permissions you grant.
