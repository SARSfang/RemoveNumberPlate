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
part = part.replace(
    "GitHub Release v1.0.1 发布时间 2026-08-17；仓库更早公开日未核实，此日期不代表首次公开发布",
    "GitHub Release v1.2.0 发布时间 2026-10-14；此日期不代表首次公开发布",
)
part = part.replace("v1.0.1 发布日", "v1.2.0 发布日").replace("v1.0.1 release", "v1.2.0 release")
part = part.replace(
    "用于汽车照片后期处理，可批量去除车牌。车牌检测、透视遮罩、纹理修复和人工复核均在本机完成。",
    "面向汽车摄影的离线车牌消除工具，支持多车牌识别、高清局部修复和人工复核。照片在本机处理，结果另存。",
)
part = part.replace(
    (
        "Offline batch licence-plate removal "
        "for automotive post-processing: dete"
        "ction, perspective masking, inpainti"
        "ng and review, all on one machine."
    ),
    (
        "Offline licence-plate removal for au"
        "tomotive photography, with multiple-"
        "plate detection, high-resolution loc"
        "al repair and manual review. Photos "
        "stay on your computer; results are s"
        "aved separately."
    ),
)
part = part.replace(
    "工具使用 ONNX Runtime 运行车牌检测和 LaMa 图像修复模型，"
    "按车牌透视轮廓修复遮挡区域的车身纹理。",
    "标准模式使用 ONNX Runtime 与 LaMa，高清模式增加 Big-LaMa 组件，按车牌透视轮廓进行局部修复。",
)
part = part.replace(
    (
        "plate detection and LaMa inpainting "
        "run under a single ONNX Runtime stac"
        "k, rebuilding body texture along eac"
        "h plate's perspective outline."
    ),
    (
        "standard processing uses ONNX Runtim"
        "e and LaMa, while high-resolution re"
        "pair uses a separate Big-LaMa compon"
        "ent. Repair follows each plate's per"
        "spective outline."
    ),
)
part = part.replace("v1.0.1 已发布", "v1.2.0 已发布").replace("v1.0.1 released", "v1.2.0 released")
part = replace(
    part,
    '      url: "https://github.com/SARSfang/RemoveNumberPlate",',
    (
        '      url: "https://github.com/SARSf'
        'ang/RemoveNumberPlate",\n      produc'
        'tUrl: "https://fangdian.xyz/remove-n'
        'umber-plate/",\n      productIntroZh:'
        ' "查看车牌消除前后与高清修复对比，了解功能、版本与使用方式。",\n  '
        '    productIntroEn: "See plate-remov'
        "al and high-resolution repair compar"
        "isons, features, versions and usage."
        '",'
    ),
)
part = part.replace(
    'stack: ["ONNX Runtime", "LaMa", "WebView2", "Python"]',
    'stack: ["ONNX Runtime", "LaMa / Big-LaMa", "WebView2", "Python"]',
)
changes[ROOT / "js/content-data.js"] = content[:start] + part + content[end:]

pages = read("js/pages.js")
pages = replace(
    pages,
    '    const problem = pick(item, "problemZh", "problemEn");',
    (
        "    const productUrl = String(item.p"
        'roductUrl || "").trim();\n    const p'
        'roductIntro = pick(item, "productInt'
        'roZh", "productIntroEn");\n    const '
        "productEntry = productUrl\n      ? `<"
        'div class="entry-product"><a class="'
        'entry-product-link" href="${esc(prod'
        'uctUrl)}" target="_blank" rel="noope'
        'ner noreferrer">${en ? "Explore the '
        'product" : "查看产品与实拍效果"} <span aria-h'
        'idden="true">↗</span></a><p>${esc(pr'
        'oductIntro)}</p></div>`\n      : "";\n'
        '    const problem = pick(item, "prob'
        'lemZh", "problemEn");'
    ),
)
pages = replace(
    pages,
    "          ${outbound}\n        </div>",
    "          ${outbound}\n          ${productEntry}\n        </div>",
)
pages = replace(
    pages,
    "    const shareUrl = entryShareUrl(id);",
    """    const productUrl = String(item.productUrl || "").trim();
    const productIntro = pick(item, "productIntroZh", "productIntroEn");
    const shareUrl = entryShareUrl(id);""",
)
pages = replace(
    pages,
    '        <div class="detail-link-row">\n          ${url && extLabel',
    (
        '        ${productUrl ? `<p class="de'
        'tail-product-intro">${esc(productInt'
        'ro)}</p>` : ""}\n        <div class="'
        'detail-link-row">\n          ${produc'
        'tUrl ? `<a class="button primary" hr'
        'ef="${esc(productUrl)}" target="_bla'
        'nk" rel="noopener noreferrer"><span '
        'class="lbl">${en ? "Explore the prod'
        'uct" : "查看产品与实拍效果"}</span><span clas'
        's="arr" aria-hidden="true">↗</span><'
        '/a>` : ""}\n          ${url && extLab'
        "el"
    ),
)
changes[ROOT / "js/pages.js"] = pages

css = read("css/pages.css")
css += (
    "\n/* Product introduction is attached"
    " to its existing project, not global"
    " navigation. */\n.entry-product {flex"
    "-basis:100%;min-width:0;padding-top:"
    "4px;}\n.entry-product-link {display:i"
    "nline-flex;align-items:center;gap:12"
    "px;min-height:44px;font-size:13px;fo"
    "nt-weight:600;color:var(--accent);}\n"
    ".entry-product-link:hover {text-deco"
    "ration:underline;text-underline-offs"
    "et:4px;}\n.entry-product-link:focus-v"
    "isible {outline:2px solid var(--acce"
    "nt);outline-offset:4px;}\n.entry-prod"
    "uct p,.detail-product-intro {font-si"
    "ze:12px;line-height:1.8;color:var(--"
    "text-aux);margin:0 0 10px;}\n.detail-"
    "product-intro {max-width:52ch;margin"
    ":0 0 14px;}\n"
)
changes[ROOT / "css/pages.css"] = css

home = read("paiche/web/src/pages/Home.jsx")
old = """            了解摄影师 ↗
          </a>
        </div>"""
new = (
    "            了解摄影师 ↗\n          </a>\n "
    '         <aside className="photograp'
    'her-product" aria-label="摄影后期工具">\n  '
    '          <p className="photographer'
    '-product-label">摄影后期工具 · 消除车牌</p>\n  '
    "          <p>本地离线去除照片中的车牌，支持多车牌处理、高清"
    "修复与人工复核，结果另存。个人及非商业用途可使用。</p>\n      "
    '      <a className="ghost-action pho'
    'tographer-product-link" href="https:'
    '//fangdian.xyz/remove-number-plate/"'
    ' target="_blank" rel="noopener noref'
    'errer">查看工具与实拍效果 <span aria-hidden="'
    'true">↗</span></a>\n          </aside'
    ">\n        </div>"
)
changes[ROOT / "paiche/web/src/pages/Home.jsx"] = replace(home, old, new)
home_css = read("paiche/web/src/styles/pages/home.css")
home_css += (
    "\n.photographer-product {margin-top:2"
    "4px;padding-top:20px;border-top:1px "
    "solid var(--border);max-width:62ch;}"
    "\n.photographer-product p.photographe"
    "r-product-label {font-size:13px;font"
    "-weight:600;color:var(--text-primary"
    ");margin:0 0 8px;}\n.photographer-pro"
    "duct p {font-size:12px;line-height:1"
    ".9;color:var(--text-secondary);margi"
    "n:0 0 8px;}\n.photographer-product-li"
    "nk {display:inline-flex;align-items:"
    "center;gap:12px;min-height:44px;font"
    "-size:12px;}\n"
)
changes[ROOT / "paiche/web/src/styles/pages/home.css"] = home_css

for path, text in changes.items():
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    print(path.relative_to(ROOT))
