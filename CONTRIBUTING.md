# 参与贡献

感谢你愿意改进 FilePortal。这个项目是一个纯 Python 标准库实现的轻量自托管文件服务，维护者会优先接受范围清晰、测试充分、不会削弱安全边界的改动。

## 开始之前

1. 先搜索现有 Issue 和 Pull Request，避免重复工作。
2. 功能类改动建议先开 Issue 说明使用场景和预期行为，再动手实现。
3. **安全漏洞不要公开提 Issue**，请按 [SECURITY.md](SECURITY.md) 私下报告。
4. 行为规范见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 开发环境

要求：

- Python 3.10 或更高版本；
- Windows、Linux 或 macOS；
- 可选：用于浏览器回归测试的 Chrome/Edge；
- 可选：构建 Windows 单文件版时需要 PyInstaller。

源码运行：

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

python FilePortal/app/app.py --root ./demo
```

运行时不需要安装第三方依赖。PyInstaller 只用于打包，不属于运行时依赖。

## 项目结构

```text
FilePortal/            Windows 源码版
FilePortal-Portable/   Windows 单文件版源码
FilePortal-Linux/      Linux 源码版
.github/               工作流、Issue/PR 模板、发布说明
```

三套版本共享核心代码，但启动器、默认配置和目录布局不同。修改核心行为时，请同步检查三套版本的 `app/server/`、`app/config.ini` 和页面资源，避免只有一套版本生效。

## 代码规范

- 优先使用 Python 标准库；引入新依赖前先讨论必要性和部署成本。
- 保持 Python 3.10+ 兼容，使用 4 空格缩进，文件使用 UTF-8 和 LF 换行。
- 路径处理优先使用 `pathlib` / `os.path`，同时考虑 Windows 和 Linux 的差异。
- 页面代码位于 `app/server/views.py`，不要依赖外部 CDN；内联 CSS/JS 需要兼容离线部署。
- 中英文文案要一起维护；新增可见文本时检查语言切换。
- 不要重新引入个人姓名、真实联系方式、生产密码、真实名单或本机绝对路径。
- 不要削弱现有的路径校验、登录限制、会话签名、下载令牌或屏蔽路径逻辑。
- 尽量保持改动小而聚焦；格式化改动和功能改动分开提交。

## 测试与回归

提交前至少运行：

```bash
python -m compileall -q FilePortal/app FilePortal-Portable/app FilePortal-Linux/app
```

手工冒烟测试建议覆盖：

- 登录成功、失败、锁定和退出；
- 目录浏览、搜索、上传、下载、重命名、移动、删除、回收站；
- ZIP 打包下载和直链下载；
- 图片、视频、音频、PDF、文本预览；
- 后台登录、规则保存、在线用户、验证码、名单和屏蔽路径；
- 云空间注册、审核、设密、个人目录、容量限制；
- 中文和 English 切换；
- 手机 360×640、390×844，平板 820×1180，桌面 1440×900 的登录页和用户须知页；
- Windows 单文件版启动后访问 `/login` 不返回空响应。

如果改动涉及 UI，请在 PR 中附上修复前后截图和测试视口尺寸。涉及安全边界时，请说明攻击面、验证方法和回归用例，但不要在公开 PR 中附带可利用的真实数据。

## 提交 Pull Request

建议流程：

1. 从 `main` 创建短分支，例如 `fix/mobile-login`、`docs/security-policy`。
2. 一个 PR 只解决一个逻辑问题，避免把无关重构混在一起。
3. 提交信息用一句清晰的祈使句，例如 `Fix mobile notice scrolling`。
4. 更新相关文档；行为变化写入 [CHANGELOG.md](CHANGELOG.md) 的 `Unreleased` 段。
5. 填写 PR 模板中的测试与安全检查项。
6. 确认 CI 通过，并回应 Review 意见。

维护者可能会要求拆分过大的 PR、补充测试，或调整与项目定位不一致的功能。

## 隐私与仓库卫生

**不要提交**：

- 含真实密码、姓名、手机号、邮箱的 `config.ini`；
- `rules.json`、`accounts.json`、真实名单、屏蔽路径、头像和日志；
- `data/.session_secret`、TLS 私钥、证书、token、Cookie；
- 本机绝对路径、生产环境截图、用户文件内容；
- 构建产物、缓存、`__pycache__`、`.venv`。

如果不确定某个文件是否敏感，先问维护者，不要在 PR 中上传。

## 许可证

提交贡献即表示你同意在 [MIT License](LICENSE) 下授权该贡献，并确认你有权提交相关代码和文档。项目不要求签署单独的 CLA。
