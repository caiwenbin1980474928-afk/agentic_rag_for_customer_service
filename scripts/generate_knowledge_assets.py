"""Generate a governed knowledge asset tree from the course KB.

This is the next step after ``data/kb``: the same customer-service knowledge is
organized by operational role instead of just by business category.

Output:

    data/knowledge/
      policies/     customer-safe policy documents with front matter
      sop/          internal handling procedures
      scripts/      reusable customer-facing response scripts
      tables/       structured rule tables
      tool_specs/   mock backend lookup contracts
      safety/       safety and escalation guardrails
      changelog/    version records
"""
from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_KB = ROOT / "data" / "kb"
OUT = ROOT / "data" / "knowledge"

STAGES = {
    "presales": "售前咨询",
    "order": "售中订单",
    "logistics": "物流配送",
    "aftersales": "售后服务",
}

OWNERS = {
    "presales": "商品运营部",
    "order": "订单履约部",
    "logistics": "物流运营部",
    "aftersales": "售后运营部",
}

H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ["policies", "sop", "scripts", "tables", "tool_specs", "safety", "changelog"]:
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    policy_count = write_policies()
    write_sop()
    write_scripts()
    write_tables()
    write_tool_specs()
    write_safety()
    write_changelog(policy_count)
    write_readme(policy_count)
    print(f"generated governed knowledge assets in {OUT.relative_to(ROOT)}")
    print(f"policies: {policy_count}")


def write_policies() -> int:
    count = 0
    for category, stage in STAGES.items():
        source_dir = SOURCE_KB / category
        target_dir = OUT / "policies" / category
        target_dir.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(sorted(source_dir.glob("*.md")), 1):
            if source.stem.endswith((" 2", " 3")):
                continue
            text = source.read_text(encoding="utf-8")
            title = extract_title(text, source.stem)
            doc_id = f"POL_{category.upper()}_{index:03d}"
            front_matter = {
                "doc_id": doc_id,
                "doc_type": "policy",
                "title": title,
                "category": category,
                "business_stage": stage,
                "version": "v2026.06",
                "effective_from": "2026-06-01",
                "effective_to": "",
                "owner": OWNERS[category],
                "auditor": "客服质检组",
                "visibility": "customer_safe",
                "priority": "80",
                "source_system": "standard_kb_seed",
            }
            (target_dir / source.name).write_text(render_front_matter(front_matter) + text.strip() + "\n", encoding="utf-8")
            count += 1
    return count


def write_sop() -> None:
    sops = {
        "presales/presales_consultation_flow.md": (
            "售前咨询统一处理 SOP",
            "presales",
            [
                "识别用户是在问商品、活动、优惠、库存、会员还是企业采购。",
                "优先给出可公开规则；涉及实时库存、页面价格、特殊折扣时提示以系统页面为准。",
                "用户提供商品链接、预算、使用场景后，可给出选购建议，但不能承诺最终库存或活动资格。",
                "批量采购、特殊折扣、保留库存、页面规则冲突必须升级人工。",
            ],
        ),
        "order/order_exception_flow.md": (
            "售中订单异常处理 SOP",
            "order",
            [
                "先确认订单号、支付状态、发货状态和用户诉求。",
                "未支付订单按普通取消或重新下单处理；已支付订单需区分待审核、待出库、已发货。",
                "重复扣款、风控拦截、企业订单审批、恢复关闭订单必须走人工复核。",
                "涉及资金时不得承诺退款必成，只能说明核实路径和预计反馈时间。",
            ],
        ),
        "logistics/logistics_exception_flow.md": (
            "物流异常工单处理 SOP",
            "logistics",
            [
                "先查询订单和物流轨迹，记录承运商、运单号、最新节点和停滞时长。",
                "物流停滞超过48小时、已签收未收到、破损、丢失、错发漏发应创建物流工单。",
                "冷链、生鲜、高价值包裹和用户投诉默认提升优先级。",
                "承运商未确认责任前不得承诺赔偿金额，可说明补发或退款需审核。",
            ],
        ),
        "aftersales/aftersales_dispute_flow.md": (
            "售后争议与人工复核 SOP",
            "aftersales",
            [
                "先确认签收时间、商品类目、售后类型、凭证材料和当前工单状态。",
                "常规售后可指导用户提交申请；质检争议、高价值商品、人为损坏争议必须人工复核。",
                "退款、换货、维修结果以审核和质检为准，客服不能提前承诺必过。",
                "用户强烈不满或要求投诉时，创建投诉工单并记录诉求、证据和期望方案。",
            ],
        ),
    }
    for rel_path, (title, category, steps) in sops.items():
        path = OUT / "sop" / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fm = {
            "doc_id": f"SOP_{category.upper()}",
            "doc_type": "sop",
            "title": title,
            "category": category,
            "business_stage": STAGES[category],
            "version": "v2026.06",
            "effective_from": "2026-06-01",
            "owner": OWNERS[category],
            "auditor": "客服质检组",
            "visibility": "internal",
            "priority": "90",
        }
        body = [f"# {title}", "", "## 适用场景", "", f"适用于{STAGES[category]}中的复杂、异常或需要跨系统核验的问题。", "", "## 标准处理流程", ""]
        body.extend(f"{i}. {step}" for i, step in enumerate(steps, 1))
        body.extend([
            "",
            "## 必须升级的情况",
            "",
            "- 涉及资金、赔付、风控、质检争议、投诉或高价值订单。",
            "- 用户明确要求人工、主管、投诉或监管渠道。",
            "- 知识库政策与系统状态不一致。",
        ])
        path.write_text(render_front_matter(fm) + "\n".join(body) + "\n", encoding="utf-8")


def write_scripts() -> None:
    script_dir = OUT / "scripts"
    scripts = {
        "refund_scripts.yaml": {
            "title": "退款与售后话术",
            "category": "aftersales",
            "normal": "您好，退款会在审核通过后按原支付路径退回，具体到账时间受支付渠道影响。",
            "missing_info": "麻烦您提供订单号、签收时间和问题凭证，我先帮您判断适用的售后路径。",
            "handoff": "这个情况涉及人工审核，我会为您转接专员继续处理。",
        },
        "logistics_scripts.yaml": {
            "title": "物流异常话术",
            "category": "logistics",
            "normal": "我先帮您看物流轨迹。如果超过48小时没有更新，会建议创建物流工单催促承运商。",
            "missing_info": "麻烦您提供订单号或物流工单号，我需要核对承运商和最新轨迹。",
            "handoff": "这个物流异常需要人工跟进承运商，我会帮您升级处理。",
        },
        "coupon_scripts.yaml": {
            "title": "优惠券与活动话术",
            "category": "presales",
            "normal": "优惠券是否可用要看有效期、适用品类、门槛金额和结算页展示。",
            "missing_info": "麻烦您提供优惠券名称、商品链接和结算页截图，我帮您排查原因。",
            "handoff": "如果页面活动规则互相冲突，需要人工核实最终适用规则。",
        },
        "order_scripts.yaml": {
            "title": "订单异常话术",
            "category": "order",
            "normal": "订单处理需要看当前状态。未发货和已发货的可操作范围不一样。",
            "missing_info": "麻烦您提供订单号，我先核对支付、审核和发货状态。",
            "handoff": "这个订单涉及异常审核或资金问题，我会转人工为您进一步核实。",
        },
    }
    for filename, data in scripts.items():
        path = script_dir / filename
        lines = [
            f"doc_id: SCRIPT_{data['category'].upper()}",
            "doc_type: script",
            f"title: {data['title']}",
            f"category: {data['category']}",
            f"business_stage: {STAGES[data['category']]}",
            "version: v2026.06",
            "visibility: customer_safe",
            "priority: 70",
            f"normal: {data['normal']}",
            f"missing_info: {data['missing_info']}",
            f"handoff: {data['handoff']}",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tables() -> None:
    table_dir = OUT / "tables"
    write_csv(table_dir / "refund_channel_sla.csv", [
        ["channel", "refund_type", "expected_sla", "customer_safe_note", "requires_handoff"],
        ["微信支付", "仅退款", "1-3个工作日", "审核通过后原路退回", "false"],
        ["支付宝", "退货退款", "3-5个工作日", "仓库签收并质检通过后原路退回", "false"],
        ["银行卡", "退款", "3-7个工作日", "以银行入账时间为准", "false"],
        ["信用卡", "退款", "7-15天", "账单日可能影响展示时间", "false"],
        ["原路退回失败", "退款", "人工处理", "需补充收款信息或等待专员核实", "true"],
    ])
    write_csv(table_dir / "category_return_rules.csv", [
        ["category", "support_7days", "quality_issue_supported", "required_condition", "handoff_if"],
        ["耳机", "true", "true", "包装配件齐全且不影响二次销售", "质量争议或人为损坏"],
        ["食品生鲜", "false", "true", "质量问题需提供照片和签收时间", "冷链延误或食品安全问题"],
        ["定制商品", "false", "true", "以定制页说明为准", "用户争议或页面说明冲突"],
        ["虚拟商品", "false", "limited", "未激活前按商品页规则", "激活状态争议"],
        ["家电", "true", "true", "需核对安装、外观和序列号", "高价值或安装争议"],
    ])
    write_csv(table_dir / "logistics_sla_by_region.csv", [
        ["region", "normal_sla", "express_sla", "remote_fee", "handoff_if"],
        ["华东", "1-2天", "次日达", "0", "超过48小时无轨迹"],
        ["华南", "2-3天", "部分城市次日达", "0", "承运商异常或冷链延误"],
        ["西南西北", "3-5天", "不支持", "可能收取", "超过承诺时效"],
        ["新疆西藏青海部分地区", "5-8天", "不支持", "15-30元", "用户投诉或高价值包裹"],
    ])
    write_csv(table_dir / "ticket_priority_rules.csv", [
        ["ticket_type", "default_priority", "upgrade_to_p1_when", "first_response_sla"],
        ["物流工单", "P2", "冷链/生鲜/高价值/投诉/丢失", "4小时"],
        ["售后工单", "P2", "质检争议/退款未到账/高价值/投诉", "4小时"],
        ["发票工单", "P3", "专票资质/跨年度/企业急用", "1个工作日"],
        ["投诉工单", "P1", "默认P1", "2小时"],
    ])


def write_tool_specs() -> None:
    specs = [
        ("order_lookup.md", "订单查询工具", "A 开头订单号", "orders.json", "查询订单状态、支付状态、承运商、运单号和摘要。"),
        ("logistics_ticket_lookup.md", "物流工单查询工具", "L 开头物流工单号", "logistics_tickets.json", "查询物流异常类型、优先级、处理状态和下一步动作。"),
        ("after_sales_ticket_lookup.md", "售后工单查询工具", "S 开头售后工单号", "after_sales_tickets.json", "查询退换修、质检、退款和争议处理进度。"),
        ("invoice_ticket_lookup.md", "发票工单查询工具", "F 开头发票工单号", "invoice_tickets.json", "查询抬头、税号、专票、纸票补寄和发票作废状态。"),
        ("complaint_ticket_lookup.md", "投诉工单查询工具", "C 开头投诉工单号", "complaint_tickets.json", "查询投诉类型、优先级、专员处理状态和处理摘要。"),
    ]
    for filename, title, trigger, source, purpose in specs:
        path = OUT / "tool_specs" / filename
        fm = {
            "doc_id": f"TOOL_{path.stem.upper()}",
            "doc_type": "tool_spec",
            "title": title,
            "category": "tool",
            "business_stage": "工具调用",
            "version": "v2026.06",
            "visibility": "internal",
            "priority": "95",
        }
        body = f"""# {title}

## 触发条件

用户问题包含{trigger}，或明确要求查询实时进度时，必须调用工具，不能只检索知识库。

## 数据来源

`data/mock/{source}`

## 工具用途

{purpose}

## 安全边界

工具未命中时，应提示用户核对编号，不要编造状态。工具返回结果与政策文档冲突时，优先说明当前系统状态，并建议人工核实。
"""
        path.write_text(render_front_matter(fm) + body, encoding="utf-8")


def write_safety() -> None:
    rules = {
        "answer_commitment_guardrails.md": (
            "客服回答承诺边界",
            [
                "不得承诺退款一定通过、赔付一定成功或换货一定有库存。",
                "不得承诺具体到账时间，只能说明审核通过后的常规时效。",
                "不得承诺承运商一定在某个时间送达。",
                "不得在工具未命中时编造订单、物流或工单状态。",
            ],
        ),
        "privacy_and_identity.md": (
            "隐私与身份核验边界",
            [
                "涉及手机号、地址、支付、发票税号等敏感信息时，只能提示用户在官方入口提交。",
                "不能在对话中完整展示用户手机号、地址、支付流水或身份证件。",
                "修改地址、手机号、企业发票和退款账户必须通过系统校验或人工处理。",
            ],
        ),
        "risk_and_fraud_boundary.md": (
            "风控与异常账号边界",
            [
                "不得解释具体风控命中规则、模型特征或规避方式。",
                "异常账号、恶意售后、批量套利和高风险支付必须人工复核。",
                "可以说明需要核验订单和账号状态，但不能透露内部判断细节。",
            ],
        ),
        "mandatory_handoff_rules.md": (
            "必须转人工规则",
            [
                "用户明确要求人工、投诉、主管、监管渠道时，必须进入人工或投诉流程。",
                "高价值订单、冷链生鲜安全、包裹丢失、质检争议、退款长期未到账必须升级。",
                "知识库规则与工具状态冲突时，应转人工核实。",
            ],
        ),
    }
    for filename, (title, bullets) in rules.items():
        fm = {
            "doc_id": f"SAFE_{Path(filename).stem.upper()}",
            "doc_type": "safety",
            "title": title,
            "category": "safety",
            "business_stage": "安全边界",
            "version": "v2026.06",
            "visibility": "internal",
            "priority": "100",
        }
        body = [f"# {title}", "", "## 安全规则", ""]
        body.extend(f"- {b}" for b in bullets)
        body.extend(["", "## 处理要求", "", "当用户诉求触碰以上边界时，回答必须保守，并优先说明需要人工核实。"])
        (OUT / "safety" / filename).write_text(render_front_matter(fm) + "\n".join(body) + "\n", encoding="utf-8")


def write_changelog(policy_count: int) -> None:
    path = OUT / "changelog" / "2026-06.md"
    fm = {
        "doc_id": "CHANGELOG_2026_06",
        "doc_type": "changelog",
        "title": "2026-06 知识库版本记录",
        "category": "governance",
        "business_stage": "知识治理",
        "version": "v2026.06",
        "visibility": "internal",
        "priority": "60",
    }
    body = f"""# 2026-06 知识库版本记录

## 发布内容

- 从课程版 `data/kb` 迁移 {policy_count} 篇 customer-safe policy 文档。
- 新增 SOP、话术、结构化规则表、工具说明和安全边界。
- 所有 policy 文档增加版本、生效时间、owner、auditor、visibility 和 priority 元数据。

## 生效范围

适用于当前 Agentic RAG 客服 Demo 的售前、售中、物流、售后和工具调用演示。
"""
    path.write_text(render_front_matter(fm) + body, encoding="utf-8")


def write_readme(policy_count: int) -> None:
    (OUT / "README.md").write_text(f"""# Governed Customer-Service Knowledge

这是生产形态的知识资产目录，不再只是给模型看的 markdown 集合。

## Asset Types

- `policies/`: customer-safe 政策文档，当前 {policy_count} 篇
- `sop/`: 内部客服处理流程
- `scripts/`: 可复用客服话术
- `tables/`: 结构化规则表
- `tool_specs/`: 工具调用契约
- `safety/`: 禁止承诺、隐私、风控、强制转人工规则
- `changelog/`: 版本与生效记录

## Metadata

核心资产包含 `doc_id`, `doc_type`, `category`, `business_stage`, `version`, `effective_from`, `owner`, `auditor`, `visibility`, `priority` 等元数据，供检索、过滤、rerank、审计和答辩展示使用。
""", encoding="utf-8")


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def extract_title(text: str, fallback: str) -> str:
    match = H1_RE.search(text)
    return match.group(1).strip() if match else fallback


def render_front_matter(data: dict[str, str]) -> str:
    lines = ["---"]
    lines.extend(f"{key}: {value}" for key, value in data.items())
    lines.append("---")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
