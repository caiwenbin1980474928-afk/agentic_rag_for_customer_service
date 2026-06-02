"""Generate the first-stage standard customer-service data package.

The generated package is intentionally deterministic and repo-local:

- 120 Markdown KB documents under ``data/kb/``
- Mock business records under ``data/mock/``
- A larger JSONL evaluation set under ``eval/testset_large.jsonl``
- A short data README under ``data/README.md``

Run from the project root:

    python -m scripts.generate_standard_data
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = ROOT / "data" / "kb"
MOCK_ROOT = ROOT / "data" / "mock"
EVAL_PATH = ROOT / "eval" / "testset_large.jsonl"
DATA_README = ROOT / "data" / "README.md"


CATEGORIES: dict[str, dict[str, object]] = {
    "presales": {
        "label": "售前咨询",
        "ticket": "PRESALES_CONSULT",
        "titles": [
            "手机类目选购与版本说明",
            "耳机音频类商品选购建议",
            "电脑与办公设备选购建议",
            "智能家电选购与安装前置条件",
            "服饰鞋包尺码与材质说明",
            "美妆个护商品适用人群说明",
            "食品生鲜购买限制与保鲜说明",
            "母婴用品选购注意事项",
            "运动户外商品规格说明",
            "图书文创商品购买说明",
            "商品库存与补货提醒规则",
            "商品真伪与官方质保承诺",
            "赠品与套装活动说明",
            "优惠券领取与使用规则",
            "优惠券不可用原因排查",
            "满减与跨店活动规则",
            "秒杀活动购买规则",
            "预售定金与尾款规则",
            "拼团与多人优惠规则",
            "会员等级与专属权益",
            "积分获取与抵扣规则",
            "价格保护申请规则",
            "企业采购售前咨询",
            "发票类型与开票前咨询",
            "售前人工升级与复杂需求登记",
        ],
    },
    "order": {
        "label": "售中订单",
        "ticket": "ORDER_SERVICE",
        "titles": [
            "下单流程与订单状态说明",
            "支付方式与到账确认",
            "支付失败排查流程",
            "重复扣款处理规则",
            "订单取消规则",
            "修改收货地址规则",
            "修改收货手机号规则",
            "修改发票信息规则",
            "订单备注与特殊要求处理",
            "合并发货与拆单发货规则",
            "预售订单履约规则",
            "尾款支付提醒与超时关闭",
            "订单审核失败处理",
            "风控拦截与身份核验说明",
            "超时未支付订单关闭规则",
            "缺货取消与补偿规则",
            "赠品漏发与补寄规则",
            "活动价争议处理规则",
            "优惠券未生效处理",
            "会员价未生效处理",
            "企业采购订单处理",
            "大件商品安装预约",
            "门店自提与核销规则",
            "订单拆包与部分发货说明",
            "售中人工升级与异常订单登记",
        ],
    },
    "logistics": {
        "label": "物流配送",
        "ticket": "LOGISTICS_TICKET",
        "titles": [
            "普通快递配送时效",
            "加急配送与次日达规则",
            "同城配送服务规则",
            "大件物流配送规则",
            "生鲜冷链配送规则",
            "偏远地区配送规则",
            "港澳台与海外配送限制",
            "运费与免邮规则",
            "偏远地区附加费说明",
            "发货时间与截单规则",
            "节假日发货安排",
            "物流单号查询方式",
            "物流停滞超过四十八小时处理",
            "催发货工单处理流程",
            "催派送工单处理流程",
            "包裹丢失处理流程",
            "包裹破损处理流程",
            "错发商品处理流程",
            "漏发商品处理流程",
            "已签收未收到处理流程",
            "快递柜与驿站签收争议",
            "用户拒收处理流程",
            "包裹退回商家处理",
            "物流改派地址规则",
            "物流投诉工单处理",
            "补发流程与时效",
            "物流赔付与补偿规则",
            "承运商异常公告处理",
            "高价值包裹签收规则",
            "物流人工升级与紧急工单",
        ],
    },
    "aftersales": {
        "label": "售后服务",
        "ticket": "AFTER_SALES_TICKET",
        "titles": [
            "七天无理由退货规则",
            "质量问题退换货规则",
            "换货申请处理流程",
            "仅退款申请处理流程",
            "退货退款申请处理流程",
            "维修申请处理流程",
            "整机保修政策",
            "延保服务使用规则",
            "人为损坏判定规则",
            "激活商品退货限制",
            "数码产品售后规则",
            "家电商品售后规则",
            "服饰尺码退换规则",
            "美妆拆封售后规则",
            "食品生鲜售后规则",
            "定制商品售后规则",
            "虚拟商品售后规则",
            "海外购售后规则",
            "赠品退回与折价规则",
            "发票作废与重开规则",
            "退款到账时间说明",
            "原路退回失败处理",
            "银行卡退款延迟处理",
            "信用卡退款周期说明",
            "售后申请入口说明",
            "售后凭证要求",
            "照片与视频凭证规范",
            "仓库质检流程",
            "质检不通过处理",
            "退货运费承担规则",
            "到付件拒收规则",
            "超出售后期处理",
            "投诉升级处理流程",
            "人工客服介入规则",
            "高价值商品售后审核",
            "异常账号与恶意售后处理",
            "售后工单状态说明",
            "售后撤销与重新申请",
            "部分退货退款规则",
            "售后人工升级与争议仲裁",
        ],
    },
}


QUESTION_PATTERNS = {
    "presales": [
        "这个商品适合什么人买？",
        "优惠券为什么不能用？",
        "现在下单还能参加活动吗？",
        "会员权益和积分怎么算？",
        "能不能申请价格保护？",
    ],
    "order": [
        "我想取消订单可以吗？",
        "收货地址填错了怎么改？",
        "支付失败但是扣款了怎么办？",
        "预售尾款忘记付了还能恢复吗？",
        "订单为什么被审核拦截？",
    ],
    "logistics": [
        "快递停了两天没有更新怎么办？",
        "包裹显示签收但我没收到怎么办？",
        "能不能改派到新地址？",
        "包裹破损了应该怎么处理？",
        "偏远地区大概多久能到？",
    ],
    "aftersales": [
        "七天无理由退货需要满足什么条件？",
        "商品有质量问题怎么申请换货？",
        "退款一般多久到账？",
        "质检不通过怎么办？",
        "超过售后期还能处理吗？",
    ],
}


def clean_filename(text: str) -> str:
    return text.replace("/", "或").replace(" ", "")


def category_terms(category: str, title: str, index: int) -> dict[str, str]:
    label = str(CATEGORIES[category]["label"])
    ticket = str(CATEGORIES[category]["ticket"])
    return {
        "label": label,
        "ticket": ticket,
        "scope": f"{label}场景中的「{title}」",
        "sla": ["2小时内", "4小时内", "1个工作日内", "24小时内"][index % 4],
        "limit": ["活动期、库存、区域", "订单状态、支付状态、实名核验", "承运商、地区、天气", "签收时间、商品状态、凭证"][index % 4],
        "risk": ["价格承诺", "订单资金", "物流履约", "退款或换货"][index % 4],
    }


TOPIC_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (("优惠券",), [
        "核对优惠券是否在有效期内，是否满足品类、金额、账号等级和活动渠道限制。",
        "同一订单内平台券、店铺券、会员券是否可叠加，以结算页展示为准。",
        "若用户下单后才发现未使用优惠券，通常不能补贴差价，可引导取消后重新下单，已发货订单不建议取消。",
    ]),
    (("价格保护", "保价"), [
        "保价以用户提交申请时的同款、同规格、同销售渠道价格为准。",
        "秒杀、限量券、赠品、直播间专属价、企业采购价通常不纳入普通保价。",
        "保价通过后一般退回差价，不改变原订单发票和售后周期。",
    ]),
    (("预售", "定金", "尾款"), [
        "预售订单需区分定金阶段、尾款阶段和现货发货阶段，不能混用普通订单规则。",
        "定金是否可退以活动页说明为准；尾款超时未付可能导致订单关闭。",
        "预售商品发货时间以商品页承诺为准，客服不能额外承诺提前发货。",
    ]),
    (("会员", "积分"), [
        "会员等级按近12个月消费、积分或平台规则计算，页面展示为准。",
        "积分抵扣通常存在比例、上限、有效期和不可抵扣品类限制。",
        "会员权益异常需核对账号、订单、活动入口和权益发放时间。",
    ]),
    (("支付", "扣款"), [
        "支付失败但用户反馈已扣款时，应先区分支付成功未同步和银行预授权占用。",
        "重复扣款需用户提供支付渠道、交易单号、扣款截图和订单号。",
        "资金类争议不得直接承诺退款成功，只能说明核实路径和预计处理时效。",
    ]),
    (("取消", "关闭"), [
        "未支付订单可自动关闭或用户主动取消；已支付订单是否可取消取决于发货状态。",
        "已出库、已揽收或生鲜定制订单通常不能直接取消，可引导拒收或售后。",
        "订单取消后优惠券、积分、赠品资格是否返还，以活动规则和系统结果为准。",
    ]),
    (("地址", "手机号", "改派"), [
        "未发货订单可优先尝试自助修改；已发货订单需要判断承运商是否支持改派。",
        "涉及跨省、市、偏远地区或冷链商品时，改派可能导致费用变化或无法处理。",
        "收货手机号修改需校验用户身份，避免影响签收和隐私安全。",
    ]),
    (("风控", "审核", "核验"), [
        "风控拦截可能来自支付异常、账号异常、收货信息异常或活动规则限制。",
        "客服只能说明需要核验，不能披露风控模型、命中规则或规避方法。",
        "用户补充身份或订单材料后，应进入人工复核，不建议反复引导用户重下单。",
    ]),
    (("发货", "配送时效", "物流单号"), [
        "发货时效受付款时间、仓库截单时间、库存位置和节假日影响。",
        "物流单号生成不等于承运商已揽收，轨迹通常会在揽收后更新。",
        "超过承诺发货时间仍未出库时，可创建催发货工单。",
    ]),
    (("物流停滞", "催派送", "催发货"), [
        "物流轨迹超过48小时无更新属于需要重点跟进的异常。",
        "先核对承运商、最新节点、停留时长和是否受天气或管制影响。",
        "普通催促可建P2工单；冷链、生鲜、高价值或用户投诉应提升为P1。",
    ]),
    (("包裹丢失", "已签收未收到", "快递柜", "驿站"), [
        "已签收未收到需核对签收人、签收地点、快递柜或驿站记录。",
        "用户需提供未收到说明、收货地址确认和必要时的小区监控或快递柜截图。",
        "承运商确认丢失后，再按补发、退款或赔付流程处理。",
    ]),
    (("破损", "错发", "漏发"), [
        "包裹破损建议用户保留外包装、面单、商品照片和开箱视频。",
        "错发或漏发需核对订单明细、仓库出库记录和用户收到的实物。",
        "责任确认前不能直接承诺赔付，可先登记工单并说明核实节点。",
    ]),
    (("冷链", "生鲜"), [
        "冷链和生鲜异常优先级高于普通包裹，需关注温控、时效和食品安全。",
        "若因延误影响品质，应优先评估退款、补发或人工专员介入。",
        "用户需提供外包装、温度状态、商品状态和签收时间。",
    ]),
    (("七天", "无理由"), [
        "七天无理由通常从签收次日开始计算，商品需保持不影响二次销售。",
        "食品、贴身衣物、定制商品、虚拟商品和已激活商品可能不支持无理由退货。",
        "用户需保留商品本体、配件、赠品、包装和发票。",
    ]),
    (("质量问题", "换货", "维修", "保修", "延保"), [
        "质量问题需先判断是否在售后期或保修期内，并排除人为损坏。",
        "换货、维修和退货退款的处理方式取决于商品类目、故障程度和库存情况。",
        "高价值商品或边界故障应进入人工复核，不能仅凭文字描述定责。",
    ]),
    (("退款", "退货退款", "仅退款", "原路退回", "信用卡"), [
        "退款通常按原支付路径退回，不同支付渠道到账时间不同。",
        "退货退款需仓库签收并质检通过后才进入退款流程。",
        "原路退回失败时，需要用户按平台提示补充收款信息或等待人工处理。",
    ]),
    (("质检", "人为损坏", "凭证", "照片", "视频"), [
        "质检会核对商品外观、功能、配件、序列号、包装和用户凭证。",
        "人为损坏、进水、摔裂、私拆、缺少关键配件可能导致售后驳回。",
        "用户对质检结果有异议时，应补充证据并转人工复核。",
    ]),
    (("发票",), [
        "发票处理需核对订单完成状态、发票类型、抬头、税号和邮箱。",
        "退货后原发票可能需要作废；部分退货通常按实际成交金额重开。",
        "跨年度、专票资质、纸质票补寄等场景建议创建发票工单。",
    ]),
    (("投诉", "人工", "争议", "仲裁"), [
        "用户明确要求投诉、人工、经理或监管渠道时，应优先进入升级流程。",
        "投诉工单需记录用户核心诉求、已给方案、证据材料和期望补偿。",
        "争议处理不得刺激用户情绪，应说明专员会在承诺时效内反馈。",
    ]),
]


def topic_notes(title: str) -> str:
    notes: list[str] = []
    for keywords, rules in TOPIC_RULES:
        if any(keyword in title for keyword in keywords):
            notes.extend(rules)
    if not notes:
        notes = [
            f"{title}应先判断是否属于平台可处理范围，再确认是否需要具体订单或工单信息。",
            "对通用规则可以直接说明，对实时状态、费用、赔付和责任归属需查询系统或转人工。",
            "回答应包含条件、步骤、材料、时效和无法处理时的替代路径。",
        ]
    return "\n".join(f"- {note}" for note in notes[:6])


def build_doc(category: str, title: str, index: int) -> str:
    t = category_terms(category, title, index)
    examples = [
        f"{title}具体怎么处理？",
        f"{title}需要我提供什么信息？",
        f"{title}哪些情况必须转人工？",
        f"{title}大概要多久有结果？",
        QUESTION_PATTERNS[category][index % len(QUESTION_PATTERNS[category])],
    ]
    ask_examples = "\n".join(f"- {q}" for q in examples)
    direct_cases = {
        "presales": "用户只是咨询规格、活动、会员、发票或库存时，可先按本规则说明；涉及最终库存、实时价格、特殊大客户折扣时，需要以系统页面为准。",
        "order": "订单未支付、待审核、待发货、部分发货等状态可直接解释；涉及扣款争议、风控拦截、企业采购审批时，应引导登记或转人工。",
        "logistics": "普通时效、运费、查询方式和常规异常可直接答复；包裹丢失、已签收未收到、冷链延误、高价值商品异常必须创建或查询物流工单。",
        "aftersales": "在售后期内且凭证齐全的常规申请可直接指导；高价值商品、质量争议、质检不通过、用户强烈不满必须升级人工或创建售后工单。",
    }[category]
    handoff_cases = {
        "presales": "用户要求保留库存、申请特殊折扣、批量采购议价、页面价格与活动规则冲突，或明确要求人工确认时。",
        "order": "存在重复扣款、订单被风控拦截、收货信息无法自助修改、用户要求恢复关闭订单，或涉及企业合同订单时。",
        "logistics": "物流停滞超过48小时、已签收未收到、包裹破损、错发漏发、生鲜冷链延误、用户要求投诉承运商时。",
        "aftersales": "超过售后期、凭证缺失、质检争议、人为损坏争议、退款迟迟未到账、用户要求投诉或仲裁时。",
    }[category]
    return f"""# {title}

## 适用场景

本规则适用于{t["scope"]}。客服在识别用户意图时，应先判断用户是在咨询通用政策，还是在查询具体订单、物流工单、售后工单或发票工单。通用政策可以直接基于知识库回答；涉及具体单号、实时状态、赔付金额或人工裁定的内容，需要调用对应工具或升级人工。

常见用户问法包括：
{ask_examples}

## 客服处理原则

处理此类问题时，优先使用页面展示、订单状态和平台规则三类依据。客服不得承诺资料中没有写明的价格、补偿、到货日期或退款到账时间。若用户提供的信息不足，应先补充询问关键字段，例如订单号、商品名称、签收时间、支付方式、收货地区、问题照片或工单编号。

本场景的一般服务时效为{t["sla"]}给出首次处理意见。若存在{t["limit"]}等限制，需要向用户说明限制原因，并给出下一步可操作路径，避免只说“不能处理”。

## 主题要点

{topic_notes(title)}

## 标准处理流程

1. 复述用户诉求，确认用户关注的是政策咨询、订单处理、物流异常还是售后申请。
2. 检查是否包含订单号、物流工单号、售后工单号或发票工单号；如果包含，应优先查询工具。
3. 如果是通用问题，按本规则说明适用条件、处理步骤、所需材料和预计时效。
4. 如果用户描述与规则边界不完全一致，先说明可判断部分，再提示需要人工核实的部分。
5. 对可能产生{t["risk"]}风险的请求，禁止口头承诺最终结果，只能说明平台会按规则审核。

## 需要用户提供的信息

- 订单号或工单号；没有单号时，需要用户说明下单手机号后四位或商品名称。
- 商品类目、购买时间、签收时间和当前订单状态。
- 问题发生时间、页面截图、物流轨迹截图、商品照片或视频凭证。
- 用户期望的处理方式，例如取消、改地址、催发货、补发、退款、换货、维修或投诉。

## 可直接答复的情况

{direct_cases}

可直接答复时，客服应给出明确步骤，例如在 App 的「我的订单」进入对应订单，再点击「申请售后」「查看物流」「修改地址」「申请发票」等入口。若入口在当前状态不可见，应说明可能原因，例如订单已发货、活动已结束、售后期已过、发票已开具或商品不支持该服务。

## 必须转人工或建工单的情况

{handoff_cases}

遇到必须转人工的情况，应告知用户已进入人工处理范围，并说明预计响应时间。涉及物流异常时建议创建物流工单；涉及退换修争议时建议创建售后工单；涉及发票抬头、税号或跨年度重开时建议创建发票工单；涉及投诉升级时建议创建投诉工单。

## 示例话术

可以这样回复用户：您好，这类问题需要先看订单或工单当前状态。如果只是咨询规则，我可以先按平台政策给您说明；如果您已经有订单号或工单号，请发给我，我会帮您查询当前进度。对于需要审核或人工判断的部分，我不会直接承诺最终结果，但会告诉您下一步该怎么提交和预计多久有反馈。

## 相关工单类型

- 推荐工单类型：{t["ticket"]}
- 可关联字段：订单号、商品类目、用户诉求、当前状态、凭证材料、期望处理方式
- 升级优先级：普通咨询为 P3，影响履约或退款为 P2，投诉、高价值订单、冷链或安全问题为 P1
"""


def write_kb() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for category, meta in CATEGORIES.items():
        folder = KB_ROOT / category
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
        titles = list(meta["titles"])
        for i, title in enumerate(titles, 1):
            filename = f"{i:03d}_{clean_filename(title)}.md"
            path = folder / filename
            path.write_text(build_doc(category, str(title), i), encoding="utf-8")
            records.append({"category": category, "title": str(title), "path": str(path.relative_to(ROOT))})
    return records


def make_orders() -> list[dict[str, object]]:
    statuses = ["待支付", "待发货", "已发货", "部分发货", "已签收", "售后中", "已取消"]
    carriers = ["顺丰", "京东物流", "中通", "德邦", "冷链专送"]
    cities = ["上海", "杭州", "广州", "北京", "成都", "武汉", "西安", "深圳"]
    orders = []
    for i in range(1, 101):
        status = statuses[i % len(statuses)]
        order_id = f"A{1000 + i}"
        orders.append({
            "order_id": order_id,
            "user_phone_tail": f"{1380 + i:04d}"[-4:],
            "category": ["手机", "耳机", "家电", "服饰", "美妆", "食品", "电脑配件"][i % 7],
            "amount": 99 + i * 13,
            "status": status,
            "created_at": f"2026-05-{(i % 27) + 1:02d} 10:{i % 60:02d}",
            "ship_to": cities[i % len(cities)],
            "carrier": carriers[i % len(carriers)] if status in {"已发货", "部分发货", "已签收", "售后中"} else None,
            "tracking_no": f"SF{2026050000 + i}" if status in {"已发货", "部分发货", "已签收", "售后中"} else None,
            "summary": f"{order_id} 当前状态为{status}，可按售中或物流规则继续处理。",
        })
    return orders


def make_logistics_tickets() -> list[dict[str, object]]:
    types = ["物流停滞", "已签收未收到", "包裹破损", "催派送", "催发货", "冷链延误", "错发漏发", "改派地址"]
    statuses = ["待受理", "处理中", "等待承运商反馈", "待用户补充凭证", "已补发", "已关闭"]
    tickets = []
    for i in range(1, 51):
        ticket_id = f"L{2000 + i}"
        order_id = f"A{1000 + ((i * 3) % 100 or 100)}"
        typ = types[i % len(types)]
        tickets.append({
            "ticket_id": ticket_id,
            "order_id": order_id,
            "type": typ,
            "status": statuses[i % len(statuses)],
            "priority": "P1" if typ in {"冷链延误", "已签收未收到", "包裹破损"} else "P2",
            "created_at": f"2026-05-{(i % 27) + 1:02d} 14:{(i * 7) % 60:02d}",
            "last_update": f"2026-05-{((i + 2) % 27) + 1:02d} 09:{(i * 5) % 60:02d}",
            "carrier": ["顺丰", "京东物流", "中通", "德邦", "冷链专送"][i % 5],
            "tracking_no": f"SF{2026060000 + i}",
            "summary": f"{typ}工单，用户反馈订单 {order_id} 存在配送异常。",
            "next_action": "已催促承运商，预计24小时内反馈；若超时未解决，将评估补发或退款。",
        })
    return tickets


def make_after_sales_tickets() -> list[dict[str, object]]:
    types = ["退货退款", "换货", "维修", "仅退款", "质检争议", "退款未到账", "发票作废", "投诉升级"]
    statuses = ["待审核", "待用户寄回", "仓库质检中", "退款处理中", "待人工复核", "已完成", "已驳回"]
    tickets = []
    for i in range(1, 51):
        ticket_id = f"S{3000 + i}"
        order_id = f"A{1000 + ((i * 5) % 100 or 100)}"
        typ = types[i % len(types)]
        tickets.append({
            "ticket_id": ticket_id,
            "order_id": order_id,
            "type": typ,
            "status": statuses[i % len(statuses)],
            "priority": "P1" if typ in {"质检争议", "投诉升级", "退款未到账"} else "P2",
            "created_at": f"2026-05-{(i % 27) + 1:02d} 16:{(i * 11) % 60:02d}",
            "last_update": f"2026-05-{((i + 3) % 27) + 1:02d} 11:{(i * 13) % 60:02d}",
            "item_condition": ["未拆封", "已拆封", "外观完好", "疑似人为损坏", "缺少配件"][i % 5],
            "summary": f"{typ}工单，关联订单 {order_id}，需按售后规则核验材料和时效。",
            "next_action": "请用户补充凭证或等待人工复核；审核通过后按原路退款、换货或维修流程处理。",
        })
    return tickets


def make_invoice_tickets() -> list[dict[str, object]]:
    tickets = []
    for i in range(1, 21):
        tickets.append({
            "ticket_id": f"F{4000 + i}",
            "order_id": f"A{1000 + ((i * 7) % 100 or 100)}",
            "type": ["抬头修改", "税号修改", "专票资质审核", "纸质发票补寄", "退货发票作废"][i % 5],
            "status": ["待审核", "处理中", "待用户补充资质", "已开具", "已驳回"][i % 5],
            "created_at": f"2026-05-{(i % 27) + 1:02d} 12:{(i * 9) % 60:02d}",
            "summary": "发票工单需核对订单完成状态、抬头、税号、邮箱和跨年度限制。",
        })
    return tickets


def make_complaint_tickets() -> list[dict[str, object]]:
    tickets = []
    for i in range(1, 21):
        tickets.append({
            "ticket_id": f"C{5000 + i}",
            "order_id": f"A{1000 + ((i * 9) % 100 or 100)}",
            "type": ["服务态度", "物流延误", "售后争议", "价格争议", "高价值订单"][i % 5],
            "status": ["待受理", "专员处理中", "等待用户确认", "已补偿", "已关闭"][i % 5],
            "priority": "P1" if i % 3 == 0 else "P2",
            "created_at": f"2026-05-{(i % 27) + 1:02d} 18:{(i * 3) % 60:02d}",
            "summary": "投诉工单需记录用户诉求、已沟通方案、期望补偿和最终处理结论。",
        })
    return tickets


def write_mock_data() -> None:
    MOCK_ROOT.mkdir(parents=True, exist_ok=True)
    datasets = {
        "orders.json": make_orders(),
        "logistics_tickets.json": make_logistics_tickets(),
        "after_sales_tickets.json": make_after_sales_tickets(),
        "invoice_tickets.json": make_invoice_tickets(),
        "complaint_tickets.json": make_complaint_tickets(),
    }
    for name, data in datasets.items():
        (MOCK_ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_eval(records: list[dict[str, str]]) -> None:
    questions = []
    i = 1
    for rec in records:
        category = rec["category"]
        title = rec["title"]
        route = "kb"
        patterns = [
            f"{title}具体怎么处理？",
            f"遇到{title}，我需要准备哪些信息？",
        ]
        for pattern in patterns:
            questions.append({
                "id": f"large_{i:03d}",
                "question": pattern,
                "category": category,
                "expected_route": route,
                "expected_sources": [Path(rec["path"]).name],
                "answer_keywords": [title[:4], "规则", "处理"],
            })
            i += 1
    tool_cases = [
        ("我的订单 A1007 现在是什么状态？", "tool", "order"),
        ("帮我查一下订单 A1032 到哪了", "tool", "order"),
        ("物流工单 L2003 处理到哪一步了？", "tool", "logistics"),
        ("L2016 这个包裹破损工单有结果了吗？", "tool", "logistics"),
        ("售后工单 S3008 为什么还没退款？", "tool", "aftersales"),
        ("S3021 质检争议现在怎么处理？", "tool", "aftersales"),
        ("发票工单 F4009 能不能加急？", "tool", "invoice"),
        ("投诉工单 C5012 有没有专员处理？", "tool", "complaint"),
    ]
    for q, route, category in tool_cases:
        questions.append({
            "id": f"large_{i:03d}",
            "question": q,
            "category": category,
            "expected_route": route,
            "expected_sources": [],
            "answer_keywords": ["状态", "处理", "工单"],
        })
        i += 1
    misc = [
        ("你好，你能帮我做什么？", "chitchat", "chitchat"),
        ("你们老板是谁？", "chitchat", "refuse"),
        ("今天天气怎么样？", "chitchat", "refuse"),
        ("我要转人工", "handoff", "handoff"),
        ("我不想和机器人说话，找人工客服", "handoff", "handoff"),
        ("我要投诉，叫你们经理来", "handoff", "handoff"),
    ]
    for q, route, category in misc:
        questions.append({
            "id": f"large_{i:03d}",
            "question": q,
            "category": category,
            "expected_route": route,
            "expected_sources": [],
            "answer_keywords": [],
        })
        i += 1
    EVAL_PATH.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in questions) + "\n",
        encoding="utf-8",
    )


def write_data_readme(records: list[dict[str, str]]) -> None:
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec["category"]] = counts.get(rec["category"], 0) + 1
    DATA_README.write_text(f"""# 标准客服数据包

本目录是一阶段扩展数据包，用于把 Demo 从 5 篇示例文档扩展为覆盖售前、售中、物流和售后的课程/答辩版知识库。

## 目录

- `kb/presales/`：售前咨询，{counts.get("presales", 0)} 篇
- `kb/order/`：售中订单，{counts.get("order", 0)} 篇
- `kb/logistics/`：物流配送，{counts.get("logistics", 0)} 篇
- `kb/aftersales/`：售后服务，{counts.get("aftersales", 0)} 篇
- `mock/`：订单、物流工单、售后工单、发票工单、投诉工单 mock 数据
- `../eval/testset_large.jsonl`：大评测集，覆盖 KB、工具、闲聊、拒答和转人工

## 使用方式

将 `.env` 中的 `DOCS_DIR` 改为：

```env
DOCS_DIR=./data/kb
```

然后重建索引：

```bash
python -m scripts.ingest
```

## 数据设计

每篇知识库文档使用统一结构：适用场景、客服处理原则、标准处理流程、所需信息、可直接答复、必须转人工或建工单、示例话术、相关工单类型。这样切块后会保留清晰标题，便于 RAG 引用和答辩展示。
""", encoding="utf-8")


def main() -> None:
    records = write_kb()
    write_mock_data()
    write_eval(records)
    write_data_readme(records)
    print(f"generated {len(records)} KB docs")
    print(f"generated mock data in {MOCK_ROOT.relative_to(ROOT)}")
    print(f"generated eval set at {EVAL_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
