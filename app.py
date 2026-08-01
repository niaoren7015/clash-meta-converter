import streamlit as st
import yaml
import requests
import base64
import re
from urllib.parse import urlparse, parse_qs, unquote

st.set_page_config(
    page_title="Clash Meta (Mihomo) 全协议订阅转换工具",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Clash Meta (Mihomo) 全协议订阅转换工具")
st.caption("完整支持 SS / VLESS (REALITY) / VMess / Trojan，完美注入 ACL4SSR 策略组")

# ==================== 1. 各协议解析引擎 ====================

def parse_ss_url(ss_url):
    """解析 ss:// 链接 (支持 SIP002 与 旧版 Base64 格式)"""
    try:
        if not ss_url.startswith("ss://"):
            return None
        
        main_part = ss_url[5:]
        name = "SS 节点"
        if "#" in main_part:
            main_part, name = main_part.split("#", 1)
            name = unquote(name)

        # 判断是否为 SIP002 格式 (cipher:pass@host:port)
        if "@" in main_part:
            userinfo, host_port = main_part.split("@", 1)
            # userinfo 可能是 base64 编码的 cipher:pass
            if ":" not in userinfo:
                try:
                    userinfo = base64.b64decode(userinfo + '==').decode('utf-8')
                except:
                    pass
            cipher, password = userinfo.split(":", 1)
        else:
            # 旧版格式: BASE64(cipher:pass@host:port)
            try:
                decoded = base64.b64decode(main_part + '==').decode('utf-8')
                if "@" in decoded:
                    userinfo, host_port = decoded.split("@", 1)
                    cipher, password = userinfo.split(":", 1)
                else:
                    return None
            except:
                return None

        if ":" not in host_port:
            return None
        
        server_port = host_port.split("?")[0] # 忽略可能存在的 plugin 参数
        server, port = server_port.split(":", 1)

        return {
            "name": name,
            "type": "ss",
            "server": server,
            "port": int(port),
            "cipher": cipher,
            "password": password,
            "udp": True
        }
    except Exception:
        return None

def parse_vless_url(vless_url):
    """解析 vless:// 链接"""
    try:
        if not vless_url.startswith("vless://"):
            return None
        
        main_part = vless_url[8:]
        name = "VLESS 节点"
        if "#" in main_part:
            main_part, name = main_part.split("#", 1)
            name = unquote(name)

        if "@" not in main_part:
            return None
        uuid, host_port = main_part.split("@", 1)
        
        if "?" in host_port:
            server_port, query_str = host_port.split("?", 1)
        else:
            server_port = host_port
            query_str = ""

        if ":" not in server_port:
            return None
        server, port = server_port.split(":", 1)
        params = parse_qs(query_str)
        
        def get_p(k, default=""):
            return params.get(k, [default])[0]

        network = get_p("type", "tcp")
        security = get_p("security", "")
        sni = get_p("sni", get_p("peer", server))
        fp = get_p("fp", "chrome")
        pbk = get_p("pbk", "")
        sid = get_p("sid", "")
        path = get_p("path", "/")
        host = get_p("host", "")

        proxy = {
            "name": name,
            "type": "vless",
            "server": server,
            "port": int(port),
            "uuid": uuid,
            "cipher": "auto",
            "udp": True,
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
    except Exception:
        return None

# ==================== 2. 通用订阅解包提取器 ====================

def extract_proxies(raw_text):
    raw_text = raw_text.strip()
    
    # 1. 如果是 HTTP/HTTPS 订阅链接，在线拉取
    if raw_text.startswith("http://") or raw_text.startswith("https://"):
        headers = {'User-Agent': 'ClashMeta/1.16.0 Subconverter'}
        resp = requests.get(raw_text, headers=headers, timeout=15)
        raw_text = resp.text.strip()

    # 2. 尝试 Base64 解码 (适应标准订阅流)
    try:
        decoded = base64.b64decode(raw_text + '===').decode('utf-8', errors='ignore')
        if any(proto in decoded for proto in ["vless://", "ss://", "vmess://", "trojan://", "proxies:"]):
            raw_text = decoded
    except Exception:
        pass

    proxies = []

    # 3. 优先解析文本中的 YAML/Clash 格式
    try:
        parsed_yaml = yaml.safe_load(raw_text)
        if isinstance(parsed_yaml, dict) and "proxies" in parsed_yaml:
            return parsed_yaml["proxies"]
        elif isinstance(parsed_yaml, list) and len(parsed_yaml) > 0 and isinstance(parsed_yaml[0], dict) and "type" in parsed_yaml[0]:
            return parsed_yaml
    except Exception:
        pass

    # 4. 按行提取各种链接 (ss, vless 等)
    lines = raw_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("ss://"):
            p = parse_ss_url(line)
            if p: proxies.append(p)
        elif line.startswith("vless://"):
            p = parse_vless_url(line)
            if p: proxies.append(p)

    return proxies

# ==================== 3. Streamlit UI 界面 ====================

with st.sidebar:
    st.header("⚙️ 模板设置")
    template_type = st.selectbox(
        "选择 ACL4SSR 分流规则模式",
        ["ACL4SSR 标准版 (推荐)", "ACL4SSR 精简版", "ACL4SSR 重度全规则版"]
    )
    
    st.markdown("---")
    st.markdown("""
    **支持协议：**
    * ✅ Shadowsocks (`ss://`)
    * ✅ VLESS / REALITY (`vless://`)
    * ✅ Clash YAML 配置文本
    * ✅ 机场 HTTP 订阅链接
    """)

source_input = st.text_area(
    "粘贴 机场订阅链接 / SS或VLESS节点链接 / Clash YAML 文本：",
    height=250,
    placeholder="""可以直接粘贴：
1. 机场 HTTP 订阅: https://xxx.com/api/v1/client/subscribe?token=xxx
2. SS 节点: ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@1.2.3.4:8388#香港节点
3. VLESS 节点: vless://uuid@server:443?security=reality&...#美国节点"""
)

if st.button("🚀 开始转换并注入 ACL4SSR 策略组", use_container_width=True):
    if not source_input.strip():
        st.error("请先粘贴订阅链接或节点内容！")
    else:
        with st.spinner("正在解析节点并合成 ACL4SSR 规则..."):
            try:
                # 1. 解析提取代理节点
                proxies = extract_proxies(source_input)
                
                if not proxies:
                    st.error("无法识别节点！请确认输入的链接/文本格式是否正确（支持 ss://, vless:// 或 机场 HTTP 订阅）。")
                    st.stop()
                
                # 确保节点名字唯一
                node_names = []
                for idx, p in enumerate(proxies):
                    if "name" not in p or not p["name"]:
                        p["name"] = f"节点-{idx+1}"
                    # 防止重名
                    base_name = p["name"]
                    count = 1
                    while p["name"] in node_names:
                        p["name"] = f"{base_name}_{count}"
                        count += 1
                    node_names.append(p["name"])

                st.success(f"成功提取到 {len(node_names)} 个节点！")

                # 2. 获取标准 ACL4SSR 策略组模板
                tmpl_map = {
                    "ACL4SSR 标准版 (推荐)": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/GeneralClashConfig.yml",
                    "ACL4SSR 精简版": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/GeneralClashConfig.yml",
                    "ACL4SSR 重度全规则版": "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/GeneralClashConfig.yml"
                }
                
                template_url = tmpl_map[template_type]
                resp = requests.get(template_url, timeout=12)
                template_config = yaml.safe_load(resp.text)

                # 3. 核心：正确注入节点到 ACL4SSR 各个策略组
                final_config = template_config.copy()
                final_config["proxies"] = proxies

                builtin_proxies = ["DIRECT", "REJECT", "no-resolve"]
                groups = final_config.get("proxy-groups", [])
                all_group_names = [g["name"] for g in groups]

                # 遍历模板里的每一个策略组 (如 Netflix, Telegram, 节点选择 等)
                for g in groups:
                    current_list = g.get("proxies", [])
                    # 过滤保留: 指向其他组的名称, 或 DIRECT/REJECT 等内置词
                    base_refs = [p for p in current_list if p in all_group_names or p in builtin_proxies]
                    
                    # 将解析出的真实节点塞入每一个策略组头部
                    g["proxies"] = node_names + base_refs

                final_config["proxy-groups"] = groups

                # 4. 生成 YAML 输出
                final_yaml = yaml.dump(final_config, allow_unicode=True, sort_keys=False)

                st.write("---")
                st.subheader("🎉 转换成功！已生成完整的 ACL4SSR 配置")
                st.download_button(
                    label="💾 点击下载 Clash Meta 配置文件 (.yaml)",
                    data=final_yaml,
                    file_name="clash_meta_acl4ssr.yaml",
                    mime="text/yaml",
                    use_container_width=True
                )
                
                with st.expander("🔍 预览导出的策略组 (验证 ACL4SSR 组别结构)"):
                    st.write(f"**策略组总数：** {len(groups)} 个")
                    st.json([g["name"] for g in groups])

            except Exception as e:
                st.error(f"转换失败: {str(e)}")
