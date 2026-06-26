#!/usr/bin/env python3
"""Compare sector classifications from different MCP data sources."""
import json

# === 1. 用户定义的 14 个 THS 一级板块 ===
USER_SECTORS = ['能源金属','半导体','元件','电子化学品','化学纤维','军工电子','消费电子','医疗服务','光学光电子','其他电子','小金属','贵金属','机场航运','工业金属']

# === 2. EastMoney 行业板块（top 50）===
EM_INDUSTRY = [
    "元件","印制电路板","电子","非银金融","证券Ⅲ","证券Ⅱ","数字芯片设计","半导体","食品饮料",
    "面板","被动元件","游戏Ⅲ","游戏Ⅱ","钨","其他专用设备","保险Ⅲ","保险Ⅱ","专用设备","白酒Ⅲ","白酒Ⅱ",
    "其他计算机设备","光学光电子","调味发酵品Ⅲ","调味发酵品Ⅱ","自动化设备","航空机场","冶钢辅料",
    "航空运输","半导体设备","地面兵装Ⅲ","地面兵装Ⅱ","合成树脂","冶钢原料","激光设备","白色家电",
    "计算机设备","垂直应用软件","其他自动化设备","集成电路封测","金属新材料","空调","环保设备Ⅲ",
    "环保设备Ⅱ","商贸零售","钢铁","氯碱","磁性材料","旅游零售Ⅲ","旅游零售Ⅱ","炭黑"
]

# === 3. EastMoney 概念板块（top 50）===
EM_CONCEPT = [
    "PCB","科技风格","券商概念","半导体概念","金融地产风格","HS300_","OLED","互联网金融",
    "MiniLED","基金重仓","深证100R","虚拟机器人","参股银行","AI芯片","长江三角","趋势股",
    "MLCC","参股期货","超级电容","百元股","存储芯片","证金持股","上证50_","石墨烯","MicroLED",
    "3D打印","新零售","屏下摄像","鸿蒙概念","高带宽内存","被动元件概念","电子纸概念","LED概念",
    "BC电池","科创板做市商","华为海思","小米概念","柔性屏(折叠屏)","电子竞技","玻璃基板",
    "大盘股","消费风格","参股券商","荣耀概念","AI手机","智能穿戴","味蕾经济","钙钛矿电池",
    "科创板做市股","先进封装"
]

# === 4. 此前从 akshare 获取的 THS 行业名称（手动整理 90 个中的相关条目）===
# 基于此前成功获取的数据
THS_BOARDS = [
    "能源金属","半导体","元件","电子化学品","化学纤维","军工电子","消费电子","医疗服务",
    "光学光电子","其他电子","小金属","贵金属","机场航运","工业金属",
    # THS 还有这些行业不在用户列表中
    "汽车","电力设备","机械设备","基础化工","医药生物","食品饮料","银行","非银金融",
    "房地产","建筑装饰","公用事业","计算机","通信","传媒","国防军工","石油石化",
    "有色金属","煤炭","交通运输","建筑材料","农林牧渔"
]

print("=" * 80)
print(f"{'分类':^20} | {'用户THS 14个':^30} | {'东财行业板块':^18} | {'东财概念板块':^18}")
print("=" * 80)

for s in USER_SECTORS:
    in_ths = s in THS_BOARDS
    # Find in EM industry
    em_industry_matches = [n for n in EM_INDUSTRY if s[:2] in n or n[:2] in s]
    em_ind = "✓ 近似" if any(s[:2] in n for n in EM_INDUSTRY) else "✗ 无"
    em_con = "✓ 找到" if any(s[:2] in n for n in EM_CONCEPT) else "✗ 无"

    em_ind_detail = ""
    for n in EM_INDUSTRY:
        if s[:3] in n or (len(n) >= 2 and n[:3] in s):
            em_ind_detail = n
            break

    em_con_detail = ""
    for n in EM_CONCEPT:
        if s[:3] in n or (len(n) >= 2 and n[:3] in s):
            em_con_detail = n
            break

    # EM industry exact match
    em_ind_exact = "✓" if s in EM_INDUSTRY else ("～" + (em_ind_detail or "—"))
    em_con_exact = "✓" if s in EM_CONCEPT else ("～" + (em_con_detail or "—"))

    ths_status = "✓" if in_ths else "⚠"
    print(f"{s:^20} | {ths_status:^30} | {em_ind_exact:^18} | {em_con_exact:^18}")

print()
print("=" * 80)
print("总结:")
# Count exact matches
ths_match = sum(1 for s in USER_SECTORS if s in THS_BOARDS)
em_ind_match = sum(1 for s in USER_SECTORS if s in EM_INDUSTRY)
em_con_match = sum(1 for s in USER_SECTORS if s in EM_CONCEPT)
print(f"  用户 14 个板块中:")
print(f"  - 同花顺 THS 数据库 → {ths_match}/14 完全匹配")
print(f"  - 东财 行业板块(top50) → {em_ind_match}/14 完全匹配（另有近似匹配）")
print(f"  - 东财 概念板块(top50) → {em_con_match}/14 完全匹配（另有近似匹配）")
