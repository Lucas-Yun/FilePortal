## 变更摘要

<!-- 用一两句话说明这个 PR 解决了什么。 -->

## 类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 文档
- [ ] 构建 / CI
- [ ] 重构（不改变行为）
- [ ] 安全加固

## 关联 Issue

<!-- 例如：Closes #12；没有就写“无”。 -->

## 改动内容

<!-- 列出关键文件和设计取舍，避免逐行复述 diff。 -->

## 验证

- [ ] `python -m compileall -q FilePortal/app FilePortal-Portable/app FilePortal-Linux/app`
- [ ] 本地启动并完成相关功能冒烟测试
- [ ] 涉及 UI 时附上修复前后截图和视口尺寸
- [ ] 涉及三版共享代码时，检查三套版本均已同步
- [ ] 涉及 Windows 便携版时，验证启动后 `/login` 正常返回

测试记录：

```text
在此粘贴已脱敏的命令、结果或截图说明。
```

## 安全与隐私

- [ ] 没有提交真实密码、token、Cookie、证书、私钥或 `.session_secret`
- [ ] 没有提交真实姓名、手机号、邮箱、名单、`rules.json`、`accounts.json` 或用户文件
- [ ] 没有削弱路径校验、登录限制、会话签名、下载令牌、屏蔽路径或响应头
- [ ] 已删除日志和截图中的个人路径、账号和用户数据

## 文档与发布

- [ ] 已更新相关 README / 文档
- [ ] 行为变化已写入 `CHANGELOG.md` 的 `Unreleased`
- [ ] 如影响发布，已说明对 Windows / Linux 构建和 Release 资产的影响
