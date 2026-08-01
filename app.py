import streamlit as st
import yaml
import requests

st.set_page_config(
    page_title="Clash Meta (Mihomo) 订阅转换工具",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Clash Meta (Mihomo) 规则注入工具")
st.caption("完美支持 VLESS / REALITY 等新协议，一键注入 ACL4SSR 分流模板并生成 .yaml 文件")

# 侧边栏说明
with st.sidebar:
    st.header("⚙️ 转换配置")
    template_type = st.selectbox(
        "选择分流模板",
        ["ACL4SSR 精简版", "ACL4SSR 全规则版", "自定义 YAML 模板 URL"]
    )
    
    custom_url = ""
    if template_type == "自定义 YAML 模板 URL":
        custom_url = st.text_input("请输入模板 URL:")

    st.markdown("---")
    st.markdown("""
    **💡 使用指南：**
    1. 粘贴包含 `proxies:` 的 YAML 文本。
    2. 选择你需要的 ACL4SSR 分流模式。
    3. 点击转换，直接下载 `.yaml` 配置文件。
    4. 将文件导入 Clash Verge / Clash Meta (Mihomo) 客户端即可。
    """)

# 主界面：输入区
col1, col2 = st.columns(2)

with col1:
    source_raw = st.text_area(
        "1. 粘贴节点数据 (支持 VLESS / SS / Trojan 等 YAML 格式):",
        height=350,
        placeholder="""proxies:
  - name: "VLESS-Reality-Node"
    type: vless
    server: example.com
    port: 443
    uuid: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    cipher: auto
    tls: true
    servername: example.com
    reality-opts:
      public-key: xxxxxx
    network: ws"""
    )

with col2:
    template_raw = st.text_area(
        "2. (可选) 粘贴自定义 ACL4 策略模板 YAML 内容:",
        height=350,
        help="如果左侧侧边栏没有勾选自定义 URL，且此处为空，系统将自动拉取官方最新 ACL4SSR 模板。"
    )

# 转换按钮
if st.button("🚀 开始转换并生成 Clash Meta 配置文件", use_container_width=True):
    if not source_raw.strip():
        st.error("请先在左侧输入框粘贴节点数据！")
    else:
        try:
            # 1. 解析节点 YAML
            source_config = yaml.safe_load(source_raw)
            
            # 兼容处理：支持直接粘贴包含 proxies 的字典，或纯节点列表
            if isinstance(source_config, dict) and "proxies" in source_config:
                proxies = source_config["proxies"]
            elif isinstance(source_config, list):
                proxies = source_config
            else:
                st.error("解析失败：输入的节点数据格式不正确，必须包含 `proxies:` 列表。")
                st.stop()

            node_names = [p["name"] for p in proxies if isinstance(p, dict) and "name" in p]
            
            if not node_names:
                st.error("未找到有效的节点信息。")
                st.stop()
                
            st.success(f"成功提取 {len(node_names)} 个节点（已识别 VLESS 及其他协议）！")

            # 2. 获取策略模板
            template_config = None
            
            # 优先使用用户在右侧文本框手动粘贴的模板
            if template_raw.strip():
                template_config = yaml.safe_load(template_raw)
            else:
                # 否则从网络下载在线模板
                st.info("正在获取在线 ACL4SSR 策略基底...")
                if template_type == "ACL4SSR 精简版":
                    target_url = "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/GeneralClashConfig.yml"
                elif template_type == "ACL4SSR 全规则版":
                    target_url = "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/GeneralClashConfig.yml"
                else:
                    target_url = custom_url
                
                if not target_url:
                    st.error("请输入有效的自定义模板 URL。")
                    st.stop()
                    
                resp = requests.get(target_url, timeout=10)
                template_config = yaml.safe_load(resp.text)

            # 3. 注入节点与组逻辑
            new_config = template_config.copy()
            new_config["proxies"] = proxies

            builtin = ["DIRECT", "REJECT", "no-resolve"]
            groups = new_config.get("proxy-groups", [])
            group_names = [g["name"] for g in groups]

            # 将节点注入到策略组中
            for g in groups:
                current_proxies = g.get("proxies", [])
                # 保留策略组对其他组的引用和内置指令
                new_group_proxies = [p for p in current_proxies if p in builtin or p in group_names]
                
                # 定义需要自动塞入全部节点的组名称关键字
                core_keywords = ['节点', 'Proxy', '加速', '选择', 'Select', 'Default', '自动', '漏网之鱼']
                if any(k in g['name'] for k in core_keywords) or len(new_group_proxies) < len(current_proxies):
                    g['proxies'] = node_names + new_group_proxies
                else:
                    g['proxies'] = new_group_proxies

            # 4. 清理无效/空引用，防止 Mihomo 报错
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

            # 5. 生成 YAML 输出
            final_yaml = yaml.dump(new_config, allow_unicode=True, sort_keys=False)

            st.write("---")
            st.subheader("🎉 转换完成")
            
            # 提供下载
            st.download_button(
                label="💾 点击下载 Clash Meta 配置文件 (.yaml)",
                data=final_yaml,
                file_name="clash_meta_acl4ssr.yaml",
                mime="text/yaml",
                use_container_width=True
            )

            with st.expander("🔍 预览生成的 YAML 内容 (部分)"):
                st.code(final_yaml[:1500] + "\n\n... (后续规则已隐藏，请直接下载文件)", language="yaml")

        except Exception as e:
            st.error(f"处理过程中发生错误: {str(e)}")
