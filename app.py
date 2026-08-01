import streamlit as st
import yaml
import requests
import base64
import copy
from urllib.parse import unquote, parse_qs

st.set_page_config(
    page_title="Clash Meta (Mihomo) 终极全能订阅转换",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Clash Meta (Mihomo) 精准分流转换工具")
st.caption("已完美修复自动选择逻辑、默认节点继承以及 B站/国内直连策略")

# ==================== 1. 各协议解析引擎 ====================

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
            "port": int(port), "cipher": cipher, "password": password, "udp": True
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
        pbk, sid = get_p("pbk", ""), get_p("sid", "")
        path, host = get_p("path", "/"), get_p("host", "")

        proxy = {
            "name": name, "type": "vless", "server": server, "port": int(port),
            "uuid": uuid, "cipher": "auto", "udp": True,
            "tls": security in ["tls", "reality"],
            "servername": sni if security in ["tls", "reality"] else None,
            "client-fingerprint": fp if fp else "chrome"
        }

        if security == "reality":
            proxy["reality-opts"] = {}
            if pbk: proxy["reality-opts"]["public-key"] = pbk
            if sid: proxy["reality-opts"]["short-id"] = sid

        if network == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {"path": path}
            if host: proxy["ws-opts"]["headers"] = {"Host": host}
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
        elif isinstance(parsed_yaml, list) and len(parsed_yaml) > 0 and isinstance(parsed_yaml[0], dict) and "type" in parsed_yaml[0]:
            return parsed_yaml
    except: pass

    for line in raw_text.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith("ss://"):
            p = parse_ss_url(line)
            if p: proxies.append(p)
        elif line.startswith("vless://"):
            p = parse_vless_url(line)
            if p: proxies.append(p)

    return proxies

# ==================== 2. 主程序逻辑 ====================

source_input = st.text_area(
    "粘贴 机场订阅 URL / SS/VLESS 链接 / YAML 配置文本：",
    height=250,
    placeholder="在此粘贴节点数据或链接..."
)

if st.button("🚀 生成优化版 Clash 配置文件", use_container_width=True):
    if not source_input.strip():
        st.error("请输入有效的订阅链接或节点！")
    else:
        with st.spinner("正在精准构建策略组..."):
            proxies = extract_proxies(source_input)
            
            if not proxies:
                st.error("未找到有效的代理节点！请检查粘贴内容。")
            else:
                # 节点去重与重命名
                node_names = []
                for idx, p in enumerate(proxies):
                    if "name" not in p or not p["name"]:
                        p["name"] = f"节点-{idx+1}"
                    base_name = p["name"]
                    count = 1
                    while p["name"] in node_names:
                        p["name"] = f"{base_name}_{count}"
                        count += 1
                    node_names.append(p["name"])

                st.success(f"成功提取 {len(node_names)} 个有效节点！")

                # 构建科学、严谨的 ACL4SSR 策略组结构
                final_config = {
                    "mixed-port": 7890,
                    "allow-lan": True,
                    "mode": "rule",
                    "log-level": "info",
                    "external-controller": "127.0.0.1:9090",
                    "dns": {
                        "enable": True,
                        "enhanced-mode": "redir-host",
                        "nameserver": ["223.5.5.5", "119.29.29.29", "1.1.1.1"]
                    },
                    "proxies": proxies,
                    "proxy-groups": [
                        # 1. 核心选择组：第一项为“📌 自动选择”，确保默认选中最快节点；随后跟具体的节点，最后支持手选直连/拦截
                        {
                            "name": "🚀 节点选择",
                            "type": "select",
                            "proxies": ["📌 自动选择"] + node_names + ["🎯 直连", "🛑 拦截"]
                        },
                        # 2. 自动选择组：【关键修正】只包含真实节点列表，绝对不含 DIRECT，按延迟延迟自动切最低者
                        {
                            "name": "📌 自动选择",
                            "type": "url-test",
                            "url": "http://www.gstatic.com/generate_204",
                            "interval": 300,
                            "tolerance": 50,
                            "proxies": copy.deepcopy(node_names)
                        },
                        # 3. 哔哩哔哩：【关键修正】默认第一项就是“🎯 直连”，不需要走代理；备选方案提供节点选择
                        {
                            "name": "🎬 哔哩哔哩",
                            "type": "select",
                            "proxies": ["🎯 直连", "🚀 节点选择"]
                        },
                        # 4. 其他业务/流媒体策略组：【关键修正】默认第一项全为“🚀 节点选择”，实现自动继承主节点的选线逻辑
                        {
                            "name": "🎥 国外媒体",
                            "type": "select",
                            "proxies": ["🚀 节点选择", "📌 自动选择", "🎯 直连"] + node_names
                        },
                        {
                            "name": "🌍 谷歌服务",
                            "type": "select",
                            "proxies": ["🚀 节点选择", "📌 自动选择", "🎯 直连"] + node_names
                        },
                        {
                            "name": "📲 极简 Telegram",
                            "type": "select",
                            "proxies": ["🚀 节点选择", "📌 自动选择", "🎯 直连"] + node_names
                        },
                        {
                            "name": "🛑 广告拦截",
                            "type": "select",
                            "proxies": ["🛑 拦截", "🎯 直连", "🚀 节点选择"]
                        },
                        {
                            "name": "🎯 漏网之鱼",
                            "type": "select",
                            "proxies": ["🚀 节点选择", "🎯 直连", "📌 自动选择"] + node_names
                        },
                        # 5. 基础基础兜底组
                        {
                            "name": "🎯 直连",
                            "type": "select",
                            "proxies": ["DIRECT"]
                        },
                        {
                            "name": "🛑 拦截",
                            "type": "select",
                            "proxies": ["REJECT"]
                        }
                    ],
                    "rules": [
                        "RULE-SET,LocalAreaNetwork,🎯 直连",
                        "RULE-SET,UnBan,🎯 直连",
                        "RULE-SET,BanAD,🛑 广告拦截",
                        "RULE-SET,Bilibili,🎬 哔哩哔哩",
                        "RULE-SET,Google,🌍 谷歌服务",
                        "RULE-SET,Telegram,📲 极简 Telegram",
                        "GEOIP,CN,🎯 直连",
                        "MATCH,🎯 漏网之鱼"
                    ],
                    "rule-providers": {
                        "LocalAreaNetwork": {
                            "type": "http",
                            "behavior": "domain",
                            "url": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/LocalAreaNetwork.list",
                            "path": "./rules/LocalAreaNetwork.list",
                            "interval": 86400
                        },
                        "UnBan": {
                            "type": "http",
                            "behavior": "domain",
                            "url": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/UnBan.list",
                            "path": "./rules/UnBan.list",
                            "interval": 86400
                        },
                        "BanAD": {
                            "type": "http",
                            "behavior": "domain",
                            "url": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/BanAD.list",
                            "path": "./rules/BanAD.list",
                            "interval": 86400
                        },
                        "Bilibili": {
                            "type": "http",
                            "behavior": "domain",
                            "url": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/Ruleset/Bilibili.list",
                            "path": "./rules/Bilibili.list",
                            "interval": 86400
                        },
                        "Google": {
                            "type": "http",
                            "behavior": "domain",
                            "url": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/Google.list",
                            "path": "./rules/Google.list",
                            "interval": 86400
                        },
                        "Telegram": {
                            "type": "http",
                            "behavior": "domain",
                            "url": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/Telegram.list",
                            "path": "./rules/Telegram.list",
                            "interval": 86400
                        }
                    }
                }

                # 输出标准的 YAML 文本
                final_yaml = yaml.dump(final_config, allow_unicode=True, sort_keys=False)

                st.write("---")
                st.subheader("🎉 完美转换完成！已校准默认选项逻辑")
                
                st.download_button(
                    label="💾 点击下载配置文件 (clash_meta_acl4ssr.yaml)",
                    data=final_yaml,
                    file_name="clash_meta_acl4ssr.yaml",
                    mime="text/yaml",
                    use_container_width=True
                )
                
                st.write("### 核心策略默认选项状态预览：")
                st.json({
                    "🚀 节点选择 (默认激活)": final_config["proxy-groups"][0]["proxies"][0],
                    "📌 自动选择 (节点池大小)": len(final_config["proxy-groups"][1]["proxies"]),
                    "🎬 哔哩哔哩 (默认激活)": final_config["proxy-groups"][2]["proxies"][0],
                    "🎥 国外媒体 (默认激活)": final_config["proxy-groups"][3]["proxies"][0],
                    "🌍 谷歌服务 (默认激活)": final_config["proxy-groups"][4]["proxies"][0]
                })
