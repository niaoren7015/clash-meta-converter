import streamlit as st
import yaml
import requests
import base64
import re
from urllib.parse import urlparse, parse_qs, unquote

st.set_page_config(
    page_title="Clash Meta (Mihomo) 全能订阅转换工具",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Clash Meta (Mihomo) 全能订阅转换工具")
st.caption("支持直接粘贴 vless:// 链接、机场订阅 URL 或 YAML 节点，一键注入 ACL4SSR 分流模板")

# ----------------- 帮助函数：解析 vless:// 链接 -----------------
def parse_vless_url(vless_url):
    """将单条 vless:// 字符串解析为 Clash Meta 代理节点字典"""
    try:
        if not vless_url.startswith("vless://"):
            return None
        
        # 处理 tag/备注 (即 # 后面的名字)
        main_part = vless_url[8:]
        name = "VLESS 节点"
        if "#" in main_part:
            main_part, name = main_part.split("#", 1)
            name = unquote(name)

        # 解析 userinfo @ host:port
        if "@" not in main_part:
            return None
        uuid, host_port = main_part.split("@", 1)
        
        # 解析 host, port 和 query 参数
        if "?" in host_port:
            server_port, query_str = host_port.split("?", 1)
        else:
            server_port = host_port
            query_str = ""

        if ":" not in server_port:
            return None
        server, port = server_port.split(":", 1)
        
        params = parse_qs(query_str)
        
        # 提取参数值
        def get_param(key, default=""):
            return params.get(key, [default])[0]

        network = get_param("type", "tcp")
        security = get_param("security", "")
        sni = get_param("sni", get_param("peer", server))
        fp = get_param("fp", "chrome")
        pbk = get_param("pbk", "")
        sid = get_param("sid", "")
        path = get_param("path", "/")
        host = get_param("host", "")

        # 构建 Mihomo / Clash Meta vless 配置结构
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

        # 清理 None 字段
        proxy = {k: v for k, v in proxy.items() if v is not None}

        # REALITY 配置
        if security == "reality":
            proxy["reality-opts"] = {}
            if pbk:
                proxy["reality-opts"]["public-key"] = pbk
            if sid:
                proxy["reality-opts"]["short-id"] = sid

        # 传输层配置 (ws, grpc 等)
        if network == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {"path": path}
            if host:
                proxy["ws-opts"]["headers"] = {"Host": host}
        elif network == "grpc":
            proxy["network"] = "grpc"
            grpc_service = get_param("serviceName", "")
            proxy["grpc-opts"] = {"grpc-service-name": grpc_service}
        elif network == "h2":
            proxy["network"] = "h2"
            proxy["h2-opts"] = {"path": path, "host": [host] if host else []}

        return proxy
    except Exception as e:
        return None

# ----------------- 帮助函数：多格式解析器 -----------------
def parse_input_to_proxies(raw_text):
    raw_text = raw_text.strip()
    proxies = []

    # 1. 尝试作为 HTTP/HTTPS 机场订阅链接读取
    if raw_text.startswith("http://") or raw_text.startswith("https://"):
        headers = {'User-Agent': 'ClashMeta'}
        resp = requests.get(raw_text, headers=headers, timeout=15)
        raw_text = resp.text.strip()

    # 2. 尝试判断是否为 Base64 编码的链接列表（常见于普通机场订阅）
    try:
        decoded_text = base64.b64decode(raw_text).decode('utf-8', errors='ignore')
        if "vless://" in decoded_text or "vmess://" in decoded_text or "ss://" in decoded_text:
            raw_text = decoded_text
    except Exception:
        pass

    # 3. 逐行解析 vless:// 链接或寻找 YAML 块
    lines = raw_text.splitlines()
    vless_found = False
    
    for line in lines:
        line = line.strip()
        if line.startswith("vless://"):
            p = parse_vless_url(line)
            if p:
                proxies.append(p)
                vless_found = True

    # 4. 如果没有找到单独的 vless:// 链接，尝试解析为标准的 YAML/Clash 格式
    if not vless_found:
        try:
            parsed_yaml = yaml.safe_load(raw_text)
            if isinstance(parsed_yaml, dict) and "proxies" in parsed_yaml:
                proxies = parsed_yaml["proxies"]
            elif isinstance(parsed_yaml, list):
                proxies = parsed_yaml
        except Exception:
            pass

    return proxies

# ----------------- Streamlit UI 主界面 -----------------

with st.sidebar:
    st.header("⚙️ 转换配置")
    template_type = st.selectbox(
        "选择分流模板",
        ["ACL4SSR 精简版", "ACL4SSR 全规则版", "自定义 YAML 模板 URL"]
    )
    custom_url = ""
    if template_type == "自定义 YAML 模板 URL":
        custom_url = st.text_input("请输入模板 URL:")

st.write("### 输入节点或订阅")
source_input = st.text_area(
    "支持粘贴以下任意形式：\n1. 机场 HTTP 订阅链接 (如 https://...)\n2. 单条或多条 vless:// 节点链接\n3. 包含 proxies 的 Clash YAML 节点文本",
    height=250,
    placeholder="""可以直接粘贴：
https://my-airport.com/api/v1/client/subscribe?token=xxxx

或者粘贴单/多行节点链接：
vless://uuid@example.com:443?security=reality&sni=google.com&fp=chrome&pbk=xxxx#节点名称

或者粘贴 YAML 代码块..."""
)

if st.button("🚀 开始解析并生成 Clash Meta 配置", use_container_width=True):
    if not source_input.strip():
        st.error("请输入节点信息或订阅链接！")
    else:
        with st.spinner("正在解析节点并下载 ACL4SSR 分流模板..."):
            try:
                # 1. 解析节点
                proxies = parse_input_to_proxies(source_input)
                
                if not proxies:
                    st.error("无法解析输入的节点数据！请确认是否为有效的 vless:// 链接、机场订阅或 YAML 内容。")
                    st.stop()
                
                node_names = [p["name"] for p in proxies if isinstance(p, dict) and "name" in p]
                st.success(f"成功识别并转化了 {len(node_names)} 个节点！")

                # 2. 下载 ACL4SSR 模板
                if template_type == "ACL4SSR 精简版":
                    target_url = "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/GeneralClashConfig.yml"
                elif template_type == "ACL4SSR 全规则版":
                    target_url = "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/GeneralClashConfig.yml"
                else:
                    target_url = custom_url

                resp = requests.get(target_url, timeout=10)
                template_config = yaml.safe_load(resp.text)

                # 3. 注入节点到策略组
                new_config = template_config.copy()
                new_config["proxies"] = proxies

                builtin = ["DIRECT", "REJECT", "no-resolve"]
                groups = new_config.get("proxy-groups", [])
                group_names = [g["name"] for g in groups]

                for g in groups:
                    current_proxies = g.get("proxies", [])
                    new_group_proxies = [p for p in current_proxies if p in builtin or p in group_names]
                    
                    core_keywords = ['节点', 'Proxy', '加速', '选择', 'Select', 'Default', '自动', '漏网之鱼']
                    if any(k in g['name'] for k in core_keywords) or len(new_group_proxies) < len(current_proxies):
                        g['proxies'] = node_names + new_group_proxies
                    else:
                        g['proxies'] = new_group_proxies

                # 4. 清理空组
                valid_targets = set(node_names + builtin + group_names)
                for _ in range(3):
                    active_groups = []
                    for g in groups:
                        g['proxies'] = [p for p in g['proxies'] if p in valid_targets]
                        if len(g['proxies']) > 0:
                            active_groups.append(g['name'])
                    valid_targets = set(node_names + builtin + active_groups)
                    groups = [g for g in groups if len(g['proxies']) > 0]
                
                new_config['proxy-groups'] = groups

                # 5. 生成结果
                final_yaml = yaml.dump(new_config, allow_unicode=True, sort_keys=False)

                st.write("---")
                st.subheader("🎉 转换完成")
                st.download_button(
                    label="💾 点击下载 Clash Meta 配置文件 (.yaml)",
                    data=final_yaml,
                    file_name="clash_meta_acl4ssr.yaml",
                    mime="text/yaml",
                    use_container_width=True
                )
                
                with st.expander("🔍 预览解析出的代理节点 (YAML 格式)"):
                    st.code(yaml.dump({"proxies": proxies}, allow_unicode=True, sort_keys=False), language="yaml")

            except Exception as e:
                st.error(f"处理失败，原因: {str(e)}")
