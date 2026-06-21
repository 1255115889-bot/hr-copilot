#!/usr/bin/env python3
"""HR Copilot - 生产级后端：SQLite + ChromaDB + 千问Embedding + RAG"""
import json, os, re, uuid, datetime, hashlib, threading
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Enum, func
from sqlalchemy.orm import DeclarativeBase, Session
import chromadb
from chromadb.config import Settings

app = Flask(__name__, template_folder="templates")

# ============================================================
# 配置
# ============================================================
BASE_DIR     = os.path.dirname(__file__)
UPLOAD_DIR   = os.path.join(BASE_DIR, "uploads")
DATA_DIR     = os.path.join(BASE_DIR, "data")
DB_PATH      = os.path.join(DATA_DIR, "hr_copilot.db")
CHROMA_PATH  = os.path.join(DATA_DIR, "chroma")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
QWEN_BASE    = "https://dashscope.aliyuncs.com/compatible-mode/v1"
EMBED_MODEL  = "text-embedding-v3"
CHAT_MODEL   = "qwen-plus"
MAX_FILE_MB  = 20
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR,   exist_ok=True)
os.makedirs(CHROMA_PATH, exist_ok=True)

# ============================================================
# SQLite 数据库
# ============================================================
class Base(DeclarativeBase): pass

class KBArticle(Base):
    __tablename__ = "kb_articles"
    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category   = Column(String(32), nullable=False)
    policy     = Column(String(128))
    question   = Column(Text, nullable=False)
    answer     = Column(Text, nullable=False)
    tags       = Column(Text, default="[]")          # JSON list
    source_file= Column(String(256))                 # 上传文件名
    chunk_index= Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Application(Base):
    __tablename__ = "applications"
    id          = Column(String(16), primary_key=True)
    app_type    = Column(String(64), nullable=False)
    applicant   = Column(String(64), nullable=False)
    dept        = Column(String(64))
    status      = Column(Enum("pending","approved","rejected"), default="pending")
    note        = Column(Text)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)

def get_db():
    return Session(engine)

def next_app_id():
    with get_db() as db:
        count = db.query(func.count(Application.id)).scalar() or 0
        return f"APP{str(count+1).zfill(3)}"

# ============================================================
# ChromaDB 向量库
# ============================================================
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
try:
    kb_collection = chroma_client.get_collection("hr_kb")
except:
    kb_collection = chroma_client.create_collection(
        "hr_kb",
        metadata={"hnsw:space": "cosine"}
    )

# ============================================================
# 千问 Embedding
# ============================================================
def get_embedding(texts: list[str]) -> list[list[float]]:
    import urllib.request
    payload = json.dumps({
        "model": EMBED_MODEL,
        "input": texts,
    }).encode()
    req = urllib.request.Request(
        f"{QWEN_BASE}/embeddings",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {QWEN_API_KEY}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

# ============================================================
# 文档解析（PDF / Word / TXT）
# ============================================================
def parse_file(filepath: str) -> list[str]:
    ext = os.path.splitext(filepath)[1].lower()
    texts = []
    if ext == ".pdf":
        import fitz
        doc = fitz.open(filepath)
        for page in doc:
            t = page.get_text().strip()
            if t: texts.append(t)
        doc.close()
    elif ext in (".docx", ".doc"):
        from docx import Document
        doc = Document(filepath)
        for para in doc.paragraphs:
            t = para.text.strip()
            if t: texts.append(t)
    elif ext == ".txt":
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            texts = [l.strip() for l in f if l.strip()]
    return texts

def chunk_texts(texts: list[str], size=300, overlap=50) -> list[str]:
    """合并段落后按字符数切块"""
    merged = "\n".join(texts)
    chunks = []
    start = 0
    while start < len(merged):
        end = min(start + size, len(merged))
        chunk = merged[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks

# ============================================================
# 向量检索
# ============================================================
def vector_search(query: str, top_k=5) -> list[dict]:
    try:
        count = kb_collection.count()
        if count == 0:
            return []
        emb = get_embedding([query])[0]
        results = kb_collection.query(
            query_embeddings=[emb],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"]
        )
        items = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            if dist < 0.6:   # cosine distance 阈值，越小越相似
                items.append({
                    "content": doc,
                    "policy":  meta.get("policy", ""),
                    "category":meta.get("category", ""),
                    "source":  meta.get("source_file", ""),
                    "score":   round(1 - dist, 3)
                })
        return items
    except Exception as e:
        print(f"vector_search error: {e}")
        return []

# ============================================================
# 意图识别 & 业务卡片
# ============================================================
def detect_intent(query):
    q = query.lower()
    if any(k in q for k in ["在职证明","工作证明","employment"]):
        return "employment_cert"
    if any(k in q for k in ["收入证明","薪资证明","income"]):
        return "income_cert"
    if any(k in q for k in ["请假","休假","年假","病假","婚假","产假","事假"]):
        return "leave"
    if any(k in q for k in ["工资","薪资","薪水","发薪","工资条","薪酬"]):
        return "salary_query"
    if any(k in q for k in ["考勤","打卡","迟到","旷工","出勤"]):
        return "attendance_query"
    if any(k in q for k in ["异常","申诉","错误","少发","扣款","投诉"]):
        return "dispute"
    if any(k in q for k in ["合同","劳动合同","协议"]):
        return "contract_query"
    return None

CARDS = {
    "employment_cert": {"type":"action","title":"在职证明申请","desc":"提供标准在职证明，适用于签证、银行、房产等场景。","meta":"处理时效：1个工作日","btn":"立即申请","action":"apply","apply_type":"在职证明","icon":"description"},
    "income_cert":     {"type":"action","title":"收入证明申请","desc":"包含税前/税后薪资明细，加盖公章，可用于贷款等。","meta":"处理时效：2个工作日","btn":"立即申请","action":"apply","apply_type":"收入证明","icon":"payments"},
    "leave":           {"type":"action","title":"请假申请","desc":"在线发起请假申请，支持年假、病假、事假等各类假期。","meta":"需提前1个工作日申请","btn":"发起申请","action":"apply","apply_type":"请假申请","icon":"calendar_today"},
    "salary_query":    {"type":"info","title":"薪资查询","desc":"查看近6个月工资条、五险一金缴纳记录及绩效奖金明细。","meta":"数据来源：薪资系统（实时）","btn":"立即查看","action":"view","icon":"account_balance_wallet"},
    "attendance_query":{"type":"info","title":"考勤记录查询","desc":"查看本月/上月打卡记录、迟到早退统计及异常记录。","meta":"数据更新：每日同步","btn":"查看记录","action":"view","icon":"schedule"},
    "dispute":         {"type":"alert","title":"薪资/考勤异常申诉","desc":"如发现薪资或考勤记录有误，可在线提交申诉，HR将在3个工作日内处理。","meta":"HR处理时限：3个工作日","btn":"提交申诉","action":"apply","apply_type":"薪资异常申诉","icon":"report_problem"},
    "contract_query":  {"type":"info","title":"合同信息查询","desc":"查看当前劳动合同期限、岗位信息及历史合同记录。","meta":"数据来源：HR档案系统","btn":"查看合同","action":"view","icon":"gavel"},
}

# ============================================================
# AI 问答（流式 SSE）
# ============================================================
def build_system_prompt(kb_items: list[dict]) -> str:
    if not kb_items:
        kb_text = "（当前知识库暂无匹配内容）"
    else:
        kb_text = ""
        for i, item in enumerate(kb_items, 1):
            src = f"【{item['policy']}】" if item['policy'] else f"【{item['source'] or '知识库'}】"
            kb_text += f"\n{src}\n{item['content']}\n"

    return f"""你是一家企业的 AI HR 政策顾问助手（HR Copilot）。只能基于下方知识库内容回答员工问题。

**严格规则：**
1. 只能基于知识库内容回答，禁止自由推测或编造
2. 知识库无匹配内容时，必须回复："该问题暂未收录在知识库中，请联系 HR 部门进一步确认。"
3. 每次回答结尾必须注明政策来源（例如：📌 来源：《考勤与休假管理制度》第3.1条）
4. 语气专业、简洁、友好，使用中文回答
5. 如有多个相关政策，分条列出

**知识库内容：**
{kb_text}"""

def stream_chat(query: str, history: list) -> Response:
    import urllib.request

    # 1. 向量检索
    kb_items = vector_search(query, top_k=5)

    # 2. 意图识别
    intent = detect_intent(query)
    card   = CARDS.get(intent) if intent else None

    # 3. 构建消息
    messages = []
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": query})

    system_prompt = build_system_prompt(kb_items)

    def generate():
        payload = json.dumps({
            "model": CHAT_MODEL,
            "max_tokens": 1000,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": True,
        }).encode()

        req = urllib.request.Request(
            f"{QWEN_BASE}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {QWEN_API_KEY}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                buf = b""
                while True:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n"):
                        line = buf.decode("utf-8", errors="replace").strip()
                        buf  = b""
                        if not line or not line.startswith("data:"):
                            continue
                        payload_str = line[5:].strip()
                        if payload_str == "[DONE]":
                            break
                        try:
                            obj  = json.loads(payload_str)
                            text = obj.get("choices",[{}])[0].get("delta",{}).get("content","")
                            if text:
                                yield f"data:{json.dumps({'text': text})}\n\n"
                        except:
                            pass
        except Exception as e:
            yield f"data:{json.dumps({'text': f'AI服务暂时不可用（{str(e)[:60]}）'})}\n\n"

        citations = [{"policy": it["policy"], "source": it["source"], "score": it["score"]} for it in kb_items]
        yield f"data:{json.dumps({'done': True, 'card': card, 'citations': citations})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ============================================================
# 路由 - 页面
# ============================================================
@app.route("/")
def index():
    from flask import make_response
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp

# ============================================================
# 路由 - 对话
# ============================================================
@app.route("/api/chat", methods=["POST"])
def chat():
    data  = request.json or {}
    query = data.get("query","").strip()
    if not query:
        return jsonify({"error": "empty query"}), 400
    return stream_chat(query, data.get("history", []))

# ============================================================
# 路由 - 知识库 CRUD
# ============================================================
@app.route("/api/kb", methods=["GET"])
def kb_list():
    category = request.args.get("category","")
    keyword  = request.args.get("q","")
    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    with get_db() as db:
        q = db.query(KBArticle)
        if category:
            q = q.filter(KBArticle.category == category)
        if keyword:
            q = q.filter(
                KBArticle.question.contains(keyword) |
                KBArticle.answer.contains(keyword)   |
                KBArticle.policy.contains(keyword)
            )
        total = q.count()
        items = q.order_by(KBArticle.created_at.desc()) \
                 .offset((page-1)*per_page).limit(per_page).all()
        return jsonify({
            "items": [{
                "id": a.id, "category": a.category, "policy": a.policy,
                "q": a.question, "a": a.answer,
                "tags": json.loads(a.tags or "[]"),
                "source_file": a.source_file,
                "created_at": a.created_at.isoformat() if a.created_at else ""
            } for a in items],
            "total": total, "page": page, "per_page": per_page
        })

@app.route("/api/kb", methods=["POST"])
def kb_add():
    data = request.json or {}
    q_text = data.get("q","").strip()
    a_text = data.get("a","").strip()
    if not q_text or not a_text:
        return jsonify({"error": "q and a required"}), 400

    article = KBArticle(
        id       = str(uuid.uuid4()),
        category = data.get("category","其他"),
        policy   = data.get("policy",""),
        question = q_text,
        answer   = a_text,
        tags     = json.dumps(data.get("tags",[])),
    )
    # 向量化写入 ChromaDB
    content  = f"问：{q_text}\n答：{a_text}"
    try:
        emb = get_embedding([content])[0]
        kb_collection.add(
            ids=[article.id],
            embeddings=[emb],
            documents=[content],
            metadatas=[{"policy": article.policy, "category": article.category, "source_file": ""}]
        )
    except Exception as e:
        print(f"embedding error: {e}")

    with get_db() as db:
        db.add(article)
        db.commit()
        return jsonify({"success": True, "id": article.id})

@app.route("/api/kb/<item_id>", methods=["DELETE"])
def kb_delete(item_id):
    with get_db() as db:
        item = db.query(KBArticle).filter(KBArticle.id == item_id).first()
        if item:
            db.delete(item)
            db.commit()
    try:
        kb_collection.delete(ids=[item_id])
    except:
        pass
    return jsonify({"success": True})

# ============================================================
# 路由 - 文件上传（异步向量化）
# ============================================================
@app.route("/api/kb/upload", methods=["POST"])
def kb_upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    file = request.files["file"]
    category = request.form.get("category", "其他")
    policy   = request.form.get("policy", "")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt"):
        return jsonify({"error": "仅支持 PDF / Word / TXT"}), 400
    if file.content_length and file.content_length > MAX_FILE_MB * 1024 * 1024:
        return jsonify({"error": f"文件不能超过 {MAX_FILE_MB}MB"}), 400

    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_name)
    file.save(save_path)

    # 异步处理（不阻塞请求）
    def process():
        try:
            texts  = parse_file(save_path)
            chunks = chunk_texts(texts, size=400, overlap=80)
            if not chunks:
                return

            # 批量 embedding（每批20条）
            batch_size = 20
            article_ids = []
            all_embeddings = []
            all_docs = []
            all_metas = []

            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i+batch_size]
                embs  = get_embedding(batch)
                for j, (chunk, emb) in enumerate(zip(batch, embs)):
                    aid = str(uuid.uuid4())
                    article_ids.append(aid)
                    all_embeddings.append(emb)
                    all_docs.append(chunk)
                    all_metas.append({
                        "policy": policy,
                        "category": category,
                        "source_file": file.filename,
                        "chunk_index": i+j
                    })
                    # 写 SQLite
                    article = KBArticle(
                        id=aid, category=category, policy=policy,
                        question=chunk[:80].replace("\n"," "),
                        answer=chunk, source_file=file.filename,
                        chunk_index=i+j
                    )
                    with get_db() as db:
                        db.add(article)
                        db.commit()

            # 批量写 ChromaDB
            kb_collection.add(
                ids=article_ids,
                embeddings=all_embeddings,
                documents=all_docs,
                metadatas=all_metas
            )
            print(f"[upload] {file.filename}: {len(chunks)} chunks done")
        except Exception as e:
            print(f"[upload] error: {e}")

    threading.Thread(target=process, daemon=True).start()
    return jsonify({"success": True, "message": f"文件已上传，正在后台解析向量化，请稍后刷新知识库..."})

# ============================================================
# 路由 - 申请管理
# ============================================================
@app.route("/api/applications", methods=["GET"])
def get_applications():
    status   = request.args.get("status","")
    page     = int(request.args.get("page",1))
    per_page = int(request.args.get("per_page",20))
    with get_db() as db:
        q = db.query(Application)
        if status:
            q = q.filter(Application.status == status)
        total = q.count()
        items = q.order_by(Application.created_at.desc()) \
                 .offset((page-1)*per_page).limit(per_page).all()
        return jsonify({
            "items": [{
                "id": a.id, "type": a.app_type, "applicant": a.applicant,
                "dept": a.dept, "status": a.status, "note": a.note,
                "date": a.created_at.strftime("%Y-%m-%d") if a.created_at else ""
            } for a in items],
            "total": total
        })

@app.route("/api/applications", methods=["POST"])
def create_application():
    data = request.json or {}
    app_type  = data.get("type","").strip()
    applicant = data.get("applicant","").strip()
    if not app_type or not applicant:
        return jsonify({"error": "type and applicant required"}), 400
    a = Application(
        id=next_app_id(), app_type=app_type,
        applicant=applicant, dept=data.get("dept",""),
        note=data.get("note","")
    )
    with get_db() as db:
        db.add(a)
        db.commit()
        return jsonify({"success": True, "app": {
            "id": a.id, "type": a.app_type, "status": a.status,
            "date": a.created_at.strftime("%Y-%m-%d") if a.created_at else ""
        }})

@app.route("/api/applications/<app_id>/approve", methods=["POST"])
def approve_app(app_id):
    with get_db() as db:
        a = db.query(Application).filter(Application.id == app_id).first()
        if not a: return jsonify({"error": "not found"}), 404
        a.status = "approved"
        db.commit()
    return jsonify({"success": True})

@app.route("/api/applications/<app_id>/reject", methods=["POST"])
def reject_app(app_id):
    with get_db() as db:
        a = db.query(Application).filter(Application.id == app_id).first()
        if not a: return jsonify({"error": "not found"}), 404
        a.status = "rejected"
        db.commit()
    return jsonify({"success": True})

# ============================================================
# 路由 - 统计
# ============================================================
@app.route("/api/stats", methods=["GET"])
def get_stats():
    with get_db() as db:
        kb_count      = db.query(func.count(KBArticle.id)).scalar() or 0
        total_apps    = db.query(func.count(Application.id)).scalar() or 0
        pending_apps  = db.query(func.count(Application.id)).filter(Application.status=="pending").scalar() or 0
        approved_apps = db.query(func.count(Application.id)).filter(Application.status=="approved").scalar() or 0
        # 分类分布
        rows = db.query(KBArticle.category, func.count(KBArticle.id)).group_by(KBArticle.category).all()
        cat_dist = {r[0]: r[1] for r in rows}
    return jsonify({
        "kb_articles":   kb_count,
        "total_apps":    total_apps,
        "pending_apps":  pending_apps,
        "approved_apps": approved_apps,
        "vector_count":  kb_collection.count(),
        "category_dist": cat_dist,
    })

# ============================================================
# 路由 - 向量库状态
# ============================================================
@app.route("/api/vector/status", methods=["GET"])
def vector_status():
    return jsonify({
        "collection": "hr_kb",
        "count": kb_collection.count(),
        "embed_model": EMBED_MODEL,
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8891"))
    print(f"[HR Copilot] SQLite: {DB_PATH}")
    print(f"[HR Copilot] ChromaDB: {CHROMA_PATH}, vectors: {kb_collection.count()}")
    app.run(host="127.0.0.1", port=port, debug=False)
