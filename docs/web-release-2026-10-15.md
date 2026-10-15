# 自动处理优先的介绍页改进与发布

日期：2026-10-15。用户已确认设计并明确授权修改、上线与 Git 同步。

## 结果与范围

正式页：https://fangdian.xyz/remove-number-plate/ ，www 同路径内容一致。

- 首屏改为“车牌自动消除，不必逐张修图。”，自动批量处理为主卖点，真实高清效果作为支撑。
- 顺序调整为效果、自动流程、多车牌与高清能力、下载、项目、FAQ；旧版／高清对比默认折叠，哈希默认折叠。
- 首屏、导航和手机浮条进入同一下载区，下载区前往 v1.2.0 正式 Release。
- 未取得当前版本真实操作截图，使用文字流程；未以模拟数据或旧版截图冒充实测。
- 不修改软件功能、安装包、模型、个人站介绍或拍车业务页面；MyWeb 只同步四个产品副本文件。保留两个仓库原有无关文件与删除状态。

实现提交：RemoveNumberPlate `3950e36`；MyWeb 副本提交 `3e2b0f2`。本记录另行提交。

## 验证

- 本地与公网浏览器：1440×1000 桌面、390×844 手机，检查内容顺序、无横向溢出、片段链接、独立对比滑块、方向键、缩放与重置、折叠区和手机浮条。普通动效、减少动效、无 JavaScript 均检查通过。
- 公网全部 11 个文件 SHA-256 与发布清单一致；www 首页同内容；嵌套错误资源返回产品自定义页且保持 HTTP 404。
- 重新通过 GitHub 核实 v1.2.0 非草稿、非预发布；安装包 481,309,207 字节，哈希与页面一致。
- 发布脚本 5 项测试通过：完整发布与备份（同时保护其他站点）、基线冲突拒绝、危险归档拒绝、切换失败回退、发布后异常回退。Ruff 全量检查与 mypy `app scripts`（65 个源文件）通过，网页 JavaScript 语法与 Git 空白检查通过。
- MyWeb `release-content.mjs --check` 通过，正式版本 r54、157 个文件。`build-static-first-batch.mjs --check` 首次因默认 Python 服务未就绪而失败；指定真实 Python 启动本地服务后，检查报多个既有全站静态批次过期。本轮未修改其模板、内容源或生成页面，不扩大到全站重新生成，不能声称该项检查通过。

浏览器与哈希证据保留于本地 `output/product-auto-review/`（不纳入 Git 或公开站点），包含桌面／手机截图、local-checks.json、online-checks.json、public-hashes.json 与发布清单。

## 发布与回退

新增 `scripts/deploy_product_site.py` 仅允许固定产品目录和明确资源清单。校验归档、上线前基线和候选文件后切换；保留原目录，失败恢复。未使用会同时切换其他站点的整轮脚本。

首次部署 `1792039203`，后续只为 404 的 base 路径修正再次部署 `1792039311`；最终缓存引用 `20261015p8`，404 样式同步。

公网验收发现历史文档中的自定义 404 尚未在服务器启用。本轮仅在现有产品 location 内加入 `error_page 404 /remove-number-plate/404.html;`，备份配置、通过 `nginx -t` 后 reload。404 页添加固定产品 base，确保多层不存在路径中的样式与回首页链接有效。

- **回到本轮之前的产品目录**：`/var/www/fangdian-products/remove-number-plate.before-1792039203`。
- 第二次备份 `/var/www/fangdian-products/remove-number-plate.before-1792039311` 为本轮中间状态，不是最初版本。
- 最终清单：`/opt/sitewide-visual-backups/rnp-product-1792039311/release.json`。
- Nginx 原配置：`/opt/sitewide-visual-backups/rnp-product-1792039203/nginx-paiche.before`；变更哈希：同目录 `nginx-change.json`。

回退时保留当前产品目录，再将首次旧目录换回正式路径；核对 Nginx 未有后续修改后，按需恢复原配置并通过检查后 reload。复验 HTTPS、文件哈希与错误路径。
