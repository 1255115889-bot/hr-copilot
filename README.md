# HR Copilot - AI员工政策顾问

基于**千问大模型（Qwen）**的企业 HR 智能问答与业务办理系统。

🔗 **在线演示**：[https://cccarolyn.top/hr](https://cccarolyn.top/hr)

## 功能特性

### 员工端
- 💬 **AI 智能问答** — 基于企业知识库的流式 RAG 问答，强制引用政策来源
- 🃏 **业务卡片推荐** — 意图识别后自动推送在职证明/收入证明/请假/申诉等卡片
- 📋 **我的申请** — 查看历史申请状态

### HR 管理端
- 📚 **知识库管理** — 增删改查政策条目，支持分类筛选
- ✅ **审批中心** — 一键通过/拒绝员工申请
- 📊 **数据统计** — 问答量、命中率、分类分布等指标

### 技术亮点
- 角色切换（员工 / HR 管理员），无需登录
- 流式 SSE 输出，实时显示 AI 回答
- 移动端适配（底部 Tab Bar + 抽屉菜单）
- 知识库 RAG 检索 + 意图识别

## 技术栈

- **后端**：Python + Flask
- **大模型**：阿里云千问 `qwen-plus`（OpenAI 兼容接口）
- **前端**：原生 HTML + Tailwind CSS + Material Icons
- **部署**：Nginx 反向代理 + 阿里云服务器

## 快速启动

```bash
# 1. 克隆项目
git clone https://github.com/1255115889-bot/hr-copilot.git
cd hr-copilot

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的千问 API Key

# 4. 启动服务
QWEN_API_KEY=你的key PORT=8891 python3 app.py
```

访问 http://localhost:8891 即可使用。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QWEN_API_KEY` | 阿里云百炼平台 API Key | 必填 |
| `PORT` | 服务端口 | `8891` |

## Nginx 配置

```nginx
location /hr {
    proxy_pass http://127.0.0.1:8891/;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 120s;
}
```

## 项目结构

```
hr-copilot/
├── app.py              # Flask 后端（API + 知识库 + AI 问答）
├── templates/
│   └── index.html      # 前端单页应用
├── requirements.txt
├── .env.example
└── README.md
```
