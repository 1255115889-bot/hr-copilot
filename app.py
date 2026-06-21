#!/usr/bin/env python3
"""AI员工政策顾问 HR Copilot - 完整版"""
import json, os, re, uuid, datetime
from flask import Flask, request, jsonify, render_template_string, Response, stream_with_context

app = Flask(__name__)

# ============================================================
# 环境变量
# ============================================================
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# ============================================================
# 内存数据存储（Demo用）
# ============================================================
KNOWLEDGE_BASE = [
    {"id": 1, "category": "休假", "policy": "《考勤与休假管理制度》第3.1条", "q": "年假有多少天", "a": "员工入职满1年享有5天带薪年假；满5年享有10天；满10年享有15天。年假按自然年度计算，当年未休完可顺延至次年3月31日。", "tags": ["年假", "带薪年假"]},
    {"id": 2, "category": "休假", "policy": "《考勤与休假管理制度》第3.2条", "q": "病假怎么请", "a": "病假需提前向直属上级报备，并在OA系统提交请假申请。1天以内由上级审批，2天及以上需提供医院诊断证明，超过3天由部门负责人审批。", "tags": ["病假", "请假"]},
    {"id": 3, "category": "休假", "policy": "《考勤与休假管理制度》第3.3条", "q": "事假如何申请", "a": "事假需提前1个工作日向直属上级申请，经批准后方可休假。每年事假累计不超过15个工作日，事假期间不发放工资。紧急情况可事后补交申请。", "tags": ["事假", "请假"]},
    {"id": 4, "category": "休假", "policy": "《考勤与休假管理制度》第3.4条", "q": "婚假几天", "a": "员工持结婚证可享受3天婚假，须在领证后6个月内一次性休完。婚假期间工资照常发放。晚婚者（男25周岁、女23周岁以上）额外增加7天。", "tags": ["婚假"]},
    {"id": 5, "category": "休假", "policy": "《考勤与休假管理制度》第3.5条", "q": "产假多少天", "a": "女性员工享受98天产假，其中产前可休15天；难产的增加15天；多胞胎的，每多一个婴儿增加15天。产假期间由生育保险基金支付生育津贴。", "tags": ["产假", "生育"]},
    {"id": 6, "category": "休假", "policy": "《考勤与休假管理制度》第3.6条", "q": "陪产假多少天", "a": "男性员工在配偶生育期间享受15天陪产假，须在婴儿出生后30天内一次性休完，期间工资照常发放。", "tags": ["陪产假"]},
    {"id": 7, "category": "薪酬", "policy": "《薪酬管理制度》第4.1条", "q": "工资什么时候发", "a": "每月10日发放上月工资，遇节假日则提前至最近工作日。工资通过银行转账方式发放至员工指定工资卡，同时发放电子工资条。", "tags": ["工资", "薪资", "发薪"]},
    {"id": 8, "category": "薪酬", "policy": "《薪酬管理制度》第5.1条", "q": "绩效考核怎么做", "a": "公司实行季度+年度绩效考核制度。绩效等级分为S/A/B/C/D五档，与年终奖金和次年调薪挂钩。考核结果由直属上级评定，经部门负责人审核。连续两次C档将进入绩效改进计划。", "tags": ["绩效", "考核", "KPI"]},
    {"id": 9, "category": "薪酬", "policy": "《薪酬管理制度》第5.3条", "q": "年终奖怎么算", "a": "年终奖根据公司年度经营业绩和个人绩效考核结果综合确定，于次年春节前发放。在发放日前离职的员工不享有年终奖。年终奖具体金额由公司根据当年效益统一公布。", "tags": ["年终奖", "奖金"]},
    {"id": 10, "category": "薪酬", "policy": "《工作时间与加班管理制度》第2.1条", "q": "加班费怎么算", "a": "工作日加班按1.5倍工资计算；休息日加班且不能安排调休的按2倍计算；法定节假日加班按3倍计算。加班需提前在OA系统申请并经审批。", "tags": ["加班", "加班费"]},
    {"id": 11, "category": "社保", "policy": "《社会保障与福利制度》第2.1条", "q": "社保怎么缴纳", "a": "公司依法为员工缴纳五险一金（养老、医疗、失业、工伤、生育保险和住房公积金），缴纳基数为员工上年度月平均工资，不低于当地最低基数、不高于当地最高基数。个人部分从工资中代扣代缴。", "tags": ["社保", "五险一金", "保险"]},
    {"id": 12, "category": "社保", "policy": "《社会保障与福利制度》第2.2条", "q": "公积金比例是多少", "a": "住房公积金缴存比例为12%，单位和个人各承担50%。缴存基数每年7月调整一次。员工可登录公积金中心网站查询个人账户余额和缴存明细。", "tags": ["公积金", "住房公积金"]},
    {"id": 13, "category": "合同", "policy": "《劳动合同管理制度》第2.4条", "q": "离职流程是什么", "a": "正式员工离职须提前30天书面通知公司，试用期员工提前3天通知。离职流程：提交辞职信→上级面谈→填写离职交接单→归还公司财产→结清工资→开具离职证明。最后工作日发放结余工资。", "tags": ["离职", "辞职"]},
    {"id": 14, "category": "福利", "policy": "《社会保障与福利制度》第3.2条", "q": "公司有哪些商业保险", "a": "公司为所有正式员工购买补充商业医疗保险和意外伤害保险，覆盖门诊、住院、重大疾病及意外身故/伤残。保险自入职当月生效，离职后自动终止。", "tags": ["商业保险", "医疗保险"]},
    {"id": 15, "category": "考勤", "policy": "《考勤与休假管理制度》第2.3条", "q": "迟到怎么处理", "a": "每月迟到累计3次以内且每次不超过10分钟不处罚；超过3次或单次超过30分钟，按事假0.5天计算。迟到1小时以上且无正当理由的，按旷工0.5天处理。", "tags": ["迟到", "考勤", "打卡"]},
    {"id": 16, "category": "考勤", "policy": "《考勤与休假管理制度》第2.1条", "q": "上班时间是几点", "a": "公司实行标准工时制，工作时间为周一至周五9:00-18:00，午休12:00-13:00。弹性工作制岗位可申请调整上下班时间，核心工作时段为10:00-16:00。每天工作时间不少于8小时。", "tags": ["上班时间", "工作时间"]},
    {"id": 17, "category": "考勤", "policy": "《考勤与休假管理制度》第3.7条", "q": "可以远程办公吗", "a": "公司允许员工每月申请不超过4天远程办公，须提前1个工作日向直属上级申请。远程办公期间需保持在线，按时完成工作任务。特殊天气或突发事件时，公司统一安排远程办公。", "tags": ["远程办公", "在家办公", "WFH"]},
    {"id": 18, "category": "福利", "policy": "《费用报销管理制度》第3.1条", "q": "出差标准是什么", "a": "国内出差：一线城市住宿费上限400元/天，餐补100元/天，交通实报实销。二线城市住宿300元/天，餐补80元/天。出差须提前填写出差申请。", "tags": ["出差", "差旅", "报销"]},
    {"id": 19, "category": "合同", "policy": "《劳动合同管理制度》第2.1条", "q": "劳动合同怎么签", "a": "员工入职后1个月内须与公司签订书面劳动合同。合同期限一般为3年，试用期2个月。合同期满前30天，双方协商是否续签。", "tags": ["劳动合同", "合同", "签合同"]},
    {"id": 20, "category": "薪酬", "policy": "《薪酬管理制度》第4.3条", "q": "试用期工资多少", "a": "试用期薪资不低于转正薪资的80%，且不低于当地最低工资标准。试用期满后经考核合格转正，薪资按约定标准执行。", "tags": ["试用期", "试用期工资"]},
]

# 申请记录（内存）
APPLICATIONS = [
    {"id": "APP001", "type": "在职证明", "applicant": "张三", "dept": "技术部", "status": "pending", "date": "2025-06-18", "note": "需要用于银行贷款"},
    {"id": "APP002", "type": "收入证明", "applicant": "李四", "dept": "市场部", "status": "approved", "date": "2025-06-17", "note": "房产公证使用"},
    {"id": "APP003", "type": "请假申请", "applicant": "王五", "dept": "运营部", "status": "pending", "date": "2025-06-19", "note": "事假3天，家中有事"},
    {"id": "APP004", "type": "薪资异常申诉", "applicant": "赵六", "dept": "销售部", "status": "rejected", "date": "2025-06-15", "note": "5月工资少发了加班费"},
]

STATS = {
    "total_queries": 1284,
    "resolved": 1156,
    "pending_apps": 23,
    "kb_articles": len(KNOWLEDGE_BASE),
    "monthly_trend": [320, 410, 380, 450, 520, 490, 1284],
    "category_dist": {"休假": 38, "薪酬": 25, "社保": 15, "合同": 12, "考勤": 10},
}

# ============================================================
# 工具函数
# ============================================================
def tokenize(text):
    text = text.lower().strip()
    grams = set()
    for i in range(len(text)-1):
        grams.add(text[i:i+2])
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or ch.isalnum():
            grams.add(ch)
    return grams

def search_kb(query, top_k=3):
    q_tokens = tokenize(query)
    results = []
    for item in KNOWLEDGE_BASE:
        kb_text = item["q"] + " " + item["a"] + " " + " ".join(item.get("tags", []))
        kb_tokens = tokenize(kb_text)
        if not q_tokens or not kb_tokens:
            continue
        inter = q_tokens & kb_tokens
        union = q_tokens | kb_tokens
        score = len(inter) / len(union) if union else 0
        # boost for tag matches
        for tag in item.get("tags", []):
            if tag.lower() in query.lower():
                score += 0.3
        if score > 0.05:
            results.append((score, item))
    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:top_k]]

def detect_intent(query):
    """识别业务意图，返回可推荐的业务卡片类型"""
    q = query.lower()
    if any(k in q for k in ["在职证明", "工作证明", "employment"]):
        return "employment_cert"
    if any(k in q for k in ["收入证明", "薪资证明", "income"]):
        return "income_cert"
    if any(k in q for k in ["请假", "休假", "年假", "病假", "婚假", "产假"]):
        return "leave"
    if any(k in q for k in ["工资", "薪资", "薪水", "发薪", "工资条"]):
        return "salary_query"
    if any(k in q for k in ["考勤", "打卡", "迟到", "旷工", "出勤"]):
        return "attendance_query"
    if any(k in q for k in ["异常", "申诉", "错误", "少发", "扣款", "投诉"]):
        return "dispute"
    if any(k in q for k in ["合同", "劳动合同", "协议"]):
        return "contract_query"
    return None

CARDS = {
    "employment_cert": {
        "type": "action",
        "title": "在职证明申请",
        "desc": "提供标准在职证明，适用于签证、银行、房产等场景。",
        "meta": "处理时效：1个工作日",
        "btn": "立即申请",
        "action": "apply",
        "apply_type": "在职证明",
        "color": "primary",
        "icon": "description",
    },
    "income_cert": {
        "type": "action",
        "title": "收入证明申请",
        "desc": "包含税前/税后薪资明细，加盖公章，可用于贷款等。",
        "meta": "处理时效：2个工作日",
        "btn": "立即申请",
        "action": "apply",
        "apply_type": "收入证明",
        "color": "secondary",
        "icon": "payments",
    },
    "leave": {
        "type": "action",
        "title": "请假申请",
        "desc": "在线发起请假申请，支持年假、病假、事假等各类假期。",
        "meta": "需提前1个工作日申请",
        "btn": "发起申请",
        "action": "apply",
        "apply_type": "请假申请",
        "color": "primary",
        "icon": "calendar_today",
    },
    "salary_query": {
        "type": "info",
        "title": "薪资查询",
        "desc": "查看近6个月工资条、五险一金缴纳记录及绩效奖金明细。",
        "meta": "数据来源：薪资系统（实时）",
        "btn": "立即查看",
        "action": "view",
        "color": "tertiary",
        "icon": "account_balance_wallet",
    },
    "attendance_query": {
        "type": "info",
        "title": "考勤记录查询",
        "desc": "查看本月/上月打卡记录、迟到早退统计及异常记录。",
        "meta": "数据更新：每日同步",
        "btn": "查看记录",
        "action": "view",
        "color": "tertiary",
        "icon": "schedule",
    },
    "dispute": {
        "type": "alert",
        "title": "薪资/考勤异常申诉",
        "desc": "如发现薪资或考勤记录有误，可在线提交申诉，HR将在3个工作日内处理。",
        "meta": "HR处理时限：3个工作日",
        "btn": "提交申诉",
        "action": "apply",
        "apply_type": "薪资异常申诉",
        "color": "error",
        "icon": "report_problem",
    },
    "contract_query": {
        "type": "info",
        "title": "合同信息查询",
        "desc": "查看当前劳动合同期限、岗位信息及历史合同记录。",
        "meta": "数据来源：HR档案系统",
        "btn": "查看合同",
        "action": "view",
        "color": "tertiary",
        "icon": "gavel",
    },
}

# ============================================================
# AI 问答（流式）
# ============================================================
def build_system_prompt(kb_items):
    kb_text = ""
    for item in kb_items:
        kb_text += f"\n【{item['policy']}】\n问：{item['q']}\n答：{item['a']}\n"
    
    return f"""你是一家企业的 AI HR 政策顾问助手（HR Copilot）。你只能基于下方提供的公司知识库内容回答员工问题。

**严格规则（必须遵守）：**
1. 只能基于知识库内容回答，禁止自由推测或编造
2. 如果知识库中找不到相关信息，必须回复："该问题暂未收录在知识库中，请联系 HR 部门进一步确认。"
3. 每次回答结尾必须注明政策来源（例如：📌 来源：《考勤与休假管理制度》第3.1条）
4. 语气专业、简洁、友好，使用中文回答
5. 如有多个相关政策，分条列出

**公司知识库内容：**
{kb_text if kb_text else "（当前查询未匹配到相关知识库条目）"}

**重要提示：** 如知识库内容不包含用户问题的答案，你必须拒答并引导联系HR。不要基于通用知识回答。"""


# ============================================================
# 路由
# ============================================================

@app.route("/")
def index():
    from flask import make_response
    resp = make_response(render_template_string(MAIN_HTML))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    query = data.get("query", "").strip()
    history = data.get("history", [])
    
    if not query:
        return jsonify({"error": "empty query"}), 400
    
    # 检索知识库
    kb_items = search_kb(query, top_k=4)
    
    # 识别意图 -> 推荐卡片
    intent = detect_intent(query)
    card = CARDS.get(intent) if intent else None
    
    # 构建消息
    messages = []
    for h in history[-6:]:  # 最近6轮
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": query})
    
    system_prompt = build_system_prompt(kb_items)
    
    def generate():
        import urllib.request, urllib.error
        
        payload = json.dumps({
            "model": "qwen-plus",
            "max_tokens": 1000,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": True,
        }).encode()
        
        req = urllib.request.Request(
            f"{QWEN_BASE_URL}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {QWEN_API_KEY}",
            },
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
                        buf = b""
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            obj = json.loads(payload)
                            text = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if text:
                                yield f"data:{json.dumps({'text': text})}\n\n"
                        except:
                            pass
        except Exception as e:
            yield f"data:{json.dumps({'text': f'AI服务暂时不可用，请稍后重试。（{str(e)[:50]}）'})}\n\n"
        
        # 发送卡片数据和引用来源
        citations = [{"id": item["id"], "policy": item["policy"], "q": item["q"]} for item in kb_items]
        yield f"data:{json.dumps({'done': True, 'card': card, 'citations': citations})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/kb", methods=["GET"])
def kb_list():
    category = request.args.get("category", "")
    keyword = request.args.get("q", "")
    items = KNOWLEDGE_BASE
    if category:
        items = [i for i in items if i["category"] == category]
    if keyword:
        items = [i for i in items if keyword in i["q"] or keyword in i["a"] or keyword in i.get("policy","")]
    return jsonify({"items": items, "total": len(items)})

@app.route("/api/kb", methods=["POST"])
def kb_add():
    data = request.json
    new_item = {
        "id": max(i["id"] for i in KNOWLEDGE_BASE) + 1,
        "category": data.get("category", "其他"),
        "policy": data.get("policy", ""),
        "q": data.get("q", ""),
        "a": data.get("a", ""),
        "tags": data.get("tags", []),
    }
    KNOWLEDGE_BASE.append(new_item)
    STATS["kb_articles"] = len(KNOWLEDGE_BASE)
    return jsonify({"success": True, "item": new_item})

@app.route("/api/kb/<int:item_id>", methods=["DELETE"])
def kb_delete(item_id):
    global KNOWLEDGE_BASE
    KNOWLEDGE_BASE = [i for i in KNOWLEDGE_BASE if i["id"] != item_id]
    STATS["kb_articles"] = len(KNOWLEDGE_BASE)
    return jsonify({"success": True})

@app.route("/api/applications", methods=["GET"])
def get_applications():
    status = request.args.get("status", "")
    items = APPLICATIONS
    if status:
        items = [a for a in items if a["status"] == status]
    return jsonify({"items": items, "total": len(items)})

@app.route("/api/applications", methods=["POST"])
def create_application():
    data = request.json
    new_app = {
        "id": f"APP{str(len(APPLICATIONS)+1).zfill(3)}",
        "type": data.get("type", ""),
        "applicant": data.get("applicant", "员工"),
        "dept": data.get("dept", "未知部门"),
        "status": "pending",
        "date": datetime.date.today().isoformat(),
        "note": data.get("note", ""),
    }
    APPLICATIONS.append(new_app)
    return jsonify({"success": True, "app": new_app})

@app.route("/api/applications/<app_id>/approve", methods=["POST"])
def approve_application(app_id):
    for app in APPLICATIONS:
        if app["id"] == app_id:
            app["status"] = "approved"
            return jsonify({"success": True})
    return jsonify({"error": "not found"}), 404

@app.route("/api/applications/<app_id>/reject", methods=["POST"])
def reject_application(app_id):
    for app in APPLICATIONS:
        if app["id"] == app_id:
            app["status"] = "rejected"
            return jsonify({"success": True})
    return jsonify({"error": "not found"}), 404

@app.route("/api/stats", methods=["GET"])
def get_stats():
    return jsonify(STATS)

# ============================================================
# 前端 HTML（单页应用）
# ============================================================
MAIN_HTML = open(os.path.join(os.path.dirname(__file__), "templates/index.html")).read()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8891"))
    app.run(host="127.0.0.1", port=port, debug=False)
