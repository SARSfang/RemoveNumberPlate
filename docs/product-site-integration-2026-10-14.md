# 产品页接入与发布准备

日期：2026-10-14。当前为本地预览，不代表公网部署。

## 文件位置

- 产品源：E:\消除车牌\product-site。
- MyWeb 副本：E:\MyWeb\products\remove-number-plate。
- 预定远端：/var/www/fangdian-products/remove-number-plate。
- URL：https://fangdian.xyz/remove-number-plate/。

## 路由

将下方两个 location 放入实际服务 fangdian.xyz 的 HTTPS server 中。
不要盲目覆盖既有 Nginx 配置；先检查现用配置、根目录、CSP 与证书。

```nginx
location = /remove-number-plate {
    return 301 /remove-number-plate/;
}
location ^~ /remove-number-plate/ {
    root /var/www/fangdian-products;
    index index.html;
    try_files $uri $uri/ =404;
}
```

产品 HTML/CSS/JavaScript/图片/许可文件分别位于此路径内。
片段不增加自定义 add_header，继承既有安全头；不存在的产品资源返回 404，不回退到拍车首页。
只上传明确的网页资源清单，不上传源照片、模型、运行环境、验证日志或文档。

## Service Worker

paiche/web/vite.config.js 的 navigateFallbackDenylist 需要追加：

```js
/^\/remove-number-plate(?:[/?]|$)/
```

覆盖带斜杠、不带斜杠和查询参数的产品导航，保留现有 preview、insights 和 privacy 排除项。
只有重新构建并发布拍车的 Service Worker 后，新的规则才会影响线上访客。
既有 skipWaiting/clientsClaim 能协助切换，但不能保证尚未获取更新的旧浏览器已经迁移。
发布验收须覆盖：全新浏览器、曾访问拍车的浏览器、新 SW 接管后的直接导航。
不以让所有访客清空缓存或注销所有 SW 作为默认解决办法。

## 个人站入口

现有 development/remove-number-plate.html 和 js/pages.js 的开发详情相关链接应增加产品入口。
可在 content-data.js 的该项目新增 productUrl，再由详情渲染器读取；不得替换既有源码 URL。
在产品路径可用之后，与相关入口同批发布，避免先上线按钮后出现 404。
两页职责不同：个人站保留研发档案，产品页提供效果和获取方式。

## 发布前检查

- 首屏完整照片不裁切，放大范围按源图坐标对应子图。
- 消除前/高清消除后与旧版/高清两组滑块独立，均可键盘、放大、重置。
- 手机无横向溢出；信息说明、FAQ 与仓库入口可达。
- 原始车牌只出现在用户明确要求的前后对比里；本地预览不等于授权公网发布。
- 原片、验收输出、源码、许可与版本日期保持准确；高清版不冒充正式版。
- 网页交付前由用户审核，公网发布按 MyWeb AGENTS.md 另行确认。
- HTTPS 路径、旧 SW、CSP、仓库链接、canonical、分享图片与站点入口在发布后复验。

目前公开版本元信息以本地 RELEASE.md 为依据。GitHub 官方 API 本轮返回配额限制，不能声称已重新验证线上资产大小或最新发布状态。
