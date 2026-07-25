"""CosyVoice 系统内置音色数据（来自阿里云百炼官方文档）。

仅包含当前插件支持的模型：cosyvoice-v3-flash、cosyvoice-v3-plus。
v3.5 系列不支持系统音色，v2/v1 为旧版模型暂不纳入。
"""

# 模型能力矩阵
MODEL_CAPABILITIES = {
    "cosyvoice-v3.5-plus": {
        "system_voices": False,
        "custom_voices": True,
        "instruction_custom": True,  # 复刻/设计音色支持任意指令
        "instruction_system": None,  # 无系统音色
    },
    "cosyvoice-v3.5-flash": {
        "system_voices": False,
        "custom_voices": True,
        "instruction_custom": True,
        "instruction_system": None,
    },
    "cosyvoice-v3-plus": {
        "system_voices": True,
        "custom_voices": True,
        "instruction_custom": False,  # 复刻/设计音色不支持指令
        "instruction_system": "fixed",  # 系统音色需固定格式
    },
    "cosyvoice-v3-flash": {
        "system_voices": True,
        "custom_voices": True,
        "instruction_custom": True,  # 复刻/设计音色支持任意指令
        "instruction_system": "fixed",  # 系统音色需固定格式
    },
}

# 支持语言列表
SUPPORTED_LANGUAGES = [
    {"code": "zh", "name": "中文"},
    {"code": "en", "name": "英语"},
    {"code": "ja", "name": "日语"},
    {"code": "ko", "name": "韩语"},
    {"code": "fr", "name": "法语"},
    {"code": "de", "name": "德语"},
    {"code": "ru", "name": "俄语"},
    {"code": "pt", "name": "葡萄牙语"},
    {"code": "th", "name": "泰语"},
    {"code": "id", "name": "印尼语"},
    {"code": "vi", "name": "越南语"},
]

# 系统音色列表
# 格式: (voice参数, 名称, 特质, 是否支持Instruct)
SYSTEM_VOICES: dict[str, list[tuple[str, str, str, bool]]] = {
    "cosyvoice-v3-plus": [
        ("longanyang", "龙安洋", "阳光大男孩", True),
        ("longanhuan", "龙安欢", "欢脱元气女", True),
    ],
    "cosyvoice-v3-flash": [
        # 社交陪伴（标杆音色）
        ("longanyang", "龙安洋", "阳光大男孩", True),
        ("longanhuan_v3", "龙安欢(V3)", "欢脱元气女(方言)", True),
        ("longanhuan", "龙安欢", "欢脱元气女", True),
        # 童声
        ("longhuhu_v3", "龙呼呼", "天真烂漫女童", True),
        ("longpaopao_v3", "龙泡泡", "飞天泡泡音", False),
        ("longjielidou_v3", "龙杰力豆", "阳光顽皮男", False),
        ("longxian_v3", "龙仙", "豪放可爱女", False),
        ("longling_v3", "龙铃", "稚气呆板女", False),
        ("longshanshan_v3", "龙闪闪", "戏剧化童声", False),
        ("longniuniu_v3", "龙牛牛", "阳光男童声", False),
        # 方言
        ("longjiaxin_v3", "龙嘉欣", "优雅粤语女", False),
        ("longjiayi_v3", "龙嘉怡", "知性粤语女", False),
        ("longanyue_v3", "龙安粤", "欢脱粤语男", False),
        ("longlaotie_v3", "龙老铁", "东北直率男", False),
        ("longshange_v3", "龙陕哥", "原味陕北男", False),
        ("longanmin_v3", "龙安闽", "清纯萝莉女(闽南)", False),
        # 出海营销
        ("loongkyong_v3", "loongkyong", "韩语女", False),
        ("loongriko_v3", "Riko", "二次元霓虹女", False),
        ("loongtomoka_v3", "loongtomoka", "日语女", False),
        ("loongabby_v3", "loongabby", "美式英文女", False),
        ("loongandy_v3", "loongandy", "美式英文男", False),
        ("loongannie_v3", "loongannie", "美式英文女", False),
        ("loongava_v3", "loongava", "美式英文女", False),
        ("loongbeth_v3", "loongbeth", "美式英文女", False),
        ("loongbetty_v3", "loongbetty", "美式英文女", False),
        ("loongcally_v3", "loongcally", "美式英文女", False),
        ("loongcindy_v3", "loongcindy", "美式英文女", False),
        ("loongdavid_v3", "loongdavid", "美式英文男", False),
        ("loongdonna_v3", "loongdonna", "美式英文女", False),
        ("loongemily_v3", "loongemily", "英式英文女", False),
        ("loongeric_v3", "loongeric", "英式英文男", False),
        ("loongluna_v3", "loongluna", "英式英文女", False),
        ("loongluca_v3", "loongluca", "英式英文男", False),
        ("loongtomoya_v3", "loongtomoya", "日语男", False),
        ("loongyuuna_v3", "Yuuna", "日语女", False),
        ("loongyuuma_v3", "Yuuma", "日语男", False),
        ("loongjihun_v3", "Jihun", "韩语男", False),
        ("loongindah_v3", "loongindah", "印尼女", False),
        # 诗词朗诵
        ("longfei_v3", "龙飞", "热血磁性男", False),
        # 电话销售
        ("longyingxiao_v3", "龙应笑", "清甜推销女", False),
        # 客服
        ("longyingxun_v3", "龙应询", "年轻青涩男", False),
        ("longyingjing_v3", "龙应静", "低调冷静女", False),
        ("longyingling_v3", "龙应聆", "温和共情女", False),
        ("longyingtao_v3", "龙应桃", "温柔淡定女", False),
        # 语音助手
        ("longxiaochun_v3", "龙小淳", "知性积极女", False),
        ("longxiaoxia_v3", "龙小夏", "沉稳权威女", False),
        ("longyumi_v3", "YUMI", "正经青年女", False),
        ("longanyun_v3", "龙安昀", "居家暖男", False),
        ("longanwen_v3", "龙安温", "优雅知性女", False),
        ("longanli_v3", "龙安莉", "利落从容女", False),
        ("longanlang_v3", "龙安朗", "清爽利落男", False),
        ("longyingmu_v3", "龙应沐", "优雅知性女", False),
        # 社交陪伴
        ("longantai_v3", "龙安台", "嗲甜台湾女", False),
        ("longhua_v3", "龙华", "元气甜美女", False),
        ("longcheng_v3", "龙橙", "智慧青年男", False),
        ("longze_v3", "龙泽", "温暖元气男", False),
        ("longzhe_v3", "龙哲", "呆板大暖男", False),
        ("longyan_v3", "龙颜", "温暖春风女", False),
        ("longxing_v3", "龙星", "温婉邻家女", False),
        ("longtian_v3", "龙天", "磁性理智男", False),
        ("longwan_v3", "龙婉", "细腻柔声女", False),
        ("longqiang_v3", "龙嫱", "浪漫风情女", False),
        ("longfeifei_v3", "龙菲菲", "甜美娇气女", False),
        ("longhao_v3", "龙浩", "多情忧郁男", False),
        ("longanrou_v3", "龙安柔", "温柔闺蜜女", False),
        ("longhan_v3", "龙寒", "温暖痴情男", False),
        ("longanzhi_v3", "龙安智", "睿智轻熟男", False),
        ("longanling_v3", "龙安灵", "思维灵动女", False),
        ("longanya_v3", "龙安雅", "高雅气质女", False),
        ("longanqin_v3", "龙安亲", "亲和活泼女", False),
        # 有声书
        ("longmiao_v3", "龙妙", "抑扬顿挫女", False),
        ("longsanshu_v3", "龙三叔", "沉稳质感男", False),
        ("longyuan_v3", "龙媛", "温暖治愈女", False),
        ("longyue_v3", "龙悦", "温暖磁性女", False),
        ("longxiu_v3", "龙修", "博才说书男", False),
        ("longnan_v3", "龙楠", "睿智青年男", False),
        ("longwanjun_v3", "龙婉君", "细腻柔声女", False),
        ("longyichen_v3", "龙逸尘", "洒脱活力男", False),
        ("longlaobo_v3", "龙老伯", "沧桑岁月爷", False),
        ("longlaoyi_v3", "龙老姨", "烟火从容阿姨", False),
        # 短视频配音
        ("longjiqi_v3", "龙机器", "呆萌机器人", False),
        ("longhouge_v3", "龙猴哥", "经典猴哥", False),
        ("longdaiyu_v3", "龙黛玉", "娇率才女音", False),
        # 直播带货
        ("longanran_v3", "龙安燃", "活泼质感女", False),
        ("longanxuan_v3", "龙安宣", "经典直播女", False),
        # 新闻播报
        ("longshuo_v3", "龙硕", "博才干练男", False),
        ("longshu_v3", "龙书", "沉稳青年男", False),
        ("loongbella_v3", "Bella3.0", "精准干练女", False),
    ],
}


def get_system_voices_for_model(model: str) -> list[dict]:
    """获取指定模型的系统音色列表（字典格式）。"""
    voices = SYSTEM_VOICES.get(model, [])
    return [
        {"voice": v[0], "name": v[1], "trait": v[2], "instruct": v[3]}
        for v in voices
    ]


def get_available_models(mode: str) -> list[str]:
    """根据模式获取可用模型列表。"""
    if mode == "system":
        return [m for m, c in MODEL_CAPABILITIES.items() if c["system_voices"]]
    else:  # custom（复刻 / 设计）
        return [m for m, c in MODEL_CAPABILITIES.items() if c["custom_voices"]]


def get_instruction_support(model: str, voice_type: str) -> str:
    """获取指令支持类型。

    返回:
        "free" - 支持任意自然语言指令
        "fixed" - 仅支持固定格式指令
        "none" - 不支持指令
    """
    cap = MODEL_CAPABILITIES.get(model)
    if not cap:
        return "none"
    if voice_type == "system":
        if cap["instruction_system"] == "fixed":
            return "fixed"
        return "none"
    else:  # custom（复刻 / 设计）
        if cap["instruction_custom"]:
            return "free"
        return "none"
