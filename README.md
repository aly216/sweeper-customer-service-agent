# 扫地机器人智能客服（ReAct 智能体）

基于 LangChain ReAct 架构的扫地机器人智能客服，实现「思考 → 行动 → 观察」的自主推理闭环，覆盖产品问答、故障排查、选购建议与个性化使用报告四类场景。

## 功能

- 基于 `create_agent` 构建 ReAct 智能体，集成 7 类工具（知识库检索、天气查询、用户定位、用户 ID、当前月份、外部业务数据、报告上下文注入），支持多轮推理与多工具协同
- 基于中间件实现工具调用监控（`wrap_tool_call`）、模型调用日志（`before_model`）与动态提示词切换（`dynamic_prompt`），在「客服问答」与「报告生成」两种模式间自动切换
- 构建 Chroma + text-embedding-v3 的 RAG 检索链路，知识库覆盖选购、故障、保养、问答等文档，支持 PDF/TXT 加载与 MD5 增量去重
- 采用抽象工厂 + YAML 配置中心管理模型与向量化参数，支持流式输出；报告场景自动生成 Markdown 使用报告与保养建议
- 基于 Streamlit 的 Web 对话界面

## 目录结构

```
Agent智能体/
├── app.py                    # 入口：Streamlit 对话界面
├── agent/
│   ├── react_agent.py        # ReAct 智能体（create_agent + 工具 + 中间件）
│   └── tools/
│       ├── agent_tools.py    # 7 类工具定义
│       └── middleware.py     # 中间件：工具监控 / 模型日志 / 提示词切换
├── rag/
│   ├── rag_service.py        # RAG 总结服务（检索 → 组装 → 生成）
│   └── vector_store.py       # Chroma 向量库封装 + 知识入库
├── model/factory.py          # 抽象工厂：模型 / 向量化实例
├── config/                   # YAML 配置中心（模型 / 向量库 / 提示词 / Agent）
├── prompt/                   # 提示词模板
├── data/                     # 知识库文档（PDF / TXT）+ 外部业务数据
└── utils/                    # 配置加载、文件处理、日志等工具
```

## 技术栈

- Python
- LangChain —— ReAct 智能体、工具调用、中间件、LCEL
- Chroma —— 向量数据库；阿里云百炼 text-embedding-v3 —— 文本向量化
- DeepSeek —— 对话模型
- Streamlit —— Web 界面
- PyYAML —— 配置管理

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入 DeepSeek 与阿里云百炼密钥：

```bash
cp .env.example .env
```

### 3. 构建知识库

将知识文档（PDF/TXT）放入 `data/` 目录，然后在项目根目录运行：

```bash
python -c "from rag.vector_store import VectorStoreService; VectorStoreService().load_documents([])"
```

向量会持久化到 `chroma_db/`（已 gitignore）。

### 4. 启动

```bash
streamlit run app.py
```

## 注意事项

- **密钥安全**：API Key 放在 `.env` 中，已加入 `.gitignore`，请勿提交到仓库。
- **首次构建**：需先执行步骤 3 构建知识库，否则问答无法检索到内容。
- 报告生成场景依赖 `config/agent.yml` 中配置的外部数据文件（`data/external/records.csv`）。
