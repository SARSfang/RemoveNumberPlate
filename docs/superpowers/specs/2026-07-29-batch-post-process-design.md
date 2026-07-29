# 子 spec 2：批量后处理（重命名 / 水印 / EXIF）

> 日期：2026-07-29
> 状态：待评审
> 版本：v0.3.0 子 spec 2
> 依赖：子 spec 1（监视文件夹）已实现；共用 BatchService 的处理完成钩子

---

## 1. 目标

车牌消除完成后，按用户配置的模板自动重命名输出文件、叠加水印、
填写 EXIF 元数据。后处理是可选的，默认关闭；启用后对每张完成图片
增量执行，不破坏原片和原始消除结果。

性能预算：单图后处理增量 ≤ 500ms。

---

## 2. 核心组件

```
PostProcessor (协调器)
   ├── NamingTemplate     解析 {client}_{seq:03}_{date}.{ext}
   ├── WatermarkRenderer  渲染文字 / 图片水印到图像
   └── ExifWriter         填入 EXIF / IPTC 字段，保留既有元数据
```

### 2.1 NamingTemplate

- 解析模板字符串，支持占位符：
  - `{client}`：客户名（来自项目预设，可为空）
  - `{seq:03}`：三位补零序号（批次内递增）
  - `{date}`：拍摄日期（从源文件 EXIF 读取，回退到文件 mtime）
  - `{original}`：原文件名（不含扩展名）
  - `{ext}`：原扩展名（含点）
- 序号冲突处理：目标文件已存在时序号自增直到不冲突
- 非法字符过滤（Windows 文件名禁用字符替换为下划线）
- 模板为空时保留默认命名 `{original}_clean{ext}`

### 2.2 WatermarkRenderer

- 文字水印：支持内容、字号、颜色、透明度、位置（9 宫格）
- 图片水印：支持图片路径、缩放比例、透明度、位置
- 字体回退：用户字体 → 系统默认字体 → Pillow 内置字体
- 基于 Pillow 绘制，不引入 OpenCV 依赖
- 水印图片处理完即从内存释放，不写入永久缓存

### 2.3 ExifWriter

- 基于 piexif（已在 requirements 中）写入 EXIF 字段
- 支持写入：Artist、Copyright、ImageDescription、UserComment
- 强制保留既有 EXIF（不破坏原片元数据）
- IPTC 字段暂不支持（piexif 不支持 IPTC，留给后续版本）
- 原子写入：临时文件 → 验证 → 重命名

### 2.4 PostProcessor

- 处理完成钩子，由 BatchService 在 item_finished 成功后调用
- 接收：源图路径、消除输出路径、配置、序号
- 输出：post_processed_output 路径（与原输出同目录）
- 异常处理：后处理失败不阻塞批处理，标记 warning 但保留原输出
- 幂等：对同一输出路径不重复后处理

---

## 3. 数据模型影响

### 3.1 settings.json

新增 `post_process_config` 字段：

```json
{
  "post_process_config": {
    "enabled": false,
    "naming_template": "{original}_clean{ext}",
    "watermark": {
      "enabled": false,
      "type": "text",
      "text": "",
      "font_size": 24,
      "color": "#FFFFFF",
      "opacity": 0.7,
      "position": "bottom-right",
      "image_path": null
    },
    "exif": {
      "enabled": false,
      "artist": "",
      "copyright": "",
      "description": ""
    }
  }
}
```

兼容性：缺失 `post_process_config` 字段时默认全禁用。

### 3.2 jobs.sqlite3

schema_version 从 5 升到 6，jobs 表新增 `post_processed_output` 列：

```sql
ALTER TABLE jobs ADD COLUMN post_processed_output TEXT;
```

兼容性：旧库自动迁移，旧任务的 `post_processed_output` 为 NULL。

---

## 4. 后端桥接扩展

`app/desktop.py` 新增方法：

- `get_post_process_config()` → 返回当前配置
- `set_post_process_config(config)` → 保存配置
- `preview_naming(template, sample_name)` → 返回预览文件名（前端实时预览）

后处理在 BatchService._finish_item 内部自动执行，不暴露单独的
API 方法。

---

## 5. 前端架构

- 设置页新增"批量后处理"区块（位于"监视文件夹"之后）
- 包含三个子区块：重命名、水印、EXIF
- 命名模板输入框带实时预览（调用 `preview_naming`）
- 水印位置选择器（9 宫格可视化）
- EXIF 字段输入框
- 全局启停开关

---

## 6. 测试边界

- NamingTemplate 解析单元测试（含中文 / 特殊字符 / 序号冲突）
- WatermarkRenderer 渲染测试（位置 / 透明度 / 字体回退）
- ExifWriter 元数据保留测试（不破坏既有 EXIF）
- PostProcessor 集成测试（完整处理 → 后处理 → 输出验证）
- settings.json 兼容性测试（缺失字段默认禁用）
- schema v5→v6 迁移测试

---

## 7. 隐私约束

- 水印图片不写入永久缓存，处理完即从内存释放
- 客户名（EXIF Artist / Copyright）视为敏感信息，诊断包不导出
- 全部后处理在本地完成，不引入任何网络请求
