# 本轮网页与 README 发布记录

2026-10-14，用户授权“网页全部上线，git”。

## 已发布范围

- 个人站主页、开发列表、消除车牌详情的产品入口与简介；共享样式及详情首章节留白。生成页面与缓存引用同批更新。
- 拍车首页摄影师区域产品入口；Service Worker 排除独立产品页。
- 独立产品页的移动端获取入口、代码签名说明及缓存引用。
- 软件仓库 README 的 Logo、海报、实拍对比、文档布局与许可说明。

正式地址：

- https://me.fangdian.xyz/
- https://me.fangdian.xyz/development/remove-number-plate.html
- https://fangdian.xyz/
- https://fangdian.xyz/remove-number-plate/

## Git 与检查

- MyWeb 源码提交 `be2f0e7e85377a7066a23e6218b56ec5e723c6d6`。
- 最终缓存版本修复提交 `137fc1ac951b15b96414c1dec5046c4954c76c16`，正式版本 r54；已推送 origin/main，核对本地与远端一致。
- 软件文档及海报提交 `ba59932`，已推送 origin/main；部署脚本及本记录另行提交。
- 初次 personal-site-gates 38556350511 失败：临时分批缓存版本未通过正式白名单。统一 r54 后，38556637492 成功。
- web-quality 38556350425、paiche-gates 38556350489、preview-gates 38556350512 均成功。
- 本地 9 项个人站门禁测试、发布内容校验、敏感文件检查通过；拍车 Home.jsx ESLint 与正式 Vite 构建通过。
- 本地静态批次生成与检查通过，生成列表的行尾空白另行清理。

## 部署与回退资料

部署脚本：`scripts/deploy_product_round.py`。只覆盖发布清单内的静态文件，不重启业务服务，不修改数据库或小程序。

首次部署标记 `1791977085`，最终 r54 部署标记 `1791977234`，每次校验 188 个文件。

**要回到本轮上线前，应使用首次备份**，最终备份保存的是已上线但尚未统一缓存版本的中间状态。

- 本轮前个人站被覆盖文件：`/opt/sitewide-visual-backups/plate-round-1791977085/personal/`。
- 本轮前产品目录：`/var/www/fangdian-products/remove-number-plate.plate-before-1791977085`。
- 本轮前拍车目录：`/var/www/paiche-web/dist.plate-before-1791977085`。
- 最终部署记录：`/opt/sitewide-visual-backups/plate-round-1791977234/release.json`。
- 最终中间状态备份同样保留，名称后缀为 `1791977234`。

产品及拍车目录使用同级候选目录切换，旧哈希资源保留以兼容已打开页面。个人站依赖先、HTML 后替换；这不是三个站点的整体原子事务，短暂混合版本窗口仍存在。脚本异常会恢复已覆盖个人文件并换回旧目录。

## 线上验收

- 服务器端清单中全部文件 SHA-256 一致。
- HTTPS 核对首页、详情、共享 CSS、产品 HTML/CSS/JS、拍车 HTML/SW/Home 脚本，返回 200 且内容指纹一致；r54 重新核对通过。
- 实际浏览器确认个人详情显示 v1.2.0、新产品简介及入口；首章节 padding-top 为 24px，产品入口打开正确地址。
- 截图：`output/product-links-review/online-detail-r54.png`。
- 本轮未重测预约、支付、管理等业务操作，也未作完整手机矩阵验收。

无关的旧拍车海报删除、IDE 缓存仍留在工作区，未纳入提交或部署。
