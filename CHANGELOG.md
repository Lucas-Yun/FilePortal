# Changelog

本项目的重要变更记录在这里。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

### Added

- 完整的 MIT 许可证署名。
- 扩展的安全政策：私密报告、协调披露、安全港、供应链和部署边界。
- 贡献指南、贡献者行为准则、支持说明、Issue 与 Pull Request 模板。
- Dependabot 配置、CODEOWNERS、EditorConfig 和 Git 属性文件。
- README 增加构建、安全、贡献和行为准则入口。

### Changed

- 发布说明补充移动端适配和文档入口。

## [1.0.0] - 2026-11-23

### Added

- Windows 源码版、Windows 单文件便携版和 Linux 源码启动包。
- 多角色登录规则、白名单/黑名单、屏蔽路径和后台管理。
- 文件浏览、递归搜索、排序、分页和缩略图。
- 上传、下载、重命名、移动、删除、回收站和 ZIP 打包。
- 图片、视频、音频、PDF、文本在线预览。
- 个人云空间：注册申请、审核、验证码设密、头像、容量限制和多设备会话。
- 中英文界面切换。
- GitHub Actions 自动构建 Windows EXE 与 Linux ZIP，并生成 SHA-256 校验文件。

### Fixed

- 手机和平板登录页改为响应式堆叠布局，长内容可从顶部完整滚动。
- 个人云盘“用户须知”长文本在手机和平板上不再被垂直居中裁切。
- 小屏设备上的语言切换按钮不再固定覆盖页面内容。
- 修复 Windows 无控制台 EXE 在 `sys.stderr` 为空时请求返回空响应的问题。

### Security

- 三个发布版均不包含真实生产密码、个人联系方式、真实名单或 `rules.json`。
- 保留路径穿越/符号链接校验、会话签名、下载令牌、POST 同源检查和安全响应头。

## [Older versions]

`v1.0.0` 是首个公开发布版本；没有更早的公开版本记录。
