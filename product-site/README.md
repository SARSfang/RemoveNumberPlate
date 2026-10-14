# 消除车牌产品网页

独立静态页面，预定正式路径 `https://fangdian.xyz/remove-number-plate/`。
目前为本地预览，未发布。

## 内容与维护

- `index.html`：产品介绍、两组实拍对比、版本信息与项目说明。
- `styles.css`：独立样式，暖白背景、蓝色重点、较浅的灰绿色影像与流程分区。
- `site.js`：每组对比独立的范围滑块、20% 放大与重置。
- `assets/high-full.webp`：PFDA0512 完整修复结果的网页展示副本，保留构图。
- `assets/original.webp`、`legacy.webp`、`high.webp`：相同局部裁剪、相同压缩设置。
- 所有软件获取入口均指向 `https://github.com/SARSfang/RemoveNumberPlate`。
- 高清版仍标测试版，公开下载尚未上传；无在线照片上传、在线推理或访客统计。
- 原始照片、无损验收结果及原项目未被修改。网页展示副本不是原始分辨率文件。
- 真实软件录屏暂无，不以虚构截图冒充实测；功能示意已明确标注。

`scripts/sync_product_site.py` 可将文件校验后复制到 `E:\MyWeb\products\remove-number-plate`。
如果目标已有不同内容，脚本会停止；先核对修改，不能强行覆盖别人的工作。

## 预览

`python -m http.server 8938 --bind 127.0.0.1 --directory product-site`

浏览器打开 `http://127.0.0.1:8938/`。
亦可直接打开 `index.html`。网页无远程字体、框架或脚本依赖。

## 站点接入

见软件仓库 `docs/product-site-integration-2026-10-14.md`。
路由片段只为审核准备，不代表服务器已经配置。
