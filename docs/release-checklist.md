# 发布检查清单

Updated: 2026-07-28

## RC2 GitHub 干净构建证据

- GitHub Actions 运行：[30319273349](https://github.com/SARSfang/RemoveNumberPlate/actions/runs/30319273349)
- 提交：`d7bc7f3ddc54b8a16436e0bd30fa03364e81eedc`
- 结果：模型从固定来源重建、依赖安装、测试、PyInstaller 打包、中文安装/卸载验收及产物上传全部通过。
- CI 安装包：`消除车牌-Setup-v0.2.0-rc.2-win64.exe`
- CI 安装包 SHA-256：`62be0b452daf8e960060b2c267583dd702514144c43f0c408a1680160eee0047`
- 产品文件版本：`0.2.0.2`
- 当前手动预览包未签名；正式 `v*` 标签仍会在没有有效 Windows 签名证书时被流水线拒绝。

## RC2 工程门槛

| 门槛 | 状态 | 证据 |
|---|---|---|
| 固定版本与哈希 | 通过 | `app/version.py`、版本同步测试、`SHA256SUMS.txt` |
| 模型可复现 | 通过 | 官方源归档经 Paddle 3.0.0 + Paddle2ONNX 2.1.0 重建，三份启用模型哈希一致 |
| 全量自动测试 | 通过 | Windows 本机单元、集成、静态类型与前端语法检查 |
| 运行时离线 | 通过 | CSP `connect-src 'none'`；应用运行时代码无网络客户端导入 |
| 原片保护 | 通过 | 原片哈希不变；输出原子写入独立目录；不覆盖同名结果 |
| 中文/空格/长路径 | 通过 | 291 字符真实冻结版图片处理，生成结果且源文件哈希不变 |
| 安装与卸载 | 通过 | 普通用户静默安装、安装后启动、卸载、目录残留检查 |
| 原位升级 | 通过 | RC1 原位升级 RC2，程序版本更新且用户数据哨兵保留 |
| 安装器本地化 | 通过 | Inno Setup 7 官方简体中文语言文件 |
| 许可证随包 | 通过 | 模型说明、Python wheel 许可证和 WebView2 通知随安装目录分发 |
| 诊断可支持性 | 通过 | 轮转日志、崩溃钩子、隐私安全诊断 ZIP |
| 发布自动化 | 通过 | GitHub 手动预览与签名 tag 发布工作流 |
| 代码签名门禁 | 通过 | EXE/安装器签名脚本；tag 无证书时拒绝发布 |

## 正式商业发布外部门槛

以下项目不能由代码或自动测试替代，关闭前只能发布候选版：

- [ ] 至少 100 张代表性私有商拍照片的摄影师质量签收；
- [ ] PaddleX/PP-Vehicle 权重商业再分发条款的专业法律复核；
- [ ] 购买 Windows 代码签名证书并配置 GitHub secrets；
- [ ] 购买适用的 Inno Setup 商业许可证。

## GitHub 签名 secrets

- `WINDOWS_SIGN_CERTIFICATE_BASE64`：PFX 文件的 Base64；
- `WINDOWS_SIGN_CERTIFICATE_PASSWORD`：PFX 密码。

正式 `v*` tag 只有在两项 secrets 可用、签名验证通过后才会创建 GitHub Release。
