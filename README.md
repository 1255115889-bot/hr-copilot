# HR Copilot - AI员工政策顾问

基于**千问大模型 + 向量数据库**的企业 HR 智能问答与业务办理系统。

🔗 **在线演示**：[https://cccarolyn.top/hr](https://cccarolyn.top/hr)

## 技术架构

```
浏览器
  ↓ HTTPS
Nginx /hr
  ↓
Flask App
  ├── SQLite          # 申请记录、知识库条目持久化
  ├── ChromaDB        # 向量数据库，RAG语义检索
  ├── 千问 Embedding  # text-embedding-v3 文本向量化
  └── 千问 qwen-plus  # 对话生成（流式SSE）
```

## 核心功能

### 员工端
- 💬 **AI 问答（RAG）** — 向量检索知识库，语义匹配，流式输出，强制引用来源
- 🃏 **业务卡片推荐** — 意图识别，自动推送在职证明/请假/薪资查询等办理入口
- 📋 **我的申请** — 申请记录持久化到 SQLite，实时查看状态

### HR 管理端
- 📚 **知识库管理** — 手动添加条目 / 上传 PDF·Word·TXT 自动切片向量化
- ✅ **审批中心** — 通过/拒绝员工申请，数据持久化
- 📊 **数据统计** — 向量库状态、分类分布、申请处理数据

## 快速启动

```bash
git clone https://github.com/1255115889-bot/hr-copilot.git
cd hr-copilot
pip install -r requirements.txt
mkdir -p data uploads templates

# 配置 API Key
export QWEN_API_KEY=你的千问APIKey

# 启动
python3 app.py
```

访问 http://localhost:8891

## 环境变量

| 变量 | 说明 |
|------|------|
| `QWEN_API_KEY` | 阿里云百炼平台 API Key（必填） |
| `PORT` | 服务端口，默认 8891 |

## 项目结构

```
hr-copilot/
├── app.py                  # 后端：Flask + SQLAlchemy + ChromaDB + RAG
├── templates/
│   └── index.html          # 前端单页应用
├── data/                   # 运行时生成
│   ├── hr_copilot.db       # SQLite 数据库
│   └── chroma/             # ChromaDB 向量存储
├── uploads/                # 上传的文档文件
├── requirements.txt
└── README.md
```
