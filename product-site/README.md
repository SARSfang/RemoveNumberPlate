# 消除车牌产品网页

独立静态页面，正式路径 `https://www.fangdian.xyz/remove-number-plate/`，已于 2026-10-14 上线。

## 内容与维护

- `index.html`：自动批量处理优先的介绍页，依次展示首屏、实拍效果、自动流程、多车牌与高清能力、下载、项目与 FAQ。
- `styles.css`：独立样式，暖白背景、蓝色重点、较浅的灰绿色影像与流程分区。
- `site.js`：原生 JavaScript，无依赖。功能包括：
  - 每组对比独立的范围滑块、放大与重置，滑块位置按区块分别记忆（localStorage，失败静默）。
  - 滚动淡入（`[data-reveal]`，仅在支持 IntersectionObserver 且未开启减少动效时生效；无 JS 时内容默认可见）。
  - 顶部导航当前章节高亮（scrollspy，aria-current）。
  - SHA-256 一键复制（Clipboard API，非安全上下文回退 execCommand）。
  - 移动端底部浮动「获取软件」条：滚过首屏后出现、进入下载区后隐藏（仅 ≤760px 显示，body 预留占位不遮挡 footer）。
- `404.html`：自定义 404 页，复用同一套样式，noindex，主入口回到产品首页。
- `assets/high-full.webp`：PFDA0512 完整修复结果的网页展示副本，保留构图。
- `assets/original.webp`、`legacy.webp`、`high.webp`：相同局部裁剪、相同压缩设置。
- `assets/pfd32132-{original,result}-{960,1920}.webp`：路虎原图与消除结果的响应式展示副本，用户已明确要求公开原图滑动对比。构图、水印、展示尺寸与压缩设置一致；支持独立拖动、键盘、两倍局部放大与重置，不推断实际使用的修复模式。
- 首屏、导航与手机浮条均进入页内 `#download`，下载按钮前往 GitHub v1.2.0 Release。
- 原图／高清结果为主要对比；旧版／高清对比默认折叠，各自的滑块、缩放、重置和位置记忆独立。
- SHA-256 默认折叠，系统要求与非商用许可保持可见。减少动效和无 JavaScript 时仍可阅读和获取软件。
- 无在线照片上传、在线推理或访客统计；安装包未做代码签名，FAQ 已说明 SmartScreen 提示与哈希核对方法。
- 原始照片、无损验收结果及原项目未被修改。网页展示副本不是原始分辨率文件。
- 本轮未取得当前版本真实软件截图，采用文字流程；未使用旧版截图或模拟数据预览冒充当前实测。

HTML/CSS/JS 的版本缓存参数需同步更新（当前 `?v=20261015p10`），404 页样式引用同步更新，避免缓存旧资源。

`scripts/sync_product_site.py` 可将文件校验后复制到 `E:\MyWeb\products\remove-number-plate`（已排除 README.md）。
如果目标已有不同内容，脚本会停止；先核对修改，不能强行覆盖别人的工作。

独立产品页发布使用 `scripts/deploy_product_site.py`：服务器固定目标为产品目录，发布包含完整资源清单、SHA-256 和上线前基线。基线变化即停止；候选目录校验后切换，保留旧目录并记录回退位置。不使用会同时切换个人站和拍车的整轮发布脚本。

## 预览

`python -m http.server 8938 --bind 127.0.0.1 --directory product-site`

浏览器打开 `http://127.0.0.1:8938/`。
亦可直接打开 `index.html`。网页无远程字体、框架或脚本依赖。

## 站点接入

见 `docs/product-site-integration-2026-10-14.md`，含线上 nginx location、Service Worker denylist 与自定义 404 的 error_page 配置。
