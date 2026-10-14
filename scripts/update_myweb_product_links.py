"""Add scoped, source-backed product links while preserving current MyWeb work."""
from pathlib import Path

ROOT = Path(r"E:\MyWeb")
URL = "https://fangdian.xyz/remove-number-plate/"
changes: dict[Path, str] = {}


def read(relative: str) -> str:
    path = ROOT / relative
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Expected one occurrence: {old[:90]}")
    return text.replace(old, new, 1)


content = read("js/content-data.js")
start = content.index('      id: "remove-number-plate",')
end = content.index('      tags: ["tool"],', start)
part = content[start:end]
part = part.replace('date: "2026-08-17"', 'date: "2026-10-14"')
part = part.replace('GitHub Release v1.0.1 发布时间 2026-08-17；仓库更早公开日未核实，此日期不代表首次公开发布', 'GitHub Release v1.2.0 发布时间 2026-10-14；此日期不代表首次公开发布')
part = part.replace('v1.0.1 发布日', 'v1.2.0 发布日').replace('v1.0.1 release', 'v1.2.0 release')
part = part.replace('用于汽车照片后期处理，可批量去除车牌。车牌检测、透视遮罩、纹理修复和人工复核均在本机完成。', '面向汽车摄影的离线车牌消除工具，支持多车牌识别、高清局部修复和人工复核。照片在本机处理，结果另存。')
part = part.replace('Offline batch licence-plate removal for automotive post-processing: detection, perspective masking, inpainting and review, all on one machine.', 'Offline licence-plate removal for automotive photography, with multiple-plate detection, high-resolution local repair and manual review. Photos stay on your computer; results are saved separately.')
part = part.replace('工具使用 ONNX Runtime 运行车牌检测和 LaMa 图像修复模型，按车牌透视轮廓修复遮挡区域的车身纹理。', '标准模式使用 ONNX Runtime 与 LaMa，高清模式增加 Big-LaMa 组件，按车牌透视轮廓进行局部修复。')
part = part.replace('plate detection and LaMa inpainting run under a single ONNX Runtime stack, rebuilding body texture along each plate\'s perspective outline.', 'standard processing uses ONNX Runtime and LaMa, while high-resolution repair uses a separate Big-LaMa component. Repair follows each plate\'s perspective outline.')
part = part.replace('v1.0.1 已发布', 'v1.2.0 已发布').replace('v1.0.1 released', 'v1.2.0 released')
part = replace(part, '      url: "https://github.com/SARSfang/RemoveNumberPlate",', '''      url: "https://github.com/SARSfang/RemoveNumberPlate",
      productUrl: "https://fangdian.xyz/remove-number-plate/",
      productIntroZh: "查看车牌消除前后与高清修复对比，了解功能、版本与使用方式。",
      productIntroEn: "See plate-removal and high-resolution repair comparisons, features, versions and usage.",''')
part = part.replace('stack: ["ONNX Runtime", "LaMa", "WebView2", "Python"]', 'stack: ["ONNX Runtime", "LaMa / Big-LaMa", "WebView2", "Python"]')
changes[ROOT / "js/content-data.js"] = content[:start] + part + content[end:]

pages = read("js/pages.js")
pages = replace(pages, '    const problem = pick(item, "problemZh", "problemEn");', '''    const productUrl = String(item.productUrl || "").trim();
    const productIntro = pick(item, "productIntroZh", "productIntroEn");
    const productEntry = productUrl
      ? `<div class="entry-product"><a class="entry-product-link" href="${esc(productUrl)}" target="_blank" rel="noopener noreferrer">${en ? "Explore the product" : "查看产品与实拍效果"} <span aria-hidden="true">↗</span></a><p>${esc(productIntro)}</p></div>`
      : "";
    const problem = pick(item, "problemZh", "problemEn");''')
pages = replace(pages, '          ${outbound}\n        </div>', '          ${outbound}\n          ${productEntry}\n        </div>')
pages = replace(pages, '    const shareUrl = entryShareUrl(id);', '''    const productUrl = String(item.productUrl || "").trim();
    const productIntro = pick(item, "productIntroZh", "productIntroEn");
    const shareUrl = entryShareUrl(id);''')
pages = replace(pages, '        <div class="detail-link-row">\n          ${url && extLabel', '''        ${productUrl ? `<p class="detail-product-intro">${esc(productIntro)}</p>` : ""}
        <div class="detail-link-row">
          ${productUrl ? `<a class="button primary" href="${esc(productUrl)}" target="_blank" rel="noopener noreferrer"><span class="lbl">${en ? "Explore the product" : "查看产品与实拍效果"}</span><span class="arr" aria-hidden="true">↗</span></a>` : ""}
          ${url && extLabel''')
changes[ROOT / "js/pages.js"] = pages

css = read("css/pages.css")
css += '''
/* Product introduction is attached to its existing project, not global navigation. */
.entry-product {flex-basis:100%;min-width:0;padding-top:4px;}
.entry-product-link {display:inline-flex;align-items:center;gap:12px;min-height:44px;font-size:13px;font-weight:600;color:var(--accent);}
.entry-product-link:hover {text-decoration:underline;text-underline-offset:4px;}
.entry-product-link:focus-visible {outline:2px solid var(--accent);outline-offset:4px;}
.entry-product p,.detail-product-intro {font-size:12px;line-height:1.8;color:var(--text-aux);margin:0 0 10px;}
.detail-product-intro {max-width:52ch;margin:0 0 14px;}
'''
changes[ROOT / "css/pages.css"] = css

home = read("paiche/web/src/pages/Home.jsx")
old = '''            了解摄影师 ↗
          </a>
        </div>'''
new = '''            了解摄影师 ↗
          </a>
          <aside className="photographer-product" aria-label="摄影后期工具">
            <p className="photographer-product-label">摄影后期工具 · 消除车牌</p>
            <p>本地离线去除照片中的车牌，支持多车牌处理、高清修复与人工复核，结果另存。个人及非商业用途可使用。</p>
            <a className="ghost-action photographer-product-link" href="https://fangdian.xyz/remove-number-plate/" target="_blank" rel="noopener noreferrer">查看工具与实拍效果 <span aria-hidden="true">↗</span></a>
          </aside>
        </div>'''
changes[ROOT / "paiche/web/src/pages/Home.jsx"] = replace(home, old, new)
home_css = read("paiche/web/src/styles/pages/home.css")
home_css += '''
.photographer-product {margin-top:24px;padding-top:20px;border-top:1px solid var(--border);max-width:62ch;}
.photographer-product p.photographer-product-label {font-size:13px;font-weight:600;color:var(--text-primary);margin:0 0 8px;}
.photographer-product p {font-size:12px;line-height:1.9;color:var(--text-secondary);margin:0 0 8px;}
.photographer-product-link {display:inline-flex;align-items:center;gap:12px;min-height:44px;font-size:12px;}
'''
changes[ROOT / "paiche/web/src/styles/pages/home.css"] = home_css

for path, text in changes.items():
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    print(path.relative_to(ROOT))
