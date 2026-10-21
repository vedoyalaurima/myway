#!/usr/bin/env python3
"""Hardened Railway nodes for v2rayN: start-commands + import links.

Two independent Railway services, one protocol each (Railway exposes ONE HTTP
port per service and Xray cannot split WS and XHTTP on one port - XHTTP
requests carry a session suffix on the path, Xray's path-fallback is exact-match):

    service "ws"     VMess + WebSocket   -> vmess:// link
    service "xhttp"  VMess + XHTTP       -> vmess:// link   (packet-up mode)

Both use VMess, so the payload is encrypted *inside* Railway's TLS tunnel and
the gateway cannot read destinations.  Loopback / private / Railway-internal
destinations are blocked on the way out.  Logging is off.

Everything is generated locally; nothing is sent anywhere.

  # after creating the service(s) and generating their domains:
  python3 gen_node.py --ws-domain a.up.railway.app --xhttp-domain b.up.railway.app
  # only one protocol:
  python3 gen_node.py --xhttp-domain b.up.railway.app
  # re-create links later from saved values:
  python3 gen_node.py --xhttp-domain b... --uuid <U> --xhttp-path <P>

Output (./out/, private perms):
  ws/start-command.txt  ws/variables.txt        paste into the "ws" service
  xhttp/start-command.txt xhttp/variables.txt   paste into the "xhttp" service
  links.txt             v2rayN import links     (SECRET: contains the UUID)
  client-*.json         full Xray client configs (v2rayN "custom config" fallback)
"""
import argparse, base64, json, os, secrets, sys, uuid as uuidlib

PRIVATE_CIDRS = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                 "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7",
                 "fe80::/10"]


def build_server_config(kind):
    """Server config as a dict; $PORT/$UUID/$URLPATH are filled by the shell."""
    stream = ({"network": "ws", "wsSettings": {"path": "/@URLPATH@"}}
              if kind == "ws" else
              {"network": "xhttp", "xhttpSettings": {"path": "/@URLPATH@"}})
    return {
        "log": {"loglevel": "none", "access": "none"},
        "inbounds": [{"tag": "in", "port": "@PORT@", "protocol": "vmess",
                      "settings": {"clients": [{"id": "@UUID@"}]},
                      "streamSettings": stream}],
        "outbounds": [{"protocol": "freedom", "tag": "direct"},
                      {"protocol": "blackhole", "tag": "block"}],
        "routing": {"domainStrategy": "IPOnDemand", "rules": [
            {"type": "field", "ip": PRIVATE_CIDRS, "outboundTag": "block"},
            {"type": "field", "domain": ["domain:railway.internal"],
             "outboundTag": "block"}]},
    }


def start_command(kind):
    s = json.dumps(build_server_config(kind), separators=(",", ":"))
    s = s.replace('"@PORT@"', "$PORT")
    for name in ("UUID", "URLPATH"):
        s = s.replace(f"@{name}@", f"${name}")
    if any(c in s for c in "'`\\"):
        sys.exit("internal error: config contains a char unsafe for sh -c")
    s = s.replace('"', '\\"')
    return ("sh -c 'echo \"" + s + "\" > /tmp/c.json; "
            "xray run -c /tmp/c.json'")


def _b64(d):
    return base64.b64encode(json.dumps(d, ensure_ascii=False,
                                       separators=(",", ":")).encode()).decode()


def vmess_link(kind, domain, uuid_, path, name, xhttp_mode="packet-up",
               xhttp_alpn="http/1.1"):
    """v2rayN 'vmess://base64(json)' (v2 schema).  For xhttp, 'type' carries
    the XHTTP mode - the convention v2rayN-compatible generators use."""
    d = {"v": "2", "ps": name, "add": domain, "port": "443", "id": uuid_,
         "aid": "0", "scy": "auto", "net": kind, "type": "none",
         "host": domain, "path": "/" + path, "tls": "tls", "sni": domain,
         "alpn": "", "fp": "chrome"}
    if kind == "xhttp":
        d["type"] = xhttp_mode
        d["alpn"] = xhttp_alpn
    return "vmess://" + _b64(d)


def client_config(kind, domain, uuid_, path, xhttp_mode="packet-up",
                  socks_port=10808, addr=None, port=443, tls=True,
                  xhttp_alpn="http/1.1"):
    ss = {"network": kind}
    if tls:
        ss["security"] = "tls"
        ss["tlsSettings"] = {"serverName": domain, "fingerprint": "chrome"}
        if kind == "xhttp":
            # Xray's XHTTP client assumes HTTP/2 over TLS when no ALPN is set;
            # a gateway that only speaks HTTP/1.1 then breaks it (tested).
            ss["tlsSettings"]["alpn"] = xhttp_alpn.split(",")
    if kind == "ws":
        ss["wsSettings"] = {"path": "/" + path, "headers": {"Host": domain}}
    else:
        ss["xhttpSettings"] = {"path": "/" + path, "host": domain,
                               "mode": xhttp_mode}
    return {"log": {"loglevel": "warning"},
            "inbounds": [{"listen": "127.0.0.1", "port": socks_port,
                          "protocol": "socks", "settings": {"udp": True}}],
            "outbounds": [{"protocol": "vmess", "settings": {"vnext": [{
                "address": addr or domain, "port": port,
                "users": [{"id": uuid_, "security": "auto"}]}]},
                "streamSettings": ss}]}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws-domain", help="domain of the VMess+WS service")
    ap.add_argument("--xhttp-domain", help="domain of the VMess+XHTTP service")
    ap.add_argument("--uuid"); ap.add_argument("--ws-path")
    ap.add_argument("--xhttp-path")
    ap.add_argument("--xhttp-mode", default="packet-up",
                    choices=["packet-up", "auto"],
                    help="packet-up (default) works behind buffering gateways; "
                         "stream-up/stream-one need full-duplex streaming and "
                         "failed behind a buffering proxy in testing")
    ap.add_argument("--xhttp-alpn", default="http/1.1", choices=["http/1.1", "h2"],
                    help="ALPN the XHTTP client offers. http/1.1 (default) works "
                         "through any gateway; h2 only if the gateway speaks it")
    ap.add_argument("--name", default="Railway")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    if not (a.ws_domain or a.xhttp_domain):
        ap.error("give --ws-domain and/or --xhttp-domain")

    u = a.uuid or str(uuidlib.uuid4())
    os.makedirs(a.out, exist_ok=True); os.chmod(a.out, 0o700)

    def write(rel, text, secret=True):
        p = os.path.join(a.out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(p, 0o600 if secret else 0o644)

    clean = lambda d: d.replace("https://", "").strip("/")
    links = []
    for kind, dom, given in (("ws", a.ws_domain, a.ws_path),
                             ("xhttp", a.xhttp_domain, a.xhttp_path)):
        if not dom:
            continue
        dom, path = clean(dom), given or secrets.token_urlsafe(9)
        write(f"{kind}/start-command.txt", start_command(kind) + "\n", secret=False)
        write(f"{kind}/variables.txt", f"UUID={u}\nURLPATH={path}\n")
        links.append(vmess_link(kind, dom, u, path, f"{a.name}-vmess-{kind}",
                                a.xhttp_mode, a.xhttp_alpn))
        write(f"client-vmess-{kind}.json", json.dumps(
            client_config(kind, dom, u, path, a.xhttp_mode,
                          xhttp_alpn=a.xhttp_alpn), indent=2))
    write("links.txt", "\n".join(links) + "\n")
    print(f"[OK] wrote {a.out}/ - links.txt, variables.txt and client-*.json "
          "contain your UUID: keep them private.")


if __name__ == "__main__":
    main()
