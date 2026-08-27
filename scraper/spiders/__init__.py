"""会议 spider 包。新增会议在此注册到 SPIDERS 映射。"""
from .pharmasug import PharmaSUGSpider
from .phuse import PHUSESpider
from .sasgf import SASGlobalForumSpider
from .rpharma import RPharmaSpider
from .wayback_pharmasug import WaybackPharmaSUGSpider
from .pharmasug_cn import PharmaSUGChinaSpider
from .pharmasug_jp import PharmaSUGJapanSpider
from .mwsug import MWSUGSpider
from .sasinnovate import SASInnovateSpider
from .psi import PSISpider
from .cdisc import CDISCInterchangeSpider
from .pharmarug import PharmaRugSpider
from .userconf import UserConfSpider
from .rmedicine import RMedicineSpider

# 会议代码 -> spider 类。main.py 据此调度。
SPIDERS = {
    "pharmasug-us": PharmaSUGSpider,
    "pharmasug-cn": PharmaSUGChinaSpider,
    "pharmasug-wayback": WaybackPharmaSUGSpider,
    "phuse-eu": PHUSESpider,
    "phuse-us": PHUSESpider,
    "phuse-apac": PHUSESpider,
    "phuse-css": PHUSESpider,
    "sgf": SASGlobalForumSpider,
    "sugi": SASGlobalForumSpider,
    "r-pharma": RPharmaSpider,
    "mwsug": MWSUGSpider,
    "sas-innovate": SASInnovateSpider,
    "pharmasug-jp": PharmaSUGJapanSpider,
    "psi": PSISpider,
    "cdisc-interchange": CDISCInterchangeSpider,
    "pharmarug-cn": PharmaRugSpider,
    "user-r": UserConfSpider,
    "r-medicine": RMedicineSpider,
}
