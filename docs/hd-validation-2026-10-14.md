# 高清修复验证记录

## 真实照片

使用用户提供的 PFDA0512.jpg（3842×5763），原片只读，结果位于 output/hd-validation。检测产生两个文字区域，扩展遮罩合并后局部裁剪 1004×1004。

旧版四倍上下文缩到 512，局部格栅横条明显变软。新标准模式收紧上下文，缩放比例约 0.51；Big-LaMa 按原尺度处理该裁剪，局部视觉检查横条及中心分隔线连续性和清晰度改善。该照片存在强结构边缘，默认开启的纹理增强自动跳过。

legacy-crop.png、standard-crop.png、high-crop.png、high-texture-crop.png 为同坐标、同尺寸对比，comparison.png 为并排展示。不能把单张照片改善推广为全部材质和反光条件均成功。

## 运行路径

权重来源、校验值固定在 models/manifest.json。Sanster TorchScript 转换版的发布者 MD5 匹配，本地 SHA-256 固定。直接 ONNX opset17 导出实测失败于 aten::fft_rfftn，因此采用独立 PyTorch 工作程序。

1024、1536、2048 三档均已执行真实 Big-LaMa 推理。worker-memory.json 记录打包 CPU 工作程序观察到的工作集峰值，约 1.57、2.90、4.61 GiB；它们是放大裁剪压力测试，不能证明原生高分辨率照片质量。

完整打包程序已通过 --smoke，并使用 --verify-repair 处理原图的无损解码副本。bundle-high.verification.json 确认使用 big-lama、scale=1、无回退。输出维度 5763×3842，遮罩外像素完全一致，结果与独立环境生成的 high-full.png 逐像素一致。

启动脚本问题已实际复现为 UTF-8 中文与非 Windows 换行导致命令解析失败。修复编码和 CRLF 后，同一脚本 --smoke 返回 0；用户随后确认程序与四项高清设置均正常。

## 验证范围

自动回退、显式高清失败、相邻车牌上下文重叠、纹理合适/平滑/排除其他遮罩、设置迁移与持久化、运行中拒绝变更、保存失败回滚、预览失效及迟到渲染有针对性测试。

修改前已有的 app/desktop.py、tests/unit/test_desktop.py 和项目交接手册未被覆盖。回归为 326 passed、1 skipped，新增工作程序错误路径另 3 passed，前端 33 passed，Ruff/Mypy 通过。中文临时路径下原有 Paddle 运行库测试跳过；尝试 ASCII 系统临时目录时受沙箱写权限限制，两项未执行，不声称全平台 Paddle 验收。监视目录原有 Windows 关闭句柄挂起的 E2E 未运行；本次对共享 BatchService 配置路由进行代码与单元验证，不声称修复此既有缺陷。

用户已确认更新后的 Logo、滑块开关、分段质量选项显示与操作均正常。浏览器工具对本地文件协议明确拒绝，未绕过；本次 GUI 视觉验收由用户完成。最新启动脚本 --smoke 返回 0，final-auto.verification.json 确认自动模式实际使用 Big-LaMa、scale=1、无回退；final-auto.png 与 high-full.png 逐像素一致，修复范围外像素完全一致。完整目录约 1.00 GiB，包含可选 CPU 后端与高清权重；GPU 未验收。

用户明确要求只使用 PFDA0512.jpg 做照片效果测试。其他样图已停止测试并排除出验收与交付对比；本记录的照片质量结论仅适用于用户指定原片。输入尺寸压力测试也由同一原片的局部裁剪生成，明确标为压力测试。
