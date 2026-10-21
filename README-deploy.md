# 本项目参考了 [free-dam-man/railway-anon-xray](https://github.com/free-dam-man/railway-anon-xray) 的思路，在此致谢。
# Railway + Xray 节点（v2rayN）：VMess+WS / VMess+XHTTP

两个协议各开一个 Railway 服务（Railway 每个服务只暴露一个 HTTP 端口；实测 Xray 的路径回落是精确匹配，
而 XHTTP 的请求路径后面会带会话后缀，所以同一端口无法按路径分流 WS 与 XHTTP）。
一个脚本 `gen_node.py` 同时生成两个服务的启动命令和两条 v2rayN 链接。只要一种协议就只给一个 `--*-domain`。

## 相比原版的改动

- **内层加密**：VLESS(encryption=none) → VMess。Railway 网关终结 TLS 后看到的是密文，看不到目的地。
- **屏蔽内网**：出站拒绝回环 / RFC1918 / CGNAT / 链路本地 / IPv6 ULA / `*.railway.internal`
  （实测：原配置能经节点读到节点本机的 127.0.0.1 服务，现配置读不到，公网不受影响）。
- **不写日志**：`loglevel none`，Railway 日志里不留目的地。
- **路径不再是公开常量**：随机 `URLPATH` 放环境变量，不再是仓库里的 `/tk-rail`。
- **XHTTP 用 packet-up + ALPN http/1.1**：实测在带缓冲的反向代理后，packet-up / auto 能通，stream-up / stream-one 不通；
  Xray 的 XHTTP 客户端在 TLS 下不设 ALPN 时默认按 h2 走，遇到只讲 HTTP/1.1 的网关会失败，所以默认强制 http/1.1。

## 部署

1. Railway 新建 Project，加两个 Service（可只加一个）：Docker Image 填 `teddysun/xray:<具体版本号>`。
   **不要用 latest**——去 Docker Hub 选一个具体 tag（需较新、支持 `xhttp` 传输的 Xray）。
   Xray 目前已把 WS 和 VMess 标为弃用（会在启动日志里警告），`latest` 哪天移除它们节点就起不来了。
2. 每个服务 Networking → Generate Domain。
3. 本地：`python3 gen_node.py --ws-domain <A域名> --xhttp-domain <B域名>`，生成 `out/`。
4. 每个服务：Variables 填 `out/<ws|xhttp>/variables.txt` 的 `UUID`、`URLPATH`；
   Settings → Custom Start Command 粘 `out/<ws|xhttp>/start-command.txt`。
5. 存活探针（`curl -s -i https://<域名>/<URLPATH>`）：
   - ws 服务：返回 **400** = Xray 存活。
   - xhttp 服务：返回 **404 且响应体为空** = Xray 存活；响应体是 `Application not found` = 域名背后没有活的部署。
   - 探针只能说明进程在，**能不能代理以拨测为准**（见下）。
6. v2rayN 导入：把 `out/links.txt` 每行从剪贴板导入，或用 `tools/sub_pack.py` 生成每条的二维码后
   「扫描屏幕上的二维码」。如果导入后 XHTTP 节点的传输协议/路径/模式显示不对，用 `out/client-vmess-xhttp.json`
   走 v2rayN 的「添加自定义配置服务器」，那份是完整的 Xray 客户端配置。

## 拨测

`tools/dial_test.py` 需要 xray 二进制（放 `tools/bin/xray` 或在 PATH 里；请从官方 release 下载并校验）：

    python3 tools/dial_test.py -f out/links.txt --out result.json

支持 vmess:// 和 vless://，传输 tcp/ws/grpc/xhttp。RTT 现在只汇报，不再默认判失败
（原版硬编码 800ms 会把健康的远端节点判死，和 README 自己的说明矛盾）；要判就加 `--rtt-limit 800`。
终端输出默认遮蔽 UUID；`--out` 文件含完整链接，权限 600，当机密处理。

## 机密清单

`links.txt`、`variables.txt`、`client-*.json`、`sub_pack` 的输出（订阅文件、二维码）都含 UUID 和路径。
别放公开仓库 / 公共网盘 / 在线二维码生成器；订阅文件的 Base64 不是加密。

## 没验证过的

- 没在真实的 Railway 网关上跑过（沙箱里用 nginx 模拟了 TLS 终结 + 请求/响应缓冲）。
  Railway 网关对 XHTTP 的实际行为需要你用拨测确认；不通就改用 `--only` 单 WS。
- 没在 v2rayN 里实际导入过。VMess 链接格式按 v2rayN 的 VMess 分享链接规范生成，XHTTP 的模式放在 `type` 字段
  （v2rayN 兼容生成器的惯例）；有问题用上面的自定义配置兜底。
- "Railway 看不到目的地"是 VMess 的协议设计保证，我没法在 Railway 端验证；它仍然知道你的客户端 IP、流量大小和时间。

# 本项目参考了 [free-dam-man/railway-anon-xray](https://github.com/free-dam-man/railway-anon-xray) 的思路，在此致谢。
