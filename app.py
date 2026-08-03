import streamlit as st
import yaml
import requests
import base64
import copy
from urllib.parse import unquote, parse_qs

st.set_page_config(page_title="Clash Meta 极速轻量订阅转换", page_icon="⚡", layout="wide")

st.title("⚡ Clash Meta 极速轻量分流转换工具")
st.caption("【零外部依赖】基于 Clash 本地 GeoIP/GeoSite 分流，秒级加载，节点零延迟损耗")

# ----------------- 1. 协议解析（补全优化参数） -----------------

def parse_ss_url(ss_url):
    try:
        if not ss_url.startswith("ss://"): return None
        main_part = ss_url[5:]
        name = "SS 节点"
        if "#" in main_part:
            main_part, name = main_part.split("#", 1)
            name = unquote(name)

        if "@" in main_part:
            userinfo, host_port = main_part.split("@", 1)
            if ":" not in userinfo:
                try: userinfo = base64.b64decode(userinfo + '==').decode('utf-8')
                except: pass
            cipher, password = userinfo.split(":", 1)
        else:
            try:
                decoded = base64.b64decode(main_part + '==').decode('utf-8')
                if "@" in decoded:
                    userinfo, host_port = decoded.split("@", 1)
                    cipher, password = userinfo.split(":", 1)
                else: return None
            except: return None

        if ":" not in host_port: return None
        server_port = host_port.split("?")[0]
        server, port = server_port.split(":", 1)

        return {
            "name": name, "type": "ss", "server": server,
            "port": int(port), "cipher": cipher, "password": password,
            "udp": True, "skip-cert-verify": True
        }
    except: return None

def parse_vless_url(vless_url):
    try:
        if not vless_url.startswith("vless://"): return None
        main_part = vless_url[8:]
        name = "VLESS 节点"
        if "#" in main_part:
            main_part, name = main_part.split("#", 1)
            name = unquote(name)

        if "@" not in main_part: return None
        uuid, host_port = main_part.split("@", 1)
        
        server_port, query_str = host_port.split("?", 1) if "?" in host_port else (host_port, "")
        if ":" not in server_port: return None
        server, port = server_port.split(":", 1)
        params = parse_qs(query_str)
        
        def get_p(k, default=""): return params.get(k, [default])[0]

        network, security = get_p("type", "tcp"), get_p("security", "")
        sni, fp = get_p("sni", get_p("peer", server)), get_p("fp", "chrome")

        proxy = {
            "name": name, "type": "vless", "server": server, "port": int(port),
            "uuid": uuid, "cipher": "auto", "udp": True,
            "tls": security in ["tls", "reality"],
            "skip-cert-verify": True,
            "servername": sni if security in ["tls", "reality"] else None,
            "client-fingerprint": fp if fp else "chrome"
        }

        if security == "reality":
            proxy["reality-opts"] = {}
            if get_p("pbk"): proxy["reality-opts"]["public-key"] = get_p("pbk")
            if get_p("sid"): proxy["reality-opts"]["short-id"] = get_p("sid")

        if network == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {"path": get_p("path", "/")}
            if get_p("host"): proxy["ws-opts"]["headers"] = {"Host": get_p("host")}
        elif network == "grpc":
            proxy["network"] = "grpc"
            proxy["grpc-opts"] = {"grpc-service-name": get_p("serviceName", "")}

        return {k: v for k, v in proxy.items() if v is not None}
    except: return None

def extract_proxies(raw_text):
    raw_text = raw_text.strip()
    if raw_text.startswith("http://") or raw_text.startswith("https://"):
        headers = {'User-Agent': 'ClashMeta/1.16.0 Subconverter'}
        resp = requests.get(raw_text, headers=headers, timeout=15)
        raw_text = resp.text.strip()

    try:
        decoded = base64.b64decode(raw_text + '===').decode('utf-8', errors='ignore')
        if any(proto in decoded for proto in ["vless://", "ss://", "vmess://", "proxies:"]):
            raw_text = decoded
    except: pass

    proxies = []
    try:
        parsed_yaml = yaml.safe_load(raw_text)
        if isinstance(parsed_yaml, dict) and "proxies" in parsed_yaml:
            return parsed_yaml["proxies"]
        elif isinstance(parsed_yaml, list) and isinstance(parsed_yaml[0], dict) and "type" in parsed_yaml[0]:
            return parsed_yaml
    except: pass

    for line in raw_text.splitlines():
        line = line.strip()
        if line.startswith("ss://"):
            p = parse_ss_url(line)
            if p: proxies.append(p)
        elif line.startswith("vless://"):
            p = parse_vless_url(line)
            if p: proxies.append(p)

    return proxies

# ----------------- 2. 主逻辑（零远程资源分流） -----------------

source_input = st.text_area("粘贴 JustMySocks 订阅链接 / SS / VLESS 节点：", height=200)

if st.button("🚀 生成本地零延迟配置文件", use_container_width=True):
    if not source_input.strip():
        st.error("请输入有效订阅或节点！")
    else:
        with st.spinner("生成中..."):
            proxies = extract_proxies(source_input)
            if not proxies:
                st.error("未能解析到节点，请检查输入格式。")
            else:
                node_names = [p["name"] for p in proxies]
                
                # 纯本地轻量配置，不带任何 rule-providers 下载项
                fast_config = {
                    "mixed-port": 7890,
                    "allow-lan": True,
                    "mode": "rule",
                    "log-level": "info",
                    "dns": {
                        "enable": True,
                        "enhanced-mode": "redir-host",
                        "nameserver": ["223.5.5.5", "119.29.29.29"]
                    },
                    "proxies": proxies,
                    "proxy-groups": [
                        {
                            "name": "🚀 节点选择",
                            "type": "select",
                            "proxies": ["📌 自动选择"] + node_names + ["🎯 直连"]
                        },
                        {
                            "name": "📌 自动选择",
                            "type": "url-test",
                            "url": "http://www.gstatic.com/generate_204",
                            "interval": 300,
                            "tolerance": 50,
                            "proxies": copy.deepcopy(node_names)
                        },
                        {
                            "name": "🎥 国外媒体",
                            "type": "select",
                            "proxies": ["🚀 节点选择", "📌 自动选择"] + node_names
                        },
                        {
                            "name": "🎯 直连",
                            "type": "select",
                            "proxies": ["DIRECT"]
                        }
                    ],
                    # 采用 Clash 内核自带的本地 GEO 数据库匹配，零加载时间
                    "rules": [
                        "GEOIP,LAN,🎯 直连",
                        "GEOSITE,cn,🎯 直连",
                        "GEOIP,CN,🎯 直连",
                        "GEOSITE,gfw,🚀 节点选择",
                        "GEOSITE,youtube,🎥 国外媒体",
                        "MATCH,🚀 节点选择"
                    ]
                }

                final_yaml = yaml.dump(fast_config, allow_unicode=True, sort_keys=False)
                st.success("✅ 配置文件已生成！已彻底移除远程依赖。")
                st.download_button(
                    label="💾 点击下载轻量级配置文件 (.yaml)",
                    data=final_yaml,
                    file_name="fast_clash_config.yaml",
                    mime="text/yaml",
                    use_container_width=True
                )
