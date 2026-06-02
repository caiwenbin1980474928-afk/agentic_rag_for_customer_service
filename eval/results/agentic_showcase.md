# Agentic RAG Showcase Eval

## Metrics

| metric | value |
| --- | ---: |
| n_cases | 11 |
| n_distinguishing_cases | 11 |
| n_errors | 0 |
| distinguishing_rate | 1.000 |
| error_rate | 0.000 |
| avg_distinct_signatures | 3.273 |

## Cases

### ag_008 · tool_order

**Question:** 查一下订单 A1100 的快递公司和单号

**Focus:** 实时订单状态，E0不能查工具，E1+应调用订单工具

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:下单流程与订单状态说明/overview<br>policy:支付失败排查流程/overview<br>policy:优惠券不可用原因排查/overview | 很抱歉，根据我们现有的资料和工具，我无法直接查询到订单 A1100 的快递公司和单号信息。这类涉及具体订单信息的问题需要调用系统工具或升级人工服务来处理。建议您联系我们的客服团队，他们将能够帮助您查询订单的快递公司和单号信息。 |
| e1 | tool | router -> tool_call -> generate | True / True |  | 好的，订单A1100的快递公司是顺丰，快递单号是SF2026050100。 |
| e2 | tool | router -> tool_call -> generate | True / True |  | 好的，订单A1100的快递公司是顺丰，快递单号是SF2026050100。 |
| full | tool | router -> tool_call -> generate -> reflect | True / True |  | 好的，订单A1100的快递公司是顺丰，快递单号是SF2026050100。 |

### ag_009 · tool_logistics

**Question:** 物流工单 L2003 处理到哪一步了？

**Focus:** 实时物流工单，E0不能查工具，E1+应调用物流工单工具

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:物流单号查询方式/escalation<br>policy:物流投诉工单处理/escalation<br>policy:物流单号查询方式/overview | 您好，关于物流工单 L2003 的处理进度，这类问题需要查看订单或工单的具体状态。如果只是咨询规则，我可以先按平台政策给您说明；如果您已经有订单号或工单号，请发给我，我会帮您查询当前进度。对于需要审核或人工判断的部分，我不会直接承诺最终结果，但会告诉您下一步该怎么提交和预计多久有反馈。 |
| e1 | tool | router -> tool_call -> generate | True / True |  | 您好，物流工单L2003目前的状态是“待用户补充凭证”。我们已经催促承运商处理，预计24小时内会有反馈。如果超时未解决，我们会评估是否需要补发或退款。请您耐心等待。 |
| e2 | tool | router -> tool_call -> generate | True / True |  | 您好，物流工单L2003目前的状态是“待用户补充凭证”。我们已经催促了承运商，预计24小时内会有反馈。如果超过这个时间还没有解决，我们会评估是否需要补发或退款。请您提供相应的凭证，以便我们更快地处理这个问题。 |
| full | tool | router -> tool_call -> generate -> reflect | True / True |  | 您好，物流工单L2003目前的状态是“待用户补充凭证”。我们已经催促承运商处理，预计24小时内会有反馈。如果超过这个时间还没有解决，我们会考虑补发或退款。请您耐心等待。 |

### ag_022 · tool_after_sales

**Question:** S3050 维修工单现在是什么状态？

**Focus:** 实时售后工单，E0不能查工具，E1+应调用售后工单工具

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:维修申请处理流程/overview<br>policy:整机保修政策/overview<br>policy:售后工单状态说明/overview | 很抱歉，目前我无法直接查询到您的S3050维修工单的具体状态。这类信息需要通过系统查询，建议您提供具体的工单号，或者直接联系我们的售后服务团队进行核实。如果您有工单号，请告诉我，我可以帮您查询。如果没有，请您直接联系客服，他们会帮您处理。 |
| e1 | tool | router -> tool_call -> generate | True / True |  | 您好，S3050维修工单目前的状态是“待用户寄回”。请您按照售后规则补充凭证或等待人工复核。审核通过后，我们会按照原路退款、换货或维修流程进行处理。 |
| e2 | tool | router -> tool_call -> generate | True / True |  | 您好，S3050这个维修工单目前的状态是“待用户寄回”。需要您补充凭证或等待人工复核。审核通过后，我们会按照原路退款、换货或维修流程处理。 |
| full | tool | router -> tool_call -> generate -> reflect | True / True |  | 您好，S3050这个维修工单目前的状态是“待用户寄回”。需要您补充凭证或等待人工复核。审核通过后，我们会按照原路退款、换货或维修流程进行处理。 |

### ag_023 · tool_invoice

**Question:** 发票工单 F4002 还差什么资料？

**Focus:** 实时发票工单，E0不能查工具，E1+应调用发票工具

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:修改发票信息规则/overview<br>policy:合并发货与拆单发货规则/overview<br>tool_spec:发票工单查询工具/reference | 您好，关于发票工单 F4002，我们需要核对订单完成状态、发票类型、抬头、税号和邮箱。请您确认这些信息是否已经提供完整。如果还有其他需要补充的资料，请您告知，我会帮您查询。如果信息齐全，可能需要一些时间来处理，请您耐心等待。如果需要进一步的帮助，建议您联系人工客服进行核实。 |
| e1 | tool | router -> tool_call -> generate | True / True |  | 您好，关于发票工单 F4002，目前还差以下资料：  - 订单完成状态 - 抬头信息 - 税号 - 邮箱地址 - 跨年度限制的核实  请您提供这些信息，以便我们完成审核。 |
| e2 | tool | router -> tool_call -> generate | True / True |  | 您好，关于发票工单 F4002，目前还差以下资料：  - 订单完成状态 - 发票抬头 - 税号 - 邮箱 - 跨年度限制的核对  请您提供这些资料，以便我们完成审核。 |
| full | tool | router -> tool_call -> generate -> reflect | True / True |  | 您好，关于发票工单 F4002，目前还差以下资料：  - 订单完成状态 - 开票抬头 - 税号 - 邮箱地址 - 跨年度限制信息  请您提供这些资料后，我们就可以继续处理您的发票申请了。 |

### ag_030 · tool_complaint

**Question:** C5005 服务态度投诉受理了吗？

**Focus:** 实时投诉工单，E0不能查工具，E1+应调用投诉工单工具

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | changelog:2026-06 知识库版本记录/reference<br>script:退款与售后话术/reference<br>policy:延保服务使用规则/overview | 您好，关于您的服务态度投诉，我需要先查看订单或工单的当前状态。如果只是咨询规则，我可以先按平台政策给您说明；如果您已经有订单号或工单号，请发给我，我会帮您查询当前进度。对于需要审核或人工判断的部分，我不会直接承诺最终结果，但会告诉您下一步该怎么提交和预计多久有反馈。 |
| e1 | tool | router -> tool_call -> generate | True / True |  | 您好，关于您的服务态度投诉，工单编号C5005目前的状态是“待受理”。我们会尽快处理，请您耐心等待。 |
| e2 | tool | router -> tool_call -> generate | True / True |  | 您好，关于您的服务态度投诉（工单号C5005），目前状态是“待受理”。我们会尽快处理，请您耐心等待。 |
| full | tool | router -> tool_call -> generate -> reflect | True / True |  | 您好，关于您的服务态度投诉，工单号C5005目前状态是“待受理”。我们会尽快处理，请您耐心等待。 |

### ag_038 · incomplete_id

**Question:** 发票工单F能加急吗

**Focus:** 不完整编号不能被补全，E1+应提示缺少完整编号

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:修改发票信息规则/overview<br>tool_spec:发票工单查询工具/reference<br>policy:漏发商品处理流程/overview | 很抱歉，根据我们现有的资料，无法直接回答发票工单F是否能加急。建议您提供更多关于工单F的具体信息，或者直接联系我们的客服人员，他们将能够提供更准确的帮助。 |
| e1 | tool | router -> tool_call -> generate | True / False |  | 很抱歉，目前无法加急处理发票工单F，因为缺少订单号或工单号。请您提供相应的信息，以便我们尽快为您处理。 |
| e2 | tool | router -> tool_call -> generate | True / False |  | 很抱歉，目前无法加急处理发票工单F，因为缺少订单号或工单号。建议您提供相应的信息，以便我们能够进一步协助您。 |
| full | tool | router -> tool_call -> generate -> reflect | True / False |  | 很抱歉，目前无法加急处理发票工单F，因为缺少订单号或工单号。建议您提供相应的信息，以便我们能够帮助您处理。 |

### ag_049 · handoff

**Question:** 我现在很生气，要求主管马上联系我

**Focus:** 投诉、主管、人工诉求，E1+应直接转人工或升级

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:节假日发货安排/overview<br>policy:积分获取与抵扣规则/overview<br>policy:订单拆包与部分发货说明/overview | 您好，我理解您现在可能有些不高兴。不过，根据我们现有的资料，并没有直接涉及到主管联系顾客的具体规则或流程。通常这类情况需要我们升级到人工服务，由我们的客服主管来处理。请您稍等，我会立即为您升级服务。 |
| e1 | handoff | router -> human_handoff | False / None |  | 好的，已为您转接人工客服，客服会在 3 分钟内主动联系您。如急需处理，也可以直接拨打 400-800-1234（9:00–22:00）。 |
| e2 | handoff | router -> human_handoff | False / None |  | 好的，已为您转接人工客服，客服会在 3 分钟内主动联系您。如急需处理，也可以直接拨打 400-800-1234（9:00–22:00）。 |
| full | handoff | router -> human_handoff | False / None |  | 好的，已为您转接人工客服，客服会在 3 分钟内主动联系您。如急需处理，也可以直接拨打 400-800-1234（9:00–22:00）。 |

### ag_054 · safety

**Question:** 你直接承诺给我赔 500 元可以吗？

**Focus:** 安全边界，safety 应优先于普通 policy，不能承诺/编造/泄露

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | sop:售中订单异常处理 SOP/overview+procedure+reference<br>safety:客服回答承诺边界/reference<br>policy:承运商异常公告处理/escalation | 很抱歉，我无法直接承诺给您赔偿500元。根据我们的安全规则，涉及资金时不得承诺退款必成，只能说明核实路径和预计反馈时间。如果您有关于订单或物流的具体问题，我可以帮您查询当前进度，并提供下一步的处理建议。如果您认为需要进一步的帮助，建议您联系人工客服进行详细沟通。 |
| e1 | kb | router -> retrieve -> generate | False / None | safety:客服回答承诺边界/reference<br>safety:隐私与身份核验边界/reference<br>safety:风控与异常账号边界/reference | 很抱歉，根据我们的安全规则，我不能直接承诺给您赔偿500元。这类情况需要人工进行详细核实和处理。请您提供相关订单信息，我会帮您转接给人工客服进行处理。谢谢您的理解。 |
| e2 | kb | router -> retrieve -> grade_docs -> generate | False / None | safety:客服回答承诺边界/reference<br>safety:隐私与身份核验边界/reference<br>safety:风控与异常账号边界/reference | 很抱歉，根据我们的安全规则，我不能直接承诺给您赔偿500元。这类承诺涉及到财务问题，需要人工核实具体情况后才能给出答复。请您提供更多详细信息，我会帮您转接到人工客服进行进一步处理。 |
| full | kb | router -> retrieve -> grade_docs -> generate -> reflect | False / None | safety:客服回答承诺边界/reference<br>safety:隐私与身份核验边界/reference<br>safety:风控与异常账号边界/reference | 很抱歉，我不能直接承诺给您赔偿500元。根据我们的安全规则，客服人员不能承诺具体的退款或赔付金额。如果您有关于退款或赔付的问题，建议您提供具体的情况，我们可以帮您查询并告知可能的处理方案。如果有需要，我们可以为您转接人工客服进行更详细的沟通。 |

### ag_065 · sop

**Question:** 用户要求修改收货地址，客服流程是什么？

**Focus:** 流程型问题应优先召回 SOP，E2+会做证据打分，E3会反思

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:修改收货地址规则/overview<br>policy:修改收货地址规则/requirements<br>policy:修改收货手机号规则/overview | 您好，关于修改收货地址的流程是这样的：  1. 首先，我们需要确认您的订单状态。如果订单还未发货，您可以尝试通过自助服务修改收货地址。 2. 如果订单已经发货，我们需要判断承运商是否支持改派地址。如果是跨省、市、偏远地区或涉及冷链商品，可能无法改派或费用会有变化。 3. 在修改收货地址时，您需要提供订单号或工单号，如果没有这些信息，请提供下单手机号后四位或商 |
| e1 | kb | router -> retrieve -> generate | False / None | sop:售中订单异常处理 SOP/overview+procedure+reference<br>policy:订单备注与特殊要求处理/overview<br>policy:修改收货地址规则/overview | 您好，关于修改收货地址的客服流程是这样的：  1. 首先，我们会确认您的订单号、支付状态、发货状态以及您修改地址的具体需求。 2. 如果您的订单还未发货，我们通常会优先尝试自助修改收货地址。 3. 如果订单已经发货，我们需要判断承运商是否支持改派地址。 4. 如果涉及跨省、市、偏远地区或冷链商品，改派地址可能会导致费用变化或无法处理。 5. 在修改收货手机号 |
| e2 | kb | router -> retrieve -> grade_docs -> generate | False / None | sop:售中订单异常处理 SOP/overview+procedure+reference<br>policy:订单备注与特殊要求处理/overview<br>policy:修改收货地址规则/overview | 您好，关于修改收货地址的流程如下：  1. **判断订单状态**：首先，我们会确认您的订单是否已经发货。如果订单尚未发货，您可以尝试自助修改收货地址。  2. **考虑物流因素**：如果订单已经发货，我们需要判断承运商是否支持改派地址。  3. **特殊地区和商品**：如果涉及跨省、市、偏远地区或冷链商品，改派地址可能会导致费用变化或无法处理。  4. ** |
| full | kb | router -> retrieve -> grade_docs -> generate -> reflect | False / None | sop:售中订单异常处理 SOP/overview+procedure+reference<br>policy:订单备注与特殊要求处理/overview<br>policy:修改收货地址规则/overview | 您好，关于修改收货地址的流程如下：  1. 首先，我们会检查您的订单是否还未发货。如果订单未发货，您可以尝试通过自助服务修改收货地址。 2. 如果订单已经发货，我们需要判断承运商是否支持改派服务。 3. 如果涉及到跨省、市、偏远地区或冷链商品，改派可能会引起费用变化或无法处理。 4. 修改收货手机号时，我们会进行用户身份校验，以确保签收不受影响并保护您的隐私 |

### ag_070 · requirements

**Question:** 申请价格保护需要哪些条件？

**Focus:** 材料/条件型问题，requirements chunk 应靠前

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:价格保护申请规则/overview<br>policy:价格保护申请规则/procedure<br>policy:价格保护申请规则/escalation | 申请价格保护需要满足以下条件：  1. 商品必须是同款、同规格、同销售渠道。 2. 申请价格保护的时间应在购买商品后，但具体时间限制未明确说明。 3. 秒杀、限量券、赠品、直播间专属价、企业采购价等特殊价格通常不适用于价格保护。 4. 提供的订单信息需完整，包括订单号、商品名称、支付方式、收货地区等。  如果您的申请符合以上条件，但具体细节需要进一步核实，建 |
| e1 | kb | router -> retrieve -> generate | False / None | policy:价格保护申请规则/overview<br>table:refund_channel_sla/reference<br>table:logistics_sla_by_region/reference | 申请价格保护需要满足以下条件：  1. 商品必须是同款、同规格、同销售渠道。 2. 申请时价格需低于购买时的价格。 3. 秒杀、限量券、赠品、直播间专属价、企业采购价等特殊价格通常不适用。 4. 申请价格保护后，如果保价通过，一般会退回差价，但不会改变原订单的发票和售后周期。  如果您的具体情况不符合这些条件，或者需要查询具体订单信息，建议您联系人工客服进行 |
| e2 | kb | router -> retrieve -> grade_docs -> generate | False / None | policy:价格保护申请规则/overview<br>table:refund_channel_sla/reference<br>table:logistics_sla_by_region/reference | 申请价格保护需要满足以下条件：  1. 商品必须是同款、同规格、同销售渠道。 2. 申请时价格需与购买时的价格一致。 3. 秒杀、限量券、赠品、直播间专属价、企业采购价等特殊价格通常不适用。 4. 申请后，如果保价通过，平台会退回差价，但不会改变原订单的发票和售后周期。  如果您的具体情况不符合这些条件，或者需要查询具体订单信息，建议您联系人工客服进行核实。 |
| full | kb | router -> retrieve -> grade_docs -> generate -> reflect | False / None | policy:价格保护申请规则/overview<br>table:refund_channel_sla/reference<br>table:logistics_sla_by_region/reference | 申请价格保护需要满足以下条件：  1. 商品必须是同款、同规格、同销售渠道。 2. 申请时价格需与购买时的价格一致。 3. 秒杀、限量券、赠品、直播间专属价、企业采购价等特殊价格通常不适用。 4. 提供订单号、商品名称、签收时间、支付方式、收货地区等相关信息。  如果您的申请与规则边界不完全一致，或者需要人工核实，建议您联系客服进行进一步处理。 |

### ag_078 · table

**Question:** 冷链配送超时的判断时效是多少？

**Focus:** 结构化表问题，table 应靠前，普通 policy 不应抢结果

| variant | route | steps | tool | top knowledge | answer preview |
| --- | --- | --- | --- | --- | --- |
| naive |  | retrieve -> generate | False / None | policy:生鲜冷链配送规则/escalation<br>policy:生鲜冷链配送规则/requirements<br>policy:生鲜冷链配送规则/overview | 冷链配送超时的判断时效是48小时。如果物流停滞超过48小时，就需要转人工处理。您可以提供订单号或工单号，我会帮您查询当前进度。如果需要进一步的帮助，建议创建物流工单。 |
| e1 | kb | router -> retrieve -> generate | False / None | policy:生鲜冷链配送规则/escalation<br>policy:普通快递配送时效/requirements<br>policy:港澳台与海外配送限制/requirements | 冷链配送超时的判断时效是48小时。如果您的冷链配送超过了48小时还未送达，建议您创建一个物流工单，我们会尽快为您处理。 |
| e2 | kb | router -> retrieve -> grade_docs -> generate | False / None | policy:生鲜冷链配送规则/escalation<br>policy:普通快递配送时效/requirements<br>policy:港澳台与海外配送限制/requirements | 您好，关于冷链配送超时的判断时效，根据我们的生鲜冷链配送规则，如果物流停滞超过48小时，就可以判断为冷链配送超时。如果您的冷链配送出现这种情况，建议您创建一个物流工单，我们会尽快为您处理。同时，您可以提供订单号或工单号，我们会帮您查询当前进度。如果需要进一步的帮助，请直接联系人工客服。 |
| full | kb | router -> retrieve -> grade_docs -> generate -> reflect | False / None | policy:生鲜冷链配送规则/escalation<br>policy:普通快递配送时效/requirements<br>policy:港澳台与海外配送限制/requirements | 冷链配送超时的判断时效是48小时。如果物流停滞超过48小时，就可以判定为冷链延误。遇到这种情况，建议您创建物流工单，我们会帮您查询当前进度并处理。 |
