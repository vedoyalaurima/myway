#!/usr/bin/env python3
"""v2rayN 订阅/二维码打包（纯本地，不联网）。

输入目录里每个方案一个 <方案名>.txt（每行一条 vmess:// 或 vless:// 连接串）。
输出：
  <方案名>-<序号>-qr.png          每条连接串一张二维码
                                   → v2rayN：服务器 → 扫描屏幕上的二维码
  <方案名>-sub-<令牌>.txt         Base64 订阅文件（v2rayN 标准订阅格式）
  <方案名>-sub-<令牌>-qr.png      订阅 URL 的二维码（仅在给了 --url-base 时生成）
                                   → v2rayN：订阅分组 → 添加分组，URL 填进去

⚠ Base64 不是加密：订阅文件里就是明文的 UUID。托管它的地址必须是私有的、
  不可猜的（所以文件名默认带随机令牌；--no-token 可关闭），不要放进公开仓库、
  公共网盘或粘贴站。个人使用更稳妥的做法是不托管：直接用每条连接串的二维码，
  或在 v2rayN 里「从剪贴板导入批量URL」。

依赖（脚本不会替你联网安装，请自己装）：  pip install qrcode pillow

用法：
  python3 sub_pack.py --in links/ --out dist/
  python3 sub_pack.py --in links/ --out dist/ --url-base https://你的私有地址/path
"""
import argparse
import base64
import os
import secrets
import sys


def load_qrcode():
    try:
        import qrcode
        return qrcode
    except ImportError:
        sys.exit("缺少 qrcode / pillow。请先手动安装：pip install qrcode pillow")


def build_sub_payload(uris):
    """连接串换行拼接 → Base64（v2rayN 订阅格式）。"""
    return base64.b64encode("\n".join(uris).encode("utf-8")).decode("utf-8")


def save_qr(qrcode, text, path):
    qr = qrcode.QRCode(box_size=8, border=3,
                       error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    if min(img.size) < 300:
        k = (300 + min(img.size) - 1) // min(img.size)
        img = img.resize((img.size[0] * k, img.size[1] * k))
    img.save(path)
    os.chmod(path, 0o600)
    return img.size


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser(description="v2rayN 订阅/二维码打包")
    ap.add_argument("--in", dest="indir", required=True,
                    help="输入目录，每方案一个 <方案名>.txt")
    ap.add_argument("--out", dest="outdir", required=True, help="输出目录")
    ap.add_argument("--url-base", default=None,
                    help="订阅文件托管的基地址（私有、HTTPS）；给了才生成订阅 URL 二维码")
    ap.add_argument("--no-token", action="store_true",
                    help="订阅文件名不加随机令牌（不推荐：文件名可被猜到）")
    args = ap.parse_args()

    qrcode = load_qrcode()
    os.makedirs(args.outdir, exist_ok=True)
    os.chmod(args.outdir, 0o700)

    names = sorted(f[:-4] for f in os.listdir(args.indir) if f.endswith(".txt"))
    if not names:
        sys.exit("输入目录里没有 .txt 文件")

    for name in names:
        with open(os.path.join(args.indir, name + ".txt"), encoding="utf-8") as f:
            uris = [ln.strip() for ln in f
                    if ln.strip() and not ln.strip().startswith("#")]
        if not uris:
            print(f"[!] {name}.txt 为空，跳过")
            continue

        for i, u in enumerate(uris, 1):
            png = os.path.join(args.outdir, f"{name}-{i}-qr.png")
            w, h = save_qr(qrcode, u, png)
            print(f"[OK] {png}（{w}x{h}）")

        token = "" if args.no_token else "-" + secrets.token_urlsafe(12)
        sub_name = f"{name}-sub{token}.txt"
        write_private(os.path.join(args.outdir, sub_name),
                      build_sub_payload(uris) + "\n")
        print(f"[OK] {sub_name}（{len(uris)} 条，含明文 UUID，勿放公开位置）")

        if args.url_base:
            sub_url = f"{args.url_base.rstrip('/')}/{sub_name}"
            png = os.path.join(args.outdir, f"{name}-sub{token}-qr.png")
            save_qr(qrcode, sub_url, png)
            print(f"[OK] 订阅 URL：{sub_url}\n     二维码：{png}")


if __name__ == "__main__":
    main()
