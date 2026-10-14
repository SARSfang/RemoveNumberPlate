# 消除车牌产品网页

独立静态页面，正式路径 `https://www.fangdian.xyz/remove-number-plate/`，已于 2026-10-14 上线。

## 内容与维护

- `index.html`：产品介绍、两组实拍对比、版本信息、SHA-256 校验信息与项目说明。
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
- 所有软件获取入口均指向 `https://github.com/SARSfang/RemoveNumberPlate` 的 v1.2.0 Release。
- 无在线照片上传、在线推理或访客统计；安装包未做代码签名，FAQ 已说明 SmartScreen 提示与哈希核对方法。
- 原始照片、无损验收结果及原项目未被修改。网页展示副本不是原始分辨率文件。
- 真实软件录屏暂无，不以虚构截图冒充实测；功能示意已明确标注。

HTML/CSS/JS 的版本缓存参数需同步更新（当前 `?v=20261015p6`），避免 CDN 与浏览器缓存旧资源。

`scripts/sync_product_site.py` 可将文件校验后复制到 `E:\MyWeb\products\remove-number-plate`（已排除 README.md）。
如果目标已有不同内容，脚本会停止；先核对修改，不能强行覆盖别人的工作。

## 预览

`python -m http.server 8938 --bind 127.0.0.1 --directory product-site`

浏览器打开 `http://127.0.0.1:8938/`。
亦可直接打开 `index.html`。网页无远程字体、框架或脚本依赖。

## 站点接入

见 `docs/product-site-integration-2026-10-14.md`，含线上 nginx location、Service Worker denylist 与自定义 404 的 error_page 配置。
