import copy
import urllib.parse
import urllib.request
import base64
import streamlit as st
import yaml

st.set_page_config(
    page_title="Clash Meta (Mihomo) 本地 GEO 极速订阅转换",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Clash Meta (Mihomo) 本地 GEO 极速订阅转换")
st.caption("【节点 100% 原样保留】基于 Clash Meta 本地 GEO 数据库分流，零远程依赖，加载秒开")

# ==================== 1. 本地 GEO 规则架构配置 ====================

BASE_CONFIG = {
    "mixed-port": 7890,
    "allow-lan": True,
    "mode": "rule",
    "log-level": "info",
    "dns": {
        "enable": True,
        "enhanced-mode": "redir-host",
        "nameserver": ["223.5.5.5", "119.29.29.29"]
    }
}

# 使用 Clash Meta 内核自带的 GEO 数据库，无任何 rule-providers 远程下载，已移除 Bilibili 策略
LOCAL_GEO_RULES = [
    "GEOIP,LAN,🎯 直连",
    "GEOSITE,cn,🎯 直连",
    "GEOIP,CN,🎯 直连",
    "GEOSITE,gfw,🚀 节点选择",
    "GEOSITE,youtube,🎥 国外媒体",
    "GEOSITE,google,🌍 谷歌服务",
    "GEOSITE,telegram,📲 极简 Telegram",
    "MATCH,🎯 漏网之鱼"
]

# ==================== 2. 安全节点提取逻辑（防 IP 篡改 & 参数丢失） ====================

def parse_ss_url(ss_url):
    """解析 ss:// 链接，严格保留 server 地址"""
    try:
        if not ss_url.startswith("ss://"): return None
        main_part = ss_url[5:]
        name = "SS 节点"
        if "#" in main_part:
            main_part, name = main_part.split("#", 1)
            name = urllib.parse.unquote(name)

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
            "name": name, "type": "ss", "server": server.strip(),
            "port": int(port), "cipher": cipher, "password": password,
            "udp": True, "skip-cert-verify": True
        }
    except: return None

def parse_vless_url(vless_url):
    """解析 vless:// 链接，完整保留 REALITY/WS/gRPC/SNI 参数"""
    try:
        if not vless_url.startswith("vless://"): return None
        main_part = vless_url[8:]
        name = "VLESS 节点"
        if "#" in main_part:
            main_part, name = main_part.split("#", 1)
            name = urllib.parse.unquote(name)

        if "@" not in main_part: return None
        uuid, host_port = main_part.split("@", 1)
        
        server_port, query_str = host_port.split("?", 1) if "?" in host_port else (host_port, "")
        if ":" not in server_port: return None
        server, port = server_port.split(":", 1)
        params = urllib.parse.parse_qs(query_str)
        
        def get_p(k, default=""): return params.get(k, [default])[0]

        network, security = get_p("type", "tcp"), get_p("security", "")
        sni, fp = get_p("sni", get_p("peer", server)), get_p("fp", "chrome")
        pbk, sid = get_p("pbk", ""), get_p("sid", "")
        path, host = get_p("path", "/"), get_p("host", "")

        proxy = {
            "name": name, "type": "vless", "server": server.strip(), "port": int(port),
            "uuid": uuid, "cipher": "auto", "udp": True,
            "tls": security in ["tls", "reality"],
            "skip-cert-verify": True,
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

def extract_proxies_strictly(raw_text):
    """最严格的节点提取：对原 YAML 节点进行原样深拷贝，绝对零改动"""
    raw_text = raw_text.strip()
    
    # 1. 如果是 HTTP/HTTPS 链接，网络拉取
    if raw_text.startswith("http://") or raw_text.startswith("https://"):
        req = urllib.request.Request(raw_text, headers={'User-Agent': 'ClashMeta/1.16.0 Subconverter'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_text = resp.read().decode('utf-8').strip()

    # 2. 尝试 Base64 解码
    try:
        decoded = base64.b64decode(raw_text + '===').decode('utf-8', errors='ignore')
        if any(proto in decoded for proto in ["vless://", "ss://", "vmess://", "proxies:"]):
            raw_text = decoded
    except: pass

    raw_proxies = []

    # 3. 优先解析原生的 YAML/Clash 格式 (官方订阅原生数据)
    try:
        parsed_yaml = yaml.safe_load(raw_text)
        if isinstance(parsed_yaml, dict) and "proxies" in parsed_yaml:
            raw_proxies = parsed_yaml["proxies"]
        elif isinstance(parsed_yaml, list) and len(parsed_yaml) > 0 and isinstance(parsed_yaml[0], dict) and "type" in parsed_yaml[0]:
            raw_proxies = parsed_yaml
    except: pass

    # 4. 如果不是 YAML，再逐行解包 ss:// 和 vless://
    if not raw_proxies:
        for line in raw_text.splitlines():
            line = line.strip()
            if line.startswith("ss://"):
                p = parse_ss_url(line)
                if p: raw_proxies.append(p)
            elif line.startswith("vless://"):
                p = parse_vless_url(line)
                if p: raw_proxies.append(p)

    # 5. 【防御核心】原样深拷贝节点字典，绝对不允许篡改任何 server 或底层属性
    cleaned_proxies = []
    for p in raw_proxies:
        if not isinstance(p, dict): continue
        node = copy.deepcopy(p)
        if not node.get("server"): continue
        node["server"] = str(node["server"]).strip()
        cleaned_proxies.append(node)

    return cleaned_proxies

# ==================== 3. Streamlit 主程序 UI ====================

source_input = st.text_area(
    "粘贴 订阅 URL / SS/VLESS 链接 / YAML 配置文本：",
    height=220,
    placeholder="在此粘贴原订阅链接或节点数据..."
)

if st.button("🚀 生成本地 GEO 零加载延迟配置文件", use_container_width=True):
    if not source_input.strip():
        st.error("请粘贴订阅或节点内容！")
    else:
        with st.spinner("正在安全提取节点并组装 GEO 规则..."):
            proxies = extract_proxies_strictly(source_input)
            
            if not proxies:
                st.error("未能提取到有效节点！请检查粘贴内容。")
            else:
                # 确保节点的名称唯一（避免同名导致测速 Timeout）
                seen_names = set()
                node_names = []
                for p in proxies:
                    base_name = p.get("name", "节点")
                    unique_name = base_name
                    count = 1
                    while unique_name in seen_names:
                        unique_name = f"{base_name}_{count}"
                        count += 1
                    p["name"] = unique_name
                    seen_names.add(unique_name)
                    node_names.append(unique_name)

                st.success(f"成功导入 {len(node_names)} 个节点！已 100% 保持原始服务器信息。")

                # 构建最终配置（精简策略组）
                final_config = copy.deepcopy(BASE_CONFIG)
                final_config["proxies"] = proxies
                final_config["proxy-groups"] = [
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
                        "name": "🌍 谷歌服务",
                        "type": "select",
                        "proxies": ["🚀 节点选择", "📌 自动选择"] + node_names
                    },
                    {
                        "name": "📲 极简 Telegram",
                        "type": "select",
                        "proxies": ["🚀 节点选择", "📌 自动选择"] + node_names
                    },
                    {
                        "name": "🎯 漏网之鱼",
                        "type": "select",
                        "proxies": ["🚀 节点选择", "🎯 直连", "📌 自动选择"]
                    },
                    {
                        "name": "🎯 直连",
                        "type": "select",
                        "proxies": ["DIRECT"]
                    }
                ]
                final_config["rules"] = LOCAL_GEO_RULES

                final_yaml = yaml.dump(final_config, allow_unicode=True, sort_keys=False)

                st.write("---")
                st.subheader("🎉 制作完成")
                
                st.download_button(
                    label="💾 点击下载轻量 GEO 配置文件 (.yaml)",
                    data=final_yaml,
                    file_name="fast_clash_geo.yaml",
                    mime="text/yaml",
                    use_container_width=True
                )
                
                with st.expander("🔍 节点 Server 信息校验 (对照原始数据，验证是否被篡改)"):
                    st.json([{"name": p["name"], "server": p["server"], "port": p["port"]} for p in proxies])
